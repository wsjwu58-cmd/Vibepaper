# Pi 垂直短剧 Agent 二次开发方向设计

> - 状态：已确定的垂直领域子设计；从属于 pi-agent-full-replacement-design.md
> - 编制日期：2026-08-28
> - 优先级：角色一致性状态层、镜头级分镜流水线、一致性审校为首批 P0
> - 范围：Pi Agent 的短剧 profile、领域事实、节点合同、审校、批量渲染和开发次序

---

## 1. 核心结论

短剧 Agent 不能把对话上下文当作作品状态。它需要一个可跨集查询、可版本化、可由工具读写的短剧领域事实层。Pi 负责在这个事实层上调用阶段工具；Canvas Text 节点、Memory 和对话只是人机交互与检索投影，不是唯一事实源。

因此采用三层表示，而不是只选 Memory 或 Text 节点：

| 层 | 定位 | 写入方式 | 读取方式 |
|---|---|---|---|
| Drama State Store | 唯一真相源。角色、世界、时间线、剧集、镜头、渲染谱系的结构化版本事实 | 仅受控工具和经过验证的 Text 节点编辑写入 | 所有生成、审校、重跑和查询必须从此层读取 |
| Canvas 投影 | 可编辑、可连接、可视化的 Text/媒体节点；每个节点指向状态实体和版本 | 用户编辑触发解析、差异预览、校验后提交新 revision | 用户与 Agent 通过画布理解、选择、局部修改 |
| Memory/检索索引 | 偏好、摘要、快捷查询和语义召回 | 由 State Store 事件异步投影 | 不可作为角色外形、时间线、伏笔等硬事实的裁决依据 |

这是本设计比“memory + Text 节点”更严格的一点：Text 节点必须可读可写，但自由文本不能直接成为 Canon。它先被解析为结构化 patch，再经版本和冲突校验写入 State Store；成功后回写节点投影。否则人工编辑和 Agent 编辑会形成两套互相漂移的真相。

## 2. 领域状态模型

### 2.1 聚合与版本原则

每个短剧 Canvas 绑定一个 Drama Series。Series 的 Canon 以 revision 为单位提交，所有生成节点记录自己使用的 Canon revision、角色 Look revision、参考素材 revision 和 Prompt revision。

| 聚合 | 最小字段 | 关键不变量 |
|---|---|---|
| DramaSeries | seriesId、canvasId、title、formatSpecId、activeCanonRevision | 同一 Canvas 至多一个 active Series；所有下游对象可追溯到其 revision。 |
| CharacterProfile | characterId、名字、身份、外形锚点 3-5 条、体型、发型、脸部特征、标志物、语气、voiceId | 外形锚点不可原地改写；修改需创建新 Look revision，并标记受影响镜头。 |
| CharacterLook | characterId、revision、服装表、三视图、表情表、角色参考包、负面约束 | 进入人物镜头的每个角色必须解析到一个已批准的 Look revision。 |
| WorldBible | 场景库、道具库、世界规则、时间线、禁忌、视觉风格边界 | 所有 Scene、Prop、TimelineEvent 必须引用有效的 Canon entity。 |
| Episode | episodeNo、目标、首 3 秒钩子、集尾断点、反转、伏笔、预算 | 单集有明确 target duration 与 shot budget，不能只保存散文大纲。 |
| Scene | episodeId、sceneNo、地点、时间、人物状态、冲突、道具状态 | 场景的进入/离开状态必须能被后续 Scene 查询。 |
| ShotSpec | shotId、sceneId、叙事功能、时长、机位、角色/Look、道具、Prompt、字幕/音频、安全区 | 是关键帧、视频、TTS、字幕和重跑的唯一镜头级输入。 |
| ContinuityFact | subject、fact、有效范围、来源、严重度、revision | 必须可由审校器定位到 episode/scene/shot。 |
| Foreshadow | plantedAt、plannedPayoff、status、resolvedAt | 状态只能为 planted、due、resolved、waived；waived 必须有原因。 |
| RenderLineage | shotId、promptRevision、referencePackId、keyframeNodeId、videoNodeId、taskId、status | 任一产物能定位到其状态、参考图和操作记录。 |

建议采用“结构化表 + revision JSON 快照”的组合：可查询字段单独建表与索引，完整 Canon snapshot 保存为不可变 JSONB revision。这样可跨集查询角色/时间线，又能显示历史版本、计算差异并支持回退。

### 2.2 状态写入合同

所有领域写操作都走以下流程：

    读取 active revision
      -> 生成结构化 patch
      -> schema、权限、时间线和引用校验
      -> 冲突检测
      -> 写 revision 与 outbox
      -> 更新 Canvas Text 投影
      -> 标记下游影响范围

