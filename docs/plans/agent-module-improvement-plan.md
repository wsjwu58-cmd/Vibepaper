# Agent 模块全面审查与改进实施方案

> 状态：P0 控制面已在 `codex/agent-module-improvements` 工作区实现并通过定向回归；待多服务联调。P1/P2 仍按本文排期推进。
> 依据：`AGENTS.md`、PRD、`docs/specs/V1.0-engineering-spec.md`、`docs/agent-control-plane-p0-spec.md` 与 2026-08-26 代码审查
> 目标：将当前“可编排的画布 Agent”升级为**安全可计费、可恢复、可审计、可局部重跑**的短剧生产 Agent。

## 1. 结论与原则

当前 `agent-service` 已具备 LangGraph、工具白名单、画布 DAG、任务 ACK、Skill、任务唤醒和基础记忆等主干能力。后续工作不得替换现有框架，也不得先新增自由对话式多 Agent；应先完成资金安全和异步执行控制面，再把短剧能力沉淀为结构化创作资产与质量闭环。

实施遵循以下原则：

1. **确认先于扣费**：所有会产生点数、覆盖输出、删除节点或批量创建超过 20 个节点的动作，必须使用一次性确认令牌。
2. **业务幂等先于重试**：重放、恢复、双消费者和网络超时都不得导致重复创建节点、重复冻结点数或重复提交任务。
3. **事件主路径、轮询兜底**：生成终态事件唤醒 Agent；`clock` 仅处理事件丢失和超时检查。
4. **画布保存资产，Agent 保存决策**：画布是创作资产和依赖关系的真相源；LangGraph 保存计划、审批、等待和恢复状态；记忆仅保存跨轮有效事实。
5. **短剧先领域化、再角色化**：编剧、分镜、连续性、声音和质检角色的输入输出必须是 schema，而不是仅靠提示词约定。

### 1.1 本轮实施状态（2026-08-27）

| 工作项 | 状态 | 本轮结果与上线前剩余事项 |
|---|---|---|
| 高风险确认 | 已实现 | 移除对话文本自动放行；确认 API 消费签名的一次性令牌，绑定用户、画布/计划版本与动作摘要；画布端已接入确认卡，展示影响与预估点数并回显确认后的增量事件。 |
| Action 幂等与审计 | 已实现 | 生成提交使用 `action_id + attempt_no` 派生键；异步任务 ID 回写 Action，并可按终态定位会话。需在 billing/generation 联调中验证冻结流水的端到端唯一性。 |
| generation 终态恢复 | 已实现 | 新增 `/internal/agent/resume`、服务间令牌校验、终态 notice 去重与处理中恢复标记。生产环境必须配置两端相同的 `VIBEPAPER_INTERNAL_SERVICE_TOKEN`。 |
| 时钟竞争 | 已实现 | 生产默认关闭服务内扫描，使用 Celery Beat；ZSET 采用 Lua 原子 claim。仍需在部署清单保证只启动一种生产扫描器。 |
| 数据迁移 | 已实现 | Alembic 从双 head 收敛为 `002_wakeup_notice_processing` 单 head；配置文件不再写入数据库口令。需在干净 PostgreSQL 库执行 upgrade 验证。 |
| 记忆检索 | 已实现（基础） | 已替换无词维度词频余弦为稳定哈希嵌入，并接入软删除/过期过滤；pgvector、企业隔离和来源 UI 仍属后续项。 |
| 短剧 schema / 资产 API | 部分实现 | `canvas-service` 已新增 `drama_assets` / 幂等命令快照、Flyway V4/V5 与 `/api/v1/canvases/{canvasId}/drama-assets`。支持故事圣经、角色 Look、ShotSpec、音频/字幕等资产的校验、画布乐观锁及按范围查询；画布侧栏已可查看、新建和编辑九类资产。节点引用自动同步、领域表单细化和 Agent 编译链路仍待完成。 |
| 质量门与计划审计 API | 部分实现 | Agent 已提供计划摘要查询与 `render-reviews` 记录/路由：只返回局部重跑或人工复核建议，绝不直接提交任务。视觉/音频评估器、审片 UI 与“将建议编译为待确认 Action”的流程仍待接入。 |

## 2. P0：安全与可靠性控制面

### 2.1 强制确认协议

替换当前基于自然语言关键字的高风险自动确认逻辑。`submit_generation`、`delete_nodes`、`replace_output`、`change_model` 及所有媒体加工工具一律进入 `interrupt()`；用户仅表达“生成”或“删除”不构成确认。

确认事件与确认 API 使用以下不可变载荷：

```json
{
  "actionId": "snowflake-id",
  "approvalToken": "signed-one-time-token",
  "userId": "...",
  "canvasId": "...",
  "canvasVersion": 12,
  "planVersion": 4,
  "actionHash": "sha256(tool + normalizedParams + childCostCap)",
  "estimatedCost": 30,
  "chainEstimatedCost": 106,
  "expiresAt": "2026-08-26T00:00:00Z"
}
```

- 令牌服务端签名并持久化 nonce；确认时校验用户、画布、画布版本、计划版本、动作摘要、过期时间和“未使用”状态，然后原子消费。
- 前端新增确认卡片，展示影响节点、单次/链路预估点数、自动推进范围；只允许卡片确认或拒绝，不以普通聊天文本替代。
- 自动推进下游任务必须绑定根确认记录和 `approved_cost_cap`。实际累计估价超过批准上限时，停止在待确认状态；任何新增节点、变更模型或参数变化达到 30% 时创建新审批。

