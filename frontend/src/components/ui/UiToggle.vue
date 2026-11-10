<script setup lang="ts">
defineProps<{ label: string }>()
const value = defineModel<boolean>({ required: true })
</script>

<template>
  <label class="flex cursor-pointer items-center gap-3">
    <button
      type="button"
      role="switch"
      :aria-checked="value"
      class="relative inline-flex h-6 w-11 shrink-0 rounded-full p-0.5 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
      :class="value ? 'bg-brand-600' : 'bg-gray-200 dark:bg-white/10'"
      @click="value = !value"
    >
      <span class="size-5 rounded-full bg-white shadow-xs ring-1 ring-gray-900/5 transition-transform" :class="value ? 'translate-x-5' : 'translate-x-0'" />
    </button>
    <span class="text-sm font-medium">{{ label }}</span>
  </label>
</template>
