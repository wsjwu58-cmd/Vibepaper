# Agent 控制平面 P0 实施 Spec

> 状态：已定稿讨论稿 · 日期：2026-08-15  
> 权威原则：LangGraph = 控制平面；Canvas = 数据与执行平面；Memory Store = 语义记忆；Checkpointer = 任务进度。  
> 相关文档：`docs/agent-runtime-flow.md`（现状）· 本文（目标 P0）  
> 范围：**不**把每个 Image/Video/Text Canvas 节点映射成 LangGraph 节点。

---

## 0. P0 目标与非目标

### 目标（可验收）

1. 主图收敛为 **12 个控制节点**（见 §3），计划以 State 内 DAG 表达。
2. LLM 只产出 **结构化领域动作**；经 Adapter 编译/校验后才调现有 `TOOLS`。
3. 写操作带 **业务幂等键**；恢复/重试不重复建节点、不重复提交生成。
4. 异步生成：**queued → checkpoint → END**；终态事件 **resume**；`clock` 降级为兜底。
5. 引用必须经 **resolve_refs**，禁止模型编造数字 `node_id`。
6. 约束优先级：`explicit > session_override > project > preferences > model_defaults`；不兼容则查能力或问用户，禁止静默改时长/画幅。

### 非目标（P0 不做）

- 拆出完整专业子图集群（script/storyboard/… 九套）
- 创作层完整 QA（剧本钩子/连续性审校 checklist）
- 替换前端确认 UI 交互范式（沿用现有确认卡 / SSE）
- 重写 canvas-service / generation-service 领域模型

---

## 1. 控制平面 vs 数据平面

| 平面 | 职责 | 存放内容 | 禁止 |
|------|------|----------|------|
| **LangGraph** | 意图、计划、审批、调度、等待、恢复、验收、回复 | `UserIntent`、`PlanStep[]`、`pending_jobs`、interrupt | 每个镜头一个 Graph 节点 |
| **Canvas** | 创作资产、依赖连线、生成状态、产物 URL/正文 | Text/Image/Video/Audio/Compose/… 节点与 Edge | 把全量历史塞进 Agent State |
| **Checkpointer** | 本会话任务执行到哪一步 | State 快照、pending、interrupt | 图片/视频二进制 |
| **Memory Store** | 跨轮语义事实 | 偏好、项目 canon、阶段摘要候选 | 整段工具原始返回 |

```text
用户消息
  → bootstrap → understand → resolve_refs → retrieve
  → plan → policy_check → ask_or_approve?
  → compile → execute → observe
       ├─ waiting → END（等事件 resume）
       ├─ recover → retry / ask / abort
       └─ validate_and_respond → END
```

---

## 2. 核心数据契约

### 2.1 UserIntent

替换当前单标签 `IntentResult.name`；路由可派生兼容字段。

```python
class UserIntent(BaseModel):
    mode: Literal[
        "discuss", "create", "edit", "rerun",
        "connect", "compose", "review", "organize",
    ]
    domain: Literal[
        "text", "image", "video", "audio",
        "storyboard", "character", "mixed",
    ]
    goal: str = ""
    deliverables: list[str] = []
    # 三层约束（合并时按优先级应用）
    constraints: dict[str, Any] = Field(
        default_factory=lambda: {"explicit": {}, "preferred": {}, "inferred": {}}
    )
    ambiguities: list[str] = []
    missing_information: list[str] = []
    selected_skill_keys: list[str] = []  # 最多 1～3
    confidence: float = 0.0
    # 兼容旧路由
    wants_execution: bool = False
```

**派生路由（规则，不全靠 LLM）：**

| 条件 | 下一跳 |
|------|--------|
| `missing_information` 非空 | `ask_or_approve`（信息补充） |
| `mode == discuss` | `validate_and_respond`（直接答，不写画布） |
| `mode in {edit,rerun,connect}` 且指代未消歧 | `resolve_refs` 后再 plan |
| 其余可执行 | `plan` |

### 2.2 PlanStep（State 内 DAG）

```python
class PlanStep(BaseModel):
    step_id: str
    action: str  # 领域动作名，如 create_script / generate_keyframes
    status: Literal[
        "pending", "running", "queued", "blocked",
        "completed", "failed", "skipped",
    ] = "pending"
    depends_on: list[str] = []
    parallel_group: str | None = None
    async_job: bool = False
    billable: bool = False
    requires_approval: bool = False
    canvas_alias: str | None = None   # 计划内别名，如 shot03_keyframe
    canvas_ref: str | None = None     # 解析后的真实 node_id 字符串
    inputs: list[str] = []            # 别名或 ref
    params: dict[str, Any] = {}
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    idempotency_key: str | None = None
```

