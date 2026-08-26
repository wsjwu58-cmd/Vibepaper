import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { RechargePackage } from '@/lib/types'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import { Field, Input, Select } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'

type PackageForm = {
  name: string
  points: string
  priceCny: string
  enabled: boolean
}

const emptyForm: PackageForm = { name: '', points: '100', priceCny: '10', enabled: true }

export function AdminPackagesPage() {
  const qc = useQueryClient()
  const [modal, setModal] = useState<'create' | number | null>(null)
  const [form, setForm] = useState<PackageForm>(emptyForm)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const { data: packages, isLoading } = useQuery({
    queryKey: ['packages'],
    queryFn: () => api<RechargePackage[]>('/packages'),
  })

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name,
        points: Number(form.points),
        priceCny: Number(form.priceCny),
        enabled: form.enabled,
      }
      if (modal === 'create') {
        return api('/admin/packages', { method: 'POST', body: JSON.stringify(body) })
      }
      return api(`/admin/packages/${modal}`, { method: 'PUT', body: JSON.stringify(body) })
    },
    onSuccess: () => {
      toastSuccess(modal === 'create' ? '套餐已创建' : '套餐已更新')
      setModal(null)
      void qc.invalidateQueries({ queryKey: ['packages'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/packages/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toastSuccess('套餐已删除')
      void qc.invalidateQueries({ queryKey: ['packages'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  const openCreate = () => {
    setForm(emptyForm)
    setModal('create')
  }

  const openEdit = (p: RechargePackage) => {
    setForm({
      name: p.name,
      points: String(p.points),
      priceCny: String(p.priceCny),
      enabled: p.enabled,
    })
    setModal(Number(p.id))
  }

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-black text-[#111]">充值套餐</h1>
          <p className="mt-1 text-[14px] text-[#666]">管理点数包与售价</p>
        </div>
        <Button onClick={openCreate}>新增套餐</Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-7 w-7" />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {packages?.map((p) => (
            <div key={p.id} className="rounded-2xl border border-black/6 bg-white p-5">
              <p className="text-[16px] font-bold text-[#111]">{p.name}</p>
              <p className="mt-1 text-[13px] text-[#666]">
                {p.points} 点 · ¥{p.priceCny}
              </p>
              <span
                className={`mt-3 inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${
                  p.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                }`}
              >
                {p.enabled ? '上架中' : '已下架'}
              </span>
              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  onClick={() => openEdit(p)}
                  className="h-9 flex-1 rounded-xl border border-black/10 text-[13px] font-bold hover:bg-black/[0.03]"
                >
                  编辑
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteId(Number(p.id))}
                  className="h-9 rounded-xl border border-red-200 px-3 text-[13px] font-bold text-red-600 hover:bg-red-50"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={modal != null}
        onClose={() => setModal(null)}
        title={modal === 'create' ? '新增套餐' : '编辑套餐'}
      >
        <div className="flex flex-col gap-3">
          <Field label="名称">
            <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </Field>
          <Field label="点数">
            <Input
              type="number"
              value={form.points}
              onChange={(e) => setForm((f) => ({ ...f, points: e.target.value }))}
            />
          </Field>
          <Field label="售价（元）">
            <Input
              type="number"
              value={form.priceCny}
              onChange={(e) => setForm((f) => ({ ...f, priceCny: e.target.value }))}
            />
          </Field>
          <Field label="状态">
            <Select
              value={form.enabled ? '1' : '0'}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.value === '1' }))}
            >
              <option value="1">上架</option>
              <option value="0">下架</option>
            </Select>
          </Field>
          <Button onClick={() => save.mutate()} disabled={!form.name.trim()}>
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
        title="删除套餐"
        message="确定删除该充值套餐？此操作不可恢复。"
        danger
      />
    </div>
  )
}
