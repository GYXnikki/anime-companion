# ADR-0001 事件日志的 P0 形态

- 日期：2026-11-02
- 状态：Accepted
- 关联：`docs/design.md` §3、§5；`docs/specs/0001-text-chat-mvp.md`

## Context

事件日志是唯一真相层，事件不可修改，schema 一旦有数据就只能追加 migration。
P0 要同时满足三个需求：

1. 能回答“这条回复属于哪条用户消息”（失败、重试、安全兜底会让事件顺序不再成对）。
2. 危机路径要写 `user.text`、`safety.triggered`、`safety.responded` 三条事件，不能出现“用户表达了危机但系统没有回应记录”的半截状态。
3. 本地还没有任何数据库文件，`0001_init.sql` 尚未在任何环境落地，此刻改表是零成本。

`docs/design.md` A.2 列出了 `schema_version`、`turn_id`、`caused_by`、`client_event_id` 四个字段，
`docs/specs/0001` §9.1 只定义了六列，两者不一致。

## Options

- **A. 严格按 spec 六列**：实现最小，但归属只能靠 seq 相邻推断，失败/重试后不可靠；以后回填 `turn_id` 需要猜测。
- **B. 只加 `turn_id`**：把“一轮对话”显式化，其余字段延后。
- **C. 加 `turn_id` + `client_event_id`**：同时做幂等，但要改 `POST /messages` 请求体，属于接口变更。
- **D. 四个字段全加**：最贴近 design.md，但 P0 会多出暂时没有读取方的列。

## Decision

选 **B**：

- `events` 增加 `turn_id TEXT`（可空；`session.started` 为 NULL），并建索引 `idx_events_turn_id`。
  每个用户消息生成一个 ULID，同一轮的 `user.text`、`assistant.completed`/`assistant.failed`、`safety.*` 共享该值。
- 其余字段延后：
  - `schema_version`：P0 所有事件都是 v1，读取时默认 1；以后 `ALTER TABLE ... DEFAULT 1` 成本低。
  - `caused_by`：`turn_id` 已表达因果。
  - `client_event_id`：P0 没有前端重试路径；等做幂等时随请求体一起加。
  - `actor`：不建列，由 `type` 推导（每个 type 只有一个 actor），见 `ACTOR_BY_TYPE`。
- `EventStore.append` 接受 1..N 条草稿，在同一个 `BEGIN IMMEDIATE` 事务内分配连续 `seq`、更新
  `sessions.last_seq`、全部插入；任一条失败则整批回滚。普通一轮仍调用两次（先 `user.text`，
  生成结束后写 `assistant.completed`），因为事务不能跨在 LLM 调用上。
- 存储用 SQLite + `aiosqlite` + 手写 SQL；`seq` 不依赖 `AUTOINCREMENT`，保证可迁移。
- 上下文窗口：最近 20 轮，一轮 = 一条 `user.text` + 至多一条 assistant 回复；失败轮保留用户消息、不补 assistant。

## Consequences

- 事件行能直接按 `turn_id` 分组，回放和排障不需要顺序推断。
- 危机路径的三条事件原子落库，不会产生半截状态。
- 编辑了初始迁移（现为 `alembic/versions/0001_init.py`）而不是新增修订：因为没有任何已部署数据库。如果别人的环境已经跑过 migrate，
  这个决定不成立，必须改为追加 migration。
- 多进程/多 worker 时，`seq` 仍由 SQLite 事务保证，但“同会话并发返回 409”的进程内锁会失效；
  P0 明确只跑单进程。
- 客户端断开时按 spec 写 `assistant.failed(code=client_disconnected)`；这与 design.md 里
  “completed + interrupted=true”不同，P0 以 spec 为准，等做语音打断时重审。

## Revisit when

- 需要多 worker 部署或换 PostgreSQL → 会话锁改为数据库租约。
- 前端开始重试请求 → 加 `client_event_id` 与部分唯一索引。
- 事件 schema 需要升级 → 加 `schema_version` 并实现 upcast。
- 做语音打断 → 重新决定断开/打断的落库语义。
- 接入真实 LLM → `assistant.completed` 的 tokens/latency 才有真实值。
