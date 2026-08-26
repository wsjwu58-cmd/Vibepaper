import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { PageResult } from '@/lib/types'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import { Field, Input, Select, Textarea } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'

type Announcement = {
  id: number
  title: string
  content: string
  status: string
  createdAt?: string
}

type FormState = { title: string; content: string; status: string }

const empty: FormState = { title: '', content: '', status: 'draft' }

export function AdminAnnouncementsPage() {
  const qc = useQueryClient()
  const [modal, setModal] = useState<'create' | number | null>(null)
  const [form, setForm] = useState<FormState>(empty)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['admin-ann'],
    queryFn: () => api<PageResult<Announcement>>('/admin/announcements'),
  })

  const save = useMutation({
    mutationFn: () => {
      const body = JSON.stringify({
        title: form.title,
        content: form.content,
        status: form.status,
      })
      if (modal === 'create') {
        return api('/admin/announcements', { method: 'POST', body })
      }
      return api(`/admin/announcements/${modal}`, { method: 'PUT', body })
    },
    onSuccess: () => {
      toastSuccess(modal === 'create' ? '公告已创建' : '公告已更新')
      setModal(null)
      void qc.invalidateQueries({ queryKey: ['admin-ann'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/announcements/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toastSuccess('公告已删除')
      void qc.invalidateQueries({ queryKey: ['admin-ann'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  const openCreate = () => {
    setForm(empty)
    setModal('create')
  }

  const openEdit = (a: Announcement) => {
    setForm({ title: a.title, content: a.content, status: a.status })
    setModal(a.id)
  }

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-black text-[#111]">公告管理</h1>
          <p className="mt-1 text-[14px] text-[#666]">发布、编辑与下线公告</p>
        </div>
        <Button onClick={openCreate}>新建公告</Button>
      </div>

      <section className="rounded-2xl border border-black/6 bg-white p-5">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="h-7 w-7" />
          </div>
        ) : !data?.items.length ? (
          <p className="py-12 text-center text-[14px] text-[#999]">暂无公告</p>
        ) : (
          <div className="divide-y divide-black/4">
            {data.items.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-[#333]">{a.title}</p>
                  <p className="mt-0.5 line-clamp-1 text-[12px] text-[#999]">{a.content}</p>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-[#666]">
                  {a.status}
                </span>
                <button
                  type="button"
                  onClick={() => openEdit(a)}
                  className="rounded-lg border border-black/10 px-3 py-1.5 text-[12px] font-bold"
                >
                  编辑
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteId(a.id)}
                  className="rounded-lg border border-red-200 px-3 py-1.5 text-[12px] font-bold text-red-600"
                >
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <Modal
        open={modal != null}
        onClose={() => setModal(null)}
        title={modal === 'create' ? '新建公告' : '编辑公告'}
      >
        <div className="flex flex-col gap-3">
          <Field label="标题">
            <Input value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
          </Field>
          <Field label="内容">
            <Textarea
              value={form.content}
              onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            />
          </Field>
          <Field label="状态">
            <Select
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
            >
              <option value="draft">草稿</option>
              <option value="published">已发布</option>
              <option value="offline">已下线</option>
            </Select>
          </Field>
          <Button onClick={() => save.mutate()} disabled={!form.title.trim() || !form.content.trim()}>
            保存
          </Button>
        </div>
      </Modal>

      <ConfirmDialog
        open={deleteId != null}
        onClose={() => setDeleteId(null)}
        onConfirm={() => {
          if (deleteId != null) remove.mutate(deleteId)
        }}
        title="删除公告"
        message="确定删除该公告？"
        danger
      />
    </div>
  )
}
