import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ChevronLeft, Copy, Eye, Play } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { sid } from '@/lib/ids'
import type { CanvasDetail, PublicationView } from '@/lib/types'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { useAuth } from '@/lib/auth'
import { GalleryProcessViewer } from './GalleryProcessViewer'

export function GalleryProcessPage() {
  const { id } = useParams()
  const pubId = sid(id)
  const nav = useNavigate()
  const user = useAuth((s) => s.user)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['gallery-detail', pubId],
    queryFn: () => api<PublicationView & { snapshot?: CanvasDetail }>(`/gallery/publications/${pubId}`),
    enabled: !!pubId,
  })

  const clone = useMutation({
    mutationFn: () =>
      api<{ canvasId: string | number }>(`/gallery/publications/${pubId}/clone`, { method: 'POST' }),
    onSuccess: (r) => {
      toastSuccess('克隆成功')
      nav(`/canvas/${sid(r.canvasId)}`)
    },
    onError: (e) => toastError((e as Error).message),
  })

  const onClone = () => {
    if (!user) {
      nav(`/login?redirect=${encodeURIComponent(`/gallery/${pubId}/process`)}`)
      return
    }
    clone.mutate()
  }

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#1a1a1c]">
        <Spinner className="h-8 w-8 text-white" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-[#1a1a1c] text-white">
        <p className="text-[16px] font-bold">无法加载流程</p>
        <p className="text-[13px] text-white/60">
          {error instanceof ApiError ? error.message : '加载失败'}
        </p>
        <Link to="/gallery" className="mt-2 rounded-full bg-white/10 px-4 py-2 text-[13px] font-semibold">
          返回创意广场
        </Link>
      </div>
    )
  }

  const snapshot = data.snapshot
  const title = data.title || snapshot?.canvas?.name || '工作流'

  return (
    <div className="relative h-screen overflow-hidden bg-[#1a1a1c]">
      <button
        type="button"
        onClick={() => nav(`/gallery/${pubId}`)}
        className="absolute left-4 top-4 z-30 inline-flex h-9 items-center gap-1.5 rounded-full bg-black/55 px-3.5 text-[13px] font-semibold text-white backdrop-blur"
      >
        <ChevronLeft size={15} /> 返回
      </button>

      <button
        type="button"
        disabled={clone.isPending}
        onClick={onClone}
        className="absolute right-4 top-4 z-30 inline-flex h-9 items-center gap-1.5 rounded-full bg-black/55 px-3.5 text-[13px] font-semibold text-white backdrop-blur disabled:opacity-60"
      >
        <Copy size={14} /> 克隆
      </button>

      <div className="absolute left-4 top-1/2 z-30 flex -translate-y-1/2 flex-col gap-2">
        <button
          type="button"
          onClick={() => nav(`/gallery/${pubId}`)}
          className="inline-flex h-10 items-center gap-2 rounded-full bg-black/55 px-3.5 text-[13px] font-semibold text-white backdrop-blur hover:bg-black/70"
        >
          <Play size={14} /> 全屏观看
        </button>
        <button
          type="button"
          className="inline-flex h-10 items-center gap-2 rounded-full bg-white px-3.5 text-[13px] font-semibold text-[#111]"
        >
          <Eye size={14} /> 查看流程
        </button>
      </div>

      <div className="absolute inset-x-10 bottom-8 top-8 overflow-hidden rounded-[28px] bg-[#ececef] shadow-[0_24px_80px_rgba(0,0,0,0.35)]">
        <div className="pointer-events-none absolute left-5 top-4 z-10 text-[15px] font-bold text-[#222]">
          {title}
        </div>
        {snapshot && (snapshot.nodes?.length ?? 0) > 0 ? (
          <GalleryProcessViewer snapshot={snapshot} />
        ) : (
          <div className="flex h-full items-center justify-center text-[14px] text-[#888]">
            该作品暂无流程快照
          </div>
        )}
      </div>
    </div>
  )
}
