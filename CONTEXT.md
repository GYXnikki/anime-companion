# 领域语言（Glossary）

本文件只记录领域术语定义，不含实现细节。实现决策见 `docs/adr/` 和 `docs/design.md`。
命名、文案、测试名都用这里的词；同一个概念不要换着叫。

## 1. 基础概念

### 角色与版本

**角色（Character）**：
一个可对话的二次元角色身份，由 ID、人格、声音、形象定义；不是模型，也不是会话。
_Avoid_: 机器人、账号、模型、Bot

**角色卡（Character Card）**：
描述角色人格、语气、边界、开场白的可替换配置。P0 固定 `default@v1`，不提供增删改查。
_Avoid_: prompt、system message、设定集

**角色版本（Character Version）**：
角色的不可变快照。会话创建时锁定版本，之后改人格不影响历史会话。
_Avoid_: 当前人格、角色配置

**默认角色（Default Character）**：
P0 内置角色「小满」`default@v1`，只用于验证链路，不是最终上线角色。
_Avoid_: 正式角色、产品角色

**人格（Persona）**：
角色版本里描述性格、语气、边界的文本。
_Avoid_: 提示词、剧本

### 会话与轮次

**会话（Session）**：
一次连续对话的容器，锁定角色版本，拥有自己的事件序列和 `last_seq`。
_Avoid_: 对话、聊天记录、房间

**轮次（Turn）**：
一条用户输入加上它对应的回复（正常完成、失败或安全兜底）。同一轮的事件共享 `turn_id`。
_Avoid_: 消息、回合、对话

**会话并发（Session Lock）**：
同一会话同时只允许一个生成任务；第二个请求返回 409，不排队。
_Avoid_: 全局限流、队列

**回放（Replay）**：
按 `seq` 读取会话事件，用于排障和评测；不是重新调用模型。
_Avoid_: 重新生成、重放模型

## 2. 事件与真相

**事件（Event）**：
会话内发生的一件事，只追加、不可修改，包含 `id / seq / type / turn_id / actor / payload / created_at`。
_Avoid_: 日志、消息、记录

**事件日志（Event Log）**：
所有事件的唯一真相来源。消息表、情绪状态、指标都是它的投影。
_Avoid_: 聊天记录、数据库、消息表

**投影（Projection）**：
从事件派生出的可重建读模型，例如消息表、情绪状态、指标。
_Avoid_: 真相、源数据

**事件类型（Event Type）**：
P0 有六种：`session.started`、`user.text`、`assistant.completed`、`assistant.failed`、`safety.triggered`、`safety.responded`。
_Avoid_: 自定义事件、裸 JSON

**事件载荷（Payload）**：
事件类型对应的结构化数据，写入前用 Pydantic 校验。
_Avoid_: 正文、content（作为泛称）

**事件序号（seq）**：
会话内从 1 开始单调递增的整数，由存储在写锁内分配；不是时间戳，也不依赖自增主键。
_Avoid_: 时间排序、rowid、自增 ID

**轮次标识（turn_id）**：
同一轮事件共享的 ULID。`session.started` 没有轮次。
_Avoid_: session_id、message_id

**行为者（actor）**：
事件产生者 `user / assistant / system`，由事件类型推导，不单独存列。
_Avoid_: 角色、发送人

**事件版本（schema_version）**：
事件结构的版本。P0 全部按 v1 读取，字段延后。
_Avoid_: API 版本

## 3. 对话与上下文

**快路径（Fast Path）**：
输入 → 安全 → 上下文 → LLM →（未来 TTS / 渲染），决定体验，必须低延迟。

**慢路径（Slow Path）**：
事件日志 → 记忆抽取 → 摘要 → 评测 → 指标，决定成长，不得阻塞快路径。

**上下文装配（Context Builder）**：
用角色、安全策略、记忆、摘要、最近轮次拼出 LLM 请求的纯函数，不碰网络和数据库。

**上下文窗口（Context Window）**：
P0 取最近 20 轮。一轮 = 用户消息 + 至多一条回复；失败的轮次保留用户消息，不补 assistant 消息。

**流式增量（Delta）**：
SSE 传输层的文本片段，不落库；落库的是 `assistant.completed`。