**Ready Set：**

```text
ready = status==pending AND all(dep in completed)
每轮只 dispatch ready；有 pending_jobs 则 observe → waiting → END
禁止每步后整图重规划（除非 recover 明确要求 replan）
```

### 2.3 CanvasAction（受控工具动作）

```python
class CanvasAction(BaseModel):
    action_id: str
    operation: Literal[
        "read", "query", "create", "patch",
        "connect", "disconnect", "delete", "layout",
        "submit", "extract_clip", "extract_frame",
        "compose", "sign", "retry", "capture",
    ]
    target_ref: str | None = None
    payload: dict[str, Any] = {}
    step_id: str | None = None
    idempotency_key: str  # 必填（写操作）
```

**幂等键公式：**

```text
{session_id}:{plan_version}:{step_id}:{action_index}
```

执行前查 `agent_actions`（或等价动作日志）：同 key 已成功 → 返回上次结果，不重放。

### 2.4 ActionResult（归一化）

```python
class ActionResult(BaseModel):
    ok: bool
    status: Literal["ready", "queued", "pending", "skipped", "failed"]
    target_ref: str | None = None
    created_refs: list[str] = []
    task_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    facts: dict[str, Any] = {}  # 仅摘要，无媒体本体
```

语义铁律：`queued ≠ ready`；创建节点成功且未提交 → `skipped` 或 `ready`（结构就绪），不得对用户宣称「已生成完成」。

### 2.5 AgentState（P0 字段集）

在现有 `graph/state.py` 上演进，**增量兼容**；大字段原则：只存 ref 与摘要。

| 分组 | 字段 | 说明 |
|------|------|------|
| 会话 | `session_id`, `user_id`, `canvas_id`, `canvas_version`, `user_content`, `selected_nodes` | 沿用 |
| 上下文 | `relevant_context`, `project_summary`, `generation_preferences`, `recent_messages`, `project_memories`, `long_term_prefs` | **废除**每轮全量 `canvas_context` 进 LLM；摘要级可保留短结构 |
| 理解 | `intent: UserIntent`, `missing_information`, `alias_bindings` | 新 |
| 计划 | `plan: {version, steps[]}`, `current_step_ids` | 升为唯一执行真相 |
| 执行 | `tool_actions`, `pending_jobs`, `failures`, `retry_count` | `pending_runs` 映射为 `pending_jobs` |
| 人机 | `requires_approval`, `approval_reason`, `interrupt_kind` | 扩三类 interrupt |
| 交付 | `validation_report`, `reply`, `next_actions`, `memory_candidates` | |
| 终端 | `terminal_status`, `waiting_external_event`, `run_version` | 沿用 |
| 可观测 | `events`（reducer + 截断） | 沿用 |

**禁止写入 State：** 图片/视频二进制、完整制品、超大画布历史 output 全文。

---

## 3. P0 十二节点职责

| # | 节点名 | 职责 | 主要读写 State |
|---|--------|------|----------------|
| 1 | `bootstrap_context` | 合并会话/偏好/未完成 checkpoint；判断是否需要读画布；递增 `run_version` | 写 preferences 快照、terminal=running |
| 2 | `understand_intent` | 输出 `UserIntent` + 三层 constraints；填 `missing_information` | 写 intent |
| 3 | `resolve_references` | 消歧「刚才那张 / 第三个镜头」→ `alias_bindings`；多候选则 missing | 写 bindings / missing |
| 4 | `retrieve_relevant_canvas` | 按任务局部拉取节点（缺事实才读）；填充 `relevant_context` | 写 relevant_context |
| 5 | `plan` | 产出 DAG `PlanStep[]`；标 parallel / async / billable / approval；加载 ≤3 Skill 规则 | 写 plan |
| 6 | `policy_check` | 约束合并、模型能力、成本/覆盖风险、依赖就绪 | 写 requires_approval、model_overrides、warnings |
| 7 | `ask_or_approve` | `interrupt()`：信息补充 / 创作决策 / 执行审批 | waiting_user |
| 8 | `compile_actions` | 领域动作 → `CanvasAction[]`；解析 alias→ref；填幂等键 | 写 tool_actions |
| 9 | `execute_tools` | Adapter 调现有 TOOLS；写动作日志；归一 `ActionResult` | 更新 step status、pending_jobs |
| 10 | `observe_results` | 汇结果；算下一 Ready Set；有 pending → waiting；全完 → validate | route |
| 11 | `recover` | 按 `error_code` 分类：wait / repair / retry / ask / abort | 更新 retry_count、failures |
| 12 | `validate_and_respond` | P0：状态真实性验收 + 回复 + memory_candidates | reply、terminal |

