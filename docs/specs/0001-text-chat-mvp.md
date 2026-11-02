# SPEC-0001 文字聊天 MVP

- 状态：Implemented（P0）
- 版本：v0.2
- 日期：2026-10-30（2026-11-02 实现）
- 关联：`docs/design.md`、`AGENTS.md`
- 目标周期：3–5 天

---

## 1. 背景与目标

先做一个最小可验证切片：用户能和固定角色进行流式文字对话，后端把对话写成事件日志，危机输入走固定兜底话术。

这个 spec 只验证四件事：

1. FastAPI + SSE 的流式链路能跑通
2. 事件日志能落库、能按会话回放
3. 对话上下文能正确装配
4. 安全兜底在 LLM 之前生效

**不追求**记忆、情绪、语音、Live2D、多用户。

---

## 2. 用户故事

1. 作为用户，我打开页面后能创建一个会话，并看到 AI 的流式回复。
2. 作为用户，我连续聊多轮，AI 能记住最近 20 轮的内容。
3. 作为用户，当我表达自伤/自杀等危机内容时，AI 不继续追问，而是给出固定安全话术和求助指引。
4. 作为开发者，我能按 `session_id` 回放某次会话的全部事件，定位问题。

---

## 3. 范围

### 3.1 范围内

- 创建会话
- 文字消息发送
- SSE 流式返回
- 最近 20 轮上下文
- 固定角色（单一 persona，不提供角色管理）
- 危机关键词规则 + 固定兜底话术
- 事件日志落 SQLite
- 事件回放接口
- 后端单测、契约测试、集成测试

### 3.2 范围外

- 语音、ASR、TTS
- Live2D、VTube Studio
- 长期记忆、摘要、记忆检索
- 情绪识别、表情驱动
- 角色卡管理、角色版本 CRUD
- 多用户、登录、权限
- PostgreSQL、pgvector
- 前端页面（本 spec 只做后端；前端另开 spec）
- 真实 LLM 供应商（先用 MockLlm，再接真实适配器）

---

## 4. P0 关键决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 角色 | 固定 `default@v1`，persona 写在代码/配置里 | 先验证链路，不做角色系统 |
| 上下文 | 最近 20 轮（user + assistant） | 简单、可预测、够 MVP |
| 输入上限 | 2000 字符 | 防止超长输入拖垮上下文 |
| 流式传输 | SSE | 文字场景最简单，自动重连 |
| 事件存储 | 只存语义事件，不存 token 级 delta | 避免写放大 |
| 安全 | 关键词规则先于 LLM；命中后不调用 LLM | 固定、可审计、不靠模型自由发挥 |
| 存储 | SQLite + aiosqlite + 手写 SQL | 单用户、零运维、可迁移 |
| 会话并发 | 每个 session 一把 asyncio 锁 | P0 单进程，避免同会话并发写 |
| 错误 | SSE `error` 事件 + `assistant.failed` 事件 | 失败不伪造回复 |

---

## 5. 接口契约

### 5.1 创建会话

```http
POST /api/sessions
```

响应 `201`：

```json
{
  "id": "01JABCDEF...",
  "character_id": "default",
  "character_version": "v1",
  "created_at": "2026-10-30T08:00:00.000Z"
}
```

规则：

- `id` 使用 ULID
- 创建时写入 `session.started` 事件
- 不接收客户端传入的 `character_version`

### 5.2 发送消息并流式回复

```http
POST /api/sessions/{session_id}/messages
Content-Type: application/json
Accept: text/event-stream
```

请求：

```json
{
  "text": "今天有点累"
}
```

成功响应 `200`，`Content-Type: text/event-stream`：

```text
event: delta
data: {"text":"听起来"}

event: delta
data: {"text":"今天不太容易。"}

event: done
data: {"message_id":"01J...","interrupted":false}
```

失败响应（流开始前）：

- `404`：session 不存在
- `422`：`text` 为空、全是空白、或超过 2000 字符
- `409`：同一 session 正在生成回复

失败响应（流开始后）：

```text
event: error
data: {"code":"llm_error","message":"模型暂时不可用，请重试"}
```

错误码：

| code | 含义 |
|---|---|
| `llm_timeout` | 模型超时 |
| `llm_error` | 模型返回错误 |
| `client_disconnected` | 客户端断开 |
| `internal_error` | 未分类错误 |

### 5.3 回放事件

```http
GET /api/sessions/{session_id}/events
```

响应 `200`：

```json
{
  "session_id": "01J...",
  "events": [
    {
      "id": "01J...",
      "seq": 1,
      "type": "user.text",
      "payload": { "text": "今天有点累" },
      "created_at": "2026-10-30T08:00:01.000Z"
    }
  ]
}
```

规则：

- 按 `seq` 升序
- 不返回敏感配置
- session 不存在返回 `404`

### 5.4 健康检查

保留现有：

```http
GET /health
```

响应：

```json
{"status":"ok"}
```

---

## 6. 事件契约

### 6.1 事件类型

