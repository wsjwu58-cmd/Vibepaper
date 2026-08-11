import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Copy, RotateCcw, RefreshCw } from 'lucide-react'
import { api, assetUrl } from '@/lib/api'
import type { GenerationTask, PageResult } from '@/lib/types'
import { Input, Select } from '@/components/ui/Input'
import { toastSuccess } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'

const statusMeta: Record<string, { text: string; cls: string }> = {
  queued: { text: '排队中', cls: 'bg-amber-100 text-amber-700' },
  running: { text: '执行中', cls: 'bg-blue-100 text-blue-700' },
  succeeded: { text: '成功', cls: 'bg-emerald-100 text-emerald-700' },
  failed: { text: '失败', cls: 'bg-red-100 text-red-700' },
  cancelled: { text: '已取消', cls: 'bg-slate-200 text-slate-600' },
  expired: { text: '已过期', cls: 'bg-slate-200 text-slate-600' },
}

export function HistoryPage() {
  const [keyword, setKeyword] = useState('')
  const [model, setModel] = useState('')
  const [taskType, setTaskType] = useState('')
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)

  const params = new URLSearchParams({ page: String(page), pageSize: '20' })
  if (keyword) params.set('keyword', keyword)
  if (model) params.set('model', model)
  if (taskType) params.set('task_type', taskType)
  if (status) params.set('status', status)
  if (from) params.set('date_from', new Date(from).toISOString())
  if (to) params.set('date_to', new Date(`${to}T23:59:59`).toISOString())

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['history', params.toString()],
    queryFn: () => api<PageResult<GenerationTask>>(`/tasks?${params.toString()}`),
  })

  const reset = () => {
    setKeyword('')
    setModel('')
    setTaskType('')
    setStatus('')
    setFrom('')
    setTo('')
    setPage(1)
  }

  return (
    <div className="w-full">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-[24px] font-black text-[#111]">历史记录</h1>
          <p className="mt-1 text-[13px] text-[#666]">查看所有画布的生成任务执行情况</p>
        </div>
        <div className="flex gap-2">
          <button onClick={reset} className="flex h-10 items-center gap-1.5 rounded-xl border border-black/10 px-3.5 text-[13px] font-semibold hover:bg-black/[0.03]">
            <RotateCcw size={14} /> 重置
          </button>
          <button onClick={() => void refetch()} className="flex h-10 items-center gap-1.5 rounded-xl border border-black/10 px-3.5 text-[13px] font-semibold hover:bg-black/[0.03]">
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} /> 刷新
          </button>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 rounded-2xl border border-black/6 bg-white p-3 md:grid-cols-6">
        <div className="relative col-span-2">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#999]" />
          <Input className="h-9 pl-8" placeholder="搜索提示词" value={keyword} onChange={(e) => { setKeyword(e.target.value); setPage(1) }} />
        </div>
        <Input className="h-9" placeholder="模型" value={model} onChange={(e) => { setModel(e.target.value); setPage(1) }} />
        <Select className="h-9" value={taskType} onChange={(e) => { setTaskType(e.target.value); setPage(1) }}>
          <option value="">全部模态</option>
          <option value="text">文本</option>
          <option value="image">图片</option>
          <option value="video">视频</option>
          <option value="audio">音频</option>
        </Select>
        <Select className="h-9" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
          <option value="">全部状态</option>
          {Object.entries(statusMeta).map(([k, v]) => (
            <option key={k} value={k}>{v.text}</option>
          ))}
        </Select>
        <div className="flex gap-1">
          <input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1) }} className="h-9 flex-1 rounded-lg border border-black/12 px-2 text-[12px]" />
          <input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(1) }} className="h-9 flex-1 rounded-lg border border-black/12 px-2 text-[12px]" />
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20"><Spinner className="h-7 w-7" /></div>
      ) : data?.items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-black/15 py-16 text-center text-[14px] text-[#999]">暂无任务记录</div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-black/6 bg-white">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-black/6 bg-slate-50 text-[12px] text-[#777]">
              <tr>
                <th className="px-3 py-2.5">时间</th>
                <th className="px-3 py-2.5">结果</th>
                <th className="px-3 py-2.5">模态</th>
                <th className="px-3 py-2.5">模型</th>
                <th className="px-3 py-2.5">点数</th>
                <th className="px-3 py-2.5">提示词</th>
                <th className="px-3 py-2.5">状态</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((t) => {
                const out = t.outputs?.[0]
                return (
                  <tr key={t.taskId} className="border-b border-black/4 hover:bg-slate-50/60">
                    <td className="whitespace-nowrap px-3 py-2.5 text-[#777]">
                      {t.createdAt ? new Date(t.createdAt).toLocaleString('zh-CN') : ''}
                    </td>
                    <td className="px-3 py-2.5">
                      {out?.url ? (
                        t.modelType === 'image' ? (
                          <img src={assetUrl(out.url)} alt="" className="h-10 w-14 rounded-lg object-cover" />
                        ) : (
                          <a href={assetUrl(out.url)} target="_blank" rel="noreferrer" className="text-[12px] font-semibold text-blue-600 hover:underline">
                            查看结果
                          </a>
                        )
                      ) : (
                        <span className="text-[#ccc]">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 font-semibold text-[#555]">{t.modelType}</td>
                    <td className="px-3 py-2.5 text-[#555]">{t.modelType}</td>
                    <td className="px-3 py-2.5 font-bold text-[#111]">{t.actualCost || t.estimatedCost}</td>
                    <td className="max-w-56 px-3 py-2.5">
                      <div className="flex items-center gap-1">
                        <span className="truncate text-[#666]">{t.prompt ?? ''}</span>
                        {t.prompt && (
                          <button onClick={() => { navigator.clipboard?.writeText(t.prompt ?? ''); toastSuccess('提示词已复制') }} className="shrink-0 rounded p-1 text-[#999] hover:text-[#111]">
                            <Copy size={12} />
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${statusMeta[t.status]?.cls ?? 'bg-slate-100 text-slate-500'}`}>
                        {statusMeta[t.status]?.text ?? t.status}
                      </span>
                      {t.status === 'failed' && t.errorMessage && <p className="mt-0.5 max-w-32 truncate text-[10px] text-red-400">{t.errorMessage}</p>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="flex items-center justify-between px-3 py-2.5 text-[12px] text-[#777]">
            <span>共 {data?.total ?? 0} 条</span>
            <div className="flex gap-1">
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-black/10 px-3 py-1 disabled:opacity-40">上一页</button>
              <button disabled={(data?.items.length ?? 0) < 20} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-black/10 px-3 py-1 disabled:opacity-40">下一页</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
