import { ArrowLeft, Check, Copy, Link2, Lock } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/lib/api'
import { sid } from '@/lib/ids'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'

export function ShareLinkPanel({
  canvasId,
  visibility,
  shareToken,
  onBack,
  onUpdated,
}: {
  canvasId: string | number
  visibility?: string
  shareToken?: string
  onBack: () => void
  onUpdated: (next: { visibility: string; shareToken?: string }) => void
}) {
  const [busy, setBusy] = useState(false)
  const linkActive = visibility === 'link' || visibility === 'public'
  const shareUrl =
    shareToken && linkActive ? `${location.origin}/canvas/shared/${shareToken}` : ''

  const setVisibility = async (next: string) => {
    setBusy(true)
    try {
      const d = await api<{ canvas: { shareToken: string; visibility: string } }>(
        `/canvases/${sid(canvasId)}/share`,
        { method: 'POST', body: JSON.stringify({ visibility: next }) },
      )
      onUpdated({ visibility: d.canvas.visibility, shareToken: d.canvas.shareToken })
      if (next === 'link' || next === 'public') {
        const url = `${location.origin}/canvas/shared/${d.canvas.shareToken}`
        void navigator.clipboard?.writeText(url)
        toastSuccess('链接已复制')
      } else {
        toastSuccess('已停止共享')
      }
    } catch (e) {
      toastError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const copyLink = async () => {
    if (!shareUrl) {
      await setVisibility('link')
      return
    }
    try {
      await navigator.clipboard?.writeText(shareUrl)
      toastSuccess('链接已复制')
    } catch {
      toastError('复制失败')
    }
  }

  return (
    <div className="py-1">
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-semibold text-[#666] hover:text-[#111]"
      >
        <ArrowLeft size={14} /> 返回
      </button>

      <div className="mb-5 flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#f3f4f6]">
          <Link2 size={18} className="text-[#555]" />
        </span>
        <div>
          <h2 className="text-[20px] font-bold text-[#111827]">以链接形式分享画布</h2>
          <p className="mt-1 text-[13px] text-[#6b7280]">任何获得链接的人可查看；可随时停止共享。</p>
        </div>
      </div>

      <div className="mb-4 rounded-[18px] border border-black/8 bg-[#f7f7f9] px-4 py-3">
        <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-[#999]">当前链接</p>
        <p className="truncate text-[13px] font-medium text-[#333]">
          {shareUrl || '尚未开启链接共享'}
        </p>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          disabled={busy}
          onClick={() => void copyLink()}
          className="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-[16px] bg-[#111] text-[14px] font-bold text-white disabled:opacity-60"
        >
          <Copy size={15} /> {shareUrl ? '复制链接' : '开启并复制'}
        </button>
        <button
          type="button"
          disabled={busy || !linkActive}
          onClick={() => void setVisibility('private')}
          className={cn(
            'inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-[16px] border border-black/10 text-[14px] font-bold',
            linkActive ? 'text-[#333] hover:bg-black/[0.03]' : 'cursor-not-allowed text-[#bbb]',
          )}
        >
          <Lock size={15} /> 停止共享
        </button>
      </div>

      {linkActive ? (
        <p className="mt-3 flex items-center justify-center gap-1.5 text-[12px] font-semibold text-emerald-600">
          <Check size={13} /> 链接共享已开启
        </p>
      ) : null}
    </div>
  )
}
