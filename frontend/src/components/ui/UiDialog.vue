<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/20/solid'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import UiToaster from '@/components/ui/UiToaster.vue'
import { useConfirm } from '@/composables/useConfirm'
import { closeDialog, openDialog } from '@/composables/useToasts'
import { setUnsaved } from '@/composables/useUnsaved'

const props = withDefaults(
  defineProps<{
    title?: string
    wide?: boolean
    /**
     * Unsaved input: closing by Escape, backdrop or X asks first. Without it the dialog counts as
     * changed as soon as something was typed or picked in it (fields with data-no-dirty, such as
     * search fields, do not count).
     */
    dirty?: boolean
  }>(),
  { title: undefined, dirty: undefined },
)
const open = defineModel<boolean>('open', { required: true })
const dialog = ref<HTMLDialogElement | null>(null)
const { t } = useI18n()
const { confirm } = useConfirm()

const touched = ref(false)
watch(open, (isOpen) => isOpen && (touched.value = false))
function onInput(event: Event): void {
  if (!(event.target as HTMLElement | null)?.closest('[data-no-dirty]')) touched.value = true
}
const isDirty = computed(() => open.value && (props.dirty ?? touched.value))
const unsavedId = Symbol('dialog')
watch(isDirty, (dirty) => setUnsaved(unsavedId, dirty), { immediate: true })
onBeforeUnmount(() => setUnsaved(unsavedId, false))

/** Escape, backdrop and X: ask before throwing away unsaved input. */
async function requestClose(): Promise<void> {
  if (isDirty.value) {
    const discard = await confirm({
      title: t('common.discardTitle'),
      message: t('common.discardMessage'),
      confirmLabel: t('common.discard'),
      cancelLabel: t('common.keepEditing'),
    })
    if (!discard) return
  }
  open.value = false
}

function onCancel(event: Event): void {
  event.preventDefault()
  void requestClose()
}

// Only a click that also started on the backdrop closes: selecting text in a field and letting
// go outside the dialog must not.
let downOnBackdrop = false
function onPointerDown(event: PointerEvent): void {
  downOnBackdrop = event.target === dialog.value
}
function onClick(event: MouseEvent): void {
  if (event.target === dialog.value && downOnBackdrop) void requestClose()
  downOnBackdrop = false
}
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
    @cancel="onCancel"
    @pointerdown="onPointerDown"
    @click="onClick"
    @input="onInput"
    @change="onInput"
  >
    <div v-if="open" class="flex max-h-[calc(100vh-2rem)] flex-col rounded-xl bg-white shadow-xl ring-1 ring-gray-900/5 dark:bg-gray-900 dark:ring-white/10">
      <header class="flex items-center justify-between gap-4 border-b border-gray-200 px-5 py-4 dark:border-white/10">
        <h2 class="text-base font-semibold text-gray-900 dark:text-white">{{ title }}</h2>
        <button type="button" class="btn-icon" aria-label="Close" @click="requestClose">
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