### 2.2 幂等与任务恢复

- `agent_actions` 增加 `idempotency_key`、`plan_version`、`approval_id`、`attempt_no`、`parent_action_id`；为 `(session_id, plan_version, step_id)` 和 `idempotency_key` 建唯一约束。
- 任务提交的 `Idempotency-Key` 固定由 `agent_action_id` 及尝试号派生，禁止使用随机 UUID。
- `agent_wakeup_notices` 记录 `(session_id, task_id, terminal_status)`，以唯一约束实现终态事件去重。
- Redis ZSET 扫描改为 Lua 原子 claim，或迁移到 Redis Stream consumer group；服务进程内扫描与 Celery Beat 二选一，生产默认仅运行 worker/beat。
- 所有恢复逻辑先读取 `AgentAction` 和画布节点实际状态；已受理/运行/成功的任务只回放状态，不再提交。

### 2.3 生成终态事件主路径

- 在 agent-service 实现并鉴权 `POST /internal/agent/resume`，接收 generation-service 的 `generation_terminal` 事件。
- 事件消费者验证任务、用户、画布和节点的一致性，读取画布最新真相后执行 wakeup 子图；不得信任回调中的产物内容覆盖画布。
- `pending_jobs` 持久化在 LangGraph state/动作表中；终态后只解锁当前 Ready Set，所有待处理任务仍存在时写 checkpoint 后结束。
- `clock` 默认延迟 10 分钟，仅在未收到终态事件时查询一次；查询仍为运行中才按退避策略重新登记。

### 2.4 数据、安全与可观测性

- 用 Alembic 管理 agent-service 所有迁移，删除启动期 `ALTER TABLE` 补丁；为动作、审批、唤醒通知和短剧资产建立明确外键/唯一索引。
- 运行配置不提供可用的数据库、Redis、Nacos 默认密码；仅通过环境变量或密钥管理服务注入。
- 每个 Agent span 必带 `request_id`、`session_id`、`canvas_id`、`canvas_version`、`plan_version`、`action_id`、`task_id`、`idempotency_key`、`estimated_cost` 与 `error_code`。
- 以 OpenTelemetry trace 或等价链路追踪串联“用户指令 → 计划 → 审批 → 调用 → 任务 → 终态 → 下游解锁”；原有 Redis telemetry 仅作为事件汇聚，不作为唯一审计源。

## 3. P1：短剧领域模型与编排

### 3.1 新增领域实体

短剧创作不再只由通用 text/image/video 节点表达。新增下列 schema，并在 Canvas 节点 `params` 中保存其稳定 ID 和版本：

| 实体 | 最小字段 | 作用 |
|---|---|---|
| `SeriesBible` | premise、world_rules、canon_version | 全剧世界观与不可违背设定 |
| `Episode` / `Scene` | episode_no、goal、hook、scene_order | 集与场的叙事边界 |
| `CharacterProfile` | identity_anchor、static_traits、dynamic_state | 角色事实与本集状态 |
| `CharacterLook` | character_id、costume、reference_asset_ids、version | 外观、服装和参考图版本 |
| `ShotSpec` | shot_no、duration、purpose、camera、screen_direction、dialogue、audio_cues | 可执行镜头合同 |
| `ContinuityConstraint` | subject、rule、scope、severity | 人物/服装/道具/空间/时间连续性规则 |
| `RenderReview` | target_node_id、scores、failures、recommended_action | 生成结果的质量门禁 |

所有实体使用 Snowflake ID，时间为 UTC。`ShotSpec` 必须明确绑定角色外观、场景、道具和上游脚本/分镜版本；节点标题仅用于展示，不作为引用依据。

### 3.2 标准短剧 DAG

```text
SeriesBible → EpisodeScript → CharacterProfile/CharacterLook
            → ShotSpec[n] → Keyframe[n] → Clip[n] ─┐
AudioCue[n] ────────────────────────────────────────┼→ Timeline/Compose → RenderReview
Subtitle[n] ────────────────────────────────────────┘
```

- 角色肖像、三视图、服装 Look 必须先生成并成为 `reference` 输入；角色卡文本不能单独视为视觉一致性实现。
- 每个 `ShotSpec` 独立生成首帧和视频，变更时只使受影响的下游 `input` 依赖节点 stale。
- 生成音频、字幕、转场和时间线组装是主链路组成部分，不再只做视频片段拼接。
- 默认竖屏 9:16；时长、模型、音轨策略以用户显式输入优先，其次为 episode/series 偏好，最后才使用模型默认值。

### 3.3 专业角色与确定性编排

保留一个主编排器，不让角色 Agent 自主修改画布。将角色能力实现为受 schema 约束的步骤：

1. **编剧**：输出 Episode/Scene/对白与集尾钩子。
2. **分镜导演**：将 Scene 编译为 `ShotSpec[]`，补全镜头目的、机位、调度、屏幕方向和节奏。
3. **视觉连续性审校**：维护 CharacterLook、场景、服装、道具、光线与方向约束。
4. **声音设计**：输出对白时长、角色声线、旁白、音效、BGM 与字幕时码。
5. **制片/质检**：按预算、依赖、模型能力、连续性分数和内容安全决定提交、局部重试、人工复核或终止。

每一步仅可读取上游 schema 并输出自己的 schema；由 adapter 将 schema 编译成既有 `TOOLS` 调用，LLM 不可输出裸 `node_id` 或直接工具参数。

