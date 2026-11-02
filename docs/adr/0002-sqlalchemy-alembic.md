# ADR-0002 用 SQLAlchemy 2.0 + Alembic 替换手写 SQL 与自研迁移器

- 日期：2026-11-02
- 状态：Accepted
- 关联：`docs/adr/0001-event-log-p0.md`、`docs/specs/0001-text-chat-mvp.md`

## Context

P0 最初用 `aiosqlite` + 手写 SQL + 自研迁移 runner。它能跑，但有两个问题：

1. P1 要加 `memory_items`、`summaries`、`jobs`、投影表，手写 row→model 映射和 `cast` 会越来越多。
2. 自研 runner 维护了版本发现、断档校验、语句拆分等逻辑，属于自己造的基础设施。

同时有三条约束不能破：

- `domain/` 不能依赖 ORM 或数据库。
- 事件不可修改，`seq` 必须在写锁内分配，`BEGIN IMMEDIATE` 不能省。
- `schema.sql` 要继续作为可读快照，并由测试守护与迁移结果一致。

## Options

- **A. 继续手写 SQL**：P0 只有 4 条语句，能忍；P1 会痛。
- **B. SQLAlchemy 2.0 async + Alembic**：ORM 模型只放适配器层，domain 保持 Pydantic；迁移交给 Alembic。
- **C. SQLModel**：模型同时是 Pydantic 和 ORM，会把 ORM 基类带进 domain，违反依赖方向。

## Decision

选 **B**：

- 新增依赖 `sqlalchemy[asyncio]`、`alembic`。
- `app/adapters/storage/tables.py` 定义 `SessionRow` / `EventRow`，只服务适配器。
- `app/adapters/storage/database.py` 创建 async engine：
  - `connect_args={"isolation_level": None}`，关闭 pysqlite 的隐式 BEGIN；
  - `connect` 事件设置 `foreign_keys`、`busy_timeout`；
  - `begin` 事件显式执行 `BEGIN IMMEDIATE`，保证 `seq` 分配在写锁内；
  - `NullPool`，避免跨事件循环复用连接。
- `SqliteEventStore` 用 `AsyncSession` 实现，`EventStore` 端口不变。
- Alembic 接管迁移，删掉自研 runner 和 `backend/migrations/*.sql`；`app.cli migrate/status` 变成 Alembic 的薄包装。
- `schema.sql` 更新为 Alembic 应用后的快照，测试继续对比两者。

## Consequences

- 读写代码不再手写 SQL；P1 加表只需要加 ORM 模型和 Alembic revision。
- domain 仍然只依赖 Pydantic，替换数据库不影响核心。
- **读操作也会走 `BEGIN IMMEDIATE`**：每次 `get_session` / `list_events` 都拿写锁。P0 单进程、单用户，可以接受；读并发变高时要拆只读 session 或换 PG。
- `db.get()` 在 `create_session` 里需要先 `flush()`，否则同一事务里查不到刚 add 的行。
- SQLite 的 `TEXT PRIMARY KEY` 在 SQLAlchemy 下会带 `NOT NULL`，`schema.sql` 已对齐。
- `alembic_version` 替换了原来的 `schema_migrations` 表。
- 旧的 `schema_migrations` 数据库不兼容；当前没有已部署实例。如果遇到旧库，需要先手工 `alembic stamp 0001` 再升级。

## Revisit when

- 需要读并发或多 worker → 拆分读写引擎，或迁移 PostgreSQL + asyncpg。
- Alembic 的 autogenerate 与手写 `schema.sql` 开始漂移 → 以 ORM 模型为唯一 schema 源，`schema.sql` 改为生成物。
- 引入向量检索 → 迁移 PG + pgvector，Alembic 换方言。
