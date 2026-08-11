import type { AgentChatMsg, ExecutionStep } from './agentTypes'
import { stepFromPlan, stepFromResult, toolLabel } from './agentTypes'

function appendExecutionStep(steps: ExecutionStep[], step: ExecutionStep): ExecutionStep[] {
  const key = `${step.kind ?? ''}|${step.tool ?? ''}|${step.summary ?? ''}`
  if (steps.some((s) => `${s.kind ?? ''}|${s.tool ?? ''}|${s.summary ?? ''}` === key)) {
    return steps
  }
  return [...steps, step]
}

export function isChatVisibleMessage(m: AgentChatMsg): boolean {
  if (m.role === 'user') return true
  if (m.type && m.type !== 'text') return false
  if (m.content?.trim()) return true
  if ((m.meta?.executionSteps?.length ?? 0) > 0) return true
  return false
}

export function patchLastAssistant(
  messages: AgentChatMsg[],
  patch: (m: AgentChatMsg) => AgentChatMsg,
): AgentChatMsg[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') {
      const next = [...messages]
      next[i] = patch(messages[i])
      return next
    }
  }
  return messages
}

export function applyAgentEvent(
  messages: AgentChatMsg[],
  ev: Record<string, unknown>,
  turnId: string | null,
): AgentChatMsg[] {
  // thinking / reflection：不渲染成「推理过程」长独白；理由走 plan_step.reasoning
  if (ev.type === 'thinking' || ev.type === 'reflection') {
    return messages
  }

  if (ev.type === 'plan_step') {
    const step = stepFromPlan(
      ev.tool as string | undefined,
      String(ev.summary ?? ev.tool ?? ''),
      Date.now(),
      typeof ev.reasoning === 'string' ? ev.reasoning : undefined,
    )
    return patchLastAssistant(messages, (m) => ({
      ...m,
      meta: {
        ...m.meta,
        executionSteps: appendExecutionStep(m.meta?.executionSteps ?? [], step),
      },
    }))
  }

  if (ev.type === 'inline_confirm' && ev.content) {
    const line = String(ev.content)
    return patchLastAssistant(messages, (m) => ({
      ...m,
      content: m.content?.trim() ? `${m.content.trim()}\n${line}` : line,
    }))
  }

  if (ev.type === 'action_result') {
    const tool = ev.tool as string | undefined
    const ok = !!ev.ok
    const data = (ev.data || {}) as Record<string, unknown>
    const detail = ok
      ? tool === 'submit_generation'
        ? '已受理，排队生成中'
        : undefined
      : String(data.error ?? '')
    const step = stepFromResult(
      tool,
      ok,
      `${toolLabel(tool)} ${ok ? '完成' : '失败'}`,
      detail,
    )
    return patchLastAssistant(messages, (m) => ({
      ...m,
      meta: {
        ...m.meta,
        executionSteps: appendExecutionStep(m.meta?.executionSteps ?? [], step),
      },
    }))
  }

  if (ev.type === 'assistant_message' && ev.content) {
    const content = String(ev.content)
    const last = messages[messages.length - 1]
    if (last?.role === 'assistant' && last.content === content) return messages
    const steps = (ev.executionSteps as ExecutionStep[] | undefined) ?? []
    const existing = messages.find((m) => m.id === turnId)
    if (existing) {
      return messages.map((m) =>
        m.id === turnId
          ? {
              ...m,
              content,
              meta: {
                ...m.meta,
                replyType: ev.replyType as string | undefined,
                pipelineStage: ev.pipelineStage as string | undefined,
                suggestions: ev.suggestions as AgentChatMsg['meta'] extends infer M ? M extends { suggestions?: infer S } ? S : never : never,
                nextActions: (ev.nextActions as string[]) ?? m.meta?.nextActions,
                executionSteps: steps.length ? steps : m.meta?.executionSteps,
              },
            }
          : m,
      )
    }
    return [
      ...messages,
      {
        id: turnId ?? Date.now(),
        role: 'assistant',
        type: 'text',
        content,
        meta: {
          replyType: ev.replyType as string | undefined,
          pipelineStage: ev.pipelineStage as string | undefined,
          suggestions: ev.suggestions as AgentChatMsg['meta'] extends { suggestions?: infer S } ? S : never,
          nextActions: ev.nextActions as string[] | undefined,
          executionSteps: steps,
        },
      },
    ]
  }

  if (ev.type === 'task_status') {
    if (ev.silent) {
      const data = (ev.data || {}) as Record<string, unknown>
      return patchLastAssistant(messages, (m) => ({
        ...m,
        meta: {
          ...m.meta,
          taskStatus: {
            taskId: data.task_id as string | undefined,
            status: data.status as string | undefined,
            nodeId: data.node_id as string | undefined,
          },
        },
      }))
    }
    const data = (ev.data || {}) as Record<string, unknown>
    const st = String(data.status ?? '')
    if (st === 'succeeded' || st === 'failed') {
      const content =
        st === 'succeeded'
          ? '✅ 生成完成，产物已写回画布节点。'
          : `❌ 生成失败：${String(data.error || data.error_code || '原因未知')}`
      return [
        ...messages,
        {
          id: `task-${data.task_id ?? Date.now()}`,
          role: 'assistant',
          type: 'text',
          content,
          meta: {
            taskStatus: {
              taskId: data.task_id as string | undefined,
              status: st,
              nodeId: data.node_id as string | undefined,
            },
            nextActions: st === 'succeeded' ? ['图生视频', '换风格重做'] : ['换模型重做', '修改 Prompt'],
          },
        },
      ]
    }
  }

  return messages
}

export function shouldRefreshCanvas(ev: Record<string, unknown>): boolean {
  if (ev.type === 'canvas_changed') return true
  if (ev.type === 'action_result' && ev.ok) {
    const tool = String(ev.tool ?? '')
    return tool === 'create_nodes' || tool === 'connect_nodes'
  }
  if (ev.type === 'task_status') {
    const data = (ev.data || {}) as Record<string, unknown>
    return data.status === 'succeeded'
  }
  return false
}
