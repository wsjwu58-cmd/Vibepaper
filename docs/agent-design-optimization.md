# VibePaper Agent 功能设计文档与优化方案

> 创作 Agent 全链路设计：从领域模型到导演方法论

> 版本：v1.2 · 日期：2026-08-06 · 依据：PRD V2.1 / 技术概要 / V1.0 Spec / 当前代码实现 / 创作Agent五层架构 / Canvas Norm 编排模型 / 多 Agent 协同架构

---

## 1. 背景与目标

VibePaper 的 Agent 不是通用 Chatbot，而是画布上下文驱动的创作参谋与执行助手。当前代码已实现会话管理、工具白名单、风险确认、计费链路的完整骨架，但 Paper Agent 的"梳理画布、提炼文案、延展方向"三项核心能力尚未落地。

### 1.1 Paper Agent 产品定位

根据产品截图，Paper Agent 强调"理解整张画布的脉络，把零散灵感推进为清晰、可执行的创作方案"。这要求 Agent 具备三类输出：

#### 梳理画布信息

提炼核心创意，指出明确的下一步动作。

#### 品牌文案生成

基于画布素材写出鲜明、有记忆点的品牌文案。

#### 内容延展

提出三个差异化、可落地的创作方向。

### 1.2 文档目标

本文档旨在：

  * 明确当前实现与 PRD / Spec 的差距；
  * 给出 Paper Agent 的专项功能设计；
  * 提出可落地的优化方案与分阶段实施计划；
  * 确保所有设计复用现有计费状态机与确认令牌机制，不引入新的资金路径。


## 2. 当前问题分析

### 2.1 已实现能力

当前 `agent-service` 已具备以下基础能力：

  * **服务边界清晰** ：Agent 不直连数据库，所有写操作通过 REST 调用 `canvas-service`、`asset-service`，通过计费接口调用 `billing-service`。
  * **数据模型完整** ：已建 `agent_sessions`、`agent_messages`、`agent_actions`、`skills`、`user_memories`、`session_fragments` 六张表，覆盖 P0~P2。
  * **工具白名单** ：12 个工具按 read/low/high 分级，与 Spec §7.2 对齐。
  * **确认令牌** ：绑定 `user_id + canvas_id + canvas_version + action_summary`，Redis 存储 5 分钟。
  * **计费链路** ：`submit_generation` 走 `billing-service` 冻结，`generation-service` 执行后回调结算/解冻。


### 2.2 主要问题

问题 | 影响 | 优先级
---|---|---
规则引擎只能按关键词建节点/提交生成，无法识别"梳理/文案/延展"意图 | Paper Agent 三项能力无法落地 | P0
LLM 规划器上下文是整个 canvas JSON，大画布 Token 爆炸 | 成本高、响应慢、易超模型上下文 | P0
工具执行结果未充分回写到对话上下文 | Agent 无法基于执行结果继续迭代 | P0
前端 Agent 面板能力未在已读源码中确认完整实现 | 用户无法看到步骤流、确认弹窗、影响范围 | P0
Agent 动作缺少独立埋点 | 无法度量 Agent 执行成功率 | P1
LangGraph 尚未接入，规划器是手写 if/else，与 PRD §3.2 / 技术概要技术选型直接冲突 | 无法支持图编排、状态持久化、循环反思、并行分支等 Agent 核心能力，阻塞 Paper Agent 落地 | P0

### 2.3 与 PRD / Spec 的对照

PRD / Spec 要求 | 当前状态
---|---
Agent 读取画布上下文 + 选中节点（§6.5.1） | 已实现，但传全量 canvas JSON
多轮对话与创作建议（§6.5.1） | 基础实现，建议质量依赖规则/LLM
重要操作确认规则量化（§5.2.1） | 已实现 create/update/delete/submit 阈值
偏好与用量（§6.5.2） | 表结构已就绪，前端展示待确认
Skill 系统（§6.5.4） | 后端 CRUD 已就绪，未与 Paper Agent 能力绑定
记忆系统（§6.5.5） | 表结构已就绪（两层），需重构为三层 + update_memory 异步机制（详见 §3.11）

## 3. Agent 功能设计

### 3.1 总体架构

Agent 功能分布在多个微服务中，遵循"业务 Java + AI Python"的分层原则。Agent 只通过 REST 读取画布/素材，通过计费接口触发资金操作，通过 MQ/REST 触发生成任务。

*[SVG 图示]* 图 1：Agent 服务调用关系

### 3.2 核心能力分层

能力层 | 职责 | 当前实现
---|---|---
会话管理层 | Session / Message / Action 持久化、用量统计 | 已完成
上下文层 | 读取画布、选中节点、素材、Skill、记忆 | 基础实现，需精简
规划层 | 意图解析、工具调用序列生成 | 规则引擎 + 可选 LLM，**强制重构为 LangGraph StateGraph**
工具执行层 | 白名单工具调用、风险分级、确认令牌 | 已完成
计费触发层 | submit_generation 走 billing-service 冻结 | 已完成
前端展示层 | Agent 面板、步骤流、确认弹窗 | 待确认/完善

### 3.3 上下文构建策略

为控制 Token 消耗并提升理解准确性，上下文按优先级拼接。建议由 `canvas-service` 提供预计算摘要接口，避免 Agent 直接处理全量 DSL。

  1. **用户当前指令**
  2. **当前选中节点** （若有）
  3. **相关上下游节点** ：沿 Edge 向上/下递归 1–2 层
  4. **画布摘要** ：节点类型统计、主题关键词、有效/无效连线
  5. **用户偏好** ：默认模型、分辨率、语言风格
  6. **当前 Skill 指令**
  7. **最近 N 轮对话** （N=10，可配置）


### 3.4 工具白名单与风险分级

工具分级沿用 PRD §5.2.1 / Spec §7.2。工具按**读写分离** 原则分为两类：`read` 类工具只查不改（查画布、查模型、查素材），`edit` 类工具改画布结构（建节点、连线、改参数、删节点），`exec` 类工具触发实际执行（提交生成、抽帧、超分）。读写分离确保 Agent 的"想"和"做"可独立审计。

风险等级 | 工具 | 确认条件
---|---|---
read | get_canvas_summary、get_selected_nodes、list_models、search_assets | 无需确认
low | create_nodes、connect_nodes、layout_nodes、update_node_config | 批量创建 >20、参数变化 ≥30%、切换模型时升级 high
high | delete_nodes、change_model、replace_output、submit_generation | 必须确认

**读写分离原则：**`read` 类工具（get_*、list_*、search_*）只查询不修改，Agent 可自由调用无需确认。`edit` 类工具修改画布结构，低风险直接执行、高风险走确认。`exec` 类工具（submit_generation）触发异步生成任务，必须走计费冻结 + 确认流程。Agent 在规划时优先用 `read` 补全信息，再用 `edit` 落地结构，最后用 `exec` 触发执行——这个顺序对应 LangGraph 图中 context_builder → planner → executor 的节点流。 

**P1+ 创作专用工具扩展点** （V1.0 不实现，但工具注册表预留扩展位）：抽帧（extract_frames）、片段剪辑（trim_clip）、素材超分（upscale）、3D场景捕获（capture_3d_scene）、拼接成片（compose_final）。这些工具遵循同样的读写分离 + 风险分级原则，注册到 `TOOLS` 字典即可被 LangGraph executor 节点调用。

#### 协同工具（§3.13 五角色配套）

多 Agent 协同架构需要额外的工具支持。这些工具不直接操作画布，而是触发后台协同角色。它们属于 `read` 风险等级（不修改画布、不扣费），但执行语义不同于普通查询工具——它们是"派发任务"而非"返回数据"：

工具 | 风险等级 | 所属角色 | 行为 | 返回值
---|---|---|---|---
`update_memory` | read | 记忆子 Agent | 触发异步记忆更新，推入 Redis 队列。主 Agent 不等待结果 | `{"queued": true}`
`clock` | read | 定时唤醒 | 注册延时任务，到点后带着 note 重新触发 Agent 查产物状态 | `{"scheduled": true, "wakeup_at": "..."}`
`load_skill` | read | 技能库 | 按需读取复合操作的 Skill 规则，注入当前轮 LLM prompt。用完即丢 | `{"instructions": "..."}`
`check_task_status` | read | 定时唤醒回调 | 查询异步生成任务状态，更新节点 output + status。由 clock 唤醒触发，不由主 Agent 直接调用 | `{"task_id": "...", "status": "succeeded", "output": "..."}`

