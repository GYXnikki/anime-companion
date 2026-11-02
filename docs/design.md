# AI 情感聊天机器人（二次元角色陪伴引擎）设计文档

- 版本：v0.1
- 日期：2026-10-30
- 状态：设计讨论整理，待继续细化
- 来源：opencode 会话「AI情感聊天机器人开发学习指导」（2026-10-29）

---

## 0. 起点：和 ai-voice-followup 的关系

**结论：情感聊天机器人不能照搬随访机器人的“表单驱动”内核，但可以复用它的工程骨架。**

| 维度 | ai-voice-followup | 情感聊天机器人 |
|---|---|---|
| 对话控制 | Schema 逐题推进 | LLM 自由对话 + 策略约束 |
| 核心难点 | 状态机、答案提取 | 人格一致性、记忆、情绪、安全 |
| 可审计性 | 高（每题有槽位） | 低（需要评估体系补） |
| 语音 | 必需 | 可后置，先文字跑通 |

### 可以直接复用的部分

- 技术栈：Vite + React + TS + Vitest，`docs/design.md` 的决策日志写法
- 适配器模式：`src/lib/asr.ts`、`src/lib/tts.ts` 的接口抽象，换供应商不影响 UI
- 密钥边界：`vite.config.ts` 开发代理，key 不进浏览器
- 纯函数 reducer：`src/engine/reducer.ts` 的状态机思路
- 文字始终兜底、localStorage 持久化、失败不伪造

### 不能照搬的部分

- Schema 逐题提问 → 情感聊天要的是开放话题 + 主动追问
- 通话后答案提取 → 改为长期记忆抽取（事实、偏好、重要事件）
- “答非所问就跳过” → 情感场景里跑题往往正是用户想聊的，不能跳过

### 学习路线

**M0 设计一页纸（1 天）**

写清楚：机器人是谁（人格卡）、能做什么/不能做什么、成功标准。重点定义边界：不做心理治疗、不诊断、危机时转介。参考 `design.md` 的“已确认决策 + 被否掉的方向”格式。

**M1 纯文字 MVP（3–5 天）**

- 流式对话 + system prompt 人格
- 只做滑动窗口上下文（最近 N 轮）
- 学到：prompt 设计、流式渲染、token 成本
- 验收：能连续聊 20 轮不崩人格

**M2 记忆系统（1 周，核心难点）**

分三层，不要一上来就上向量库：

1. 短期：最近 N 轮原文
2. 中期：每 10 轮生成一次摘要，替换旧原文
3. 长期：抽取“事实卡片”（姓名、职业、重要关系、反复出现的情绪主题），存 JSON

关键问题：什么值得记、什么时候写、冲突时信谁。建议先做“只追加 + 人工可删”，别做自动覆盖。

验收：隔天再聊，机器人能自然提起昨天的事且不显得 creepy。

**M3 情绪与对话策略（1 周）**

- 让 LLM 每轮额外输出结构化字段：`emotion`、`intensity`、`user_intent`（倾诉/求助/闲聊/测试）
- 用这些字段驱动策略：高负面情绪 → 先共情少建议；连续低落 → 温和询问；用户想聊事实 → 切换信息模式
- 学到：结构化输出、对话策略与生成解耦

**M4 安全兜底（必做，3 天）**

- 危机识别：自伤、自杀、伤人、急性心理危机
- 分级响应：黄线（持续低落）→ 关心 + 建议求助；红线（明确危机）→ 固定话术 + 转介热线 + 不继续深聊
- 写 20–30 条测试用例做回归，这是情感类产品最不能省的部分

**M5 语音（可选，复用随访项目）**

直接搬 `asr.ts` / `tts.ts` 适配器，先做“按住说话 → TTS 回复”，不要一上来做全双工。情感场景对语气要求高，TTS 音色和语速比随访更重要。

**M6 评估体系（持续）**

情感对话没有标准答案，必须自建评估：

- 固定 30–50 条场景用例（失恋、焦虑、孤独、危机、越界请求）
- rubric 打分：共情、不评判、不越界、人格一致、安全
- LLM-as-judge + 人工抽检，每次改 prompt 跑一遍回归

### 最容易踩的坑

1. **过度顺从（sycophancy）**：情感陪伴最容易变成“什么都顺着说”，要明确写进 prompt 和评估
2. **记忆污染**：把模型自己的猜测写进长期记忆，越聊越偏。记忆只记用户明确表达的内容
3. **上下文成本**：20 轮后 token 爆炸，摘要层必须早做
4. **安全边界模糊**：用户会把它当心理咨询师，产品话术要主动管理预期
5. **隐私**：情感对话比随访更敏感，本地存储也要想清楚删除和导出

### 建议先做的三个小实验

1. 50 行代码跑通流式对话，感受延迟和成本
2. 给对话加“事实卡片”记忆，对比加之前后 20 轮的一致性
3. 写 20 条危机/越界测试，看当前模型会怎么答

---

## 1. 定位：二次元角色陪伴引擎

**不要只做一个“DS 拟人聊天窗”，要做「二次元角色陪伴引擎」，DS 拟人只是其中一个 demo 角色。**

### 为什么这样定位

只做单角色 bot：传播快，但技术含量看起来像套壳，容易被当成玩具。

做引擎 + 角色皮肤：

- 开源传播：角色卡可以换，社区会自己二创，star 来得快
- 技术展示价值：你卖的是记忆系统、实时语音、情绪状态机，不是“老婆”
- IP 风险：引擎是原创的，DS 拟人只是示例资产，可随时替换