**安全兜底（Safety Response）**：
命中危机关键词后返回的固定话术，不调用 LLM，不追问细节。

**危机红线（Crisis Red Line）**：
自伤、自杀、伤人、急性心理危机。命中即走固定流程，不让模型自由发挥。

**越界请求（Out-of-Scope Request）**：
要求诊断、处方、治疗建议、色情内容、替代真人关系等；由安全策略处理。

**过度顺从（Sycophancy）**：
一味顺着用户说。情感陪伴最主要的失败模式，评估必须覆盖。

**打断（Interrupt）**：
用户在 AI 说话时打断。P0 不做，P2 做按钮打断。
_Avoid_: 全双工（那是另一件事）

**半双工 / 全双工（Half / Full Duplex）**：
TTS 播放时是否继续听。MVP 半双工；全双工需要 AEC 或耳机假设。

## 4. 记忆（P1 起）

**记忆（Memory）**：
关于用户的派生知识，回答“我们知道这个人什么”，不是聊天记录。
_Avoid_: 聊天历史、上下文

**记忆条目（Memory Item）**：
一条记忆，带 `type / key / content / source_event_ids / confidence / importance / status / valid_from / valid_to`。
_Avoid_: 事实、笔记、用户画像

**记忆候选（Memory Candidate）**：
LLM 抽取出的待校验记忆，不能直接入库。
_Avoid_: 记忆、事实卡片

**出处（Source Events）**：
记忆必须引用的 `user.text` 事件 ID；没有出处不入库。
_Avoid_: 来源、引用

**置信度与重要度（Confidence / Importance）**：
置信度是对真实性的把握，重要度是对未来对话的价值；两者不是一回事。
_Avoid_: 权重、分数

**生命周期（Lifecycle）**：
`candidate / active / superseded / deleted`。冲突时新条目取代旧条目，保留历史，不物理覆盖。
_Avoid_: 删除、覆盖

**摘要（Summary）**：
对一段对话的压缩，替代旧原文进入上下文；可重建，不是真相。
_Avoid_: 记忆、聊天记录

**三层记忆（Three-Tier Memory）**：
短期最近 N 轮原文、中期滚动摘要、长期事实卡片。
_Avoid_: 向量记忆（P4 才考虑）

## 5. 情绪与表现（P2 / P3）

**情绪（Emotion）与强度（Intensity）**：
每轮结构化输出里的情绪标签和 0–1 强度，驱动表情与动作。
_Avoid_: 心情、语气

**表演参数（Performance）**：
`emotion + intensity + motion_hint`，属于表现层，不是事件日志的 token 级内容。
_Avoid_: 动画参数、表情包

**会话状态机（Session State）**：
`idle / listening / thinking / speaking / interrupted / ended`，保持纯 reducer。
_Avoid_: 一堆布尔值

**口型同步（Lip Sync）**：
用音频包络驱动 `ParamMouthOpenY`；MVP 用 RMS 就够，不必先上 viseme。

**Live2D**：
浏览器内嵌渲染，使用 pixi-live2d-display / Cubism SDK，是主路径。

**VTube Studio（VTS）**：
可选桌面桥接，用于直播演示，不是主路径。

## 6. 工程概念

**端口（Port）**：
领域定义的接口，只放在会变的地方：LLM、ASR、TTS、Live2D、存储。
_Avoid_: 抽象基类、工具类

**适配器（Adapter）**：
端口的具体实现。供应商 SDK 只能出现在这一层。
_Avoid_: 驱动、客户端

**MockLlm**：
P0 的确定性 LLM 适配器，不产生真实回复，也不伪造 token 用量。
_Avoid_: 假模型、测试桩

**事件存储（EventStore）**：
事件的读写端口；`append` 支持一次写入多条，并在同一事务内分配连续 `seq`。
_Avoid_: DAO、Repository（泛称）

**迁移（Migration）**：
Alembic 版本脚本，schema 变更的唯一入口。
_Avoid_: 建表脚本、SQL 文件

**投影检查点（Projection Checkpoint）**：
投影重建的游标，P1 起使用。
_Avoid_: 进度、offset
