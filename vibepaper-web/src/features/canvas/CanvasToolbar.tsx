import {
  MousePointer2,
  Hand,
  Plus,
  Upload,
  Focus,
  Grid2x2,
  LayoutGrid,
  Library,
  Boxes,
  Layers,
  Download,
  Ungroup,
  Palette,
  Type,
  Image,
  Video,
  Mic,
  Clapperboard,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { api, uploadAsset } from '@/lib/api'
import { sid } from '@/lib/ids'
import { useCanvasStore } from './canvasStore'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'

const NODE_MENU = [
  { type: 'text', label: '文本', sub: 'Text', icon: Type },
  { type: 'image', label: '图片', sub: 'Image', icon: Image },
  { type: 'video', label: '视频', sub: 'Video', icon: Video },
  { type: 'audio', label: '音频', sub: 'Audio', icon: Mic },
  { type: 'compose', label: '合成', sub: 'Synthesis', icon: Clapperboard },
  { type: 'director', label: '导演台', sub: 'Director', icon: Clapperboard },
]

const GROUP_COLORS = ['#8b5cf6', '#0ea5e9', '#10b981', '#f59e0b', '#f43f5e', '#111111']

export function CanvasToolbar({
  mode,
  setMode,
  onFitView,
  onAutoLayout,
  onAddNode,
}: {
  mode: 'select' | 'pan'
  setMode: (m: 'select' | 'pan') => void
  onFitView: () => void
  onAutoLayout: () => void
  onAddNode: (type: string) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const setAssetOpen = useCanvasStore((s) => s.setAssetOpen)
  const canvas = useCanvasStore((s) => s.canvas)
  const nodes = useCanvasStore((s) => s.nodes)
  const groups = useCanvasStore((s) => s.groups)
  const stacks = useCanvasStore((s) => s.stacks)
  const setGroups = useCanvasStore((s) => s.setGroups)
  const setStacks = useCanvasStore((s) => s.setStacks)
  const setNodes = useCanvasStore((s) => s.setNodes)
  const setDirty = useCanvasStore((s) => s.setDirty)
  const selected = nodes.filter((n) => n.selected)

  const activeGroup = groups.find((g) => selected.length > 0 && selected.every((n) => g.nodeIds.map(sid).includes(sid(n.id))))
  const activeStack = stacks.find((s) => selected.length > 0 && selected.every((n) => s.nodeIds.map(sid).includes(sid(n.id))))

  const onUpload = async (file: File) => {
    try {
      await uploadAsset(file, undefined, canvas?.canvas.id)
      toastSuccess('上传成功')
      window.dispatchEvent(new Event('vp-assets-updated'))
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const groupSelected = async () => {
    if (!canvas || selected.length < 2) return
    try {
      const g = await api<{ id: string | number; nodeIds: Array<string | number> }>(
        `/canvases/${sid(canvas.canvas.id)}/groups`,
        {
          method: 'POST',
          body: JSON.stringify({ nodeIds: selected.map((n) => sid(n.id)) }),
        },
      )
      setGroups([...groups, { id: sid(g.id), name: '编组', color: '#8b5cf6', layout: 'free', nodeIds: g.nodeIds.map(sid) }])
      toastSuccess('已编组')
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const updateGroup = async (patch: { color?: string; layout?: string; name?: string }) => {
    if (!canvas || !activeGroup) return
    try {
      const g = await api<{ id: string | number; name: string; color: string; layout: string; nodeIds: Array<string | number> }>(
        `/canvases/${sid(canvas.canvas.id)}/groups/${sid(activeGroup.id)}`,
        { method: 'PUT', body: JSON.stringify(patch) },
      )
      setGroups(
        groups.map((item) =>
          sid(item.id) === sid(activeGroup.id)
            ? { ...item, name: g.name, color: g.color, layout: g.layout, nodeIds: g.nodeIds.map(sid) }
            : item,
        ),
      )
      if (patch.layout === 'grid' || patch.layout === 'horizontal') {
        const members = nodes.filter((n) => activeGroup.nodeIds.map(sid).includes(sid(n.id)))
        const originX = Math.min(...members.map((m) => m.position.x))
        const originY = Math.min(...members.map((m) => m.position.y))
        const next = nodes.map((n) => {
          const idx = activeGroup.nodeIds.map(sid).indexOf(sid(n.id))
          if (idx < 0) return n
          if (patch.layout === 'grid') {
            return { ...n, position: { x: originX + (idx % 3) * 330, y: originY + Math.floor(idx / 3) * 280 } }
          }
          return { ...n, position: { x: originX + idx * 330, y: originY } }
        })
        setNodes(next)
        setDirty(true)
      }
      toastSuccess('编组已更新')
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const ungroup = async () => {
    if (!canvas || !activeGroup) return
    try {
      await api(`/canvases/${sid(canvas.canvas.id)}/groups/${sid(activeGroup.id)}`, { method: 'DELETE' })
      setGroups(groups.filter((g) => sid(g.id) !== sid(activeGroup.id)))
      toastSuccess('已取消编组')
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const stackSelected = async () => {
    if (!canvas || selected.length < 2) return
    try {
      const s = await api<{ id: string | number; nodeIds: Array<string | number> }>(
        `/canvases/${sid(canvas.canvas.id)}/stacks`,
        {
          method: 'POST',
          body: JSON.stringify({ nodeIds: selected.map((n) => sid(n.id)) }),
        },
      )
      setStacks([...stacks, { id: sid(s.id), collapsed: true, nodeIds: s.nodeIds.map(sid) }])
      const ids = s.nodeIds.map(sid)
      const base = nodes.find((n) => sid(n.id) === ids[0])
      if (base) {
        setNodes(
          nodes.map((n) => {
            const idx = ids.indexOf(sid(n.id))
            if (idx <= 0) return n
            return { ...n, position: { x: base.position.x + idx * 12, y: base.position.y + idx * 12 } }
          }),
        )
        setDirty(true)
      }
      toastSuccess('已堆叠')
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const expandStack = async () => {
    if (!canvas || !activeStack) return
    try {
      await api(`/canvases/${sid(canvas.canvas.id)}/stacks/${sid(activeStack.id)}`, {
        method: 'PUT',
        body: JSON.stringify({ collapsed: false }),
      })
      const ids = activeStack.nodeIds.map(sid)
      const base = nodes.find((n) => sid(n.id) === ids[0])
      if (base) {
        setNodes(
          nodes.map((n) => {
            const idx = ids.indexOf(sid(n.id))
            if (idx < 0) return n
            return { ...n, position: { x: base.position.x + (idx % 3) * 330, y: base.position.y + Math.floor(idx / 3) * 280 } }
          }),
        )
        setDirty(true)
      }
      setStacks(stacks.map((s) => (sid(s.id) === sid(activeStack.id) ? { ...s, collapsed: false } : s)))
      toastSuccess('堆叠已展开')
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const unstack = async () => {
    if (!canvas || !activeStack) return
    try {
      await api(`/canvases/${sid(canvas.canvas.id)}/stacks/${sid(activeStack.id)}`, { method: 'DELETE' })
      setStacks(stacks.filter((s) => sid(s.id) !== sid(activeStack.id)))
      toastSuccess('已取消堆叠')
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const downloadSelected = () => {
    const urls = selected
      .map((n) => n.data.node.params.url as string | undefined)
      .filter((u): u is string => Boolean(u))
    if (urls.length === 0) {
      toastError('选中节点暂无本地素材 URL')
      return
    }
    urls.forEach((url, i) => {
      const a = document.createElement('a')
      a.href = url
      a.download = `selected-${i + 1}`
      a.target = '_blank'
      a.click()
    })
    toastSuccess(`已触发下载 ${urls.length} 个内容`)
  }

  return (
    <div className="flex flex-col gap-1 rounded-[24px] border border-white/10 bg-[#1a1c24]/95 px-2 py-3 shadow-[0_16px_48px_rgba(0,0,0,0.28)] backdrop-blur-md">
      <ToolButton active={mode === 'select'} onClick={() => setMode('select')} title="选择模式">
        <MousePointer2 size={17} />
      </ToolButton>
      <ToolButton active={mode === 'pan'} onClick={() => setMode('pan')} title="抓手模式">
        <Hand size={17} />
      </ToolButton>

      <div className="mx-2 my-1 h-px bg-white/10" />

      <div className="relative">
        <ToolButton active={menuOpen} onClick={() => setMenuOpen((v) => !v)} title="添加节点">
          <Plus size={18} />
        </ToolButton>
        {menuOpen && (
          <div className="absolute left-[58px] top-0 z-50 w-[220px] rounded-[20px] border border-white/10 bg-[#1a1c24]/98 p-3 shadow-[0_24px_72px_rgba(0,0,0,0.35)] backdrop-blur-md">
            <p className="mb-2 px-1 text-[11px] font-bold tracking-wide text-[#8e929c]">添加节点</p>
            {NODE_MENU.map((t) => {
              const Icon = t.icon
              return (
                <button
                  key={t.type}
                  onClick={() => {
                    onAddNode(t.type)
                    setMenuOpen(false)
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition hover:bg-white/8"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-[#2d303a] text-white/90">
                    <Icon size={17} strokeWidth={1.6} />
                  </span>
                  <div>
                    <p className="text-[14px] font-semibold text-white">{t.label}</p>
                    <p className="text-[11px] text-[#8e929c]">{t.sub}</p>
                  </div>
                </button>
              )
            })}
            <div className="mx-1 my-2 h-px bg-white/10" />
            <button
              onClick={() => fileRef.current?.click()}
              className="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition hover:bg-white/8"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-[#2d303a] text-white/90">
                <Upload size={17} strokeWidth={1.6} />
              </span>
              <div>
                <p className="text-[14px] font-semibold text-white">上传</p>
                <p className="text-[11px] text-[#8e929c]">Upload</p>
              </div>
            </button>
          </div>
        )}
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/*,video/*,audio/*"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
      />

      <ToolButton onClick={() => setAssetOpen(true)} title="素材库">
        <Library size={17} />
      </ToolButton>

      <div className="mx-2 my-1 h-px bg-white/10" />

      <ToolButton onClick={onFitView} title="聚焦视图">
        <Focus size={17} />
      </ToolButton>
      <ToolButton onClick={onAutoLayout} title="网格整理">
        <Grid2x2 size={17} />
      </ToolButton>

      {selected.length >= 2 && (
        <>
          <div className="mx-2 my-1 h-px bg-white/10" />
          <ToolButton onClick={groupSelected} title="编组">
            <Boxes size={17} />
          </ToolButton>
          <ToolButton onClick={stackSelected} title="堆叠">
            <Layers size={17} />
          </ToolButton>
          <ToolButton onClick={downloadSelected} title="下载选中内容">
            <Download size={17} />
          </ToolButton>
        </>
      )}

      {activeGroup && (
        <>
          <div className="mx-2 my-1 h-px bg-white/10" />
          <ToolButton onClick={() => void updateGroup({ layout: 'grid' })} title="网格排列">
            <LayoutGrid size={17} />
          </ToolButton>
          <ToolButton onClick={() => void updateGroup({ layout: 'horizontal' })} title="水平排列">
            <Boxes size={17} />
          </ToolButton>
          <ToolButton
            onClick={() => {
              const next = GROUP_COLORS[(GROUP_COLORS.indexOf(activeGroup.color) + 1) % GROUP_COLORS.length]
              void updateGroup({ color: next })
            }}
            title="编组颜色"
          >
            <Palette size={17} />
          </ToolButton>
          <ToolButton onClick={() => void ungroup()} title="取消编组">
            <Ungroup size={17} />
          </ToolButton>
        </>
      )}

      {activeStack && (
        <>
          <div className="mx-2 my-1 h-px bg-white/10" />
          <ToolButton onClick={() => void expandStack()} title="展开堆叠">
            <Layers size={17} />
          </ToolButton>
          <ToolButton onClick={() => void unstack()} title="取消堆叠">
            <Ungroup size={17} />
          </ToolButton>
        </>
      )}
    </div>
  )
}

function ToolButton({
  active,
  title,
  onClick,
  children,
}: {
  active?: boolean
  title: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        'flex h-10 w-10 items-center justify-center rounded-full transition',
        active
          ? 'bg-white text-[#1a1c24]'
          : 'text-white/75 hover:bg-white/10 hover:text-white',
      )}
    >
      {children}
    </button>
  )
}
