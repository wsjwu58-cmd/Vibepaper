# VibePaper 简历亮点（STAR 法则）

> 项目一句话：AI 原生节点化无限画布创作平台——核心场景为竖屏短剧的 AI 工业化生产：文本/图片/视频/音频以节点表达、连线建立引用、Agent 驱动编排、点数计费闭环；微服务架构（网关 + 8 个业务服务，Java / Node / Python 多语言栈）。

**使用说明**
- 每个模块提供两版：「STAR 完整版」用于面试口述与项目详述；「简历精简版」直接作为简历 bullet。
- R 中的【待填】处请替换为真实实测数据；没有的数据直接删除，不要留空壳。
- Agent 模块为基于开源 Pi Agent Core（MIT）的二次开发实现，位于 `pi-main/packages/vibepaper-agent-service`；根目录 `agent-service/`（Python + LangGraph）为被替代的旧路径，按 M0-M6 方案灰度迁移后删除。

---

## 一、Agent 模块（agent-service · 竖屏短剧创作场景）

**技术栈**：Node.js 22 + TypeScript + Fastify + Pi Agent Core 二次开发（@earendil-works/pi-agent-core@0.84.3，锁定版本与 commit）+ PostgreSQL（JSONB）+ Nacos

**业务背景**：产品核心场景是竖屏短剧的 AI 工业化生产——一集 3 分钟、60-90 个镜头，从故事圣经、角色设定、分镜、关键帧到成片合成，全流程在节点画布上由 Agent 驱动完成。

### STAR 完整版

**S（情境）**：AI 短剧生产存在四个工业化痛点：①角色漂移——AI 生成视频中角色形象跨镜头不一致（"换脸感"），观众出戏直接影响完播率与付费转化；②节奏错配——竖屏短剧每镜 2-5 秒，通用视频模型动辄产出 8 秒以上镜头，节奏错配即废片；③工作流越轨——LLM 若从脚本直接触发生视频、或用未确认的草稿关键帧生视频，产出的素材无法进入剪辑；④成本敏感——一集 60-90 镜的批量生成，误操作一次就是整批点数浪费。

**T（任务）**：设计 Agent 驱动的短剧创作管线：把角色一致性、镜头节奏、工作流依赖、成本确认这些业务规则沉淀为代码级领域状态机（而非提示词纪律），并基于开源 Pi Agent Core 二次开发 Agent 运行时承接，核心原则是"业务硬规则与安全规则永不交给 LLM 决定"。

