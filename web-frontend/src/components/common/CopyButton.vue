<template>
  <el-tooltip :content="copied ? '已复制' : '复制'" placement="top">
    <el-button text size="small" @click="doCopy">
      <el-icon><Check v-if="copied" /><DocumentCopy v-else /></el-icon>
    </el-button>
  </el-tooltip>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { copyText } from '../../utils/report'

const props = defineProps<{ text: string }>()
const copied = ref(false)

async function doCopy() {
  const ok = await copyText(props.text)
  if (ok) {
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } else {
    ElMessage.error('复制失败')
  }
}
</script>
