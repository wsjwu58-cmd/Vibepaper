import { useState } from 'react'
import type { ModelInfo } from '@/lib/types'

export type ModelBrand =
  | 'deepseek'
  | 'qwen'
  | 'openai'
  | 'google'
  | 'doubao'
  | 'flux'
  | 'stability'
  | 'kling'
  | 'wan'
  | 'audio'
  | 'compose'
  | 'director'
  | 'generic'

const ENGINE_LLM_BASE = 'https://tos.nexra-ai.com/engine-llm'

const BRAND_ICON_URL: Partial<Record<ModelBrand, string>> = {
  deepseek: `${ENGINE_LLM_BASE}/deepseek.png`,
  qwen: `${ENGINE_LLM_BASE}/qwen.png`,
  openai: `${ENGINE_LLM_BASE}/openai.png`,
  google: `${ENGINE_LLM_BASE}/google.png`,
  doubao: `${ENGINE_LLM_BASE}/doubao.png`,
  flux: `${ENGINE_LLM_BASE}/flux.png`,
  stability: `${ENGINE_LLM_BASE}/stability.png`,
  kling: `${ENGINE_LLM_BASE}/kling.png`,
  wan: `${ENGINE_LLM_BASE}/wan.png`,
}

const BRAND_META: Record<ModelBrand, { label: string; bg: string; fg: string }> = {
  deepseek: { label: 'DS', bg: '#4d6bfe', fg: '#fff' },
  qwen: { label: 'QW', bg: '#615ced', fg: '#fff' },
  openai: { label: 'AI', bg: '#10a37f', fg: '#fff' },
  google: { label: 'G', bg: '#4285f4', fg: '#fff' },
  doubao: { label: '豆', bg: '#3b82f6', fg: '#fff' },
  flux: { label: 'FX', bg: '#111827', fg: '#fff' },
  stability: { label: 'SD', bg: '#9333ea', fg: '#fff' },
  kling: { label: 'KL', bg: '#0f766e', fg: '#fff' },
  wan: { label: 'WN', bg: '#ea580c', fg: '#fff' },
  audio: { label: '♪', bg: '#db2777', fg: '#fff' },
  compose: { label: '合', bg: '#475569', fg: '#fff' },
  director: { label: '导', bg: '#1e293b', fg: '#fff' },
  generic: { label: 'M', bg: '#64748b', fg: '#fff' },
}

/** 按 provider / 模型名推断品牌，用于图标。 */
export function resolveModelBrand(model: Pick<ModelInfo, 'name' | 'provider' | 'displayName'> | string): ModelBrand {
  const name = (typeof model === 'string' ? model : model.name || '').toLowerCase()
  const provider = (typeof model === 'string' ? '' : model.provider || '').toLowerCase()
  const display = (typeof model === 'string' ? '' : model.displayName || '').toLowerCase()
  const hay = `${provider} ${name} ${display}`

  if (/deepseek/.test(hay)) return 'deepseek'
  if (/qwen|tongyi|通义/.test(hay)) return 'qwen'
  if (/gemini|google/.test(hay)) return 'google'
  if (/gpt|openai/.test(hay)) return 'openai'
  if (/doubao|seedream|seedance|volc|ark|方舟/.test(hay)) return 'doubao'
  if (/flux/.test(hay)) return 'flux'
  if (/stable|sd3|sd-/.test(hay)) return 'stability'
  if (/kling|可灵/.test(hay)) return 'kling'
  if (/wan-|\bwan\b/.test(hay)) return 'wan'
  if (/music|audio/.test(hay)) return 'audio'
  if (/compose|合成/.test(hay)) return 'compose'
  if (/director|导演/.test(hay)) return 'director'
  return 'generic'
}

/** CDN 模型图标 URL，与 web 参考 UI 一致。 */
export function resolveModelIconUrl(
  model: Pick<ModelInfo, 'name' | 'provider' | 'displayName'> | string,
): string | null {
  const brand = resolveModelBrand(model)
  return BRAND_ICON_URL[brand] ?? null
}

function BeanIcon({ size, className }: { size: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden
    >
      <path d="M12 2c-4.5 0-8 3.5-8 9 0 4 2 11 8 11s8-7 8-11c0-5.5-3.5-9-8-9zm0 3c.8 0 1.5.4 2 1.2.5 1.2.3 2.8-.5 4.1-.8 1.3-2.2 2-3.5 1.8-1.3-.2-2.2-1.2-2.2-2.5 0-2.5 2.2-4.6 4.2-4.6z" />
    </svg>
  )
}

export function ModelBrandIcon({
  model,
  size = 18,
  className = '',
  preferImage = true,
}: {
  model: Pick<ModelInfo, 'name' | 'provider' | 'displayName'> | string
  size?: number
  className?: string
  /** 优先使用 CDN 图标（与 web 一致），加载失败时回退字母徽章 */
  preferImage?: boolean
}) {
  const brand = resolveModelBrand(model)
  const meta = BRAND_META[brand]
  const font = Math.max(8, Math.round(size * 0.42))
  const iconUrl = preferImage ? resolveModelIconUrl(model) : null
  const [imgFailed, setImgFailed] = useState(false)
  const title = typeof model === 'string' ? model : model.displayName || model.name

  if (iconUrl && !imgFailed) {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded ${className}`}
        style={{ width: size, height: size }}
        title={title}
        aria-hidden
      >
        <img
          alt=""
          src={iconUrl}
          className="size-full object-contain"
          onError={() => setImgFailed(true)}
        />
      </span>
    )
  }

  const useBean = brand === 'doubao' || brand === 'wan'

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-md font-black leading-none ${className}`}
      style={{
        width: size,
        height: size,
        background: meta.bg,
        color: meta.fg,
        fontSize: font,
      }}
      title={title}
      aria-hidden
    >
      {useBean ? <BeanIcon size={size} /> : meta.label}
    </span>
  )
}