**协同工具设计原则：** 这些工具的返回值是"已派发"确认（ack），不是实际工作结果。`update_memory` 返回 `queued: true` 表示记忆更新任务已入队，但去重 / 合并尚未完成。`clock` 返回 `scheduled: true` 表示唤醒已注册，但还没到点。主 Agent 拿到 ack 后继续回复用户，不等实际工作完成。 

### 3.5 确认令牌机制

高风险操作必须生成确认令牌，绑定 `user_id + canvas_id + canvas_version + action_summary`，Redis 存储 5 分钟。若确认期间画布版本变化，令牌失效。

**设计要点：** 前端确认弹窗必须展示影响范围（涉及节点数、estimated_cost、操作摘要），用户确认后才执行工具调用或发送计费消息。该机制当前已在 `tools/registry.py` 中实现，无需改动数据结构。 

### 3.6 LangGraph 编排框架（强制）

**强制约束：** PRD §3.2 和技术概要已指定 LangGraph 作为 agent-service 的编排框架。本文档将其从 `pyproject.toml` 中的"可选依赖"提升为**强制核心依赖** ——`langgraph` 必须移入 `dependencies` 主列表，`langgraph>=0.2`。不允许以规则引擎或裸 HTTP 调用 LLM 的方式作为最终实现交付。 

#### 为什么必须用 LangGraph

  * 当前 `planner.py` 的 if/else 线性规划和 `llm_plan` 的单次 HTTP 调用，无法支持条件分支、循环反思、并行工具调用、断点恢复等 Agent 核心能力。
  * PRD §6.5 要求的多轮对话、Skill 路由、记忆系统，需要图结构编排而非线性流水线。
  * 确认令牌当前用 Redis + hashlib 手写实现，LangGraph 的 `interrupt()` \+ `Command(resume=)` 提供了标准化的 human-in-the-loop 机制，状态自动持久化到 checkpoint，无需手动管理令牌生命周期。


#### StateGraph 节点设计

AgentState 使用 `TypedDict` 定义，贯穿整个图的执行：

```python
class AgentState(TypedDict):
    messages: list[dict]                  # 消息历史
    canvas_context: dict                  # 画布摘要（非全量 JSON）
    selected_nodes: list[int]             # 选中节点 ID
    skill: Skill | None                   # 当前 Skill 指令
    planned_actions: list[PlannedAction]  # 规划动作列表
    executed_results: list[dict]          # 已执行结果
    pending_confirm: dict | None          # 待确认动作
    reply: str                            # 最终回复
``` 

图由 6 个节点组成，通过条件边路由。每个节点对应当前代码中的一个函数，迁移时逐节点替换：

节点 | 职责 | 当前对应代码
---|---|---
`context_builder` | 调用 canvas-service 摘要接口，拼接上下文 | `run_turn` 中 `httpx.get` canvas
`planner` | LLM 规划，输出结构化动作列表 | `planner.py` `plan()` / `llm_plan()`
`risk_classifier` | 对每个动作调用 `classify_risk` 分级 | `session_service` for 循环内
`executor` | 调用 TOOLS 白名单工具执行 | `execute_tool()`
`confirmer` | `interrupt()` 暂停执行，等待用户确认 | `create_confirm_token` \+ Redis
`reply_builder` | 汇总结果构建最终回复 | `build_reply()`

#### 条件路由

```python
from langgraph.graph import StateGraph, START, END

graph = StateGraph(AgentState)
graph.add_node("context_builder", context_builder_node)
graph.add_node("planner", planner_node)
graph.add_node("risk_classifier", risk_classifier_node)
graph.add_node("executor", executor_node)
graph.add_node("confirmer", confirmer_node)
graph.add_node("reply_builder", reply_builder_node)

graph.add_edge(START, "context_builder")
graph.add_edge("context_builder", "planner")
graph.add_edge("planner", "risk_classifier")

# risk_classifier 按风险等级分流
graph.add_conditional_edges("risk_classifier", route_by_risk, {
    "execute": "executor",   # read / low 风险直接执行
    "confirm": "confirmer",  # high 风险拦截确认
    "done": "reply_builder",  # 无动作可执行
})

# confirmer 暂停等待用户确认
graph.add_conditional_edges("confirmer", route_by_confirm, {
    "accept": "executor",
    "reject": "reply_builder",
})

graph.add_edge("executor", "reply_builder")
graph.add_edge("reply_builder", END)

app = graph.compile(checkpointer=PostgresSaver(...))
``` 

#### Checkpointer 与中断恢复

  * 使用 `PostgresSaver`，`thread_id = session_id`，复用 agent-service 现有 PostgreSQL 实例。
  * 用户确认时前端 POST `/confirm`，后端调用 `Command(resume={"accept": True})` 从 checkpoint 恢复，无需手动管理 Redis 令牌。
  * 画布版本校验在 resume 时重新检查 `canvas_version`，版本不匹配则拒绝执行并提示刷新。
  * 5 分钟超时由 checkpoint TTL 控制，替代当前 Redis 5 分钟过期逻辑。


**确认令牌迁移：** 当前 `tools/registry.py` 中的 `create_confirm_token` / `verify_confirm_token` 将被 LangGraph `interrupt()` 机制替代。迁移完成后 Redis 确认令牌逻辑可移除，但 `classify_risk` 函数保留，作为 `risk_classifier` 节点的核心逻辑。 

#### 协同角色集成（§3.13 落地）

LangGraph 图结构天然适配多角色协同。§3.13 定义的五角色不作为独立进程，而是作为图中的子图 / 异步分支 / 条件边集成到主图。主 Agent 只做编排决策，杂活交给协同角色：

协同角色 | LangGraph 集成方式 | 与主图的交互
---|---|---
**执行引擎** | `executor` 节点内的 exec 类工具调用 | 提交异步任务后返回 ack，不等待结果。条件边路由到 `clock_node` 设置唤醒
**记忆子 Agent** | `reply_builder` 后置 `memory_updater` 子图 | 通过 `Send()` 异步触发，不阻塞主图。主图回复用户后即结束，记忆去重在后台完成
**定时唤醒** | `executor` 条件边 → `clock_node` | 设置延时任务，到点后触发新的图执行（`check_task_status` 入口节点），查询产物状态并 SSE 通知用户
**技能库** | `planner` 节点前置 `skill_loader` 条件判断 | 检测到复合操作指令时，`load_skill` 读取规则注入当前轮 LLM prompt。用完即丢，不常驻
**模型目录** | `planner` 节点内的按需查询 | 缺模型能力事实时，`planner` 内部调用 `list_models` 查参数约束，拿到后继续规划。不作为独立节点

```python
# 集成协同角色后的增强图结构
graph = StateGraph(AgentState)

# 主图节点
graph.add_node("context_builder", context_builder_node)
graph.add_node("skill_loader", skill_loader_node)      # 按需加载 Skill 规则
graph.add_node("planner", planner_node)                # 内部可查模型目录
graph.add_node("risk_classifier", risk_classifier_node)
graph.add_node("executor", executor_node)              # exec 类返回 ack
graph.add_node("clock_node", clock_node)               # 设置定时唤醒
graph.add_node("confirmer", confirmer_node)
graph.add_node("reply_builder", reply_builder_node)
graph.add_node("memory_updater", memory_updater_node)  # 异步记忆更新

# 主图边
graph.add_edge(START, "context_builder")
graph.add_edge("context_builder", "skill_loader")
graph.add_edge("skill_loader", "planner")
graph.add_edge("planner", "risk_classifier")

graph.add_conditional_edges("risk_classifier", route_by_risk, {
    "execute": "executor",
    "confirm": "confirmer",
    "done": "reply_builder",
})
graph.add_conditional_edges("confirmer", route_by_confirm, {
    "accept": "executor",
    "reject": "reply_builder",
})

# executor 后条件路由：有 exec 任务 → clock_node；无 → reply_builder
graph.add_conditional_edges("executor", route_after_exec, {
    "wait_for_result": "clock_node",
    "done": "reply_builder",
})
graph.add_edge("clock_node", "reply_builder")

# reply_builder 后异步触发记忆更新，不阻塞
graph.add_edge("reply_builder", "memory_updater")
graph.add_edge("memory_updater", END)

app = graph.compile(checkpointer=PostgresSaver(...))
``` 

**异步不阻塞原则：**`memory_updater` 和 `clock_node` 都是"发完即走"——`memory_updater` 把记忆更新任务推入 Redis 队列后立即返回，`clock_node` 注册延时任务后立即返回。主图不等它们完成实际工作，只确认任务已派发。用户在 `reply_builder` 阶段就收到回复。 