**A（行动）**：
1. 设计短剧领域状态机（DramaState）：将竖屏短剧格式规范固化为 DramaFormatSpec（9:16、单集 180 秒、60-90 镜、每镜 2-5 秒、关键帧先行）；建模角色档案（3-5 条不可变外形锚点如"琥珀色右眼"+ Look 版本 + 声音 ID）、角色参考包（正/侧/背三视图 + 表情表，draft/approved/retired 三态）、镜头规格 ShotSpec（集号/镜号/时长/角色绑定）、关键帧渲染与渲染谱系（draft → ready_for_video → submitted），PostgreSQL JSONB 落地。
2. 攻坚角色一致性：所有人物镜头强制绑定 approved 角色参考包——prepare_keyframe_node 工具自动解析挂载，缺失报 MISSING_CHARACTER_REFERENCE、多候选报 CHARACTER_REFERENCE_AMBIGUOUS 强制人工选择；角色锚点不可原地改写，必须创建新 Look revision，并按 markLineagesStaleForCharacter 幂等地只失效该角色参与的渲染谱系（其他角色的镜头不受影响，最小化重做范围）。
3. 创作管线护栏（workflow rails）：定义 script → character → shot → keyframe → clip → composite 的上游依赖矩阵（ALLOWED_INPUTS），代码级拦截三类越轨——脚本直接触发生图/生视频、未 accepted 关键帧提交视频生成（KEYFRAME_NOT_ACCEPTED）、合成节点接受非法上游；叙事软纪律（前 3 秒必须有钩子、集尾必须有断点、视频/TTS/字幕必须引用 ShotSpec）放系统提示词，与硬约束分层治理。
4. 基于开源 Pi Agent Core（MIT，锁定 0.84.3 版本与源码 commit）二次开发 Agent 运行时（Node 22 + TypeScript + Fastify + Nacos，monorepo 独立包）：Agent Factory 组装短剧系统提示词与白名单工具，`beforeToolCall` 拦截白名单外调用并 terminate，工具固定 sequential 执行避免并发写画布；Pi 原生事件流映射为领域事件（thinking/assistant_message/tool/usage）经 Fastify SSE 流式输出。
5. 双层工具安全 + 成本人审：Pi 工具钩子仅作本地预检（TypeBox 参数校验/调用配额），自研 Tool Gateway 在服务端二次校验用户/企业/画布版本/领域依赖/风险成本——业务上对应"批量生成一集关键帧/视频前，按预估点数先出确认卡"；确认令牌 HMAC-SHA256 签名 + 常量时间比对 + 300s TTL + 一次性消费状态机，确认后按 `agt:{action_id}:{attempt_no}` 幂等键执行冻结动作。
6. Skill 渐进式披露：沉淀 16 个短剧方法论 Skill（故事圣经、竖屏分集、长篇改编、分镜板、角色一致性、连贯性审查、对白润色、六格漫画、视听导演、制作排期等），系统提示词仅注入索引行，`load_skill` 工具按需加载全文，`skill://session/{id}` URI 防同一会话重复加载。
7. 画布协同：节点以 creativeType（script/character/shot/keyframe/clip/audio/composite）双维度投影创作管线，画布 buildSummary 为 Agent 生成 pipelineHint 阶段摘要；上游节点变更沿依赖连线 markDownstreamStale 传播失效标记。
8. 主导旧 Python/LangGraph Agent → Node/Pi 的 M0-M6 六阶段灰度迁移方案（基础设施替换 → 读路径等价 → 写路径等价 → 资金链路等价 → 影子执行灰度 → 切流删除），每阶段以契约测试等价性为退出标准，含成功率/P95/成本指标门槛与回退预案。

**R（结果）**：领域状态机以 6 类实体、8 张表（6 个外键 + 镜号唯一约束）、3 组状态机共 11 个状态（参考包 draft/approved/retired、关键帧 draft/accepted/rejected/stale、渲染谱系 draft/ready_for_video/submitted/stale）、22 个代码级校验点、12 类领域错误码将业务硬规则 100% 代码化：角色一致性由"参考包 + 不可变锚点 + 谱系精准失效"机制保证，多镜头人物形象不再漂移；工作流越轨在任务提交前被依赖矩阵拦截，杜绝无法剪辑的废片；一集 60-90 镜（120-180 次渲染）的批量生成点数风险前置到确认卡环节；vitest 覆盖 7 个短剧状态机场景（锚点数量校验、参考包唯一性/缺失/歧义、关键帧就绪门禁、谱系精准失效）+ API 契约 + Skill 披露三类核心路径。【待填：一集 60-90 镜端到端产出耗时、关键帧一次通过率、角色一致性人工抽检通过率】

### 简历精简版