**Skill：** P0 只注入规则进 `plan`，**不**新增 9 个 workflow Graph 节点。

---

## 4. 与现网 `app.py` 对照

### 4.1 节点映射

| 现节点 | P0 归属 | 迁移说明 |
|--------|---------|----------|
| `ingest` + `context_builder` | `bootstrap_context` | 合并；偏好快照进此 |
| `classify_intent` | `understand_intent` | 升维 UserIntent |
| （缺失） | `resolve_references` | **新建** |
| `acquire_context` / 摘要读取 | `retrieve_relevant_canvas` | 局部检索，禁止默认全量 |
| `select_skill` + `load_skill` | `plan` 内前置 | 选 key + 注入规则，不单独成边 |
| `create_plan`（含 ReAct） | `plan` | **取消自由 ReAct  invent tools**；复杂任务也出 DAG |
| `validate_plan` + `risk_classifier` | `policy_check` + `compile_actions` | 拆：策略 vs 编译 |
| `request_user_input` + `confirmer` | `ask_or_approve` | 统一三类 interrupt |
| `executor` / `tool_worker` / `parallel_merge` | `execute_tools` | 并行保留 Send，但动作必须来自 compile |
| `clock_node`（生成轮询） | 降级兜底 | 主路径改事件 resume |
| `reflect` | `recover` | 按 error_code 分类，限次 |
| `finalize` + `reply_builder` + `memory_updater` | `validate_and_respond` | 可内部分函数，对外一节点 |
| `answer_discussion` / `fallback` | `understand` 后短路到 `validate_and_respond` | 保留行为 |
| `reconcile_canvas` / `plan_recovery` | `bootstrap` 检测未完成 + `plan` rails | 推进/重跑进 DAG，不另开意图名分叉优先 |

### 4.2 边对照（目标）

```text
START → bootstrap → understand
understand →
  missing? ask_or_approve → (resume) understand|plan
  discuss? validate_and_respond → END
  else → resolve_refs → retrieve → plan → policy_check
policy_check →
  ask/approve? ask_or_approve → (resume) compile|plan
  fail? validate_and_respond → END
  else → compile → execute → observe
observe →
  continue → compile|execute   # 下一 Ready Set
  waiting → END
  recover → recover
  validate → validate_and_respond → END
recover →
  retry → execute
  wait → END
  ask → ask_or_approve
  abort → validate_and_respond → END
```

### 4.3 删除/冻结的行为

| 行为 | 处理 |
|------|------|
| `route_after_exec` → `continue: create_plan`（整轮重规划） | 改为 Ready Set 循环，默认不重规划 |
| ReAct 每拍自由 invent `create_nodes`/`submit_generation` | 仅允许输出领域动作 / 更新 plan；执行只走 compile |
| `clock` 主路径轮询生成 | 仅兜底（事件丢失）；见 §5 |
| 模型输出裸数字 node_id | compile 阶段拒绝，必须经 `alias_bindings` |

---

## 5. 异步事件 Resume 契约

### 5.1 现状问题

- 主路径：`executor` ack → `clock_node` → Redis ZSET → Celery → `run_agent_wakeup` → `check_task_status` 退避再挂 clock。
- generation 终态已 `notify_canvas_node`，**未**直接 resume Agent checkpoint。

### 5.2 P0 目标链路

```text
execute_tools: submit → ActionResult(status=queued, task_id)
  → pending_jobs += {task_id, node_ref, step_id, session_id, plan_version}
  → checkpoint
  → terminal_status=waiting_external_event
  → END

generation 终态 (succeeded|failed|cancelled|expired|settlement_error)
  → 写 Canvas（已有）
  → 发事件 AgentResumeEvent
  → agent-service 消费者：Command(resume=payload) 或 invoke wakeup 子图
  → observe：核对 Canvas 真实 execStatus
  → ready：step=completed，解锁下游 Ready Set → compile/execute
  → failed：failures += … → recover
```

