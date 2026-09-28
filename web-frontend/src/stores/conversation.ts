import { defineStore } from 'pinia'
import type { AnyReport, Conversation, Message, StageEvent } from '../types'
import {
  listConversations,
  createConversation,
  renameConversation,
  togglePinConversation,
  deleteConversation,
  clearAllConversations,
  listMessages,
  sendMessageSync,
} from '../api/decision'
import { sendMessageStream } from '../api/sse'
import { usePersonaStore } from './persona'

interface StreamingState {
  active: boolean
  stage: string
  personaNames: string[]
}

interface ConversationState {
  sessions: Conversation[]
  activeId: number | null
  messages: Message[]
  streaming: StreamingState
  abortCtrl: AbortController | null
}

export const useConversationStore = defineStore('conversation', {
  state: (): ConversationState => ({
    sessions: [],
    activeId: null,
    messages: [],
    streaming: { active: false, stage: '', personaNames: [] },
    abortCtrl: null,
  }),
  getters: {
    activeSession(state): Conversation | undefined {
      return state.sessions.find((c) => c.id === state.activeId)
    },
    isStreaming(state): boolean {
      return state.streaming.active
    },
  },
  actions: {
    // ---------- 会话列表 ----------
    async loadSessions() {
      this.sessions = await listConversations()
    },
    async newSession(title?: string): Promise<number> {
      const conv = await createConversation(title)
      this.sessions.unshift(conv)
      await this.selectSession(conv.id)
      return conv.id
    },
    async selectSession(id: number) {
      if (this.streaming.active) this.abort()
      this.activeId = id
      this.messages = await listMessages(id)
      const personaStore = usePersonaStore()
      await personaStore.loadForConversation(id)
    },
    async renameSession(id: number, title: string) {
      await renameConversation(id, title)
      const conv = this.sessions.find((c) => c.id === id)
      if (conv) conv.title = title
    },
    async togglePin(id: number) {
      const res = await togglePinConversation(id)
      const conv = this.sessions.find((c) => c.id === id)
      if (conv) {
        conv.is_pinned = res.is_pinned
        // 重新排序：置顶优先
        this.sessions.sort((a, b) => Number(b.is_pinned) - Number(a.is_pinned))
      }
    },
    async removeSession(id: number) {
      await deleteConversation(id)
      this.sessions = this.sessions.filter((c) => c.id !== id)
      if (this.activeId === id) {
        this.activeId = null
        this.messages = []
      }
    },
    async clearSessions() {
      await clearAllConversations()
      this.sessions = []
      this.activeId = null
      this.messages = []
    },

    // ---------- 发送消息 ----------
    /**
     * 发送一条决策消息。优先走 SSE（阶段进度可见），
     * SSE 不可用时降级同步接口。
     * 返回最终报告（供错误处理等场景）。
     */
    async send(scenario: string): Promise<AnyReport | null> {
      if (!this.activeId) return null
      const convId = this.activeId
      const personaStore = usePersonaStore()
      const activated = personaStore.normalizedActivated()

      // 本地立即展示用户消息（临时 id 为负数，消息列表刷新时会被服务端记录替换）
      this.messages.push({
        id: -Date.now(),
        conversation_id: convId,
        role: 'user',
        content: scenario,
        created_at: new Date().toISOString(),
      })

      this.streaming = { active: true, stage: 'start', personaNames: [] }
      this.abortCtrl = new AbortController()

      let finalReport: AnyReport | null = null
      try {
        const stageEvents: Array<[string, any]> = []
        await sendMessageStream({
          convId,
          scenario,
          activatedPersonas: activated,
          signal: this.abortCtrl.signal,
          onEvent: (event, data) => {
            if (event === 'stage') {
              const se = data as StageEvent
              this.streaming.stage = se.stage
              if (se.stage === 'personas' && se.names) {
                this.streaming.personaNames = se.names
              }
            } else if (event === 'result') {
              finalReport = data as AnyReport
            } else if (event === 'error') {
              throw new Error(data?.detail || '分析失败')
            }
            stageEvents.push([event, data])
          },
        })
      } catch (e) {
        if ((e as Error).name === 'AbortError') {
          this.streaming.active = false
          this.streaming.stage = ''
          this.abortCtrl = null
          // 中止后以服务端实际记录为准
          this.messages = await listMessages(convId)
          return null
        }
        // SSE 失败 → 降级同步接口
        try {
          finalReport = await sendMessageSync(convId, scenario, activated)
        } catch (e2) {
          this.streaming.active = false
          this.streaming.stage = ''
          this.abortCtrl = null
          throw e2
        }
      }

      this.streaming = { active: false, stage: '', personaNames: [] }
      this.abortCtrl = null
      // 以服务端记录为准刷新（拿到真实消息 id，供反馈接口使用）
      this.messages = await listMessages(convId)
      await this.loadSessions()
      return finalReport
    },
    abort() {
      this.abortCtrl?.abort()
    },
  },
})