### 推荐的项目形态

**名字建议**：`anime-companion` / `角色陪伴引擎`

定位一句话：

> 可私有部署的实时语音二次元角色陪伴系统，支持角色卡、长期记忆、情绪状态与 Live2D 联动。

差异化点（选 2–3 个做深，别全做）：

1. **实时语音**：VAD + 流式 ASR + 流式 TTS + 打断，延迟做到 1 秒内
2. **长期记忆**：短期窗口 + 中期摘要 + 长期事实卡片，可查看可删除
3. **Live2D / VTube Studio 联动**：口型同步 + 情绪驱动表情
4. **角色卡生态**：兼容 SillyTavern 角色卡格式，降低上手门槛
5. **本地部署**：Ollama / 本地 TTS，隐私和成本是卖点

### 4 周 MVP 路线

| 周 | 做什么 | 产出 |
|---|---|---|
| W1 | 文字 MVP + 角色卡 + 记忆 v1 + 30 条评估集 | 能聊、能记住、有回归测试 |
| W2 | 流式语音 + 按钮/语音打断 | 延迟数据、录音 demo |
| W3 | Live2D 口型 + 情绪表情 | 15 秒演示视频 |
| W4 | Docker 一键部署 + README + B 站演示 + 技术博客 | 可传播的开源项目 |

直接复用 ai-voice-followup 的 ASR/TTS 适配器和 Vite 代理思路，别从零写。

### 必须提前想清楚的边界

1. **IP**：不要用 DeepSeek 官方 logo，不暗示官方背书；引擎 MIT，角色资产 CC BY-NC；README 写明非官方二创
2. **NSFW**：开源项目会被用来做擦边内容，提前定内容策略和年龄提示
3. **情感依赖**：陪伴类产品要有使用时长提醒和危机转介，这本身就是很好的技术展示点
4. **隐私**：情感对话数据敏感，本地优先、可导出可删除

---

## 2. Live2D 路线

Live2D 是最容易出效果、也最能体现工程能力的方向。但先分清两条路线：

| 路线 | 适合 | 代价 |
|---|---|---|
| **浏览器内嵌渲染**（Cubism SDK / pixi-live2d-display） | 开源项目、Web demo、公开演示 | 要处理 SDK、模型、性能 |
| **VTube Studio 驱动**（WebSocket API） | 直播、最快出效果 | 依赖桌面软件，不像“产品” |

**推荐：浏览器内嵌为主，VTube Studio 作为可选桥接。** 开源项目要的是“打开网页就能用”，VTS 更适合后续做直播演示。

### 技术链路

```
LLM 结构化输出 {reply, emotion, intensity, motion_hint}
        │
        ├─→ TTS 音频 ─→ Web Audio AnalyserNode ─→ ParamMouthOpenY（口型）
        │                                      └─→ ParamMouthForm（笑/撇嘴）
        └─→ emotion ─→ .exp3.json 表情 + .motion3.json 动作
                          │
会话状态机 listening / thinking / speaking / idle
        └─→ 待机呼吸、眨眼、点头、歪头
```

关键点：

- **口型 MVP 用音量驱动就够**：`AnalyserNode` 取 RMS，映射到 `ParamMouthOpenY`，加 lerp 平滑。中文不看音素也能接受
- **要更准再上 viseme**：Azure TTS 有 viseme 事件；百炼 TTS 大概率没有，别一开始就卡在这
- **表情靠 LLM 结构化输出**：让模型每轮多返回 `emotion` 和 `intensity`，比事后分类准，也顺便练了 structured output
- **别只做张嘴**：眨眼、呼吸、`ParamMouthForm`、头部轻微摆动，缺一个都会“假”

### 接口设计（复用随访项目的适配器思路）

```ts
interface CharacterRuntime {
  speak(audio: AudioBuffer, emotion: Emotion): Promise<void>;
  setState(s: "idle" | "listening" | "thinking" | "speaking"): void;
  setEmotion(e: Emotion, intensity: number): void;
  destroy(): void;
}
```

Live2D、VRM、以后接 3D 都实现这个接口，对话引擎完全不感知渲染层。这个抽象本身就是架构上值得讲的点。

### 两周学习 sprint

| 天 | 任务 | 学到什么 |
|---|---|---|
| 1–2 | Cubism Editor 打开官方示例模型，改参数、播表情/动作 | 模型结构、参数、exp3/motion3 |
| 3–4 | Vite + React 里用 pixi-live2d-display 渲染 + 待机 | WebGL、PixiJS、资源加载 |
| 5–6 | TTS 播放 + 音量驱动口型 + 平滑 | Web Audio、实时动画循环 |
| 7–8 | LLM 输出 emotion → 表情/动作映射 | 结构化输出、状态映射 |
| 9–10 | 接会话状态机：听/想/说 | 状态机与渲染解耦 |
| 11–12 | 性能、移动端、iOS 自动播放限制 | 真机调试 |
| 13–14 | 15 秒演示视频 + README + 技术博客 | 传播材料 |

### 三个坑

1. **许可证是最大雷**：Cubism SDK 和模型资产要分开看。官方示例模型有使用条款，Booth 上很多模型只允许个人使用。开源项目建议用官方免费示例模型或委托原创，README 写清资产许可
2. **别在 Live2D 上过度投入**：它是冰淇淋，不是主食。对话、记忆、语音没跑通之前，皮套再好看也只是 demo
3. **口型不同步比没有口型更出戏**：音频分析要跟播放时钟对齐，别用 `setInterval` 拍脑袋

