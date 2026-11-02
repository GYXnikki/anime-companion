# anime-companion

> 可私有部署的二次元角色陪伴引擎：对话状态与数据是核心，LLM / ASR / TTS / Live2D 都是可替换的外围。

当前完成 **P0 文字聊天后端**：流式对话、事件日志、安全兜底。文档更新：2026-11-02。

---

## 1. 项目概览

anime-companion 不是单个聊天窗，而是「引擎 + 角色皮肤」：角色卡可替换，核心是事件日志、上下文装配、安全边界，后续再接记忆、语音和 Live2D。

| 维度 | 现状 |
| --- | --- |
| 后端 | Python 3.11 / FastAPI / Pydantic v2 |
| 存储 | SQLite + SQLAlchemy 2.0 async（aiosqlite）+ Alembic |
| 对话 | SSE 流式文字；最近 20 轮上下文从事件重建 |
| LLM | 仅 `MockLlm`，真实供应商未接 |
| 前端 | 未开始（计划 React + TypeScript + Vite） |
| 语音 / Live2D | 未开始（P2 / P3） |
| 记忆 / 情绪 / 评测 | 未开始（P1 起） |

**明确不做**：心理治疗、诊断、处方或医疗建议；不把 AI 包装成真人；不做真实电话外呼；第一版不做全双工语音；不提前上向量库、微服务、多用户；不允许 LLM 直接写数据库。

---

## 2. 目录结构

```text
anime-companion/
├── backend/
│   ├── app/
│   │   ├── domain/            # 实体、值对象、端口、纯逻辑；不依赖供应商 SDK
│   │   ├── application/       # ChatService / SafetyService / ContextBuilder
│   │   ├── adapters/          # llm / storage
│   │   ├── transport/http/    # sessions / chat / health
│   │   ├── shared/            # ULID、时间
│   │   ├── config.py          # 环境变量
│   │   ├── cli.py             # migrate / status
│   │   └── main.py            # create_app、生命周期、路由挂载
│   ├── alembic/               # 迁移脚本
│   ├── tests/                 # pytest
│   └── pyproject.toml
├── docs/
│   ├── design.md              # 设计文档
│   ├── adr/                   # 架构决策
│   └── specs/                 # 功能规格
├── schema.sql                 # 当前 schema 快照（有测试守护）
├── CONTEXT.md                 # 领域词表
└── README.md
```

`frontend/` 和 `eval/` 尚未落地。目录按任务逐步创建，不提前放业务空壳。

---

## 3. 快速开始

### 3.1 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- 本地无需任何 API key（当前只有 MockLlm）

### 3.2 启动后端

```bash
cd backend
uv sync
uv run python -m app.cli migrate
uv run uvicorn app.main:app --reload
```

启动时会检查数据库版本；未迁移会直接失败并提示执行 `uv run python -m app.cli migrate`。服务地址 `http://127.0.0.1:8000`，健康检查 `GET /health`。

### 3.3 对话示例

```bash
# 1. 创建会话
curl -X POST http://127.0.0.1:8000/api/sessions

# 2. 发消息，流式读取
curl -N -X POST http://127.0.0.1:8000/api/sessions/<id>/messages \
  -H 'Content-Type: application/json' \
  -d '{"text":"今天有点累"}'

# 3. 回放事件
curl http://127.0.0.1:8000/api/sessions/<id>/events
```

SSE 输出：

```text
event: delta
data: {"text":"我在这儿"}

event: done
data: {"message_id":"01J...","interrupted":false}
```

失败时返回 `event: error`，`code` 为 `llm_timeout`、`llm_error`、`client_disconnected` 或 `internal_error`。

---

## 4. 配置

读取顺序：环境变量 → `backend/.env.local` → 代码默认值。完整样例见 `backend/.env.example`。

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `ANIME_COMPANION_ENVIRONMENT` | 运行环境标识 | `local` |
| `ANIME_COMPANION_DATABASE_PATH` | SQLite 文件路径 | `data/anime_companion.db` |
| `ANIME_COMPANION_LLM_TIMEOUT_SECONDS` | 单轮 LLM 超时（秒） | `30` |
| `ANIME_COMPANION_MAX_CONTEXT_TURNS` | 上下文保留轮数 | `20` |

