import { ArrowLeft, Bird, FileText, ImagePlus, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { api, uploadAsset } from '@/lib/api'
import { toastError, toastSuccess } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'

type AssetView = { url?: string; name?: string }

export function PublishToPaperHubPanel({
  canvasId,
  defaultTitle,
  onBack,
  onDone,
}: {
  canvasId: string | number
  defaultTitle?: string
  onBack: () => void
  onDone: () => void
}) {
  const [title, setTitle] = useState(defaultTitle ?? '')
  const [description, setDescription] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [resultFiles, setResultFiles] = useState<File[]>([])
  const [coverFile, setCoverFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const resultRef = useRef<HTMLInputElement>(null)
  const coverRef = useRef<HTMLInputElement>(null)

  const canSubmit = title.trim().length > 0 && resultFiles.length > 0 && !!coverFile && !busy

  const addTag = () => {
    const parts = tagInput
      .split(/[,，\s]+/)
      .map((t) => t.trim())
      .filter(Boolean)
    if (parts.length === 0) return
    setTags((prev) => {
      const next = [...prev]
      for (const p of parts) {
        if (!next.includes(p) && next.length < 10) next.push(p)
      }
      return next
    })
    setTagInput('')
  }

  const onSubmit = async () => {
    if (!canSubmit || !coverFile) return
    setBusy(true)
    try {
      const cover = (await uploadAsset(coverFile, 'image', canvasId)) as AssetView
      const resultUrls: string[] = []
      for (const file of resultFiles) {
        const asset = (await uploadAsset(file, undefined, canvasId)) as AssetView
        if (asset.url) resultUrls.push(String(asset.url))
      }
      if (!cover.url || resultUrls.length === 0) {
        throw new Error('上传文件失败，请重试')
      }
      await api('/publications', {
        method: 'POST',
        body: JSON.stringify({
          canvasId,
          title: title.trim(),
          description: description.trim() || undefined,
          tags,
          thumbnailUrl: cover.url,
          previewAssetUrl: resultUrls[0],
          resultAssetUrls: resultUrls,
        }),
      })
      toastSuccess('已提交 PaperHub，等待审核')
      onDone()
    } catch (e) {
      toastError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="py-1">
      <button
        type="button"
        onClick={onBack}
        className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-semibold text-[#666] hover:text-[#111]"
      >
        <ArrowLeft size={14} /> 返回
      </button>

      <div className="mb-6 flex items-start gap-3">
        <Bird size={28} className="mt-0.5 shrink-0 text-[#111]" strokeWidth={1.6} />
        <div>
          <h2 className="text-[20px] font-bold text-[#111827]">上传画布到 PaperHub</h2>
          <p className="mt-1 text-[13px] text-[#6b7280]">发布当前工作区快照，并附上结果文件与封面。</p>
        </div>
      </div>

      <label className="mb-1.5 block text-[13px] font-bold text-[#333]">项目名字</label>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="请输入项目名字"
        className="mb-4 h-12 w-full rounded-[16px] border border-black/10 bg-white px-4 text-[14px] outline-none focus:border-[#111]/35"
      />

      <label className="mb-1.5 block text-[13px] font-bold text-[#333]">项目描述</label>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="一句话介绍你的创作（可选）"
        rows={3}
        className="mb-4 w-full resize-none rounded-[16px] border border-black/10 bg-white px-4 py-3 text-[14px] outline-none focus:border-[#111]/35"
      />

      <label className="mb-1.5 block text-[13px] font-bold text-[#333]">标签（最多 10 个）</label>
      <div className="mb-2 flex gap-2">
        <input
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              addTag()
            }
          }}
          placeholder="输入后回车添加"
          className="h-11 flex-1 rounded-[14px] border border-black/10 bg-white px-3 text-[13px] outline-none"
        />
        <button
          type="button"
          onClick={addTag}
          className="h-11 rounded-[14px] bg-[#e8e8ec] px-3 text-[13px] font-bold text-[#333]"
        >
          添加
        </button>
      </div>
      {tags.length > 0 ? (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <span
              key={t}
              className="inline-flex items-center gap-1 rounded-full bg-[#f3f4f6] px-2.5 py-1 text-[12px] font-semibold text-[#555]"
            >
              {t}
              <button type="button" onClick={() => setTags((prev) => prev.filter((x) => x !== t))}>
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      ) : (
        <div className="mb-4" />
      )}

      <label className="mb-1.5 block text-[13px] font-bold text-[#333]">结果文件</label>
      <div className="mb-5 flex items-center gap-3 rounded-[16px] bg-[#f3f4f6] px-3 py-2.5">
        <FileText size={16} className="shrink-0 text-[#888]" />
        <span className="min-w-0 flex-1 truncate text-[13px] text-[#666]">
          {resultFiles.length ? resultFiles.map((f) => f.name).join('、') : '选择本地结果文件'}
        </span>
        <button
          type="button"
          onClick={() => resultRef.current?.click()}
          className="h-9 shrink-0 rounded-[12px] bg-[#e8e8ec] px-3 text-[13px] font-bold text-[#333] hover:bg-[#dddde3]"
        >
          选择文件
        </button>
        <input
          ref={resultRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => setResultFiles(Array.from(e.target.files ?? []))}
        />
      </div>

      <label className="mb-1.5 block text-[13px] font-bold text-[#333]">封面</label>
      <div className="mb-6 flex items-center gap-3 rounded-[16px] bg-[#f3f4f6] px-3 py-2.5">
        <ImagePlus size={16} className="shrink-0 text-[#888]" />
        <span className="min-w-0 flex-1 truncate text-[13px] text-[#666]">
          {coverFile?.name ?? '选择本地封面图片'}
        </span>
        <button
          type="button"
          onClick={() => coverRef.current?.click()}
          className="h-9 shrink-0 rounded-[12px] bg-[#e8e8ec] px-3 text-[13px] font-bold text-[#333] hover:bg-[#dddde3]"
        >
          上传封面
        </button>
        <input
          ref={coverRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => setCoverFile(e.target.files?.[0] ?? null)}
        />
      </div>

      <button
        type="button"
        disabled={!canSubmit}
        onClick={() => void onSubmit()}
        className={cn(
          'h-12 w-full rounded-[16px] text-[15px] font-bold text-white',
          canSubmit ? 'bg-[#3f3f46] hover:bg-[#27272a]' : 'cursor-not-allowed bg-[#c4c4c8]',
        )}
      >
        {busy ? '上传中…' : '上传到 PaperHub'}
      </button>
    </div>
  )
}
