<template>
  <div class="stage-container">
    <div class="stage-header">
      <h2 class="text-2xl font-bold">阶段 2：故事框架</h2>
      <p class="text-gray-600 mt-2">构建完整的故事梗概和世界观设定</p>
    </div>

    <div v-if="isGenerating" class="loading-state">
      <n-spin size="large" />
      <p class="mt-4 text-gray-600">AI 正在生成故事框架...</p>
    </div>

    <div v-else-if="data" class="stage-content">
      <n-form ref="formRef" :model="formData" :rules="rules" label-placement="top">
        <n-form-item label="完整故事梗概" path="full_synopsis">
          <n-input
            v-model:value="formData.full_synopsis"
            type="textarea"
            :rows="10"
            placeholder="详细描述故事的主要情节和发展"
            :disabled="!isEditing"
          />
        </n-form-item>

        <n-divider />

        <h3 class="text-lg font-semibold mb-4">世界观设定</h3>

        <!-- 核心规则 -->
        <n-collapse :default-expanded-names="['core_rules']" class="mb-4">
          <n-collapse-item title="核心世界规则（建议3条）" name="core_rules">
            <div class="space-y-4">
              <n-card
                v-for="(rule, index) in (formData.world_setting as WorldSetting).core_rules"
                :key="index"
                size="small"
                :title="`规则 ${index + 1}`"
                class="rule-card"
              >
                <template #header-extra>
                  <n-button
                    v-if="isEditing"
                    text
                    type="error"
                    @click="removeCoreRule(index)"
                  >
                    <template #icon>
                      <n-icon><DeleteOutlined /></n-icon>
                    </template>
                  </n-button>
                </template>

                <n-form-item label="规则内容（30-50字）" :show-feedback="false">
                  <n-input
                    v-model:value="rule.rule_content"
                    type="textarea"
                    :rows="2"
                    placeholder="世界的客观规律或运行机制"
                    :disabled="!isEditing"
                    maxlength="50"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="对主角的影响（20-30字）" :show-feedback="false">
                  <n-input
                    v-model:value="rule.impact_on_protagonist"
                    type="textarea"
                    :rows="2"
                    placeholder="规则如何影响主角"
                    :disabled="!isEditing"
                    maxlength="30"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="潜在冲突点（20-30字）" :show-feedback="false">
                  <n-input
                    v-model:value="rule.conflict_potential"
                    type="textarea"
                    :rows="2"
                    placeholder="可能引发的戏剧冲突"
                    :disabled="!isEditing"
                    maxlength="30"
                    show-count
                  />
                </n-form-item>
              </n-card>

              <n-button
                v-if="isEditing"
                dashed
                block
                @click="addCoreRule"
              >
                <template #icon>
                  <n-icon><PlusOutlined /></n-icon>
                </template>
                添加核心规则
              </n-button>
            </div>
          </n-collapse-item>
        </n-collapse>

        <!-- 关键地点 -->
        <n-collapse :default-expanded-names="['key_locations']" class="mb-4">
          <n-collapse-item title="关键地点（建议3-4个）" name="key_locations">
            <div class="space-y-4">
              <n-card
                v-for="(location, index) in (formData.world_setting as WorldSetting).key_locations"
                :key="index"
                size="small"
                :title="`地点 ${index + 1}`"
                class="location-card"
              >
                <template #header-extra>
                  <n-button
                    v-if="isEditing"
                    text
                    type="error"
                    @click="removeKeyLocation(index)"
                  >
                    <template #icon>
                      <n-icon><DeleteOutlined /></n-icon>
                    </template>
                  </n-button>
                </template>

                <n-form-item label="地点名称（3-8字）" :show-feedback="false">
                  <n-input
                    v-model:value="location.name"
                    placeholder="简洁有辨识度的名称"
                    :disabled="!isEditing"
                    maxlength="8"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="视觉描述（30-40字）" :show-feedback="false">
                  <n-input
                    v-model:value="location.visual_description"
                    type="textarea"
                    :rows="2"
                    placeholder="2-3个核心视觉元素"
                    :disabled="!isEditing"
                    maxlength="40"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="功能定位（15-20字）" :show-feedback="false">
                  <n-input
                    v-model:value="location.functional_role"
                    placeholder="场景功能定位"
                    :disabled="!isEditing"
                    maxlength="20"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="情感氛围（10-15字）" :show-feedback="false">
                  <n-input
                    v-model:value="location.emotional_tone"
                    placeholder="情感基调"
                    :disabled="!isEditing"
                    maxlength="15"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="剧情作用（30-40字）" :show-feedback="false">
                  <n-input
                    v-model:value="location.plot_usage"
                    type="textarea"
                    :rows="2"
                    placeholder="在剧情中的作用"
                    :disabled="!isEditing"
                    maxlength="40"
                    show-count
                  />
                </n-form-item>
              </n-card>

              <n-button
                v-if="isEditing"
                dashed
                block
                @click="addKeyLocation"
              >
                <template #icon>
                  <n-icon><PlusOutlined /></n-icon>
                </template>
                添加关键地点
              </n-button>
            </div>
          </n-collapse-item>
        </n-collapse>

        <!-- 主要势力 -->
        <n-collapse :default-expanded-names="['factions']" class="mb-4">
          <n-collapse-item title="主要势力（建议2-3个）" name="factions">
            <div class="space-y-4">
              <n-card
                v-for="(faction, index) in (formData.world_setting as WorldSetting).factions"
                :key="index"
                size="small"
                :title="`势力 ${index + 1}`"
                class="faction-card"
              >
                <template #header-extra>
                  <n-button
                    v-if="isEditing"
                    text
                    type="error"
                    @click="removeFaction(index)"
                  >
                    <template #icon>
                      <n-icon><DeleteOutlined /></n-icon>
                    </template>
                  </n-button>
                </template>

                <n-form-item label="势力名称（3-8字）" :show-feedback="false">
                  <n-input
                    v-model:value="faction.name"
                    placeholder="简洁有辨识度的名称"
                    :disabled="!isEditing"
                    maxlength="8"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="核心利益（20-30字）" :show-feedback="false">
                  <n-input
                    v-model:value="faction.core_interest"
                    type="textarea"
                    :rows="2"
                    placeholder="该势力的核心诉求"
                    :disabled="!isEditing"
                    maxlength="30"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="实力层级（15-20字）" :show-feedback="false">
                  <n-input
                    v-model:value="faction.power_level"
                    placeholder="在世界中的地位"
                    :disabled="!isEditing"
                    maxlength="20"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="代表人物（20-30字）" :show-feedback="false">
                  <n-input
                    v-model:value="faction.representative"
                    type="textarea"
                    :rows="2"
                    placeholder="至少1个关键角色及其特点"
                    :disabled="!isEditing"
                    maxlength="30"
                    show-count
                  />
                </n-form-item>

                <n-form-item label="与主角关系（30-40字）" :show-feedback="false">
                  <n-input
                    v-model:value="faction.relation_to_protagonist"
                    type="textarea"
                    :rows="2"
                    placeholder="与主角关系的演变"
                    :disabled="!isEditing"
                    maxlength="40"
                    show-count
                  />
                </n-form-item>
              </n-card>

              <n-button
                v-if="isEditing"
                dashed
                block
                @click="addFaction"
              >
                <template #icon>
                  <n-icon><PlusOutlined /></n-icon>
                </template>
                添加势力
              </n-button>
            </div>
          </n-collapse-item>
        </n-collapse>
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
      <p class="text-gray-600">点击下方按钮开始生成故事框架</p>
      <n-button type="primary" size="large" @click="handleGenerate" class="mt-4">
        开始生成
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { NForm, NFormItem, NInput, NButton, NSpace, NSpin, NIcon, NDivider, NCard, useMessage, NCollapse, NCollapseItem } from 'naive-ui'
import { EditOutlined, ReloadOutlined, ArrowRightOutlined, ArrowLeftOutlined, PlusOutlined, DeleteOutlined } from '@vicons/antd'
import type { Stage2Data } from '@/api/novel'

