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
          <span class="card-title">数据管理</span>
        </template>
        <div class="field-desc">清空所有对话及决策记录（分身配置会保留），此操作不可恢复。</div>
        <el-button type="danger" plain @click="onClearAll">清空所有对话</el-button>
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
import { getRootStatus, type RootStatus } from '../api/decision'

const router = useRouter()
const settingsStore = useSettingsStore()
const conversationStore = useConversationStore()

const urlDraft = ref(settingsStore.baseUrl)
const testing = ref(false)
const testResult = ref<'' | 'ok' | 'fail'>('')
const testError = ref('')
const statusInfo = ref<RootStatus | null>(null)

onMounted(() => {
  urlDraft.value = settingsStore.baseUrl
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
</style>
