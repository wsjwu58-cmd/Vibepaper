import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Bot,
  X,
  Send,
  Settings2,
  BookOpen,
  Plus,
  History,
  BarChart3,
  Upload,
  Square,
  SquarePlus,
  Puzzle,
  SlidersHorizontal,
  Lightbulb,
  ListTree,
  Megaphone,
} from 'lucide-react'
import { api, apiUrl } from '@/lib/api'
import { parseJsonPreserveIds } from '@/lib/ids'
import { useAuth } from '@/lib/auth'
import type { MemoryView, ModelInfo, SkillView } from '@/lib/types'
import { ModelPicker } from '@/components/ui/ModelPicker'
import { useCanvasStore } from './canvasStore'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import type { AgentChatMsg, AgentSuggestion, ExecutionStep } from './agentTypes'
import { AgentExecutionRecord, AgentNextActions, AgentTaskBadge } from './AgentExecutionRecord'
import { applyAgentEvent, isChatVisibleMessage, shouldRefreshCanvas } from './agentEventHandlers'

const AGENT_PANEL_DEFAULT_WIDTH = 380
const AGENT_PANEL_MIN_WIDTH = 300
const AGENT_PANEL_MAX_WIDTH = 720

const SUGGESTIONS = [
  { icon: ListTree, text: '梳理画布信息，提炼核心创意与明确的下一步' },
  { icon: Megaphone, text: '基于画布素材，写出鲜明有记忆点的品牌文案' },
  { icon: Lightbulb, text: '延展画布内容，提出三个差异化可落地的方向' },
] as const

interface Suggestion extends AgentSuggestion {}

export function AgentLauncher({ onOpen }: { onOpen: () => void }) {
  return (
    <span className="absolute bottom-4 right-4 z-20 inline-flex" title="打开对话">
      <button
        type="button"
        aria-label="打开对话"
        onClick={onOpen}
        className="group/agent-launcher relative z-0 inline-flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-zinc-300/50 bg-white p-1 text-xs text-zinc-950 shadow-[0_4px_12px_rgb(0_0_0_/_0.05)] transition-all duration-300 hover:border-zinc-400 hover:bg-white"
      >
        <img alt="" className="size-8 object-contain" src="/paper-agent.svg" />
      </button>
    </span>
  )
}

