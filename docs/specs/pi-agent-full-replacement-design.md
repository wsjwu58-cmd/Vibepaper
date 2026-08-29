# VibePaper Agent 全量迁移至 Pi 的重构设计

> - 状态：已确定，作为 Agent 重构的唯一实施基线
> - 编制日期：2026-08-28
> - 决策：完整替换 Python agent-service 的 FastAPI、LangGraph、Celery Agent 执行路径；generation-service 仍保持 Python。
> - 依据：PRD §5.2 / §5.3 / §6.5、根目录 AGENTS.md §3 / §5 / §6、技术概要、现有 Agent 数据契约与 [Pi Agent Core v0.84.3](https://github.com/earendil-works/pi/tree/v0.84.3/packages/agent)。
> - 上游锁定：@earendil-works/pi-agent-core@0.84.3，上游 commit 4e58f324fae8ebfa98a3d45181fb248072a2afac，Node.js >=22.19.0，MIT。升级须审查 [release notes](https://github.com/earendil-works/pi/releases/tag/v0.84.3)、依赖锁和所有契约测试。

---

## 1. 决策与边界

agent-service 保留服务名、数据库所有权、网关路由和外部 REST/SSE 合同，但整体重建为 Node.js 22.19+、TypeScript、Fastify、Pi Agent Core 服务。Pi 是进程内库，不再有 Python Agent 控制面、Node sidecar 或 LangGraph 回退路径。

| 范围 | 目标状态 | 不做的事 |
|---|---|---|
| Agent 运行时 | Pi Agent Core 驱动所有通用与短剧会话、工具循环、steer/follow-up、上下文裁剪、流事件 | 不使用 Pi Coding Agent CLI、TUI、Harness 的文件/Shell/浏览器工具。 |
| Agent HTTP 服务 | Node TypeScript agent-service 接收现有 agent API 并输出 SSE | 不保留 FastAPI 作为代理层，不让前端调用 Pi。 |
| 领域能力 | vibepaper-agent Pi 适配包承载通用画布、短剧、Skill、记忆和任务观察的垂直 Prompt/工具适配 | 不把领域合同或资金规则放进 LLM 提示词。 |
| 业务事实 | 新 Agent 服务独占 vibepaper_agent PostgreSQL；Redis、RocketMQ 继续按现有边界使用 | 不采用 Pi 本地/SQLite 会话作为生产业务账本。 |
| Python 代码 | Python Agent 在灰度期仅作为旧版本可回退镜像，M5 后退出生产镜像与部署 | 不迁移或修改 generation-service 的 Python 供应商/任务执行代码。 |

这是一项明确的技术栈替换：技术概要、AGENTS.md、部署和 CI 中 Agent 必须 Python/LangGraph 的约束由本设计取代；PRD 的确认令牌、点数、任务状态机、画布并发和 API 语义不变。

## 2. 目标架构

    React Canvas -> Gateway -> agent-service
                              Node 22 + TypeScript + Fastify
                                       |
                               Pi Agent Core
                                       |
                              Tool Gateway
                    /----------|----------|----------\
            canvas-service  asset-service billing-service generation-service
                                       |
                         PostgreSQL / Redis / RocketMQ

### 2.1 单一服务内的分层

    pi-main/packages/vibepaper-agent-service/
      src/
        server/          Fastify route、鉴权上下文、SSE
        application/     session、run、approval、skill、memory 用例
        domain/          policy、creative contract、状态机、纯领域模型
        pi/              Agent factory、prompt、context、event mapper
        tools/           TypeBox manifest、tool adapter、工具网关客户端
        infrastructure/  PostgreSQL、Redis、RocketMQ、REST、LLM provider
        workers/         终态消费、clock、notification；非 Agent loop
      migrations/
      test/
      Dockerfile

依赖方向固定为 server -> application -> domain，application -> pi/tools/infrastructure，pi -> domain/tools。Pi 层不得导入数据库、MQ、HTTP 客户端；所有副作用必须经 Tool Gateway/应用服务执行。

### 2.2 二次开发方式

pi-main 必须成为锁定上游版本的 Git submodule 或可复现 vendor snapshot，而非无 Git 元数据的复制目录。VibePaper 代码只新增工作区包 packages/vibepaper-agent-service 和需要的内部包，不修改上游 packages/agent、packages/ai 或 packages/coding-agent。

- 使用 Agent、AgentTool、transformContext、beforeToolCall、afterToolCall、shouldStopAfterTurn 和事件订阅 API。
- TypeBox 定义模型可见的工具参数；默认 toolExecution 为 sequential。
- 仅按需使用 Pi 会话/压缩辅助函数；生产持久化始终经过 VibePaper PostgreSQL repository。
- 不注册 Pi 默认系统工具。工具数组必须由服务端 profile manifest 显式构建；空白 profile 即无工具。

## 3. 运行模型

### 3.1 一次 Agent Run

    前端 POST message
      -> Node Agent 鉴权，持久化用户消息和 AgentRun
      -> 读取受限 Canvas 快照、Skill 与记忆
      -> Pi prompt(context, tool manifest)
      -> Pi 文本、工具开始和工具进度事件
      -> Tool Gateway 复核权限、版本、领域约束、风险与成本
      -> 只读/低风险：调用现有 REST 或任务入口并返回 observation
      -> 高风险/计费：写 AgentAction 与 Approval，终止本次 Pi run
      -> 持久化 agent_end，向前端输出兼容 SSE

每个用户输入创建 agent_run，并以 run_id 贯穿日志、SSE、工具、审批和任务。Pi Agent 仅存在于单次 run 内存；每轮由 agent_messages、持久化 tool observation、当前画布摘要和记忆重建。进程重启不会丢失业务事实或重放副作用。

### 3.2 上下文与多领域路由

服务端先确定 profile，而不是让模型选择安全边界：

| Profile | 适用输入 | Prompt/工具组合 |
|---|---|---|
| canvas-general | 画布查询、通用创作、节点编辑 | 通用 Canvas 规则与基础读写工具 |
| vertical-short-drama | 短剧、剧本、角色、分镜、首帧、视频、成片 | 短剧方法论、阶段工具与创作依赖合同 |
| asset-assistant | 素材检索与引用 | 只读素材工具，默认无生成能力 |

路由是确定性、可审计的 profile selection。LLM 只能在当前 profile manifest 内选择工具。上下文按当前输入与待处理事实、Canvas 摘要与选中节点、一跳依赖、当前 Skill/偏好、对话摘要的顺序装配；超预算压缩时永不删除待审批动作、任务终态或 Canvas 版本。

### 3.3 中断、确认与异步任务

Pi 的工具钩子只是本地预检点，不是权限系统。

1. beforeToolCall 校验工具存在、TypeBox 参数与调用配额。
2. Tool Gateway 再校验用户、企业、Canvas 版本、领域依赖、模型能力、风险与成本。
3. 高风险调用写入 AgentAction 和 Approval，返回 approval_required；afterToolCall 设置 terminate=true 并结束当前 Pi run。
4. 用户确认后，应用服务直接执行冻结的 action，使用 agt:{action_id}:{attempt_no}；如需继续解释或推进，创建新的 Pi run 并注入 action observation。
5. generation 任务仍遵循 idle -> queued -> running -> succeeded|failed|cancelled|expired；RocketMQ 消费者写 observation、更新画布、发送会话事件，不能阻塞 Pi run。

确认令牌继续绑定 user_id、canvas_id、canvas_version、action hash 和有效期。画布变化、令牌过期、参数变化 >=30%、模型变更或点数不足均要求重新计划。

## 4. 工具、领域和数据契约

### 4.1 受控工具

| 类别 | 工具 | 行为 |
|---|---|---|
| 只读 | get_canvas_summary、get_selected_nodes、list_models、search_assets、get_task_status、load_skill | 可并行，但结果截断、脱敏并绑定用户/Canvas 范围。 |
| 低风险写 | create_nodes、connect_nodes、layout_nodes、update_node_config | 版本校验后直接执行；单批创建 >20 节点自动升为需确认。 |
| 高风险写 | delete_nodes、change_model、replace_output | 生成 action 和确认卡，未批准不执行。 |
| 计费/长任务 | submit_generation、compose_final、extract_frames、trim_clip、upscale、outpaint | 必须确认；只能走既有 billing/generation 入口，Pi 不得直发 MQ。 |

单一 tool-manifest 是权威契约，包含工具名、profile、TypeBox/JSON Schema、风险、最大批量、费用模型、审批条件、审计字段及 schema 版本。TypeBox 从 manifest 构造 Pi 工具；应用层用同一 manifest 生成或校验请求 schema。禁止两套手工字段定义。

### 4.2 永不由 LLM 决定的规则

- 工具白名单、用户/企业权限、Canvas ID 和服务 URL。
- available_points = balance - frozen_points 及冻结、解冻、结算。
- 幂等键、审批哈希、任务状态机、Canvas 乐观锁。
- 短剧 script、character、shot、keyframe、clip、audio、composite 的依赖关系。
- 脚本不能直接触发生图/生视频，未就绪关键帧不能提交视频，合成只接受合法片段/音频。
- 所有跨服务调用只能为 REST/RocketMQ，且从 Node 应用层发起，绝不直连其他服务数据库。

短剧计划、提示词拆分、工作流推进和素材复用移植到 domain/short-drama 与 profile prompt。先以现有 Python 测试固化黑盒行为，再以 TypeScript 重写；不得逐行翻译 Python。

## 5. 外部合同、持久化与安全

### 5.1 API 与 SSE

保留现有 agent sessions、messages、confirmations、plans、usage、events、Skill 和 memory 的 REST 路径及语义。错误体保持：

    { code, message, details, request_id, retryable }

前端事件继续使用 thinking、assistant_message、confirm_required、task_status 等既有类型；新增可忽略字段 runId、runtime=pi、runtimeVersion、eventSeq、actionId。SSE 由 Fastify 直接输出，事件先追加持久化 outbox，再推送 Redis/SSE；断线恢复从 run_id + event_seq 继续，不重复副作用。

### 5.2 数据迁移

保留 agent_sessions、agent_messages、agent_actions、skills、user_memories 的业务 ID 和历史数据，逐步扩展：

| 实体 | 新字段/表 | 目的 |
|---|---|---|
| agent_runs | id、session_id、profile、runtime/version、status、canvas_version、context_hash、event_seq、error_code、时间戳 | 明确每轮 Pi 运行、恢复和审计边界。 |
| agent_actions | run_id、tool、manifest_version、params_hash、observation_hash | 将 Pi 工具意图关联到审批与幂等执行。 |
| agent_messages | run_id、event_seq、runtime | 消息和流事件去重，不迁移历史内容。 |
| agent_event_outbox | 事件 payload、投递状态、去重键 | 保证持久化后再 SSE/Redis/MQ 投递。 |
| agent_runtime_rollouts | profile、allowlist、比例、fallback、开始/结束时间 | 灰度配置可审计。 |

迁移工具改为 Node migration runner。迁移前验证 PostgreSQL 备份及 schema 兼容；迁移后历史会话仍可读。Python Agent 使用同一数据库的只读兼容窗口结束后才下线，禁止双写。

### 5.3 安全要求

Pi 上游没有内建文件、进程、网络或凭据权限限制，因此必须：

- 不向 Pi 注册 bash、PowerShell、文件、浏览器或任意 HTTP 工具。
- Canvas 文本、Skill、素材元数据均视为不可信 data，不能覆盖 system prompt、manifest 或 policy。
- 工具客户端使用服务器侧身份调用领域服务，用户和 Canvas 范围永不来自模型参数。
- 写操作在提交前持久化 action/幂等键，网络重试只查询动作状态。
- provider key 只从 Node 密钥管理加载，不写入 prompt、日志、Pi session 或客户端。
- 每次操作记录 request_id、run_id、session_id、user_id、canvas_id、canvas_version、action_id、task_id、模型、token、成本、错误码和耗时。

## 6. 迁移步骤与删除标准

| 阶段 | 交付 | 退出标准 |
|---|---|---|
| M0：基础设施 | 固定 Pi 源码、Node 22.19 镜像、Fastify 骨架、Node PostgreSQL/Redis/RocketMQ clients、迁移 runner、SBOM/NOTICE | Python 不再是新 Agent 开发入口。 |
| M1：读路径等价 | Session/message/Skill/memory API、Pi 与只读工具、SSE 事件持久化 | 历史会话可读，通用与短剧只读问答通过契约测试。 |
| M2：低风险写等价 | Canvas 写工具、manifest、通用/短剧 profile、TypeScript 领域合同 | 30 秒 3 镜短剧产生合法节点和连线；无 LangGraph 参与。 |
| M3：资金与异步等价 | Approval、AgentAction、计费生成/合成工具、MQ 终态消费、clock/通知 | 确认、拒绝、过期、版本冲突、冻结超时、回调全链路通过。 |
| M4：全量灰度 | 用户/企业/profile 灰度、影子执行、指标、回退到已部署 Python 镜像 | 连续 7 天达到成功率、P95、成本、审批和错误预算门槛。 |
| M5：完全切换 | 默认 100% Pi；移除 Python 容器、Celery Agent worker、LangGraph 依赖和路由 | 无活跃 Python run/审批；历史会话与任务仍可查询。 |
| M6：代码删除 | 删除 Python agent-service、Alembic/Python Agent 测试和旧镜像 CI | 仅 Node Agent 服务可构建、部署和通过全部回归。 |

灰度回退仅适用于尚未开始的下一轮。已持久化的动作、审批和 generation 任务由同一业务表和领域服务处理，不得在两个运行时之间重放。

## 7. 测试、可观测性与验收

| 层级 | 最小覆盖 |
|---|---|
| Pi 适配单测 | profile 选择、上下文裁剪、工具 schema、顺序/只读并行、事件映射、取消、未知工具拒绝。 |
| 领域单测 | 短剧链条、提示词非原文复制、模型能力、Canvas 版本、审批哈希、幂等和点数边界。 |
| API/存储契约 | 既有 REST/SSE 和错误体兼容，数据库迁移/回滚/历史读取通过。 |
| E2E | 30 秒 3 镜雨夜城门橘猫生成 script/character/shot/keyframe/clip/composite；关键帧未 ready 不提交视频；确认后才冻结/排队；失败全额解冻。 |
| 韧性与安全 | 在流、工具开始、审批等待、终态回调时杀服务；验证无重复写/扣点；覆盖提示词注入、伪造用户/Canvas、重复确认、批量 >20。 |

上线门槛：资金核心分支覆盖率 >=90%；100% 高风险/计费调用生成 AgentAction；0 次 Pi 直连外部服务数据库/MQ；短剧成功率、P95、用户拒绝率不低于旧基线；连续 7 天无 P0 数据或资金事故。

## 8. 现有文档和代码的处置

| 现有项 | 处置 |
|---|---|
| docs/specs/agent-langgraph-design.md | 标为已被本设计替代，仅保留产品契约和历史参考。 |
| docs/specs/pi-short-drama-agent-refactor-design.md | 标为已被本设计替代，其短剧迁移背景并入本文件。 |
| docs/specs/pi-vertical-short-drama-agent-direction.md | 作为本设计的短剧领域子设计，规定状态层、镜头流水线、审校与批量渲染。 |
| docs/技术概要设计方案.md、根 AGENTS.md | 更新为 agent-service = Node/TypeScript/Pi；Python 仅保留 generation-service。 |
| Python agent-service | 迁移期间冻结功能，只修严重生产问题；M6 删除。 |
| pi-main | 成为 Pi 上游锁定来源和 VibePaper Agent 二次开发工作区。 |

## 9. 实施前检查清单

1. 将 pi-main 变为可复现来源并提交精确 gitlink/lockfile。
2. 在部署基础设施中提供 Node 22.19+ 镜像、Agent 专属数据库连接和密钥注入。
3. 由产品、计费和架构共同确认：确认后直接执行冻结 action，后续另起 Pi run。
4. 将现有 Python 行为测试分类为 API、领域、资金和 UI 契约，先移测试再移实现。
5. 每个删除 Python 文件的 PR 必须附 M0-M5 对应验收证据，禁止一次性重写上线。