#### 后续扩展方向（P1+）

以下能力在 V1.0 不实现，但图结构已预留扩展点。§3.12 的 Canvas Norm 编排模型和 §3.13 的五角色协同已在图设计中落地，后续扩展主要是深化：

  * **循环反思** ：`executor` 结果不满足条件时回到 `planner` 重新规划，而非直接进入 `reply_builder`。只需将 `executor → reply_builder` 改为条件边。
  * **并行分支** ：多个独立工具调用（如同时搜索素材 + 读取画布）通过 `Send()` 并行执行，结果在 `reply_builder` 前汇聚。
  * **Canvas Norm 子图** ：§3.12 的依赖图走路（Text 总脚本 → 拆镜头 → 逐镜头生成 → Compose）作为独立子图，`planner` 检测到创作链路指令时路由到该子图，子图内部按 creative_type 自动编排节点 + 连线。
  * **记忆子图深化** ：P1 将 `memory_updater` 从 Celery worker 迁移到 LangGraph 子图，实现去重 / 合并 / 压缩的可视化编排和断点恢复。
  * **多模型路由** ：不同 Skill 路由到不同 LLM（如文案用文学模型，代码用代码模型），在 `planner` 节点前增加 `model_router`。


### 3.7 创作领域模型设计

当前 VibePaper 的节点模型是通用的（text/image/video/audio），Agent 只能做"建几个节点、连几条线"。要让 Agent 真正像导演一样干活，必须在通用节点之上建立**创作领域模型** ——让 Agent 理解每个节点在创作链路中的角色、输入输出规格、以及节点间的依赖语义。

#### 创作节点规格

每种创作节点都有明确的输入契约、输出契约和可执行参数。Agent 在规划时必须按规格匹配上下游，不能把脚本节点直接喂给视频生成节点：

节点类型 | 创作角色 | 输入契约 | 输出契约 | 关键参数
---|---|---|---|---
script（脚本圣经） | 全局上下文，所有镜头的剧情根基 | 用户指令 / 画布已有素材 | 故事大纲、主题、基调 | genre, tone, length
character（角色卡） | 角色一致性规范，下游镜头引用 | 脚本节点 / 用户描述 | 形象描述、服装、表情表 | name, style, ref_images
shot（分镜） | 单镜头可执行规格 | 脚本 + 角色卡 | 画面描述、运镜、时长、台词、转场 | shot_type, duration, transition
keyframe（关键帧） | 镜头首帧构图参考 | 分镜 + 角色卡 | 静态关键图 | composition, camera_angle, style
clip（视频片段） | 单段动态视频 | 关键帧 / 首尾帧 + 分镜参数 | 视频片段 | model, motion_strength, duration
audio（音频） | 旁白 / 对白 / 配乐 | 分镜台词 / 脚本 | 音频片段 | voice_type, language, speed
composite（拼接成片） | 最终输出 | 多个 clip + audio 按顺序 | 成片视频 | order, transition, resolution

#### 活依赖模型

当前 VibePaper 的连线只是"有边"，没有语义。创作 Agent 需要的连线是**活依赖** ——上游改了，下游标记为 stale，Agent 可以自动重跑。这是 Agent 能持续迭代、而不只是单次生成的根基。

**设计要点：** 在 `canvas-service` 的 Edge 模型中增加 `dependency_type` 字段（`reference` / `input` / `control`）。`input` 类型的连线表示下游节点的生成参数依赖上游输出，上游变更时下游自动标记为 `stale`，Agent 可批量重跑 stale 节点。这与 PRD §6.1 乐观锁版本机制兼容——版本变更触发 stale 检查，而非全量重算。 

#### 任务状态机感知

Agent 必须能感知和处理生成任务的真实状态，绝不编造"已完成"。当前任务状态机（`idle → queued → running → succeeded | failed | cancelled | expired`）已就绪，但 Agent 的 `executor` 节点需要在执行前查询任务状态，而非假设上次提交已成功。

```python
# executor 节点内的状态检查逻辑
def executor_node(state: AgentState) -> AgentState:
    for action in state["planned_actions"]:
        if action.tool_name == "submit_generation":
            # 检查该节点是否已有 running/queued 任务
            existing = query_task_status(action.params["node_id"])
            if existing and existing["status"] in ("queued", "running"):
                # 不重复提交，返回当前状态
                state["executed_results"].append({
                    "tool": "submit_generation",
                    "ok": True,
                    "data": {"status": existing["status"], "taskId": existing["id"]},
                    "note": "任务已在队列中，未重复提交"
                })
                continue
        # 正常执行
        result = execute_tool(action)
        state["executed_results"].append(result)
    return state
``` 

### 3.8 决策策略层设计

这是区分"聪明 Agent"和"机械执行器"的关键。当前 `run_turn` 每轮都全量拉取画布 JSON，不管用户问什么都走相同的规划路径。需要引入**决策策略** ，让 Agent 按需获取信息、按需提问、按需写入记忆。

#### 缺了才查，不缺就干

这是最重要的效率规则。`context_builder` 节点不应每次都全量拉取画布，而是根据用户指令判断**缺什么信息才查什么** ：

用户指令类型 | 必须查询 | 无需查询
---|---|---
"帮我梳理画布" | 画布摘要（节点统计 + 连线结构） | 逐个节点详情、素材文件内容
"给这个角色换套衣服" | 选中节点详情 + 关联角色卡 | 画布全量、其他节点
"生成10秒视频" | 选中节点 + 模型能力表（哪个模型支持10秒） | 画布摘要、素材库
"把所有镜头拼成成片" | 所有 clip 节点状态 + 顺序 | 脚本内容、角色卡（已有快照）

#### 信息分层与记忆写入

不同生命周期的信息写入不同存储，不混写。完整的记忆系统设计见 §3.11，此处列出核心规则：

  * **长期记忆** （用户偏好：默认模型、叙事风格、常用音色）→ `user_memories`（scope=long_term），跨画布生效。Agent 在 `reply_builder` 节点检测用户反复选择同一参数时，通过 `update_memory` 异步写入。
  * **当日记忆** （当天临时想法、阶段状态）→ Redis `agent_daily:{user_id}:{date}`，TTL=24h 次日失效。不污染长期层。
  * **项目记忆** （当前画布的世界观、角色设定、风格规范）→ `session_fragments`（canvas_id 绑定），同一画布跨轮生效。Agent 在创建脚本/角色卡节点后异步写入摘要。
  * **阶段临时** （当前轮次的规划动作、工具执行结果）→ AgentState 内部，轮次结束即丢弃，不持久化。
  * **写入三关** ：跨轮需要？归哪层？画布已有？三关全过才写。详见 §3.11 写入判据表。


#### 何时该问用户

只有以下情况才暂停执行并提问，其余情况 Agent 自主决策：

  * **需要创意决策** ：选剧情反转方向、定风格偏好、从多个方案中选一个——这些没有"正确答案"，必须用户定。
  * **只有用户能提供的信息** ：品牌名、目标受众、保密要求等画布上不存在的外部约束。
  * **高风险操作确认** ：删除、花费点数、覆盖已有输出——走 `interrupt()` 机制（§3.6）。


**反模式禁止：** 不允许"确认一下你是否要创建节点？"这类废话提问。如果用户说了"创建一个图片节点"，Agent 直接创建，不问"确定吗"。能用 `read` 工具查到的信息（节点ID、模型参数、素材状态）绝不问用户。 

### 3.9 创作方法论与工作流链路

VibePaper Agent 不应是一个被动的"你说我做"工具，而应内置**导演方法论** ——按创作规律走链路，不跳步、不堆无关节点。这套方法论通过 Skill 指令注入 `planner` 节点的 LLM prompt，决定 Agent 的规划行为。

#### 从0到片的五层工作流

Agent 默认按以下顺序推进创作，每层产出物作为下游层的输入依赖。用户可以从任意层介入，但 Agent 会检查上游是否就绪：

层 | 产出物 | 节点类型 | Agent 行为
---|---|---|---
① 文本底座 | 总脚本 / 故事圣经 / 角色卡 / 风格规范 | script, character | 先落文本节点作为全局参考，后续所有镜头连它
② 拆分镜 | 单镜头可执行规格 | shot | 把长脚本拆成镜头级节点，每个含画面/运镜/时长/台词/转场
③ 视觉锚点 | 角色一致性规范 + 首帧关键图 | keyframe | 先做角色一致性，再逐镜头出关键帧；需精准构图时引导用户用3D导演台
④ 动态生成 | 单段视频 + 匹配音频 | clip, audio | 用关键帧/首尾帧生视频，同步生成旁白/对白，匹配音色
⑤ 后期成片 | 超分 / 裁剪 / 拼接 → 最终成片 | composite | 对片段超分、裁掉多余部分、按顺序拼接输出

