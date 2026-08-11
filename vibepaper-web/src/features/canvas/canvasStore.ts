import { create } from 'zustand'
import type { Edge, Node } from '@xyflow/react'
import { sid } from '@/lib/ids'
import type { CanvasDetail, EdgePayload, GroupPayload, Id, NodePayload, StackPayload } from '@/lib/types'

export interface FlowNode extends Node {
  data: {
    node: NodePayload
    selected: boolean
    onConfig: (nodeId: string) => void
    models: import('@/lib/types').ModelInfo[]
  }
}

interface CanvasState {
  canvas: CanvasDetail | null
  nodes: FlowNode[]
  edges: Edge[]
  groups: GroupPayload[]
  stacks: StackPayload[]
  dirty: boolean
  saving: boolean
  selectedNodeId: string | null
  /** 双击进入节点编辑（文本等） */
  editingNodeId: string | null
  agentOpen: boolean
  agentPanelWidth: number
  assetOpen: boolean
  /** 画布右上角账户弹层：订阅 / 奖励 / 邀请 / 公告 */
  accountPanel: null | 'subscription' | 'rewards' | 'invites' | 'announcements'
  setCanvas: (c: CanvasDetail) => void
  setNodes: (n: FlowNode[]) => void
  setEdges: (e: Edge[]) => void
  setDirty: (d: boolean) => void
  setSaving: (s: boolean) => void
  selectNode: (id: string | null) => void
  setEditingNodeId: (id: string | null) => void
  setAgentOpen: (v: boolean) => void
  setAgentPanelWidth: (w: number) => void
  setAssetOpen: (v: boolean) => void
  setAccountPanel: (v: CanvasState['accountPanel']) => void
  updateNodePayload: (id: Id, patch: Partial<NodePayload>) => void
  setGroups: (g: GroupPayload[]) => void
  setStacks: (s: StackPayload[]) => void
}

export const useCanvasStore = create<CanvasState>((set) => ({
  canvas: null,
  nodes: [],
  edges: [],
  groups: [],
  stacks: [],
  dirty: false,
  saving: false,
  selectedNodeId: null,
  editingNodeId: null,
  agentOpen: true,
  agentPanelWidth: 380,
  assetOpen: false,
  accountPanel: null,

  setCanvas(c) {
    set({ canvas: c })
  },
  setNodes(n) {
    set({ nodes: n })
  },
  setEdges(e) {
    set({ edges: e })
  },
  setDirty(d) {
    set({ dirty: d })
  },
  setSaving(s) {
    set({ saving: s })
  },
  selectNode(id) {
    const next = id == null ? null : sid(id)
    set((s) => ({
      selectedNodeId: next,
      // 切换选中时退出其他节点的编辑态
      editingNodeId: next && s.editingNodeId === next ? s.editingNodeId : null,
    }))
  },
  setEditingNodeId(id) {
    set({ editingNodeId: id == null ? null : sid(id) })
  },
  setAgentOpen(v) {
    set({ agentOpen: v })
  },
  setAgentPanelWidth(w) {
    set({ agentPanelWidth: w })
  },
  setAssetOpen(v) {
    set({ assetOpen: v })
  },
  setAccountPanel(v) {
    set({ accountPanel: v })
  },
  updateNodePayload(id, patch) {
    set((s) => ({
      dirty: true,
      nodes: s.nodes.map((n) =>
        sid(n.id) === sid(id) ? { ...n, data: { ...n.data, node: { ...n.data.node, ...patch } } } : n,
      ),
    }))
  },
  setGroups(g) {
    set({ groups: g })
  },
  setStacks(s) {
    set({ stacks: s })
  },
}))

/** 从后端负载构建 React Flow 图 */
export function buildFlow(
  detail: CanvasDetail,
  onConfig: (nodeId: string) => void,
): { nodes: FlowNode[]; edges: Edge[] } {
  const nodes: FlowNode[] = detail.nodes.map((n) => ({
    id: sid(n.id),
    type: n.type,
    position: { x: n.x ?? 120, y: n.y ?? 120 },
    data: { node: { ...n, id: sid(n.id) }, selected: false, onConfig, models: [] },
  }))
  const edges: Edge[] = detail.edges.map((e) => ({
    id: sid(e.id),
    source: sid(e.sourceNodeId),
    target: sid(e.targetNodeId),
    animated: false,
    label: e.valid ? undefined : '无效',
    labelStyle: e.valid ? undefined : { fill: '#888', fontSize: 10, fontWeight: 700 },
    style: { stroke: e.valid ? '#93c5fd' : '#c0c0c0', strokeWidth: 1.5 },
    data: { valid: e.valid, edge: e },
  }))
  return { nodes, edges }
}

export function toPayloads(nodes: FlowNode[]): NodePayload[] {
  return nodes.map((n) => ({
    ...n.data.node,
    id: sid(n.id),
    x: n.position.x,
    y: n.position.y,
  }))
}

export function toEdgePayloads(edges: Edge[]): EdgePayload[] {
  return edges.map((e) => {
    const old = (e.data as { edge?: EdgePayload } | undefined)?.edge
    return {
      id: sid(e.id),
      sourceNodeId: sid(e.source),
      sourcePort: old?.sourcePort ?? 'output',
      targetNodeId: sid(e.target),
      targetPort: old?.targetPort ?? 'input',
      valid: old?.valid ?? true,
    }
  })
}
