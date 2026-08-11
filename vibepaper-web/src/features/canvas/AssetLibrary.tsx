import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, X, Grid2X2, List, Download, Trash2, Pencil, Building2, Maximize2, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, assetUrl, getAccessToken, uploadAsset, ApiError } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { useAuthedMediaUrl } from '@/lib/media'
import { parseJsonPreserveIds, sid } from '@/lib/ids'
import type { AssetView, Id, PageResult } from '@/lib/types'
import { useCanvasStore } from './canvasStore'
import { toastError, toastSuccess } from '@/components/ui/Toast'

async function replaceAsset(id: Id, file: File) {
  const fd = new FormData()
  fd.append('file', file)
  const headers: Record<string, string> = {}
  const token = getAccessToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`/api/v1/assets/${sid(id)}/replace`, { method: 'POST', headers, body: fd })
  if (!res.ok) throw new ApiError(res.status, 'UPLOAD_FAILED', '替换失败')
  return parseJsonPreserveIds(await res.text())
}

export function AssetLibrary() {
  const open = useCanvasStore((s) => s.assetOpen)
  const setOpen = useCanvasStore((s) => s.setAssetOpen)
  const canvas = useCanvasStore((s) => s.canvas)
  const enterpriseId = useAuth((s) => s.user?.enterpriseId)
  const [mode, setMode] = useState<'grid' | 'list'>('grid')
  const [renameId, setRenameId] = useState<Id | null>(null)
  const [renameName, setRenameName] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<AssetView | null>(null)
  const [preview, setPreview] = useState<AssetView | null>(null)
  const [replaceId, setReplaceId] = useState<Id | null>(null)
  const replaceInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['assets'],
    queryFn: () => api<PageResult<AssetView>>('/assets?page=1&pageSize=100'),
    enabled: open,
  })

  useEffect(() => {
    const onUpdated = () => {
      if (open) void refetch()
    }
    window.addEventListener('vp-assets-updated', onUpdated)
    return () => window.removeEventListener('vp-assets-updated', onUpdated)
  }, [open, refetch])

  const upload = useMutation({
    mutationFn: (file: File) => uploadAsset(file, undefined, canvas?.canvas.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assets'] })
      toastSuccess('上传成功')
    },
    onError: (e) => toastError((e as Error).message),
  })

  const del = useMutation({
    mutationFn: (id: Id) =>
      api<{ references?: Array<{ canvasId?: Id; nodeId?: Id; type?: string }> }>(`/assets/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['assets'] })
      const n = res?.references?.length ?? 0
      toastSuccess(n > 0 ? `已删除（曾被 ${n} 处引用）` : '已删除')
      setDeleteTarget(null)
    },
    onError: (e) => toastError((e as Error).message),
  })

  const replace = useMutation({
    mutationFn: ({ id, file }: { id: Id; file: File }) => replaceAsset(id, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assets'] })
      toastSuccess('素材已替换')
      setReplaceId(null)
    },
    onError: (e) => toastError((e as Error).message),
  })

  const rename = useMutation({
    mutationFn: ({ id, name }: { id: Id; name: string }) =>
      api(`/assets/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assets'] })
      toastSuccess('已重命名')
    },
  })

  const toEnterprise = useMutation({
    mutationFn: (id: Id) =>
      api(`/assets/${id}/to-enterprise`, {
        method: 'POST',
        body: JSON.stringify({ enterpriseId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assets'] })
      toastSuccess('已添加到企业素材库')
    },
    onError: (e) => toastError((e as Error).message),
  })

  const download = (a: AssetView) => {
    const url = assetUrl(a.url)
    if (!url) return
    const link = document.createElement('a')
    link.href = url
    link.download = a.name
    link.click()
  }

  const importToCanvas = (a: AssetView) => {
    window.dispatchEvent(new CustomEvent('vp-add-asset-node', { detail: a }))
    toastSuccess('正在导入画布…')
  }

  const startReplace = (id: Id) => {
    setReplaceId(id)
    window.setTimeout(() => replaceInputRef.current?.click(), 0)
  }

  if (!open) return null
  return (
    <div className="absolute left-[72px] top-20 z-40 flex h-[calc(100%-104px)] w-80 flex-col rounded-2xl border border-black/8 bg-white shadow-[0_16px_48px_rgba(15,23,42,0.18)]">
      <input
        ref={replaceInputRef}
        type="file"
        accept="image/*,video/*,audio/*,text/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (!file || !replaceId) return
          replace.mutate({ id: replaceId, file })
        }}
      />
      <div className="flex items-center justify-between border-b border-black/6 px-3 py-2.5">
        <p className="text-[14px] font-bold text-[#111]">个人素材库</p>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMode('grid')}
            className={`rounded-lg p-1.5 ${mode === 'grid' ? 'bg-black/8 text-[#111]' : 'text-[#999]'}`}
          >
            <Grid2X2 size={14} />
          </button>
          <button
            onClick={() => setMode('list')}
            className={`rounded-lg p-1.5 ${mode === 'list' ? 'bg-black/8 text-[#111]' : 'text-[#999]'}`}
          >
            <List size={14} />
          </button>
          <button onClick={() => setOpen(false)} className="ml-1 rounded-lg p-1.5 text-[#888] hover:bg-black/5">
            <X size={14} />
          </button>
        </div>
      </div>
      <div className="flex items-center justify-between px-3 py-2">
        <label className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-[#111] px-3 py-1.5 text-[12px] font-bold text-white">
          <Upload size={13} /> 上传
          <input
            type="file"
            accept="image/*,video/*,audio/*,text/*"
            multiple
            className="hidden"
            onChange={(e) => Array.from(e.target.files ?? []).forEach((f) => upload.mutate(f))}
          />
        </label>
        <span className="text-[11px] text-[#999]">{data?.total ?? 0} 个素材</span>
      </div>
      <div className="flex-1 overflow-auto p-3">
        {isLoading ? (
          <p className="py-10 text-center text-[13px] text-[#999]">加载中…</p>
        ) : data?.items.length === 0 ? (
          <p className="py-10 text-center text-[13px] text-[#999]">暂无素材，上传或从画布卡片存入</p>
        ) : mode === 'grid' ? (
          <div className="grid grid-cols-2 gap-2">
            {data?.items.map((a) => (
              <div key={a.id} className="group relative overflow-hidden rounded-xl border border-black/8">
                <AssetThumb asset={a} onClick={() => importToCanvas(a)} />
                <div className="absolute right-1 top-1 flex flex-wrap justify-end gap-0.5 opacity-0 transition group-hover:opacity-100">
                  <MiniBtn title="导入画布" onClick={() => importToCanvas(a)}>
                    <Upload size={11} />
                  </MiniBtn>
                  <MiniBtn title="全屏预览" onClick={() => setPreview(a)}>
                    <Maximize2 size={11} />
                  </MiniBtn>
                  <MiniBtn title="下载" onClick={() => download(a)}>
                    <Download size={11} />
                  </MiniBtn>
                  <MiniBtn title="替换素材" onClick={() => startReplace(a.id)}>
                    <RefreshCw size={11} />
                  </MiniBtn>
                  {enterpriseId && !a.enterpriseId && (
                    <MiniBtn title="添加到企业素材库" onClick={() => toEnterprise.mutate(a.id)}>
                      <Building2 size={11} />
                    </MiniBtn>
                  )}
                  <MiniBtn
                    title="重命名"
                    onClick={() => {
                      setRenameId(a.id)
                      setRenameName(a.name)
                    }}
                  >
                    <Pencil size={11} />
                  </MiniBtn>
                  <MiniBtn danger title="删除" onClick={() => setDeleteTarget(a)}>
                    <Trash2 size={11} />
                  </MiniBtn>
                </div>
                <p className="truncate bg-black/50 px-1.5 py-0.5 text-[10px] font-semibold text-white">{a.name}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {data?.items.map((a) => (
              <div key={a.id} className="flex items-center gap-2 rounded-lg border border-black/6 px-2 py-1.5">
                <AssetThumb asset={a} className="h-10 w-10" onClick={() => importToCanvas(a)} />
                <p className="flex-1 truncate text-[12px] font-semibold text-[#444]">{a.name}</p>
                <button onClick={() => importToCanvas(a)} className="rounded p-1 text-[#888] hover:text-[#111]" title="导入画布">
                  <Upload size={12} />
                </button>
                <button onClick={() => setPreview(a)} className="rounded p-1 text-[#888] hover:text-[#111]" title="全屏预览">
                  <Maximize2 size={12} />
                </button>
                {enterpriseId && !a.enterpriseId && (
                  <button
                    onClick={() => toEnterprise.mutate(a.id)}
                    className="rounded p-1 text-[#888] hover:text-[#111]"
                    title="添加到企业素材库"
                  >
                    <Building2 size={12} />
                  </button>
                )}
                <button onClick={() => download(a)} className="rounded p-1 text-[#888] hover:text-[#111]">
                  <Download size={12} />
                </button>
                <button onClick={() => startReplace(a.id)} className="rounded p-1 text-[#888] hover:text-[#111]" title="替换">
                  <RefreshCw size={12} />
                </button>
                <button
                  onClick={() => {
                    setRenameId(a.id)
                    setRenameName(a.name)
                  }}
                  className="rounded p-1 text-[#888] hover:text-[#111]"
                >
                  <Pencil size={12} />
                </button>
                <button onClick={() => setDeleteTarget(a)} className="rounded p-1 text-[#888] hover:text-red-600">
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      {renameId && (
        <div className="border-t border-black/6 p-3">
          <input
            autoFocus
            value={renameName}
            onChange={(e) => setRenameName(e.target.value)}
            className="h-9 w-full rounded-lg border border-black/10 px-2 text-[13px]"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                rename.mutate({ id: renameId, name: renameName })
                setRenameId(null)
              }
            }}
          />
        </div>
      )}

      {deleteTarget && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full rounded-2xl bg-white p-4 shadow-xl">
            <p className="text-[15px] font-bold text-[#111]">确认删除素材？</p>
            <p className="mt-2 text-[12px] text-[#666]">
              「{deleteTarget.name}」删除后不可恢复。若已被画布节点引用，相关节点将失去该素材关联。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="h-8 rounded-full px-3 text-[12px] font-semibold text-[#555]"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => del.mutate(deleteTarget.id)}
                className="h-8 rounded-full bg-red-600 px-3 text-[12px] font-bold text-white"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}

      {preview && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/85 p-6" onClick={() => setPreview(null)}>
          <button
            type="button"
            className="absolute right-5 top-5 rounded-full bg-white/10 p-2 text-white"
            onClick={() => setPreview(null)}
          >
            <X size={18} />
          </button>
          <PreviewMedia asset={preview} />
        </div>
      )}
    </div>
  )
}

function MiniBtn({
  title,
  danger,
  onClick,
  children,
}: {
  title: string
  danger?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`rounded-md bg-white/95 p-1 shadow ${danger ? 'text-red-500' : 'text-[#444]'}`}
    >
      {children}
    </button>
  )
}

function AssetThumb({
  asset,
  onClick,
  className = '',
}: {
  asset: AssetView
  onClick: () => void
  className?: string
}) {
  const raw = asset.thumbnailUrl ?? asset.url
  const url = useAuthedMediaUrl(raw)
  if ((asset.assetType === 'image' || /\.(png|jpe?g|gif|webp)(\?|$)/i.test(raw ?? '')) && url) {
    return (
      <img
        src={url}
        alt={asset.name}
        className={`h-20 w-full cursor-grab object-cover ${className}`}
        onClick={onClick}
        draggable
        onDragStart={(e) => e.dataTransfer.setData('application/json', JSON.stringify(asset))}
      />
    )
  }
  return (
    <div
      className={`flex h-20 w-full cursor-grab items-center justify-center bg-slate-100 text-[10px] font-bold uppercase text-[#888] ${className}`}
      onClick={onClick}
      draggable
      onDragStart={(e) => e.dataTransfer.setData('application/json', JSON.stringify(asset))}
    >
      {asset.assetType}
    </div>
  )
}

function PreviewMedia({ asset }: { asset: AssetView }) {
  const url = useAuthedMediaUrl(asset.url)
  if (!url) return <p className="text-white">无法预览</p>
  if (asset.assetType === 'video') {
    return <video src={url} controls autoPlay className="max-h-full max-w-full rounded-xl" onClick={(e) => e.stopPropagation()} />
  }
  if (asset.assetType === 'audio') {
    return <audio src={url} controls className="w-full max-w-lg" onClick={(e) => e.stopPropagation()} />
  }
  return (
    <img
      src={url}
      alt={asset.name}
      className="max-h-full max-w-full rounded-xl object-contain"
      onClick={(e) => e.stopPropagation()}
    />
  )
}
