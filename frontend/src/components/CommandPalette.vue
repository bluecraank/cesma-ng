<script setup lang="ts">
import {
  BoltIcon,
  MagnifyingGlassIcon,
  QueueListIcon,
  ServerStackIcon,
  UserIcon,
} from '@heroicons/vue/24/outline'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api, type SearchHit } from '@/api/client'
import { useSitesStore } from '@/stores/sites'

const open = defineModel<boolean>('open', { required: true })
const { t } = useI18n()
const router = useRouter()
const sites = useSitesStore()

const query = ref('')
const hits = ref<SearchHit[]>([])
const selected = ref(0)
const input = ref<HTMLInputElement | null>(null)
const icons = { device: ServerStackIcon, port: BoltIcon, client: UserIcon, vlan: QueueListIcon }

let timer: ReturnType<typeof setTimeout> | undefined
let requestNo = 0
watch(query, (q) => {
  clearTimeout(timer)
  timer = setTimeout(async () => {
    const mine = ++requestNo
    const result = q.trim().length < 2 ? { hits: [] } : await api.get<{ hits: SearchHit[] }>('/search', { q }).catch(() => ({ hits: [] }))
    if (mine === requestNo) {
      hits.value = result.hits
      selected.value = 0
    }
  }, 150)
})

watch(open, async (isOpen) => {
  if (!isOpen) return
  query.value = ''
  hits.value = []
  await nextTick()
  input.value?.focus()
})

const grouped = computed(() => hits.value.map((hit, index) => ({ hit, index })))

async function choose(hit: SearchHit): Promise<void> {
  open.value = false
  // Switch to the site of the result so the target page shows it.
  if (hit.site_id && hit.site_id !== sites.currentId) sites.currentId = hit.site_id
  if (hit.kind === 'client') await router.push({ name: 'clients', query: { q: hit.query ?? hit.title } })
  else if (hit.kind === 'vlan') await router.push({ name: 'device', params: { id: hit.device_id }, query: { tab: 'vlans' } })
  else if (hit.device_id) await router.push({ name: 'device', params: { id: hit.device_id }, query: { tab: 'ports' } })
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    selected.value = Math.min(selected.value + 1, hits.value.length - 1)
    event.preventDefault()
  } else if (event.key === 'ArrowUp') {
    selected.value = Math.max(selected.value - 1, 0)
    event.preventDefault()
  } else if (event.key === 'Enter' && hits.value[selected.value]) {
    void choose(hits.value[selected.value]!)
  } else if (event.key === 'Escape') {
    open.value = false
  }
}

/** Global shortcut: Ctrl+K / Cmd+K, and "/" outside of input fields. */
function onGlobalKey(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  const typing = target?.closest('input, textarea, select, [contenteditable]')
  if ((event.key === 'k' && (event.ctrlKey || event.metaKey)) || (event.key === '/' && !typing)) {
    event.preventDefault()
    open.value = true
  }
}
onMounted(() => window.addEventListener('keydown', onGlobalKey))
onUnmounted(() => window.removeEventListener('keydown', onGlobalKey))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[60] flex items-start justify-center bg-gray-900/50 p-4 pt-[12vh]" @click.self="open = false">
      <div class="w-full max-w-xl overflow-hidden rounded-xl bg-white shadow-2xl ring-1 ring-gray-900/10 dark:bg-gray-900 dark:ring-white/10">
        <div class="relative border-b border-gray-200 dark:border-white/10">
          <MagnifyingGlassIcon class="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-gray-400" />
          <input
            ref="input"
            v-model="query"
            class="h-12 w-full bg-transparent pr-4 pl-11 text-sm text-gray-900 outline-none placeholder:text-gray-400 dark:text-white"
            :placeholder="t('search.placeholder')"
            @keydown="onKey"
          />
        </div>
        <ul v-if="hits.length" class="max-h-96 overflow-y-auto p-2">
          <li
            v-for="{ hit, index } in grouped"
            :key="index"
            class="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2"
            :class="index === selected ? 'bg-indigo-600 text-white' : 'text-gray-900 dark:text-gray-100'"
            @mouseenter="selected = index"
            @click="choose(hit)"
          >
            <component :is="icons[hit.kind as keyof typeof icons]" class="size-5 shrink-0" :class="index === selected ? 'text-white' : 'text-gray-400'" />
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium">{{ hit.title }}</p>
              <p class="truncate text-xs" :class="index === selected ? 'text-indigo-100' : 'text-gray-500'">{{ hit.subtitle }}</p>
            </div>
            <span class="text-xs" :class="index === selected ? 'text-indigo-100' : 'text-gray-400'">{{ t(`search.kinds.${hit.kind}`) }}</span>
          </li>
        </ul>
        <p v-else-if="query.trim().length >= 2" class="p-6 text-center text-sm text-gray-500">{{ t('search.empty') }}</p>
      </div>
    </div>
  </Teleport>
</template>
