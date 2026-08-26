import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Boxes, CheckCircle2, Clock, Ban, Users } from 'lucide-react'
import { api } from '@/lib/api'
import { Spinner } from '@/components/ui/Spinner'

type PubStats = {
  pending: number
  published: number
  rejected: number
  taken_down: number
}

export function AdminDashboardPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['admin-pub-stats'],
    queryFn: () => api<PubStats>('/publications/admin/stats'),
  })

  const { data: users } = useQuery({
    queryKey: ['admin-users-count'],
    queryFn: () =>
      api<{ items: unknown[]; total: number }>('/admin/users?page=1&pageSize=1'),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner className="h-8 w-8" />
      </div>
    )
  }

  const cards = [
    { label: '待审核', value: stats?.pending ?? 0, icon: Clock, tone: 'bg-amber-100 text-amber-700' },
    { label: '已发布', value: stats?.published ?? 0, icon: CheckCircle2, tone: 'bg-emerald-100 text-emerald-700' },
    { label: '已驳回', value: stats?.rejected ?? 0, icon: Ban, tone: 'bg-red-100 text-red-700' },
    { label: '已下架', value: stats?.taken_down ?? 0, icon: Boxes, tone: 'bg-slate-100 text-slate-600' },
  ]

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-6">
        <h1 className="text-[24px] font-black text-[#111]">仪表盘</h1>
        <p className="mt-1 text-[14px] text-[#666]">运营概览与待办入口</p>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-2xl border border-black/6 bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[13px] font-semibold text-[#777]">{c.label}</span>
              <span className={`inline-flex h-8 w-8 items-center justify-center rounded-xl ${c.tone}`}>
                <c.icon size={15} />
              </span>
            </div>
            <p className="text-[28px] font-black text-[#111]">{c.value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-black/6 bg-white p-5">
          <div className="mb-2 flex items-center gap-2">
            <Users size={16} className="text-[#666]" />
            <h2 className="text-[15px] font-bold text-[#111]">用户总量</h2>
          </div>
          <p className="text-[28px] font-black text-[#111]">{users?.total ?? '—'}</p>
          <Link
            to="/admin/users"
            className="mt-3 inline-flex items-center gap-1 text-[13px] font-semibold text-[#555] hover:text-[#111]"
          >
            查看用户 <ArrowRight size={14} />
          </Link>
        </div>

        <div className="rounded-2xl border border-black/6 bg-white p-5">
          <div className="mb-2 flex items-center gap-2">
            <Boxes size={16} className="text-[#666]" />
            <h2 className="text-[15px] font-bold text-[#111]">内容审核</h2>
          </div>
          <p className="text-[14px] text-[#666]">
            当前有 <span className="font-bold text-[#111]">{stats?.pending ?? 0}</span> 条待审核作品
          </p>
          <Link
            to="/admin/gallery-review"
            className="mt-3 inline-flex h-10 items-center gap-1.5 rounded-[12px] bg-[#111] px-4 text-[13px] font-bold text-white"
          >
            进入审核 <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  )
}
