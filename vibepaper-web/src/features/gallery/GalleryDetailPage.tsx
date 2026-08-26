import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Copy, Eye, Maximize2, Play } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { sid } from '@/lib/ids'
import type { PageResult, PublicationView } from '@/lib/types'
import { useAuthedMediaUrl } from '@/lib/media'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { useAuth } from '@/lib/auth'
import { isAudioUrl, isVideoUrl } from './galleryUtils'

export function GalleryDetailPage() {
  const { id } = useParams()
  const pubId = sid(id)
  const nav = useNavigate()
  const user = useAuth((s) => s.user)
  const mediaRef = useRef<HTMLDivElement>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [mediaIndex, setMediaIndex] = useState(0)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['gallery-detail', pubId],
    queryFn: () => api<PublicationView>(`/gallery/publications/${pubId}`),
    enabled: !!pubId,
  })

  const { data: list } = useQuery({
    queryKey: ['gallery', '', 1],
    queryFn: () => api<PageResult<PublicationView>>('/gallery/publications?page=1&pageSize=48'),
  })

  useEffect(() => {
    setMediaIndex(0)
  }, [pubId, data?.id])

  const mediaList = useMemo(() => {
    const urls = [...(data?.resultAssetUrls ?? [])]
    if (data?.previewAssetUrl && !urls.includes(data.previewAssetUrl)) urls.unshift(data.previewAssetUrl)
    if (urls.length === 0 && data?.thumbnailUrl) urls.push(data.thumbnailUrl)
    return urls
  }, [data])

  const mediaUrl = mediaList[mediaIndex] || data?.previewAssetUrl || data?.thumbnailUrl
  const authed = useAuthedMediaUrl(mediaUrl)
  const video = isVideoUrl(mediaUrl)
  const audio = isAudioUrl(mediaUrl)

  const neighbors = useMemo(() => {
    const items = list?.items ?? []
    const idx = items.findIndex((p) => sid(p.id) === pubId)
    if (idx < 0) return { prev: null as PublicationView | null, next: null as PublicationView | null }
    return {
      prev: idx > 0 ? items[idx - 1] : null,
      next: idx < items.length - 1 ? items[idx + 1] : null,
    }
  }, [list, pubId])

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
      nav(`/login?redirect=${encodeURIComponent(`/gallery/${pubId}`)}`)
      return
    }
    clone.mutate()
  }

  const enterFullscreen = async () => {
    const el = mediaRef.current
    if (!el) return
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen()
        setFullscreen(false)
      } else {
        await el.requestFullscreen()
        setFullscreen(true)
      }
    } catch {
      setFullscreen((v) => !v)
    }
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
        <p className="text-[16px] font-bold">无法打开作品</p>
        <p className="text-[13px] text-white/60">
          {error instanceof ApiError ? error.message : '加载失败'}
        </p>
        <Link to="/gallery" className="mt-2 rounded-full bg-white/10 px-4 py-2 text-[13px] font-semibold">
          返回创意广场
        </Link>
      </div>
    )
  }

  return (
    <div className="relative h-screen overflow-hidden bg-[#1a1a1c] text-white">
      <button
        type="button"
        onClick={() => nav('/gallery')}
        className="absolute left-4 top-4 z-20 inline-flex h-9 items-center gap-1.5 rounded-full bg-black/55 px-3.5 text-[13px] font-semibold backdrop-blur"
      >
        <ChevronLeft size={15} /> 返回
      </button>

      <button
        type="button"
        disabled={clone.isPending}
        onClick={onClone}
        className="absolute right-4 top-4 z-20 inline-flex h-9 items-center gap-1.5 rounded-full bg-black/55 px-3.5 text-[13px] font-semibold backdrop-blur disabled:opacity-60"
      >
        <Copy size={14} /> 克隆
      </button>

      <div className="absolute left-4 top-1/2 z-20 flex -translate-y-1/2 flex-col gap-2">
        <SidePill icon={<Play size={14} />} label="全屏观看" onClick={() => void enterFullscreen()} />
        <SidePill
          icon={<Eye size={14} />}
          label="查看流程"
          onClick={() => nav(`/gallery/${pubId}/process`)}
        />
      </div>

      {neighbors.prev ? (
        <button
          type="button"
          onClick={() => nav(`/gallery/${sid(neighbors.prev!.id)}`)}
          className="absolute left-3 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/40 p-2 text-white/80 hover:bg-black/60"
          aria-label="上一件"
        >
          <ChevronLeft size={22} />
        </button>
      ) : null}
      {neighbors.next ? (
        <button
          type="button"
          onClick={() => nav(`/gallery/${sid(neighbors.next!.id)}`)}
          className="absolute right-3 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/40 p-2 text-white/80 hover:bg-black/60"
          aria-label="下一件"
        >
          <ChevronRight size={22} />
        </button>
      ) : null}

      <div
        ref={mediaRef}
        className={`flex h-full flex-col items-center justify-center px-16 py-16 ${fullscreen ? 'bg-black' : ''}`}
      >
        <div className="relative max-h-[70vh] max-w-4xl overflow-hidden rounded-2xl bg-[#111]">
          {!authed ? (
            <div className="flex h-[60vh] w-[40vw] min-w-[280px] items-center justify-center text-[13px] text-white/50">
              暂无成品预览
            </div>
          ) : video ? (
            <video src={authed} controls className="max-h-[70vh] max-w-full object-contain" />
          ) : audio ? (
            <div className="flex h-48 w-[min(480px,80vw)] items-center justify-center px-6">
              <audio src={authed} controls className="w-full" />
            </div>
          ) : (
            <img src={authed} alt={data.title} className="max-h-[70vh] max-w-full object-contain" />
          )}
          {mediaList.length > 1 ? (
            <>
              <button
                type="button"
                className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-2"
                onClick={() => setMediaIndex((i) => (i - 1 + mediaList.length) % mediaList.length)}
              >
                <ChevronLeft size={18} />
              </button>
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-2"
                onClick={() => setMediaIndex((i) => (i + 1) % mediaList.length)}
              >
                <ChevronRight size={18} />
              </button>
              <span className="absolute bottom-3 left-3 rounded-full bg-black/55 px-2 py-0.5 text-[11px] font-semibold">
                {mediaIndex + 1}/{mediaList.length}
              </span>
            </>
          ) : null}
          <button
            type="button"
            onClick={() => void enterFullscreen()}
            className="absolute bottom-3 right-3 rounded-full bg-black/55 p-2 text-white/80 backdrop-blur hover:text-white"
            title="全屏"
          >
            <Maximize2 size={16} />
          </button>
        </div>

        <div className="mt-5 max-w-xl px-4 text-center">
          <h1 className="text-[18px] font-bold">{data.title}</h1>
          {data.description ? (
            <p className="mt-2 text-[13px] leading-relaxed text-white/65">{data.description}</p>
          ) : null}
          {(data.tags?.length ?? 0) > 0 ? (
            <div className="mt-3 flex flex-wrap justify-center gap-1.5">
              {data.tags!.map((t) => (
                <span key={t} className="rounded-full bg-white/10 px-2.5 py-0.5 text-[11px] font-semibold text-white/80">
                  {t}
                </span>
              ))}
            </div>
          ) : null}
          <p className="mt-2 text-[12px] text-white/40">
            @{data.authorName ?? '创作者'}
            {typeof data.viewCount === 'number' ? ` · ${data.viewCount} 次浏览` : ''}
          </p>
        </div>
      </div>
    </div>
  )
}

function SidePill({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-10 items-center gap-2 rounded-full bg-black/55 px-3.5 text-[13px] font-semibold backdrop-blur hover:bg-black/70"
    >
      {icon}
      {label}
    </button>
  )
}
