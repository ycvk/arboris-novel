<template>
  <TransitionRoot as="template" :show="show">
    <Dialog as="div" class="relative z-50" @close="$emit('close')">
      <TransitionChild as="template" enter="ease-out duration-300" enter-from="opacity-0" enter-to="opacity-100" leave="ease-in duration-200" leave-from="opacity-100" leave-to="opacity-0">
        <div class="fixed inset-0 bg-slate-900/40 backdrop-blur-sm" />
      </TransitionChild>

      <div class="fixed inset-0 z-10 overflow-y-auto">
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <TransitionChild as="template" enter="ease-out duration-300" enter-from="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95" enter-to="opacity-100 translate-y-0 sm:scale-100" leave="ease-in duration-200" leave-from="opacity-100 translate-y-0 sm:scale-100" leave-to="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95">
            <DialogPanel class="relative transform overflow-hidden rounded-2xl bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg">
              <div class="px-6 pt-6 pb-4">
                <div class="flex items-start gap-4">
                  <div class="mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 sm:mx-0 sm:h-12 sm:w-12">
                    <svg class="h-6 w-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 6v12m6-6H6" />
                    </svg>
                  </div>
                  <div class="flex-1">
                    <DialogTitle as="h3" class="text-xl font-semibold leading-7 text-slate-900">拆分第 {{ chapterNumber }} 章</DialogTitle>
                    <p class="mt-1 text-sm text-slate-600">请输入拆分数量及可选参数。</p>
                  </div>
                </div>

                <div class="mt-6 space-y-5">
                  <div>
                    <label class="block text-sm font-medium text-slate-700">拆分为几章（≥2）</label>
                    <input type="number" v-model.number="count" min="2" class="mt-2 block w-full rounded-xl border border-slate-300 bg-gray-50 px-4 py-2.5 text-sm focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                    <div class="mt-3 flex flex-wrap gap-2">
                      <button v-for="c in [2,3,4,5]" :key="c" type="button" @click="count=c" :class="['px-3 py-1.5 rounded-full text-sm', count===c ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-700 hover:bg-slate-300']">{{ c }} 章</button>
                    </div>
                  </div>

                  <div>
                    <label class="block text-sm font-medium text-slate-700">节奏偏好（可选）</label>
                    <input type="text" v-model="pacing" placeholder="如：慢 / 中 / 快" class="mt-2 block w-full rounded-xl border border-slate-300 bg-gray-50 px-4 py-2.5 text-sm focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>

                  <div>
                    <label class="block text-sm font-medium text-slate-700">约束（可选，JSON）</label>
                    <textarea v-model="constraintsText" rows="3" placeholder='例如：{"avoid": ["副线展开"], "tone": "紧凑"}' class="mt-2 block w-full rounded-xl border border-slate-300 bg-gray-50 px-4 py-2.5 text-sm focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"></textarea>
                    <p v-if="constraintsError" class="mt-1 text-xs text-red-500">{{ constraintsError }}</p>
                  </div>
                </div>
              </div>

              <div class="bg-gray-50 px-6 py-4 sm:flex sm:flex-row-reverse">
                <button type="button" class="inline-flex w-full justify-center rounded-lg border border-transparent bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 sm:ml-3 sm:w-auto" @click="onSubmit">开始拆分</button>
                <button type="button" class="mt-3 inline-flex w-full justify-center rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 sm:mt-0 sm:ml-3 sm:w-auto" @click="$emit('close')">取消</button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
  
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'

interface Props {
  show: boolean
  chapterNumber: number
  defaultCount?: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'submit', payload: { count: number; pacing?: string; constraints?: Record<string, any> }): void }>()

const count = ref<number>(props.defaultCount ?? 3)
const pacing = ref<string>('')
const constraintsText = ref<string>('')
const constraintsError = ref<string>('')

watch(() => props.defaultCount, (val) => {
  if (typeof val === 'number') count.value = Math.max(2, val)
})

const onSubmit = () => {
  constraintsError.value = ''
  if (!count.value || count.value < 2) {
    constraintsError.value = '拆分数量需 ≥ 2'
    return
  }
  let constraints: Record<string, any> | undefined
  if (constraintsText.value.trim()) {
    try {
      constraints = JSON.parse(constraintsText.value)
    } catch (e) {
      constraintsError.value = '约束需为合法 JSON'
      return
    }
  }
  emit('submit', { count: count.value, pacing: pacing.value || undefined, constraints })
  emit('close')
}
</script>

<script lang="ts">
import { defineComponent } from 'vue'
export default defineComponent({ name: 'SplitChapterModal' })
</script>

