import { get, post, del } from './client'
import type {
  AnyReport,
  AddFactorPayload,
  ArchiveReport,
  ActivatedPersona,
  BoundaryConfig,
  BoundaryConfigMeta,
  CalibrationTrajectory,
  Conversation,
  Message,
  Persona,
  PersonaCreatePayload,
  PersonaUpdatePayload,
  SystemAudit,
} from '../types'

// ---------- 根状态（用于设置页测试连接） ----------
export interface RootStatus {
  status: string
  system: string
  version: string
  phase: string
  features: string[]
  /** 后端是否启用了令牌鉴权（.env 里的 DM_AUTH_TOKEN） */
  auth_required?: boolean
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

/**
 * 用户确认后新增/更新能力因子（复盘摘要卡片的「接受提议」调用此接口）。
 * 后端会校验名称与取值范围，非法输入返回 400。
 */
export const addUserFactor = (payload: AddFactorPayload) =>
  post<{ status: string; factor_name: string; value: number }>(
    '/api/user-profile/add-factor',
    payload,
  )

// ---------- L3 系统自校正 ----------
/** 汇总审计（只读，不触发任何 Agent 调用） */
export const getSystemAudit = () => get<SystemAudit>('/api/system-audit')

// ---------- 关系边界（P1-4） ----------
export const getBoundaryConfig = () => get<BoundaryConfigMeta>('/api/boundary-config')
export const updateBoundaryConfig = (payload: Partial<BoundaryConfig>) =>
  post<{ status: string; config: BoundaryConfig }>('/api/boundary-config', payload)
export const resetBoundaryConfig = () =>
  post<{ status: string; config: BoundaryConfig }>('/api/boundary-config/reset')

// ---------- L1 执行中校准（P1-5） ----------
export const getExecutionTrajectory = (convId: number, msgId: number) =>
  get<CalibrationTrajectory>(
    `/api/conversations/${convId}/messages/${msgId}/execution-updates`,
  )
/** 记录一条阶段性进展，返回「初始预判 → 逐次校准」的完整轨迹 */
export const addExecutionUpdate = (convId: number, msgId: number, note: string) =>
  post<CalibrationTrajectory>(
    `/api/conversations/${convId}/messages/${msgId}/execution-updates`,
    { note },
  )

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
