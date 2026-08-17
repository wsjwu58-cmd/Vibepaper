import { Fragment, useEffect, type ReactNode } from 'react'
import { useTypewriter } from './useTypewriter'
import { cn } from '@/lib/cn'

/** 对话正文：标题、列表（含 emoji 行）、表格、加粗、行内代码。字号对齐官网。 */
export function AgentMarkdown({ text, className }: { text: string; className?: string }) {
  if (!text) return null
  const blocks = parseBlocks(text)
  return (
    <div className={cn('space-y-2.5 text-[15px] leading-[1.7] text-[#222]', className)}>
      {blocks.map((b, i) => (
        <Fragment key={i}>{renderBlock(b)}</Fragment>
      ))}
    </div>
  )
}

export function StreamingAgentReply({
  text,
  animate,
  streamComplete,
  className,
  onRevealDone,
}: {
  text: string
  animate?: boolean
  streamComplete?: boolean
  className?: string
  onRevealDone?: () => void
}) {
  const { text: shown, catchingUp, done } = useTypewriter(text, !!animate, 14)

  useEffect(() => {
    if (animate && streamComplete && done && !catchingUp) onRevealDone?.()
  }, [animate, streamComplete, done, catchingUp, onRevealDone])

  if (!text && !shown) return null
  return (
    <div className={cn('relative', className)}>
      <AgentMarkdown text={shown || (animate ? '' : text)} />
      {(animate || catchingUp) && (
        <span
          aria-hidden
          className="ml-0.5 inline-block h-[14px] w-[7px] translate-y-[2px] animate-pulse rounded-[1px] bg-[#bbb]"
        />
      )}
    </div>
  )
}

type Block =
  | { type: 'heading'; level: 1 | 2 | 3; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'emoji-list'; items: string[] }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'p'; text: string }

function isTableSep(line: string): boolean {
  const t = line.trim()
  if (!t) return false
  return /^\s*\|?\s*:?-{2,}[-:|\s]*$/.test(t) || /^\s*\|?\s*[-: ]+\|/.test(t)
}

function isPipeRow(line: string): boolean {
  if (!line.includes('|') || isTableSep(line)) return false
  return splitRow(line).length >= 2
}

function startsTable(lines: string[], i: number): boolean {
  if (!isPipeRow(lines[i]) || i + 1 >= lines.length) return false
  return isTableSep(lines[i + 1]) || isPipeRow(lines[i + 1])
}

/** 📄 / 🎬 / 🖼️ 等开头的进度行 */
function isEmojiBullet(line: string): boolean {
  return /^\s*\p{Extended_Pictographic}/u.test(line)
}

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i += 1
      continue
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line)
    if (heading) {
      blocks.push({
        type: 'heading',
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2].trim(),
      })
      i += 1
      continue
    }
    // **已就位** 单独成行当小标题
    const boldOnly = /^\*\*([^*]+)\*\*\s*$/.exec(line.trim())
    if (boldOnly && (boldOnly[1].includes('已就位') || boldOnly[1].includes('生成中') || boldOnly[1].length <= 24)) {
      blocks.push({ type: 'heading', level: 2, text: boldOnly[1] })
      i += 1
      continue
    }
    if (startsTable(lines, i)) {
      const headers = splitRow(line)
      i += 1
      if (isTableSep(lines[i])) i += 1
      const rows: string[][] = []
      while (i < lines.length && (isPipeRow(lines[i]) || isTableSep(lines[i]))) {
        if (isTableSep(lines[i])) {
          i += 1
          continue
        }
        rows.push(splitRow(lines[i]))
        i += 1
      }
      blocks.push({ type: 'table', headers, rows })
      continue
    }
    if (isEmojiBullet(line)) {
      const items: string[] = []
      while (i < lines.length && isEmojiBullet(lines[i])) {
        items.push(lines[i].trim())
        i += 1
      }
      blocks.push({ type: 'emoji-list', items })
      continue
    }
    const ul = /^\s*[-*]\s+/.test(line)
    const ol = /^\s*\d+[.)]\s+/.test(line)
    if (ul || ol) {
      const items: string[] = []
      const re = ol ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*]\s+(.*)$/
      while (i < lines.length) {
        const m = re.exec(lines[i])
        if (!m) break
        items.push(m[1])
        i += 1
      }
      blocks.push({ type: 'list', ordered: ol, items })
      continue
    }
    const para: string[] = [line]
    i += 1
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,3})\s+/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^\s*\d+[.)]\s+/.test(lines[i]) &&
      !isEmojiBullet(lines[i]) &&
      !startsTable(lines, i)
    ) {
      para.push(lines[i])
      i += 1
    }
    blocks.push({ type: 'p', text: para.join('\n') })
  }
  return blocks
}

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((c) => c.trim())
}

function renderInline(line: string): ReactNode[] {
  const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong key={i} className="font-semibold text-[#111]">
          {part.slice(2, -2)}
        </strong>
      )
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={i}
          className="mx-0.5 rounded-[5px] bg-[#f0f0f0] px-1.5 py-0.5 font-mono text-[13px] text-[#555]"
        >
          {part.slice(1, -1)}
        </code>
      )
    }
    return <Fragment key={i}>{part}</Fragment>
  })
}

function renderBlock(block: Block): ReactNode {
  if (block.type === 'heading') {
    const Tag = block.level === 1 ? 'h3' : block.level === 2 ? 'h4' : 'h5'
    return (
      <Tag className="text-[15px] font-bold text-[#111]">
        {renderInline(block.text)}
      </Tag>
    )
  }
  if (block.type === 'emoji-list') {
    return (
      <ul className="space-y-1.5">
        {block.items.map((item, i) => (
          <li key={i} className="text-[15px] leading-[1.7] text-[#222]">
            {renderInline(item)}
          </li>
        ))}
      </ul>
    )
  }
  if (block.type === 'list') {
    const List = block.ordered ? 'ol' : 'ul'
    return (
      <List className={cn('ml-4 space-y-1.5', block.ordered ? 'list-decimal' : 'list-disc')}>
        {block.items.map((item, i) => (
          <li key={i} className="text-[15px] leading-[1.7]">
            {renderInline(item)}
          </li>
        ))}
      </List>
    )
  }
  if (block.type === 'table') {
    return (
      <div className="overflow-x-auto rounded-[10px] border border-black/8">
        <table className="w-full border-collapse text-left text-[13px]">
          <thead>
            <tr className="bg-[#f4f4f5]">
              {block.headers.map((h, i) => (
                <th key={i} className="border-b border-black/8 px-2.5 py-1.5 font-semibold text-[#444]">
                  {renderInline(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, ri) => (
              <tr key={ri} className="align-top">
                {block.headers.map((_, ci) => (
                  <td key={ci} className="border-b border-black/5 px-2.5 py-1.5 text-[#555]">
                    {renderInline(row[ci] || '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return (
    <p className="whitespace-pre-wrap text-[15px] leading-[1.7]">
      {renderInline(block.text)}
    </p>
  )
}