#### 三条核心方法论

  * **写下来** ：脚本/分镜/角色卡/一致性规范先落成文本节点，作为全局参考。下游镜头全部连它，保证剧情和视觉的一致性。Agent 不允许"直接生成视频"跳过脚本层——如果用户要求跳步，Agent 提示先建立文本底座。
  * **先静后动** ：先做关键帧/构图参考，再做动态生成。需要精准构图先引导用户搭3D导演台摆机位，而不是上来就乱生成视频。Agent 在规划时自动安排"先生成关键帧图"再"生成视频片段"的顺序。
  * **能力边界认知** ：Agent 知道长脚本不能直接喂给生图节点期望自动出全部分镜——要先拆成镜头级规格。Agent 在规划时自己判断"什么指令该拆、怎么拆"，通过 `list_models` 工具查询模型能力限制（如哪个模型支持10秒视频）。


**活依赖链路：** 所有节点的连线都是"活依赖"——用户改了上游的角色设定或脚本，下游所有镜头标记为 stale，Agent 可以一键重跑自动同步更新。这不是写完就死的静态文字稿，而是可持续迭代的创作管线。 

### 3.10 人格与交互层设计

Agent 人格通过 `planner` 注入的 `AGENT_PERSONA` 固化（自定义 Skill 也保留此骨架）。**结构由规则约束，措辞临场生成**——不背固定模板，也不是「给方向自由发挥」。

**分工（铁路 vs 火车头）**

  * **工作流（纪律）**：能不能、走哪步、参数合不合法——拆节点、依赖/role、偏好参数回填、能力校验与兼容换模、动作路由（edit/exec/read）、状态纪律。
  * **模型（自由度）**：内容长什么样——脚本/对白/镜头描述、prompt 措辞、创意取舍建议。
  * 例：用户「生成镜头 3 视频」→ 系统按偏好回填 Seedance 1.0 Pro / 16:9 / 720p / 4s / 音轨；若用户要 8s 而偏好模型不支持 → 换兼容模型并在回复说明，再由模型写运动描述。

实现：`agent-service/src/agent/domain/workflow_rails.py` · `video_task.py`。

**性格层（软约束）**

  * **身份**：名为 **DD**（VibePaper 创作搭档）；默认回复不报名字，用户问起再说明。
  * **专业**：镜头、分镜、节奏、转场——视频创作语言，不空泛大白话。
  * **简洁偏暖**：先动作后理由；不废话，但语气自然、好商量，不像冷指令机。
  * **有审美**：不堆效果；取舍要有意图。
  * **多语言**：始终跟随用户当前用语。

**原则层（动作纪律）**

  * **直接帮**：暖但不客套；能动手就动手，做完说结果。
  * **缺了才查、不缺就干**：读/查不是打卡。
  * **有主见敢反对**：讨论 → 建议与替代；下指令 → 执行，明显风险可一句点破。
  * **绝不编造**：queued 是回执不是成品。

**规则层（硬约束）**

  * 真缺 id / 状态才 `read` / `query`，否则直接 `edit` / `exec`。
  * 工具报错：解释原因 + 替代方案，禁止同参盲目重试。
  * 不向用户暴露节点 id、jobId、task_id 等内部标识。

**回复形态（措辞层，择一临场写）**

  * **动作型**：做完说结果——「已建节点接上上游，正在生成镜头 3。」
  * **决策型**：需拍板时摆选项——「镜头 5：冷色收尾 / 暖色反转，你定哪个？」
  * **建议型**：风险 + 可执行建议——「第 4 秒转场可能太急，建议抽帧看节奏。」
  * **反对型**：问题 + 应怎么改——「对白情绪偏平，反转点应前置。」

权威源码：`agent-service/src/agent/agent/persona.py`（`AGENT_PERSONA` / `PAPER_AGENT_INSTRUCTIONS`）。

### 3.11 记忆系统设计（三层架构）

当前记忆系统是两层（`UserMemory` 长期 + `SessionFragment` 会话级），用简单词频向量占位，缺少当日记忆层和异步去重合并机制。按"按作用域分层、写入有判据、画布即外部存储"三条原则重构为三层。

**核心理念：** 记忆系统的难点不是"存多少"，而是"什么值得存、什么不值得"。Agent 不自己手动翻三层去"查"，而是用 `update_memory` 后台动作触发记忆子 Agent 异步去重合并——Agent 只负责判断"这条该归哪层、值不值得记"，实际的去重、更新、压缩交给子 Agent 异步完成，不等待、不向用户汇报细节。 

#### 三层记忆架构

层级 | 存什么 | 存储位置 | 特点 | 当前对应
---|---|---|---|---
**长期记忆** | 跨项目、长期的用户偏好：习惯的叙事风格、常用音色、讨厌的镜头语言 | `user_memories` 表（scope=long_term） | 只沉淀会反复用到的稳定偏好，不存一次性琐事。跨画布生效。 | 已有 `UserMemory` 表
**当日记忆** | 今天这个时段内的个人状态/临时想法 | Redis `agent_daily:{user_id}:{date}` | 易过期，次日自然失效，不污染长期层 | **新增**
**项目记忆** | 当前创作项目的一切：世界观、角色设定、剧情线、已定风格方向 | `session_fragments` 表（canvas_id 绑定） | 绑定当前画布/项目，跟着项目走 | 已有 `SessionFragment` 表

#### 写入判据（三关全过才写）

记忆系统最难的不是"存多少"，而是什么值得存。Agent 在写入前必须过三关：

关卡 | 判断 | 通过示例 | 不通过示例
---|---|---|---
① 跨轮需要？ | 这条信息后续轮次是否还要用到 | "主角穿红衣"——后面所有镜头都要保持一致 | "这次用红色"——一次性指令，不写
② 归哪层？ | 分清个人长期偏好、当前项目设定、阶段临时 | 用户习惯用 qwen 模型 → 长期；角色设定 → 项目 | 写错层比不写更糟——会污染别的项目
③ 画布已有？ | 这条信息是否已在画布节点里 | 角色性格不在画布上 → 写项目记忆 | 脚本内容已在节点里 → 不重复存

**反模式禁止：** 不把画布节点内容复制进记忆。画布节点本身已经是"活上下文"——脚本、角色卡、分镜都在节点里，Agent 需要时用 `read` 去取。把画布内容再复制进记忆会造成冗余和数据不一致。 

#### update_memory 异步机制

Agent 在执行过程中判断"这条该记"，但不自己执行去重合并，而是触发 `update_memory` 后台动作，交给记忆子 Agent 异步完成：

```python
# reply_builder 节点内的记忆写入触发
def reply_builder_node(state: AgentState) -> AgentState:
    reply = build_reply(state)

    # 判断是否有值得记忆的信息
    for result in state["executed_results"]:
        # 三关检查
        if should_remember(result, state):
            scope = classify_scope(result, state)  # long_term / daily / project
            # 触发异步记忆更新，不等待
            trigger_memory_update(
                user_id=state["user_id"],
                canvas_id=state["canvas_id"],
                scope=scope,
                content=extract_memory_content(result),
            )

    state["reply"] = reply
    return state


def should_remember(result: dict, state: AgentState) -> bool:
    """三关检查：跨轮需要 + 归属明确 + 画布没有。"""
    # 关1：是否跨轮需要
    if not is_cross_turn_relevant(result, state):
        return False
    # 关2：能否明确归属层级
    scope = classify_scope(result, state)
    if scope is None:
        return False
    # 关3：画布上是否已有
    if already_on_canvas(result, state):
        return False
    return True
``` 

**子 Agent 职责：** 记忆子 Agent 接收 `update_memory` 请求后执行：① 与同层已有记忆做语义去重（embedding 相似度 ≥0.85 视为重复）；② 合并冲突项（新值覆盖旧值，保留时间戳）；③ 长期记忆达 50 条时触发压缩（合并同类项，保留最新）。整个过程异步执行，Agent 不等待结果，不向用户汇报细节。 

#### 上下文压缩：画布即外部存储

