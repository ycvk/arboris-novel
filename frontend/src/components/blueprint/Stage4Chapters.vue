<template>
  <div class="stage-container">
    <div class="stage-header">
      <h2 class="text-2xl font-bold">阶段 4：章节规划</h2>
      <p class="text-gray-600 mt-2">生成章节大纲</p>
    </div>

    <div v-if="isGenerating" class="loading-state">
      <n-spin size="large" />
      <p class="mt-4 text-gray-600">AI 正在生成章节规划...</p>
      <n-progress
        v-if="generatedChapters > 0"
        type="line"
        :percentage="(generatedChapters / totalChapters) * 100"
        :show-indicator="false"
        class="mt-4 w-64"
      />
      <p v-if="generatedChapters > 0" class="text-sm text-gray-500 mt-2">
        已生成 {{ generatedChapters }} / {{ totalChapters }} 章
      </p>
    </div>

    <div v-else-if="data && data.chapter_outline.length > 0" class="stage-content">
      <div class="chapters-list">
        <n-collapse>
          <n-collapse-item
            v-for="(chapter, index) in formData.chapter_outline"
            :key="index"
            :title="`第 ${chapter.chapter_number || index + 1} 章：${chapter.title || '未命名'}`"
          >
            <pre class="whitespace-pre-wrap">{{ JSON.stringify(chapter, null, 2) }}</pre>
          </n-collapse-item>
        </n-collapse>
      </div>

      <div class="action-buttons">
        <n-space>
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

          <n-button type="success" @click="handleConfirm">
            完成蓝图创建
            <template #icon>
              <n-icon><CheckOutlined /></n-icon>
            </template>
          </n-button>
        </n-space>
      </div>
    </div>

    <div v-else class="empty-state">
      <p class="text-gray-600">点击下方按钮开始生成章节规划</p>
      <n-button type="primary" size="large" @click="handleGenerate" class="mt-4">
        开始生成
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  NCollapse,
  NCollapseItem,
  NButton,
  NSpace,
  NSpin,
  NIcon,
  NProgress,
  useMessage
} from 'naive-ui'
import { ReloadOutlined, ArrowLeftOutlined, CheckOutlined } from '@vicons/antd'
import type { Stage4Data } from '@/api/novel'

const props = defineProps<{
  data: Stage4Data | null
  isGenerating: boolean
}>()

const emit = defineEmits<{
  generate: []
  regenerate: []
  confirm: [data: Stage4Data]
  back: []
  chapterGenerated: [chapter: any]
}>()

const message = useMessage()
const isRegenerating = ref(false)
const generatedChapters = ref(0)
const totalChapters = ref(0)

const formData = ref<Stage4Data>({
  chapter_outline: []
})

watch(
  () => props.data,
  (newData) => {
    if (newData) {
      formData.value = JSON.parse(JSON.stringify(newData))
      totalChapters.value = newData.chapter_outline.length
    }
  },
  { immediate: true }
)

const handleGenerate = () => {
  generatedChapters.value = 0
  totalChapters.value = 0
  emit('generate')
}

const handleRegenerate = async () => {
  isRegenerating.value = true
  generatedChapters.value = 0
  try {
    emit('regenerate')
  } finally {
    setTimeout(() => {
      isRegenerating.value = false
    }, 1000)
  }
}

const handleConfirm = () => {
  emit('confirm', formData.value)
}

const handleBack = () => {
  emit('back')
}

// 暴露方法供父组件调用
defineExpose({
  onChapterGenerated: (chapter: any) => {
    generatedChapters.value++
    emit('chapterGenerated', chapter)
  }
})
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

.chapters-list {
  max-height: 600px;
  overflow-y: auto;
}
</style>

