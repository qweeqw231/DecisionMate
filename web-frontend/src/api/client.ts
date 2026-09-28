import { useSettingsStore } from '../stores/settings'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function base(): string {
  return useSettingsStore().apiBase
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = base() + path
  let res: Response
  try {
    res = await fetch(url, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
    })
  } catch (e) {
    throw new ApiError(0, `无法连接后端（${url}）。请在「设置」页检查后端地址，或确认后端已启动。`)
  }

  const text = await res.text()
  let data: any = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    // 非 JSON 响应（如静态托管返回的 HTML），原样抛出
  }

  if (!res.ok) {
    const detail = data?.detail || text || `HTTP ${res.status}`
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data as T
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    body: body === undefined ? '{}' : JSON.stringify(body),
  })
}

export function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}