Agent 没有一个"塞满的聊天上下文"要硬压缩，而是靠两套机制天然控制体量：

  * **画布即外部存储** ：创作的核心信息（脚本、角色、分镜）都落在画布节点里，它们是活依赖。Agent 要参考时用 `read` 去取，不需要把全部内容常驻在对话里。这等于把"记忆"卸载到了可查询的结构化存储上。
  * **按需读取，缺了才查** ：Agent 不在每个动作前把记忆和画布全读一遍，只在缺真实信息时才读（缺节点 ID、缺状态、缺参数）。所以"工作记忆"始终精炼，不被冗余信息挤占。


#### LangGraph 集成

记忆系统在 LangGraph 图中通过两个机制接入：

  * **读取** ：`context_builder` 节点按需读取项目记忆（`session_fragments`），不读长期记忆（长期记忆只在 `planner` 节点 LLM prompt 中作为 system context 注入）。
  * **写入** ：`reply_builder` 节点末尾触发 `update_memory`，通过 `Send()` 发送到记忆子图（P1 实现），主图不等待子图完成。

```python
# P1: 记忆子图作为并行分支
graph.add_conditional_edges("reply_builder", route_to_memory, {
    "memory_update": "memory_subgraph",  # 异步触发，不阻塞主流程
    "done": END,
})
# memory_subgraph 完成后直接 END，结果不回传主图
``` 

#### 数据模型变更

表 | 变更 | 说明
---|---|---
`user_memories` | 增加 `scope` 字段 | `long_term` / `daily`，区分长期和当日。当日记忆 TTL=24h，由 Redis 管理过期。
`user_memories` | 增加 `last_merged_at` 字段 | 记录子 Agent 最后一次去重合并时间，用于判断是否需要压缩
`session_fragments` | 增加 `fragment_type` 字段 | `worldview` / `character` / `style` / `plot` / `status`，便于按类型检索
Redis | 新增 `agent_daily:{user_id}:{date}` | 当日记忆，TTL=86400s（24h），次日自动失效

### 3.12 Canvas Norm 编排模型

当前 Agent 的"编排"是把用户指令翻译成一组工具调用，顺序执行完就结束。这是**提示词化** 的思路——所有创作逻辑塞进一个 LLM prompt。真正的创作编排应该是**节点化** 的：创作过程不写成一个大 prompt，而是拆成节点。

**核心理念：** 每个节点 = 一个创作意图 + 模型/参数 + <Prompt> \+ <Input>（依赖/连线）+ 当前产出。节点既是上下文单元（脚本、分镜、角色各自独立可复用），也是执行单元（Image/Video/Audio/Text 节点本身就是可执行规格）。Agent 的"工作流"其实是顺着依赖图走路，而非线性地调工具。 

#### 节点即上下文单元

当前 VibePaper 的节点只存 type + params，没有明确的"创作意图"和"输入依赖"语义。Canvas Norm 要求每个创作节点显式声明：

属性 | 含义 | 当前对应 | 变更
---|---|---|---
`creative_type` | 创作意图：script/character/shot/keyframe/clip/audio/composite | 无（§3.7 已设计，未落地） | Node 增加字段
`model_ref` | 绑定的模型 ID + 参数规格 | `params.model` | 提升为节点级一等字段
`prompt` | 该节点的生成提示词（独立可编辑） | `params.prompt` | 提升为节点级一等字段
`inputs` | 显式声明的上游依赖列表（连线就是 Input） | Edge 隐式表达 | Edge 增加 `dependency_type`（§3.7）
`output` | 当前产出（生成后的 URL / 文本内容） | `params.output_url` | 提升为节点级一等字段
`status` | 节点执行状态：idle/queued/running/ready/failed/stale | 任务状态机有，节点没有 | Node 增加 `exec_status` 字段

#### 节点即执行单元

Image / Video / Audio / Text 节点本身就是可执行规格。Agent 不需要把"生成一张图"翻译成 `submit_generation` 调用，而是直接驱动节点执行——节点的 `creative_type` \+ `model_ref` \+ `prompt` \+ `inputs` 已经构成了完整的执行规格。

```python
# Canvas Norm 执行模型：驱动节点而非调用工具
def executor_node(state: AgentState) -> AgentState:
    for node_spec in state["planned_nodes"]:
        # 节点已有完整执行规格，直接驱动
        if node_spec["creative_type"] in ("image", "video", "audio"):
            # exec: 提交异步生成，返回 ack 而非结果
            task_id = submit_generation(
                node_id=node_spec["id"],
                model=node_spec["model_ref"],
                prompt=node_spec["prompt"],
                inputs=resolve_inputs(node_spec["inputs"]),
            )
            # 节点状态 → queued，产物稍后变成节点 output
            update_node_status(node_spec["id"], "queued")
            state["executed_results"].append({
                "node_id": node_spec["id"],
                "ack": True,
                "task_id": task_id,
                "status": "queued",
            })
        elif node_spec["creative_type"] in ("script", "character", "shot"):
            # edit: 文本类节点直接写入内容
            update_node_content(node_spec["id"], node_spec["prompt"])
            update_node_status(node_spec["id"], "ready")
    return state
``` 

#### 依赖图走路

Agent 的工作流是顺着依赖图走路，而非线性地调工具。用户下达意图后，Agent 把意图落成节点 + 连线，然后按拓扑序驱动执行：

阶段 | Agent 动作 | 节点操作
---|---|---
意图落地 | 解析用户意图 → 创建节点 + 连线 | `edit`: create_nodes + connect_nodes
拓扑排序 | 按 Input 依赖对节点排序，确定执行顺序 | 读 Edge 的 `dependency_type=input`
逐节点执行 | 按拓扑序驱动每个可执行节点 | `exec`: submit_generation → ack
产物回写 | 生成完成后，产物变成节点 output | update_node_output + status=ready
下游联动 | 上游 ready 后，下游 stale 节点可重跑 | status 传播 + stale 标记

**edit / exec 二分：** 所有画布操作归为两类。`edit` 搭创作结构（建节点、写提示词、连依赖、调参数、排版、删节点）——同步、即时生效。`exec` 触发实际执行（提交生成、抽帧、剪辑、超分、拼接）——异步、返回 ack 而非结果。这个二分对应工具白名单中的 low risk（edit）和 high risk（exec）。 

### 3.13 多 Agent 协同架构

当前 Agent 是单进程内的线性执行，所有职责挤在一个 `run_turn` 里。真正的创作 Agent 需要多角色协同：执行引擎跑异步生成、记忆子 Agent 后台去重、定时唤醒轮询产物状态、技能库按需加载复合操作规则、模型目录提供能力事实。Agent 自身只做编排决策，不亲自干这些杂活。

#### 五角色协同模型

角色 | 机制 | 干什么 | 当前状态 | 实现方式
---|---|---|---|---
**执行引擎** | `exec` 类工具：submit / compose / extract_clip 等 | 异步跑节点生成，返回 ack 不是结果，产物稍后变成节点 output | `submit_generation` 已实现，其余待扩展 | generation-service + RocketMQ 回调
**记忆子 Agent** | `update_memory` | 后台去重更新跨轮记忆（long_term/daily/project 分域），不阻塞主 Agent | §3.11 已设计，Redis 队列 + Celery worker | P1 迁移到 LangGraph 子图
**定时唤醒** | `clock` | 设置延时提醒，到点带着 note 重新唤醒 Agent 去查产物状态 | **新增** | XXL-JOB 定时任务 / Redis TTL 过期事件
**技能库** | `load_skill` | 需要多步编排的复合操作时按需读规则，不在上下文里重复加载 | Skill CRUD 已实现，未与执行联动 | planner 节点检测 skill_id → 注入 instructions
**模型目录** | `query kind:model` | 缺模型能力事实时才查，拿到完整 params / 输入约束 | `list_models` 工具已实现 | generation-service 模型目录接口

#### 协同交互流程

五个角色不是平行的，而是围绕主 Agent 的编排决策提供能力。以下是典型交互：

