# AGENTS.md

本文件是本仓库对 AI 编码代理的约束。开始任何任务前，先读本文件、`docs/design.md` 和相关 `docs/adr/`。

如果本文件与 `docs/design.md` 冲突，以 `docs/design.md` 的最新决策为准，并明确向人指出冲突，不要自行选择。

---

## 0. 硬性要求

1. **不确定就问**：需求、接口、数据结构、依赖、验收标准不清楚时，先提问，不猜。
2. **一次只做一个可验证的切片**：不要顺手重构、不要扩大范围、不要一次性搭完整项目。
3. **先计划后编码**：动手前给出计划，说明要改哪些文件、为什么、怎么验证。人确认后再写代码。
4. **不自动提交**：不执行 `git commit`、`git push`、`git reset`、强制推送，除非人明确要求。
5. **不擅自加依赖**：新增 npm/pip 依赖前必须说明理由并获得确认。
6. **不碰密钥和数据**：不读取、不打印、不提交 `.env*`、API key、数据库文件、用户数据。
7. **不绕过验证**：不删除测试、不跳过类型检查、不注释掉 lint、不修改 CI 来让检查通过。
8. **失败时停下**：连续两次修复失败，停止并说明现状、证据和可选方案，不要继续盲试。

---

## 1. 项目是什么

**定位**：可私有部署的实时语音二次元角色陪伴系统，支持角色卡、长期记忆、情绪状态与 Live2D 联动。

**核心**：对话状态与数据是核心；LLM、ASR、TTS、Live2D、数据库都是可替换的外围。

**明确不做**：

- 不做心理治疗、诊断、处方或医疗建议
- 不把 AI 包装成真人
- 不做真实电话外呼
- 不在第一版做全双工语音
- 不在第一版上向量数据库、微服务、多用户
- 不允许 LLM 直接写数据库

---

## 2. 当前状态

- 设计文档：`docs/design.md` v0.1
- 代码：后端文字聊天 MVP 已实现（事件日志 + SSE + 安全兜底 + MockLlm + 回放），见 `docs/specs/0001-text-chat-mvp.md`
- 已确认：后端 Python 3.11 + FastAPI；包管理 uv；SQLite + aiosqlite；第一版只做文字
- 数据库 schema 已建立（`backend/migrations/0001_init.sql`，根 `schema.sql` 为快照，有测试守护一致）
- 架构决策记录：`docs/adr/0001-event-log-p0.md`
- 前端、CI、git 仓库尚未建立
- 以下决策未定，AI 不要自行拍板：
  - 真实模型供应商（百炼 / OpenAI / Claude / 本地模型）；P0 用 MockLlm
  - Live2D 模型资产来源与许可证
  - 自用 demo 还是开源后供他人部署
  - 前端目录位置（`frontend/` 或 `src/web/`）

---

## 3. 技术栈与目录

### 3.1 目标技术栈

- 后端：Python 3.11 + FastAPI + Pydantic v2 + Uvicorn
- 包管理：uv（`pyproject.toml` + `uv.lock`）
- 前端：React + TypeScript + Vite
- 测试：pytest + pytest-asyncio（后端）、Vitest（前端）
- 数据库：SQLite（P0–P3）+ aiosqlite，后续可迁移 PostgreSQL + pgvector
- 渲染：浏览器内嵌 Live2D（pixi-live2d-display / Cubism SDK），VTube Studio 仅作可选桥接

### 3.2 目标目录结构

```
docs/
  design.md          # 设计文档，单一事实源
  adr/               # 架构决策记录
  specs/             # 功能规格说明，按功能编号
schema.sql           # 可移植 SQL schema
backend/
  pyproject.toml     # uv 项目配置
  app/
    domain/          # 实体、值对象、端口、用例；不依赖任何供应商 SDK
    application/     # ChatService / MemoryService / EvalService / SafetyService
    adapters/        # llm / asr / tts / storage / runtime-live2d
    transport/       # http / ws
    shared/          # Pydantic schema、事件类型、通用工具
  tests/             # 后端单测、契约测试
  migrations/        # 编号 SQL migration
frontend/
  src/               # React + Live2D
eval/
  cases/             # 情感对话、危机、越界用例
  harness/           # 评测脚本与 judge
tests/               # 跨端、契约、回放测试
```

目录按任务需要逐步落地；不要提前创建业务代码空壳。

---

## 4. 架构铁律

1. **domain 不依赖 SDK**
   `src/domain/` 不得 import `openai`、`pixi`、`sqlite`、`axios` 等供应商或基础设施库。只定义接口和纯逻辑。

2. **事件日志是唯一真相**
   对话、打断、表情、记忆写入都写事件；消息表、情绪状态、指标都是投影。投影可重建。

3. **记忆是派生数据**
   记忆不是聊天记录。每条记忆必须有 `source_event_ids`、置信度和生命周期；禁止把模型猜测写入长期记忆。

4. **快慢路径分离**
   快路径：输入 → 安全 → 上下文 → LLM → TTS → 渲染。
   慢路径：事件日志 → 记忆抽取 → 摘要 → 评测 → 指标。
   慢路径不得阻塞快路径。