---

## 3. 架构：模块化单体 + 事件日志 + 端口适配器

**核心是对话状态与数据，语音和渲染都是可替换的外围。**

### 三条原则

1. **领域核心不依赖任何 SDK**：domain 层只定义实体、用例、端口；LLM/ASR/TTS/Live2D/DB 全是适配器。换模型、加语音、换皮套都不动核心。
2. **事件日志是唯一真相，表是投影**：对话、打断、表情、记忆写入都记事件；消息表、情绪状态、指标都是投影。可回放、可评测、可排查。
3. **记忆是派生数据，不是聊天记录**：聊天记录回答“说过什么”，记忆回答“关于这个人我们知道什么”，必须带出处、置信度、生命周期。

### 分层与依赖方向

```
┌──────────────────────────────────────────────┐
│ Transport   WebSocket / HTTP / CLI           │
├──────────────────────────────────────────────┤
│ Application ChatService / MemoryService      │
│             EvalService / SafetyService      │
├──────────────────────────────────────────────┤
│ Domain      entities + use cases + ports     │
│             不 import openai / pixi / sqlite │
├──────────────────────────────────────────────┤
│ Adapters    LLM / ASR / TTS / Live2D / DB    │
└──────────────────────────────────────────────┘
```

依赖永远向内。`domain` 里只有接口：

```ts
interface LlmPort {
  stream(req: LlmRequest): AsyncIterable<LlmChunk>;
}
interface MemoryStore {
  search(q: MemoryQuery): Promise<MemoryItem[]>;
  upsert(items: MemoryCandidate[]): Promise<void>;
}
interface CharacterRuntime {
  speak(audio: AudioRef, emotion: Emotion): Promise<void>;
  setState(s: SessionState): void;
}
```

### 核心数据模型

#### 角色与会话

```sql
characters(id, slug, created_at)
character_versions(
  id, character_id, version, name,
  persona_json,        -- 人格、语气、边界
  voice_json,          -- provider, voice_id, speed
  avatar_json,         -- live2d 模型、表情/动作映射
  created_at,
  UNIQUE(character_id, version)
)
users(id, display_name, locale, created_at, deleted_at)
sessions(
  id, user_id, character_version_id,
  mode,                -- text | voice
  status, started_at, ended_at
)
```

**角色必须版本化，会话锁定版本。** 改人格不能影响历史会话，否则评测和回放全乱。

#### 事件日志（真相层）

```sql
events(
  id,                  -- ULID，时间有序
  session_id,
  seq,                 -- 会话内递增
  type,                -- user.text / asr.final / assistant.delta ...
  actor,               -- user | assistant | system
  payload_json,
  created_at,
  UNIQUE(session_id, seq)
)
```

事件用联合类型约束，别用裸 JSON：

```ts
type ChatEvent =
  | { type: "user.text"; text: string }
  | { type: "asr.final"; text: string; confidence: number }
  | { type: "assistant.performance"; emotion: Emotion; intensity: number; motion?: string }
  | { type: "tts.started"; utteranceId: string }
  | { type: "user.interrupt"; atMs: number }
  | { type: "memory.candidate"; items: MemoryCandidate[] }
  | { type: "state.changed"; from: SessionState; to: SessionState };
```

> `assistant.delta` 只存在于传输层（SSE），不写事件日志；落库的是 `assistant.completed`。P0 已按此实现。

#### 投影表

```sql
messages(
  id, session_id, event_id, role, content,
  audio_ref, emotion, intensity,
  model, prompt_version, tokens_in, tokens_out, latency_ms,
  created_at
)
emotion_states(
  session_id PRIMARY KEY,
  emotion, intensity, valence, arousal,
  evidence_event_id, updated_at
)
turn_metrics(
  id, session_id, event_id, stage,   -- vad/asr/llm/tts
  duration_ms, provider, model, cost, created_at
)
```

`messages` 存 `model` 和 `prompt_version`，否则三个月后无法解释某次回复为什么变差。

#### 记忆

```sql
memory_items(
  id, user_id, character_id,
  type,                -- fact | preference | relationship | event | emotion_pattern
  key,                 -- 可选，结构化事实用，如 "职业"
  value_json,
  content,             -- 自然语言描述
  source_event_ids,    -- 必填，出处
  confidence,          -- 0-1
  importance,          -- 0-1
  status,              -- candidate | active | superseded | deleted
  valid_from, valid_to,
  superseded_by,
  created_at, updated_at
)
summaries(
  id, scope,           -- session | user
  session_id, user_id, character_id,
  level,               -- rolling | session | period
  covers_from_seq, covers_to_seq,
  content, token_count, created_at
)
```

记忆生命周期：

```
LLM 抽取候选 → 校验（必须有出处、不许推测）
→ 去重/合并 → active
→ 冲突时新条目 supersede 旧条目（保留历史，不覆盖）
→ 用户可查看/删除
```

**永远不要让 LLM 直接写库。** 它只产出 `MemoryCandidate`，由 `MemoryService` 校验后落库。

### 上下文装配（60% 的核心）

`ContextBuilder` 做成纯函数，不碰网络，方便单测：

```ts
buildContext({
  character, safetyPolicy, profile,
  memories, summaries, recentTurns, userInput,
  tokenBudget
}): LlmMessage[]
```

预算示例：

