import { defineStore } from 'pinia'
import type { ActivatedPersona, Persona } from '../types'
import {
  listPersonas,
  createPersona,
  updatePersona,
  deletePersona,
  resetPersona,
  getConversationPersonas,
  saveConversationPersonas,
} from '../api/decision'

interface PersonaState {
  personas: Persona[]
  /** 当前对话激活的分身 id 集合 */
  selectedIds: number[]
  /** 各分身的权重草稿（滑块值，未归一化），key 为 persona id */
  weights: Record<number, number>
}

export const usePersonaStore = defineStore('persona', {
  state: (): PersonaState => ({
    personas: [],
    selectedIds: [],
    weights: {},
  }),
  getters: {
    selectedPersonas(state): Persona[] {
      return state.personas.filter((p) => state.selectedIds.includes(p.id))
    },
    /** 自定义分身数量（上限 3） */
    customCount(state): number {
      return state.personas.filter((p) => !p.is_preset).length
    },
    /** 当前滑块权重总和（用于 UI 提示是否需要归一化） */
    weightSum(): number {
      return this.selectedPersonas.reduce((sum, p) => sum + (this.weights[p.id] ?? p.weight), 0)
    },
  },
  actions: {
    async loadPersonas() {
      this.personas = await listPersonas()
    },
    async loadForConversation(convId: number) {
      const ids = await getConversationPersonas(convId)
      if (ids.length) {
        this.selectedIds = ids
      } else {
        // 与鸿蒙版一致：默认仅激活中性分身
        const neutral = this.personas.find((p) => p.risk_preference === 'neutral')
        this.selectedIds = neutral ? [neutral.id] : []
      }
      this.selectedIds.forEach((id) => {
        const p = this.personas.find((x) => x.id === id)
        if (p) this.weights[id] = p.weight
      })
    },
    async persistForConversation(convId: number) {
      await saveConversationPersonas(convId, this.selectedIds)
    },
    togglePersona(id: number) {
      const idx = this.selectedIds.indexOf(id)
      if (idx >= 0) {
        this.selectedIds.splice(idx, 1)
      } else {
        this.selectedIds.push(id)
        const p = this.personas.find((x) => x.id === id)
        if (p) this.weights[id] = p.weight
      }
    },
    setWeight(id: number, value: number) {
      this.weights[id] = value
    },
    /**
     * 组装发送消息所需的 activated_personas：
     * 滑块权重按总和归一化（与鸿蒙 InputPage 逻辑一致）。
     */
    normalizedActivated(): ActivatedPersona[] {
      const selected = this.selectedPersonas
      const raw = selected.map((p) => ({
        persona_id: p.id,
        w: this.weights[p.id] ?? p.weight,
      }))
      const total = raw.reduce((s, x) => s + (x.w > 0 ? x.w : 0), 0) || 1
      return raw.map((x) => ({
        persona_id: x.persona_id,
        normalized_weight: x.w > 0 ? x.w / total : 0,
      }))
    },

    // ---------- 分身管理 CRUD ----------
    async create(payload: { name: string; risk_preference: string; core_principle?: string }) {
      const created = await createPersona(payload)
      this.personas.push(created)
      return created
    },
    async update(id: number, payload: {
      name?: string
      core_principle?: string
      weight?: number
      risk_preference?: string
    }) {
      const updated = await updatePersona(id, payload)
      const idx = this.personas.findIndex((p) => p.id === id)
      if (idx >= 0) this.personas[idx] = updated
      if (this.weights[id] !== undefined && payload.weight !== undefined) {
        this.weights[id] = updated.weight
      }
    },
    async remove(id: number) {
      await deletePersona(id)
      this.personas = this.personas.filter((p) => p.id !== id)
      this.selectedIds = this.selectedIds.filter((x) => x !== id)
      delete this.weights[id]
    },
    async reset(id: number) {
      const updated = await resetPersona(id)
      const idx = this.personas.findIndex((p) => p.id === id)
      if (idx >= 0) this.personas[idx] = updated
      if (this.weights[id] !== undefined) this.weights[id] = updated.weight
    },
  },
})
