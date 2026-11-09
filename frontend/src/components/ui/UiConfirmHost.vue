<script setup lang="ts">
import { ExclamationTriangleIcon } from '@heroicons/vue/24/outline'
import { computed } from 'vue'
import { useConfirm } from '@/composables/useConfirm'
import UiDialog from './UiDialog.vue'

const { pending, answer } = useConfirm()
const open = computed({
  get: () => pending.value !== null,
  set: (value) => !value && answer(false),
})
</script>

<template>
  <UiDialog v-model:open="open" :title="pending?.title">
    <div class="flex gap-4">
      <div
        v-if="pending?.danger"
        class="flex size-10 shrink-0 items-center justify-center rounded-full bg-red-100 dark:bg-red-500/10"
      >
        <ExclamationTriangleIcon class="size-6 text-red-600 dark:text-red-400" />
      </div>
      <p class="text-sm text-gray-600 dark:text-gray-300">{{ pending?.message }}</p>
    </div>
    <template #footer>
      <button type="button" class="btn btn-secondary" @click="answer(false)">{{ pending?.cancelLabel }}</button>
      <button
        type="button"
        class="btn"
        :class="pending?.danger ? 'btn-danger' : 'btn-primary'"
        @click="answer(true)"
      >
        {{ pending?.confirmLabel }}
      </button>
    </template>
  </UiDialog>
</template>
