import { useSettingsStore } from '../stores/settings'
import type { ActivatedPersona, AnyReport, StageEvent } from '../types'

export type SseHandler = (event: string, data: any) => void

export interface SendStreamOptions {
  convId: number
  scenario: string
  activatedPersonas?: ActivatedPersona[] | null
  onEvent: SseHandler
  signal?: AbortSignal
}

/**
 * SSE 客户端：EventSource 不支持 POST，用 fetch + ReadableStream 手工解析
 * text/event-stream（按空行分帧，解析 event:/data: 行）。
 * 服务端事件：start / fast / quant / personas{names} / risk / scene / merge / result / error
 */
export async function sendMessageStream(opts: SendStreamOptions): Promise<void> {
  const { convId, scenario, activatedPersonas, onEvent, signal } = opts
  const url = useSettingsStore().apiBase + `/api/conversations/${convId}/messages/stream`

  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        scenario,
        activated_personas: activatedPersonas ?? null,
      }),
      signal,
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new Error(`无法连接后端（${url}），请在「设置」页检查后端地址。`)
  }

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => '')
    let detail = text
    try {
      detail = JSON.parse(text)?.detail || text
    } catch { /* 保留原文 */ }
    throw new Error(detail || `HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  const dispatchFrame = (frame: string) => {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).replace(/^ /, ''))
      }
    }
    if (!dataLines.length && event === 'message') return // 纯注释/心跳帧
    const raw = dataLines.join('\n')
    let data: any = raw
    try {
      data = JSON.parse(raw)
    } catch { /* 保留原文 */ }
    onEvent(event, data)
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE 帧以 \n\n 分隔（兼容 \r\n\r\n）
    let idx: number
    while ((idx = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx).replace(/^\r?\n\r?\n/, '')
      if (frame.trim()) dispatchFrame(frame)
    }
  }
  if (buffer.trim()) dispatchFrame(buffer)
}

/** 从 SSE 事件流中提取最终报告（result 事件） */
export function extractReport(events: Array<[string, any]>): AnyReport | null {
  for (const [event, data] of events.reverse()) {
    if (event === 'result') return data as AnyReport
  }
  return null
}

export type { StageEvent }