```python
# 用户："生成第三镜的视频，10秒"
# 主 Agent 的编排决策流程：

# 1. 技能库：检测到用户指令涉及视频生成，加载 "video-generation" Skill 规则
skill_rules = load_skill("video-generation")  # 按需加载，不常驻

# 2. 模型目录：缺模型能力事实——哪个模型支持10秒？查一下
model_caps = query(kind="model", filter="duration>=10s")
# → seedance-pro supports 10s, params: {resolution, fps, ...}

# 3. edit：落节点 + 连线
node = create_nodes([{
    "creative_type": "clip",
    "model_ref": "seedance-pro",
    "prompt": "第三镜画面描述...",
    "inputs": [{"from": "keyframe_node_3", "type": "input"}],
}])
connect_nodes([{"source": keyframe_3, "target": node, "dependency_type": "input"}])

# 4. exec：提交异步生成，返回 ack 不是结果
task_id = submit_generation(node_id=node, model="seedance-pro", ...)
# → 节点 status = queued, 返回 {"ack": True, "task_id": "xxx"}

# 5. 定时唤醒：设置30秒后查状态
clock(delay=30, note=f"查询任务 {task_id} 状态，更新节点 {node}")

# 6. 记忆子 Agent：异步写入"用户常用 seedance-pro 生成10秒视频"
trigger_memory_update(scope="long_term", content="用户偏好 seedance-pro 10s 视频")

# 主 Agent 立即回复用户："已提交第三镜视频生成（seedance-pro, 10s），预计30秒后出结果。"
# 不等待生成完成，不等待记忆写入，不等待定时任务触发
``` 

**异步 ack 原则：** 执行引擎返回的是 ack（"已收到，正在跑"）不是结果（"这是生成的视频"）。产物稍后通过 MQ 回调变成节点 output，定时唤醒到点后 Agent 主动去查状态并通知用户。主 Agent 绝不阻塞等待生成完成。 

#### 定时唤醒设计

当前 Agent 提交生成任务后，用户只能手动刷新看结果。定时唤醒让 Agent 在产物就绪后主动通知：

  * **触发** ：`executor` 节点提交 exec 类任务后，通过 `clock(delay, note)` 设置延时唤醒。delay 根据模型预估耗时（图15s / 视频60s / 长视频180s）。
  * **唤醒** ：到点后，定时任务带着 note（含 task_id + node_id）重新触发 Agent 的 `check_status` 节点，查询任务状态。
  * **通知** ：任务 succeeded → 更新节点 output + status=ready → 通过 SSE 推送"第三镜视频已生成"给前端。任务 failed → 推送"生成失败，原因是X" + 建议重跑参数。
  * **退避** ：任务还在 running → 设置下一次唤醒（delay *= 1.5，上限 5 分钟），不频繁轮询。

```python
# 定时唤醒在 LangGraph 中的集成
# executor 提交任务后，通过 Send() 触发 clock 子图
graph.add_conditional_edges("executor", route_after_exec, {
    "wait_for_result": "clock_node",    # 设置定时唤醒
    "done": "reply_builder",             # 无 exec 任务，直接回复
})

# clock_node 不阻塞主图，独立完成后触发新的图执行
def clock_node(state: AgentState) -> AgentState:
    for result in state["executed_results"]:
        if result.get("ack") and result.get("task_id"):
            delay = estimate_wait_time(result["model_type"])
            schedule_wakeup(
                delay=delay,
                callback="check_task_status",
                note={"task_id": result["task_id"], "node_id": result["node_id"]},
            )
    return state
``` 

#### 技能库按需加载

当前 Skill 的 instructions 在会话创建时一次性注入 planner，所有规则常驻上下文。按需加载改为：planner 节点检测到用户指令涉及复合操作（如3D导演台构图、超分+抽帧+剪辑流水线）时，才通过 `load_skill` 读取对应技能规则，注入当前轮次的 LLM prompt。用完即丢，不常驻。

场景 | 加载的 Skill | 注入内容
---|---|---
视频生成 | video-generation | 模型能力约束、首尾帧规则、时长限制
3D导演台构图 | 3d-stage-composition | 机位参数、角色站位规则、静态构图参考流程
后期流水线 | post-production | 超分→裁剪→拼接的顺序约束、参数传递规则
角色一致性 | character-consistency | 形象/服装/表情表规范、ref_images 使用方式

#### 模型目录按需查询

Agent 不在每次规划前都查模型目录，只在缺模型能力事实时才查（缺了才查原则，§3.8）：

  * 用户说"生成10秒视频" → 查哪个模型支持10秒 + 完整参数约束
  * 用户说"用 seedance 生成" → 不查（已知模型，直接用）
  * 用户说"超分到4K" → 查哪个超分模型支持4K输出
  * 用户没指定模型 → 查默认推荐模型 + 参数


## 4. 创作 Agent 专项设计

Paper Agent 不是一个只读建议工具，而是创作全链路的编排器。它从"梳理画布"起步，引导用户走完文本底座→拆分镜→视觉锚点→动态生成→后期成片的完整链路（§3.9），并在每个阶段主动落地结构到画布。Agent 的编排遵循 Canvas Norm（§3.12）——创作过程拆成节点而非塞进一个大 prompt，每个节点是独立的上下文单元和执行单元，Agent 顺着依赖图走路而非线性调工具。执行过程中，Agent 只做编排决策，异步生成交给执行引擎、记忆更新交给子 Agent、状态轮询交给定时唤醒（§3.13），自身不阻塞等待。

### 4.1 能力映射

将创作 Agent 的能力映射为内置 Skill `paper-agent-default`，覆盖从0到片的全链路。V1.0 聚焦前三项（梳理/文案/方向），后两项（链路推进、批量重跑）作为 P1 扩展：

能力 | Skill 意图 | 输出形态 | 可能触发的工具 | 优先级
---|---|---|---|---
梳理画布信息，提炼核心创意与明确的下一步 | summarize_canvas | 只读文本建议；可选创建"下一步"文本节点 | get_canvas_summary → （可选）create_nodes | P0
基于画布素材，写出鲜明有记忆点的品牌文案 | write_brand_copy | 只读文案；用户确认后写入文本节点 | get_canvas_summary + search_assets → create_nodes | P0
延展画布内容，提出三个差异化可落地的方向 | brainstorm_directions | 只读三条方案；用户确认后为每条创建分支节点 | get_canvas_summary → create_nodes | P0
链路推进：检查当前画布处于五层工作流的哪一层，推进下一步 | advance_pipeline | 创建下一层节点 + 连线；触发生成 | get_canvas_summary → create_nodes + connect_nodes → submit_generation | P1
批量重跑：上游变更后，重跑所有 stale 下游节点 | reregenerate_stale | 批量 submit_generation + 状态追踪 | get_canvas_summary（stale 节点）→ submit_generation × N | P1

### 4.2 Skill 指令模板

Paper Agent 作为内置 Skill，其 instructions 应固定写入代码或数据库种子，不对普通用户暴露编辑入口（P1 可开放自定义）。指令模板融入五层工作流方法论和人格基线：

```markdown
你是 DD，VibePaper 的创作搭档。

行为准则：
- 用创作者语言说话：分镜、关键帧、运镜、转场、调色。
- 先做再说：能直接执行的不要问"要不要"，做完告知结果；语气自然好商量，暖但不客套。
- 有主见：发现创作问题主动指出，给替代方案。
- 诚实：不编造生成结果，不确定就说不确定。
- 简洁：先动作再理由；默认不报名字、不每轮自我介绍。
- 按创作规律走：文本底座→拆分镜→视觉锚点→动态生成→后期成片，不跳步。

创作方法论：
1. 写下来：脚本/分镜/角色卡/一致性规范先落文本节点，下游镜头全部连它。
2. 先静后动：先做关键帧/构图参考，再做动态生成。
3. 能力边界：长脚本先拆成镜头级规格再生成；查模型能力表确认参数限制。
4. 节点化思维：创作意图落成节点+连线，不塞进一个大 prompt。每个节点是独立的上下文单元和执行单元。
5. 异步不等待：提交生成后返回排队状态，用 clock 设置延时查状态，不阻塞等待。记忆更新交给 update_memory 后台完成。

当前画布信息：
- 画布名称：{canvas_name}
- 节点数量：{node_count}
- 连线数量：{edge_count}
- 选中节点：{selected_nodes}
- 相关上下游节点：{related_nodes}
- 项目记忆（世界观/角色/风格）：{session_fragments}

请根据用户指令选择以下模式回复：
1. 梳理画布：提炼核心创意，指出明确的下一步动作，判断当前处于五层工作流的哪一层。
2. 品牌文案：基于画布素材写出 1–3 条鲜明、有记忆点的品牌文案。
3. 延展方向：提出三个差异化、可落地的创作方向，说明每个方向需要的节点类型。
4. 链路推进（P1）：检查画布创作进度，创建下一层节点并连线，触发生成。
5. 批量重跑（P1）：找到所有 stale 节点，按依赖顺序重新提交生成。

注意：
- 缺了才查：上下文已有信息不要重复查询。只有缺节点ID、素材状态、模型参数时才调 read 工具。
- 除非用户明确要求"添加到画布"，否则只返回文本建议。
- 所有花费点数的操作必须通过 submit_generation，走确认流程。
- 生成任务提交后返回排队状态，不编造"已完成"。用 clock 设置延时查状态，到点主动通知用户。
- 复杂操作先 load_skill 读规则，不在上下文里常驻技能指令。
- 记忆写入用 update_memory 异步触发，不向用户汇报记忆细节。
``` 

