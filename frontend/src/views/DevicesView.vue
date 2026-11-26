<script setup lang="ts">
import { CheckIcon, ExclamationTriangleIcon, MagnifyingGlassIcon, PlusIcon, SignalIcon, XMarkIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Device, type DeviceHint } from '@/api/client'
import DeviceFormDialog from '@/components/DeviceFormDialog.vue'
import DiscoverDialog from '@/components/DiscoverDialog.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useJobWatcher } from '@/composables/useJobWatcher'
import DeviceStatusTag from '@/components/DeviceStatusTag.vue'
import SwitchIcon from '@/components/SwitchIcon.vue'
import UiColumnMenu from '@/components/ui/UiColumnMenu.vue'
import UiCsvButton from '@/components/ui/UiCsvButton.vue'
import UiSortTh from '@/components/ui/UiSortTh.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useColumns } from '@/composables/useColumns'
import { useNotify } from '@/composables/useNotify'
import { useTableSort } from '@/composables/useTableSort'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'
import { csvDate, downloadCsv } from '@/utils/csv'
import UiTime from '@/components/ui/UiTime.vue'
import { useQueryParam } from '@/composables/useQueryState'

const { t } = useI18n()
const notify = useNotify()
const auth = useAuthStore()
const sites = useSitesStore()

const devices = ref<Device[]>([])
const hints = ref<DeviceHint[]>([])
const hintsOf = (id: number): DeviceHint[] => hints.value.filter((h) => h.device_id === id)
const devicesWithHints = computed(() => new Set(hints.value.map((h) => h.device_id)).size)
const loading = ref(false)
const search = useQueryParam('q')
// status filter, also set from the dashboard (?status=offline)
const STATUS_FILTERS = ['online', 'offline', 'unknown', 'unconfirmed'] as const
const statusFilter = useQueryParam('status')
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

const canCreate = computed(() => auth.can('devices.manage', sites.currentId))

const columns = computed<{ key: Parameters<typeof sort.toggle>[0]; label: string }[]>(() => [
  { key: 'name', label: t('common.name') },
  { key: 'ip_address', label: t('device.ip') },
  { key: 'dns_name', label: t('device.dns') },
  { key: 'place', label: t('switchports.place') },
  { key: 'model', label: t('device.model') },
  { key: 'firmware', label: t('device.firmware') },
  { key: 'status', label: t('device.status') },
  { key: 'last_seen_at', label: t('device.lastSeen') },
])
// The name always stays; everything else can be hidden.
const cols = useColumns<(typeof columns.value)[number]['key']>('devices')
const optionalColumns = computed(() => columns.value.filter((c) => c.key !== 'name'))
const shownColumns = computed(() => columns.value.filter((c) => c.key === 'name' || cols.shows(c.key)))

/** All columns of the rows currently shown, whatever is hidden on screen. */
function exportCsv(): void {
  downloadCsv(
    `switches-${sites.current?.name ?? ''}`,
    [t('common.name'), t('device.hostname'), t('device.ip'), t('device.dns'), t('switchports.place'), t('device.location'), t('device.model'), t('device.serial'), t('device.firmware'), t('device.status'), t('device.lastSeen')],
    rows.value.map((d) => [
      d.name,
      d.hostname,
      d.ip_address,
      d.dns_name,
      place(d),
      d.location_note,
      d.model_name || t(`device.models.${d.model}`),
      d.serial_number,
      d.firmware,
      t(`device.statuses.${d.status}`),
      csvDate(d.last_seen_at),
    ]),
  )
}

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

/** room id -> "building room", so the search also finds switches by their place */
const places = computed(() => {
  const map = new Map<number, string>()
  for (const b of sites.current?.buildings ?? []) for (const r of b.rooms) map.set(r.id, `${b.name} · ${r.name}`)
  return map
})

const place = (d: Device): string | undefined => (d.room_id === null ? undefined : places.value.get(d.room_id))

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return devices.value.filter(
    (d) =>
      (!statusFilter.value || d.status === statusFilter.value) &&
      (!q ||
        [d.name, d.hostname, d.ip_address, d.dns_name, d.model_name, d.serial_number, d.firmware, place(d), d.location_note].some((v) =>
          v?.toLowerCase().includes(q),
        )),
  )
})

const { sort, sorted: rows } = useTableSort(
  () => filtered.value,
  {
    name: (d) => d.name,
    ip_address: (d) => d.ip_address,
    dns_name: (d) => d.dns_name,
    place,
    model: (d) => d.model_name || d.model,
    firmware: (d) => d.firmware,
    status: (d) => d.status,
    last_seen_at: (d) => d.last_seen_at,
  },
  'name',
  true,
  'sort',
)

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
        <UiColumnMenu :columns="optionalColumns" :state="cols" />
        <UiCsvButton :disabled="!rows.length" @click="exportCsv" />
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
            <UiSortTh v-for="col in shownColumns" :key="col.key" :sort="sort" :column="col.key">{{ col.label }}</UiSortTh>
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
            <td v-if="cols.shows('ip_address')" class="whitespace-nowrap"><span v-if="d.ip_address">{{ d.ip_address }}</span><span v-else class="muted">—</span></td>
            <td v-if="cols.shows('dns_name')" class="max-w-56 truncate" :title="d.dns_name ?? ''"><span v-if="d.dns_name">{{ d.dns_name }}</span><span v-else class="muted">—</span></td>
            <td v-if="cols.shows('place')" class="max-w-56 truncate" :title="place(d) ?? ''"><span v-if="place(d)">{{ place(d) }}</span><span v-else class="muted">—</span></td>
            <td v-if="cols.shows('model')">{{ d.model_name || t(`device.models.${d.model}`) }}</td>
            <td v-if="cols.shows('firmware')">{{ d.firmware || '—' }}</td>
            <td v-if="cols.shows('status')"><DeviceStatusTag :status="d.status" /></td>
            <td v-if="cols.shows('last_seen_at')" class="whitespace-nowrap tabular-nums"><UiTime :value="d.last_seen_at" /></td>
          </tr>
          <tr v-if="loading">
            <td :colspan="shownColumns.length + 1" class="py-8"><UiSpinner class="mx-auto" /></td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="shownColumns.length + 1" class="py-8 text-center text-gray-500">—</td>
          </tr>
        </tbody>
      </table>
    </div>

    <DeviceFormDialog v-model:open="dialogOpen" @saved="load" />
    <DiscoverDialog v-model:open="discoverOpen" @started="watchJob" />
  </div>
</template>