- 面向竖屏短剧工业化生产设计 Agent 领域状态机（6 类领域实体 / 8 张表 / 3 组状态机共 11 个状态 / 22 个代码级校验点）：固化格式规范（9:16、单集 180s/60-90 镜、每镜 2-5s、关键帧先行）；人物镜头 100% 强制挂载版本化三视图参考包（3-5 条不可变外形锚点 + ≥4 张参考图），12 类领域错误码在任务提交前确定性拦截角色缺失/参考歧义/依赖越轨；一集 120-180 次渲染（60-90 镜 × 关键帧+视频）全链路由渲染谱系状态机管控，角色锚点变更最小化失效（仅该角色参与镜头重做），PostgreSQL JSONB 落地，7 个状态机场景测试全绿。
- 攻坚 AI 视频角色漂移痛点：人物镜头强制挂载 approved 角色参考包（缺失即拒绝、多候选强制人工选择），角色锚点修改走新 Look revision 并幂等失效仅该角色参与的渲染谱系——多镜头形象一致性由代码保证而非提示词。
- 设计创作管线护栏：script→character→shot→keyframe→clip→composite 上游依赖矩阵，代码级拦截"脚本直生视频""未就绪关键帧提交视频"等越轨操作；叙事纪律（前 3 秒钩子、集尾断点）分层进系统提示词，硬软约束分离。
- 基于开源 Pi Agent Core 二次开发 Agent 运行时（Node 22 + TypeScript + Fastify + Nacos）：白名单工具 + beforeToolCall 拦截，Pi 钩子本地预检 + 自研 Tool Gateway 服务端权限/成本双层校验，HMAC 确认令牌人审（批量生成前确认预估点数），16 个短剧方法论 Skill 渐进披露控制上下文占用。
- 主导 Python/LangGraph → Node/Pi 六阶段灰度重构（契约等价测试 + 影子执行 + 指标门槛 + 可回退）。

---

## 一·补、Agent 编排架构（Pi Agent Core 二次开发 · 运行时视角）

> 与上文「Agent 模块」互补：上文讲业务领域（短剧状态机），本节讲编排运行时（Pi 二次开发的架构决策与工程实现）。面试时按追问深度选用。

**技术栈**：Node.js 22.19+ + TypeScript + Fastify + @earendil-works/pi-agent-core@0.84.3（锁定上游 commit）+ PostgreSQL + Nacos；约 2.5k 行 TS 适配层（`pi-main/packages/vibepaper-agent-service`）

### STAR 完整版

**S（情境）**：原 Agent 编排为 Python + LangGraph 实现——单张 23 节点状态大图（意图分流 → Skill 选择/加载 → 计划编译 → 契约校验 → 风险分级 → 确认门 → 执行器/并行 worker → 反思重规划 → 时钟轮询异步任务 → 记忆更新），叠加 800+ 行工作流编排器。核心痛点：领域编译、LLM JSON 解析、ReAct 循环、事件转换与恢复逻辑相互交织，模型调用失败需多处兜底（规则回退、JSON 修复、降级注记），工具循环、上下文压缩、中途改指令（steering）难以稳定扩展——图框架把"编排控制流"和"领域规则"焊死在一起。

**T（任务）**：将 Agent 运行时从 Python/LangGraph 全量迁移至 Pi Agent Core 二次开发（Node 22 + TypeScript + Fastify），硬约束：对外 REST/SSE 合同零破坏（前端无感）、审批/计费/幂等/画布乐观锁等资金安全契约不变、全程可灰度可回退。