| type | actor | payload | 说明 |
|---|---|---|---|
| `session.started` | system | `{character_id, character_version}` | 创建会话 |
| `user.text` | user | `{text}` | 用户输入 |
| `assistant.completed` | assistant | `{content, model, prompt_version, tokens_in, tokens_out, latency_ms}` | 正常回复完成 |
| `assistant.failed` | assistant | `{code, message}` | 回复失败 |
| `safety.triggered` | system | `{category, matched_keyword}` | 命中危机规则 |
| `safety.responded` | assistant | `{content, hotline_shown}` | 固定安全话术 |

### 6.2 不落库的事件

- LLM token 级 `delta`
- SSE 心跳
- 前端渲染状态

> 与 `docs/design.md` 的事件类型示例存在冲突：按该文档 A.2“不存 token 级 delta”，本 spec 只在传输层流式输出 delta，事件日志只落 `assistant.completed`。2026-11-02 已同步修正 design.md。

### 6.3 不变量

1. 事件只追加，不修改、不删除
2. 同一 session 内 `seq` 从 1 开始单调递增
3. 每条 `user.text` 最多对应一条 `assistant.completed` 或 `assistant.failed` 或 `safety.responded`
4. 命中危机规则时必须有 `safety.triggered` 和 `safety.responded`
5. 事件 `payload_json` 写入前必须通过 Pydantic 校验
6. `session.started` 是每个 session 的第一条事件

---

## 7. 对话流程

### 7.1 正常对话

```text
POST /messages
  → 校验 text
  → 获取 session
  → 获取 per-session 锁
  → 安全检查
      ├─ 命中 → 写 user.text → safety.triggered → safety.responded → 返回固定话术
      └─ 未命中
          → 写 user.text
          → 读取最近 20 轮事件
          → 装配上下文
          → 调 MockLlm / LlmPort 流式生成
          → SSE delta 输出（不落库）
          → 生成完成 → 写 assistant.completed
          → SSE done
  → 释放锁
```

### 7.2 失败

```text
LLM 超时/报错/客户端断开
  → SSE error（如果能写）
  → 写 assistant.failed
  → 释放锁
```

失败后不写 `assistant.completed`，用户可重试。

---

## 8. 安全兜底

### 8.1 规则

在调用 LLM 之前做关键词匹配，命中即走固定话术。

P0 关键词示例（不追求完整，后续由安全用例扩充）：

- 自杀、自残、不想活、活着没意思、结束生命
- 伤害自己、杀了自己、跳楼、割腕
- 不想活了、想消失

规则放在 `application/safety`，不依赖 LLM，纯函数可单测。

### 8.2 固定话术

> 我很在意你现在的感受。如果你正处在危险中，请先保证自己的安全：立即拨打 120 或 110，或联系身边可信的人陪着你。我是 AI，不能替代专业帮助，也不会继续追问细节。

要求：

- 不诊断、不分析、不追问细节
- 不建议具体方法
- 不继续调用 LLM
- 结果页/接口标明“不构成医疗建议”

### 8.3 事件

命中时写入：

```json
{"type":"safety.triggered","payload":{"category":"self_harm","matched_keyword":"不想活"}}
{"type":"safety.responded","payload":{"content":"我很在意你现在的感受……","hotline_shown":true}}
```

---

## 9. 数据与持久化

### 9.1 P0 表

```sql
sessions(
  id TEXT PRIMARY KEY,
  character_id TEXT NOT NULL,
  character_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
  last_seq INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)

events(
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
  seq INTEGER NOT NULL,
  type TEXT NOT NULL,
  turn_id TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(session_id, seq)
)

schema_migrations(
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
)
```

索引与时间：

- `UNIQUE(session_id, seq)` 已生成等价索引，不再额外建 `idx_events_session_seq`
- `idx_events_turn_id` 支撑按轮排查；`turn_id` 由应用生成，同一轮的 user / assistant / safety 事件共享
- `updated_at` 在每次追加事件时与 `last_seq` 同事务更新，表示最后活动时间
- `schema.sql` 是当前完整 schema 快照，全部 migration 应用后的结构必须与其一致（有测试守护）

### 9.2 暂不建的表

- `messages` 投影：P0 从事件重建上下文，等有性能/查询需求再加
- `memory_items`、`summaries`：后续 spec
- `characters`、`character_versions`：P0 固定角色，后续 spec

### 9.3 写入规则

- `seq` 分配：在同一个 SQLite 事务里更新 `sessions.last_seq` 并插入事件
- 不使用 `INSERT OR REPLACE`
- 时间统一 UTC ISO8601 带毫秒
- 数据库文件放 `backend/data/`，不提交仓库

### 9.4 迁移执行

- 手动执行：`cd backend && uv run python -m app.cli migrate`；`status` 查看已应用/待应用版本
- 应用启动只检查，不自动迁移；存在待应用 migration 时启动失败并提示上述命令
- migration 文件按 `0001_*.sql` 连续编号；版本断档、已应用版本缺文件时 CLI 和启动均报错

---

## 10. 验收标准

### 10.1 功能