### 5.3 事件载荷（建议）

```json
{
  "type": "generation_terminal",
  "session_id": 123,
  "user_id": 456,
  "canvas_id": 789,
  "task_id": "…",
  "node_id": 1011,
  "status": "succeeded",
  "plan_version": 3,
  "step_id": "s4",
  "error_code": null,
  "occurred_at": "2026-08-15T02:00:00Z"
}
```

投递通道 P0 可选其一（按现有基建优先级）：

1. **Redis Stream / List**（与现 `agent_clock_jobs` 同栈，改造成终态推送）  
2. RocketMQ（generation 已有 messaging 骨架）  
3. HTTP 内部回调 `POST /internal/agent/resume`

**幂等：** 同一 `(session_id, task_id, status)` 只 resume 一次（可用 `agent_wakeup_notice` 类去重键）。

### 5.4 clock 降级策略

| 场景 | 行为 |
|------|------|
| 正常终态事件 | 不挂 clock |
| 事件超时未达（如 10min 仍 queued） | clock 兜底查一次真实状态 |
| 非生成提醒 | clock 仍可用 |

### 5.5 wakeup 子图（演进）

现 `build_wakeup_graph`：`check_task_status → clock|reply`  

P0 改为：

```text
ingest_event → verify_canvas_truth → advance_plan → execute_ready? → reply
```

不再默认 `needs_reclock` 循环。

---

## 6. Canvas Tool Adapter

### 6.1 对外稳定接口（领域/能力层）

| Adapter API | 底层 TOOLS（过渡期） |
|-------------|----------------------|
| `read_canvas` / `read_node` | `get_canvas_summary`, `get_selected_nodes`, `get_all_nodes` |
| `query_nodes` / `query_models` / `query_assets` | 新建条件查询 + `list_models` + `search_assets` |
| `create_canvas_node` / `patch_canvas_node` | `create_nodes`, `update_node_config` |
| `connect_nodes` / `disconnect` / `layout` | `connect_nodes`, `layout_nodes`, `delete_nodes` |
| `submit_node` | `submit_generation` |
| `extract_clip` / `extract_frame` | `trim_clip`, `extract_frames` |
| `compose_videos` | `compose_final` |
| `sign_asset` / `retry_artifact` | **P0 可 stub**（返回明确 not_implemented） |
| `capture_scene` | `capture_3d_scene` |

### 6.2 管线

```text
PlanStep.action
  → compile_actions（领域→CanvasAction）
  → Validator（引用存在、模型能力、参数、依赖 ready）
  → Permission / Cost Guard（确认令牌、点数预估）
  → Tool Executor（调 TOOLS）
  → Result Normalizer（ActionResult）
  → State Reducer（更新 plan / pending_jobs）
```

### 6.3 偏好合并

```text
resolve_generation_config:
  model_defaults
  < user_preferences（generation_preferences）
  < project_rules
  < session_override（确认卡修改）
  < explicit（本轮 UserIntent.constraints.explicit）
```

关键帧→视频同链路：planner 必须输出统一 `aspectRatio`；若 preferences 图 1:1 / 视频 16:9 冲突，以 explicit 或本链路统一值为准，并写入 `plan.assumptions`。

---

## 7. Human-in-the-loop

使用 LangGraph `interrupt()`，三类 payload：

| kind | 何时 | 示例 options |
|------|------|----------------|
| `clarify` | 缺只有用户能给的信息 / 指代多候选 | 上传、选择素材 |
| `decide` | 互斥创作方向 | A/B 风格、叙事视角 |
| `approve` | 成本/范围/覆盖 | 继续 / 只做脚本分镜 / 修改方案 |

与 PRD 对齐：

- 写画布（创建/连线/布局/改配置/删除）默认免确认，执行后回显。  
- `estimated_cost ≥ 1` 的生成、模型切换、批量 >20、覆盖输出 → `approve`。  
- 常规景别、布局、默认节奏、已唯一目标的轻量修改 → **不** interrupt。

---

## 8. 失败恢复（P0 最小集）

| error_code | failure_class | 动作 | 上限 |
|------------|---------------|------|------|
| `inputs_not_ready` | dependency | wait / 挂 pending | — |
| `unsupported_mode` / `invalid_param` | configuration | repair_params 一次 | 1 |
| `model_unavailable` | configuration | resolve_model 或 ask | 1 |
| 网络/上传类 retryable | transient | retry 同幂等键 | 3 |
| `generation_failed` | content | ask 或单次 reprompt | 1 |
| 其他 | fatal | report + END | — |