## 4. P2：质量闭环、记忆与体验

### 4.1 多模态质量门禁

- Keyframe：人物身份、服装、场景、构图和文字污染检测。
- Clip：首尾帧一致性、运动合理性、角色漂移、屏幕方向、动作/镜头匹配和时长检查。
- Episode：叙事钩子、冲突升级、对白可表演性、镜头覆盖、音画同步、字幕可读性和连续性检查。
- 每项输出分数、证据、失败类型和最小修复动作。低于阈值仅重跑受影响节点；连续失败两次、预算超限或叙事歧义时进入人工确认。

### 4.2 记忆治理

- 短期记忆只保存会话工作上下文；日记忆保存当天可过期偏好；长期记忆保存可复用、用户授权的偏好；项目记忆保存 canon 摘要与关键决策。
- 采用带词维度的 embedding 或 pgvector，禁止将无词维度的频次数组用于余弦相似度。
- 每条记忆带来源、scope、置信度、可见性、TTL 与删除标记；企业场景须隔离 tenant/user/project 范围。

### 4.3 画布与前端体验

- 增加“短剧项目”侧栏：故事圣经、角色资产、分镜表、镜头包、任务时间线、质量报告和预算。
- 画布节点可打开 `ShotSpec` 编辑器与局部重跑面板；重跑前明确展示受影响节点、费用和审批范围。
- 确认卡、任务时间线和 SSE 事件支持断线重连与幂等回放；不展示内部 ID、原始异常或链路实现细节。

## 5. 接口与数据契约

新增或调整接口，均遵循 `/api/v1`、ISO 8601 UTC、错误体 `{ code, message, details, request_id, retryable }`：

| 接口 | 行为 |
|---|---|
| `POST /agent/sessions/{id}/confirmations/{actionId}` | 仅接收 `approvalToken`、`accept`、可编辑但需重新哈希的确认参数 |
| `POST /internal/agent/resume` | generation 终态事件入口；仅服务身份调用，幂等消费 |
| `GET /agent/sessions/{id}/plans/{planVersion}` | 返回可审计计划、动作、审批和等待任务摘要 |
| `POST /canvases/{id}/drama-assets` | 创建/更新结构化短剧资产，使用乐观锁和 `Idempotency-Key` |
| `GET /canvases/{id}/drama-assets` | 按 `episode_id`、`scene_id`、`shot_id` 查询资产与引用 |
| `POST /render-reviews` | 写入异步质检结果；不直接修改生成资产 |

确认、创建资产、提交生成、局部重跑和任何成本操作都要求 `Idempotency-Key`。OpenAPI 更新后通过 `openapi-typescript` 重新生成前端类型。

## 6. 测试、验收与发布

### 6.1 必须测试

- 单元：审批令牌绑定/过期/重放、固定幂等键、预算上限、Ready Set、stale 传播、质量路由、记忆 scope。
- 集成：Testcontainers 下 billing 冻结→生成→终态事件→下游解锁；事件重复、worker 并发、网络超时、恢复重放均只产生一个任务/流水。
- 契约：确认、resume、短剧资产和质量报告 OpenAPI 差异检测与 Schemathesis。
- E2E：创建短剧→编辑分镜→确认根任务→断线重连→单镜失败局部重跑→合成→质量复核；验证点数、画布版本与任务状态一致。
- 评测：建立不少于 30 个短剧样例，比较角色一致性、分镜字段完整率、连续性缺陷、一次成片率、平均点数和人工修正次数。

### 6.2 验收指标

| 指标 | P0 门槛 | 短剧能力门槛 |
|---|---:|---:|
| 重放/双消费者重复提交 | 0 | 0 |
| 高风险无确认执行 | 0 | 0 |
| 终态事件 5 分钟内送达率 | ≥99% | ≥99% |
| 短剧镜头 schema 完整率 | — | ≥98% |
| 自动质检拦截的明显连续性缺陷准确率 | — | 建立人工标注基线后持续提升 |
| 单镜失败局部重跑率 | — | 100% 可用，禁止全链路无故重跑 |

### 6.3 推荐排期

1. **第 1–2 周**：P0 确认、固定幂等、单消费者、resume 事件、迁移与集成测试。
2. **第 3–4 周**：短剧领域 schema、资产 API、角色 Look 与镜头 DAG、前端确认卡。
3. **第 5–6 周**：声音/字幕/时间线、连续性与视觉质量 Review、局部重跑。
4. **第 7 周起**：离线评测集、追踪面板、灰度发布与指标优化。

## 7. 明确不做

- 不引入可绕过工具白名单、直接写数据库或自由执行 SQL 的 Agent。
- 不以多 Agent 自由聊天替代确定性计划、审批和账务控制。
- 不在 P0 阶段引入多人实时协同编辑、企业跨成员内容可见性放宽或复杂剪辑工作站。
- 不把整张画布 JSON、完整视频二进制或未经筛选的原始工具结果写入 LangGraph checkpoint/长期记忆。

## 8. 审查范围、方法与现状基线

### 8.1 审查范围

本报告覆盖 `agent-service` 的对话编排、工具调用、确认、人机协作、会话/记忆、Skill、异步生成任务回调、定时唤醒、画布 DAG 与短剧工作流；同时检查了其与 `generation-service`、`canvas-service`、`billing-service` 的契约边界。结论以仓库 2026-08-26 的实现为准，不假定设计文档中标为“已完成”的能力已经落地。

