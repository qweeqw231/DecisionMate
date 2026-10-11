<template>
  <div class="settings-view">
    <div class="page-header">
      <el-button text @click="router.push('/')">
        <el-icon><ArrowLeft /></el-icon>&nbsp;返回
      </el-button>
      <span class="page-title">设置</span>
    </div>

    <div class="page-body">
      <el-card shadow="never" class="setting-card">
        <template #header>
          <span class="card-title">后端服务地址</span>
        </template>

        <div class="field-desc">
          没有云服务时，前后端可运行在不同设备上，后端设备 IP 变化时在此更新地址即可。
        </div>
        <el-input
          v-model="urlDraft"
          placeholder="留空 = 同源访问（推荐：由后端托管前端时）；或填写 http://192.168.1.100:8000"
          clearable
          class="url-input"
        />
        <div class="url-actions">
          <el-button @click="testConnection" :loading="testing">测试连接</el-button>
          <el-button type="primary" @click="saveUrl">保存地址</el-button>
        </div>
        <el-alert
          v-if="testResult === 'ok'"
          type="success"
          :closable="false"
          class="test-alert"
          :title="`连接成功：${statusInfo?.system || ''} ${statusInfo?.version || ''}（${statusInfo?.phase || ''}）`"
        />
        <el-alert
          v-if="testResult === 'fail'"
          type="error"
          :closable="false"
          class="test-alert"
          :title="`连接失败：${testError}`"
        />
      </el-card>

      <el-card shadow="never" class="setting-card">
        <template #header>
          <span class="card-title">访问令牌（可选）</span>
        </template>
        <div class="field-desc">
          后端默认不鉴权（仅本机/局域网自用）。若在共享局域网里使用，可在后端的
          <code>.env</code> 中设置 <code>DM_AUTH_TOKEN=&lt;一串随机字符&gt;</code> 并重启，
          然后在这里填入同一串字符。令牌只存在本机浏览器 localStorage，随请求头发送。
        </div>
        <el-input
          v-model="tokenDraft"
          type="password"
          show-password
          clearable
          placeholder="留空 = 后端未启用鉴权"
          class="url-input"
        />
        <div class="url-actions">
          <el-button type="primary" @click="saveToken">保存令牌</el-button>
          <el-button @click="clearToken">清除</el-button>
        </div>
        <el-alert
          v-if="authRequiredHint && !settingsStore.authToken"
          type="warning"
          :closable="false"
          class="test-alert"
          title="后端已启用鉴权，但本机尚未填写令牌——数据接口会返回 401。"
        />
      </el-card>

      <el-card shadow="never" class="setting-card">
        <template #header>
          <span class="card-title">数据管理</span>
        </template>
        <div class="field-desc">清空所有对话及决策记录（分身配置会保留），此操作不可恢复。</div>
        <el-button type="danger" plain @click="onClearAll">清空所有对话</el-button>
      </el-card>

      <el-card shadow="never" class="setting-card">
        <template #header>
          <span class="card-title">关系边界保护（伦理关机）</span>
        </template>
        <div class="field-desc">
          当决策对象是一个具体的、平等的他人时，系统会主动关机：不做量化、不给建议。
          你在这里维护的硬规则是确定性的，永远优先于大模型判定。
        </div>

        <el-skeleton v-if="!boundaryMeta" :rows="4" animated />

        <template v-else>
          <div class="switch-row">
            <span class="switch-label">启用关系边界保护</span>
            <el-switch v-model="boundaryDraft.enabled" />
          </div>
          <div class="switch-row">
            <span class="switch-label">
              启用语义判定
              <el-tooltip content="硬规则之外，再调用大模型区分「自我审视」与「物化他人」" placement="top">
                <el-icon class="hint-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
            <el-switch v-model="boundaryDraft.use_semantic_check" />
          </div>
          <div class="switch-row">
            <span class="switch-label">
              命中边界时不记录该场景
              <el-tooltip
                content="架构 5.3.4 要求不记录详细数据以保护相关方隐私。关闭后边界场景也会写入消息与决策记录。"
                placement="top"
              >
                <el-icon class="hint-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
            <el-switch v-model="boundaryDraft.skip_persistence" />
          </div>
          <el-alert
            v-if="!boundaryDraft.skip_persistence"
            type="warning"
            :closable="false"
            class="inline-alert"
            title="隐私保护已关闭：边界场景会被写入消息、决策记录与向量库，与架构 5.3.4 的要求不符。"
          />

          <div class="field-label">硬规则（每行一条，子串匹配）</div>
          <el-input
            v-model="patternsText"
            type="textarea"
            :rows="6"
            placeholder="每行一条，例如：&#10;追她&#10;表白"
          />

          <div class="field-label">关机提示文案</div>
          <el-input v-model="boundaryDraft.shutdown_message" type="textarea" :rows="3" />

          <div class="url-actions">
            <el-button type="primary" :loading="savingBoundary" @click="saveBoundary">保存边界配置</el-button>
            <el-button @click="resetBoundary">恢复默认</el-button>
            <span v-if="boundaryMeta.updated_at" class="muted">
              上次修改：{{ boundaryMeta.updated_at.replace('T', ' ').slice(0, 19) }}
            </span>
          </div>
        </template>
      </el-card>

      <el-card shadow="never" class="setting-card">
        <template #header>
          <span class="card-title">部署说明</span>
        </template>
        <div class="deploy-hint">
          <p><strong>方式一（推荐）：同源托管。</strong>执行 <code>npm run build</code>，将
            <code>dist</code> 目录内容复制到后端的 <code>static/</code> 目录下，重启后端，
            局域网设备访问 <code>http://&lt;后端IP&gt;:8000</code> 即可，后端更换 IP 无需任何配置。</p>
          <p><strong>方式二：独立部署。</strong>将构建产物部署到任意静态服务器，
            在本页填写后端地址即可连接。</p>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSettingsStore } from '../stores/settings'
