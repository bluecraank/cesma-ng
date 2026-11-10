<script setup lang="ts">
/** Small dropdown menu ("More" actions). Items are buttons in the default slot with class "menu-item". */
import { EllipsisHorizontalIcon } from '@heroicons/vue/20/solid'
import { onBeforeUnmount, ref, watch } from 'vue'

defineProps<{ label: string }>()

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
    <button type="button" class="btn btn-secondary" :aria-expanded="open" aria-haspopup="menu" @click="open = !open">
      <EllipsisHorizontalIcon class="size-4" /> {{ label }}
    </button>
    <div
      v-if="open"
      role="menu"
      class="absolute right-0 z-40 mt-1 min-w-52 rounded-md bg-white py-1 shadow-lg ring-1 ring-gray-200 dark:bg-gray-800 dark:ring-white/10"
      @click="open = false"
    >
      <slot />
    </div>
  </div>
</template>