Text 节点必须带 stateRef、entityType、entityId、revision、projectionHash。编辑时 projectionHash 不匹配表示存在并发变化，拒绝覆盖并返回差异。Canvas 的 version 乐观锁继续生效；领域 revision 不替代 Canvas version。

角色的外形锚点建议区分：

- Identity anchors：面部骨相、瞳色、发型、体型、标志物。跨剧集默认不可变。
- Look variables：服装、妆容、伤势、年龄阶段。必须有剧情原因、适用范围和 revision。
- Performance profile：声线、语速、语气、常用情绪。TTS 由 voiceId 和该配置解析，不能由每镜自由传参。

## 3. 一致性执行链

### 3.1 角色参考是工具硬约束

人物镜头的合法调用链是：

    CharacterProfile
      -> 已批准 CharacterLook
      -> 三视图和表情表 ReferencePack
      -> ShotSpec
      -> Keyframe Node
      -> Video Node

关键规则：

1. 创建人物 ShotSpec 时，工具必须解析每个角色的 active Look revision。
2. 创建关键帧节点时，工具必须将角色 ReferencePack 中的参考素材作为 input/reference 连线写入节点。
3. 若已存在唯一的已批准 ReferencePack，允许自动补挂并在事件中明确回显。
4. 若 ReferencePack 缺失、过期或出现多个候选，拒绝提交并返回 action required；禁止模型猜测或静默降级。
5. 提交关键帧和视频时再次验证角色参考、Look revision、状态 revision、素材可访问性和节点依赖，避免绕过创建工具。
6. 视频节点必须复用其关键帧和角色参考；只允许重跑当前 ShotSpec，不允许无谱系的新视频覆盖旧产物。

自动补挂只适用于唯一且已批准的角色参考包。没有“唯一”这个条件时，自动化会把错误角色或错误服装批量传播，风险比拒绝更高。

### 3.2 状态变更的定向影响

变更不会自动无边界重生成。工具先计算 impact set：

| 变更 | 必须失效/标记待复核 | 默认动作 |
|---|---|---|
| 角色 identity anchor | 该角色参与的全部 Keyframe/Video lineage | 只标记 stale，要求用户选择局部或全量重跑。 |
| 某套服装或伤势 | 适用范围内的 ShotSpec 与下游媒体 | 提供镜头列表与成本预估。 |
| 场景/道具/时间线事实 | 受影响 Scene、ShotSpec 与审校报告 | 重新审校后再允许重渲。 |
| 镜头 Prompt | 当前镜头的关键帧和视频 | 先重出低成本关键帧。 |
| 视频模型/参数 | 当前 RenderLineage | 创建新 revision，不覆盖历史。 |

## 4. 分层创作流水线

一句话生成整集只能作为 Demo 或创建初稿入口，不能是生产主路径。生产主路径固定为独立、可编辑、可回退的对象链：

    故事圣经
      -> 单集 Beat/剧本
      -> Scene
      -> ShotSpec
      -> 镜头级 Prompt
      -> 关键帧预览
      -> 视频
      -> TTS/字幕
      -> 拼接与交付

每层都有独立 Node 投影、状态实体、revision、输入依赖和验收状态。上游修改只生成影响报告，不立即重跑下游。

### 4.1 镜头级刚性门

ShotSpec 是短剧 P0 的最小生产单元，至少包括：

- 叙事目的、时长、景别/机位/运动、进入状态和结束状态；
- 角色与 Look revision、场景、道具、屏幕方向、光线、情绪；
- 台词、音效、字幕、安全区、口播节奏；
- 镜头 Prompt 和 Negative constraints；
- 关键帧、视频、音频、字幕节点及其状态。

任何 Video、TTS 或字幕生成请求必须引用 ShotSpec。没有 ShotSpec 的生成请求直接拒绝；这比生成后再补结构可靠得多。

### 4.2 两段式渲染

    ShotSpec 定稿
      -> 低成本关键帧批次
      -> 一致性审校和人工挑选
      -> 高成本视频批次
      -> 局部重跑/拼接

关键帧阶段是视觉锁定点，不可跳过。视频仅能引用已接受的关键帧和有效角色参考。若关键帧被替换，关联视频应标为 stale，不可自动继续提交。

## 5. Skill 与 SYSTEM 的职责

### 5.1 全局 SYSTEM 只管纪律

全局 system prompt 控制在几十行，内容只包括每次成立且违反即出错的硬规则：

