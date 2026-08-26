import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { PageResult } from '@/lib/types'
import { Button } from '@/components/ui/Button'
import { Field, Input } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'

type AuditLog = {
  id: number
  operatorId: number
  action: string
  targetType: string
  targetId?: number
  detail?: string
  createdAt: string
}

export function AdminAuditPage() {
  const [action, setAction] = useState('')
  const [operatorId, setOperatorId] = useState('')
  const [page, setPage] = useState(1)
  const [applied, setApplied] = useState({ action: '', operatorId: '' })

  const { data, isLoading } = useQuery({
    queryKey: ['admin-audit', applied.action, applied.operatorId, page],
    queryFn: () => {
      const qs = new URLSearchParams({ page: String(page), pageSize: '20' })
      if (applied.action) qs.set('action', applied.action)
      if (applied.operatorId) qs.set('operatorId', applied.operatorId)
      return api<PageResult<AuditLog>>(`/admin/audit-logs?${qs}`)
    },
  })

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-5">
        <h1 className="text-[24px] font-black text-[#111]">审计日志</h1>
        <p className="mt-1 text-[14px] text-[#666]">运营操作留痕</p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="w-[200px]">
          <Field label="动作">
            <Input
              value={action}
              onChange={(e) => setAction(e.target.value)}
              placeholder="如 approve / ban"
            />
          </Field>
        </div>
        <div className="w-[160px]">
          <Field label="操作人 ID">
            <Input
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              placeholder="可选"
            />
          </Field>
        </div>
        <div className="flex items-end">
          <Button
            onClick={() => {
              setApplied({ action, operatorId })
              setPage(1)
            }}
          >
            查询
          </Button>
        </div>
      </div>

      <section className="rounded-2xl border border-black/6 bg-white p-5">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="h-7 w-7" />
          </div>
        ) : !data?.items.length ? (
          <p className="py-12 text-center text-[14px] text-[#999]">暂无日志</p>
        ) : (
          <table className="w-full text-left text-[13px]">
            <thead className="text-[12px] text-[#999]">
              <tr>
                <th className="py-2">操作人</th>
                <th>动作</th>
                <th>对象</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id} className="border-t border-black/4">
                  <td className="py-2.5 text-[#777]">{a.operatorId ?? '—'}</td>
                  <td className="font-bold">{a.action}</td>
                  <td className="text-[#555]">
                    {a.targetType}
                    {a.targetId != null ? ` #${a.targetId}` : ''}
                  </td>
                  <td className="text-[#999]">{new Date(a.createdAt).toLocaleString('zh-CN')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {(data?.total ?? 0) > 20 ? (
          <div className="mt-4 flex items-center justify-between text-[13px] text-[#666]">
            <span>
              第 {page} 页 · 共 {data?.total} 条
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
    </div>
  )
}
