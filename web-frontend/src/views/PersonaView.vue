<template>
  <div class="persona-view">
    <div class="page-header">
      <el-button text @click="router.push('/')">
        <el-icon><ArrowLeft /></el-icon>&nbsp;返回
      </el-button>
      <span class="page-title">分身管理</span>
      <el-button
        type="primary"
        plain
        :disabled="personaStore.customCount >= 3"
        @click="createVisible = true"
      >
        <el-icon><Plus /></el-icon>&nbsp;新建分身
      </el-button>
    </div>

    <div class="page-body">
      <el-alert
        type="info"
        :closable="false"
        class="limit-alert"
        :title="`自定义分身上限 3 个，当前 ${personaStore.customCount}/3；预置分身不可删除或改名，可调整权重或重置。`"
      />

      <div class="persona-grid">
        <el-card v-for="p in personaStore.personas" :key="p.id" shadow="never" class="persona-card">
          <div class="card-head">
            <span class="p-name">{{ p.name }}</span>
            <el-tag size="small" effect="plain" :type="prefType(p.risk_preference)">
              {{ prefLabel(p.risk_preference) }}
            </el-tag>
            <el-tag v-if="p.is_preset" size="small" type="info" effect="plain">预置</el-tag>
            <el-tag v-else size="small" type="success" effect="plain">自定义</el-tag>
          </div>

          <div class="p-principle">
            <span class="label">核心原则：</span>{{ p.core_principle || '—' }}
          </div>

          <div class="p-weight">
            <span class="label">会商权重：</span>
            <el-slider
              :model-value="p.weight"
              :min="0"
              :max="1"
              :step="0.05"
              class="weight-slider"
              @change="(v: number) => onWeightChange(p, v)"
            />
            <span class="weight-val">{{ p.weight.toFixed(2) }}</span>
          </div>

          <div class="card-actions">
            <el-button
              v-if="p.is_preset"
              size="small"
              text
              @click="onReset(p.id)"
            >
              <el-icon><RefreshLeft /></el-icon>&nbsp;重置为默认
            </el-button>
            <template v-else>
              <el-button
                size="small"
                text
                @click="openEdit(p)"
              >
                <el-icon><Edit /></el-icon>&nbsp;编辑
              </el-button>
              <el-button
                size="small"
                type="danger"
                text
                @click="onDelete(p)"
              >
                <el-icon><Delete /></el-icon>&nbsp;删除
              </el-button>
            </template>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 新建分身 -->
    <el-dialog v-model="createVisible" title="新建自定义分身" width="480px">
      <el-form label-width="90px">
        <el-form-item label="分身名称">
          <el-input v-model="form.name" placeholder="如：长期主义分身" maxlength="20" />
        </el-form-item>
        <el-form-item label="风险偏好">
          <el-select v-model="form.risk_preference" class="full-width">
            <el-option label="激进（机会优先）" value="aggressive" />
            <el-option label="中性（凯利数学）" value="neutral" />
            <el-option label="保守（生存优先）" value="conservative" />
            <el-option label="自定义（依据核心原则）" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="核心原则">
          <el-input
            v-model="form.core_principle"
            type="textarea"
            :rows="3"
            placeholder="风险偏好选「自定义」时必填，描述该分身的决策原则"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑自定义分身 -->
    <el-dialog v-model="editVisible" title="编辑分身" width="480px">
      <el-form label-width="90px">
        <el-form-item label="分身名称">
          <el-input v-model="editForm.name" placeholder="分身名称" maxlength="20" />
        </el-form-item>
        <el-form-item label="风险偏好">
          <el-select v-model="editForm.risk_preference" class="full-width">
            <el-option label="激进（机会优先）" value="aggressive" />
            <el-option label="中性（凯利数学）" value="neutral" />
            <el-option label="保守（生存优先）" value="conservative" />
            <el-option label="自定义（依据核心原则）" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="核心原则">
          <el-input
            v-model="editForm.core_principle"
            type="textarea"
            :rows="4"
            placeholder="描述该分身的决策原则"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="onEditSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { usePersonaStore } from '../stores/persona'