- [x] `POST /api/sessions` 返回 201，数据库存在对应 session
- [x] 发送“你好”后，SSE 至少收到一个 `delta` 和一个 `done`
- [x] `GET /events` 返回 `session.started`、`user.text`、`assistant.completed`，`seq` 连续递增
- [x] 连续发送消息时，上下文包含最近 20 轮
- [x] 输入“我不想活了”时，不调用 LLM，返回固定安全话术
- [x] 危机事件包含 `safety.triggered` 和 `safety.responded`
- [x] 不存在的 session 返回 404
- [x] 空文本、超长文本返回 422
- [x] LLM 报错时返回 SSE `error`，并写入 `assistant.failed`
- [x] 同一 session 并发请求时，第二个请求返回 409 或排队（P0 选 409）

### 10.2 工程

- [x] `uv run pytest` 全绿
- [x] `uv run ruff check .` 通过
- [x] `uv run mypy app` 通过
- [x] 无密钥、无用户数据写入日志
- [x] 没有引入范围外依赖
- [x] `docs/design.md` 或本 spec 已同步新决策

---

## 11. 测试计划

### 11.1 单元测试

- `SafetyService`：命中/不命中、大小写/空格、多个关键词
- `ContextBuilder`：空历史、1 轮、20 轮、超过 20 轮
- 事件序列化：payload 校验失败时拒绝写入
- ULID / 时间格式

### 11.2 契约测试

- `EventStore.append` / `list_by_session`
- `LlmPort` Mock 实现：正常流、空流、异常流
- 同一 session 并发 append：seq 不重复

### 11.3 集成测试

- 创建 session → 发消息 → 解析 SSE → 回放事件
- 危机输入 → 固定话术 → 事件正确
- LLM 异常 → SSE error → `assistant.failed`
- 404 / 422 / 409

### 11.4 验证命令

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app
```

---

## 12. 任务拆分（2026-11-02 全部完成）

1. 补各包 `__init__.py`
2. `schema.sql` + `backend/migrations/0001_init.sql` + DB 初始化
3. `domain/events`：事件类型与 payload 模型
4. `domain/ports`：`EventStore`、`LlmPort`
5. `adapters/storage/sqlite_event_store.py`
6. `application/safety`：关键词规则 + 固定话术
7. `application/chat`：上下文装配 + ChatService
8. `adapters/llm/mock.py`
9. `transport/http/routes/chat.py`：session + SSE
10. 测试与验证
11. 更新 `docs/design.md` 中 `assistant.delta` 的冲突说明

每个任务单独验证；仓库尚未 `git init`，本次未产生提交。

---

## 13. 风险与待确认

### 13.1 风险

| 风险 | 影响 | 应对 |
|---|---|---|
| SSE + POST 在部分代理下被缓冲 | 流式失效 | 本地 P0 直连；生产加 `X-Accel-Buffering: no` |
| SQLite 同会话并发写 | seq 冲突 | per-session 锁 + 唯一约束兜底 |
| 关键词误判 | 正常表达被拦截 | 只做保守匹配；记录命中，后续人工 review |
| 危机话术不合适 | 安全风险 | 上线前由人确认固定文案；不交给模型生成 |
| 事件日志与 design.md 冲突 | 实现分歧 | 本 spec 先按“不落 delta”执行，随后同步文档 |
| 测试客户端弃用警告 | 未来升级问题 | 用 `httpx.AsyncClient` + ASGITransport，避免 TestClient |

### 13.2 待确认

1. 固定安全话术的最终文案（当前用 §8.2 草稿，上线前必须人工确认）
2. 默认角色 persona（当前 `default@v1`「小满」，可替换，见 `app/domain/character.py`）
3. 真实 LLM 供应商与模型（P0 用 MockLlm）
4. 前端是否放 `frontend/`（P0 未做前端）
5. ~~P0 是否需要 `messages` 投影表~~ 已定：不需要，上下文从事件重建

---

## 14. 完成定义

满足以下全部条件才算完成（2026-11-02 满足）：

- 所有验收标准通过
- 测试、ruff、mypy 全绿
- 事件可回放
- 危机路径不调用 LLM
- 没有实现范围外功能
- 文档已更新

---

## 15. 实现记录（2026-11-02）

| 任务 | 落地位置 |
|---|---|
| 事件模型与 payload 校验 | `app/domain/events.py` |
| 端口 | `app/domain/ports.py` |
| 固定角色与 prompt | `app/domain/character.py` |
| 安全关键词 + 固定话术 | `app/application/safety.py` |
| 上下文装配（最近 20 轮） | `app/application/context.py` |
| 会话锁 | `app/application/locks.py` |
| ChatService / SSE 事件流 | `app/application/chat.py` |
| SQLite 事件存储 | `app/adapters/storage/sqlite_event_store.py` |
| MockLlm | `app/adapters/llm/mock.py` |
| HTTP 接口 | `app/transport/http/{sessions,chat}.py` |

验证命令与结果：

```text
cd backend
uv run pytest        → 40 passed
uv run ruff check .  → All checks passed
uv run mypy app      → Success: no issues found in 30 source files
```

决策记录见 `docs/adr/0001-event-log-p0.md`。

P0 明确未做：前端、真实 LLM 供应商、CI、git 仓库。`git init` 与首次提交需要人明确指示。
