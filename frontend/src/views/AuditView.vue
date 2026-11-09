<script setup lang="ts">
import { ChevronLeftIcon, ChevronRightIcon, MagnifyingGlassIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type AuditEntry, type AuditPage } from '@/api/client'
import { useNotify } from '@/composables/useNotify'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

const PAGE_SIZE = 50
const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()

const entries = ref<AuditEntry[]>([])
const total = ref(0)
const offset = ref(0)
const search = ref('')

const pageInfo = computed(() =>
  total.value ? `${offset.value + 1}–${Math.min(offset.value + PAGE_SIZE, total.value)} / ${total.value}` : '0',
)

async function load(): Promise<void> {
  await notify.run(async () => {
    const page = await api.get<AuditPage>('/audit', {
      site_id: sites.currentId,
      search: search.value,
      limit: PAGE_SIZE,
      offset: offset.value,
    })
    entries.value = page.items
    total.value = page.total
  })
}

function go(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * PAGE_SIZE)
  void load()
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    offset.value = 0
    void load()
  }, 300)
})
watch(
  () => sites.currentId,
  () => {
    offset.value = 0
    void load()
  },
  { immediate: true },
)

const levelBadge = { info: 'badge-blue', warning: 'badge-yellow', error: 'badge-red' } as const

function changes(entry: AuditEntry): { key: string; old: string; new: string }[] {
  const keys = Object.keys(entry.new_values ?? entry.old_values ?? {})
  const show = (v: unknown) => (v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v))
  return keys.map((key) => ({ key, old: show(entry.old_values?.[key]), new: show(entry.new_values?.[key]) }))
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="page-title">{{ t('audit.title') }}</h1>
      <div class="relative">
        <MagnifyingGlassIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
        <input v-model="search" class="input w-64 pl-8" :placeholder="t('common.search')" />
      </div>
    </div>

    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>{{ t('audit.time') }}</th>
              <th>{{ t('audit.level') }}</th>
              <th>{{ t('audit.action') }}</th>
              <th>{{ t('audit.actor') }}</th>
              <th>{{ t('audit.message') }}</th>
              <th>{{ t('audit.changes') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in entries" :key="e.id">
              <td class="whitespace-nowrap tabular-nums">{{ formatDateTime(e.created_at, locale) }}</td>
              <td><span class="badge" :class="levelBadge[e.level]">{{ e.level }}</span></td>
              <td class="font-mono text-xs whitespace-nowrap">{{ e.action }}</td>
              <td class="whitespace-nowrap">{{ e.actor_name }}</td>
              <td class="min-w-48">{{ e.message }}</td>
              <td class="text-xs">
                <div v-for="c in changes(e)" :key="c.key" class="whitespace-nowrap">
                  <span class="text-gray-500 dark:text-gray-400">{{ c.key }}:</span>
                  <span class="text-red-600 line-through decoration-red-300 dark:text-red-400"> {{ c.old }}</span>
                  <span class="text-gray-400"> → </span>
                  <span class="text-green-700 dark:text-green-400">{{ c.new }}</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm dark:border-white/10">
        <span class="text-gray-500 dark:text-gray-400">{{ pageInfo }}</span>
        <div class="flex gap-2">
          <button type="button" class="btn btn-secondary btn-sm" :disabled="offset === 0" @click="go(-1)">
            <ChevronLeftIcon class="size-4" />
          </button>
          <button type="button" class="btn btn-secondary btn-sm" :disabled="offset + PAGE_SIZE >= total" @click="go(1)">
            <ChevronRightIcon class="size-4" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
