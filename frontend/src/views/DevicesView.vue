<script setup lang="ts">
import { CheckIcon, ChevronUpDownIcon, ExclamationTriangleIcon, MagnifyingGlassIcon, PlusIcon, SignalIcon, XMarkIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api, type Device, type DeviceHint } from '@/api/client'
import DeviceFormDialog from '@/components/DeviceFormDialog.vue'
import DiscoverDialog from '@/components/DiscoverDialog.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useJobWatcher } from '@/composables/useJobWatcher'
import DeviceStatusTag from '@/components/DeviceStatusTag.vue'
import SwitchIcon from '@/components/SwitchIcon.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()
const notify = useNotify()
const auth = useAuthStore()
const sites = useSitesStore()

const devices = ref<Device[]>([])
const hints = ref<DeviceHint[]>([])
const hintsOf = (id: number): DeviceHint[] => hints.value.filter((h) => h.device_id === id)
const devicesWithHints = computed(() => new Set(hints.value.map((h) => h.device_id)).size)
const loading = ref(false)
const search = ref('')
// status filter, also set from the dashboard (?status=offline)
const route = useRoute()
const router = useRouter()
const STATUS_FILTERS = ['online', 'offline', 'unknown', 'unconfirmed'] as const
const statusFilter = ref(typeof route.query.status === 'string' ? route.query.status : '')
watch(statusFilter, (status) => void router.replace({ query: { ...route.query, status: status || undefined } }))
const dialogOpen = ref(false)
const discoverOpen = ref(false)
const confirmDelete = useConfirmDelete()
const { watch: watchJob } = useJobWatcher(() => load())

/** Switches found automatically wait here until an admin takes them over. */
const unconfirmed = computed(() => devices.value.filter((d) => d.status === 'unconfirmed'))

async function accept(device: Device): Promise<void> {
  if (await notify.run(() => api.patch(`/devices/${device.id}`, { name: device.name }), t('discover.accepted'))) await load()
}

async function reject(device: Device): Promise<void> {
  if (await confirmDelete(device.name)) {
    if (await notify.run(() => api.delete(`/devices/${device.id}`), t('common.deleted'))) await load()
  }
}

type SortKey = 'name' | 'ip_address' | 'dns_name' | 'model' | 'firmware' | 'status' | 'last_seen_at'
const sortKey = ref<SortKey>('name')
const sortAsc = ref(true)

const canCreate = computed(() => auth.can('devices.manage', sites.currentId))

const columns = computed<{ key: SortKey; label: string }[]>(() => [
  { key: 'name', label: t('common.name') },
  { key: 'ip_address', label: t('device.ip') },
  { key: 'dns_name', label: t('device.dns') },
  { key: 'model', label: t('device.model') },
  { key: 'firmware', label: t('device.firmware') },
  { key: 'status', label: t('device.status') },
  { key: 'last_seen_at', label: t('device.lastSeen') },
])

async function load(): Promise<void> {
  if (sites.currentId === null) return
  loading.value = true
  await notify.run(async () => {
    ;[devices.value, hints.value] = await Promise.all([
      api.get<Device[]>('/devices', { site_id: sites.currentId }),
      api.get<DeviceHint[]>(`/sites/${sites.currentId}/device-hints`).catch(() => []),
    ])
  })
  loading.value = false
}

/** 10.0.0.9 before 10.0.0.10 */
function ipSortKey(ip: string | null): string {
  return ip ? ip.split('.').map((part) => part.padStart(3, '0')).join('.') : '~'
}

function sortBy(key: SortKey): void {
  sortAsc.value = sortKey.value === key ? !sortAsc.value : true
  sortKey.value = key
}

const rows = computed(() => {
  const q = search.value.trim().toLowerCase()
  const filtered = devices.value.filter(
    (d) =>
      (!statusFilter.value || d.status === statusFilter.value) &&
      (!q || [d.name, d.hostname, d.ip_address, d.dns_name, d.model_name, d.serial_number, d.firmware].some((v) => v?.toLowerCase().includes(q))),
  )
  const dir = sortAsc.value ? 1 : -1
  const value = (d: Device): string =>
    sortKey.value === 'ip_address' ? ipSortKey(d.ip_address) : String(d[sortKey.value] ?? '')
  return [...filtered].sort((a, b) => value(a).localeCompare(value(b), undefined, { numeric: true }) * dir)
})

