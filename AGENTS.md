# AGENTS.md

本文件给编码 agent 使用，只写会影响你行为的规则。项目背景和运行方式见 `README.md`，
领域词见 `CONTEXT.md`，实现决策见 `docs/design.md` 和 `docs/adr/`。

用户在当前对话里的明确指令优先于本文件。文档之间冲突时，先指出冲突并询问，不要自行选一个。

## 1. 项目与范围

- anime-companion：可私有部署的二次元角色陪伴引擎。当前只有 P0 文字聊天后端。
- 只做任务要求的事。不做任务之外的重构、顺手格式化、批量重命名或“清理旧代码”。
- 明确不做：心理治疗、诊断、处方或医疗建议；把 AI 包装成真人；真实电话外呼；
  第一版全双工语音；提前上向量数据库、微服务、多用户；让 LLM 直接写数据库。
- 以下决策未定，不要自行拍板：真实模型供应商、Live2D 资产来源与许可证、
  自用还是开源部署、前端目录位置。

## 2. 开始前读什么

1. `README.md`：目录、启动、配置、API、测试基线。
2. `CONTEXT.md`：领域术语。命名、文案、测试名都用这里的词。
3. `docs/design.md`：目标、范围、架构、数据模型、路线。
4. 相关 `docs/adr/`、`docs/specs/`：已有决策和功能边界。
5. 相关代码。

## 3. 目录与职责

- `backend/app/domain/`：实体、值对象、端口、纯逻辑。不得 import 供应商 SDK。
- `backend/app/application/`：ChatService、SafetyService、ContextBuilder 等用例编排。
- `backend/app/adapters/`：LLM、存储等端口实现。供应商 SDK 只能出现在这里。
- `backend/app/transport/`：HTTP / WS。保持薄；参数校验后调用 application。
- `backend/app/shared/`：ULID、时间等通用工具。
- `backend/app/config.py`：环境变量。不要在业务代码里散落 `os.environ`。
- `backend/app/cli.py`：`migrate` / `status`。
- `backend/alembic/`：迁移脚本，schema 变更的唯一入口。
- `backend/tests/`：pytest，文件名 `test_<feature>.py`。
- `schema.sql`：当前 schema 快照，由测试守护与迁移一致。
- `docs/adr/`、`docs/specs/`、`docs/design.md`：决策与规格。
- `frontend/`、`eval/`：尚未落地，不要提前创建业务空壳。

新代码放到对应层。不要把业务逻辑写进 transport，不要把 SQL 写进 transport，不要把供应商 SDK 写进 domain。

## 4. 精确命令

### 后端

```bash
cd backend
uv sync
uv run python -m app.cli migrate     # 应用待执行 migration
uv run python -m app.cli status      # 查看当前/最新版本
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
uv run mypy app
```

- 启动只检查 migration，不自动迁移；有 pending 时启动失败。
- 前端命令尚未配置；不要假装执行成功，明确说明“尚未配置”。
- 不修改这些命令的含义来绕过检查。

## 5. 架构铁律

1. **domain 不依赖 SDK**：`domain/` 不得 import `openai`、`sqlalchemy`、`fastapi`、
   `aiosqlite`、`pixi` 等供应商或基础设施库。
2. **事件日志是唯一真相**：消息、情绪、指标都是投影，投影可重建。
3. **记忆是派生数据**（P1 起）：每条记忆必须有 `source_event_ids`、置信度和生命周期；
   禁止把模型猜测写入长期记忆。
4. **快慢路径分离**：记忆、摘要、评测走慢路径，不得阻塞回复。
5. **端口只放在会变的地方**：LLM、ASR、TTS、Live2D、存储可以有端口；领域核心不要过度抽象。
6. **版本化一切**：角色、prompt、事件 schema、数据库 schema 都要有版本；会话锁定角色版本。
7. **模块化单体优先**：一个进程 + SQLite 起步。不要提前拆微服务、消息队列、Redis。
8. **永远不要让 LLM 直接写库**：它只产出候选数据，由应用层校验后落库。
9. **不要把 ASR partial 逐条写库**：内存缓冲，只落 `asr.final` 和关键事件。

## 6. 数据与契约

- ID 用 ULID，存 `TEXT`；时间统一 UTC ISO8601 带毫秒。
- 事件在会话内 `seq` 单调递增，只追加、不修改；纠错靠新事件。
- 每条 message 必须对应 event；每条 memory 必须有出处。
- 事件 payload 用 Pydantic 校验后再写入；SQLite 里存 `TEXT`，到 PG 再换 `JSONB`。
- 不用 `INSERT OR REPLACE`，用显式 upsert。
- 不使用 SQLite 独有能力（如依赖 `rowid`），保证可迁移。
- schema 变更必须通过 Alembic，不手改线上库；`schema.sql` 同步更新。
- `seq` 分配必须在 `BEGIN IMMEDIATE` 事务内完成，不能交给 ORM 的默认事务。
- 同会话并发返回 409 依赖进程内锁，只保证单进程；多 worker 部署前必须重做。
- 不用 token 级 delta 或 ASR partial 落库。