import type { Persona } from '../types'

const router = useRouter()
const personaStore = usePersonaStore()

const createVisible = ref(false)
const creating = ref(false)
const form = reactive({ name: '', risk_preference: 'neutral', core_principle: '' })

// 编辑自定义分身
const editVisible = ref(false)
const editing = ref(false)
const editTargetId = ref<number | null>(null)
const editForm = reactive({ name: '', risk_preference: 'neutral', core_principle: '' })

function openEdit(p: Persona) {
  editTargetId.value = p.id
  editForm.name = p.name
  editForm.risk_preference = p.risk_preference
  editForm.core_principle = p.core_principle || ''
  editVisible.value = true
}

async function onEditSave() {
  if (editTargetId.value === null) return
  if (!editForm.name.trim()) {
    ElMessage.warning('请输入分身名称')
    return
  }
  if (editForm.risk_preference === 'custom' && !editForm.core_principle.trim()) {
    ElMessage.warning('风险偏好为「自定义」时必须填写核心原则')
    return
  }
  editing.value = true
  try {
    await personaStore.update(editTargetId.value, {
      name: editForm.name.trim(),
      risk_preference: editForm.risk_preference,
      core_principle: editForm.core_principle.trim(),
    })
    ElMessage.success('分身已更新')
    editVisible.value = false
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    editing.value = false
  }
}

onMounted(async () => {
  if (!personaStore.personas.length) await personaStore.loadPersonas()
})

function prefLabel(p: string): string {
  return { aggressive: '激进', neutral: '中性', conservative: '保守', custom: '自定义' }[p] || p
}
function prefType(p: string): 'danger' | 'success' | 'info' {
  return ({ aggressive: 'danger', neutral: 'info', conservative: 'success' } as const)[
    p as 'aggressive' | 'neutral' | 'conservative'
  ] || 'info'
}

async function onWeightChange(p: Persona, v: number | number[]) {
  const value = Array.isArray(v) ? v[0] : v
  await personaStore.update(p.id, { weight: value })
  ElMessage.success(`「${p.name}」权重已更新为 ${value.toFixed(2)}`)
}

async function onReset(id: number) {
  await personaStore.reset(id)
  ElMessage.success('已重置为默认值')
}

async function onDelete(p: Persona) {
  try {
    await ElMessageBox.confirm(`确定删除分身「${p.name}」吗？`, '删除分身', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await personaStore.remove(p.id)
    ElMessage.success('已删除')
  } catch { /* 取消 */ }
}

async function onCreate() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入分身名称')
    return
  }
  if (form.risk_preference === 'custom' && !form.core_principle.trim()) {
    ElMessage.warning('风险偏好为「自定义」时必须填写核心原则')
    return
  }
  creating.value = true
  try {
    await personaStore.create({
      name: form.name.trim(),
      risk_preference: form.risk_preference,
      core_principle: form.core_principle.trim() || undefined,
    })
    ElMessage.success('分身创建成功')
    createVisible.value = false
    Object.assign(form, { name: '', risk_preference: 'neutral', core_principle: '' })
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.persona-view {
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
  flex: 1;
  font-size: 16px;
  font-weight: 600;
}
.page-body {
  max-width: 960px;
  margin: 20px auto;
  padding: 0 24px;
}
.limit-alert {
  margin-bottom: 16px;
}
.persona-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.persona-card {
  border-radius: 10px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.p-name {
  font-size: 15px;
  font-weight: 600;
}
.p-principle {
  margin-top: 10px;
  font-size: 13px;
  color: #4e5969;
  line-height: 1.6;
}
.label {
  color: #8f959e;
}
.p-weight {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 13px;
}
.weight-slider {
  flex: 1;
}
.weight-val {
  width: 36px;
  text-align: right;
  color: #1f2329;
}
.card-actions {
  margin-top: 6px;
  text-align: right;
}
.full-width {
  width: 100%;
}
</style>