| 部分 | 占比 | 说明 |
|---|---|---|
| 角色人格 + 边界 | 15% | 稳定，放最前 |
| 安全策略 | 5% | 危机/越界规则 |
| 长期记忆 | 20% | top-k，按重要度+相关度 |
| 摘要 | 15% | 滚动摘要，替代旧对话 |
| 最近对话 | 35% | 保证连贯 |
| 输出契约 | 10% | JSON schema |

**记忆检索 MVP 不要上向量库**：先按 `user_id + character_id + status` 过滤，再按 `importance + recency + 关键词` 排序。等有真实数据再加 pgvector。

### 一次对话的事件流

```
文字：
user.text → safety.check → context.build → llm.stream
→ SSE delta*（不落库）→ assistant.completed
→ [异步] memory.extract → summary.maybe → metrics

语音：
vad.start → asr.partial* → vad.end → asr.final
→ 同上 → sentence.chunk → tts.stream → audio.queue → runtime.speak
→ 打断：tts.cancel + queue.clear + state=listening
```

状态机保持纯 reducer：`idle → listening → thinking → speaking → interrupted → listening`。这部分直接复用 ai-voice-followup 的 `reducer.ts` 思路。

### 目录结构

```
src/
  domain/          # 实体、值对象、端口、用例
  application/     # ChatService / MemoryService / EvalService
  adapters/
    llm/ asr/ tts/ storage/ runtime-live2d/
  transport/
    ws/ http/
  web/             # React + Live2D
  shared/          # zod schema、事件类型
```

先用**模块化单体**，一个进程 + SQLite 就够。等真有多用户再拆 Postgres/Redis/对象存储，别一开始上微服务。

### 演进路线

| 阶段 | 重点 | 数据层 |
|---|---|---|
| P0 | 事件日志 + 文字对话 + ContextBuilder | SQLite |
| P1 | 记忆写入/检索 + 摘要 + 评测集 | SQLite |
| P2 | 流式语音 + 打断 | 加音频文件存储 |
| P3 | Live2D + Docker 部署 | 不变 |
| P4 | 多用户 + 可观测性 | Postgres + pgvector |

### 常见反模式

- 把整段对话塞进一个 JSON 字段
- 拿聊天记录当记忆
- Live2D 和 LLM 响应直接耦合
- 同步抽取记忆，阻塞回复
- 角色 prompt 原地修改，没有版本
- 没有 event id，出问题无法回放
- 一上来就向量数据库 / 微服务
- LLM 直接写库，没有校验

---

## 4. 为什么先用 SQLite

不是“都用 SQLite”，而是**这个阶段用 SQLite 更划算**。数据库选型看并发模型、运维成本和未来迁移代价，不是“哪个更专业”。

### 四个理由

1. **零运维**：一个文件，不用起服务、配账号、开端口、做连接池。省下的时间花在记忆和评测上。
2. **单用户写入完全够**：WAL 模式下多读一写，聊天一轮只写几条事件，毫无压力。真正的瓶颈是多用户并发写。
3. **测试和本地开发极爽**：内存库跑单测、复制文件做备份、隐私数据不出本机。
4. **迁移成本可控**：只要通过仓储接口访问，换 PG 是换适配器，不是重写业务。

### 什么时候必须换 Postgres

| 触发条件 | 说明 |
|---|---|
| 多用户并发写 | 实时语音会话一多，单写者会成为瓶颈 |
| 要做向量检索 | pgvector 一步到位，省一个向量库 |
| 需要远程访问/权限/行级安全 | SQLite 没有网络协议和角色体系 |
| 复杂分析查询 | 窗口函数、JSONB 索引、并行查询 |
| 多人协作/部署多实例 | 需要网络数据库和复制 |

MySQL 没选的原因：**AI 场景的默认答案是 PG**。pgvector、JSONB、扩展生态都更顺手；MySQL 更适合“团队本来就用 MySQL”的情况。

### 让数据库可替换

```ts
interface EventStore {
  append(e: ChatEvent): Promise<void>;
  listBySession(sessionId: string): Promise<ChatEvent[]>;
}
interface MemoryStore {
  search(q: MemoryQuery): Promise<MemoryItem[]>;
  upsert(items: MemoryCandidate[]): Promise<void>;
}
```

- 业务只依赖接口，不直接写 SQL
- 用迁移工具（Drizzle / Kysely / Alembic），schema 进版本控制
- 类型可移植：ID 用 `TEXT` 存 ULID，时间统一 UTC ISO8601，JSON 先当 `TEXT` 存，到 PG 再换 `JSONB`
- 别用 SQLite 独有能力（比如 `rowid` 假设）

### 具体建议

- **P0–P3 用 SQLite**，开 WAL、设 `busy_timeout`，DB 文件放本地磁盘，别放 NFS
- **P4 换 PG**，同时上 pgvector 做记忆检索
- 现在就把 schema 写成“可移植 SQL”，并写一个仓储接口的契约测试

一个实践坑：**别把 ASR 的 partial 结果逐条写库**，写放大很严重。内存里缓冲，只落 `asr.final` 和关键事件。

> SQLite 是起点，不是终点；PG 是终点，但不是第一天的必需品。

---

## 5. 字段级细化

### A. 数据模型逐字段评审

#### A.1 通用约定

