<template>
  <div class="space-y-6 relative">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold text-slate-900">章节大纲</h2>
        <p class="text-sm text-slate-500">故事结构与章节节奏一目了然</p>
      </div>
      <div v-if="editable" class="flex items-center gap-2">
        <button
          type="button"
          class="flex items-center gap-1 px-3 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg"
          @click="$emit('add')"
        >
          <svg class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 5a1 1 0 011 1v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0v-3H6a1 1 0 110-2h3V6a1 1 0 011-1z" clip-rule="evenodd" />
          </svg>
          新增章节
        </button>
        <button
          type="button"
          class="flex items-center gap-1 px-3 py-2 text-sm text-gray-500 hover:text-indigo-600 transition-colors"
          @click="emitEdit('chapter_outline', '章节大纲', outline)"
        >
          <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" />
            <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" />
          </svg>
          编辑大纲
        </button>
      </div>
    </div>

    <ol class="relative border-l border-slate-200 ml-3 space-y-8">
      <li
        v-for="chapter in outline"
        :key="chapter.chapter_number"
        class="ml-6"
      >
        <span class="absolute -left-3 mt-1 flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500 text-white text-xs font-semibold">
          {{ chapter.chapter_number }}
        </span>
        <div class="bg-white/95 rounded-2xl border border-slate-200 shadow-sm p-5">
          <div class="flex items-center justify-between gap-4">
            <h3 class="text-lg font-semibold text-slate-900">{{ chapter.title || `第${chapter.chapter_number}章` }}</h3>
            <div class="flex items-center gap-3">
              <button
                v-if="editable"
                type="button"
                class="text-xs px-2.5 py-1 rounded-lg border transition-colors"
                :class="splittingChapterNumber === chapter.chapter_number ? 'bg-indigo-200 text-indigo-700 border-indigo-200 cursor-not-allowed' : 'bg-indigo-50 text-indigo-600 hover:bg-indigo-100 border-indigo-100'"
                :disabled="splittingChapterNumber === chapter.chapter_number || isSplitting"
                @click="openSplitModal(chapter.chapter_number)"
                title="将本章拆分为多章"
              >
                <span v-if="splittingChapterNumber === chapter.chapter_number" class="inline-flex items-center gap-1">
                  <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <circle cx="12" cy="12" r="10" stroke-width="4" class="opacity-25" />
                    <path d="M4 12a8 8 0 018-8" stroke-width="4" class="opacity-75" />
                  </svg>
                  拆分中...
                </span>
                <span v-else>拆分本章</span>
              </button>
              <span class="text-xs text-slate-400">#{{ chapter.chapter_number }}</span>
            </div>
          </div>
          <p class="mt-3 text-sm text-slate-600 leading-6 whitespace-pre-line">{{ chapter.summary || '暂无摘要' }}</p>
        </div>
      </li>
      <li v-if="!outline.length" class="ml-6 text-slate-400 text-sm">暂无章节大纲</li>
    </ol>
    <!-- 拆分中的全局遮罩动画 -->
    <div v-if="isSplitting" class="absolute inset-0 bg-white/70 backdrop-blur-[1px] rounded-xl flex flex-col items-center justify-center z-10">
      <div class="relative">
        <div class="w-12 h-12 border-4 border-indigo-100 rounded-full"></div>
        <div class="absolute top-0 left-0 w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
      <p class="mt-3 text-sm text-slate-600">正在拆分第 {{ splittingChapterNumber }} 章，请稍候...</p>
    </div>

    <!-- 拆分参数弹窗 -->
    <SplitChapterModal
      v-if="showSplitModal"
      :show="showSplitModal"
      :chapter-number="pendingChapterNumber || 0"
      :default-count="3"
      @close="showSplitModal = false"
      @submit="handleSplitSubmit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { defineEmits, defineProps } from 'vue'
import { useRoute } from 'vue-router'
import { NovelAPI } from '@/api/novel'
import SplitChapterModal from '@/components/novel-detail/SplitChapterModal.vue'
import { globalAlert } from '@/composables/useAlert'

interface OutlineItem {
  chapter_number: number
  title: string
  summary: string
}

const props = defineProps<{
  outline: OutlineItem[]
  editable?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit', payload: { field: string; title: string; value: any }): void
  (e: 'add'): void
  (e: 'refresh'): void
}>()

const emitEdit = (field: string, title: string, value: any) => {
  if (!props.editable) return
  emit('edit', { field, title, value })
}

const route = useRoute()

// UI 状态
const showSplitModal = ref(false)
const isSplitting = ref(false)
const splittingChapterNumber = ref<number | null>(null)
const pendingChapterNumber = ref<number | null>(null)

const openSplitModal = (chapterNumber: number) => {
  if (!props.editable) return
  pendingChapterNumber.value = chapterNumber
  showSplitModal.value = true
}

const handleSplitSubmit = async (payload: { count: number; pacing?: string; constraints?: Record<string, any> }) => {
  if (!props.editable || pendingChapterNumber.value == null) return
  const projectId = route.params.id as string
  isSplitting.value = true
  splittingChapterNumber.value = pendingChapterNumber.value
  try {
    await NovelAPI.splitChapterOutline(
      projectId,
      pendingChapterNumber.value,
      payload.count,
      payload.pacing,
      payload.constraints
    )
    globalAlert.showSuccess(`已拆分第 ${pendingChapterNumber.value} 章为 ${payload.count} 章`)
    emit('refresh')
  } catch (err) {
    console.error('拆分本章失败:', err)
    const msg = err instanceof Error ? err.message : '未知错误'
    globalAlert.showError(`拆分失败：${msg}`)
  } finally {
    isSplitting.value = false
    splittingChapterNumber.value = null
    pendingChapterNumber.value = null
    showSplitModal.value = false
  }
}
</script>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'ChapterOutlineSection'
})
</script>