审查采用以下方法：

1. 使用 CodeGraph 索引追踪图状态、工具注册、动作记录、任务回调及调度的跨文件调用关系；关键结论再用文本检索回查，避免只依赖静态解析。
2. 读取 PRD、工程 Spec、技术概要、控制面 P0 Spec 与 `AGENTS.md`，将代码行为逐项和产品契约比对。
3. 对照开源的 LangGraph、OpenAI Agents SDK、ViMax 与 Open-AI-Micro-Drama-Generator，重点比较运行时治理和短剧生产工艺；它们是设计参考，不作为可直接复制的生产代码。
4. 运行 Python 测试收集。当前收集到 190 个测试；完整测试在对话问候用例进入真实 LLM 路径后迟滞，已停止该测试进程，未将“测试卡住”误报为通过。

### 8.2 当前能力盘点

| 领域 | 已有能力 | 评价 |
|---|---|---|
| 编排 | LangGraph 主图、计划/执行节点、画布 DAG 规划、任务 ACK/唤醒 | 架构方向正确，但恢复语义未闭环 |
| 工具 | 工具白名单、参数解析、画布节点/连线与生成提交封装 | 有基本隔离，仍需把所有写操作落到可审计 action |
| 人机协作 | `interrupt()`、确认辅助逻辑、会话消息 | 有骨架，但令牌校验和前端确认闭环未完成 |
| 异步生成 | generation 提交、任务状态、Redis 时钟扫描、Celery Beat | 事件入口缺失且存在双扫描竞争 |
| 创作 | 文本/角色文本/分镜/首帧/视频/合成 DAG、可按节点重跑 | 是“视频生产原型”，尚不是完整短剧生产线 |
| 知识与复用 | Skill 种子、短期/长期记忆接口 | 内容能存，检索与治理不足 |
| 安全与资金 | 工具限制、估价、确认相关代码 | 与 PRD 的资金确认规则仍有 P0 级偏差 |
| 测试与运维 | 单测、Celery、Redis telemetry | 缺乏关键链路的确定性集成测试、审计和告警 |

### 8.3 关键实现证据

下列位置用于后续实施时快速定位；行号会随代码演进变化，应以符号名为准。

| 观察 | 代码位置 | 对应结论 |
|---|---|---|
| Agent 图和调度分支 | `agent-service/src/agent/graph/app.py` | LangGraph 是可保留的编排基座 |
| 确认令牌构造及自动确认判断 | `agent-service/src/agent/graph/confirm_helpers.py`、`agent-service/src/agent/graph/nodes/confirmer.py` | 当前令牌形式可预测，且高风险动作可被自然语言“执行”类表述自动放行 |
| 令牌校验函数 | `agent-service/src/agent/tools/registry.py` | 已有校验能力没有形成提交前的强制调用链 |
| 提交生成任务 | `agent-service/src/agent/tools/registry.py` | 每次调用生成随机 `Idempotency-Key`，重放不能天然去重 |
| 服务内时钟扫描 | `agent-service/src/agent/main.py` | 与 Beat 形成两套潜在消费者 |
| Celery Beat 扫描任务 | `agent-service/src/agent/workers/celery_app.py` | 对同一 Redis ZSET 的非原子移除存在并发竞争 |
| generation 终态回调 | `generation-service/src/generation/services/task_service.py` | 会调用 `/internal/agent/resume`，但 agent-service 未实现对应入口 |
| 记忆向量 | `agent-service/src/agent/services/memory_service.py` | 词频排序数组丢失词维度，余弦相似度没有可解释的语义空间 |
| 短剧工作流 | `agent-service/src/agent/services/workflow_orchestrator.py` | 当前主要为脚本→关键帧→片段→合成，缺少领域资产和质量门 |
| 短剧 Skill 种子 | `agent-service/src/agent/services/default_skills_seed.py` | 专业知识停留在提示词，而非可校验的结构化输入输出 |
| 遗留集成声明 | `docs/agent-control-plane-p0-spec.md` | 文档与实际回调路由需重新对账，避免“文档完成、代码缺失” |

## 9. 全量问题清单与优先级

### 9.1 P0：会造成越权、资金错误、重复执行或任务卡死的问题

| 编号 | 问题与事实 | 影响 | 必须采取的动作 |
|---|---|---|---|
| AGT-P0-01 | 高风险操作的自动确认取决于用户文本中是否有“执行”等意图词；这与“估价 ≥1 即确认、切换模型、参数变化 ≥30%、批量 >20、覆盖输出必须确认”的产品规则冲突 | 未经明确同意就冻结/扣除点数或覆盖产物 | 移除高风险自动确认；统一走签名、一次性、版本绑定的确认 API |
| AGT-P0-02 | 确认令牌可由会话/动作等可推断组成，且令牌校验没有成为工具提交的不可绕过关口 | 伪造、重放、跨画布确认与审批失效后继续执行 | 令牌签名 + nonce 持久化 + 原子消费；提交工具必须验证 approval 记录 |
| AGT-P0-03 | `generation-service` 已发送终态恢复请求，而 `agent-service` 没有相应路由 | 下游节点不会被可靠解锁，任务停留在等待 | 实现内网鉴权的 resume 入口与幂等事件记录；契约测试两端共同覆盖 |
| AGT-P0-04 | FastAPI 循环和 Celery Beat 都扫描等待集合；ZSET `zrem` 不是跨消费者的原子 claim | 同一终态/时钟任务可能被唤醒两次，导致重复生成或重复写画布 | 只保留一种生产消费者；使用 Lua/Stream 原子认领与数据库去重 |
| AGT-P0-05 | 生成提交使用随机 `Idempotency-Key`，重试与恢复无法识别为同一业务动作 | 重复冻结、重复扣费、重复生成，难以审计 | 从 `action_id + attempt_no` 固定派生幂等键，并在动作/任务两侧存储 |
| AGT-P0-06 | 启动过程用 `ALTER TABLE` 兜底，而不是受版本控制的迁移 | 多实例启动竞争、环境漂移、回滚困难 | 使用 Alembic 迁移；CI 校验干净库升级和回滚策略 |
| AGT-P0-07 | Agent 处理画布写入与任务推进时缺少统一的 action 真相源 | 中断后无法判断“计划了、已调用、已受理、已完成”的精确边界 | 建立不可变 AgentAction/Approval/Notice 审计表和状态机 |

