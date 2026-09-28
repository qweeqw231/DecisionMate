<template>
  <div class="feedback-bar">
    <template v-if="!archive">
      <el-button
        size="small"
        :type="feedbackType === 'useful' ? 'success' : ''"
        plain
        @click="submit('useful')"
      >
        <el-icon><Select /></el-icon>&nbsp;决策有效
      </el-button>
      <el-button
        size="small"
        :type="feedbackType === 'inaccurate' ? 'danger' : ''"
        plain
        @click="submit('inaccurate')"
      >
        <el-icon><CloseBold /></el-icon>&nbsp;决策不准确
      </el-button>
      <el-button size="small" plain @click="openCustom">
        <el-icon><ChatLineSquare /></el-icon>&nbsp;自定义反馈
      </el-button>
    </template>
    <ArchivePanel v-else :report="archive" />

    <el-dialog v-model="customVisible" title="提交自定义反馈" width="480px">
      <el-input
        v-model="customText"
        type="textarea"
        :rows="4"
        placeholder="请描述实际结果与系统建议的差异…"
      />
      <template #footer>
        <el-button @click="customVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="submit('custom', customText)">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ArchiveReport } from '../../types'
import { submitFeedback } from '../../api/decision'
import ArchivePanel from './ArchivePanel.vue'

const props = defineProps<{ convId: number; msgId: number; disabled?: boolean }>()

const archive = ref<ArchiveReport | null>(null)
const feedbackType = ref('')
const loading = ref(false)
const customVisible = ref(false)
const customText = ref('')

function openCustom() {
  customText.value = ''
  customVisible.value = true
}

async function submit(type: 'useful' | 'inaccurate' | 'custom', text?: string) {
  if (type === 'custom' && !text?.trim()) {
    ElMessage.warning('请填写反馈内容')
    return
  }
  loading.value = true
  try {
    const res = await submitFeedback(props.convId, props.msgId, type, text?.trim())
    feedbackType.value = type
    archive.value = res.archive_report
    customVisible.value = false
    ElMessage.success('反馈已提交，复盘归档完成')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.feedback-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
