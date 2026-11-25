<script setup lang="ts">
/** Dropdown to show and hide the optional columns of a table; used together with useColumns. */
import { ViewColumnsIcon } from '@heroicons/vue/20/solid'
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ColumnState } from '@/composables/useColumns'

defineProps<{ columns: { key: string; label: string }[]; state: ColumnState }>()

const { t } = useI18n()
const open = ref(false)
const root = ref<HTMLElement | null>(null)

function onDocument(event: Event): void {
  if (event instanceof KeyboardEvent ? event.key === 'Escape' : !root.value?.contains(event.target as Node)) open.value = false
}

watch(open, (isOpen) => {
  const method = isOpen ? 'addEventListener' : 'removeEventListener'
  document[method]('mousedown', onDocument)
  document[method]('keydown', onDocument)
})
onBeforeUnmount(() => (open.value = false))
</script>

<template>
  <div ref="root" class="relative">
    <button type="button" class="btn btn-secondary" :aria-expanded="open" aria-haspopup="true" @click="open = !open">
      <ViewColumnsIcon class="size-4" /> {{ t('common.columns') }}
    </button>
    <div
      v-if="open"
      class="absolute right-0 z-40 mt-1 min-w-52 rounded-md bg-white py-1 shadow-lg ring-1 ring-gray-200 dark:bg-gray-800 dark:ring-white/10"
    >
      <label
        v-for="col in columns"
        :key="col.key"
        class="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm whitespace-nowrap hover:bg-gray-50 dark:hover:bg-white/5"
      >
        <input type="checkbox" class="accent-brand-600" :checked="state.shows(col.key)" @change="state.toggle(col.key)" />
        {{ col.label }}
      </label>
    </div>
  </div>
</template>
