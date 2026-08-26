import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Spinner } from '@/components/ui/Spinner'
import { cn } from '@/lib/cn'

type TxRow = {
  id: number
  orderNo: string
  userId: number
  points: number
  amountCny: number
  status: string
  createdAt: string
}

const STATUS_FILTERS = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待支付' },
  { key: 'success', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'cancelled', label: '已取消' },
]

export function AdminTransactionsPage() {
  const [status, setStatus] = useState('')

  const { data: txs, isLoading } = useQuery({
    queryKey: ['admin-tx', status],
    queryFn: () => {
      const qs = status ? `?status=${encodeURIComponent(status)}` : ''
      return api<TxRow[]>(`/admin/transactions${qs}`)
    },
  })

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-5">
        <h1 className="text-[24px] font-black text-[#111]">交易记录</h1>
        <p className="mt-1 text-[14px] text-[#666]">充值与订阅订单</p>
      </div>

      <div className="mb-4 flex flex-wrap gap-1 rounded-2xl border border-black/6 bg-white p-1.5">
        {STATUS_FILTERS.map((t) => (
          <button
            key={t.key || 'all'}
            type="button"
            onClick={() => setStatus(t.key)}
            className={cn(
              'h-9 rounded-xl px-3.5 text-[13px] font-bold',
              status === t.key ? 'bg-[#111] text-white' : 'text-[#666] hover:bg-black/[0.04]',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <section className="rounded-2xl border border-black/6 bg-white p-5">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="h-7 w-7" />
          </div>
        ) : !txs?.length ? (
          <p className="py-12 text-center text-[14px] text-[#999]">暂无交易</p>
        ) : (
          <table className="w-full text-left text-[13px]">
            <thead className="text-[12px] text-[#999]">
              <tr>
                <th className="py-2">订单号</th>
                <th>用户</th>
                <th>点数</th>
                <th>金额</th>
                <th>状态</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {txs.map((t) => (
                <tr key={t.id} className="border-t border-black/4">
                  <td className="py-2.5 text-[#777]">{t.orderNo}</td>
                  <td className="text-[#555]">#{t.userId}</td>
                  <td className="font-bold">{t.points}</td>
                  <td>¥{t.amountCny}</td>
                  <td>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                        t.status === 'success'
                          ? 'bg-emerald-100 text-emerald-700'
                          : t.status === 'failed'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-amber-100 text-amber-700'
                      }`}
                    >
                      {t.status}
                    </span>
                  </td>
                  <td className="text-[#999]">{new Date(t.createdAt).toLocaleString('zh-CN')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
