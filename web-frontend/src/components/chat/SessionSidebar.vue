<template>
  <div class="sidebar">
    <div class="brand">
      <el-icon class="brand-icon"><Compass /></el-icon>
      <span>DecisionMate</span>
    </div>

    <el-button class="new-btn" type="primary" plain @click="emit('new-session')">
      <el-icon><Plus /></el-icon>&nbsp;新建对话
    </el-button>

    <div class="session-list">
      <div
        v-for="c in store.sessions"
        :key="c.id"
        class="session-item"
        :class="{ active: c.id === store.activeId }"
        @click="emit('select', c.id)"
      >
        <el-icon class="pin-icon" :class="{ pinned: c.is_pinned }" @click.stop="store.togglePin(c.id)">
          <Top v-if="c.is_pinned" />
          <TopRight v-else />
        </el-icon>
        <div class="session-info">
          <div class="session-title" :title="c.title">{{ c.title }}</div>
          <div class="session-meta">{{ c.message_count }} 条消息</div>
        </div>
        <el-dropdown trigger="click" @command="(cmd: string) => onCommand(cmd, c)">
          <el-icon class="more-icon" @click.stop><MoreFilled /></el-icon>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="rename">重命名</el-dropdown-item>
              <el-dropdown-item command="pin">{{ c.is_pinned ? '取消置顶' : '置顶' }}</el-dropdown-item>
              <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <el-empty v-if="!store.sessions.length" description="暂无对话" :image-size="60" />
    </div>

    <div class="sidebar-footer">
      <div class="footer-item" @click="router.push('/personas')">
        <el-icon><User /></el-icon><span>分身管理</span>
      </div>
      <div class="footer-item" @click="router.push('/settings')">
        <el-icon><Setting /></el-icon><span>设置</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useConversationStore } from '../../stores/conversation'
import type { Conversation } from '../../types'

const emit = defineEmits<{
  (e: 'select', id: number): void
  (e: 'new-session'): void
}>()

const router = useRouter()
const store = useConversationStore()

async function onCommand(cmd: string, conv: Conversation) {
  if (cmd === 'pin') {
    await store.togglePin(conv.id)
  } else if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('请输入新的对话名称', '重命名对话', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: conv.title,
      })
      if (value?.trim()) {
        await store.renameSession(conv.id, value.trim())
        ElMessage.success('重命名成功')
      }
    } catch { /* 取消 */ }
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(`确定删除对话「${conv.title}」吗？此操作不可恢复。`, '删除对话', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
      await store.removeSession(conv.id)
      ElMessage.success('已删除')
    } catch { /* 取消 */ }
  }
}
</script>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-right: 1px solid #eef0f2;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 16px 12px;
  font-size: 17px;
  font-weight: 700;
  color: #1f2329;
}
.brand-icon {
  font-size: 22px;
  color: #4080ff;
}
.new-btn {
  margin: 0 12px 8px;
}
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.session-item:hover {
  background: #f2f3f5;
}
.session-item.active {
  background: #e8f1ff;
}
.pin-icon {
  font-size: 14px;
  color: #c9cdd4;
  flex-shrink: 0;
}
.pin-icon.pinned {
  color: #4080ff;
}
.session-info {
  flex: 1;
  min-width: 0;
}
.session-title {
  font-size: 13px;
  color: #1f2329;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-meta {
  font-size: 11px;
  color: #a9aeb8;
  margin-top: 2px;
}
.more-icon {
  color: #a9aeb8;
  font-size: 16px;
  opacity: 0;
}
.session-item:hover .more-icon {
  opacity: 1;
}
.sidebar-footer {
  border-top: 1px solid #eef0f2;
  padding: 8px;
}
.footer-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 8px;
  font-size: 13px;
  color: #4e5969;
  cursor: pointer;
}
.footer-item:hover {
  background: #f2f3f5;
}
</style>
