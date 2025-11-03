/**
 * 蓝图分阶段生成 Composable
 */

import { ref, computed } from 'vue'
import { NovelAPI, type Stage1Data, type Stage2Data, type Stage3Data, type Stage4Data, type BlueprintDraft } from '@/api/novel'
import { API_BASE_URL, API_PREFIX } from '@/api/novel'
import { useAuthStore } from '@/stores/auth'

export function useBlueprintStage(projectId: string) {
  const currentStage = ref(1)
  const isGenerating = ref(false)
  const error = ref<string | null>(null)

  // 各阶段数据
  const stage1Data = ref<Stage1Data | null>(null)
  const stage2Data = ref<Stage2Data | null>(null)
  const stage3Data = ref<Stage3Data | null>(null)
  const stage4Data = ref<Stage4Data | null>(null)

  // 进度状态
  const progress = computed(() => {
    return (currentStage.value / 4) * 100
  })

  /**
   * 生成阶段1：核心概念
   */
  const generateStage1 = async () => {
    isGenerating.value = true
    error.value = null

    try {
      const response = await NovelAPI.generateStage1(projectId)
      stage1Data.value = response.data as Stage1Data
      // 不自动跳转，让用户确认后再跳转

      // 自动保存草稿
      await saveDraft()

      return response
    } catch (e: any) {
      error.value = e.message || '生成失败'
      throw e
    } finally {
      isGenerating.value = false
    }
  }

  /**
   * 生成阶段2：故事框架
   */
  const generateStage2 = async () => {
    if (!stage1Data.value) {
      throw new Error('请先完成阶段1')
    }

    isGenerating.value = true
    error.value = null

    try {
      const response = await NovelAPI.generateStage2(projectId, stage1Data.value)
      stage2Data.value = response.data as Stage2Data
      // 不自动跳转，让用户确认后再跳转

      // 自动保存草稿
      await saveDraft()

      return response
    } catch (e: any) {
      error.value = e.message || '生成失败'
      throw e
    } finally {
      isGenerating.value = false
    }
  }

  /**
   * 生成阶段3：角色设定
   */
  const generateStage3 = async () => {
    if (!stage1Data.value || !stage2Data.value) {
      throw new Error('请先完成前2个阶段')
    }

    isGenerating.value = true
    error.value = null

    try {
      const response = await NovelAPI.generateStage3(
        projectId,
        stage1Data.value,
        stage2Data.value
      )
      stage3Data.value = response.data as Stage3Data
      // 不自动跳转，让用户确认后再跳转

      // 自动保存草稿
      await saveDraft()

      return response
    } catch (e: any) {
      error.value = e.message || '生成失败'
      throw e
    } finally {
      isGenerating.value = false
    }
  }

  /**
   * 生成阶段4：章节规划（SSE流式）
   */
  const generateStage4 = async (onChapter?: (chapter: any) => void) => {
    if (!stage1Data.value || !stage2Data.value || !stage3Data.value) {
      throw new Error('请先完成前3个阶段')
    }

    isGenerating.value = true
    error.value = null

    try {
      // 确保草稿已保存（包含前3个阶段的数据）
      await saveDraft()

      const authStore = useAuthStore()
      const token = authStore.token || localStorage.getItem('token')
      if (!token) {
        throw new Error('未登录，请先登录')
      }

      const url = `${API_BASE_URL}${API_PREFIX}/blueprint/${projectId}/generate-stage/4/stream?token=${encodeURIComponent(token)}`
      const eventSource = new EventSource(url)

      return new Promise((resolve, reject) => {
        eventSource.addEventListener('chapter', (e: MessageEvent) => {
          const chapter = JSON.parse(e.data)
          if (onChapter) {
            onChapter(chapter)
          }
        })

        eventSource.addEventListener('complete', (e: MessageEvent) => {
          const data = JSON.parse(e.data)
          stage4Data.value = data as Stage4Data
          eventSource.close()
          isGenerating.value = false

          // 保存草稿
          saveDraft().then(() => {
            resolve(data)
          })
        })

        eventSource.addEventListener('error', (e: MessageEvent) => {
          console.error('❌ SSE错误事件:', e)
          const errorData = JSON.parse(e.data)
          error.value = errorData.error || '生成失败'
          eventSource.close()
          isGenerating.value = false
          reject(new Error(error.value || '生成失败'))
        })

        eventSource.onerror = (event) => {
          console.error('❌ SSE连接错误:', event)
          error.value = '连接失败或中断'
          eventSource.close()
          isGenerating.value = false
          reject(new Error(error.value))
        }
      })
    } catch (e: any) {
      error.value = e.message || '生成失败'
      isGenerating.value = false
      throw e
    }
  }

  /**
   * 保存草稿
   */
  const saveDraft = async () => {
    const draft: BlueprintDraft = {
      current_stage: currentStage.value,
      stage1: stage1Data.value || undefined,
      stage2: stage2Data.value || undefined,
      stage3: stage3Data.value || undefined,
      stage4: stage4Data.value || undefined
    }

    try {
      await NovelAPI.saveDraft(projectId, draft)
    } catch (e: any) {
      console.error('保存草稿失败:', e)
      // 不抛出异常，因为草稿保存失败不应该影响主流程
    }
  }

  /**
   * 加载草稿
   */
  const loadDraft = async () => {
    try {
      const response = await NovelAPI.getDraft(projectId)
      if (response.exists && response.draft) {
        const draft = response.draft
        currentStage.value = draft.current_stage
        stage1Data.value = draft.stage1 || null
        stage2Data.value = draft.stage2 || null
        stage3Data.value = draft.stage3 || null
        stage4Data.value = draft.stage4 || null
        return true
      }
      return false
    } catch (e: any) {
      console.error('加载草稿失败:', e)
      return false
    }
  }

  /**
   * 删除草稿
   */
  const deleteDraft = async () => {
    try {
      await NovelAPI.deleteDraft(projectId)
      currentStage.value = 1
      stage1Data.value = null
      stage2Data.value = null
      stage3Data.value = null
      stage4Data.value = null
    } catch (e: any) {
      console.error('删除草稿失败:', e)
    }
  }

  /**
   * 重新生成当前阶段
   */
  const regenerateCurrentStage = async () => {
    switch (currentStage.value) {
      case 1:
        return generateStage1()
      case 2:
        return generateStage2()
      case 3:
        return generateStage3()
      case 4:
        return generateStage4()
      default:
        throw new Error('无效的阶段')
    }
  }

  /**
   * 跳转到指定阶段
   */
  const goToStage = (stage: number) => {
    if (stage < 1 || stage > 4) {
      throw new Error('无效的阶段')
    }
    currentStage.value = stage
  }

  /**
   * 更新阶段数据（用户手动编辑后）
   */
  const updateStageData = async (stage: number, data: any) => {
    switch (stage) {
      case 1:
        stage1Data.value = data
        break
      case 2:
        stage2Data.value = data
        break
      case 3:
        stage3Data.value = data
        break
      case 4:
        stage4Data.value = data
        break
    }

    await saveDraft()
  }

  return {
    // 状态
    currentStage,
    isGenerating,
    error,
    progress,

    // 数据
    stage1Data,
    stage2Data,
    stage3Data,
    stage4Data,

    // 方法
    generateStage1,
    generateStage2,
    generateStage3,
    generateStage4,
    saveDraft,
    loadDraft,
    deleteDraft,
    regenerateCurrentStage,
    goToStage,
    updateStageData
  }
}

