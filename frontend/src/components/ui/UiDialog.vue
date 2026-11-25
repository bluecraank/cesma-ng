<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/20/solid'
import { onBeforeUnmount, ref, watch } from 'vue'
import UiToaster from '@/components/ui/UiToaster.vue'
import { closeDialog, openDialog } from '@/composables/useToasts'

defineProps<{ title?: string; wide?: boolean }>()
const open = defineModel<boolean>('open', { required: true })
const dialog = ref<HTMLDialogElement | null>(null)
/** While open, toasts appear inside this dialog (see useToasts). */
const host = ref<number | null>(null)

// Native <dialog>: focus trap, Escape and backdrop come from the browser.
watch(
  [open, dialog],
  ([isOpen, el]) => {
    if (!el) return
    if (isOpen && !el.open) el.showModal()
    if (!isOpen && el.open) el.close()
  },
  { immediate: true },
)
watch(
  open,
  (isOpen) => {
    if (isOpen && host.value === null) host.value = openDialog()
    if (!isOpen && host.value !== null) {
      closeDialog(host.value)
      host.value = null
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => host.value !== null && closeDialog(host.value))
</script>

<template>
  <dialog
    ref="dialog"
    class="m-auto max-h-[calc(100vh-2rem)] overflow-visible rounded-xl bg-transparent p-0 backdrop:bg-gray-900/50"
    :class="wide ? 'w-[min(42rem,calc(100vw-2rem))]' : 'w-[min(32rem,calc(100vw-2rem))]'"
    @close="open = false"
    @click.self="open = false"
  >
    <div v-if="open" class="flex max-h-[calc(100vh-2rem)] flex-col rounded-xl bg-white shadow-xl ring-1 ring-gray-900/5 dark:bg-gray-900 dark:ring-white/10">
      <header class="flex items-center justify-between gap-4 border-b border-gray-200 px-5 py-4 dark:border-white/10">
        <h2 class="text-base font-semibold text-gray-900 dark:text-white">{{ title }}</h2>
        <button type="button" class="btn-icon" aria-label="Close" @click="open = false">
          <XMarkIcon class="size-5" />
        </button>
      </header>
      <div class="overflow-y-auto px-5 py-4">
        <slot />
      </div>
      <footer v-if="$slots.footer" class="flex justify-end gap-2 border-t border-gray-200 px-5 py-3 dark:border-white/10">
        <slot name="footer" />
      </footer>
    </div>
    <UiToaster v-if="open && host !== null" :host="host" />
  </dialog>
</template>
