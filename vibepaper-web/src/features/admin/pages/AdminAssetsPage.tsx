import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'
import type { PageResult } from '@/lib/types'
import { ConfirmDialog } from '@/components/ui/Modal'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'

type AssetRow = {
  id: number
  name: string
  assetType?: string
  type?: string
  status: string
}

export function AdminAssetsPage() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [confirm, setConfirm] = useState<{ id: number; action: 'block' | 'unblock' } | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-assets', page],
    queryFn: () => api<PageResult<AssetRow>>(`/admin/assets?page=${page}&pageSize=20`),
    retry: false,
  })

  const apiMissing = error instanceof ApiError && error.status === 404

  const moderate = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'block' | 'unblock' }) =>
      api(`/admin/assets/${id}/moderate`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      }),
    onSuccess: () => {
      toastSuccess('素材状态已更新')
      void qc.invalidateQueries({ queryKey: ['admin-assets'] })
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 404) {
        toastError('素材治理 API 尚未上线')
        return
      }
      toastError((e as Error).message)
    },
  })

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-5">
        <h1 className="text-[24px] font-black text-[#111]">素材治理</h1>
        <p className="mt-1 text-[14px] text-[#666]">屏蔽违规素材</p>
      </div>

      <section className="rounded-2xl border border-black/6 bg-white p-5">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="h-7 w-7" />
          </div>
        ) : apiMissing ? (
          <div className="py-16 text-center">
            <p className="text-[15px] font-bold text-[#333]">暂无数据</p>
            <p className="mt-2 text-[13px] text-[#999]">
              素材治理 API 尚未就绪（404），将在后端并行上线后自动可用
            </p>
          </div>
        ) : error ? (
          <p className="py-12 text-center text-[14px] text-red-600">{(error as Error).message}</p>
        ) : !data?.items.length ? (
          <p className="py-12 text-center text-[14px] text-[#999]">暂无素材</p>
        ) : (
          <>
            <table className="w-full text-left text-[13px]">
              <thead className="text-[12px] text-[#999]">
                <tr>
                  <th className="py-2">名称</th>
                  <th>类型</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => {
                  const blocked = a.status === 'blocked' || a.status === 'banned'
                  return (
                    <tr key={a.id} className="border-t border-black/4">
                      <td className="py-2.5 font-bold">{a.name}</td>
                      <td className="text-[#666]">{a.assetType ?? a.type ?? '—'}</td>
                      <td>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                            blocked ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'
                          }`}
                        >
                          {a.status}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() =>
                            setConfirm({ id: a.id, action: blocked ? 'unblock' : 'block' })
                          }
                          className="rounded-lg border border-black/10 px-3 py-1.5 text-[12px] font-bold"
                        >
                          {blocked ? '解除屏蔽' : '屏蔽'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {(data.total ?? 0) > 20 ? (
              <div className="mt-4 flex items-center justify-between text-[13px] text-[#666]">
                <span>
                  第 {page} 页 · 共 {data.total} 条
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
                    disabled={page * 20 >= data.total}
                    onClick={() => setPage((p) => p + 1)}
                    className="h-8 rounded-lg border border-black/10 px-3 font-semibold disabled:opacity-40"
                  >
                    下一页
                  </button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </section>

      <ConfirmDialog
        open={!!confirm}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          if (confirm) moderate.mutate(confirm)
        }}
        title={confirm?.action === 'block' ? '屏蔽素材' : '解除屏蔽'}
        message={
          confirm?.action === 'block'
            ? '确定屏蔽该素材？用户将无法访问。'
            : '确定解除屏蔽该素材？'
        }
        danger={confirm?.action === 'block'}
      />
    </div>
  )
}
