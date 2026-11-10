<script setup lang="ts">
import { CheckCircleIcon, InformationCircleIcon, XCircleIcon } from '@heroicons/vue/24/outline'
import { XMarkIcon } from '@heroicons/vue/20/solid'
import { useToasts } from '@/composables/useToasts'

const { toasts, dismiss } = useToasts()
const icons = { success: CheckCircleIcon, error: XCircleIcon, info: InformationCircleIcon }
const colors = { success: 'text-green-500', error: 'text-red-500', info: 'text-brand-500' }
</script>

<template>
  <div aria-live="assertive" class="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-end gap-3 p-4 sm:p-6">
    <TransitionGroup
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="translate-y-2 opacity-0"
      leave-active-class="transition duration-150 ease-in"
      leave-to-class="opacity-0"
    >
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="pointer-events-auto flex w-full max-w-sm gap-3 rounded-lg bg-white p-4 shadow-lg ring-1 ring-gray-900/5 dark:bg-gray-800 dark:ring-white/10"
      >
        <component :is="icons[toast.kind]" class="size-6 shrink-0" :class="colors[toast.kind]" />
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium text-gray-900 dark:text-white">{{ toast.title }}</p>
          <p v-if="toast.detail" class="mt-1 text-sm break-words text-gray-500 dark:text-gray-400">{{ toast.detail }}</p>
        </div>
        <button type="button" class="btn-icon -m-1 self-start" aria-label="Close" @click="dismiss(toast.id)">
          <XMarkIcon class="size-5" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
