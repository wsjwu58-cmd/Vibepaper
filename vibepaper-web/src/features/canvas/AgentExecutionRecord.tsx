import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, Info } from 'lucide-react'
import type { ExecutionStep } from './agentTypes'
import { cn } from '@/lib/cn'

/** 图一样式：只展示计划/结果步骤；「推理过程」长独白不单独成块，理由嵌在「为什么这么做」。 */
function displaySteps(steps: ExecutionStep[]): ExecutionStep[] {
  const actionable = steps.filter((s) => s.kind === 'plan' || s.kind === 'result')
  const resultByTool = new Map<string, ExecutionStep>()
  for (const s of actionable) {
    if (s.kind === 'result' && s.tool) resultByTool.set(s.tool, s)
  }
  const shown: ExecutionStep[] = []
  const usedTools = new Set<string>()
  for (const s of actionable) {
    if (s.kind === 'plan') {
      const done = s.tool ? resultByTool.get(s.tool) : undefined
      if (done) {
        // 合并：绿勾结果 + 保留计划里的「为什么这么做」
        shown.push({
          ...done,
          reasoning: done.reasoning || s.reasoning,
          summary: done.summary || s.summary,
        })
        if (s.tool) usedTools.add(s.tool)
      } else {
        shown.push(s)
      }
      continue
    }
    if (s.kind === 'result' && s.tool && usedTools.has(s.tool)) continue
    if (s.kind === 'result' && s.tool && !usedTools.has(s.tool)) {
      shown.push(s)
      usedTools.add(s.tool)
    }
  }
  return shown
}

export function AgentExecutionRecord({
  steps,
  defaultOpen = true,
}: {
  steps: ExecutionStep[]
  defaultOpen?: boolean
}) {
  const visible = displaySteps(steps)
  const [open, setOpen] = useState(defaultOpen)
  if (visible.length === 0) return null

  const doneCount = visible.filter((s) => s.kind === 'result' && s.ok).length
  const title =
    doneCount > 0 ? `执行记录 · 执行了 ${doneCount} 项操作` : `执行记录 · ${visible.length} 步`

  return (
    <div className="mt-2.5 rounded-[14px] border border-black/8 bg-[#f7f7f8]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[12px] font-semibold text-[#555]"
      >
        <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
        <span className="flex-1">{title}</span>
        {open ? <ChevronDown size={14} className="text-[#999]" /> : <ChevronRight size={14} className="text-[#999]" />}
      </button>
      {open && (
        <div className="space-y-2 border-t border-black/6 px-3 pb-3 pt-2">
          {visible.map((s) => {
            const isDone = s.kind === 'result' && s.ok
            const isFail = s.kind === 'result' && s.ok === false
            return (
              <div key={s.id} className="flex items-start gap-2 rounded-[10px] bg-white px-2.5 py-2">
                <span
                  className={cn(
                    'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full',
                    isDone
                      ? 'bg-emerald-50 text-emerald-600'
                      : isFail
                        ? 'bg-red-50 text-red-500'
                        : 'bg-blue-50 text-blue-500',
                  )}
                >
                  {isDone ? (
                    <Check size={10} strokeWidth={3} />
                  ) : (
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-bold text-[#333]">{s.label}</p>
                  <p className="text-[11px] leading-relaxed text-[#777]">{s.summary}</p>
                  {s.detail && (
                    <p className="mt-0.5 text-[10px] leading-relaxed text-[#999]">{s.detail}</p>
                  )}
                  {s.reasoning ? (
                    <div className="mt-1.5 rounded-[8px] border border-black/5 bg-[#fafafa] px-2 py-1.5">
                      <p className="mb-0.5 flex items-center gap-1 text-[10px] font-semibold text-[#888]">
                        <Info size={10} /> 为什么这么做
                      </p>
                      <p className="whitespace-pre-line text-[10px] leading-relaxed text-[#777]">
                        {s.reasoning}
                      </p>
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function AgentNextActions({
  actions,
  onPick,
}: {
  actions: string[]
  onPick: (text: string) => void
}) {
  if (actions.length === 0) return null
  return (
    <div className="mt-3">
      <p className="text-[11px] leading-relaxed text-[#666]">
        <span className="font-bold">下一步建议：</span>
        {actions.map((a, idx) => (
          <span key={a}>
            <button
              type="button"
              onClick={() => onPick(a)}
              className="text-[#333] underline-offset-2 transition hover:text-[#111] hover:underline"
            >
              {a}
            </button>
            {idx < actions.length - 1 ? ' · ' : null}
          </span>
        ))}
      </p>
    </div>
  )
}

export function AgentTaskBadge({
  status,
  taskId,
}: {
  status?: string
  taskId?: string
}) {
  if (!status || status === 'succeeded' || status === 'failed') return null
  const label =
    status === 'running' ? '生成中…' : status === 'queued' ? '排队中…' : `任务 ${status}`
  return (
    <p className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-[#888]">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
      {label}
      {taskId ? <span className="text-[#bbb]">#{String(taskId).slice(-6)}</span> : null}
    </p>
  )
}