watch(() => sites.currentId, load, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('device.title') }}</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ rows.length }} / {{ devices.length }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <div class="relative">
          <MagnifyingGlassIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
          <input v-model="search" class="input w-64 pl-8" :placeholder="t('common.search')" />
        </div>
        <select v-model="statusFilter" class="input w-40" :aria-label="t('device.status')">
          <option value="">{{ t('device.allStatuses') }}</option>
          <option v-for="s in STATUS_FILTERS" :key="s" :value="s">{{ t(`device.statuses.${s}`) }}</option>
        </select>
        <button v-if="canCreate" type="button" class="btn btn-secondary" @click="discoverOpen = true">
          <SignalIcon class="size-4" /> {{ t('discover.title') }}
        </button>
        <button v-if="canCreate" type="button" class="btn btn-primary" @click="dialogOpen = true">
          <PlusIcon class="size-5" /> {{ t('device.new') }}
        </button>
      </div>
    </div>

    <p v-if="devicesWithHints" class="flex items-center gap-2 text-sm text-yellow-700 dark:text-yellow-400">
      <ExclamationTriangleIcon class="size-4" /> {{ t('hints.summary', devicesWithHints) }}
    </p>

    <div v-if="unconfirmed.length" class="rounded-xl bg-yellow-50 p-4 ring-1 ring-yellow-600/20 dark:bg-yellow-500/10 dark:ring-yellow-500/20">
      <p class="text-sm font-semibold text-yellow-800 dark:text-yellow-300">{{ t('discover.waiting', unconfirmed.length) }}</p>
      <ul class="mt-2 space-y-1.5">
        <li v-for="d in unconfirmed" :key="d.id" class="flex flex-wrap items-center gap-3 text-sm">
          <span class="font-medium">{{ d.name }}</span>
          <span class="font-mono text-xs">{{ d.hostname }}</span>
          <span class="text-xs text-gray-600 dark:text-gray-400">{{ t(`device.models.${d.model}`) }}</span>
          <span v-if="canCreate" class="ml-auto flex gap-2">
            <button type="button" class="btn btn-secondary btn-sm" @click="accept(d)"><CheckIcon class="size-4" /> {{ t('discover.accept') }}</button>
            <button type="button" class="btn btn-ghost btn-sm" @click="reject(d)"><XMarkIcon class="size-4" /> {{ t('discover.reject') }}</button>
          </span>
        </li>
      </ul>
    </div>

    <div class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th class="w-12"><span class="sr-only">{{ t('device.model') }}</span></th>
            <th v-for="col in columns" :key="col.key">
              <button type="button" class="inline-flex items-center gap-1 hover:text-gray-900 dark:hover:text-white" @click="sortBy(col.key)">
                {{ col.label }}
                <ChevronUpDownIcon class="size-4" :class="sortKey === col.key ? 'text-brand-500' : 'opacity-40'" />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in rows" :key="d.id">
            <td class="py-2">
              <RouterLink :to="{ name: 'device', params: { id: d.id } }">
                <SwitchIcon :model="d.model" :status="d.status" :title="`${t(`device.models.${d.model}`)} · ${t(`device.statuses.${d.status}`)}`" />
              </RouterLink>
            </td>
            <td>
              <RouterLink :to="{ name: 'device', params: { id: d.id } }" class="link">{{ d.name }}</RouterLink>
              <RouterLink
                v-if="hintsOf(d.id).length"
                :to="{ name: 'device', params: { id: d.id }, query: { tab: 'details' } }"
                class="ml-1.5 inline-flex align-middle"
                :class="hintsOf(d.id).some((h) => h.level === 'error') ? 'text-red-500' : 'text-yellow-500'"
                :title="hintsOf(d.id).map((h) => t(`hints.${h.code}.title`, { profile: h.detail })).join(' · ')"
              >
                <ExclamationTriangleIcon class="size-4" />
              </RouterLink>
            </td>
            <td class="whitespace-nowrap"><span v-if="d.ip_address">{{ d.ip_address }}</span><span v-else class="muted">—</span></td>
            <td class="max-w-56 truncate" :title="d.dns_name ?? ''"><span v-if="d.dns_name">{{ d.dns_name }}</span><span v-else class="muted">—</span></td>
            <td>{{ d.model_name || t(`device.models.${d.model}`) }}</td>
            <td>{{ d.firmware || '—' }}</td>
            <td><DeviceStatusTag :status="d.status" /></td>
            <td class="whitespace-nowrap tabular-nums">{{ formatDateTime(d.last_seen_at, locale) }}</td>
          </tr>
          <tr v-if="loading">
            <td :colspan="columns.length + 1" class="py-8"><UiSpinner class="mx-auto" /></td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="columns.length + 1" class="py-8 text-center text-gray-500">—</td>
          </tr>
        </tbody>
      </table>
    </div>

    <DeviceFormDialog v-model:open="dialogOpen" @saved="load" />
    <DiscoverDialog v-model:open="discoverOpen" @started="watchJob" />
  </div>
</template>