**A（行动）**：
1. **架构选型与责任切割**：只采用 pi-agent-core + pi-ai 两个进程内库（MIT），明确拒绝 Pi Coding Agent CLI/TUI/Harness——其自带 bash/文件/浏览器工具权限面过大；确立"Pi 负责模型-工具-观察-再决策循环，自研控制面负责领域合同、权限、审批、计费、持久化"的边界，副作用只能经 Tool Gateway 触发。
2. **供应链锁定**：上游锁定 v0.84.3 + 精确 commit，二次开发只新增 monorepo 工作区包 vibepaper-agent-service，不修改上游 packages/agent——升级走 release notes 评审 + 契约测试，杜绝供应链漂移。
3. **Agent Factory + 白名单硬拦截**：createDramaAgent 组装系统提示词与工具数组，`beforeToolCall` 以 Set 白名单校验，白名单外调用直接 `block + terminate`（"工具不在短剧 Agent 白名单中"）；`toolExecution: "sequential"` 固定串行，杜绝并发写画布/冻结点数的竞态——空工具集即零工具，模型永远看不到未声明的能力。
4. **双层参数校验防 schema 漂移**：Pi 层 TypeBox（`additionalProperties: false`）约束模型只能产出合法参数形状；服务端领域层做权威业务校验；单一 tool-manifest 作为权威契约同时生成两侧 schema，禁止两套手工定义漂移。
5. **确认-执行分离的 run 生命周期**：高风险工具调用写 AgentAction + Approval（HMAC-SHA256 签名令牌 + timingSafeEqual 常量时间比对 + TTL + consumed_at 一次性消费），`afterToolCall` 置 terminate 结束当前 run 并下发 confirm_required；用户确认后应用层按 `agt:{action_id}:{attempt_no}` 幂等键直接执行冻结动作——不恢复不可信的内存循环、不要求模型重新生成，需要继续解释时新起 run 注入执行观察。
6. **无状态运行时重建**：每轮 run 从 PostgreSQL 重建 Pi Agent（历史裁剪至最近 24 条），进程崩溃/扩容/重试零依赖 Node 内存，业务事实源唯一在数据库；自定义 provider 适配（agnesModel 接 openai-completions 协议）+ streamSimple 流式驱动。
7. **事件桥接零改造前端**：`agent.subscribe` 订阅 Pi 原生事件流（message_update / message_end / tool_execution_end），捕获映射为既有 SSE 事件（thinking / assistant_message / tool / usage），前端与历史记录零迁移。
8. **Skill 渐进披露**：系统提示词仅注入索引行，`load_skill` 工具按需加载全文，会话级 Set 去重 + `skill://session/{id}` URI 引用，长方法论不占常驻上下文。
9. **受控副作用网关**：自研 ToolGateway 统一出口调用 canvas/billing——注入网关身份头（X-User-Id / X-Request-Id）、计费提交强制 Idempotency-Key、AbortSignal 超时熔断（10s/15s）、稳定错误码（CANVAS_UNAVAILABLE / GENERATION_UNAVAILABLE），Pi 不持有任何数据库凭据。
10. **M0-M6 六阶段灰度迁移**：基础设施 → 读路径等价 → 低风险写等价 → 资金与异步等价 → 全量灰度（影子执行 + 成功率/P95/成本指标门槛）→ 切流删除；每阶段以契约测试等价性为退出标准，回退仅适用于未开始的下一轮，已持久化动作不在两个运行时间重放。

**R（结果）**：约 2.5k 行 TS 适配层承接原 23 节点 LangGraph 大图 + 800 行编排器的全部职责，编排控制流与领域规则彻底解耦；运行时崩溃/重启零副作用重放（幂等键 + 数据库唯一事实源）；100% 高风险调用经确认门（设计验收门槛：0 次未确认计费提交）；前端 REST/SSE 合同零破坏实现灰度切换；vitest 覆盖状态机、API 契约、Skill 披露三类核心路径。【待填：迁移后短剧主路径成功率对比、P95 延迟对比、token 成本变化】

### 简历精简版

- 主导 Agent 运行时从 Python/LangGraph（23 节点状态大图）全量迁移至 Pi Agent Core 二次开发：确立"Pi 只负责模型-工具循环、自研控制面负责领域/权限/计费/持久化"的责任边界，上游锁定版本与 commit、仅以独立工作区包扩展不修改上游源码，约 2.5k 行 TS 承接全部编排职责。
- 设计双层工具安全体系：`beforeToolCall` Set 白名单硬拦截（白名单外 block+terminate）+ TypeBox 参数形状约束，服务端 Tool Gateway 二次鉴权（网关身份头 / Idempotency-Key / 超时熔断），工具固定串行执行杜绝并发写竞态——空 manifest 即零工具，模型能力面完全由服务端定义。
- 实现确认-执行分离的高风险编排：高风险调用经 HMAC-SHA256 确认令牌（常量时间比对 + TTL + 一次性消费）人审后，应用层按幂等键直接执行冻结动作而非恢复模型循环，杜绝"等待确认期间持有挂起执行流"与重复扣费。
- 无状态运行时设计：每轮 run 从 PostgreSQL 重建 Agent 上下文，进程崩溃/扩容/重试零副作用重放；Pi 原生事件流桥接为既有 SSE 协议，前端零改造完成运行时灰度切换。
- 制定 M0-M6 六阶段灰度迁移方案（契约测试等价性退出标准 + 影子执行 + 指标门槛 + 回退预案），高风险技术栈替换全程可控。