### 9.2 P1：会降低产物质量、可维护性或交付效率的问题

| 编号 | 问题与事实 | 影响 | 改造方向 |
|---|---|---|---|
| AGT-P1-01 | 角色卡主要是文本，角色肖像、服装、三视图等不是强制引用资产 | 镜头间角色脸、服装和气质漂移 | `CharacterLook` + 可版本化 reference asset + 连续性审核 |
| AGT-P1-02 | 分镜没有强制 `ShotSpec` 合同，镜头目的、调度、屏幕方向、对白/音频等字段不完整 | 下游提示词不稳定，无法做局部影响分析 | 将 Scene 编译成结构化镜头，校验后才能提交渲染 |
| AGT-P1-03 | 只覆盖关键帧、视频片段与合成，声音、配音、字幕、时间线和后期不在主图 | 难以交付可播放、可审片的短剧成片 | 把音频、字幕、转场、混音和合成纳入依赖 DAG |
| AGT-P1-04 | 没有多模态质检和重试路由 | 失败产物混入成片，人工筛选成本高 | 引入关键帧、片段、剧集三级 `RenderReview` 与最小重跑 |
| AGT-P1-05 | Skill/角色主要靠自然语言提示词约束 | 输出字段漂移、难以测试和复用 | 角色输入/输出使用 Pydantic schema，adapter 才可调工具 |
| AGT-P1-06 | 记忆相似度算法没有稳定词维度/embedding，且 scope 治理不完整 | 检索结果随机，项目/企业信息可能串扰 | pgvector/合格 embedding + source/scope/TTL/授权治理 |
| AGT-P1-07 | 真实 LLM 调用进入常规单测 | 测试不稳定、CI 耗时和偶发失败 | 测试强制 FakeLLM/录制响应；真实模型仅在标记的集成评测中调用 |

### 9.3 P2：产品竞争力与规模化运营差距

| 编号 | 目前不足 | 拓展方向 |
|---|---|---|
| AGT-P2-01 | 缺乏项目级故事圣经、角色状态和连续性总览 | 建立 SeriesBible、Episode、Scene、CharacterState 的版本链与可视化 |
| AGT-P2-02 | 不能量化 Agent 对成片质量、点数和人工修正的贡献 | 离线评测集、trace、成本归因、A/B 和人工标注闭环 |
| AGT-P2-03 | 任务恢复、异常、审批、预算没有面向用户的统一时间线 | 任务时间线、审批历史、预算预警、局部重跑解释与失败恢复面板 |
| AGT-P2-04 | 供应商/模型差异尚未反映为能力合同 | 模型目录声明输入模态、参考图数量、时长、成本、延迟、内容限制与降级策略 |
| AGT-P2-05 | 未建立受控的工作流模板/Skill 版本治理 | 版本化短剧模板、灰度发布、回滚、素材许可/来源记录与审计 |

## 10. 外部开源对标与可吸收做法

### 10.1 Agent 运行时对标

| 参考项目 | 可观察到的核心做法 | 当前项目差距 | 建议吸收方式 |
|---|---|---|---|
| LangGraph | 持久状态图、可中断的人机协作、checkpoint、可恢复执行 | 已采用图编排，但 action、审批和外部任务终态尚未形成一致的恢复状态机 | 保留 LangGraph；把持久状态限定为计划/等待/审批，外部资产真相仍在服务数据库 |
| OpenAI Agents SDK | Agents、工具、handoff、guardrails、human-in-the-loop、sessions 与 tracing 是同一运行时的一等概念 | 工具白名单已有，但 guardrail、会话、审批与 trace 断裂 | 将确认、参数 schema、预算和内容审核实现为平台 guardrail，不依赖提示词自觉遵守 |
| 通用生产 Agent | 幂等命令、Outbox/事件、审计日志、死信/重放、可观测性 | 当前随机幂等键、双扫描和缺失回调使恰好一次业务效果无法证明 | action 驱动的命令模型 + 去重事件表 + 端到端 trace |

### 10.2 短剧 Agent 对标

