import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Field, Input, Select } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'

type ModelRow = {
  id: number
  name: string
  modelType: string
  enabled: boolean
  basePrice: number
  provider?: string
}

export function AdminModelsPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [pricingId, setPricingId] = useState<number | null>(null)
  const [basePrice, setBasePrice] = useState('')
  const [form, setForm] = useState({ name: '', modelType: 'text', basePrice: '10' })

  const { data, isLoading } = useQuery({
    queryKey: ['admin-models'],
    queryFn: () => api<{ items: ModelRow[] }>('/admin/models'),
  })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api(`/admin/models/${id}`, { method: 'PUT', body: JSON.stringify({ enabled }) }),
    onSuccess: () => {
      toastSuccess('模型状态已更新')
      void qc.invalidateQueries({ queryKey: ['admin-models'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  const create = useMutation({
    mutationFn: () => {
      const modelType = form.modelType
      const provider =
        modelType === 'text'
          ? 'agnes-text'
          : modelType === 'image'
            ? 'agnes-image'
            : modelType === 'video'
              ? 'agnes-video'
              : modelType === 'audio'
                ? 'doubao-tts'
                : 'openai-text'
      return api('/admin/models', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name,
          modelType,
          provider,
          basePrice: Number(form.basePrice),
        }),
      })
    },
    onSuccess: () => {
      toastSuccess('模型已创建')
      setCreateOpen(false)
      setForm({ name: '', modelType: 'text', basePrice: '10' })
      void qc.invalidateQueries({ queryKey: ['admin-models'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  const updatePricing = useMutation({
    mutationFn: () =>
      api(`/admin/models/${pricingId}/pricing`, {
        method: 'PUT',
        body: JSON.stringify({ basePrice: Number(basePrice) }),
      }),
    onSuccess: () => {
      toastSuccess('定价已更新')
      setPricingId(null)
      void qc.invalidateQueries({ queryKey: ['admin-models'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-black text-[#111]">模型管理</h1>
          <p className="mt-1 text-[14px] text-[#666]">启用状态与基础定价</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>新增模型</Button>
      </div>

      <section className="rounded-2xl border border-black/6 bg-white p-5">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="h-7 w-7" />
          </div>
        ) : (
          <table className="w-full text-left text-[13px]">
            <thead className="text-[12px] text-[#999]">
              <tr>
                <th className="py-2">模型</th>
                <th>类型</th>
                <th>基础价</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((m) => (
                <tr key={m.id} className="border-t border-black/4">
                  <td className="py-2.5 font-bold">{m.name}</td>
                  <td className="text-[#666]">{m.modelType}</td>
                  <td>{m.basePrice} 点</td>
                  <td>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                        m.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      {m.enabled ? '启用' : '停用'}
                    </span>
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        onClick={() => toggle.mutate({ id: m.id, enabled: !m.enabled })}
                        className="rounded-lg border border-black/10 px-3 py-1.5 text-[12px] font-bold"
                      >
                        {m.enabled ? '停用' : '启用'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setPricingId(m.id)
                          setBasePrice(String(m.basePrice))
                        }}
                        className="rounded-lg border border-black/10 px-3 py-1.5 text-[12px] font-bold"
                      >
                        改价
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="新增模型">
        <div className="flex flex-col gap-3">
          <Field label="模型名称">
            <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </Field>
          <Field label="类型">
            <Select
              value={form.modelType}
              onChange={(e) => setForm((f) => ({ ...f, modelType: e.target.value }))}
            >
              <option value="text">文本</option>
              <option value="image">图片</option>
              <option value="video">视频</option>
              <option value="audio">音频</option>
            </Select>
          </Field>
          <Field label="基础价（点数）">
            <Input
              type="number"
              value={form.basePrice}
              onChange={(e) => setForm((f) => ({ ...f, basePrice: e.target.value }))}
            />
          </Field>
          <Button onClick={() => create.mutate()} disabled={!form.name.trim()}>
            保存
          </Button>
        </div>
      </Modal>

      <Modal open={pricingId != null} onClose={() => setPricingId(null)} title="修改定价">
        <div className="flex flex-col gap-3">
          <Field label="基础价（点数）">
            <Input type="number" value={basePrice} onChange={(e) => setBasePrice(e.target.value)} />
          </Field>
          <Button onClick={() => updatePricing.mutate()}>保存</Button>
        </div>
      </Modal>
    </div>
  )
}
