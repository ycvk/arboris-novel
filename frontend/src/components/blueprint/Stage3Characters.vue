<template>
  <div class="stage-container">
    <div class="stage-header">
      <h2 class="text-2xl font-bold">阶段 3：角色设定</h2>
      <p class="text-gray-600 mt-2">创建角色列表和角色关系</p>
    </div>

    <div v-if="isGenerating" class="loading-state">
      <n-spin size="large" />
      <p class="mt-4 text-gray-600">AI 正在生成角色设定...</p>
    </div>

    <div v-else-if="data" class="stage-content">
      <n-tabs type="line">
        <n-tab-pane name="characters" tab="角色列表">
          <div class="characters-list">
            <n-card
              v-for="(char, index) in formData.characters"
              :key="index"
              class="character-card mb-4"
            >
              <template #header>
                <div class="flex justify-between items-center">
                  <span class="font-semibold">{{ char.name || `角色 ${index + 1}` }}</span>
                  <n-button
                    v-if="isEditing"
                    text
                    type="error"
                    @click="removeCharacter(index)"
                  >
                    删除
                  </n-button>
                </div>
              </template>
              <pre class="whitespace-pre-wrap">{{ JSON.stringify(char, null, 2) }}</pre>
            </n-card>

            <n-button v-if="isEditing" @click="addCharacter" class="mt-4">
              + 添加角色
            </n-button>
          </div>
        </n-tab-pane>

        <n-tab-pane name="relationships" tab="角色关系">
          <div class="relationships-list">
            <n-card
              v-for="(rel, index) in formData.relationships"
              :key="index"
              class="relationship-card mb-4"
            >
              <pre class="whitespace-pre-wrap">{{ JSON.stringify(rel, null, 2) }}</pre>
            </n-card>
          </div>
        </n-tab-pane>
      </n-tabs>

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

          <n-button @click="handleBack">
            <template #icon>
              <n-icon><ArrowLeftOutlined /></n-icon>
            </template>
            返回上一步
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
      <p class="text-gray-600">点击下方按钮开始生成角色设定</p>
      <n-button type="primary" size="large" @click="handleGenerate" class="mt-4">
        开始生成
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  NCard,
  NTabs,
  NTabPane,
  NButton,
  NSpace,
  NSpin,
  NIcon,
  useMessage
} from 'naive-ui'
import { EditOutlined, ReloadOutlined, ArrowRightOutlined, ArrowLeftOutlined } from '@vicons/antd'
import type { Stage3Data } from '@/api/novel'

const props = defineProps<{
  data: Stage3Data | null
  isGenerating: boolean
}>()

const emit = defineEmits<{
  generate: []
  regenerate: []
  confirm: [data: Stage3Data]
  update: [data: Stage3Data]
  back: []
}>()

const message = useMessage()
const isEditing = ref(false)
const isRegenerating = ref(false)

const formData = ref<Stage3Data>({
  characters: [],
  relationships: []
})

watch(
  () => props.data,
  (newData) => {
    if (newData) {
      formData.value = JSON.parse(JSON.stringify(newData))
      isEditing.value = false
    }
  },
  { immediate: true }
)

const addCharacter = () => {
  formData.value.characters.push({
    name: '',
    role: '',
    description: ''
  })
}

const removeCharacter = (index: number) => {
  formData.value.characters.splice(index, 1)
}

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

const handleSave = () => {
  emit('update', formData.value)
  isEditing.value = false
  message.success('修改已保存')
}

const handleCancel = () => {
  if (props.data) {
    formData.value = JSON.parse(JSON.stringify(props.data))
  }
  isEditing.value = false
}

const handleConfirm = () => {
  emit('confirm', formData.value)
}

const handleBack = () => {
  emit('back')
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

.character-card,
.relationship-card {
  background: #f9f9f9;
}
</style>

