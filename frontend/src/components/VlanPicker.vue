<script setup lang="ts">
/**
 * Pick several VLANs: chips with ID and name, typing suggests matching VLANs by ID or name.
 * Enter/Tab/comma takes the highlighted suggestion; a typed ID or range ("100-105") also works.
 */
import { XMarkIcon } from '@heroicons/vue/20/solid'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ vlans: { vid: number; name: string }[]; exclude?: number | null; inputId?: string }>()
const model = defineModel<number[]>({ required: true })
const { t } = useI18n()

const query = ref('')
const open = ref(false)
const active = ref(0)

const nameOf = (vid: number): string => props.vlans.find((v) => v.vid === vid)?.name ?? ''

const suggestions = computed(() => {
  const q = query.value.trim().toLowerCase()
  return props.vlans
    .filter((v) => !model.value.includes(v.vid) && v.vid !== props.exclude)
    .filter((v) => !q || String(v.vid).startsWith(q) || v.name.toLowerCase().includes(q))
    .slice(0, 8)
})

function add(vids: number[]): void {
  const valid = vids.filter((v) => Number.isInteger(v) && v > 0 && v < 4095 && v !== props.exclude)
  model.value = [...new Set([...model.value, ...valid])].sort((a, b) => a - b)
  query.value = ''
  active.value = 0
}

function remove(vid: number): void {
  model.value = model.value.filter((v) => v !== vid)
}

/** "100-105" or "20" typed directly; otherwise the highlighted suggestion. */
function commit(): boolean {
  const text = query.value.trim()
  const range = /^(\d{1,4})\s*-\s*(\d{1,4})$/.exec(text)
  if (range) {
    const [from, to] = [Number(range[1]), Number(range[2])].sort((a, b) => a - b) as [number, number]
    if (to - from <= 200) add(Array.from({ length: to - from + 1 }, (_, i) => from + i))
    return true
  }
  const pick = suggestions.value[active.value]
  if (pick && text) {
    add([pick.vid])
    return true
  }
  if (/^\d{1,4}$/.test(text)) {
    add([Number(text)])
    return true
  }
  return false
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    active.value = Math.min(active.value + 1, suggestions.value.length - 1)
    event.preventDefault()
  } else if (event.key === 'ArrowUp') {
    active.value = Math.max(active.value - 1, 0)
    event.preventDefault()
  } else if (['Enter', 'Tab', ','].includes(event.key) && query.value.trim()) {
    if (commit()) event.preventDefault()
  } else if (event.key === 'Backspace' && !query.value && model.value.length) {
    model.value = model.value.slice(0, -1)
  } else if (event.key === 'Escape') {
    open.value = false
  }
}
</script>

<template>
  <div class="relative">
    <div
      class="input flex min-h-10 flex-wrap items-center gap-1.5 !py-1.5"
      @click="($refs.input as HTMLInputElement).focus()"
    >
      <span
        v-for="vid in model"
        :key="vid"
        class="inline-flex items-center gap-1 rounded-md bg-brand-50 py-0.5 pr-1 pl-2 text-xs text-brand-700 ring-1 ring-brand-600/20 dark:bg-brand-500/10 dark:text-brand-300"
      >
        <span class="font-mono font-semibold">{{ vid }}</span>
        <span v-if="nameOf(vid)" class="max-w-32 truncate">{{ nameOf(vid) }}</span>
        <span v-else class="text-yellow-600 dark:text-yellow-400" :title="t('vlanPicker.unknownHint')">?</span>
        <button type="button" class="rounded p-0.5 hover:bg-brand-100 dark:hover:bg-white/10" :aria-label="t('common.delete')" @click.stop="remove(vid)">
          <XMarkIcon class="size-3" />
        </button>
      </span>
      <input
        :id="inputId"
        ref="input"
        v-model="query"
        class="min-w-24 flex-1 border-0 bg-transparent p-0 text-sm outline-none focus:ring-0"
        :placeholder="model.length ? '' : t('vlanPicker.placeholder')"
        autocomplete="off"
        @focus="open = true"
        @blur="open = false"
        @input="((open = true), (active = 0))"
        @keydown="onKey"
      />
    </div>
    <ul
      v-if="open && suggestions.length"
      class="mt-1 max-h-56 w-full overflow-auto rounded-md bg-white py-1 text-sm shadow-lg ring-1 ring-black/5 dark:bg-gray-800 dark:ring-white/10"
    >
      <li
        v-for="(v, i) in suggestions"
        :key="v.vid"
        class="flex cursor-pointer gap-3 px-3 py-1.5"
        :class="i === active ? 'bg-brand-600 text-white' : 'hover:bg-gray-50 dark:hover:bg-white/5'"
        @mousedown.prevent="add([v.vid])"
        @mouseenter="active = i"
      >
        <span class="w-12 font-mono font-semibold">{{ v.vid }}</span>
        <span class="truncate">{{ v.name }}</span>
      </li>
    </ul>
  </div>
</template>