interface CoreRule {
  rule_content: string
  impact_on_protagonist: string
  conflict_potential: string
}

interface KeyLocation {
  name: string
  visual_description: string
  functional_role: string
  emotional_tone: string
  plot_usage: string
}

interface Faction {
  name: string
  core_interest: string
  power_level: string
  representative: string
  relation_to_protagonist: string
}

interface WorldSetting {
  core_rules: CoreRule[]
  key_locations: KeyLocation[]
  factions: Faction[]
}

const props = defineProps<{
  data: Stage2Data | null
  isGenerating: boolean
}>()

const emit = defineEmits<{
  generate: []
  regenerate: []
  confirm: [data: Stage2Data]
  update: [data: Stage2Data]
  back: []
}>()

const message = useMessage()
const formRef = ref()
const isEditing = ref(false)
const isRegenerating = ref(false)

const formData = ref<Stage2Data>({
  full_synopsis: '',
  world_setting: {
    core_rules: [],
    key_locations: [],
    factions: []
  }
})

const rules = {
  full_synopsis: { required: true, message: '请输入完整故事梗概', trigger: 'blur' }
}

// 初始化世界观设定结构
const initWorldSetting = (data: any): WorldSetting => {
  return {
    core_rules: data?.core_rules || [],
    key_locations: data?.key_locations || [],
    factions: data?.factions || []
  }
}

