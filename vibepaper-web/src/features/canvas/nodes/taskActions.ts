import { api, apiUrl } from '@/lib/api'
import { sid } from '@/lib/ids'
import type { Id } from '@/lib/types'
import { useCanvasStore } from '../canvasStore'

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
  useCanvasStore.getState().updateNodePayload(nodeId, {
    status: 'queued',
    params: {
      ...(useCanvasStore.getState().nodes.find((n) => sid(n.id) === sid(nodeId))?.data.node.params ?? {}),
      ...modelParams,
    },
    currentOutputId: res.taskId,
  })
  useAuth.getState().refreshAccount()
  window.dispatchEvent(new CustomEvent('vp-task-updated', { detail: { taskId: res.taskId, nodeId: sid(nodeId) } }))
  const es = new EventSource(apiUrl(`/tasks/${res.taskId}/events`))
  es.onmessage = (ev) => {
    try {
      const d = JSON.parse(ev.data)
      const status = d.status
      if (!status) return
      const patch: Record<string, unknown> = { status }
      if (status === 'succeeded' && d.outputs?.[0]) {
        const out = d.outputs[0] as { url?: string; meta?: Record<string, unknown> }
        const node = useCanvasStore.getState().nodes.find((n) => sid(n.id) === sid(nodeId))?.data.node
        const url = out.url || (typeof out.meta?.remoteUrl === 'string' ? out.meta.remoteUrl : undefined)
        if (node && url) {
          patch.params = { ...node.params, url, lastOutputUrl: url }
        }
      }
      useCanvasStore.getState().updateNodePayload(nodeId, patch as never)
      if (['succeeded', 'failed', 'cancelled', 'expired'].includes(status)) {
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
