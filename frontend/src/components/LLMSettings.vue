<template>
  <div class="bg-white/70 backdrop-blur-xl rounded-2xl shadow-lg p-8">
    <h2 class="text-2xl font-bold text-gray-800 mb-6">LLM 配置</h2>
    <h5 class="text-1xl font-bold text-gray-800 mb-6">建议使用自己的中转API和KEY</h5>
    <form @submit.prevent="handleSave" class="space-y-6">
      <div>
        <label for="url" class="block text-sm font-medium text-gray-700">API URL</label>
        <input type="text" id="url" v-model="config.llm_provider_url" class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="https://api.example.com/v1">
      </div>
      <div>
        <label for="key" class="block text-sm font-medium text-gray-700">API Key</label>
        <input type="password" id="key" v-model="config.llm_provider_api_key" class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="留空则使用默认Key">
      </div>
      <div>
        <label for="model" class="block text-sm font-medium text-gray-700">Model</label>
        <input type="text" id="model" v-model="config.llm_provider_model" class="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="留空则使用默认模型">
      </div>
      <div class="flex justify-end space-x-4 pt-4">
        <button type="button" @click="handleDelete" class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors">删除配置</button>
        <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">保存</button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { getLLMConfig, createOrUpdateLLMConfig, deleteLLMConfig, type LLMConfigCreate } from '@/api/llm';

const config = ref<LLMConfigCreate>({
  llm_provider_url: '',
  llm_provider_api_key: '',
  llm_provider_model: '',
});

onMounted(async () => {
  const existingConfig = await getLLMConfig();
  if (existingConfig) {
    config.value = {
      llm_provider_url: existingConfig.llm_provider_url || '',
      llm_provider_api_key: existingConfig.llm_provider_api_key || '',
      llm_provider_model: existingConfig.llm_provider_model || '',
    };
  }
});

const handleSave = async () => {
  await createOrUpdateLLMConfig(config.value);
  alert('设置已保存！');
};

const handleDelete = async () => {
  if (confirm('确定要删除您的自定义LLM配置吗？删除后将恢复为默认配置。')) {
    await deleteLLMConfig();
    config.value = {
      llm_provider_url: '',
      llm_provider_api_key: '',
      llm_provider_model: '',
    };
    alert('配置已删除！');
  }
};
</script>