export function AgentPanel() {
  const open = useCanvasStore((s) => s.agentOpen)
  const setOpen = useCanvasStore((s) => s.setAgentOpen)
  const setAgentPanelWidth = useCanvasStore((s) => s.setAgentPanelWidth)
  const canvas = useCanvasStore((s) => s.canvas)
  const preferences = useAuth((s) => s.preferences)
  const updatePreferences = useAuth((s) => s.updatePreferences)
  const [width, setWidth] = useState(AGENT_PANEL_DEFAULT_WIDTH)
  const [resizing, setResizing] = useState(false)
  const resizeStartRef = useRef<{ x: number; w: number } | null>(null)
  const [textModels, setTextModels] = useState<ModelInfo[]>([])
  const [agentModel, setAgentModel] = useState(preferences?.defaultTextModel || 'deepseek-v4-pro')
  const [sessionId, setSessionId] = useState<string | number | null>(null)
  const [sessionTitle, setSessionTitle] = useState('新对话')
  const [messages, setMessages] = useState<AgentChatMsg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [tab, setTab] = useState<'chat' | 'pref' | 'skills' | 'usage' | 'history'>('chat')
  const [selectedNodes, setSelectedNodes] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const sseAbortRef = useRef<AbortController | null>(null)
  const sendAbortRef = useRef<AbortController | null>(null)
  const turnIdRef = useRef<string | null>(null)
  const seenTaskIdsRef = useRef<Set<string>>(new Set())
  const canvasId = canvas?.canvas.id

  useEffect(() => {
    setAgentPanelWidth(open ? width : 0)
  }, [open, width, setAgentPanelWidth])

  useEffect(() => {
    if (preferences?.defaultTextModel) {
      setAgentModel(preferences.defaultTextModel)
    }
  }, [preferences?.defaultTextModel])

  useEffect(() => {
    void api<{ items: ModelInfo[] }>('/models')
      .then((r) => setTextModels(r.items.filter((m) => m.modelType === 'text')))
      .catch(() => undefined)
  }, [])

  const onResizePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return
      e.preventDefault()
      try {
        e.currentTarget.setPointerCapture?.(e.pointerId)
      } catch {
        /* synthetic pointer events may lack an active pointer */
      }
      resizeStartRef.current = { x: e.clientX, w: width }
      setResizing(true)
    },
    [width],
  )

  const onResizePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const start = resizeStartRef.current
    if (!start) return
    const dx = start.x - e.clientX
    const next = Math.min(AGENT_PANEL_MAX_WIDTH, Math.max(AGENT_PANEL_MIN_WIDTH, start.w + dx))
    setWidth(next)
  }, [])

  const endResize = useCallback(() => {
    resizeStartRef.current = null
    setResizing(false)
  }, [])

  const onAgentModelChange = (name: string) => {
    setAgentModel(name)
    void updatePreferences({ defaultTextModel: name }).catch(() => undefined)
  }

  const handleBackgroundEvent = (ev: Record<string, unknown>) => {
    if (shouldRefreshCanvas(ev)) {
      window.dispatchEvent(new Event('vp-agent-executed'))
    }
    if (ev.type === 'task_status') {
      const data = (ev.data || {}) as Record<string, unknown>
      const tid = String(data.task_id ?? '')
      if (ev.silent) {
        setMessages((m) => applyAgentEvent(m, ev, turnIdRef.current))
        return
      }
      if (tid && seenTaskIdsRef.current.has(tid)) return
      if (tid) seenTaskIdsRef.current.add(tid)
    }
    if (ev.type === 'assistant_message') {
      const content = String(ev.content ?? '')
      setMessages((prev) => {
        if (prev.some((m) => m.role === 'assistant' && m.content === content)) return prev
        return applyAgentEvent(prev, ev, turnIdRef.current)
      })
      if (Array.isArray(ev.nextActions)) {
        /* next actions live on message meta */
      }
      return
    }
    setMessages((m) => applyAgentEvent(m, ev, turnIdRef.current))
  }

  const loadSessionQuiet = async (id: string | number, title?: string) => {
    const res = await api<{ items: AgentChatMsg[] }>(`/agent/sessions/${id}/messages`)
    setSessionId(id)
    setSessionTitle(title || `对话 #${id}`)
    setMessages(
      res.items
        .map((m) => ({ ...m, type: m.type || 'text', meta: (m.meta as AgentChatMsg['meta']) ?? {} }))
        .filter(isChatVisibleMessage),
    )
    setSuggestions([])
  }

  const ensureSession = async (forceNew = false) => {
    if (!canvas?.canvas.id) {
      throw new Error('画布尚未加载，请稍后再试')
    }
    if (!forceNew && sessionId) return sessionId

    // 打开画布时恢复该画布最近一次对话，而不是总是新建
    if (!forceNew) {
      try {
        const list = await api<{
          items: Array<{ sessionId: string | number; title: string; canvasId?: string | number }>
        }>(`/agent/sessions?canvasId=${encodeURIComponent(String(canvas.canvas.id))}`)
        const latest = list.items?.[0]
        if (latest?.sessionId != null) {
          await loadSessionQuiet(latest.sessionId, latest.title)
          return latest.sessionId
        }
      } catch {
        /* 列表失败则回退创建 */
      }
    }

    const s = await api<{ sessionId: string | number; title?: string; canvasId?: string | number }>('/agent/sessions', {
      method: 'POST',
      body: JSON.stringify({
        canvasId: String(canvas.canvas.id),
        title: '新对话',
      }),
    })
    setSessionId(s.sessionId)
    setSessionTitle(s.title || '新对话')
    setMessages([])
    setSuggestions([])
    return s.sessionId
  }

  useEffect(() => {
    if (!open) return
    if (!canvas?.canvas.id) return
    if (sessionId) return
    void ensureSession().catch((e) => toastError((e as Error).message))
  }, [open, sessionId, canvas?.canvas.id])

  useEffect(() => {
    if (!open || !sessionId) return
    const ac = new AbortController()
    sseAbortRef.current = ac
    void (async () => {
      try {
        const res = await fetch(apiUrl(`/agent/sessions/${sessionId}/events`), {
          headers: { Authorization: `Bearer ${localStorage.getItem('vp_access') ?? ''}` },
          signal: ac.signal,
        })
        if (!res.ok || !res.body) return
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const parts = buf.split('\n\n')
          buf = parts.pop() ?? ''
          for (const part of parts) {
            const dataLine = part.split('\n').find((l) => l.startsWith('data: '))
            if (!dataLine) continue
            const ev = parseJsonPreserveIds(dataLine.slice(6)) as Record<string, unknown>
            if (ev.type === 'task_status' || ev.type === 'assistant_message' || ev.type === 'canvas_changed') {
              handleBackgroundEvent(ev)
            }
          }
        }
      } catch {
        /* closed or network */
      }
    })()
    return () => {
      ac.abort()
      sseAbortRef.current = null
    }
  }, [open, sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  useEffect(() => {
    const pick = (nodes: { selected?: boolean; id: string | number }[]) =>
      nodes.filter((n) => n.selected).map((n) => String(n.id))
    setSelectedNodes(pick(useCanvasStore.getState().nodes))
    const unsub = useCanvasStore.subscribe((s) => {
      setSelectedNodes(pick(s.nodes))
    })
    return unsub
  }, [])

  const loadSession = async (id: string | number, title?: string) => {
    try {
      await loadSessionQuiet(id, title)
      setTab('chat')
      toastSuccess('已切换会话')
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const addSuggestionsToCanvas = async (items: Suggestion[]) => {
    if (!canvasId || items.length === 0) return
    try {
      for (const [i, s] of items.entries()) {
        const type = s.type === 'image' || s.type === 'video' || s.type === 'audio' ? s.type : 'text'
        await api(`/canvases/${canvasId}/nodes`, {
          method: 'POST',
          body: JSON.stringify({
            type,
            x: 180 + i * 40,
            y: 140 + i * 30,
            params: {
              prompt: s.prompt || s.content || s.title || '',
              title: s.title,
              ...(s.nodeParams || {}),
            },
          }),
        })
      }
      toastSuccess(`已添加 ${items.length} 个节点到画布`)
      window.dispatchEvent(new Event('vp-agent-executed'))
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const stop = () => {
    sendAbortRef.current?.abort()
    sendAbortRef.current = null
    setBusy(false)
  }

  const processStreamEvent = (ev: Record<string, unknown>) => {
    if (shouldRefreshCanvas(ev)) {
      window.dispatchEvent(new Event('vp-agent-executed'))
    }
    if (ev.type === 'assistant_message') {
      if (Array.isArray(ev.suggestions)) setSuggestions(ev.suggestions as Suggestion[])
    }
    setMessages((m) => applyAgentEvent(m, ev, turnIdRef.current))
  }

  const send = async () => {
    const content = input.trim()
    if (!content || busy) return
    const isFirstUserTurn = !messages.some((m) => m.role === 'user')
    setInput('')
    setBusy(true)
    setSuggestions([])
    // 对话历史命名：首条用户语句
    if (
      isFirstUserTurn &&
      (!sessionTitle || sessionTitle === '新对话' || sessionTitle === '画布对话' || sessionTitle.startsWith('对话 '))
    ) {
      setSessionTitle(content.slice(0, 48))
    }
    const turnId = `turn-${Date.now()}`
    turnIdRef.current = turnId
    setMessages((m) => [
      ...m,
      { id: Date.now(), role: 'user', type: 'text', content },
      {
        id: turnId,
        role: 'assistant',
        type: 'text',
        content: '',
        meta: { executionSteps: [] as ExecutionStep[] },
      },
    ])
    const ac = new AbortController()
    sendAbortRef.current = ac
    try {
      const sid = await ensureSession()
      if (ac.signal.aborted) return
      const res = await fetch(apiUrl(`/agent/sessions/${sid}/messages`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('vp_access') ?? ''}`,
        },
        body: JSON.stringify({
          content,
          selectedNodeIds: selectedNodes,
          canvasId: canvas?.canvas.id != null ? String(canvas.canvas.id) : undefined,
        }),
        signal: ac.signal,
      })
      if (!res.ok) throw new Error(`Agent 请求失败 (${res.status})`)
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (reader) {
        if (ac.signal.aborted) {
          await reader.cancel().catch(() => undefined)
          break
        }
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          const dataLine = part.split('\n').find((l) => l.startsWith('data: '))
          if (!dataLine) continue
          const ev = parseJsonPreserveIds(dataLine.slice(6)) as Record<string, unknown>
          if (ev.type === 'done') continue
          processStreamEvent(ev)
        }
      }
      if (ac.signal.aborted) return
      window.dispatchEvent(new Event('vp-agent-executed'))
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') return
      toastError((e as Error).message)
    } finally {
      if (sendAbortRef.current === ac) sendAbortRef.current = null
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <aside
        aria-hidden
        className="pointer-events-none relative z-30 h-full flex-none overflow-hidden"
        style={{ width: 0 }}
      />
    )
  }

  return (
    <aside
      aria-hidden={!open}
      className={cn(
        'relative z-30 h-full flex-none bg-[var(--canvas-surface)] text-[var(--canvas-text)] shadow-xl shadow-black/20 backdrop-blur-md',
        resizing ? 'duration-0' : 'transition-[width] duration-200 ease-out',
        'overflow-visible border-l border-[var(--canvas-border)]',
      )}
      style={{ width }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        className={cn(
          'group absolute -left-1.5 top-0 z-40 h-full w-3 cursor-col-resize touch-none select-none',
          resizing && 'is-resizing',
        )}
        onPointerDown={onResizePointerDown}
        onPointerMove={onResizePointerMove}
        onPointerUp={endResize}
        onPointerCancel={endResize}
        onDoubleClick={() => setWidth(AGENT_PANEL_DEFAULT_WIDTH)}
      >
        <span
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-0 h-full w-[3px] -translate-x-1/2 bg-transparent transition-colors group-hover:bg-[var(--canvas-border-strong)] group-active:bg-[var(--canvas-border-strong)]"
        />
      </div>
      <div className="flex h-full flex-col" style={{ width }}>
      <div className="flex items-center justify-between px-4 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#111] text-white">
            <Bot size={16} />
          </span>
          <div>
            <p className="max-w-[140px] truncate text-[14px] font-bold text-[#111]">{sessionTitle}</p>
            <p className="text-[11px] text-[#999]">Paper Agent</p>
          </div>
        </div>
        <div className="flex items-center gap-0.5">
          {tab === 'chat' ? (
            <button
              type="button"
              onClick={() => void ensureSession(true).then(() => toastSuccess('已创建新对话'))}
              title="新对话"
              className="rounded-full p-2 text-[#888] transition hover:bg-black/[0.04]"
            >
              <SquarePlus size={16} />
            </button>
          ) : (
            <NavIcon tab="chat" current={tab} set={setTab} icon={Bot} label="对话" />
          )}
          <NavIcon tab="skills" current={tab} set={setTab} icon={BookOpen} label="Skills" />
          <NavIcon tab="history" current={tab} set={setTab} icon={History} label="历史" />
          <NavIcon tab="usage" current={tab} set={setTab} icon={BarChart3} label="用量" />
          <NavIcon tab="pref" current={tab} set={setTab} icon={Settings2} label="偏好" />
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="ml-1 rounded-full p-2 text-[#888] hover:bg-black/[0.04]"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {tab === 'chat' && (
        <div className="flex min-h-0 flex-1 flex-col bg-[var(--canvas-surface)]">
          <div className="relative min-h-0 flex-1 overflow-y-auto bg-transparent px-3.5 pb-8 pt-3.5">
            {selectedNodes.length > 0 && (
              <p className="mb-3 rounded-full bg-[#f2f2f2] px-3 py-1.5 text-[11px] font-semibold text-[#555]">
                已选中 {selectedNodes.length} 个节点，Agent 将基于这些节点操作
              </p>
            )}

            {messages.length === 0 && (
              <div className="flex h-full min-h-[220px] items-center justify-center px-4 py-8 text-center">
                <div className="w-full max-w-[560px]">
                  <img alt="" className="mx-auto mb-9 h-32 w-auto object-contain" src="/paper-agent.svg" />
                  <p className="text-sm font-medium text-[var(--canvas-text-strong)]">Paper Agent</p>
                  <p className="mt-1.5 text-xs leading-relaxed text-[var(--canvas-muted)]">
                    让 Paper Agent 理解整张画布的脉络，把零散灵感推进为清晰、可执行的创作方案。
                  </p>
                  <div className="-mx-2 mt-4 grid grid-cols-[repeat(auto-fit,minmax(92px,1fr))] gap-2">
                    {SUGGESTIONS.map(({ icon: Icon, text }) => (
                      <button
                        key={text}
                        type="button"
                        onClick={() => setInput(text)}
                        className="flex min-h-24 flex-col items-start justify-center gap-2 rounded-xl border border-[var(--canvas-border)] bg-[var(--canvas-surface-muted)] px-2.5 py-3 text-left text-xs leading-snug text-[var(--canvas-text)] transition-colors hover:border-[var(--canvas-border-strong)] hover:bg-[var(--canvas-hover)]"
                      >
                        <Icon size={16} strokeWidth={2} className="size-4 flex-none self-center text-[var(--canvas-muted)]" />
                        <span>{text}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {messages.filter(isChatVisibleMessage).map((m) => (
              <div key={m.id} className={`mb-3 flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={cn(
                    'max-w-[92%] px-3.5 py-2.5 text-[13px] leading-relaxed',
                    m.role === 'user'
                      ? 'rounded-[18px] whitespace-pre-line bg-[#efefef] text-[#111]'
                      : 'text-[#333]',
                  )}
                >
                  {m.content ? (
                    <p className="whitespace-pre-line">{m.content}</p>
                  ) : busy && m.role === 'assistant' ? (
                    <p className="text-[12px] text-[#999]">正在编排…</p>
                  ) : null}
                  {m.meta?.executionSteps && m.meta.executionSteps.length > 0 && (
                    <AgentExecutionRecord steps={m.meta.executionSteps} defaultOpen />
                  )}
                  <AgentTaskBadge status={m.meta?.taskStatus?.status} taskId={m.meta?.taskStatus?.taskId} />
                  {m.meta?.pipelineStage && m.role === 'assistant' && (
                    <p className="mt-2 text-[10px] font-medium text-[#aaa]">
                      创作阶段 · {m.meta.pipelineStage}
                    </p>
                  )}
                  {m.meta?.nextActions && m.meta.nextActions.length > 0 && (
                    <AgentNextActions
                      actions={m.meta.nextActions}
                      onPick={(text) => {
                        setInput(text)
                      }}
                    />
                  )}
                </div>
              </div>
            ))}

            {suggestions.length > 0 && (
              <div className="mb-3 space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-[12px] font-bold text-[#333]">建议卡片</p>
                  <button
                    type="button"
                    onClick={() => void addSuggestionsToCanvas(suggestions)}
                    className="text-[11px] font-bold text-[#111] underline underline-offset-2"
                  >
                    全部添加到画布
                  </button>
                </div>
                {suggestions.map((s, idx) => (
                  <div key={`${s.title ?? 's'}-${idx}`} className="rounded-[16px] border border-black/8 bg-white p-3">
                    <p className="text-[12px] font-bold text-[#111]">{s.title || `建议 ${idx + 1}`}</p>
                    <p className="mt-1 text-[12px] leading-relaxed text-[#555]">{s.content || s.prompt || ''}</p>
                    <button
                      type="button"
                      onClick={() => void addSuggestionsToCanvas([s])}
                      className="mt-2 text-[11px] font-bold text-[#111] underline underline-offset-2"
                    >
                      添加到画布
                    </button>
                  </div>
                ))}
              </div>
            )}

            {busy && (
              <p className="mb-1 flex items-center gap-1.5 text-[12px] font-medium text-[#888]">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                正在工作
              </p>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="shrink-0">
            <form
              className="shrink-0 px-3 pb-3 pt-0"
              onSubmit={(e) => {
                e.preventDefault()
                if (!busy) void send()
              }}
            >
              <div className="relative rounded-lg border border-[var(--canvas-border)] bg-[color-mix(in_srgb,var(--canvas-surface)_88%,var(--canvas-surface-muted))] shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition-colors focus-within:border-[var(--canvas-border-strong)] focus-within:ring-1 focus-within:ring-[var(--canvas-border)]">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      if (!busy) void send()
                    }
                  }}
                  rows={3}
                  placeholder="描述创意或需求，@ 引用参考，/ 选择 Skill"
                  disabled={busy}
                  className="block min-h-[72px] w-full resize-none bg-transparent px-3 pb-12 pt-3 text-[13px] leading-relaxed text-[var(--canvas-text)] outline-none placeholder:text-[var(--canvas-muted-soft)] disabled:opacity-60"
                />
                <div className="absolute bottom-2 left-2 right-2 z-10 flex min-w-0 items-center gap-1.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 items-center gap-0.5">
                      <button
                        type="button"
                        aria-label="添加 Skill"
                        title="添加 Skill"
                        onClick={() => setTab('skills')}
                        className="relative flex size-8 shrink-0 items-center justify-center rounded-lg text-[var(--canvas-muted)] transition-colors hover:bg-[var(--canvas-hover)] hover:text-[var(--canvas-text)]"
                      >
                        <Puzzle size={16} strokeWidth={2} className="size-4" />
                      </button>
                      <button
                        type="button"
                        aria-label="生成偏好"
                        title="生成偏好"
                        onClick={() => setTab('pref')}
                        className="relative flex size-8 items-center justify-center rounded-lg text-[var(--canvas-muted)] transition-colors hover:bg-[var(--canvas-hover)] hover:text-[var(--canvas-text)]"
                      >
                        <SlidersHorizontal size={16} strokeWidth={2} className="size-4" />
                      </button>
                    </div>
                  </div>
                  <div className="min-w-0 shrink">
                    <ModelPicker
                      composer
                      models={
                        textModels.length
                          ? textModels
                          : [
                              {
                                name: agentModel,
                                displayName: agentModel,
                                enabled: true,
                                basePrice: 0,
                                modelType: 'text',
                                id: agentModel,
                              } as ModelInfo,
                            ]
                      }
                      value={agentModel}
                      onChange={onAgentModelChange}
                    />
                  </div>
                  {busy ? (
                    <button
                      type="button"
                      onClick={stop}
                      title="停止"
                      aria-label="停止"
                      className="inline-flex size-7 items-center justify-center rounded-lg bg-[var(--canvas-active)] text-[var(--canvas-active-text)] transition-colors"
                    >
                      <Square size={12} strokeWidth={2.5} />
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={!input.trim()}
                      aria-label="发送"
                      className={cn(
                        'inline-flex size-7 items-center justify-center rounded-lg transition-colors',
                        input.trim()
                          ? 'bg-[var(--canvas-active)] text-[var(--canvas-active-text)] hover:opacity-90'
                          : 'cursor-not-allowed bg-[var(--canvas-surface-muted)] text-[var(--canvas-muted-soft)]',
                      )}
                    >
                      <Send size={14} strokeWidth={2} className="size-3.5" />
                    </button>
                  )}
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {tab === 'pref' && <PreferencesTab />}
      {tab === 'skills' && <SkillsTab sessionId={sessionId} />}
      {tab === 'usage' && <UsageTab sessionId={sessionId} />}
      {tab === 'history' && (
        <HistoryTab
          sessionId={sessionId}
          canvasId={canvas?.canvas.id}
          onOpenSession={loadSession}
          onImported={(id) => void loadSession(id)}
        />
      )}
      </div>
    </aside>
  )
}

function NavIcon({
  tab,
  current,
  set,
  icon: Icon,
  label,
}: {
  tab: 'chat' | 'pref' | 'skills' | 'usage' | 'history'
  current: string
  set: (t: 'chat' | 'pref' | 'skills' | 'usage' | 'history') => void
  icon: React.ComponentType<{ size?: number }>
  label: string
}) {
  return (
    <button
      type="button"
      onClick={() => set(tab)}
      title={label}
      className={cn(
        'rounded-full p-2 transition',
        current === tab ? 'bg-black/8 text-[#111]' : 'text-[#888] hover:bg-black/[0.04]',
      )}
    >
      <Icon size={16} />
    </button>
  )
}

function PreferencesTab() {
  const preferences = useAuth((s) => s.preferences)
  const updatePreferences = useAuth((s) => s.updatePreferences)
  const [models, setModels] = useState<ModelInfo[]>([])
  const [pref, setPref] = useState({
    text: preferences?.defaultTextModel || 'deepseek-v4-pro',
    image: preferences?.defaultImageModel || 'doubao-seedream-5-0-260128',
    video: preferences?.defaultVideoModel || 'doubao-seedance-1-0-pro-250528',
    resolution: preferences?.defaultResolution || '1024x1024',
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    void api<{ items: ModelInfo[] }>('/models')
      .then((r) => setModels(r.items))
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    setPref({
      text: preferences?.defaultTextModel || 'deepseek-v4-pro',
      image: preferences?.defaultImageModel || 'doubao-seedream-5-0-260128',
      video: preferences?.defaultVideoModel || 'doubao-seedance-1-0-pro-250528',
      resolution: preferences?.defaultResolution || '1024x1024',
    })
  }, [preferences])

  const options = (type: string) => models.filter((m) => m.modelType === type)

  return (
    <div className="flex-1 space-y-3 overflow-auto p-4">
      <p className="text-[13px] font-bold text-[#111]">偏好设置</p>
      <p className="text-[11px] leading-relaxed text-[#888]">
        Agent 对话默认走 DeepSeek；下方为节点生成默认模型。
      </p>
      {(
        [
          ['text', '文本模型'],
          ['image', '图片模型'],
          ['video', '视频模型'],
        ] as const
      ).map(([key, label]) => (
        <div key={key}>
          <p className="mb-1 text-[12px] font-bold text-[#555]">{label}</p>
          <ModelPicker
            models={
              options(key).length
                ? options(key)
                : [{ name: pref[key], displayName: pref[key], enabled: true, basePrice: 0, modelType: key, id: pref[key] } as ModelInfo]
            }
            value={pref[key]}
            onChange={(name) => setPref({ ...pref, [key]: name })}
          />
        </div>
      ))}
      <label className="block text-[12px] font-bold text-[#555]">
        默认分辨率
        <select
          className="mt-1 h-10 w-full rounded-lg border border-black/10 bg-white px-2 text-[13px]"
          value={pref.resolution}
          onChange={(e) => setPref({ ...pref, resolution: e.target.value })}
        >
          {['512x512', '1024x1024', '1280x720', '1920x1080'].map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
      </label>
      <button
        disabled={saving}
        onClick={() => {
          setSaving(true)
          void updatePreferences({
            defaultTextModel: pref.text,
            defaultImageModel: pref.image,
            defaultVideoModel: pref.video,
            defaultResolution: pref.resolution,
          })
            .then(() => toastSuccess('偏好已保存'))
            .catch((e) => toastError((e as Error).message))
            .finally(() => setSaving(false))
        }}
        className="h-10 w-full rounded-full bg-[#111] text-[13px] font-bold text-white disabled:opacity-50"
      >
        {saving ? '保存中…' : '保存偏好'}
      </button>
      <div className="rounded-[18px] bg-[#f7f7f7] p-3">
        <p className="mb-2 text-[12px] font-bold text-[#555]">长期记忆</p>
        <Memories />
      </div>
    </div>
  )
}

function Memories() {
  const [items, setItems] = useState<MemoryView[]>([])
  useEffect(() => {
    void api<{ items: MemoryView[] }>('/memories')
      .then((r) => setItems(r.items))
      .catch(() => undefined)
  }, [])
  return (
    <div className="space-y-1.5">
      {items.length === 0 && <p className="text-[12px] text-[#999]">暂无长期记忆</p>}
      {items.map((m) => (
        <div key={m.id} className="flex items-center gap-2 rounded-lg bg-white px-2 py-1.5 text-[12px]">
          <span className="flex-1 text-[#555]">{m.content}</span>
          <button
            onClick={() =>
              void api(`/memories/${m.id}`, { method: 'DELETE' }).then(() => setItems((prev) => prev.filter((x) => x.id !== m.id)))
            }
            className="text-red-400 hover:text-red-600"
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  )
}

function SkillsTab({ sessionId }: { sessionId: string | number | null }) {
  const [skills, setSkills] = useState<SkillView[]>([])
  const [keyword, setKeyword] = useState('')
  const [creating, setCreating] = useState<'blank' | 'chat' | null>(null)
  const [draft, setDraft] = useState({ name: '', description: '', instructions: '' })
  const fileRef = useRef<HTMLInputElement>(null)

  const reload = () => {
    void api<{ items: SkillView[] }>(`/skills${keyword ? `?keyword=${encodeURIComponent(keyword)}` : ''}`)
      .then((r) => setSkills(r.items))
      .catch(() => undefined)
  }

  useEffect(() => {
    reload()
  }, [keyword])

  const createBlank = async () => {
    try {
      await api('/skills', {
        method: 'POST',
        body: JSON.stringify(draft),
      })
      toastSuccess('Skill 已创建')
      setCreating(null)
      setDraft({ name: '', description: '', instructions: '' })
      reload()
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const createFromChat = async () => {
    if (!sessionId) {
      toastError('请先打开一个对话')
      return
    }
    try {
      await api('/skills/from-conversation', {
        method: 'POST',
        body: JSON.stringify({ sessionId, name: draft.name || undefined }),
      })
      toastSuccess('已从对话生成 Skill')
      setCreating(null)
      reload()
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  const uploadSkill = async (file: File) => {
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch(apiUrl('/skills/upload'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('vp_access') ?? ''}` },
        body: fd,
      })
      if (!res.ok) throw new Error('上传失败')
      toastSuccess('Skill 文件已上传')
      reload()
    } catch (e) {
      toastError((e as Error).message)
    }
  }

  return (
    <div className="flex-1 space-y-2 overflow-auto p-3">
      <div className="flex gap-2">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜索 Skill"
          className="h-9 flex-1 rounded-full border border-black/10 px-3 text-[12px]"
        />
        <button
          onClick={() => setCreating('blank')}
          className="flex h-9 items-center gap-1 rounded-full bg-[#111] px-3 text-[12px] font-bold text-white"
        >
          <Plus size={13} /> 新建
        </button>
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => setCreating('chat')}
          className="h-8 flex-1 rounded-full border border-black/10 text-[11px] font-bold text-[#444]"
        >
          从当前对话生成
        </button>
        <button
          onClick={() => fileRef.current?.click()}
          className="flex h-8 flex-1 items-center justify-center gap-1 rounded-full border border-black/10 text-[11px] font-bold text-[#444]"
        >
          <Upload size={12} /> 上传 .md
        </button>
        <input ref={fileRef} type="file" accept=".md,.markdown" className="hidden" onChange={(e) => e.target.files?.[0] && void uploadSkill(e.target.files[0])} />
      </div>
      {creating && (
        <div className="space-y-2 rounded-[18px] border border-black/8 bg-[#f7f7f7] p-2.5">
          <input
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="Skill 名称"
            className="h-9 w-full rounded-lg border border-black/10 px-2 text-[12px]"
          />
          {creating === 'blank' && (
            <>
              <input
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                placeholder="描述"
                className="h-9 w-full rounded-lg border border-black/10 px-2 text-[12px]"
              />
              <textarea
                value={draft.instructions}
                onChange={(e) => setDraft({ ...draft, instructions: e.target.value })}
                placeholder="指令内容"
                className="h-24 w-full rounded-lg border border-black/10 p-2 text-[12px]"
              />
            </>
          )}
          <div className="flex gap-2">
            <button onClick={() => setCreating(null)} className="h-8 flex-1 rounded-lg border border-black/10 text-[12px] font-bold">
              取消
            </button>
            <button
              onClick={() => void (creating === 'blank' ? createBlank() : createFromChat())}
              className="h-8 flex-1 rounded-lg bg-[#111] text-[12px] font-bold text-white"
            >
              保存
            </button>
          </div>
        </div>
      )}
      {skills.map((s) => (
        <div key={s.id} className="rounded-[18px] border border-black/6 p-2.5">
          <p className="text-[13px] font-bold text-[#111]">{s.name}</p>
          <p className="mt-0.5 line-clamp-2 text-[12px] text-[#777]">{s.description ?? s.instructions}</p>
          {sessionId && (
            <button
              onClick={() => {
                void api(`/skills/${s.id}/attach?sessionId=${sessionId}`, { method: 'POST' }).catch(() => undefined)
                toastSuccess(`已添加 Skill：${s.name}`)
              }}
              className="mt-1.5 flex items-center gap-1 rounded-full bg-[#111] px-2.5 py-1 text-[11px] font-bold text-white"
            >
              添加到对话
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

function UsageTab({ sessionId }: { sessionId: string | number | null }) {
  const [usage, setUsage] = useState<{ tokenTotal: number; pointsUsed: number; modelUsage: Record<string, number> } | null>(null)
  useEffect(() => {
    if (!sessionId) return
    void api(`/agent/sessions/${sessionId}/usage`)
      .then((u) => setUsage(u as typeof usage))
      .catch(() => undefined)
  }, [sessionId])
  return (
    <div className="flex-1 space-y-3 overflow-auto p-4">
      <p className="text-[13px] font-bold text-[#111]">当前对话用量</p>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-[18px] bg-[#f7f7f7] p-3 text-center">
          <p className="text-[22px] font-black text-[#111]">{usage?.tokenTotal ?? 0}</p>
          <p className="text-[11px] text-[#999]">Token 总量</p>
        </div>
        <div className="rounded-[18px] bg-[#f7f7f7] p-3 text-center">
          <p className="text-[22px] font-black text-[#111]">{usage?.pointsUsed ?? 0}</p>
          <p className="text-[11px] text-[#999]">点数消耗</p>
        </div>
      </div>
      <div>
        <p className="mb-1 text-[12px] font-bold text-[#555]">各模型消耗</p>
        {Object.entries(usage?.modelUsage ?? {}).map(([m, t]) => (
          <div key={m} className="flex items-center justify-between rounded-lg bg-[#f7f7f7] px-2 py-1.5 text-[12px]">
            <span className="font-semibold text-[#555]">{m}</span>
            <span className="text-[#999]">{t} tokens</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function HistoryTab({
  sessionId,
  canvasId,
  onOpenSession,
  onImported,
}: {
  sessionId: string | number | null
  canvasId?: string | number
  onOpenSession: (id: string | number, title?: string) => void
  onImported: (id: string | number) => void
}) {
  const [sessions, setSessions] = useState<Array<{ sessionId: string | number; title: string; updatedAt?: string }>>([])
  const [fragments, setFragments] = useState<Array<{ id: number; title: string }>>([])
  const reload = () => {
    const q = canvasId != null ? `?canvasId=${encodeURIComponent(String(canvasId))}` : ''
    void api<{ items: typeof sessions }>(`/agent/sessions${q}`)
      .then((r) => setSessions(r.items))
      .catch(() => undefined)
    void api<{ items: typeof fragments }>('/agent/fragments')
      .then((r) => setFragments(r.items))
      .catch(() => undefined)
  }
  useEffect(() => {
    reload()
  }, [canvasId])
  const saveFragment = async () => {
    if (!sessionId) return
    try {
      await api(`/agent/sessions/${sessionId}/fragments`, {
        method: 'POST',
        body: JSON.stringify({ title: '片段 ' + new Date().toLocaleTimeString() }),
      })
      toastSuccess('会话片段已保存，可跨画布复用')
      reload()
    } catch (e) {
      toastError((e as Error).message)
    }
  }
  return (
    <div className="flex-1 space-y-3 overflow-auto p-3">
      <button
        onClick={() => void saveFragment()}
        className="flex h-9 w-full items-center justify-center gap-1 rounded-full bg-[#111] text-[12px] font-bold text-white"
      >
        <Plus size={13} /> 保存当前会话片段
      </button>
      <p className="text-[12px] font-bold text-[#555]">对话历史</p>
      {sessions.map((s) => (
        <button
          key={s.sessionId}
          type="button"
          onClick={() => onOpenSession(s.sessionId, s.title)}
          className={`w-full rounded-[16px] border px-2.5 py-2 text-left text-[12px] ${
            String(s.sessionId) === String(sessionId) ? 'border-[#111] bg-[#f7f7f7]' : 'border-black/6 hover:bg-[#f7f7f7]'
          }`}
        >
          <p className="font-bold text-[#333]">{s.title}</p>
          <p className="text-[#999]">#{s.sessionId}</p>
        </button>
      ))}
      <p className="text-[12px] font-bold text-[#555]">可复用片段</p>
      {fragments.map((f) => (
        <div key={f.id} className="flex items-center gap-2 rounded-[16px] bg-[#f7f7f7] px-2.5 py-2 text-[12px]">
          <span className="flex-1 font-semibold text-[#555]">{f.title}</span>
          <button
            type="button"
            onClick={() => {
              void api<{ sessionId: string | number }>(`/agent/fragments/${f.id}/import`, {
                method: 'POST',
                body: JSON.stringify({ canvasId }),
              })
                .then((r) => {
                  toastSuccess('片段已导入当前画布')
                  onImported(r.sessionId)
                })
                .catch((e) => toastError((e as Error).message))
            }}
            className="rounded-full bg-white px-2.5 py-1 text-[11px] font-bold text-[#111] shadow-sm"
          >
            导入
          </button>
        </div>
      ))}
    </div>
  )
}