---

## 9. 记忆（P0）

| 存储 | 用途 | P0 |
|------|------|----|
| Checkpointer | 执行进度 | 已有 PostgresSaver，`thread_id=session_id` |
| Memory Store | 偏好 / 项目 canon | 沿用 `update_memory` + 候选列表；Writer 去重合并 |
| Canvas | 资产真相 | 不复制进长期记忆 |

`validate_and_respond` 只写 `memory_candidates`；真正写入走现有异步队列，不阻塞主路径。

---

## 10. 实施任务拆分

### Slice A — 契约与 State（不改行为）

- [x] Pydantic：`UserIntent`, `PlanStep`, `CanvasAction`, `ActionResult`
- [x] `AgentState` 字段扩展 + 旧字段兼容读取
- [x] 单测：序列化 / Ready Set / 幂等键格式

### Slice B — Adapter + 编译管线

- [x] `CanvasToolAdapter` 包装现有 TOOLS
- [x] `compile_actions` + 引用校验（拒绝裸 id）
- [x] 动作日志幂等查重（`agent_actions.idempotency_key`）
- [x] 单测：create→submit 归一化 status；重复 key 不重放

### Slice C — 主图重接线

- [x] 实现/合并 12 节点（可先 alias 旧函数）
- [x] 去掉 `continue → create_plan` 整轮重规划（改为 Ready Set → compile）
- [x] `ask_or_approve` 统一 interrupt；compile 后对本批做风险确认
- [x] `compile → executable_actions` 桥接 executor
- [x] 回归：`test_p0_nodes` / `test_resume_and_compile` / adapter 契约

### Slice D — 事件 Resume

- [x] generation 终态发 `AgentResumeEvent`（HTTP → `/internal/agent/resume`）
- [x] agent 登记 `pending_job` + 消费者 resume + Canvas 真相校验（复用 wakeup 子图）
- [x] clock 仅超时兜底（默认 600s）
- [x] 单测：queued→事件→下游 unlock；失败→recover（基础路径）

### Slice E — 文档与前端标签

- [x] 更新 `docs/agent-runtime-flow.md` 指向本文
- [x] 前端 `TOOL_LABELS` 按 operation 归类展示（可读性，非协议破坏）

---

## 11. 验收用例（P0 DoD）

1. **单图**：用户「生成一张海报」→ 1 个 Image 节点 + queued→事件→succeeded；回复不说「已完成」直到 ready。  
2. **改 Prompt 重跑**：指代「这张图」经 resolve → patch → submit；幂等键防双提交。  
3. **已有链路合成**：rails 进 compose，不搭短剧空壳。  
4. **讨论态**：「这个方案怎么样」→ 不 create/submit。  
5. **约束优先**：用户「9:16、8 秒」；若默认模型不支持 8 秒 → 查兼容模型或 ask，不得改回 4 秒。  
6. **关键帧→视频画幅统一**：同链路 aspectRatio 一致。  
7. **恢复**：进程重启后 checkpoint + 终态事件仍能推进下游。

---

## 12. 工程铁律（摘要）

1. LangGraph 管流程，Canvas 管资产，勿混拓扑。  
2. 写操作必有幂等键。  
3. 异步生成事件恢复，主路径禁止 sleep 轮询。  
4. 计划是结构化 DAG，不是散文 Todo。  
5. 节点/制品引用必须来自真实查询。  
6. 用户明确约束优先于偏好与默认值。  
7. Checkpointer ≠ Memory Store。  
8. 上下文按任务检索，不每轮加载整项目。  
9. 失败先分类再 wait/repair/retry/ask。  
10. P0 验收以状态真实性为主；创作 QA 留 P1。

---

## 13. 开放项（不阻塞 P0 开工）

| 项 | 默认决策 | 可复议 |
|----|----------|--------|
| 事件总线 | Redis 终态推送 + clock 兜底 | 后迁 RocketMQ |
| `sign` / `retry` | Adapter stub | generation API 就绪后接通 |
| 专业子图 | P1 再拆 character/storyboard/compose 编译器 | — |
| 旧 ReAct 代码 | 保留文件但主路径停用，便于对照 | 稳定后删除 |