---

## 二、计费模块（billing-service）

**技术栈**：Java 21 + Spring Boot 3 + MyBatis-Plus + RocketMQ + PostgreSQL

### STAR 完整版

**S（情境）**：AI 生成任务是"先冻结、后结算"的异步资金链路：提交 → 排队 → 执行 → 回调结算，中途存在失败、超时、取消、消息重复投递等多种情况。高并发提交与 MQ 重试背景下，任何一条路径处理不当都会造成重复扣费或冻结额度泄漏——都是资损事故。

**T（任务）**：负责点数账户与冻结/结算/解冻全生命周期设计，要求并发安全、全链路幂等、每一笔变动可审计。

**A（行动）**：
1. 设计"冻结-结算-解冻"两阶段计费模型：`available = balance − frozen`；任务提交时校验可用额度并冻结预估点数（个人不足时支持企业共享池兜底），成功按实际用量结算，失败/取消/超时全额解冻，余额不足进入 settlement_error 兜底态而非静默失败。
2. 账户资金操作统一 `SELECT ... FOR UPDATE` 行锁 + `@Transactional` 串行化，杜绝并发双花；任务创建接口强制 Idempotency-Key。
3. 5 分钟超时自动解冻：`@Scheduled` 30s 扫描过期冻结单，`FOR UPDATE SKIP LOCKED` 分批（每批 200 条）处理，多实例部署下并行扫描不重复消费、不互相阻塞。
4. 引入 Transactional Outbox 模式替代分布式事务：业务事务内写 outbox_events，后台任务每 3s 扫描投递 RocketMQ（失败自动重试），保证本地事务与消息发送的原子性；MQ 不可用时降级为直调内部接口，保证可用性。
5. point_ledgers 只追加流水设计（freeze / settle / unfreeze_* / recharge / allocate / recycle 共 9 类账变），每条记录变动后余额快照，任意时点账户状态可回放审计；冻结单状态机 pending → settled / expired / cancelled / refunded / settlement_error 全闭环。
6. 消费 generation-task-completed / failed 等 MQ 事件驱动结算与解冻，与生成服务彻底解耦。

**R（结果）**：重复提交、消息重投、超时、失败等异常路径全部幂等收敛，设计上保障零重复扣费、零冻结泄漏；全部点数变动有流水可查、可回放对账。【待填：核心分支单测覆盖率、压测 TPS、对账差异数】

### 简历精简版

- 设计"冻结-结算-解冻"两阶段点数计费模型（available = balance − frozen）：提交时行锁校验并冻结预估点数、成功按实际用量结算、失败/取消/超时全额解冻、余额不足进入兜底态，保障异步生成链路零资损。
- 采用 Transactional Outbox + RocketMQ 实现跨服务事件驱动结算（业务事务内写 outbox、后台扫描投递、失败自动重试、MQ 不可用降级直调），替代分布式事务保证最终一致性。
- 资金安全三件套：账户行锁串行化、任务创建强制幂等键、只追加流水账（9 类账变 + 余额快照）支持任意时点审计回放；超时解冻用 SKIP LOCKED 批量扫描，多实例安全。

---

## 三、画布模块（canvas-service + 前端无限画布）

**技术栈**：后端 Java + Spring Boot + MyBatis-Plus；前端 React + TypeScript + @xyflow/react + Zustand + TanStack Query

### STAR 完整版

**S（情境）**：节点化无限画布是产品核心交互载体：节点/连线数量大、保存高频（防抖 500ms 级），用户多端操作与 AI Agent 写画布并存，并发覆盖会直接丢失创作内容；导入导出还需要跨版本兼容，且保存不能误清已有生成产物。

