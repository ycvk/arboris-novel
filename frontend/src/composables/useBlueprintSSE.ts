import { reactive, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

export interface BlueprintSSEState {
  isGenerating: boolean
  progress: number
  currentStep: number
  totalSteps: number
  statusMessage: string
  error: string | null
}

export function useBlueprintSSE() {
  const state = reactive<BlueprintSSEState>({
    isGenerating: false,
    progress: 0,
    currentStep: 0,
    totalSteps: 7,
    statusMessage: '',
    error: null
  })

  let abortController: AbortController | null = null
  let timeoutTimer: number | null = null

  const startGeneration = (projectId: string): Promise<any> => {
    return new Promise(async (resolve, reject) => {
      state.isGenerating = true
      state.progress = 0
      state.currentStep = 0
      state.error = null
      state.statusMessage = '正在连接...'

      const authStore = useAuthStore()
      const url = `/api/blueprint/${projectId}/generate-stream`

      abortController = new AbortController()

      timeoutTimer = window.setTimeout(() => {
        cleanup()
        reject(new Error('生成超时（10分钟）'))
      }, 600000)  // 10分钟

      try {
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${authStore.token}`,
            'Accept': 'text/event-stream'
          },
          signal: abortController.signal
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        const reader = response.body?.getReader()
        const decoder = new TextDecoder()

        if (!reader) {
          throw new Error('无法读取响应流')
        }

        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()

          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (!line.trim()) continue

            const [eventLine, dataLine] = line.split('\n')
            if (!eventLine.startsWith('event:') || !dataLine.startsWith('data:')) {
              continue
            }

            const eventType = eventLine.substring(6).trim()
            const eventData = dataLine.substring(5).trim()

            try {
              const data = JSON.parse(eventData)

              if (eventType === 'progress') {
                state.currentStep = data.step
                state.totalSteps = data.total
                state.progress = data.percentage
                state.statusMessage = data.message
              } else if (eventType === 'complete') {
                state.progress = 100
                state.statusMessage = '生成完成！'
                cleanup()
                resolve(data.blueprint)
                return
              } else if (eventType === 'error') {
                state.error = data.error || '生成失败，请重试'
                cleanup()
                reject(new Error(data.error))
                return
              }
            } catch (err) {
              console.error('解析SSE数据失败:', err, eventData)
            }
          }
        }

        cleanup()
      } catch (err: any) {
        if (err.name === 'AbortError') {
          reject(new Error('生成已取消'))
        } else {
          state.error = err.message || '生成失败，请重试'
          cleanup()
          reject(err)
        }
      }
    })
  }

  const cleanup = () => {
    if (abortController) {
      abortController.abort()
      abortController = null
    }

    if (timeoutTimer) {
      clearTimeout(timeoutTimer)
      timeoutTimer = null
    }

    state.isGenerating = false
  }

  onUnmounted(() => {
    cleanup()
  })

  return {
    state,
    startGeneration,
    cleanup
  }
}