- ID 用 ULID 存 `TEXT`：时间有序、无中心依赖、SQLite/PG 通用；PG 以后可转 `uuid`
- 时间统一 UTC ISO8601 带毫秒：`2026-10-29T08:00:00.000Z`，字典序即时间序；但排序用 `seq`，不靠时间
- JSON 在 SQLite 存 `TEXT`，写入前 zod 校验；到 PG 换 `JSONB`，MVP 不查 JSON 内部
- 不用 `INSERT OR REPLACE`，用显式 upsert + 冲突目标
- 所有表带 `created_at`，可变表带 `updated_at`

#### A.2 `events`

| 字段 | 为什么存在 | 注意 |
|---|---|---|
| `seq` | 会话内严格顺序 | 单写者保证 gap-free，唯一约束兜底 |
| `schema_version` | 事件结构升级 | 读取时做 upcast，不原地改老事件 |
| `turn_id` | 把事件归到一轮 | 用户输入时生成 |
| `caused_by` | 因果链 | 如 `assistant.completed` 指向 `user.text` |
| `client_event_id` | 幂等 | 部分唯一索引，重试不重复 |
| `payload_json` | 事件内容 | 每个 `type` 注册 zod schema |

不存 token 级 delta 和 ASR partial，否则写放大不可控。

P0 落地时的取舍（2026-11-02，见 ADR-0001）：`turn_id` 已加；`schema_version`、`caused_by`、
`client_event_id` 延后；`actor` 不建列，由 `type` 推导。事件写入支持批量原子提交。

#### A.3 `sessions`

- `last_seq`：快速分配 seq，必须和事件插入同事务
- `character_version_id`：锁版本，改人格不影响历史
- `status`：`active/ended/abandoned/error`
- `client_json`：UA、时区、能力（voice/live2d），不存 PII

#### A.4 `turns`（投影）

- `first_token_ms` / `first_audio_ms`：延迟指标
- `interrupted`：是否被打断
- `status`：`created/input/safety/context/generating/speaking/completed/failed`
- 一轮对应一个 `user_event_id`，`assistant_event_id` 可空（失败时）

#### A.5 `messages`（投影）

- `content`：模型生成全文；`spoken_text`：实际播报部分；`interrupted` 标记
- `event_id` 唯一，保证投影幂等
- `model` + `prompt_version`：三个月后能解释回复为什么变了
- `tokens_in/out`、`latency_ms`：成本与性能
- 音频只存 `audio_ref`，不存二进制

#### A.6 `memory_items`

| 字段 | 含义 | 易错点 |
|---|---|---|
| `type` | fact/preference/relationship/event/emotion_pattern | 不要所有记忆都用 fact |
| `key` | 结构化事实的键，可空 | 开放记忆不需要 key |
| `value_json` | 可查询的值 | 与 `content` 二选一为主 |
| `content` | 注入 prompt 的自然语言 | 必须可读、简短 |
| `confidence` | 对真实性的把握 | 和 importance 不是一回事 |
| `importance` | 对未来对话的价值 | 由抽取模型打分 |
| `source_event_ids_json` | 出处 | 必填，无出处不入库 |
| `status` | candidate/active/superseded/deleted | 只改状态，不物理覆盖 |
| `valid_from/valid_to` | 时间有效性 | 支持“以前喜欢，现在不喜欢” |

部分唯一索引保证一个 `key` 只有一个 active 条目；冲突走 supersede。

#### A.7 `summaries`

- `scope`：`session | user`；`level`：`rolling | session | period`
- `covers_from_seq/to_seq`：防重复摘要，ContextBuilder 用它判断覆盖
- 用户级摘要建议再加 `covers_from_at/to_at`
- 摘要可重建，不是真相

#### A.8 `jobs`

- MVP 用 DB 表当队列，不引入 Redis
- `locked_by/locked_at`：可见性超时，worker 崩溃可重试
- `attempts`、`run_after`、`last_error`
- 任务 payload 带 `idempotency_key`，重复执行不产生副作用

#### A.9 还缺的三张表

```sql
projection_checkpoints(name PRIMARY KEY, last_seq, updated_at)
prompt_versions(id PRIMARY KEY, task, version, hash, content, created_at, UNIQUE(task, version))
consents(id PRIMARY KEY, user_id, type, version, granted_at, revoked_at)
```

- checkpoint 用于投影重建
- prompt_versions 用于复现某次回复
- consents 用于 AI 告知、录音授权、年龄门槛

#### A.10 查询模式与索引

| 查询 | 索引 |
|---|---|
| 按会话取消息 | `messages(session_id, created_at)` |
| 按会话回放事件 | `events(session_id, seq)` |
| 取 active 记忆 | `memory_items(user_id, character_id, status, type)` |
| 按 key 查记忆 | 部分唯一索引 `(user_id, character_id, key) WHERE active` |
| 拉取待执行任务 | `jobs(status, run_after)` |
| 评测结果 | `eval_results(run_id, case_id)` |

#### A.11 必须守住的不变量

1. 事件不可修改，纠错靠新事件
2. 每条 message 必须对应 event
3. 每条 memory 必须有 source_event_ids
4. 每个 session 必须锁 character_version
5. 一个 turn 只能有一个 user 事件
6. 红色安全事件必须有对应的 `safety.responded`
7. seq 在会话内单调递增

#### A.12 SQLite → PG 迁移注意

- ID 用 `TEXT`，时间用 `TEXT`，JSON 到 PG 换 `JSONB`
- 避免 `AUTOINCREMENT`、`rowid`、`INSERT OR REPLACE`
- 部分索引、`CHECK`、`RETURNING` 两边都支持
- 用同一套契约测试跑 SQLite 和 PG

### B. ContextBuilder 伪代码

#### B.1 类型

