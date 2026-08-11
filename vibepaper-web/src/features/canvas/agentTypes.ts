export interface ExecutionStep {
  id: string
  kind: 'plan' | 'result' | 'reasoning'
  tool?: string
  label: string
  summary: string
  /** 这步为什么这么做（创作者语言，展示在计划步骤下） */
  reasoning?: string
  ok?: boolean
  detail?: string
}

export interface AgentSuggestion {
  type?: string
  title?: string
  content?: string
  prompt?: string
  nodeParams?: Record<string, unknown>
}

export interface AgentChatMsg {
  id: number | string
  role: string
  type: string
  content: string
  meta?: {
    replyType?: string
    pipelineStage?: string
    suggestions?: AgentSuggestion[]
    nextActions?: string[]
    executionSteps?: ExecutionStep[]
    taskStatus?: { taskId?: string; status?: string; nodeId?: string; modelType?: string }
    requiresConfirmation?: boolean
  }
}

export const TOOL_LABELS: Record<string, string> = {
  get_canvas_summary: '读取画布',
  get_selected_nodes: '读取选中节点',
  list_models: '查询模型',
  search_assets: '查询资源',
  create_nodes: '编辑画布',
  connect_nodes: '编辑画布',
  layout_nodes: '整理画布',
  update_node_config: '修改节点',
  delete_nodes: '删除节点',
  change_model: '切换模型',
  replace_output: '覆盖输出',
  submit_generation: '提交生成',
  check_task_status: '查询任务',
  update_memory: '更新记忆',
  clock: '安排轮询',
  load_skill: '加载 Skill',
}

export function toolLabel(tool?: string): string {
  if (!tool) return '操作'
  return TOOL_LABELS[tool] || tool
}

export function stepFromPlan(
  tool: string | undefined,
  summary: string,
  idx: number,
  reasoning?: string,
): ExecutionStep {
  return {
    id: `plan-${idx}-${tool ?? 'x'}`,
    kind: 'plan',
    tool,
    label: toolLabel(tool),
    summary,
    reasoning: reasoning?.trim() || undefined,
  }
}

export function stepFromThinking(content: string, idx: number): ExecutionStep {
  return {
    id: `reason-${idx}`,
    kind: 'reasoning',
    label: '推理过程',
    summary: content.trim(),
  }
}

export function stepFromResult(
  tool: string | undefined,
  ok: boolean,
  summary: string,
  detail?: string,
  idx = 0,
): ExecutionStep {
  return {
    id: `result-${idx}-${tool ?? 'x'}`,
    kind: 'result',
    tool,
    label: toolLabel(tool),
    summary,
    ok,
    detail,
  }
}
