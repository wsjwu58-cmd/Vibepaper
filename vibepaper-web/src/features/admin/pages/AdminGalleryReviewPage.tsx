import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { api, assetUrl } from '@/lib/api'
import type { PageResult, PublicationView } from '@/lib/types'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import { Field, Input } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'

const STATUS_TABS = [
  { key: 'pending', label: '待审核' },
  { key: 'published', label: '已发布' },
  { key: 'rejected', label: '已驳回' },
  { key: 'taken_down', label: '已下架' },
  { key: 'all', label: '全部' },
] as const

type StatusTab = (typeof STATUS_TABS)[number]['key']

/** Snowflake ID 必须用字符串，禁止 Number() 以免精度丢失 */
function pubId(id: string | number | undefined | null): string {
  return String(id ?? '')
}

function statusBadge(status: string) {
  if (status === 'published') return 'bg-emerald-100 text-emerald-700'
  if (status === 'pending') return 'bg-amber-100 text-amber-700'
  if (status === 'rejected') return 'bg-red-100 text-red-700'
  return 'bg-slate-100 text-slate-600'
}

export function AdminGalleryReviewPage() {
  const qc = useQueryClient()
  const [status, setStatus] = useState<StatusTab>('pending')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [detail, setDetail] = useState<PublicationView | null>(null)
  const [reason, setReason] = useState('')
  const [confirm, setConfirm] = useState<{
    title: string
    message: string
    action: () => void
    danger?: boolean
  } | null>(null)
  const [reasonModal, setReasonModal] = useState<{
    title: string
    action: 'reject' | 'take_down'
    ids: string[]
  } | null>(null)

  const queryStatus = status === 'all' ? '' : status
  const { data, isLoading } = useQuery({
    queryKey: ['admin-pubs', queryStatus, page],
    queryFn: () =>
      api<PageResult<PublicationView>>(
        `/publications/admin/list?status=${encodeURIComponent(queryStatus)}&page=${page}&pageSize=20`,
      ),
  })

  const items = data?.items ?? []
  const allIds = useMemo(() => items.map((i) => pubId(i.id)), [items])
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id))

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['admin-pubs'] })
    void qc.invalidateQueries({ queryKey: ['admin-pub-stats'] })
    setSelected(new Set())
  }

  const moderate = useMutation({
    mutationFn: ({ id, action, reason: r }: { id: string; action: string; reason?: string }) =>
      api(`/publications/admin/${id}/${action}`, {
        method: 'POST',
        body: JSON.stringify(r ? { reason: r } : {}),
      }),
    onSuccess: () => {
      toastSuccess('操作成功')
      setDetail(null)
      invalidate()
    },
    onError: (e) => toastError((e as Error).message),
  })

  const batch = useMutation({
    mutationFn: ({ ids, action, reason: r }: { ids: string[]; action: string; reason?: string }) =>
      api('/publications/admin/batch', {
        method: 'POST',
        body: JSON.stringify({ ids, action, reason: r }),
      }),
    onSuccess: () => {
      toastSuccess('批量操作完成')
      setDetail(null)
      invalidate()
    },
    onError: (e) => toastError((e as Error).message),
  })

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(allIds))
  }

  const openReason = (action: 'reject' | 'take_down', ids: string[]) => {
    setReason('')
    setReasonModal({
      title: action === 'reject' ? '驳回作品' : '下架作品',
      action,
      ids,
    })
  }

  const submitReason = () => {
    if (!reasonModal) return
    if (!reason.trim()) {
      toastError('请填写原因')
      return
    }
    const { action, ids } = reasonModal
    setReasonModal(null)
    if (ids.length === 1) {
      moderate.mutate({ id: ids[0], action, reason: reason.trim() })
    } else {
      batch.mutate({ ids, action, reason: reason.trim() })
    }
  }

  return (
    <div className="mx-auto max-w-[1200px]">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-black text-[#111]">内容审核</h1>
          <p className="mt-1 text-[14px] text-[#666]">审核 PaperHub 发布内容</p>
        </div>
        {selected.size > 0 ? (
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() =>
                setConfirm({
                  title: '批量通过',
                  message: `确定通过选中的 ${selected.size} 条作品？`,
                  action: () => batch.mutate({ ids: [...selected], action: 'approve' }),
                })
              }
            >
              批量通过 ({selected.size})
            </Button>
            <Button variant="secondary" onClick={() => openReason('reject', [...selected])}>
              批量驳回
            </Button>
            <Button variant="ghost" onClick={() => openReason('take_down', [...selected])}>
              批量下架
            </Button>
          </div>
        ) : null}
      </div>

      <div className="mb-4 flex flex-wrap gap-1 rounded-2xl border border-black/6 bg-white p-1.5">
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => {
              setStatus(t.key)
              setPage(1)
              setSelected(new Set())
            }}
            className={cn(
              'h-9 rounded-xl px-3.5 text-[13px] font-bold',
              status === t.key ? 'bg-[#111] text-white' : 'text-[#666] hover:bg-black/[0.04]',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <section className="rounded-2xl border border-black/6 bg-white">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="h-7 w-7" />
          </div>
        ) : items.length === 0 ? (
          <p className="py-16 text-center text-[14px] text-[#999]">暂无数据</p>
        ) : (
          <table className="w-full text-left text-[13px]">
            <thead className="text-[12px] text-[#999]">
              <tr className="border-b border-black/6">
                <th className="w-10 px-4 py-3">
                  <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                </th>
                <th className="py-3">封面</th>
                <th>标题</th>
                <th>作者</th>
                <th>状态</th>
                <th className="pr-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const id = pubId(p.id)
                return (
                  <tr
                    key={id}
                    className="cursor-pointer border-t border-black/4 hover:bg-black/[0.02]"
                    onClick={() => setDetail(p)}
                  >
                    <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(id)}
                        onChange={() => toggleOne(id)}
                      />
                    </td>
                    <td className="py-2.5">
                      <div className="h-12 w-16 overflow-hidden rounded-lg bg-black/[0.04]">
                        {p.thumbnailUrl ? (
                          <img
                            src={assetUrl(p.thumbnailUrl)}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                        ) : null}
                      </div>
                    </td>
                    <td className="pr-3 font-bold text-[#333]">{p.title}</td>
                    <td className="text-[#666]">{p.authorName ?? `#${p.ownerId}`}</td>
                    <td>
                      <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-bold', statusBadge(p.status))}>
                        {p.status}
                      </span>
                    </td>
                    <td className="pr-4" onClick={(e) => e.stopPropagation()}>
                      <div className="flex flex-wrap gap-1.5">
                        {p.status === 'pending' ? (
                          <>
                            <button
                              type="button"
                              className="rounded-lg bg-emerald-600 px-2.5 py-1 text-[12px] font-bold text-white"
                              onClick={() =>
                                setConfirm({
                                  title: '通过审核',
                                  message: `确定通过「${p.title}」？`,
                                  action: () => moderate.mutate({ id, action: 'approve' }),
                                })
                              }
                            >
                              通过
                            </button>
                            <button
                              type="button"
                              className="rounded-lg bg-red-600 px-2.5 py-1 text-[12px] font-bold text-white"
                              onClick={() => openReason('reject', [id])}
                            >
                              驳回
                            </button>
                          </>
                        ) : null}
                        {p.status === 'published' ? (
                          <button
                            type="button"
                            className="rounded-lg border border-black/10 px-2.5 py-1 text-[12px] font-bold"
                            onClick={() => openReason('take_down', [id])}
                          >
                            下架
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {(data?.total ?? 0) > 20 ? (
          <div className="flex items-center justify-between border-t border-black/6 px-4 py-3 text-[13px] text-[#666]">
            <span>
              共 {data?.total} 条 · 第 {page} 页
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="h-8 rounded-lg border border-black/10 px-3 font-semibold disabled:opacity-40"
              >
                上一页
              </button>
              <button
                type="button"
                disabled={page * 20 >= (data?.total ?? 0)}
                onClick={() => setPage((p) => p + 1)}
                className="h-8 rounded-lg border border-black/10 px-3 font-semibold disabled:opacity-40"
              >
                下一页
              </button>
            </div>
          </div>
        ) : null}
      </section>

      {detail ? (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={() => setDetail(null)}>
          <aside
            className="flex h-full w-full max-w-md flex-col bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-black/6 px-5 py-4">
              <h2 className="text-[16px] font-bold text-[#111]">作品详情</h2>
              <button
                type="button"
                onClick={() => setDetail(null)}
                className="rounded-full p-2 text-[#666] hover:bg-black/5"
              >
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              <div className="mb-4 overflow-hidden rounded-2xl bg-black/[0.04]">
                {(detail.previewAssetUrl || detail.thumbnailUrl) && (
                  <img
                    src={assetUrl(detail.previewAssetUrl || detail.thumbnailUrl)}
                    alt=""
                    className="max-h-64 w-full object-contain"
                  />
                )}
              </div>
              <h3 className="text-[18px] font-black text-[#111]">{detail.title}</h3>
              <p className="mt-1 text-[13px] text-[#666]">作者 {detail.authorName ?? `#${detail.ownerId}`}</p>
              <span className={cn('mt-2 inline-block rounded-full px-2 py-0.5 text-[11px] font-bold', statusBadge(detail.status))}>
                {detail.status}
              </span>
              {detail.description ? (
                <p className="mt-4 whitespace-pre-wrap text-[14px] text-[#444]">{detail.description}</p>
              ) : null}
              {detail.tags?.length ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {detail.tags.map((t) => (
                    <span key={t} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-[#555]">
                      {t}
                    </span>
                  ))}
                </div>
              ) : null}
              {detail.rejectedReason ? (
                <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-[13px] text-red-700">
                  原因：{detail.rejectedReason}
                </p>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2 border-t border-black/6 px-5 py-4">
              {detail.status === 'pending' ? (
                <>
                  <Button
                    onClick={() =>
                      setConfirm({
                        title: '通过审核',
                        message: `确定通过「${detail.title}」？`,
                        action: () => moderate.mutate({ id: pubId(detail.id), action: 'approve' }),
                      })
                    }
                  >
                    通过
                  </Button>
                  <Button variant="secondary" onClick={() => openReason('reject', [pubId(detail.id)])}>
                    驳回
                  </Button>
                </>
              ) : null}
              {detail.status === 'published' ? (
                <Button variant="ghost" onClick={() => openReason('take_down', [pubId(detail.id)])}>
                  下架
                </Button>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}

      <Modal open={!!reasonModal} onClose={() => setReasonModal(null)} title={reasonModal?.title ?? ''}>
        <div className="flex flex-col gap-3">
          <Field label="原因（必填）">
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="请输入原因" />
          </Field>
          <Button onClick={submitReason}>确认</Button>
        </div>
      </Modal>

      <ConfirmDialog
        open={!!confirm}
        onClose={() => setConfirm(null)}
        onConfirm={() => confirm?.action()}
        title={confirm?.title ?? ''}
        message={confirm?.message ?? ''}
        danger={confirm?.danger}
      />
    </div>
  )
}