import { useConversationStore } from '../stores/conversation'
import {
  getRootStatus,
  getBoundaryConfig,
  updateBoundaryConfig,
  resetBoundaryConfig,
  type RootStatus,
} from '../api/decision'
import type { BoundaryConfigMeta, BoundaryConfig } from '../types'

const router = useRouter()
const settingsStore = useSettingsStore()
const conversationStore = useConversationStore()

const urlDraft = ref(settingsStore.baseUrl)
const testing = ref(false)
const testResult = ref<'' | 'ok' | 'fail'>('')
const testError = ref('')
const statusInfo = ref<RootStatus | null>(null)

// ---------- 访问令牌 ----------
const tokenDraft = ref(settingsStore.authToken)
const authRequiredHint = ref(false)

function saveToken() {
  settingsStore.setAuthToken(tokenDraft.value)
  tokenDraft.value = settingsStore.authToken
  ElMessage.success(settingsStore.authToken ? '令牌已保存' : '令牌已清空')
}

function clearToken() {
  tokenDraft.value = ''
  settingsStore.setAuthToken('')
  ElMessage.success('令牌已清空')
}

// ---------- 关系边界配置 ----------
const boundaryMeta = ref<BoundaryConfigMeta | null>(null)
const boundaryDraft = ref<BoundaryConfig>({
  enabled: true,
  use_semantic_check: true,
  hard_patterns: [],
  shutdown_message: '',
  skip_persistence: true,
})
const patternsText = ref('')
const savingBoundary = ref(false)

function applyBoundaryMeta(meta: BoundaryConfigMeta) {
  boundaryMeta.value = meta
  boundaryDraft.value = { ...meta.current }
  patternsText.value = meta.current.hard_patterns.join('\n')
}

async function loadBoundary() {
  try {
    applyBoundaryMeta(await getBoundaryConfig())
  } catch (e) {
    ElMessage.error(`读取边界配置失败：${(e as Error).message}`)
  }
}

function parsePatterns(): string[] {
  return patternsText.value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

async function saveBoundary() {
  const patterns = parsePatterns()
  if (!patterns.length) {
    ElMessage.warning('硬规则不能为空；若不想拦截任何内容，请关闭「启用关系边界保护」')
    return
  }
  if (!boundaryDraft.value.shutdown_message.trim()) {
    ElMessage.warning('关机提示文案不能为空')
    return
  }
  savingBoundary.value = true
  try {
    const res = await updateBoundaryConfig({
      ...boundaryDraft.value,
      hard_patterns: patterns,
    })
    applyBoundaryMeta({ ...boundaryMeta.value!, current: res.config })
    ElMessage.success('边界配置已保存')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    savingBoundary.value = false
  }
}

async function resetBoundary() {
  try {
    await ElMessageBox.confirm('确定恢复关系边界的默认配置吗？', '恢复默认', {
      type: 'warning',
      confirmButtonText: '恢复',
      cancelButtonText: '取消',
    })
    const res = await resetBoundaryConfig()
    applyBoundaryMeta({ ...boundaryMeta.value!, current: res.config })
    ElMessage.success('已恢复默认配置')
  } catch { /* 取消 */ }
}

onMounted(() => {
  urlDraft.value = settingsStore.baseUrl
  loadBoundary()
})

function saveUrl() {
  settingsStore.setBaseUrl(urlDraft.value)
  urlDraft.value = settingsStore.baseUrl
  ElMessage.success('后端地址已保存')
}

async function testConnection() {
  // 先临时生效草稿地址再测试
  settingsStore.setBaseUrl(urlDraft.value)
  testing.value = true
  testResult.value = ''
  try {
    statusInfo.value = await getRootStatus()
    authRequiredHint.value = !!statusInfo.value?.auth_required
    testResult.value = 'ok'
  } catch (e) {
    testResult.value = 'fail'
    testError.value = (e as Error).message
  } finally {
    testing.value = false
  }
}

async function onClearAll() {
  try {
    await ElMessageBox.confirm('确定清空所有对话和决策记录吗？分身配置会保留。', '清空数据', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
    })
    await conversationStore.clearSessions()
    ElMessage.success('所有对话已清空')
  } catch { /* 取消 */ }
}
</script>

<style scoped>
.settings-view {
  height: 100%;
  overflow-y: auto;
  background: #f5f6f7;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  background: #fff;
  border-bottom: 1px solid #eef0f2;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
}
.page-body {
  max-width: 720px;
  margin: 20px auto;
  padding: 0 24px;
}
.setting-card {
  margin-bottom: 16px;
  border-radius: 10px;
}
.card-title {
  font-weight: 600;
}
.field-desc {
  font-size: 13px;
  color: #8f959e;
  margin-bottom: 10px;
  line-height: 1.6;
}
.url-actions {
  margin-top: 12px;
  display: flex;
  gap: 10px;
}
.test-alert {
  margin-top: 12px;
}
.deploy-hint {
  font-size: 13px;
  line-height: 1.8;
  color: #4e5969;
}
.deploy-hint p {
  margin: 0 0 8px;
}
.deploy-hint code {
  background: #f2f3f5;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed #f0f1f3;
  font-size: 13px;
}
.switch-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #4e5969;
}
.hint-icon {
  color: #a0a4ab;
  cursor: help;
}
.inline-alert {
  margin: 10px 0;
}
.field-label {
  margin: 14px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #4e5969;
}
.muted {
  font-size: 12px;
  color: #a0a4ab;
  align-self: center;
}
</style>
