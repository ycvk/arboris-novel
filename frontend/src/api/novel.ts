import { useAuthStore } from '@/stores/auth'
import router from '@/router'

// API 配置
// 在生产环境中使用相对路径，在开发环境中使用绝对路径
export const API_BASE_URL = import.meta.env.MODE === 'production' ? '' : 'http://127.0.0.1:8000'
export const API_PREFIX = '/api'

// 统一的请求处理函数
const request = async (url: string, options: RequestInit = {}) => {
  const authStore = useAuthStore()
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...options.headers
  })

  if (authStore.isAuthenticated && authStore.token) {
    headers.set('Authorization', `Bearer ${authStore.token}`)
  }

  const response = await fetch(url, { ...options, headers })

  if (response.status === 401) {
    // Token 失效或未授权
    authStore.logout()
    router.push('/login')
    throw new Error('会话已过期，请重新登录')
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `请求失败，状态码: ${response.status}`)
  }

  return response.json()
}

// 类型定义
export interface NovelProject {
  id: string
  title: string
  initial_prompt: string
  blueprint?: Blueprint
  chapters: Chapter[]
  conversation_history: ConversationMessage[]
}

export interface NovelProjectSummary {
  id: string
  title: string
  genre: string
  last_edited: string
  completed_chapters: number
  total_chapters: number
}

export interface Blueprint {
  title?: string
  target_audience?: string
  genre?: string
  style?: string
  tone?: string
  one_sentence_summary?: string
  full_synopsis?: string
  world_setting?: any
  characters?: Character[]
  relationships?: any[]
  chapter_outline?: ChapterOutline[]
}

export interface Character {
  name: string
  description: string
  identity?: string
  personality?: string
  goals?: string
  abilities?: string
  relationship_to_protagonist?: string
}

export interface ChapterOutline {
  chapter_number: number
  title: string
  summary: string
}

export interface ChapterVersion {
  content: string
  style?: string
}

export interface Chapter {
  chapter_number: number
  title: string
  summary: string
  content: string | null
  versions: string[] | null  // versions是字符串数组，不是对象数组
  evaluation: string | null
  generation_status: 'not_generated' | 'generating' | 'evaluating' | 'selecting' | 'failed' | 'evaluation_failed' | 'waiting_for_confirm' | 'successful'
  word_count?: number  // 字数统计
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface BlueprintProgress {
  core_spark: string | null
  genre_tone: string | null
  prose_style: string | null
  protagonist: string | null
  central_conflict: string | null
  antagonist: string | null
  inciting_incident: string | null
  core_theme: string | null
  working_titles: string[] | null
  target_length: string | null
}

export interface ConverseResponse {
  message: string
  question_type: 'open_ended' | 'multiple_choice' | 'confirmation' | 'complete'
  options: string[] | null
  blueprint_progress: BlueprintProgress
  completion_percentage: number
  next_action: 'continue' | 'generate_blueprint'
}

export interface BlueprintGenerationResponse {
  blueprint: Blueprint
  ai_message: string
}

export interface UIControl {
  type: 'single_choice' | 'text_input'
  options?: Array<{ id: string; label: string }>
  placeholder?: string
}

export interface ChapterGenerationResponse {
  versions: ChapterVersion[] // Renamed from chapter_versions for consistency
  evaluation: string | null
  ai_message: string
  chapter_number: number
}

export interface DeleteNovelsResponse {
  status: string
  message: string
}

export type NovelSectionType = 'overview' | 'world_setting' | 'characters' | 'relationships' | 'chapter_outline' | 'chapters'

export interface NovelSectionResponse {
  section: NovelSectionType
  data: Record<string, any>
}

// API 函数
const NOVELS_BASE = `${API_BASE_URL}${API_PREFIX}/novels`
const WRITER_PREFIX = '/api/writer'
const WRITER_BASE = `${API_BASE_URL}${WRITER_PREFIX}/novels`

export class NovelAPI {
  static async createNovel(title: string, initialPrompt: string): Promise<NovelProject> {
    return request(NOVELS_BASE, {
      method: 'POST',
      body: JSON.stringify({ title, initial_prompt: initialPrompt })
    })
  }