5. **端口只放在会变的地方**
   LLM、ASR、TTS、Live2D、存储可以有端口；领域核心不要为了“通用”而过度抽象。

6. **版本化一切**
   角色、prompt、事件 schema、数据库 schema 都要有版本。会话锁定 `character_version_id`。

7. **模块化单体优先**
   一个进程 + SQLite 起步。不要提前拆微服务、消息队列、Redis。

8. **永远不要让 LLM 直接写库**
   LLM 只产出候选数据，由应用层校验后落库。

9. **不要把 ASR partial 逐条写库**
   内存缓冲，只落 `asr.final` 和关键事件。

---

## 5. 数据与契约规则

- ID 用 ULID，存 `TEXT`；时间统一 UTC ISO8601 带毫秒
- 事件在会话内 `seq` 单调递增；事件不可修改，纠错靠新事件
- 每条 message 必须对应 event；每条 memory 必须有出处
- JSON 在 SQLite 存 `TEXT`，写入前用 zod 校验；到 PG 再换 `JSONB`
- 不用 `INSERT OR REPLACE`，用显式 upsert
- 不使用 SQLite 独有能力（如依赖 `rowid`），保证可迁移
- schema 变更必须通过 migration，不手改线上库

---

## 6. 编码规范

- TypeScript 开启 `strict`；禁止无理由的 `any`
- 外部输入（HTTP、WS、LLM 输出、环境变量）必须用 zod 校验
- 纯函数优先：ContextBuilder、状态机、校验器不碰网络和数据库
- 错误分类明确：供应商超时、限流、解析失败、安全拦截、用户取消
- 不写无用注释；命名表达意图；不留死代码
- 单测与代码同目录或 `tests/`；改纯函数必须补/改测试
- 不新增依赖，除非现有工具无法解决且人已确认

---

## 7. 安全与隐私

- API key 只放 `.env.local`，不进入浏览器、日志、提交
- 不记录完整用户对话到普通日志；敏感字段脱敏
- 情感对话数据本地优先，支持导出和删除
- 危机场景：自伤、自杀、伤人、急性心理危机必须有固定兜底话术和转介，不让模型自由发挥
- 不生成诊断、处方、治疗建议
- 开源前确认 Live2D SDK 与模型资产许可证，README 写清资产许可

---

## 8. AI 工作流

每个任务按以下顺序执行：

1. **读上下文**：`AGENTS.md`、`docs/design.md`、相关 ADR、相关代码
2. **复述任务**：用一句话说明目标、边界、验收标准；不确定就提问
3. **出计划**：列出要改的文件、关键决策、验证命令
4. **等人确认**：计划未确认，不写代码
5. **小步实现**：一次只改一个关注点
6. **验证**：跑测试、类型检查、lint；没有命令就说明缺什么
7. **自检偏差**：对照第 9 节清单
8. **更新文档**：设计变更写回 `docs/design.md` 或新增 ADR
9. **停止**：不自动提交，不继续做未要求的下一步

### 计划模板

```
目标：
非目标：
涉及文件：
关键决策：
验证命令：
风险/待确认：
```

---

## 9. 完成前自检清单

- [ ] 改动是否超出任务范围？
- [ ] 是否新增了未确认的依赖？
- [ ] `domain` 是否仍然不依赖供应商 SDK？
- [ ] 是否让 LLM 直接写库，或把猜测写进记忆？
- [ ] 是否绕过了测试、类型检查或 lint？
- [ ] 是否打印、提交或泄露了密钥/用户数据？
- [ ] 是否新增/修改了数据契约？是否同步 schema 和类型？
- [ ] 是否更新了 `docs/design.md` 或 ADR？
- [ ] 是否运行了可用的验证命令？结果是什么？
- [ ] 是否执行了 commit/push？（默认不应该）

任何一项答不上来，先停下来说明。

---

## 10. 命令

当前仓库尚未完全初始化，以下为约定命令；脚手架建立后必须保持一致。

后端：

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
uv run pytest
uv run ruff check .
uv run mypy app
```

前端（待前端脚手架建立后生效）：

```bash
npm install
npm run dev
npm test
npm run typecheck
npm run lint
```

- 命令不存在时，不要假装执行成功；明确说明“尚未配置”。
- 不修改这些命令的含义来绕过检查。
- 新增或重命名命令时，同步更新本文件和 CI。

---

## 11. 文档与决策

- `docs/design.md`：目标、范围、架构、数据模型、阶段计划
- `docs/adr/NNNN-title.md`：每个难改决策一页
- `docs/specs/NNNN-title.md`：单个功能的需求、边界与验收标准
- 新增或推翻决策时，必须更新文档，不只留在对话里
- ADR 模板：

```
# ADR-NNNN 标题

## Context
## Options
## Decision
## Consequences
## Revisit when
```

---

## 12. 提交与评审

- 只有人明确要求时才 commit
- 一次提交只做一件事；提交信息说明“为什么”，不只说“改了什么”
- review diff 时重点看：
  - 是否超出范围
  - 是否破坏架构边界
  - 是否绕过验证
  - 是否偷偷改契约
  - 是否引入安全/隐私风险
- AI 可以提出 review 意见，但最终由人拍板