### 4.3 执行流程

*[SVG 图示]* 图 2：Paper Agent 执行流程

### 4.4 输出规范

创作 Agent 的输出应统一为 JSON 结构，便于前端渲染。V1.0 支持三种 replyType，P1 扩展两种：

```json
{
  "replyType": "summary" | "copy" | "directions" | "pipeline" | "rerun",
  "reply": "用户可直接阅读的自然语言回复",
  "pipelineStage": "text_base" | "storyboard" | "visual_anchor" | "dynamic_gen" | "post_production",
  "suggestions": [
    {"type": "text", "title": "", "content": "", "nodeParams": {}},
    {"type": "image", "title": "", "prompt": ""}
  ],
  "staleNodes": [{"nodeId": 0, "reason": "上游角色卡已修改"}],
  "nextActions": ["创建文本节点", "生成概念图"],
  "requiresConfirmation": true | false
}
``` 

## 5. 优化方案

### 5.1 规划器重构：强制 LangGraph 接入

当前 `planner.py` 的规则引擎和 `llm_plan` 裸 HTTP 调用必须重构为 LangGraph StateGraph（详见 §3.6）。重构要点：

  * **依赖提升** ：将 `langgraph` 从 `pyproject.toml` 的 optional-dependencies 移入 `dependencies` 主列表，安装时默认包含。
  * **规则引擎降级为 fallback** ：`planner.py` 中的 `plan()` 规则引擎不删除，作为 LLM 不可用时的 fallback 逻辑嵌入 `planner` 节点内部。当 `llm_api_key` 未配置或 LLM 调用失败时自动回退。
  * **内置 Skill 路由** ：`planner` 节点检测会话是否绑定 `paper-agent-default`，若是则使用专用 LLM prompt，否则走通用规划。
  * **LLM 默认启用** ：P0 阶段 Paper Agent 三项能力必须依赖 LLM。配置缺失时给出明确降级提示，不生成低质量占位节点。
  * **输出约束** ：LLM prompt 强制要求输出 `replyType` 和 `suggestions` JSON，配合 LangGraph Structured Output 解析，减少解析失败。
  * **确认机制迁移** ：`confirmer` 节点使用 `interrupt()` 替代 Redis 令牌，`classify_risk` 函数保留作为 `risk_classifier` 节点逻辑。


### 5.2 上下文精简

  * 在 `canvas-service` 新增 `GET /internal/canvases/{id}/summary`，返回节点类型统计、主题关键词、有效/无效连线、选中节点摘要。
  * Agent 不再传输全量 canvas JSON，只请求摘要 + 选中节点 + 上下游节点详情。
  * 素材上下文只传前 5 个最相关素材的标题/类型/缩略图 URL，不传输文件内容。


### 5.3 工具执行与上下文回写

  * `execute_tool` 成功后，将工具结果以 `assistant` 角色追加到 `agent_messages`，msg_type=`result`。
  * LLM 规划时读取这些 `result` 消息，使 Agent 能基于执行结果继续迭代。
  * 失败时同样回写，msg_type=`error`，避免重复尝试同一错误路径。


### 5.4 前端 Agent 面板

前端需实现以下组件（如尚未完成）：

  * **Agent 浮窗** ：右下角展开/收起，显示对话历史。
  * **步骤流** ：展示 Agent 当前正在执行的 tool 和 summary。
  * **确认弹窗** ：展示影响范围、涉及节点数、estimated_cost、操作摘要，提供"确认/取消"。
  * **建议卡片** ：Paper Agent 的文案/方向以卡片形式展示，支持"一键添加到画布"。


### 5.5 计费与资金安全

优化过程中必须保留现有计费链路，不新增资金路径：

  * Paper Agent 触发生成时仍通过 `submit_generation` → `billing-service:/api/v1/tasks`。
  * 只读建议（梳理/文案/方向）不触发计费。
  * 写入节点操作若产生费用，必须在确认弹窗中展示 `estimated_cost`。


### 5.5a 创作领域模型扩展

当前 VibePaper 的节点和连线没有创作领域语义，Agent 无法理解"这个节点是脚本还是分镜"以及"这条连线是引用还是输入依赖"。需要扩展：

  * **节点类型扩展** ：在 `canvas-service` 的 Node 模型中增加 `creative_type` 字段（`script` / `character` / `shot` / `keyframe` / `clip` / `audio` / `composite`），与现有通用 `type`（text/image/video/audio）正交。`creative_type` 为 null 时表示普通节点，非 null 时 Agent 按创作规格匹配上下游。
  * **连线语义扩展** ：Edge 增加 `dependency_type` 字段（`reference` / `input` / `control`）。`input` 类型连线上游变更时下游标记 `stale`，Agent 可批量重跑。
  * **stale 标记** ：Node 增加 `stale` 布尔字段，画布版本变更时由 `canvas-service` 沿 `input` 连线传播标记。Agent 通过 `get_canvas_summary` 返回的 stale 节点列表决定是否提示用户重跑。


### 5.5b 决策策略实现

当前 `context_builder` 节点（对应 `run_turn` 中的 `httpx.get`）每轮都全量拉取画布 JSON。需要按 §3.8 的"缺了才查"策略重构：

  * **指令分类** ：在 `context_builder` 节点内，先对用户指令做轻量分类（梳理/编辑/生成/查询），按分类决定查询范围。不需要全量画布的指令只请求摘要接口。
  * **记忆写入** ：在 `reply_builder` 节点通过 `update_memory` 异步触发记忆子 Agent，按三关判据写入对应层（长期/当日/项目）。不等待子 Agent 完成，不向用户汇报记忆细节。详见 §3.11。
  * **废话提问过滤** ：在 `planner` 节点的 LLM prompt 中加入约束——"能用 read 工具查到的信息不要问用户；只有创意决策和外部信息才提问"。


### 5.6 埋点与可观测性

补充 PRD §11 要求的 Agent 事件：

事件 | 触发条件 | 必传参数
---|---|---
agent_action_success | 工具执行成功 | session_id, action_type, node_count_affected
agent_action_fail | 工具执行失败 | session_id, action_type, error_code
agent_confirm_show | 确认弹窗展示 | session_id, action_type, confirm_reason
agent_confirm_accept | 用户确认 | session_id, action_type
agent_confirm_reject | 用户取消 | session_id, action_type

### 5.7 优化优先级矩阵

问题 | 优化项 | 优先级 | 估算工作量
---|---|---|---
规划器是手写 if/else，与 PRD 技术选型冲突 | 强制重构为 LangGraph StateGraph + interrupt 确认机制 + 协同角色节点集成 | P0 | 5–8 天
创作 Agent 能力未落地 | 内置 paper-agent-default Skill + 专用 LLM prompt（融入五层工作流方法论 + Canvas Norm 节点化思维） | P0 | 3–4 天
上下文 Token 爆炸 | canvas-service 摘要接口 + context_builder 按需查询（缺了才查） | P0 | 2–3 天
工具结果未回写 | execute_tool 结果写入 agent_messages | P0 | 1–2 天
前端缺少 Agent 面板 | 浮窗、步骤流、确认弹窗、建议卡片 | P0 | 5–7 天
创作编排是提示词化，不是节点化 | Canvas Norm 编排模型：节点 creative_type 扩展 + 依赖图走路 + edit/exec 二分落地 | P1 | 4–5 天
Agent 单进程线性执行，无协同角色 | 五角色协同：clock 定时唤醒 + update_memory 异步记忆 + load_skill 按需技能 + 模型目录按需查询 | P1 | 5–7 天
连线无语义，无法实现活依赖 | Edge 增加 dependency_type 字段 + stale 标记机制 | P1 | 3–4 天
Agent 每轮全量拉画布，效率低 | context_builder 按指令类型决定查询范围 + 记忆分层写入规则 | P1 | 2–3 天
记忆系统两层，缺当日层和异步去重 | 重构为三层记忆 + update_memory 异步子 Agent + 写入三关判据 | P1 | 4–5 天
缺少 Agent 埋点 | 补充 agent_action/confirm 事件 + 协同角色事件（clock_wakeup/memory_updated/skill_loaded） | P1 | 1–2 天
创作专用工具未注册 | 抽帧/剪辑/超分/拼接工具注册到 TOOLS 白名单 + 协同工具（clock/update_memory/load_skill）注册 | P2 | 5–8 天