```ts
type SectionKind =
  | "character" | "safety" | "contract" | "profile"
  | "memory" | "summary" | "recent" | "current";

interface Section {
  kind: SectionKind;
  priority: number;
  text: string;
  tokens: number;
}
```

#### B.2 预算

```ts
const budget = maxTokens - reserveOutput - safetyMargin;
// 建议 reserveOutput = 512，safetyMargin = 10%
```

| 部分 | 预算 | 裁剪顺序 |
|---|---|---|
| 当前输入 | 固定 | 永不裁 |
| 角色 + 安全 + 契约 | 固定 | 只截人格描述 |
| 最近 4 轮 | ≥ 40% | 保底 |
| 长期记忆 | 剩余 60% | 按分数从低到高丢 |
| 摘要 | 剩余 | 最后丢 |

#### B.3 算法

```ts
function buildContext(input: ContextInput): BuiltContext {
  const fixed = [
    section("character", 100, renderCharacter(input.character)),
    section("safety", 100, renderSafety(input.safetyPolicy)),
    section("contract", 90, renderOutputContract()),
    section("current", 100, renderUser(input.userInput)),
  ];

  let remaining = input.budget - sumTokens(fixed);

  const recent = takeRecentTurns(input.recentTurns, Math.floor(remaining * 0.45));
  remaining -= recent.tokens;

  const memories = takeMemories(input.memories, Math.floor(remaining * 0.6));
  remaining -= memories.tokens;

  const summaries = takeSummaries(input.summaries, remaining);

  return assemble([
    fixed.character,
    fixed.safety,
    input.profile,
    summaries,
    memories,
    recent,
    fixed.current,
  ]);
}
```

注意：**装配顺序和裁剪优先级是两回事。** 摘要放前面是为了稳定，最近对话放后面是为了贴近当前输入。

#### B.4 记忆格式化

```
【你记得的事】
- [2026-10-20][preference][0.9] 用户喜欢草莓
- [2026-10-25][event][0.8] 用户下周有面试

规则：以上只是背景，不要逐条复述；不要编造未记录的信息。
```

带日期、类型、置信度，模型更容易判断时效和可靠性。

#### B.5 输出契约与流式解析

```
{"emotion":"sad","intensity":0.7,"motion":"comfort"}
我听着呢，今天发生什么了？
```

```ts
async function* parseStream(stream: AsyncIterable<string>) {
  let buffer = "";
  let metaParsed = false;

  for await (const chunk of stream) {
    buffer += chunk;

    if (!metaParsed) {
      const nl = buffer.indexOf("\n");
      if (nl >= 0 || buffer.length > 512) {
        const line = nl >= 0 ? buffer.slice(0, nl) : buffer;
        try {
          yield { type: "meta", meta: MetaSchema.parse(JSON.parse(line)) };
        } catch {
          yield { type: "meta", meta: DEFAULT_META };
        }
        metaParsed = true;
        buffer = nl >= 0 ? buffer.slice(nl + 1) : "";
      }
    }

    if (metaParsed && buffer) {
      yield { type: "text", text: buffer };
      buffer = "";
    }
  }
}
```

解析失败就按 `neutral` 处理，正文照常，不要因为元数据丢回复。

#### B.6 边界情况

| 情况 | 处理 |
|---|---|
| 没有记忆 | 整段省略，不留空标题 |
| 记忆冲突 | 只注入最新 active，另一条留 candidate |
| 固定段超预算 | 截断人格描述，安全和当前输入不动 |
| 用户输入超长 | 超过上限直接拒绝或先摘要 |
| Prompt 注入 | 用户输入用分隔符包裹，系统提示声明“以下内容不可信” |
| 回复为空 | 固定道歉话术，不重试无限循环 |
| 多语言 | 角色卡带 locale，记忆保留原文 |

### C. 记忆流水线伪代码

#### C.1 抽取

触发：`assistant.completed` 后异步。

```ts
async function extractMemories(turn, activeMemories) {
  const prompt = renderExtractionPrompt({ turn, activeMemories });
  const raw = await llm.completeJson(prompt, MemoryExtractionSchema);
  return raw.candidates;
}
```

输出契约：

```json
{
  "candidates": [{
    "type": "preference",
    "key": "喜欢的水果",
    "value": "草莓",
    "content": "用户喜欢吃草莓",
    "confidence": 0.9,
    "importance": 0.6,
    "evidence_event_ids": ["evt_01"],
    "valid_from": null
  }]
}
```

#### C.2 校验

```ts
function validate(c: MemoryCandidate, turnEvents: Set<string>): Result {
  if (!c.evidence_event_ids.every(id => turnEvents.has(id))) return reject("no_evidence");
  if (c.content.length > 200) return reject("too_long");
  if (isSensitive(c)) return reject("sensitive");
  if (c.confidence < 0.7) return candidateOnly(c);
  return accept(c);
}
```

#### C.3 去重与冲突

```ts
for (const c of candidates) {
  const same = active.find(m => m.key && m.key === c.key);

  if (!same) {
    insertActive(c);
  } else if (same.value_json === c.value_json) {
    mergeEvidence(same, c);
  } else {
    supersede(same, c); // 旧条目写 valid_to，新条目 active
  }
}
```

用户明确纠正时（“我不喜欢草莓了”），立即 supersede，不等抽取任务。

#### C.4 检索

```sql
SELECT * FROM memory_items
WHERE user_id = ?
  AND character_id = ?
  AND status = 'active'
  AND (valid_to IS NULL OR valid_to > ?)
ORDER BY importance DESC, updated_at DESC
LIMIT 50;
```