**T（任务）**：负责画布领域模型、并发保存协议与前端渲染性能优化。

**A（行动）**：
1. 设计画布领域模型：canvases / nodes / edges / groups / stacks / revisions 六张表，节点按 nodeType（文本/图片/视频/音频/合成/导演台）× creativeType（脚本/角色/分镜/关键帧等）双维度分类，params 以 JSONB 存储；连线经 EdgeRules 类型兼容矩阵校验合法性。
2. 实现乐观锁并发控制：保存时 version 全量比对（MyBatis-Plus @Version），冲突返回 VERSION_CONFLICT 拒绝覆盖，前端提示"画布已在其他会话更新"并拉取最新版本，杜绝静默覆盖丢数据。
3. 设计高频保存协议：前端 500ms 防抖 + beforeunload 强制 flush + 首次 hydrate 跳过；后端全量重放保存时通过 applyPreservedGeneration / mergeParamsKeepMedia 产物保护策略，避免前端 payload 缺失导致已生成的 output、媒体 URL、执行状态被误清空。
4. 导入导出带 schema_version 主版本兼容校验：不兼容直接拒绝；导入时 ID 重映射、连线合法性按规则引擎重算、缺失引用跳过，保证跨版本画布克隆可用；每次保存写入 canvas_revisions 版本快照支持历史回溯。
5. 前端性能优化：核心节点视图 memo 化渲染、编组边界/堆叠徽章 useMemo 预计算、任务状态条件轮询（仅 queued/running 时 2s 间隔，react-query 自动启停）、音视频 preload=metadata 按需加载。

**R（结果）**：多端 + Agent 并发写场景下零覆盖丢失；已生成产物在全量保存协议下不丢失。【待填：千节点画布 FPS、保存接口 P95 延迟】

### 简历精简版

- 设计画布领域模型（画布/节点/连线/编组/堆叠 + 版本快照），节点双维度分类 + JSONB 参数存储，连线经类型兼容矩阵校验；导入导出带 schema_version 兼容校验 + ID 重映射 + 合法性重算，支持跨版本克隆。
- 实现乐观锁并发保存协议（version 比对 + 冲突拒绝 + 前端引导刷新），高频防抖保存（500ms + 关页 flush）下以产物保护策略避免已生成内容被误清空，解决多端与 Agent 并发写覆盖问题。
- 基于 @xyflow/react 优化无限画布性能：节点 memo 化、派生数据预计算、任务条件轮询按需启停、媒体懒加载，保障大规模节点流畅交互。

---

## 四、面试追问准备点

**Agent 模块（业务向为主）**
- 角色一致性为什么靠参考包而不是把外貌写进提示词？——提示词无法可靠约束生成模型的人物身份保持；参考包提供视觉锚点（三视图 + 表情表），approved 状态保证全镜头统一到同一版本，生成模型以图生图/图生视频方式锚定形象。
- 为什么角色锚点不可变、修改必须走新 Look revision？——已生成素材锚定在旧锚点上，原地改写会让历史素材"来历不明"；新版本 + 谱系失效让重做范围显式化、可追溯。
- 多个 approved 参考包为什么强制人工选择而不自动选第一个？——IP 形象选错的错误会沿整集 60-90 镜传播，代价远高于一次人工决策（CHARACTER_REFERENCE_AMBIGUOUS）。
- markLineagesStaleForCharacter 为什么只标该角色的谱系？——最小失效范围：全量失效等于整集重做，按角色精准失效让未受影响镜头保留。
- 前 3 秒钩子、集尾断点为什么放系统提示词而不放代码校验？——分层治理：硬规则（依赖矩阵、状态门禁、权限、成本）进代码确定性拦截；软知识（叙事判断）交给 LLM 发挥，两者的失效模式不同。
- 为什么 keyframe-first（先关键帧后视频）？——关键帧是图片生成，成本低、秒级迭代，先确认构图与角色形象；accepted 后再生视频，把最贵的视频生成放在确定性最高的环节，降低整集试错成本。
- 每镜 2-5 秒的约束在哪几层生效？——DramaFormatSpec 固化在领域模型（min/maxShotDurationSeconds）、ShotSpec 创建校验、系统提示词纪律，还有工作流 rails 的时长钳制兜底（如 25 秒请求被钳到上限）。
- 为什么选 Pi Agent Core 而不是 LangGraph / 自研？——Pi 是进程内库：Agent Loop、事件流、工具钩子、上下文管理均可编程接管，MIT 许可支持可控二次开发，TypeScript 与前端同构；LangGraph 需要重建图编排控制面，自研重复造轮子。
- beforeToolCall 和 Tool Gateway 为什么分两层？——Pi 钩子只是本地预检点（参数/配额快速失败），真正的权限校验（用户、企业、画布版本、成本）必须在服务端 Tool Gateway 执行，不信任 LLM 输出。
- 高风险确认后为什么新建 run 而非恢复原 run？——terminate 结束当前 run，避免等待用户确认（可能数分钟）期间持有挂起执行流；确认后应用层按幂等键执行冻结 action，再新建 run 注入执行观察继续对话。

