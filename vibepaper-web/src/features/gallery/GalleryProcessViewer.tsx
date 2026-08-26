import { memo, useEffect, useMemo } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { FileText, Image as ImageIcon, Music, Video } from 'lucide-react'
import type { CanvasDetail, GroupPayload, NodePayload } from '@/lib/types'
import { sid } from '@/lib/ids'
import { nodeMediaUrl } from '@/features/canvas/canvasStore'
import { resolveMediaUrl, useAuthedMediaUrl } from '@/lib/media'
import { isAudioUrl, isVideoUrl } from './galleryUtils'

type GalleryFlowNode = Node<{
  node: NodePayload
  label: string
}>

function typeLabel(type: string): string {
  const map: Record<string, string> = {
    text: 'Text',
    image: 'Image',
    video: 'Video',
    audio: 'Audio',
    compose: 'Compose',
    director: 'Director',
  }
  return map[type] || type
}

function TypeIcon({ type }: { type: string }) {
  if (type === 'video') return <Video size={12} />
  if (type === 'audio') return <Music size={12} />
  if (type === 'text') return <FileText size={12} />
  return <ImageIcon size={12} />
}

const GalleryMediaNode = memo(function GalleryMediaNode(props: NodeProps<GalleryFlowNode>) {
  const node = props.data.node
  const raw = resolveMediaUrl(nodeMediaUrl(node), node.output as Record<string, unknown>) || nodeMediaUrl(node)
  const src = useAuthedMediaUrl(raw)
  const video = node.type === 'video' || isVideoUrl(raw)
  const audio = node.type === 'audio' || isAudioUrl(raw)
  const text =
    node.type === 'text'
      ? String(node.params?.lastOutputText || node.params?.prompt || node.params?.name || '')
      : ''

  return (
    <div className="min-w-[200px] max-w-[280px] overflow-hidden rounded-2xl border border-black/10 bg-white shadow-[0_8px_24px_rgba(0,0,0,0.08)]">
      <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-0 !bg-[#333]" />
      <div className="flex items-center gap-1.5 border-b border-black/6 px-3 py-2 text-[12px] font-bold text-[#333]">
        <TypeIcon type={node.type} />
        <span className="truncate">{props.data.label || typeLabel(node.type)}</span>
      </div>
      <div className="bg-[#111]">
        {video && src ? (
          <video src={src} muted playsInline className="max-h-[180px] w-full object-cover" />
        ) : audio && src ? (
          <div className="flex h-20 items-center justify-center px-3">
            <audio src={src} controls className="w-full" />
          </div>
        ) : text ? (
          <div className="max-h-[160px] overflow-hidden bg-white px-3 py-2.5 text-[12px] leading-relaxed text-[#444]">
            {text}
          </div>
        ) : src ? (
          <img src={src} alt="" className="max-h-[220px] w-full object-cover" />
        ) : (
          <div className="flex h-28 items-center justify-center text-[11px] text-white/40">无预览</div>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-0 !bg-[#333]" />
    </div>
  )
})

const galleryNodeTypes = {
  text: GalleryMediaNode,
  image: GalleryMediaNode,
  video: GalleryMediaNode,
  audio: GalleryMediaNode,
  compose: GalleryMediaNode,
  director: GalleryMediaNode,
  default: GalleryMediaNode,
}

function toSnapshotDetail(snapshot: CanvasDetail | Record<string, unknown>): CanvasDetail {
  const s = snapshot as CanvasDetail
  return {
    canvas: s.canvas,
    nodes: s.nodes ?? [],
    edges: s.edges ?? [],
    groups: (s.groups ?? []) as GroupPayload[],
    stacks: s.stacks ?? [],
  }
}

function buildGalleryFlow(detail: CanvasDetail): {
  nodes: GalleryFlowNode[]
  edges: Edge[]
  groups: GroupPayload[]
} {
  const nodes: GalleryFlowNode[] = detail.nodes.map((n) => ({
    id: sid(n.id),
    type: n.type in galleryNodeTypes ? n.type : 'default',
    position: { x: n.x ?? 120, y: n.y ?? 120 },
    data: {
      node: { ...n, id: sid(n.id) },
      label: String(n.params?.name || typeLabel(n.type)),
    },
    draggable: false,
    selectable: false,
    connectable: false,
  }))
  const edges: Edge[] = detail.edges.map((e) => ({
    id: sid(e.id),
    source: sid(e.sourceNodeId),
    target: sid(e.targetNodeId),
    animated: false,
    style: { stroke: '#1f1f23', strokeWidth: 1.8 },
    type: 'default',
  }))
  return { nodes, edges, groups: detail.groups ?? [] }
}

function FitViewOnce({ nodeCount }: { nodeCount: number }) {
  const { fitView } = useReactFlow()
  useEffect(() => {
    if (nodeCount === 0) return
    const t = window.setTimeout(() => {
      void fitView({ padding: 0.18, duration: 280 })
    }, 60)
    return () => window.clearTimeout(t)
  }, [fitView, nodeCount])
  return null
}

export function GalleryProcessViewer({ snapshot }: { snapshot: CanvasDetail | Record<string, unknown> }) {
  const detail = useMemo(() => toSnapshotDetail(snapshot), [snapshot])
  const flow = useMemo(() => buildGalleryFlow(detail), [detail])

  const groupNodes: Node[] = useMemo(
    () =>
      flow.groups
        .map((g) => {
          const members = g.nodeIds
            .map((nid) => flow.nodes.find((n) => n.id === sid(nid)))
            .filter(Boolean) as GalleryFlowNode[]
          if (members.length === 0) return null
          const minX = Math.min(...members.map((m) => m.position.x)) - 20
          const minY = Math.min(...members.map((m) => m.position.y)) - 36
          const maxX = Math.max(...members.map((m) => m.position.x + 260)) + 20
          const maxY = Math.max(...members.map((m) => m.position.y + 240)) + 20
          return {
            id: `group-${sid(g.id)}`,
            type: 'group',
            position: { x: minX, y: minY },
            style: {
              width: Math.max(200, maxX - minX),
              height: Math.max(120, maxY - minY),
              border: `2px dashed ${g.color || '#93c5fd'}`,
              borderRadius: 18,
              background: `${g.color || '#93c5fd'}14`,
              paddingTop: 28,
            },
            data: { label: g.name || 'Group' },
            zIndex: -1,
            draggable: false,
            selectable: false,
          } as Node
        })
        .filter((g): g is Node => g !== null),
    [flow.groups, flow.nodes],
  )

  const allNodes = useMemo(() => [...groupNodes, ...flow.nodes], [groupNodes, flow.nodes])

  return (
    <ReactFlowProvider>
      <div className="h-full w-full">
        <ReactFlow
          nodes={allNodes}
          edges={flow.edges}
          nodeTypes={galleryNodeTypes as never}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag
          zoomOnScroll
          fitView
          proOptions={{ hideAttribution: true }}
          minZoom={0.2}
          maxZoom={1.6}
          defaultEdgeOptions={{ type: 'default' }}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} color="#cfcfd4" />
          <Controls showInteractive={false} />
          <FitViewOnce nodeCount={flow.nodes.length} />
        </ReactFlow>
      </div>
    </ReactFlowProvider>
  )
}
