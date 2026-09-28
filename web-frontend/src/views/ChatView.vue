<template>
  <div class="chat-view">
    <div class="sidebar-wrap">
      <SessionSidebar @select="onSelect" @new-session="onNewSession" />
    </div>
    <div class="main-wrap">
      <MessageList @example="onExample" />
      <div class="composer-wrap">
        <Composer :loading="conversationStore.isStreaming" @send="onSend" @abort="onAbort" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import SessionSidebar from '../components/chat/SessionSidebar.vue'
import MessageList from '../components/chat/MessageList.vue'
import Composer from '../components/chat/Composer.vue'
import { useConversationStore } from '../stores/conversation'
import { usePersonaStore } from '../stores/persona'

const conversationStore = useConversationStore()
const personaStore = usePersonaStore()

onMounted(async () => {
  try {
    await personaStore.loadPersonas()
    await conversationStore.loadSessions()
    if (conversationStore.sessions.length) {
      await conversationStore.selectSession(conversationStore.sessions[0].id)
    }
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
})

async function onSelect(id: number) {
  try {
    await conversationStore.selectSession(id)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function onNewSession() {
  try {
    await conversationStore.newSession()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function ensureSession(): Promise<number | null> {
  if (conversationStore.activeId) return conversationStore.activeId
  if (!personaStore.personas.length) await personaStore.loadPersonas()
  return conversationStore.newSession()
}

async function onSend(text: string) {
  try {
    await ensureSession()
    await conversationStore.send(text)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function onExample(text: string) {
  await onSend(text)
}

function onAbort() {
  conversationStore.abort()
}
</script>

<style scoped>
.chat-view {
  display: flex;
  height: 100%;
}
.sidebar-wrap {
  width: 260px;
  flex-shrink: 0;
}
.main-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.composer-wrap {
  padding: 0 24px 18px;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
}
</style>