`.env.local`、`*.db`、`backend/data/` 都已 gitignore；不要提交密钥或数据库文件。

---

## 5. API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/sessions` | 创建会话，201 |
| `POST` | `/api/sessions/{id}/messages` | 发送消息，SSE 返回 |
| `GET` | `/api/sessions/{id}/events` | 按 `seq` 回放事件 |

错误码：`404` 会话不存在；`409` 同一会话正在生成；`422` 文本为空或超过 2000 字符。流开始后的错误走 SSE `error` 事件，同时写入 `assistant.failed`。

事件类型见 `CONTEXT.md` 的「事件类型」。消息、回放、安全兜底都不返回任何配置或密钥。

---

## 6. 测试

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app
```

当前基线（2026-11-02）：

- `pytest`：**39 passed**
- `ruff check .`：**All checks passed**
- `mypy app`：**no issues in 32 source files**

测试不调用真实 LLM、TTS 或任何外部服务。改存储或迁移时，`schema.sql` 快照测试会守护 schema 与迁移一致。

---

## 7. 已实现 / 未实现

| 能力 | 状态 |
| --- | --- |
| 会话创建、事件回放 | ✅ |
| SSE 流式文字对话 | ✅ |
| 最近 20 轮上下文（从事件重建） | ✅ |
| 危机关键词 + 固定话术（LLM 之前生效） | ✅ |
| 同会话并发 409 | ✅ |
| 事件批量原子写入、`seq` 无重复 | ✅ |
| 真实 LLM 供应商 | ❌ |
| 记忆 / 摘要 / 情绪 / 评测 | ❌ |
| 语音 / 打断 / Live2D | ❌ |
| 前端 / CI | ❌ |

---

## 8. 架构速览

```text
快路径：输入 → 安全 → 上下文 → LLM →（未来 TTS / 渲染）
慢路径：事件日志 → 记忆抽取 → 摘要 → 评测 → 指标（慢路径不阻塞快路径）
```

四条不变量：

1. 事件只追加，不修改；纠错靠新事件。
2. 每条记忆必须带出处；P0 还没有记忆表。
3. 每个会话锁定角色版本；P0 固定 `default@v1`。
4. 每条 `user.text` 至多对应一条 `assistant.completed` / `assistant.failed` / `safety.responded`。

`domain/` 不 import 任何供应商 SDK；SQLAlchemy、FastAPI 只出现在适配器和传输层。

---

## 9. 安全与隐私

- 危机场景走固定话术，不诊断、不追问细节、不调用 LLM；**最终文案上线前必须人工确认**。
- 不生成诊断、处方或治疗建议；不把 AI 包装成真人。
- 不记录完整对话到普通日志；日志里不出现用户文本。
- API key 只放 `.env.local`，不进入浏览器、日志或提交。
- 单进程限制：同会话 409 依赖进程内锁，多 worker 部署会失效（见 ADR-0002 / ADR-0001）。
- 仓库内暂无 Live2D 模型与第三方美术资产；后续资产许可证单独说明。

---

## 10. 文档索引

| 文档 | 内容 |
| --- | --- |
| `CONTEXT.md` | 领域词表；命名和文案以它为准 |
| `AGENTS.md` | 编码 agent 的行为规则 |
| `docs/design.md` | 设计文档：目标、范围、架构、数据模型、路线 |
| `docs/specs/0001-text-chat-mvp.md` | P0 文字聊天规格与验收 |
| `docs/adr/0001-event-log-p0.md` | 事件日志形态、`turn_id`、批量原子写入 |
| `docs/adr/0002-sqlalchemy-alembic.md` | SQLAlchemy + Alembic、`BEGIN IMMEDIATE` |

---

## 11. 许可证

代码采用 [MIT License](LICENSE)。

仓库内暂无 Live2D 模型与第三方美术资产；后续资产计划使用 CC BY-NC，与代码许可证分开。
