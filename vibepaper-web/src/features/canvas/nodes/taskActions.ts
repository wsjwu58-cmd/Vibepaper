import { api, apiUrl } from '@/lib/api'
import { sid } from '@/lib/ids'
import type { Id, NodePayload } from '@/lib/types'
import { useCanvasStore } from '../canvasStore'

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled', 'expired'])

export function syncExecFields(status: string): Pick<NodePayload, 'status' | 'execStatus'> {
  return { status, execStatus: status }
}

/** 立刻把节点执行态写回画布服务，避免只改本地 store、Agent 摘要仍读到 running。 */
export async function persistNodeExec(nodeId: Id, patch: Partial<NodePayload>): Promise<void> {
  const canvasId = useCanvasStore.getState().canvas?.canvas.id
  if (canvasId == null) return
  try {
    await api(`/canvases/${sid(canvasId)}/nodes/${sid(nodeId)}`, {
      method: 'PUT',
      body: JSON.stringify(patch),
    })
  } catch {
    /* 整表防抖保存仍会带上；这里失败不打断生成回写 */
  }
}

export async function submitNodeTask(
  nodeId: Id,
  modelType: string,
  modelParams: Record<string, unknown>,
  estimatedCost = 8,
) {
  const { useAuth } = await import('@/lib/auth')
  const canvas = useCanvasStore.getState().canvas
  const user = useAuth.getState().user
  const res = await api<{ taskId: string }>('/tasks', {
    method: 'POST',
    idempotencyKey: crypto.randomUUID().replace(/-/g, ''),
    body: JSON.stringify({
      userId: user?.id,
      nodeId,
      canvasId: canvas?.canvas.id,
      modelType,
      modelParams,
      estimatedCost,
      source: 'user',
    }),
  })
  const queued = {
    ...syncExecFields('queued'),
    params: {
      ...(useCanvasStore.getState().nodes.find((n) => sid(n.id) === sid(nodeId))?.data.node.params ?? {}),
      ...modelParams,
    },
    currentOutputId: res.taskId,
  }
  useCanvasStore.getState().updateNodePayload(nodeId, queued)
  void persistNodeExec(nodeId, queued)
  useAuth.getState().refreshAccount()
  window.dispatchEvent(new CustomEvent('vp-task-updated', { detail: { taskId: res.taskId, nodeId: sid(nodeId) } }))
  const es = new EventSource(apiUrl(`/tasks/${res.taskId}/events`))
  es.onmessage = (ev) => {
    try {
      const d = JSON.parse(ev.data)
      const status = d.status as string | undefined
      if (!status) return
      const patch: Record<string, unknown> = { ...syncExecFields(status) }
      if (status === 'succeeded' && d.outputs?.[0]) {
        const out = d.outputs[0] as { url?: string; meta?: Record<string, unknown> }
        const node = useCanvasStore.getState().nodes.find((n) => sid(n.id) === sid(nodeId))?.data.node
        const url = out.url || (typeof out.meta?.remoteUrl === 'string' ? out.meta.remoteUrl : undefined)
        if (node && url) {
          patch.params = { ...node.params, url, lastOutputUrl: url }
        }
      }
      useCanvasStore.getState().updateNodePayload(nodeId, patch as never)
      if (TERMINAL.has(status)) {
        void persistNodeExec(nodeId, patch as Partial<NodePayload>)
        es.close()
        useAuth.getState().refreshAccount()
        window.dispatchEvent(
          new CustomEvent('vp-task-updated', { detail: { taskId: res.taskId, nodeId: sid(nodeId) } }),
        )
      }
    } catch {
      /* ignore */
    }
  }
  es.onerror = () => {
    window.dispatchEvent(new CustomEvent('vp-task-updated', { detail: { taskId: res.taskId, nodeId: sid(nodeId) } }))
  }
  return res.taskId
}
