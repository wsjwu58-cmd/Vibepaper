import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/Modal'
import { Field, Input, Select } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'

type UserRow = {
  id: number
  nickname: string
  email: string
  role: string
  status: string
  createdAt?: string
}

type UserDetail = UserRow & {
  phone?: string
  lastLoginAt?: string
  balance?: number
  frozenPoints?: number
}

export function AdminUsersPage() {
  const qc = useQueryClient()
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [applied, setApplied] = useState({ keyword: '', status: '' })
  const [detailId, setDetailId] = useState<number | null>(null)
  const [banConfirm, setBanConfirm] = useState<{ id: number; status: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users', applied.keyword, applied.status, page],
    queryFn: () => {
      const qs = new URLSearchParams({ page: String(page), pageSize: '20' })
      if (applied.keyword) qs.set('keyword', applied.keyword)
      if (applied.status) qs.set('status', applied.status)
      return api<{ items: UserRow[]; total: number }>(`/admin/users?${qs}`)
    },
  })

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['admin-user', detailId],
    queryFn: () => api<UserDetail>(`/admin/users/${detailId}`),
    enabled: detailId != null,
  })

  const setStatusMut = useMutation({
    mutationFn: ({ id, status: s }: { id: number; status: string }) =>
      api(`/admin/users/${id}/status`, { method: 'PUT', body: JSON.stringify({ status: s }) }),
    onSuccess: () => {
      toastSuccess('状态已更新')
      void qc.invalidateQueries({ queryKey: ['admin-users'] })
      void qc.invalidateQueries({ queryKey: ['admin-user'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  const changeStatus = (id: number, next: string) => {
    if (next === 'banned') {
      setBanConfirm({ id, status: next })
      return
    }
    setStatusMut.mutate({ id, status: next })
  }

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-5">
        <h1 className="text-[24px] font-black text-[#111]">用户管理</h1>
        <p className="mt-1 text-[14px] text-[#666]">共 {data?.total ?? 0} 位用户</p>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#999]" />
          <Input
            className="pl-9"
            placeholder="搜索昵称 / 邮箱"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setApplied({ keyword, status })
                setPage(1)
              }
            }}
          />
        </div>
        <Select
          className="w-[140px]"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="active">正常</option>
          <option value="disabled">禁用</option>
          <option value="banned">封禁</option>
        </Select>
        <Button
          onClick={() => {
            setApplied({ keyword, status })
            setPage(1)
          }}
        >
          查询
        </Button>
      </div>

      <section className="rounded-2xl border border-black/6 bg-white">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="h-7 w-7" />
          </div>
        ) : (
          <table className="w-full text-left text-[13px]">
            <thead className="text-[12px] text-[#999]">
              <tr className="border-b border-black/6">
                <th className="px-4 py-3">昵称</th>
                <th>邮箱</th>
                <th>角色</th>
                <th>状态</th>
                <th className="pr-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((u) => (
                <tr key={u.id} className="border-t border-black/4 hover:bg-black/[0.02]">
                  <td className="cursor-pointer px-4 py-2.5 font-bold" onClick={() => setDetailId(u.id)}>
                    {u.nickname}
                  </td>
                  <td className="text-[#666]">{u.email}</td>
                  <td>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold">{u.role}</span>
                  </td>
                  <td className="text-[#777]">{u.status}</td>
                  <td className="pr-4">
                    <select
                      value={u.status}
                      onChange={(e) => changeStatus(u.id, e.target.value)}
                      className="h-8 rounded-lg border border-black/10 px-2 text-[12px]"
                    >
                      <option value="active">正常</option>
                      <option value="disabled">禁用</option>
                      <option value="banned">封禁</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {(data?.total ?? 0) > 20 ? (
          <div className="flex items-center justify-between border-t border-black/6 px-4 py-3 text-[13px] text-[#666]">
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

      {detailId != null ? (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={() => setDetailId(null)}>
          <aside
            className="flex h-full w-full max-w-md flex-col bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-black/6 px-5 py-4">
              <h2 className="text-[16px] font-bold text-[#111]">用户详情</h2>
              <button type="button" onClick={() => setDetailId(null)} className="rounded-full p-2 hover:bg-black/5">
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {detailLoading || !detail ? (
                <div className="flex justify-center py-12">
                  <Spinner className="h-7 w-7" />
                </div>
              ) : (
                <div className="space-y-3 text-[14px]">
                  <Row label="昵称" value={detail.nickname} />
                  <Row label="邮箱" value={detail.email} />
                  <Row label="角色" value={detail.role} />
                  <Row label="状态" value={detail.status} />
                  {detail.phone ? <Row label="手机" value={detail.phone} /> : null}
                  {detail.balance != null ? <Row label="余额" value={`${detail.balance} 点`} /> : null}
                  {detail.frozenPoints != null ? (
                    <Row label="冻结" value={`${detail.frozenPoints} 点`} />
                  ) : null}
                  {detail.createdAt ? (
                    <Row label="注册" value={new Date(detail.createdAt).toLocaleString('zh-CN')} />
                  ) : null}
                  <Field label="变更状态">
                    <Select
                      value={detail.status}
                      onChange={(e) => changeStatus(detail.id, e.target.value)}
                    >
                      <option value="active">正常</option>
                      <option value="disabled">禁用</option>
                      <option value="banned">封禁</option>
                    </Select>
                  </Field>
                </div>
              )}
            </div>
          </aside>
        </div>
      ) : null}

      <ConfirmDialog
        open={!!banConfirm}
        onClose={() => setBanConfirm(null)}
        onConfirm={() => {
          if (banConfirm) setStatusMut.mutate(banConfirm)
        }}
        title="确认封禁"
        message="封禁后该用户将无法登录，确定继续？"
        danger
      />
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className={cn('flex items-start justify-between gap-3 border-b border-black/4 py-2')}>
      <span className="text-[12px] font-semibold text-[#999]">{label}</span>
      <span className="text-right font-semibold text-[#333]">{value}</span>
    </div>
  )
}
