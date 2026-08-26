import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { Field, Input } from '@/components/ui/Input'
import { Spinner } from '@/components/ui/Spinner'
import { toastError, toastSuccess } from '@/components/ui/Toast'

type ApiKeyRow = {
  id: number
  name: string
  provider: string
  enabled: boolean
  rateLimit: number
  baseUrl?: string
}

type FormState = {
  name: string
  provider: string
  apiKey: string
  baseUrl: string
  rateLimit: string
}

const empty: FormState = {
  name: '',
  provider: '',
  apiKey: '',
  baseUrl: '',
  rateLimit: '60',
}

export function AdminApiKeysPage() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(empty)

  const { data: keys, isLoading } = useQuery({
    queryKey: ['admin-keys'],
    queryFn: () => api<ApiKeyRow[]>('/admin/api-keys'),
  })

  const create = useMutation({
    mutationFn: () =>
      api('/admin/api-keys', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name,
          provider: form.provider,
          apiKey: form.apiKey,
          baseUrl: form.baseUrl || undefined,
          rateLimit: Number(form.rateLimit),
        }),
      }),
    onSuccess: () => {
      toastSuccess('API Key 已创建')
      setOpen(false)
      setForm(empty)
      void qc.invalidateQueries({ queryKey: ['admin-keys'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api(`/admin/api-keys/${id}/toggle`, {
        method: 'PUT',
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () => {
      toastSuccess('状态已更新')
      void qc.invalidateQueries({ queryKey: ['admin-keys'] })
    },
    onError: (e) => toastError((e as Error).message),
  })

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-[24px] font-black text-[#111]">API Keys</h1>
          <p className="mt-1 text-[14px] text-[#666]">第三方供应商密钥管理</p>
        </div>
        <Button
          onClick={() => {
            setForm(empty)
            setOpen(true)
          }}
        >
          新增 Key
        </Button>
      </div>

      <section className="rounded-2xl border border-black/6 bg-white p-5">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Spinner className="h-7 w-7" />
          </div>
        ) : !keys?.length ? (
          <p className="py-12 text-center text-[14px] text-[#999]">暂无 API Key</p>
        ) : (
          <div className="divide-y divide-black/4">
            {keys.map((k) => (
              <div key={k.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-[#333]">
                    {k.name} · {k.provider}
                  </p>
                  <p className="text-[12px] text-[#999]">
                    限流 {k.rateLimit}/分
                    {k.baseUrl ? ` · ${k.baseUrl}` : ''}
                  </p>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                    k.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                  }`}
                >
                  {k.enabled ? '启用' : '停用'}
                </span>
                <button
                  type="button"
                  onClick={() => toggle.mutate({ id: k.id, enabled: !k.enabled })}
                  className="rounded-lg border border-black/10 px-3 py-1.5 text-[12px] font-bold"
                >
                  {k.enabled ? '停用' : '启用'}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <Modal open={open} onClose={() => setOpen(false)} title="新增 API Key">
        <div className="flex flex-col gap-3">
          <Field label="名称">
            <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </Field>
          <Field label="供应商">
            <Input
              value={form.provider}
              onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))}
              placeholder="如 openai / agnes"
            />
          </Field>
          <Field label="API Key">
            <Input
              type="password"
              value={form.apiKey}
              onChange={(e) => setForm((f) => ({ ...f, apiKey: e.target.value }))}
            />
          </Field>
          <Field label="Base URL（可选）">
            <Input
              value={form.baseUrl}
              onChange={(e) => setForm((f) => ({ ...f, baseUrl: e.target.value }))}
            />
          </Field>
          <Field label="限流（次/分）">
            <Input
              type="number"
              value={form.rateLimit}
              onChange={(e) => setForm((f) => ({ ...f, rateLimit: e.target.value }))}
            />
          </Field>
          <Button
            onClick={() => create.mutate()}
            disabled={!form.name.trim() || !form.provider.trim() || !form.apiKey.trim()}
          >
            保存
          </Button>
        </div>
      </Modal>
    </div>
  )
}
