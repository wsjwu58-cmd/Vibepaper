import { Bird, CloudUpload, Link2 } from 'lucide-react'
import { cn } from '@/lib/cn'

export type ShareView = 'choice' | 'link' | 'paperhub'

export function ShareChoicePanel({
  onLink,
  onPaperHub,
}: {
  onLink: () => void
  onPaperHub: () => void
}) {
  return (
    <div className="flex flex-col items-center py-2 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center">
        <Bird size={40} className="text-[#111]" strokeWidth={1.6} />
      </div>
      <h2 className="text-[22px] font-bold text-[#111827]">分享画布</h2>
      <p className="mb-6 text-[14px] text-[#6b7280]">选择你希望发布当前画布的方式。</p>

      <div className="w-full space-y-3">
        <ChoiceCard
          icon={<Link2 size={18} className="text-[#555]" />}
          title="以链接形式分享画布"
          desc="保留现有共享链接能力，可复制或停止共享。"
          onClick={onLink}
        />
        <ChoiceCard
          icon={<CloudUpload size={18} className="text-[#555]" />}
          title="上传画布到 PaperHub"
          desc="编辑项目名，上传结果文件与封面后发布。"
          onClick={onPaperHub}
        />
      </div>
    </div>
  )
}

function ChoiceCard({
  icon,
  title,
  desc,
  onClick,
}: {
  icon: React.ReactNode
  title: string
  desc: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-4 rounded-[20px] border border-[#f3f4f6] bg-white p-4 text-left transition',
        'hover:border-[#111]/25 hover:bg-[#fafafa]',
      )}
    >
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#f3f4f6]">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-[16px] font-bold text-[#111827]">{title}</p>
        <p className="mt-0.5 text-[13px] leading-snug text-[#6b7280]">{desc}</p>
      </div>
    </button>
  )
}