| 参考项目 | 值得借鉴的完整链路 | 当前项目差距 | 应用到 VibePaper 的方式 |
|---|---|---|---|
| ViMax | 导演/编剧/制片协作；故事、角色、脚本、分镜结构化；参考图/首帧/镜头连续性；预览与最终组装 | 现有角色/分镜偏文本，参考资产、连续性和预览审核不是强制链路 | 用 `SeriesBible`、`CharacterLook`、`ShotSpec`、`RenderReview` 填补，不复制其实现或 UI |
| Open-AI-Micro-Drama-Generator | 编剧→角色提取→分镜→角色肖像→首帧→视频→拼接；角色静态/动态特征；可恢复的进度输出 | 当前角色肖像不是必经产物，动态角色状态、音频/字幕和可恢复事件仍不完整 | 将角色外观及本集状态作为上游合同；通过任务事件而非仅 SSE 进度恢复 |
| 通用视频工作流 | 将“可预览的中间产物”和“失败的最小重试单元”显式保存 | 视频结果多以终态节点对待，缺乏质量证据与局部修复决策 | 每个 keyframe/clip 产出 review，失败只让其下游 stale |

这些项目不应引入本项目的直接依赖；价值在于验证了“先叙事资产、再视觉锚点、再镜头执行、再质量门”的产品顺序。VibePaper 的差异化应是画布可视化依赖、点数安全和可局部重跑，而不是无约束的 Agent 数量。

## 11. 目标架构与责任边界

```text
Web / Canvas
  │  创建计划、查看审批/时间线、编辑结构化短剧资产
  ▼
agent-service
  ├─ Session / LangGraph：意图、计划、审批中断、等待与恢复决策
  ├─ Action / Approval：不可变业务动作、签名确认、幂等与审计
  ├─ Drama compiler：SeriesBible/Scene/ShotSpec → 白名单工具命令
  └─ Review router：质量结果 → 接受、局部重跑、人工复核
  │                         ▲ generation_terminal（幂等事件）
  │ REST / RocketMQ          │
  ▼                          │
generation-service ──────────┘
  ├─ 模型能力选择、任务状态机、供应商/ComfyUI 适配
  └─ 仅负责生成任务，不决定画布结构或用户审批
  │
  ├── canvas-service：画布版本、节点/连线、资产引用的真相源
  ├── billing-service：冻结、结算、退款与不可变点数流水的真相源
  └── asset-service：素材、预签名、来源/许可与派生关系的真相源
```

边界要求如下：

1. `agent-service` 不直连其他服务数据库、不生成 SQL、不写完整画布 JSON；所有画布变更经 canvas API，并携带预期 `canvas_version`。
2. `agent-service` 可以提出成本计划，但不自行扣点；generation 提交前必须由 billing/generation 既有冻结协议验证资金状态。
3. generation 终态是事实事件，不是让 Agent 重新“思考”的自由提示；恢复只读取受控摘要、最新画布状态和对应 action。
4. 任何自动重试、下游自动推进都受根审批的预算上限、模型/参数摘要和有效期约束；越界立刻回到人工确认。
5. 内容安全、版权/肖像/素材来源和模型可用性应是工具调用前后的 guardrail；拒绝理由使用稳定错误码并可审计。

## 12. 数据状态机、失败恢复与一致性规则

### 12.1 推荐的 AgentAction 状态机

```text
planned → awaiting_approval → approved → dispatching → accepted → waiting_terminal
  │             │                 │              │             │
  └→ cancelled └→ rejected/expired└→ failed      └→ failed     └→ succeeded/failed/cancelled
```

- `dispatching` 前必须检查审批、画布版本、工具版本、预算上限和 idempotency key。
- HTTP 超时后不得猜测失败；查询同一幂等键的任务。存在任务则进入 `accepted` 或 `waiting_terminal`，不存在才在同一 action 下增加 `attempt_no`。
- 收到重复终态事件时，`agent_wakeup_notices` 唯一约束返回已处理，不能再次执行下游工具。
- 画布版本冲突返回 `VERSION_CONFLICT`，保留计划和审批记录，要求客户端获取新版本后重新计算影响面；禁止覆盖。
- 生成失败、取消、过期时，不触发下游生成；只写状态和质量/错误信息。点数冻结、解冻与结算只由 billing/generation 的既有规则处理。

### 12.2 风险与降级矩阵

| 场景 | 首选处理 | 用户可见结果 | 禁止行为 |
|---|---|---|---|
| LLM 超时或不可用 | 保留计划草稿、指数退避或切换已批准模型 | `MODEL_TIMEOUT` / `MODEL_UNAVAILABLE`，可重新规划 | 以空计划继续执行 |
| generation HTTP 超时 | 按固定幂等键查询任务 | “正在确认任务状态” | 立即再次提交 |
| 重复终态事件 | notice 去重并返回成功 ACK | 无重复界面事件 | 再次解锁下游 |
| 画布版本变化 | 拒绝旧审批，重算摘要 | `VERSION_CONFLICT` | 用旧计划覆盖新画布 |
| 成本超过批准上限 | 创建新确认 | 显示增量成本与原因 | 静默继续生成 |
| 连续性/安全质检失败 | 标记失败原因，最小范围重跑或人工复核 | 质量报告和影响节点 | 直接纳入合成 |
| 消息系统故障 | Outbox 重投 + `clock` 兜底查询 | 任务可恢复 | 将 Redis 当唯一账本 |

## 13. 短剧生产链路的详细设计要求

### 13.1 从创意到成片的输入/输出合同

