import { defineStore } from 'pinia'

const LS_KEY = 'dm_base_url'
const LS_TOKEN = 'dm_auth_token'

/**
 * 全局设置：后端地址与访问令牌都在运行时可配置。
 * - 地址留空 = 同源相对路径（vite 代理开发模式 / FastAPI 静态托管部署模式）
 * - 地址填写如 http://192.168.1.100:8000 = 跨机直连（后端 IP 漂移场景）
 * - 令牌对应后端 .env 里的 DM_AUTH_TOKEN；后端未启用鉴权时留空即可
 */
export const useSettingsStore = defineStore('settings', {
  state: () => ({
    baseUrl: localStorage.getItem(LS_KEY) || '',
    authToken: localStorage.getItem(LS_TOKEN) || '',
  }),
  getters: {
    /** API 请求的 base，不含末尾斜杠 */
    apiBase(): string {
      return this.baseUrl.replace(/\/+$/, '')
    },
  },
  actions: {
    setBaseUrl(url: string) {
      this.baseUrl = url.trim()
      if (this.baseUrl) {
        localStorage.setItem(LS_KEY, this.baseUrl)
      } else {
        localStorage.removeItem(LS_KEY)
      }
    },
    setAuthToken(token: string) {
      this.authToken = token.trim()
      if (this.authToken) {
        localStorage.setItem(LS_TOKEN, this.authToken)
      } else {
        localStorage.removeItem(LS_TOKEN)
      }
    },
  },
})