### 5.8 Canvas Norm 编排与多 Agent 协同优化

§3.12 和 §3.13 引入的两项架构升级需要在优化方案中明确落地路径。这两项不是独立功能，而是对已有 LangGraph 图、工具白名单、Skill 系统的深化扩展：

  * **Canvas Norm 落地** ：在 `canvas-service` 的 Node 模型增加 `creative_type` 字段（§5.5a 已规划），Agent 的 `planner` 节点根据 `creative_type` 自动匹配上下游依赖规格。用户说"生成第三镜视频"时，Agent 不是查全部画布，而是沿 `input` 连线找到第三镜的脚本节点和首帧节点，按依赖规格生成。这是从"工具线性调用"到"依赖图走路"的核心转变。
  * **协同角色落地** ：在 LangGraph 图中增加 `clock_node`、`memory_updater`、`skill_loader` 三个节点（§3.6 已设计）。V1.0 用 Celery + Redis 实现异步队列，P1 迁移到 LangGraph 子图。`check_task_status` 作为独立的图入口节点，由定时唤醒触发，查询产物状态后通过 SSE 推送通知。
  * **edit / exec 二分强化** ：工具白名单中的 `edit` 类工具（create_nodes / connect_nodes / update_node_config）搭创作结构，`exec` 类工具（submit_generation / extract_clip / compose_final）触发异步执行。Agent 的 LLM prompt 必须在规划时明确区分"我要搭结构"还是"我要触发执行"，不混用。
  * **异步 ack 协议** ：`exec` 类工具统一返回 `{"ack": true, "task_id": "..."}`，主 Agent 回复用户"已提交，预计 N 秒后出结果"，然后 `clock_node` 设置延时唤醒。产物就绪后 Agent 主动 SSE 通知，用户无需手动刷新。


## 6. 实施计划

### 6.1 阶段划分

阶段 | 任务 | 验收标准
---|---|---
Phase 1（1.5 周） |  1\. **LangGraph StateGraph 接入** ：langgraph 移入主依赖，6 节点图替换 run_turn 线性循环
2\. interrupt() 替代 Redis 确认令牌，PostgresSaver 持久化
3\. 实现 canvas-service 摘要接口
4\. Agent 上下文精简（context_builder 节点）
5\. 工具结果回写 agent_messages（executor 节点）  |  LangGraph 图编译通过，SSE 流式输出正常
高风险操作 interrupt/resume 端到端验证通过
大画布请求 Token 降低 ≥50%
工具执行结果可在消息历史中查看
Phase 2（1.5 周） |  1\. 内置 paper-agent-default Skill（融入五层工作流方法论 + Canvas Norm 节点化思维 + 人格基线）
2\. 专用 LLM prompt + JSON 输出约束（含 pipelineStage 字段）
3\. 后端建议/文案/方向生成接口
4\. context_builder 按需查询（缺了才查策略）
5\. 记忆分层写入规则初步落地（user_memories scope 字段 + session_fragments fragment_type）
6\. **协同工具注册** ：update_memory / clock / load_skill 注册到 TOOLS 白名单  |  梳理/文案/方向 API 返回符合格式
Agent 回复包含专业术语，不寒暄
不同指令类型查询范围不同（可从日志验证）
人工抽检建议质量可接受
协同工具调用返回 ack 格式正确
Phase 3（1.5 周） |  1\. 前端 Agent 浮窗
2\. 步骤流与建议卡片
3\. 确认弹窗（影响范围 + 费用）
4\. **三层记忆系统** ：当日记忆 Redis 层 + update_memory 异步子 Agent + 写入三关判据
5\. **定时唤醒** ：clock_node 节点 + XXL-JOB 定时任务 + check_task_status 入口节点 + SSE 产物通知
6\. **技能库按需加载** ：skill_loader 节点 + 复合操作 Skill 规则注入  |  Paper Agent 三条能力端到端可演示
高风险操作必须确认后才能执行
记忆写入异步触发不阻塞主流程（日志可验证）
当日记忆次日自动失效
生成任务完成后 Agent 主动 SSE 通知（无需手动刷新）
复合操作自动加载对应 Skill 规则
Phase 3b（1 周） |  1\. **Canvas Norm 编排落地** ：Node 增加 creative_type 字段 + Edge 增加 dependency_type
2\. planner 节点按 creative_type 匹配上下游依赖规格
3\. edit / exec 二分强化：LLM prompt 明确区分搭结构 vs 触发执行
4\. 异步 ack 协议：exec 类工具统一返回 {"ack": true, "task_id"}
5\. stale 标记传播 + 批量重跑  |  节点 creative_type 在画布 CRUD 中正确持久化
Agent 生成指令时沿 input 连线查找依赖（日志可验证）
exec 工具统一返回 ack 格式
上游节点变更后下游标记 stale 并提示重跑
Phase 4（0.5 周） |  1\. 补充 Agent 埋点
2\. 集成测试与回归  |  agent_action/confirm 事件接入 admin 分析
Playwright Smoke 通过

### 6.2 验收标准

  * 用户输入"帮我梳理这张画布"，Agent 返回核心创意 + 下一步建议，并判断当前处于五层工作流的哪一层。
  * 用户输入"写一句品牌文案"，Agent 基于画布素材返回文案，并支持一键写入文本节点。
  * 用户输入"给我三个方向"，Agent 返回三条差异化方案，并支持为每条创建分支节点。
  * Agent 回复使用专业术语（分镜/关键帧/运镜），不寒暄不铺垫，先动作再理由。
  * 不同指令类型的查询范围不同——"梳理画布"只请求摘要，"修改选中节点"只请求选中节点详情（可从日志验证）。
  * Agent 不问"确定要创建节点吗"这类废话——能用 read 工具查到的信息不问用户。
  * 所有写入/生成操作在确认前不改画布、不扣费。
  * 画布版本变化后，未确认的 interrupt 自动失效。
  * 生成任务提交后返回排队状态，不编造"已完成"。
  * 生成任务完成后，Agent 通过 SSE 主动通知用户"第三镜视频已生成"，无需手动刷新。
  * Agent 规划时沿 input 连线查找依赖节点——用户说"生成第三镜视频"时，Agent 自动找到第三镜的脚本和首帧节点，不查全量画布（可从日志验证）。
  * exec 类工具统一返回 ack 格式 `{"ack": true, "task_id": "..."}`，主 Agent 回复"已提交，预计 N 秒后出结果"。
  * 记忆写入通过 update_memory 异步触发，主流程响应时间不受记忆去重影响（可从日志验证 ack 到回复的时间差）。
  * 复合操作（如3D导演台构图）自动加载对应 Skill 规则，不在上下文中常驻所有技能指令。
  * 上游节点变更后，下游 stale 节点被正确标记，Agent 提示用户可重跑。


## 7. 附录

### 7.1 数据模型（已存在，无需变更）

表 | 关键字段
---|---
agent_sessions | id, user_id, canvas_id, title, skill_id, token_used_total, points_used_total, model_usage, status
agent_messages | id, session_id, role, msg_type, content, meta
agent_actions | id, session_id, user_id, action_type, tool_name, params, risk_level, confirm_reason, status, confirm_token, canvas_version, result
skills | id, owner_id, name, description, instructions, source, version

### 7.2 新增/变更接口

接口 | 服务 | 说明
---|---|---
GET /internal/canvases/{id}/summary | canvas-service | 新增：返回画布摘要、节点统计、关键词
POST /api/v1/agent/sessions/{id}/messages | agent-service | 已有：Paper Agent 能力复用此 SSE 接口
POST /api/v1/agent/sessions/{id}/confirmations/{action_id} | agent-service | 已有：高风险操作确认

### 7.3 错误码

错误码 | 场景 | retryable
---|---|---
INSUFFICIENT_POINTS | 可用点数不足 | false
VERSION_CONFLICT | 确认期间画布版本变化 | true
CONFIRM_TOKEN_EXPIRED | 确认令牌过期 | true
TOOL_ERROR | 工具执行失败 | false

VibePaper Agent 功能设计文档与优化方案 · v1.2 · 2026-08-06

依据：PRD V2.1、技术概要设计方案、V1.0-engineering-spec.md、当前代码实现、Canvas Norm 编排模型、多 Agent 协同架构