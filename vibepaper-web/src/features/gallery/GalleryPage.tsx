import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, Sparkles, Trash2 } from 'lucide-react'
import { api } from '@/lib/api'
import type { PageResult, PublicationView } from '@/lib/types'
import { Input } from '@/components/ui/Input'
import { ConfirmDialog } from '@/components/ui/Modal'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'
import { useAuthedMediaUrl } from '@/lib/media'
import { formatRelativeTime } from './galleryUtils'
import { useAuth } from '@/lib/auth'
import { sid } from '@/lib/ids'

const PAGE_SIZE = 24

export function GalleryPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const user = useAuth((s) => s.user)
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [items, setItems] = useState<PublicationView[]>([])
  const [delTarget, setDelTarget] = useState<PublicationView | null>(null)

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['gallery', keyword, page],
    queryFn: () =>
      api<PageResult<PublicationView>>(
        `/gallery/publications?page=${page}&pageSize=${PAGE_SIZE}${keyword ? `&keyword=${encodeURIComponent(keyword)}` : ''}`,
      ),
  })

  useEffect(() => {
    if (!data) return
    setItems((prev) => (page === 1 ? data.items : [...prev, ...data.items.filter((n) => !prev.some((p) => sid(p.id) === sid(n.id)))]))
  }, [data, page])

  useEffect(() => {
    setPage(1)
    setItems([])
  }, [keyword])

  const del = useMutation({
    mutationFn: (id: string | number) => api(`/publications/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gallery'] })
      toastSuccess('已删除')
      setDelTarget(null)
    },
    onError: (e) => toastError((e as Error).message),
  })

  const total = data?.total ?? 0
  const hasMore = page * PAGE_SIZE < total

  return (
    <div className="w-full">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-black tracking-tight text-[#111]">创意广场</h1>
          <p className="mt-1.5 text-[14px] text-[#666]">探索其他创作者的工作流，开始你自己的创作</p>
        </div>
        <div className="relative">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#999]" />
          <Input
            className="h-11 w-72 rounded-full border-black/8 bg-white pl-10"
            placeholder="搜索工作流、创作者..."
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value)
            }}
          />
        </div>
      </div>

      {isLoading && page === 1 ? (
        <div className="flex justify-center py-24">
          <Spinner className="h-8 w-8" />
        </div>
      ) : !items.length ? (
        <div className="rounded-3xl border border-dashed border-black/12 py-24 text-center">
          <Sparkles size={32} className="mx-auto mb-2 text-[#ccc]" />
          <p className="text-[14px] text-[#999]">暂无公开作品</p>
        </div>
      ) : (
        <>
          <div className="columns-1 gap-5 sm:columns-2 lg:columns-3 xl:columns-4 2xl:columns-5">
            {items.map((p) => (
              <GalleryCard
                key={String(p.id)}
                pub={p}
                isOwner={user != null && sid(user.id) === sid(p.ownerId)}
                onOpen={() => nav(`/gallery/${sid(p.id)}`)}
                onDelete={() => setDelTarget(p)}
              />
            ))}
          </div>
          {hasMore ? (
            <div className="mt-8 flex justify-center">
              <button
                type="button"
                disabled={isFetching}
                onClick={() => setPage((p) => p + 1)}
                className="h-11 rounded-full bg-[#111] px-6 text-[13px] font-bold text-white disabled:opacity-60"
              >
                {isFetching ? '加载中…' : '加载更多'}
              </button>
            </div>
          ) : null}
        </>
      )}

      <ConfirmDialog
        open={!!delTarget}
        onClose={() => setDelTarget(null)}
        onConfirm={() => delTarget && del.mutate(delTarget.id)}
        title="删除作品"
        message="仅能删除自己上传的作品，确定删除吗？"
        danger
      />
    </div>
  )
}

function GalleryCard({
  pub,
  isOwner,
  onOpen,
  onDelete,
}: {
  pub: PublicationView
  isOwner: boolean
  onOpen: () => void
  onDelete: () => void
}) {
  const thumb = useAuthedMediaUrl(pub.thumbnailUrl || pub.previewAssetUrl)
  const author = pub.authorName ? `@${pub.authorName}` : '@创作者'
  const when = formatRelativeTime(pub.publishedAt || pub.createdAt)
  const tags = pub.tags ?? []

  return (
    <article className="mb-5 break-inside-avoid">
      <button type="button" onClick={onOpen} className="group block w-full text-left">
        <div className="overflow-hidden rounded-2xl bg-[#ececef]">
          {thumb ? (
            <img
              src={thumb}
              alt={pub.title}
              className="block w-full object-cover transition duration-300 group-hover:scale-[1.02]"
            />
          ) : (
            <div className="flex aspect-[4/5] items-center justify-center bg-gradient-to-br from-slate-100 to-slate-200">
              <Sparkles size={28} className="text-[#bbb]" />
            </div>
          )}
        </div>
        <p className="mt-2.5 truncate text-[15px] font-bold text-[#111]">{pub.title}</p>
        {tags.length > 0 ? (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {tags.slice(0, 3).map((t) => (
              <span key={t} className="rounded-full bg-[#f3f4f6] px-2 py-0.5 text-[10px] font-semibold text-[#666]">
                {t}
              </span>
            ))}
          </div>
        ) : null}
        <div className="mt-1 flex items-center gap-2 text-[12px] text-[#888]">
          {pub.authorAvatar ? (
            <img src={pub.authorAvatar} alt="" className="h-5 w-5 rounded-full object-cover" />
          ) : (
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#111] text-[10px] font-bold text-white">
              {(pub.authorName ?? '创').slice(0, 1)}
            </span>
          )}
          <span className="truncate font-medium">{author}</span>
          {when ? <span className="shrink-0 text-[#aaa]">{when}</span> : null}
        </div>
      </button>
      {isOwner ? (
        <button
          type="button"
          onClick={onDelete}
          className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-[#bbb] hover:text-red-500"
        >
          <Trash2 size={12} /> 删除
        </button>
      ) : null}
    </article>
  )
}