// 监听数据变化
watch(
  () => props.data,
  (newData) => {
    if (newData) {
      formData.value = {
        full_synopsis: newData.full_synopsis,
        world_setting: initWorldSetting(newData.world_setting)
      }
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

// 添加核心规则
const addCoreRule = () => {
  const ws = formData.value.world_setting as WorldSetting
  if (ws.core_rules.length < 5) {
    ws.core_rules.push({
      rule_content: '',
      impact_on_protagonist: '',
      conflict_potential: ''
    })
  } else {
    message.warning('最多添加5条核心规则')
  }
}

// 删除核心规则
const removeCoreRule = (index: number) => {
  const ws = formData.value.world_setting as WorldSetting
  if (ws.core_rules.length > 1) {
    ws.core_rules.splice(index, 1)
  } else {
    message.warning('至少保留1条核心规则')
  }
}

// 添加关键地点
const addKeyLocation = () => {
  const ws = formData.value.world_setting as WorldSetting
  if (ws.key_locations.length < 6) {
    ws.key_locations.push({
      name: '',
      visual_description: '',
      functional_role: '',
      emotional_tone: '',
      plot_usage: ''
    })
  } else {
    message.warning('最多添加6个关键地点')
  }
}

// 删除关键地点
const removeKeyLocation = (index: number) => {
  const ws = formData.value.world_setting as WorldSetting
  if (ws.key_locations.length > 1) {
    ws.key_locations.splice(index, 1)
  } else {
    message.warning('至少保留1个关键地点')
  }
}

// 添加势力
const addFaction = () => {
  const ws = formData.value.world_setting as WorldSetting
  if (ws.factions.length < 5) {
    ws.factions.push({
      name: '',
      core_interest: '',
      power_level: '',
      representative: '',
      relation_to_protagonist: ''
    })
  } else {
    message.warning('最多添加5个势力')
  }
}

// 删除势力
const removeFaction = (index: number) => {
  const ws = formData.value.world_setting as WorldSetting
  if (ws.factions.length > 1) {
    ws.factions.splice(index, 1)
  } else {
    message.warning('至少保留1个势力')
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
    formData.value = {
      full_synopsis: props.data.full_synopsis,
      world_setting: initWorldSetting(props.data.world_setting)
    }
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

.space-y-4 > * + * {
  margin-top: 16px;
}

.rule-card,
.location-card,
.faction-card {
  transition: all 0.3s ease;
}

.rule-card:hover,
.location-card:hover,
.faction-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}
</style>

