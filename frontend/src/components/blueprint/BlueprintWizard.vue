<template>
  <div class="blueprint-wizard">
    <!-- 进度指示器 -->
    <div class="progress-indicator">
      <n-steps :current="currentStage" :status="stepsStatus">
        <n-step title="核心概念" description="定义基本信息" />
        <n-step title="故事框架" description="构建梗概和世界观" />
        <n-step title="角色设定" description="创建角色和关系" />
        <n-step title="章节规划" description="生成章节大纲" />
      </n-steps>
    </div>

    <!-- 草稿恢复提示 -->
    <n-alert v-if="hasDraft && !draftLoaded" type="info" class="mt-4" closable>
      <template #header>发现未完成的蓝图草稿</template>
      <div class="flex items-center justify-between">
        <span>您有一个未完成的蓝图草稿，是否继续？</span>
        <n-space>
          <n-button size="small" @click="loadDraft">继续草稿</n-button>
          <n-button size="small" type="error" @click="deleteDraft">删除草稿</n-button>
        </n-space>
      </div>
    </n-alert>

    <!-- 阶段内容 -->
    <div class="stage-wrapper mt-6">
      <Stage1Concept
        v-if="currentStage === 1"
        :data="stage1Data"
        :is-generating="isGenerating"
        @generate="handleStage1Generate"
        @regenerate="handleStage1Generate"
        @confirm="handleStage1Confirm"
        @update="handleStage1Update"
      />

      <Stage2Framework
        v-if="currentStage === 2"
        :data="stage2Data"
        :is-generating="isGenerating"
        @generate="handleStage2Generate"
        @regenerate="handleStage2Generate"
        @confirm="handleStage2Confirm"
        @update="handleStage2Update"
        @back="goToStage(1)"
      />

      <Stage3Characters
        v-if="currentStage === 3"
        :data="stage3Data"
        :is-generating="isGenerating"
        @generate="handleStage3Generate"
        @regenerate="handleStage3Generate"
        @confirm="handleStage3Confirm"
        @update="handleStage3Update"
        @back="goToStage(2)"
      />

      <Stage4Chapters
        v-if="currentStage === 4"
        ref="stage4Ref"
        :data="stage4Data"
        :is-generating="isGenerating"
        @generate="handleStage4Generate"
        @regenerate="handleStage4Generate"
        @confirm="handleStage4Confirm"
        @back="goToStage(3)"
      />
    </div>

    <!-- 错误提示 -->
    <n-alert v-if="error" type="error" class="mt-4" closable @close="error = null">
      {{ error }}
    </n-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { NSteps, NStep, NAlert, NSpace, NButton, useMessage } from 'naive-ui'
import { useBlueprintStage } from '@/composables/useBlueprintStage'
import Stage1Concept from './Stage1Concept.vue'
import Stage2Framework from './Stage2Framework.vue'
import Stage3Characters from './Stage3Characters.vue'
import Stage4Chapters from './Stage4Chapters.vue'

const props = defineProps<{
  projectId: string
}>()

const emit = defineEmits<{
  complete: [data: any]
}>()

const message = useMessage()
const stage4Ref = ref()

const {
  currentStage,
  isGenerating,
  error,
  progress,
  stage1Data,
  stage2Data,
  stage3Data,
  stage4Data,
  generateStage1,
  generateStage2,
  generateStage3,
  generateStage4,
  loadDraft: loadDraftFn,
  deleteDraft: deleteDraftFn,
  goToStage,
  updateStageData
} = useBlueprintStage(props.projectId)

const hasDraft = ref(false)
const draftLoaded = ref(false)

const stepsStatus = computed(() => {
  if (error.value) return 'error'
  if (isGenerating.value) return 'process'
  return 'process'
})

onMounted(async () => {
  // 检查是否有草稿
  const loaded = await loadDraftFn()
  if (loaded) {
    hasDraft.value = true
  }
})

const loadDraft = async () => {
  draftLoaded.value = true
  hasDraft.value = false
  message.success('草稿已加载')
}

const deleteDraft = async () => {
  await deleteDraftFn()
  hasDraft.value = false
  message.success('草稿已删除')
}

// 阶段1处理
const handleStage1Generate = async () => {
  try {
    await generateStage1()
    message.success('核心概念生成成功！')
  } catch (e: any) {
    message.error(e.message || '生成失败')
  }
}

const handleStage1Confirm = async (data: any) => {
  console.log('✅ 阶段1确认，接收到的数据:', data)
  // 先切换到下一阶段，再保存数据（这样草稿中的 current_stage 就是下一阶段）
  goToStage(2)
  await updateStageData(1, data)
}

const handleStage1Update = async (data: any) => {
  await updateStageData(1, data)
}

// 阶段2处理
const handleStage2Generate = async () => {
  try {
    await generateStage2()
    message.success('故事框架生成成功！')
  } catch (e: any) {
    message.error(e.message || '生成失败')
  }
}

const handleStage2Confirm = async (data: any) => {
  console.log('✅ 阶段2确认，接收到的数据:', data)
  // 先切换到下一阶段，再保存数据（这样草稿中的 current_stage 就是下一阶段）
  goToStage(3)
  await updateStageData(2, data)
}

const handleStage2Update = async (data: any) => {
  await updateStageData(2, data)
}

// 阶段3处理
const handleStage3Generate = async () => {
  try {
    await generateStage3()
    message.success('角色设定生成成功！')
  } catch (e: any) {
    message.error(e.message || '生成失败')
  }
}

const handleStage3Confirm = async (data: any) => {
  console.log('✅ 阶段3确认，接收到的数据:', data)
  // 先切换到下一阶段，再保存数据（这样草稿中的 current_stage 就是下一阶段）
  goToStage(4)
  await updateStageData(3, data)
}

const handleStage3Update = async (data: any) => {
  await updateStageData(3, data)
}

// 阶段4处理
const handleStage4Generate = async () => {
  try {
    await generateStage4((chapter) => {
      // 逐章回调
      if (stage4Ref.value) {
        stage4Ref.value.onChapterGenerated(chapter)
      }
    })
    message.success('章节规划生成成功！')
  } catch (e: any) {
    message.error(e.message || '生成失败')
  }
}

const handleStage4Confirm = async (data: any) => {
  await updateStageData(4, data)
  
  // 完成蓝图创建
  const blueprintData = {
    ...stage1Data.value,
    ...stage2Data.value,
    ...stage3Data.value,
    ...stage4Data.value
  }
  
  emit('complete', blueprintData)
  message.success('蓝图创建完成！')
}
</script>

<style scoped>
.blueprint-wizard {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.progress-indicator {
  background: white;
  padding: 24px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.stage-wrapper {
  min-height: 400px;
}
</style>

