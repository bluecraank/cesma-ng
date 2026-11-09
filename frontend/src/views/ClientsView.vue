<script setup lang="ts">
import { ChevronLeftIcon, ChevronRightIcon, MagnifyingGlassIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api, type ClientPage, type ClientRow } from '@/api/client'
import MacTypeIcon from '@/components/MacTypeIcon.vue'
import { useNotify } from '@/composables/useNotify'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

const PAGE_SIZE = 100
const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()
const route = useRoute()
const router = useRouter()

const rows = ref<ClientRow[]>([])
const total = ref(0)
const offset = ref(0)
// The search lives in the URL, so a search can be shared as a link.
const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const activeOnly = ref(false)

const pageInfo = computed(() =>
  total.value ? `${offset.value + 1}–${Math.min(offset.value + PAGE_SIZE, total.value)} / ${total.value}` : '0',
)

async function load(): Promise<void> {
  await notify.run(async () => {
    const page = await api.get<ClientPage>('/clients', {
      q: query.value,
      site_id: sites.currentId,
      active_only: activeOnly.value,
      limit: PAGE_SIZE,
      offset: offset.value,
    })
    rows.value = page.items
    total.value = page.total
  })
}

function go(delta: number): void {
  offset.value = Math.max(0, offset.value + delta * PAGE_SIZE)
  void load()
}

let timer: ReturnType<typeof setTimeout> | undefined
watch(query, (q) => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    offset.value = 0
    void router.replace({ query: q ? { q } : {} })
    void load()
  }, 300)
})
watch(
  () => route.query.q,
  (q) => {
    if (typeof q === 'string' && q !== query.value) query.value = q
  },
)
watch(
  [() => sites.currentId, activeOnly],
  () => {
    offset.value = 0
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('clients.title') }}</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t('clients.hint') }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-4">
        <label class="flex items-center gap-2 text-sm"><input v-model="activeOnly" type="checkbox" class="accent-indigo-600" /> {{ t('clients.activeOnly') }}</label>
        <div class="relative">
          <MagnifyingGlassIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
          <input v-model="query" class="input w-80 pl-8" :placeholder="t('common.search')" autofocus />
        </div>
      </div>
    </div>

    <div class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>{{ t('clients.hostname') }}</th>
              <th>{{ t('clients.ip') }}</th>
              <th>{{ t('clients.mac') }}</th>
              <th>{{ t('clients.vendor') }}</th>
              <th>{{ t('clients.vlan') }}</th>
              <th>{{ t('clients.location') }}</th>
              <th>{{ t('clients.lastSeen') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in rows" :key="c.id">
              <td class="whitespace-nowrap">
                <span class="inline-flex items-center gap-2">
                  <MacTypeIcon :icon="c.type_icon" :title="c.type_name ?? ''" />
                  <span class="font-medium text-gray-900 dark:text-white">{{ c.hostname || '—' }}</span>
                </span>
              </td>
              <td class="font-mono text-xs">{{ c.ip_address ?? '' }}</td>
              <td class="font-mono text-xs whitespace-nowrap">{{ c.mac_address }}</td>
              <td class="max-w-48 truncate text-xs" :title="c.vendor ?? ''">{{ c.vendor ?? '' }}</td>
              <td class="tabular-nums">{{ c.vid ?? '' }}</td>
              <td class="whitespace-nowrap">
                <RouterLink
                  v-if="c.device_id"
                  :to="{ name: 'device', params: { id: c.device_id }, query: { tab: 'ports', ...(c.port_id ? { port: c.port_id } : {}) } }"
                  class="link"
                  :title="t('clients.toPort')"
                >
                  {{ c.device_name }} <span class="font-mono text-xs">{{ c.port_name }}</span>
                </RouterLink>
                <span v-else class="ml-1 font-mono text-xs">{{ c.port_name }}</span>
              </td>
              <td class="whitespace-nowrap">
                <span v-if="c.active" class="badge badge-green">{{ t('clients.active') }}</span>
                <span v-else class="text-xs text-gray-500 tabular-nums" :title="`${t('clients.firstSeen')}: ${formatDateTime(c.first_seen_at, locale)}`">
                  {{ formatDateTime(c.last_seen_at, locale) }}
                </span>
              </td>
            </tr>
            <tr v-if="!rows.length"><td colspan="7" class="py-8 text-center text-gray-500">{{ t('search.empty') }}</td></tr>
          </tbody>
        </table>
      </div>
      <div class="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm dark:border-white/10">
        <span class="text-gray-500 dark:text-gray-400">{{ pageInfo }}</span>
        <div class="flex gap-2">
          <button type="button" class="btn btn-secondary btn-sm" :disabled="offset === 0" @click="go(-1)"><ChevronLeftIcon class="size-4" /></button>
          <button type="button" class="btn btn-secondary btn-sm" :disabled="offset + PAGE_SIZE >= total" @click="go(1)"><ChevronRightIcon class="size-4" /></button>
        </div>
      </div>
    </div>
  </div>
</template>
