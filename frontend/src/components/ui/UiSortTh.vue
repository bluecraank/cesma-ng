<script setup lang="ts">
/** Table header cell that sorts its column; used together with useTableSort. */
import { ChevronDownIcon, ChevronUpDownIcon, ChevronUpIcon } from '@heroicons/vue/20/solid'
import { computed } from 'vue'
import type { SortState } from '@/composables/useTableSort'

const props = defineProps<{ sort: SortState; column: string }>()
const active = computed(() => props.sort.key === props.column)
</script>

<template>
  <th :aria-sort="active ? (sort.asc ? 'ascending' : 'descending') : 'none'">
    <button type="button" class="inline-flex items-center gap-1 hover:text-gray-900 dark:hover:text-white" @click="sort.toggle(column)">
      <slot />
      <ChevronUpDownIcon v-if="!active" class="size-4 opacity-40" />
      <ChevronUpIcon v-else-if="sort.asc" class="size-4 text-brand-500" />
      <ChevronDownIcon v-else class="size-4 text-brand-500" />
    </button>
  </th>
</template>
