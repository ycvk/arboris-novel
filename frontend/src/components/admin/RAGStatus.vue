<template>
  <div class="rag-status">
  <n-card title="RAG 运行状态" size="small" :bordered="false" class="mb-16">
      <n-grid :cols="4" :x-gap="16" :y-gap="12">
        <n-gi>
          <div class="stat-item"><div class="label">状态</div><div class="value">{{ statusText }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">提供方</div><div class="value">{{ status.provider || '-' }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">向量库 URL</div><div class="value">{{ status.url || '-' }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">集合前缀</div><div class="value">{{ status.collection_prefix || '-' }}</div></div>
        </n-gi>
      </n-grid>
      <n-grid :cols="4" :x-gap="16" :y-gap="12" class="mt-12">
        <n-gi>
          <div class="stat-item"><div class="label">Embedding 模型</div><div class="value">{{ status.embedding_model || '-' }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">Embedding 维度</div><div class="value">{{ status.embedding_dim ?? '-' }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">切分大小</div><div class="value">{{ status.chunk_size }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">重叠</div><div class="value">{{ status.chunk_overlap }}</div></div>
        </n-gi>
      </n-grid>
      <n-grid :cols="4" :x-gap="16" :y-gap="12" class="mt-12">
        <n-gi>
          <div class="stat-item"><div class="label">TopK(正文)</div><div class="value">{{ status.top_k_chunks }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">TopK(摘要)</div><div class="value">{{ status.top_k_summaries }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">片段总数</div><div class="value">{{ status.total_chunks }}</div></div>
        </n-gi>
        <n-gi>
          <div class="stat-item"><div class="label">摘要总数</div><div class="value">{{ status.total_summaries }}</div></div>
        </n-gi>
      </n-grid>
  </n-card>

  <n-card title="近 7 天运行指标" size="small" :bordered="false" class="mb-16">
    <n-grid :cols="3" :x-gap="16" :y-gap="12">
      <n-gi>
        <div class="stat-item"><div class="label">平均检索延迟</div><div class="value">{{ latencyText }}</div></div>
      </n-gi>
      <n-gi>
        <div class="stat-item"><div class="label">空召回率</div><div class="value">{{ emptyRateText }}</div></div>
      </n-gi>
      <n-gi>
        <div class="stat-item"><div class="label">重复片段率</div><div class="value">{{ duplicateRateText }}</div></div>
      </n-gi>
    </n-grid>
  </n-card>

    <n-card title="项目向量规模 (Top 5)" size="small" :bordered="false">
      <n-data-table :columns="columns" :data="status.top_projects" :bordered="false" size="small" />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { AdminAPI } from '@/api/admin'
import type { DataTableColumns } from 'naive-ui'
import { NCard, NDataTable, NGi, NGrid } from 'naive-ui'

interface RAGProjectStat { project_id: string; title?: string; chunks: number; summaries: number }
interface RAGStatus {
  enabled: boolean
  provider: string
  url?: string
  collection_prefix?: string
  embedding_model?: string
  embedding_dim?: number
  top_k_chunks: number
  top_k_summaries: number
  chunk_size: number
  chunk_overlap: number
  total_chunks: number
  total_summaries: number
  top_projects: RAGProjectStat[]
  avg_latency_ms_7d?: number | null
  empty_recall_rate_7d?: number | null
  duplicate_chunk_rate_7d?: number | null
}

const status = ref<RAGStatus>({
  enabled: false,
  provider: '-',
  top_k_chunks: 0,
  top_k_summaries: 0,
  chunk_size: 0,
  chunk_overlap: 0,
  total_chunks: 0,
  total_summaries: 0,
  top_projects: [],
  avg_latency_ms_7d: null as any,
  empty_recall_rate_7d: null as any,
  duplicate_chunk_rate_7d: null as any
})

const statusText = computed(() => (status.value.enabled ? '已启用' : '未启用'))
const latencyText = computed(() => status.value.avg_latency_ms_7d != null ? `${Math.round(status.value.avg_latency_ms_7d)} ms` : '-')
const emptyRateText = computed(() => status.value.empty_recall_rate_7d != null ? `${(status.value.empty_recall_rate_7d * 100).toFixed(1)}%` : '-')
const duplicateRateText = computed(() => status.value.duplicate_chunk_rate_7d != null ? `${(status.value.duplicate_chunk_rate_7d * 100).toFixed(1)}%` : '-')

const columns: DataTableColumns<RAGProjectStat> = [
  { title: '项目ID', key: 'project_id' },
  { title: '标题', key: 'title' },
  { title: '片段数', key: 'chunks' },
  { title: '摘要数', key: 'summaries' }
]

const fetchStatus = async () => {
  const data = await AdminAPI.getRAGStatus()
  status.value = data as RAGStatus
}

onMounted(() => {
  fetchStatus()
})

</script>

<script lang="ts">
export default {}
</script>

<style scoped>
.mb-16 { margin-bottom: 16px; }
.rag-status { display: flex; flex-direction: column; gap: 16px; }
.stat-item .label { color: #6b7280; font-size: 12px; }
.stat-item .value { color: #111827; font-weight: 600; font-size: 16px; margin-top: 2px; }
</style>