| 阶段 | 输入 | 必须产出 | 通过条件 | 最小重跑单位 |
|---|---|---|---|---|
| 立项 | 题材、受众、时长、平台、预算 | SeriesBible、风格/内容边界、剧集大纲 | 设定不自相矛盾、预算可行 | Episode |
| 编剧 | Bible、Episode 目标、已有 canon | Scene、冲突、转折、对白、钩子 | 场次完整、人物动机可追溯 | Scene |
| 角色资产 | CharacterProfile、风格、许可素材 | CharacterLook、参考图、服装/发型/道具版本 | 每个出镜角色有视觉锚点 | CharacterLook |
| 分镜 | Scene、角色状态、场景、Look | ShotSpec[]、节奏/机位/运动/方向/对白/声效 | 镜头字段齐全、时长合计匹配 | ShotSpec |
| 视觉生成 | ShotSpec、reference assets、首帧策略 | Keyframe、Clip、元数据 | 人物/构图/动作/时长审核通过 | Keyframe 或 Clip |
| 声音与字幕 | 对白、角色声线、时长、语言 | TTS/配音、BGM/SFX、字幕与时码 | 语音、字幕、镜头时长同步 | AudioCue/Subtitle |
| 后期 | Clip、音轨、字幕、转场方案 | Timeline、Preview、FinalRender | 轨道对齐、响度/字幕可读性、总时长正确 | Track/Transition |
| 审片 | 全部资产、质量报告 | Pass、局部修复清单或人工复核 | 连续性、安全、叙事、技术指标达标 | 失败节点 |

### 13.2 连续性约束的最小集合

每个 `ShotSpec` 至少保存并可校验：角色 ID 与 Look 版本、人物在画面左右位置、朝向、服装、发型、手持/关键道具、场景与时间、光线、情绪、上一个镜头的结尾状态、接续方式以及禁变字段。需要支持“本镜可变”和“全场不可变”两种规则范围。

这比在提示词中重复角色描述更可靠：提示词仍是渲染实现细节，结构化约束才可用于 diff、影响分析、质检和局部重跑。

### 13.3 质量评估与重试策略

1. 评估器要同时保留机器分数、阈值、模型版本、证据资产/截图、人工最终裁决，避免分数成为不可解释的黑盒。
2. 同一失败类别最多自动重试两次；每次重试必须记录参数 diff、额外估价和是否落在已批准 cost cap 内。
3. 人脸/服装漂移优先重跑 keyframe 或变更 reference；运动错误重跑 clip；音画不同步重跑音轨/时间线；不要因为单一缺陷重渲整个 Episode。
4. 内容审核、版权/肖像风险或安全策略拒绝时，使用 `CONTENT_BLOCKED` 并提示可修改的输入范围；不得通过提示词绕过。

## 14. 模型、Skill、记忆与工具的治理

### 14.1 模型目录与供应商适配

每个模型版本应声明：支持模态、分辨率/画幅、最大时长、参考图/首帧数量、音频能力、排队/超时策略、单位估价、内容限制、可用区域、降级模型和输出规格。编排器只根据该能力合同生成计划，不能把提示词当作能力探测。

模型切换永远是确认边界；参数改动达到 30%、时长/数量改变、启用高价参考或重试导致累计估价超限，也必须产生新 action hash 和确认。

### 14.2 Skill 生命周期

- Skill 必须有 `skill_id`、版本、作者/审批人、输入输出 schema、适用模型、提示词哈希、成本影响、启用状态与回滚版本。
- Skill 只能补充受控上下文或编译策略，不能新增未登记工具、绕过审批、直接访问服务数据库或隐藏成本。
- 生产 Skill 发布先跑离线样例和安全扫描，再灰度给指定用户/画布；出现质量或费用回归可按版本回滚。

### 14.3 记忆的最小数据策略

| 类型 | 内容例子 | 生命周期 | 检索范围 | 禁止写入 |
|---|---|---|---|---|
| 会话短期 | 当前目标、待确认动作、临时偏好 | 会话或 24 小时 | 当前 session | 密钥、完整工具原文、素材二进制 |
| 项目/canon | 角色设定、剧情事实、风格决策 | 用户删除或项目归档 | canvas/project | 未审核模型猜测 |
| 用户长期 | 用户明确保存的偏好 | 用户可查看/删除 | 当前 user | 企业/其他用户内容 |
| 企业知识 | 经授权的公共规范 | 管理员策略 | 当前 enterprise | 个人私密会话 |

检索使用维度稳定的 embedding/pgvector，并结合 `tenant_id`、`user_id`、`canvas_id`、`scope`、`visibility`、`confidence`、`expires_at` 过滤；召回结果必须附来源，不能把低置信度模型推断写回 canon。

## 15. 实施拆分、依赖与交付物

| 工作包 | 前置依赖 | 主要交付物 | 完成定义 |
|---|---|---|---|
| WP-A：控制面对账 | PRD/Spec 确认 | 回调契约、action/approval 状态机、差异清单 | generation 与 agent 的 OpenAPI/事件字段一致 |
| WP-B：审批与幂等 | WP-A | 签名令牌、审批 API、固定业务幂等、动作审计迁移 | 并发/重放测试证明不重复扣费或提交 |
| WP-C：事件恢复 | WP-B | `/internal/agent/resume`、notice 去重、唯一调度器、死信/clock 兜底 | 重复事件、进程重启、网络超时均能收敛 |
| WP-D：短剧资产 | WP-B | drama schema、资产 API、canvas 节点适配、Look 与 ShotSpec 编辑器 | 可创建并版本化一集的角色/分镜资产 |
| WP-E：短剧执行 | WP-C、WP-D | 编剧/导演/连续性/声音/制片 adapters、含音轨的 DAG | 任一镜头可独立提交、取消、恢复和重跑 |
| WP-F：质量闭环 | WP-E | Review schema、评估任务、路由策略、审片 UI | 缺陷可定位到节点并触发最小重跑 |
| WP-G：评测与运营 | WP-F | 样例集、trace 面板、成本/质量指标、灰度与回滚 | 灰度数据可比较、异常可告警、Skill 可回滚 |

