<template>
  <div class="stage-container">
    <div class="stage-header">
      <h2 class="text-2xl font-bold">阶段 1：核心概念</h2>
      <p class="text-gray-600 mt-2">定义小说的基本信息和核心创意</p>
    </div>

    <div v-if="isGenerating" class="loading-state">
      <n-spin size="large" />
      <p class="mt-4 text-gray-600">AI 正在生成核心概念...</p>
    </div>

    <div v-else-if="data" class="stage-content">
      <n-form ref="formRef" :model="formData" :rules="rules" label-placement="top">
        <n-form-item label="小说标题" path="title">
          <n-input
            v-model:value="formData.title"
            placeholder="请输入小说标题"
            :disabled="!isEditing"
          />
        </n-form-item>

        <n-form-item label="类型/流派" path="genre">
          <n-input
            v-model:value="formData.genre"
            placeholder="例如：玄幻、都市、科幻"
            :disabled="!isEditing"
          />
        </n-form-item>

        <n-form-item label="基调/风格" path="tone">
          <n-input
            v-model:value="formData.tone"
            placeholder="例如：轻松幽默、严肃深沉"
            :disabled="!isEditing"
          />
        </n-form-item>

        <n-form-item label="目标读者" path="target_audience">
          <n-input
            v-model:value="formData.target_audience"
            placeholder="例如：青少年、成年读者"
            :disabled="!isEditing"
          />
        </n-form-item>

        <n-form-item label="文风" path="style">
          <n-input
            v-model:value="formData.style"
            placeholder="例如：简洁明快、华丽细腻"
            :disabled="!isEditing"
          />
        </n-form-item>

        <n-form-item label="一句话简介" path="one_sentence_summary">
          <n-input
            v-model:value="formData.one_sentence_summary"
            type="textarea"
            :rows="3"
            placeholder="用一句话概括你的小说"
            :disabled="!isEditing"
          />
        </n-form-item>
      </n-form>

      <div class="action-buttons">
        <n-space>
          <n-button v-if="!isEditing" @click="isEditing = true">
            <template #icon>
              <n-icon><EditOutlined /></n-icon>
            </template>
            编辑
          </n-button>

          <template v-else>
            <n-button @click="handleCancel">取消</n-button>
            <n-button type="primary" @click="handleSave">保存修改</n-button>
          </template>

          <n-button @click="handleRegenerate" :loading="isRegenerating">
            <template #icon>
              <n-icon><ReloadOutlined /></n-icon>
            </template>
            重新生成
          </n-button>

          <n-button type="success" @click="handleConfirm" :disabled="isEditing">
            确认并继续
            <template #icon>
              <n-icon><ArrowRightOutlined /></n-icon>
            </template>
          </n-button>
        </n-space>
      </div>
    </div>

    <div v-else class="empty-state">
      <p class="text-gray-600">点击下方按钮开始生成核心概念</p>
      <n-button type="primary" size="large" @click="handleGenerate" class="mt-4">
        开始生成
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NForm, NFormItem, NInput, NButton, NSpace, NSpin, NIcon, useMessage } from 'naive-ui'
import { EditOutlined, ReloadOutlined, ArrowRightOutlined } from '@vicons/antd'
import type { Stage1Data } from '@/api/novel'

const props = defineProps<{
  data: Stage1Data | null
  isGenerating: boolean
}>()

const emit = defineEmits<{
  generate: []
  regenerate: []
  confirm: [data: Stage1Data]
  update: [data: Stage1Data]
}>()

const message = useMessage()
const formRef = ref()
const isEditing = ref(false)
const isRegenerating = ref(false)

const formData = ref<Stage1Data>({
  title: '',
  genre: '',
  tone: '',
  target_audience: '',
  style: '',
  one_sentence_summary: ''
})

const rules = {
  title: { required: true, message: '请输入小说标题', trigger: 'blur' },
  genre: { required: true, message: '请输入类型/流派', trigger: 'blur' },
  tone: { required: true, message: '请输入基调/风格', trigger: 'blur' },
  one_sentence_summary: { required: true, message: '请输入一句话简介', trigger: 'blur' }
}

// 监听数据变化
watch(
  () => props.data,
  (newData) => {
    if (newData) {
      formData.value = { ...newData }
      isEditing.value = false
    }
  },
  { immediate: true }
)

const handleGenerate = () => {
  emit('generate')
}

const handleRegenerate = async () => {
  isRegenerating.value = true
  try {
    emit('regenerate')
  } finally {
    setTimeout(() => {
      isRegenerating.value = false
    }, 1000)
  }
}

const handleSave = async () => {
  try {
    await formRef.value?.validate()
    emit('update', formData.value)
    isEditing.value = false
    message.success('修改已保存')
  } catch (e) {
    message.error('请填写必填项')
  }
}

const handleCancel = () => {
  if (props.data) {
    formData.value = { ...props.data }
  }
  isEditing.value = false
}

const handleConfirm = async () => {
  try {
    await formRef.value?.validate()
    emit('confirm', formData.value)
  } catch (e) {
    message.error('请填写必填项')
  }
}
</script>

<style scoped>
.stage-container {
  padding: 24px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.stage-header {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e8e8e8;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}

.stage-content {
  margin-top: 24px;
}

.action-buttons {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  justify-content: flex-end;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}
</style>

