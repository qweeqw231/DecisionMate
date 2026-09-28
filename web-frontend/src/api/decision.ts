import { get, post, del } from './client'
import type {
  AnyReport,
  ArchiveReport,
  ActivatedPersona,
  Conversation,
  Message,
  Persona,
  PersonaCreatePayload,
  PersonaUpdatePayload,
} from '../types'

// ---------- 根状态（用于设置页测试连接） ----------
export interface RootStatus {
  status: string
  system: string
  version: string
  phase: string
  features: string[]
}
export const getRootStatus = () => get<RootStatus>('/api/health')

// ---------- 对话 ----------
export const listConversations = () => get<Conversation[]>('/api/conversations')
export const createConversation = (title?: string) =>
  post<Conversation>('/api/conversations', title ? { title } : {})
export const renameConversation = (id: number, title: string) =>
  post<{ status: string }>(`/api/conversations/${id}/rename`, { title })
export const togglePinConversation = (id: number) =>
  post<{ status: string; is_pinned: boolean }>(`/api/conversations/${id}/pin`)
export const deleteConversation = (id: number) => del<{ status: string }>(`/api/conversations/${id}`)
export const clearAllConversations = () => del<{ status: string }>('/api/conversations')

// ---------- 消息 ----------
export const listMessages = (convId: number) =>
  get<Message[]>(`/api/conversations/${convId}/messages`)

/** 同步发送消息（降级通道，一次性返回完整报告） */
export const sendMessageSync = (convId: number, scenario: string, activatedPersonas?: ActivatedPersona[]) =>
  post<AnyReport>(`/api/conversations/${convId}/messages`, {
    scenario,
    activated_personas: activatedPersonas ?? null,
  })

// ---------- 反馈 / 归档 ----------
export const submitFeedback = (
  convId: number,
  msgId: number,
  feedbackType: 'useful' | 'inaccurate' | 'custom',
  feedbackText?: string,
) =>
  post<{ status: string; archive_report: ArchiveReport }>(
    `/api/conversations/${convId}/messages/${msgId}/feedback`,
    { feedback_type: feedbackType, feedback_text: feedbackText ?? null },
  )

// ---------- 用户画像 ----------
export interface UserProfile {
  [key: string]: unknown
}
export const getUserProfile = () => get<UserProfile>('/api/user-profile')

// ---------- 分身 ----------
export const listPersonas = () => get<Persona[]>('/api/personas')
export const createPersona = (payload: PersonaCreatePayload) => post<Persona>('/api/personas', payload)
export const updatePersona = (id: number, payload: PersonaUpdatePayload) =>
  post<Persona>(`/api/personas/${id}/update`, payload)
export const deletePersona = (id: number) => del<{ status: string }>(`/api/personas/${id}`)
export const resetPersona = (id: number) => post<Persona>(`/api/personas/${id}/reset`)

// ---------- 对话-分身绑定 ----------
export const getConversationPersonas = (convId: number) =>
  get<number[]>(`/api/conversations/${convId}/personas`)
export const saveConversationPersonas = (convId: number, personaIds: number[]) =>
  post<{ status: string; persona_ids: number[] }>(`/api/conversations/${convId}/personas`, {
    persona_ids: personaIds,
  })
