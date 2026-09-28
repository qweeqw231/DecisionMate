import type { AnyReport, DecisionReport, FastDecisionReport } from '../types'

/** 安全解析 assistant 消息内容（后端存的是报告 JSON 字符串） */
export function parseReport(content: string): AnyReport | null {
  try {
    const obj = JSON.parse(content)
    if (obj && typeof obj === 'object' && 'loop_type' in obj) {
      return obj as AnyReport
    }
    // 兼容历史数据中可能缺失 loop_type 的慢报告
    if (obj && typeof obj === 'object' && 'recommendation' in obj && 'f_star' in obj) {
      return { ...obj, loop_type: 'slow' } as DecisionReport
    }
  } catch {
    /* 非报告 JSON（旧数据/纯文本） */
  }
  return null
}

export function isFastReport(r: AnyReport): r is FastDecisionReport {
  return r.loop_type === 'fast'
}

/** 风险等级标签颜色 */
export function riskTagType(level: string): 'success' | 'info' | 'warning' | 'danger' {
  if (/低/.test(level)) return 'success'
  if (/中/.test(level)) return 'warning'
  if (/高|严重/.test(level)) return 'danger'
  return 'info'
}

/** 格式化时间为 HH:MM */
export function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ''
  }
}

/** 复制文本到剪贴板，兼容非安全上下文 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}