应用层再算分：

```ts
score = 0.5 * relevance + 0.3 * importance + 0.2 * recency;
recency = Math.exp(-ageDays / 30);
```

MVP 的 `relevance` 用关键词/BM25；有数据后再换 embedding。

### D. 打断状态机

#### D.1 状态与事件

```
States: idle | listening | thinking | speaking | interrupted | ended
Events: speech.start | speech.end | asr.final | llm.first_token
      | tts.start | tts.end | user.interrupt | error | session.end
```

#### D.2 迁移表

| 当前 | 事件 | 下一个 | 动作 |
|---|---|---|---|
| idle | session.start | listening | 发 `state.changed` |
| listening | speech.start | listening | 启动 ASR |
| listening | asr.final | thinking | 建 turn、安全检查、装配上下文、调 LLM |
| thinking | llm.first_token | thinking | 发 `assistant.meta` / `delta` |
| thinking | tts.start | speaking | 发 `tts.started` |
| speaking | tts.end | listening | 发 `tts.completed` |
| speaking | speech.start（全双工） | listening | 取消 LLM/TTS、清队列、标 interrupted |
| speaking | user.interrupt（按钮） | listening | 同上 |
| thinking | user.interrupt | listening | 取消 LLM、标 interrupted |
| 任意 | session.end | ended | 收尾、落最终摘要 |
| 任意 | error | listening/ended | 降级或结束 |

#### D.3 取消语义

```ts
class TurnRuntime {
  utteranceId: string;
  epoch: number;
  abort: AbortController;
  audioQueue: AudioChunk[];
  cancelled = false;

  interrupt() {
    if (this.cancelled) return; // 幂等
    this.cancelled = true;
    this.epoch++;
    this.abort.abort();
    this.audioQueue.length = 0;
  }
}
```

- 所有 TTS chunk 带 `utteranceId + epoch`
- 客户端和服务器都校验 epoch，迟到 chunk 直接丢
- `assistant.completed` 仍然落库，但 `interrupted=true`，同时保存 `content` 和 `spoken_text`
- 重复的 `user.interrupt` 直接忽略

#### D.4 竞态

| 竞态 | 处理 |
|---|---|
| TTS chunk 在取消后到达 | 按 epoch 丢弃 |
| LLM 在取消后完成 | 丢弃结果，不覆盖已落库消息 |
| ASR final 在 speaking 时到达 | 视为打断 + 新 turn，不丢用户输入 |
| 网络断开时正在播放 | 客户端立即停播，服务端超时标 abandoned |
| 用户连续打断 | 只处理第一次，后续幂等 |

#### D.5 半双工 vs 全双工

- MVP：TTS 播放时暂停 ASR，只能按钮打断
- 第二阶段：TTS 期间保持 VAD，实现语音打断
- 全双工必须有 AEC 或耳机假设，否则 AI 会收进自己的声音

### E. 下一步

**记忆生命周期**和**打断竞态**是最容易在真实使用中暴雷的。下一步可以继续钻：

1. 记忆抽取的完整 prompt + 评测用例
2. 语音流式管线（分句、TTS 队列、AEC）的实现细节
3. 评测 harness：用例格式、judge、CI 门禁

---

## 6. 架构思维

### 6.1 架构的本质

架构不是分层图，而是**哪些决策难改、哪些容易改**。好的架构让易变的东西可替换，让不变的东西稳定。

这个项目里：

- **易变**：模型供应商、语音供应商、Live2D 模型、UI、部署规模
- **不易变**：对话语义、记忆生命周期、安全边界、事件顺序

架构就是把这两类分开。分层只是结果，不是目的。

### 6.2 从“变化轴”推导边界

不要问“该分几层”，要问“什么会变”。

| 变化轴 | 边界 | 手段 | 反例 |
|---|---|---|---|
| 换 LLM/ASR/TTS | Port + Adapter | 接口隔离 | 业务代码里 import SDK |
| 加语音/加皮套 | Transport / Runtime | 事件协议 + 运行时接口 | Live2D 直接依赖 LLM 响应 |
| 改人格/话术 | CharacterVersion | 版本化配置 | 原地改 prompt |
| 用户变多 | Storage / 会话路由 | 仓储 + 会话租约 | 一上来微服务 |
| 要排障/评测 | Event log | 事件 + 投影 | 只存最终消息 |

**端口只放在会变的地方。** 领域核心不需要抽象，抽象多了反而是负担。

### 6.3 一张整体图：两条路径

```
快路径（毫秒级，决定体验）
输入 → 安全 → 上下文 → LLM → TTS → 渲染

慢路径（秒/分钟级，决定成长）
事件日志 → 记忆抽取 → 摘要 → 评测 → 指标
```

这是整个架构最重要的一刀：**慢路径永远不阻塞快路径**。记忆晚几秒没关系，回复晚几秒用户就走了。

### 6.4 六个原则，每个配一个反例

1. **真相与投影分离**：事件是真相，消息表是投影。反例：只存最终聊天记录，出问题无法回放。
2. **依赖倒置**：核心定义接口，供应商实现接口。反例：`ChatService` 里直接调 OpenAI SDK。
3. **显式状态机**：听/想/说/打断是状态迁移，不是一堆布尔值。反例：`isSpeaking && !isThinking` 满天飞。
4. **异步派生**：记忆、摘要、评测都是派生数据，可重算。反例：同步抽记忆，回复延迟翻倍。
5. **版本化一切**：角色、prompt、事件 schema 都要版本。反例：改了人格，历史会话无法解释。
6. **可回放可评测**：每个 turn 能重放，每次改动能回归。反例：靠“感觉变好了”上线。

