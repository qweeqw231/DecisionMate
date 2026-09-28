import { defineStore } from 'pinia'

const LS_KEY = 'dm_base_url'

/**
 * 全局设置：后端地址运行时可配置。
 * - 留空 = 同源相对路径（vite 代理开发模式 / FastAPI 静态托管部署模式）
 * - 填写如 http://192.168.1.100:8000 = 跨机直连（后端 IP 漂移场景）
 */
export const useSettingsStore = defineStore('settings', {
  state: () => ({
    baseUrl: localStorage.getItem(LS_KEY) || '',
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
  },
})