**Agent 编排架构（Pi 二次开发 · 技术向）**
- 为什么 2.5k 行 TS 能替代 23 节点 LangGraph 图？——LangGraph 图中大部分节点在做 Pi 已内建的事：工具循环、流事件、参数校验、上下文管理；自研代码只保留 Pi 做不了的部分（领域合同、审批、计费、持久化），职责切割后代码量天然收敛。
- 为什么固定 sequential 不让只读工具并行？——写画布/冻结点数的工具存在先后依赖，Pi 默认并行执行会引入竞态；宁可牺牲只读工具的理论并行度，换取副作用确定性（设计上只读且不依赖同批结果的工具才允许并行）。
- beforeToolCall 拦截为什么不够、还要 Tool Gateway？——Pi 钩子只是本地预检点：参数形状、白名单快速失败；用户/企业权限、画布版本、成本风险是业务事实，必须服务端权威校验，LLM 环境内的任何"通过"都不等于授权。
- 每轮重建 Agent 不浪费吗（vs 常驻 Agent）？——换来的是崩溃/扩容/重试语义极简：业务事实源唯一在 PostgreSQL，Node 进程随时可杀可换；模型侧损失只是一次上下文重建，且历史裁剪（24 条）本就是上下文管理策略的一部分。
- 事件桥接怎么保证前端零改造？——Pi 原生事件（message_update / tool_execution_end 等）在 subscribe 回调中映射为既有 SSE 事件名，新增字段（runId / runtime / eventSeq）设计为旧前端可忽略；持久化先于推送，断线从 run_id + event_seq 续读。
- 上游升级 Pi 版本怎么控风险？——版本与 commit 锁定在 vendor 快照，升级必须过 release notes 评审 + 上游核心包测试 + 本项目契约测试三方验证；二次开发只在工作区包内扩展，diff 可审计。

**计费模块**
- 为什么用 Outbox 而不是 RocketMQ 事务消息 / Seata？——Outbox 实现简单、无侵入，与"事务内禁止发 MQ"的工程约束一致；Seata 仅作备选。
- SKIP LOCKED 的作用？——多实例并行扫描同一批过期冻结单时跳过已锁行，不重复消费、不互相阻塞。
- settlement_error 为什么不自动重试？——资金异常宁可停机人工介入，避免自动补偿引入二次资损。

**画布模块**
- 乐观锁冲突的 UX？——拒绝覆盖 + 提示刷新 + 自动拉取最新版本，用户自行决定重放操作。
- 全量保存 vs 增量 patch 的取舍？——V1.0 用全量重放 + 乐观锁保证正确性优先，代价是流量；产物保护弥补前端 payload 缺失问题。
- 为什么需要产物保护？——前端防抖保存的 payload 可能缺失 output 字段，直接落库会清掉已生成内容。