## 7. 编码规范

- Python 3.11；mypy strict；ruff 必须通过。
- 外部输入（HTTP、WS、LLM 输出、环境变量）必须校验后再进入领域逻辑。
- 纯函数优先：ContextBuilder、安全规则、状态机不碰网络和数据库。
- 错误分类明确：供应商超时、限流、解析失败、安全拦截、客户端断开。
- 不写无用注释；命名表达意图；不留死代码。
- 改纯函数或业务逻辑必须补/改测试。
- 不新增依赖，除非现有工具无法解决且人已确认。

## 8. 安全与隐私

- API key 只放 `backend/.env.local`，不进入代码、浏览器、日志或提交。
- 不记录完整用户对话到普通日志；日志里不出现用户文本。
- 危机场景（自伤、自杀、伤人、急性心理危机）必须有固定兜底话术和转介，
  不让模型自由发挥；最终文案上线前必须人工确认。
- 不生成诊断、处方或治疗建议；不把 AI 包装成真人。
- 情感对话数据本地优先，支持导出和删除。
- 开源前确认 Live2D SDK 与模型资产许可证，README 写清资产许可。

## 9. 测试要求

- Bug 修复：先补能复现的回归用例，再修；修完该用例必须通过。
- 新增/修改业务逻辑、API、存储、迁移：必须带测试。
- 纯文案、样式、注释、文档：可不加测试，但要跑最接近的现有检查。
- 当前基线（2026-11-02）：`pytest` 39 passed；`ruff` 通过；`mypy` 32 个源文件通过。
- 不得新增失败；不要顺手修无关失败。
- 测试使用临时 SQLite，不污染 `backend/data/`；必须确定性、可单独运行。
- 测试不得调用真实 LLM、TTS 或外部服务；需要时用 mock/fixture。
- 汇报必须写实际跑过的命令和结果，不能只说“测试通过”。

## 10. AI 工作流

每个任务按以下顺序执行：

1. **读上下文**：`AGENTS.md`、`README.md`、`CONTEXT.md`、`docs/design.md`、相关 ADR 和代码。
2. **复述任务**：一句话说明目标、边界、验收标准；不确定就提问。
3. **出计划**：列出要改的文件、关键决策、验证命令。
4. **等人确认**：计划未确认，不写代码。
5. **小步实现**：一次只改一个关注点。
6. **验证**：跑测试、类型检查、lint；没有命令就说明缺什么。
7. **自检偏差**：对照第 12 节清单。
8. **更新文档**：命令/配置 → README；领域术语 → CONTEXT；功能边界 → spec；架构决策 → ADR。
9. **停止**：不自动提交，不继续做未要求的下一步。

计划模板：

```text
目标：
非目标：
涉及文件：
关键决策：
验证命令：
风险/待确认：
```

## 11. 提交与评审

- 只有人明确说“提交 / commit”才提交；不主动 `push`、不 force push、不改写历史。
- 提交格式：

```text
type(scope): 中文简述

- 为什么改、改了什么（需要时）
- 验证：<命令> → <结果>（需要时）
```

- `type`：`feat` / `fix` / `refactor` / `test` / `docs` / `chore`
- 一次提交只做一件事；提交信息说明“为什么”，不只说“改了什么”。
- 只 `git add` 本次改动的具体文件；不要 `git add -A` / `git add .`。
- 永不提交 `.env*`、`*.db`、`backend/data/`、日志、密钥，也不要把 `.opencode/`、
  `.idea/`、`docs/private/` 等个人工具或私有目录 stage 进去。
- review diff 时重点看：是否超出范围、是否破坏架构边界、是否绕过验证、
  是否偷偷改契约、是否引入安全/隐私风险。
- AI 可以提出 review 意见，但最终由人拍板。

## 12. 完成门禁

完成前逐项确认：

1. 已跑本次改动最接近的检查。
2. 已跑全量测试，并在汇报里写明实际命令 + 结果；不得新增失败。
3. 行为、命令、配置、领域术语变化时，同步更新对应文档，只更新一处，不重复写。
4. `git diff --stat` 和 `git diff --check` 通过；没有密钥、数据库、日志、无关文件混入。
5. `domain/` 仍不依赖供应商 SDK；没有让 LLM 直接写库。
6. 没有绕过测试、类型检查或 lint。
7. 最终汇报：改了哪些文件、为什么、跑了什么、结果、剩余风险；未提交就说明未提交。

任何一项答不上来，先停下来说明。