  static async getNovel(projectId: string): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}`)
  }

  static async getChapter(projectId: string, chapterNumber: number): Promise<Chapter> {
    return request(`${NOVELS_BASE}/${projectId}/chapters/${chapterNumber}`)
  }

  static async getSection(projectId: string, section: NovelSectionType): Promise<NovelSectionResponse> {
    return request(`${NOVELS_BASE}/${projectId}/sections/${section}`)
  }

  static async converseConcept(
    projectId: string,
    userInput: any,
    conversationState: any = {}
  ): Promise<ConverseResponse> {
    const formattedUserInput = userInput || { id: null, value: null }
    return request(`${NOVELS_BASE}/${projectId}/concept/converse`, {
      method: 'POST',
      body: JSON.stringify({
        user_input: formattedUserInput,
        conversation_state: conversationState
      })
    })
  }

  static async regenerateConcept(projectId: string): Promise<ConverseResponse> {
    return request(`${NOVELS_BASE}/${projectId}/concept/regenerate`, {
      method: 'POST'
    })
  }

  static async generateBlueprint(projectId: string): Promise<BlueprintGenerationResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/generate`, {
      method: 'POST'
    })
  }

  static async saveBlueprint(projectId: string, blueprint: Blueprint): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/save`, {
      method: 'POST',
      body: JSON.stringify(blueprint)
    })
  }

  static async generateChapter(projectId: string, chapterNumber: number): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/generate`, {
      method: 'POST',
      body: JSON.stringify({ chapter_number: chapterNumber })
    })
  }

  static async evaluateChapter(projectId: string, chapterNumber: number): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/evaluate`, {
      method: 'POST',
      body: JSON.stringify({ chapter_number: chapterNumber })
    })
  }

  static async selectChapterVersion(
    projectId: string,
    chapterNumber: number,
    versionIndex: number
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/select`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        version_index: versionIndex
      })
    })
  }

  static async getAllNovels(): Promise<NovelProjectSummary[]> {
    return request(NOVELS_BASE)
  }

  static async deleteNovels(projectIds: string[]): Promise<DeleteNovelsResponse> {
    return request(NOVELS_BASE, {
      method: 'DELETE',
      body: JSON.stringify(projectIds)
    })
  }

  static async updateChapterOutline(
    projectId: string,
    chapterOutline: ChapterOutline
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/update-outline`, {
      method: 'POST',
      body: JSON.stringify(chapterOutline)
    })
  }

  static async deleteChapter(
    projectId: string,
    chapterNumbers: number[]
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/delete`, {
      method: 'POST',
      body: JSON.stringify({ chapter_numbers: chapterNumbers })
    })
  }

  static async generateChapterOutline(
    projectId: string,
    startChapter: number,
    numChapters: number
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/outline`, {
      method: 'POST',
      body: JSON.stringify({
        start_chapter: startChapter,
        num_chapters: numChapters
      })
    })
  }

  static async splitChapterOutline(
    projectId: string,
    sourceChapter: number,
    targetCount: number,
    pacing?: string,
    constraints?: Record<string, any>
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/split-outline`, {
      method: 'POST',
      body: JSON.stringify({
        source_chapter: sourceChapter,
        target_count: targetCount,
        pacing,
        constraints
      })
    })
  }

  static async updateBlueprint(projectId: string, data: Record<string, any>): Promise<NovelProject> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    })
  }

  static async editChapterContent(
    projectId: string,
    chapterNumber: number,
    content: string
  ): Promise<NovelProject> {
    return request(`${WRITER_BASE}/${projectId}/chapters/edit`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        content: content
      })
    })
  }

  // ==================== 分阶段蓝图生成 ====================

  static async generateStage1(projectId: string): Promise<StageGenerationResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/blueprint/${projectId}/generate-stage/1`, {
      method: 'POST'
    })
  }

  static async generateStage2(
    projectId: string,
    stage1Data: Record<string, any>
  ): Promise<StageGenerationResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/blueprint/${projectId}/generate-stage/2`, {
      method: 'POST',
      body: JSON.stringify({ stage1_data: stage1Data })
    })
  }

  static async generateStage3(
    projectId: string,
    stage1Data: Record<string, any>,
    stage2Data: Record<string, any>
  ): Promise<StageGenerationResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/blueprint/${projectId}/generate-stage/3`, {
      method: 'POST',
      body: JSON.stringify({ stage1_data: stage1Data, stage2_data: stage2Data })
    })
  }

  static async saveDraft(projectId: string, draftData: BlueprintDraft): Promise<{ success: boolean }> {
    return request(`${API_BASE_URL}${API_PREFIX}/blueprint/${projectId}/draft`, {
      method: 'POST',
      body: JSON.stringify(draftData)
    })
  }

  static async getDraft(projectId: string): Promise<DraftResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/blueprint/${projectId}/draft`, {
      method: 'GET'
    })
  }

  static async deleteDraft(projectId: string): Promise<{ success: boolean }> {
    return request(`${API_BASE_URL}${API_PREFIX}/blueprint/${projectId}/draft`, {
      method: 'DELETE'
    })
  }
}

// ==================== 分阶段蓝图类型定义 ====================

export interface Stage1Data {
  title: string
  genre: string
  tone: string
  target_audience?: string
  style?: string
  one_sentence_summary: string
}

export interface Stage2Data {
  full_synopsis: string
  world_setting: Record<string, any>
}

export interface Stage3Data {
  characters: Array<Record<string, any>>
  relationships: Array<Record<string, any>>
}

export interface Stage4Data {
  chapter_outline: Array<Record<string, any>>
}

export interface BlueprintDraft {
  current_stage: number
  stage1?: Stage1Data
  stage2?: Stage2Data
  stage3?: Stage3Data
  stage4?: Stage4Data
}

export interface StageGenerationResponse {
  stage: number
  data: Record<string, any>
  next_stage?: number
  ai_message?: string
}

export interface DraftResponse {
  exists: boolean
  draft?: BlueprintDraft
}