- 默认竖屏 9:16。
- ShotSpec 是视频、TTS、字幕和渲染的必经对象。
- 人物镜头必须绑定批准的角色参考包。
- 单镜默认 2-5 秒；偏离需显式记录理由。
- 首 3 秒必须有 hook；集尾必须有断点。
- 不得绕过 Tool Gateway、审批、状态版本与领域校验。

不得把剧本模板、角色卡字段、题材套路和长教程写进 SYSTEM。它们会稀释纪律且跨任务互相干扰。

### 5.2 Skill 按创作阶段加载

| Skill | 输入 | 结构化输出 | 可写状态 |
|---|---|---|---|
| 故事圣经 | 主题、受众、已有设定 | WorldBible、CharacterProfile、关系、长线伏笔 | Canon patch |
| 单集 | episode goal、Canon、已用反转/伏笔 | Episode、Beat、hook、cliffhanger | Episode revision |
| 分镜 | Episode、Scene、CharacterLook、场景/道具 | ShotSpec 列表和 Prompt draft | Scene/Shot revision |
| 对白润色 | 指定 ShotSpec、角色语气、时长 | Dialogue/Subtitle patch | Shot revision |
| 一致性审校 | 只读 Canon、Episode、ShotSpec、产物元数据 | AuditReport | 不可直接写 Canon |

甜宠、逆袭、悬疑等题材是上述 Skill 的 genre parameters 或示例模板，不单独成为一组平行 Skill。这样故事圣经与分镜能共享同一状态模型，不产生组合爆炸。

## 6. 独立一致性审校 Agent

审校不是生成 Agent 的一个自检步骤，而是单独的 Pi invocation：

| 项目 | 审校 Agent 约束 |
|---|---|
| Session | 独立 audit session，不继承生成 Agent 的 assistant 思维链或成功偏好。 |
| 输入 | 只读 Canon revision、Episode/Scene/ShotSpec、RenderLineage、参考图元数据与历史 AuditReport。 |
| 工具 | 仅 query、compare、evidence retrieval；没有 create/update/submit 工具。 |
| 输出 | 结构化 AuditReport：ruleId、severity、entity refs、evidence、最小修复建议、是否阻塞视频/拼接。 |
| 执行时机 | 分镜完成、关键帧接受前、视频批次提交前、拼接前，以及 Canon revision 变更后。 |

审校规则分两类：确定性规则优先由代码完成，例如缺角色参考、镜头时长越界、字幕安全区、未回收伏笔、时间线次序；语义一致性才交给审校模型，例如外形漂移、动机矛盾、道具穿越、信息知情范围不一致。

这是比“独立一个审校 prompt”更可控的实现：审校报告必须引用证据和实体 ID，不能只给泛泛评价。生成 Agent 可以读取报告提出修复 patch，但不能自行把报告标为通过。

## 7. 竖屏短剧默认规格与成本调度

### 7.1 默认 FormatSpec

FormatSpec 是版本化配置，不散落在 Prompt：

| 字段 | 初始默认 | 执行约束 |
|---|---|---|
| aspectRatio | 9:16 | 所有 Keyframe/Video 节点默认写入，变更需显式确认。 |
| shotDuration | 2-5 秒 | ShotSpec 校验；超范围需给出叙事理由。 |
| openingHook | 前 3 秒 | Episode/Shot 审校规则。 |
| endingCliffhanger | 必须 | Episode 审校规则，允许标记 author-approved waiver。 |
| subtitleSafeArea | 顶部/底部安全区 | Subtitle 生成和渲染校验使用具体百分比配置。 |
| speechRate | 角色 voice profile 默认值 | TTS 任务不能绕过 voiceId。 |
| renderStrategy | keyframe-first | Video 批次必须有 accepted keyframe。 |

单集 60-90 镜与单镜 2-5 秒推导出的成片长度为 120-450 秒，即 2-7.5 分钟。这与现有 1-3 分钟的默认 Skill 不一致，不能同时作为默认值。产品必须按内容类型定义 FormatSpec，而不是在全局写一个含糊的“短剧默认”。

### 7.2 批量调度和成本安全

引入 RenderBatch 和 RenderJob 两级实体：

| 实体 | 作用 |
|---|---|
| RenderBatch | 某集/场景/筛选集合的批次意图、预算上限、优先级、并发上限、确认状态和汇总进度。 |
| RenderJob | 单个 ShotSpec 的关键帧/视频/TTS/字幕任务，含 action、task、attempt、成本、依赖和局部重试状态。 |

批次调度必须先做依赖图和预算预检，再创建单镜 Job；不能一次向生成服务发送几百个无状态请求。失败默认只重试同一 ShotSpec 与同一 lineage，超过重试阈值转人工处理。