### 15.1 建议的 PR 切分

1. `feature/agent-approval-action-model`：迁移、领域状态机、令牌和单元测试；不改短剧 UI。
2. `feature/agent-generation-resume-idempotency`：事件入口、Outbox/去重、固定幂等键、集成测试。
3. `feature/agent-single-clock-recovery`：关闭重复扫描、原子 claim、重启/超时恢复测试。
4. `feature/drama-domain-schema-canvas-api`：短剧资产 schema、OpenAPI、画布引用与乐观锁。
5. `feature/drama-shot-workflow-references`：Look、ShotSpec、关键帧/视频依赖与局部 stale。
6. `feature/drama-audio-timeline-review`：音频/字幕/时间线、Review 与局部重跑。
7. `feature/agent-eval-observability`：评测集、trace、仪表盘、告警和灰度。

每个 PR 保持单一职责；涉及计费/任务状态机的变更必须附单元测试与跨服务集成测试，且不在事务内发 Feign 或 MQ，使用 Outbox/事务消息。

## 16. 评测、监控与运营指标细化

### 16.1 离线评测集设计

建立至少 30 个已授权的短剧样例，覆盖都市情感、悬疑反转、古风、喜剧等题材，以及多角色、换装、跨场、快速对白、复杂动作、负面内容拦截和供应商故障。每例保存输入、期望 `ShotSpec`、角色/道具连续性标注、预算上限、人工可接受成片标准；不可使用无授权演员肖像、受版权保护的剧本或线上用户原始素材。

评测指标至少包括：计划解析成功率、schema 完整率、角色/服装/屏幕方向连续性、镜头时长偏差、音画同步、一次审片通过率、局部重跑命中率、平均点数、P95 成片耗时、人工修订次数、确认拒绝率和恢复成功率。所有指标按模型、Skill、工作流版本和供应商拆分比较。

### 16.2 在线可观测性与告警

| 信号 | 告警建议 | 排查首点 |
|---|---|---|
| 重复 action/task/ledger | 任一非零即 P0 告警 | action 幂等键、notice 唯一冲突、账本 task_id |
| awaiting terminal 超时 | 超过预期模型 SLA 或 5 分钟未 running | generation 状态、resume 事件、clock claim |
| 终态回调失败/积压 | 5 分钟成功率低于 99% | Outbox、服务鉴权、消费幂等 |
| 审批令牌校验失败激增 | 单用户或全局阈值告警 | 前端版本、过期策略、恶意重放 |
| 质检失败率/重试率突增 | 相对 7 日基线显著上升 | 模型/Skill/供应商版本、参考资产 |
| 点数估价与实际结算偏差 | 超过设定阈值 | 模型目录价格、重试、billing 对账 |

日志脱敏，不记录 API Key、签名 token、完整私密提示词、素材预签名 URL 或原始人脸特征；审计查询依权限返回最小必要字段。

## 17. 上线门槛与后续决策

### 17.1 P0 上线前阻断项

以下任一未满足，禁止开启 Agent 自动提交生成：

1. 高风险路径无法绕过确认卡；approval token 绑定用户、画布版本、摘要和过期并只能消费一次。
2. generation 提交、回调和唤醒在重试/重放/多进程下均实现一次业务效果；重复不会产生第二笔冻结或任务。
3. 两端的 `resume` 事件接口已上线、鉴权、监控和契约测试；仅存在文档声明不视为完成。
4. 一个且只有一个生产时钟消费者；故障恢复有可观察的死信/重投和人工处理入口。
5. billing 的冻结、解冻、结算状态能够按 `task_id` 与 AgentAction 追溯，不由 Agent 绕过计费服务操作。

### 17.2 需要产品/架构共同确认的事项

- 短剧 V1 是否包含真人声线、口型同步、音乐版权库和人工审片；这些决定模型供应商、合规成本与数据保留策略，不应由 Agent 模块自行假定。
- `SeriesBible`、角色 Look、镜头包等作为 canvas 节点参数还是独立资源的最终权威存储位置；建议独立服务实体 + 画布引用，避免画布 JSON 膨胀。
- 自动质检的阈值和“允许自动重试的最大点数”；建议按用户/企业方案配置，默认保守。
- 项目记忆与企业知识的留存/删除、管理员可见范围、导出和审计策略；应由隐私与企业契约确认。
- 可支持的模型清单、分辨率、参考图规则和统一价格目录；需由 generation 与 billing 共同签署能力合同。

## 18. 参考资料

- [LangGraph](https://github.com/langchain-ai/langgraph)：持久状态图、人机协作与可恢复编排参考。
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)：工具、guardrails、handoff、会话和 tracing 的运行时参考。
- [ViMax](https://github.com/HKUDS/ViMax)：故事/角色/脚本/分镜、视觉连续性和视频组装的多智能体研究原型。
- [Open-AI-Micro-Drama-Generator](https://github.com/Anil-matcha/Open-AI-Micro-Drama-Generator)：角色提取、角色肖像、分镜、视频生成与可恢复进度的工程参考。

> 参考项目的许可证、模型依赖、素材权利与生产可用性须在引入任何代码或素材前单独审查；本方案仅吸收架构与产品方法，不授权复制其实现。