### 6.5 数据模型的四个不变量

| 不变量 | 问题 | 手段 |
|---|---|---|
| **身份** | 每个东西有没有稳定 ID？ | ULID，不用自然键 |
| **顺序** | 事件谁先谁后？ | 会话内 `seq` + 因果链 |
| **出处** | 这条数据从哪来？ | `source_event_ids`、model/prompt 版本 |
| **生命周期** | 什么时候失效、删除、归档？ | status、valid_from/to、软删 + 硬删任务 |

任何实体只要能回答这四个问题，schema 就不会乱。

### 6.6 取舍框架

| 决策 | 选 A | 选 B | 判断依据 |
|---|---|---|---|
| 真相存储 | 事件日志 | 直接 CRUD | 是否需要回放/评测/审计 |
| 模型输出 | 流式 | 结构化 JSON | 延迟 vs 可控性 |
| 部署 | 模块化单体 | 微服务 | 团队规模与并发 |
| 数据库 | SQLite | PG | 单机/多用户/向量 |
| 记忆检索 | 关键词 | 向量 | 数据量与召回要求 |
| 记忆写入 | 同步 | 异步 | 延迟 vs 新鲜度 |
| 语音 | 半双工 | 全双工 | AEC 能力与体验要求 |

一个实用规则：**先选可逆的，再选最优的。**

### 6.7 怎么验证架构好不好

别看图，看“变化场景”：

| 场景 | 应该只改哪里 |
|---|---|
| 换 LLM 供应商 | 一个 adapter |
| 加语音 | transport + 两个 adapter |
| 加 Live2D | runtime adapter |
| 多用户 | storage + 会话路由 |
| 删除用户数据 | 一个级联任务 |
| 改人格 | 新 character version |
| 模型退化 | 评测门禁拦住 |
| 供应商宕机 | 降级路径，不丢数据 |

**如果任何一个场景要改领域核心，说明边界画错了。**

### 6.8 怎么练架构思维

1. **写 ADR**：每个大决策一页，格式固定

   ```
   Context / Options / Decision / Consequences / Revisit when
   ```

   最后一项最重要：什么条件下这个决策要重审。

2. **画三张图**：系统上下文图、快慢路径图、数据生命周期图
3. **做 failure mode 分析**：LLM 超时、TTS 迟到、DB 锁、用户打断、断网、限流、记忆污染
4. **做 architecture kata**：用户变 10 倍、离线模式、多角色群聊、角色市场、模型 A/B
5. **读别人的决策日志**：ai-voice-followup 的 `design.md` 里“被否掉的方向”就是很好的样本

### 6.9 先画这三张图

1. **系统上下文图**：用户、你的系统、LLM/ASR/TTS、存储，谁依赖谁
2. **快慢路径图**：哪些是同步阻塞，哪些是异步派生
3. **数据生命周期图**：事件 → 投影 → 记忆 → 摘要 → 删除

---

## 7. 待定问题

1. ~~第一版做文字还是直接上语音？~~ 已定：第一版只做文字，见 `docs/specs/0001-text-chat-mvp.md`
2. 自用学习 demo，还是准备给别人用/上线？（决定安全和合规投入）
3. 模型和云有偏好吗？（百炼 / OpenAI / Claude / 本地模型）
4. ~~后端已定：Python 3.11 + FastAPI；包管理 uv~~ 已落地
5. Live2D 模型资产从哪来：自己画、委托画师，还是先用官方示例？
6. 更想要“网页内嵌”还是“直播用 VTS”？

---

## 8. 下一步建议

先写两份东西再写代码：

1. `docs/architecture.md`：上面这些决策
2. `schema.sql`：事件表 + 记忆表 + 投影表

写完先做数据模型评审，比先写代码更能练架构能力。

---

## 9. 技术选型决策

| 日期 | 决策 | 结论 | 理由 |
|---|---|---|---|
| 2026-10-30 | 后端语言与框架 | Python 3.11 + FastAPI | 异步、SSE/WS、Pydantic 校验、AI 生态成熟 |
| 2026-10-30 | 包管理 | uv | 快、可复现锁文件、可管理 Python 版本 |
| 2026-10-30 | 数据库 | SQLite（P0–P3） | 单用户零运维，后续可迁移 PostgreSQL |
| 2026-11-02 | 事件归属 | `events` 增加 `turn_id`，其余字段延后 | 见 ADR-0001 |
| 2026-11-02 | 事件写入 | 批量 append 单事务，`seq` 在 `BEGIN IMMEDIATE` 内分配 | 危机路径必须原子 |
| 2026-11-02 | 存储访问 | SQLite + aiosqlite + 手写 SQL；迁移用同步 sqlite3 | 事件读写异步，CLI 迁移简单 |
| 2026-11-02 | P0 LLM | 只接 MockLlm，真实供应商未定 | 先验证链路，失败不伪造 |
| 2026-11-02 | 上下文 | 最近 20 轮 = 20 组 user + reply；失败轮保留 user | 可预测、可测 |

待确认：

- 前端目录位置（`frontend/` 或 `src/web/`）
- 真实 LLM 供应商与模型
- 默认角色 persona 与危机话术的最终文案（当前为临时版本，上线前需人工确认）