批量确认需要新增 Group Approval：一个 token 绑定 batch manifest hash、成员 job ID 集、每项与总成本上限、Canvas/Canon revision、有效期。成员变化或成本上浮即令 token 失效。它需要在 PRD/计费契约中明确“批量确认”的授权语义；没有该决议时，不得用 UI 批量按钮绕过现有单动作确认。

## 8. Pi 二次开发任务拆分

| 顺序 | 包/模块 | 先做什么 | 验收 |
|---|---|---|---|
| P0-1 | domain/drama-state | Series、角色、Look、World、Episode、Shot、revision、Text 投影合同 | 角色状态跨会话/跨集查询不丢失；并发编辑不覆盖。 |
| P0-2 | tools/character-reference | ReferencePack 解析、自动补挂、缺失拒绝、Video 二次校验 | 人物镜头 100% 有批准参考；无参考不产生任务。 |
| P0-3 | domain/shot-pipeline | Story -> Episode -> Scene -> Shot -> Keyframe -> Video 的依赖与 impact set | 改第 37 镜只使第 37 镜 lineage stale。 |
| P0-4 | pi/skills | 五个阶段 Skill、短 SYSTEM、profile manifest、结构化 patch 输出 | 题材通过参数化，不产生题材 Skill 组合。 |
| P0-5 | pi/auditor | 独立只读 audit session、规则引擎、AuditReport、阻塞门 | 审校结果含实体证据，阻断不合格视频批次。 |
| P1 | application/render-batch | Keyframe-first、Batch/Job、队列、部分失败重试、Group Approval | 失败镜头局部重跑，总预算不可超授权。 |
| P1 | rhythm auditor | hook、时长、信息/反转密度的量化审校 | 只在指标稳定后启用；不做主观感觉评分。 |

首个可演示的纵切不应是一整集视频，而应是：建立角色档案和三视图 -> 创建 3 个 ShotSpec -> 自动挂参考生成低成本关键帧 -> 审校 -> 只对接受的镜头提交视频。它能同时验证最关键的三个 P0。

## 9. 必须先确定的产品/架构决策

1. 单集目标时长和镜头数。是否采用 1-3 分钟/约 20-45 镜，还是 2-7.5 分钟/60-90 镜？这会直接决定成本、并发和节奏算法。
2. 角色 identity anchor 的修改权限。建议只有项目 owner/指定编剧能创建新 Canon revision，其他成员只能提议 patch。
3. ReferencePack 的最低组成。建议至少一张批准正面身份图；P0 的人物主角要求正/侧/背三视图和表情表，配角可使用简化档。
4. Canon Text 节点编辑冲突时采用何种交互。建议差异预览 + 显式合并，禁止最后写入者覆盖。
5. Group Approval 是否纳入 P0。若需要批量量产，建议纳入；若 PRD 暂不修改，则先限制为预览批次和逐镜确认。
6. 字幕安全区的具体比例、TTS 支持语言、voiceId 是否允许跨角色复用。
7. 审校 Agent 的阻塞等级。建议 must 级错误阻断视频/拼接，should 级只警告，optional 级仅记录。

## 10. 建议采纳的额外原则

- 将 Canon revision 作为任何生成节点的输入哈希，而不仅是一个展示字段。它能让错误产物的来源可追溯、可批量定位。
- “自动补挂”只能补唯一已批准引用；不确定时要求用户决定。自动猜测是角色一致性系统最大的隐患。
- 先建设确定性审校规则库，再增加模型审校。缺引用、超时长、字幕越界、依赖非法等问题不应消耗模型调用。
- 从一开始记录每个镜头的成本、失败原因、重跑次数和被接受率；这些数据会决定之后是否值得增加节奏审校、换模型或调并发。
- 把局部重生成设计为创建新 RenderLineage，而不是覆盖 URL。短剧量产需要比较、回退和复用旧版本。

## 11. 参考现有实现

- agent-service/src/agent/domain/drama_schema.py 已有 SeriesBible、CharacterProfile、CharacterLook、ShotSpec 与 RenderReview 的初始形状，可作为迁移素材，但需增加 revision、ReferencePack、时间线、伏笔与渲染谱系。
- agent-service/src/agent/models.py 的 AgentAction、AgentApproval、RenderReview、Skill、UserMemory 是迁移到 Node 服务时需要保持兼容的业务记录。
- agent-service/src/agent/domain/default_skills_seed.py 已按故事圣经、单集、分镜、对白和一致性审校提供初始内容；迁移时改为阶段 profile，而不是题材分支。
- pi-agent-full-replacement-design.md 规定了 Pi、Tool Gateway、审批、SSE、数据迁移和 Python Agent 下线的服务级边界。
