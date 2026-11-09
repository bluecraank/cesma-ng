<script setup lang="ts">
import { CheckIcon, ChevronUpDownIcon, MagnifyingGlassIcon, PlusIcon, SignalIcon, XMarkIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Device } from '@/api/client'
import DeviceFormDialog from '@/components/DeviceFormDialog.vue'
import DiscoverDialog from '@/components/DiscoverDialog.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useJobWatcher } from '@/composables/useJobWatcher'
import DeviceStatusTag from '@/components/DeviceStatusTag.vue'
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
const loading = ref(false)
const search = ref('')
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

type SortKey = 'name' | 'hostname' | 'model' | 'firmware' | 'status' | 'last_seen_at'
const sortKey = ref<SortKey>('name')
const sortAsc = ref(true)

const canCreate = computed(() => auth.canAdmin(sites.currentId))

const columns = computed<{ key: SortKey; label: string }[]>(() => [
  { key: 'name', label: t('common.name') },
  { key: 'hostname', label: t('device.hostname') },
  { key: 'model', label: t('device.model') },
  { key: 'firmware', label: t('device.firmware') },
  { key: 'status', label: t('device.status') },
  { key: 'last_seen_at', label: t('device.lastSeen') },
])

async function load(): Promise<void> {
  if (sites.currentId === null) return
  loading.value = true
  await notify.run(async () => {
    devices.value = await api.get<Device[]>('/devices', { site_id: sites.currentId })
  })
  loading.value = false
}

function sortBy(key: SortKey): void {
  sortAsc.value = sortKey.value === key ? !sortAsc.value : true
  sortKey.value = key
}

const rows = computed(() => {
  const q = search.value.trim().toLowerCase()
  const filtered = q
    ? devices.value.filter((d) =>
        [d.name, d.hostname, d.model_name, d.serial_number, d.firmware].some((v) => v?.toLowerCase().includes(q)),
      )
    : devices.value
  const dir = sortAsc.value ? 1 : -1
  return [...filtered].sort((a, b) => String(a[sortKey.value] ?? '').localeCompare(String(b[sortKey.value] ?? ''), undefined, { numeric: true }) * dir)
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
        <button v-if="canCreate" type="button" class="btn btn-secondary" @click="discoverOpen = true">
          <SignalIcon class="size-4" /> {{ t('discover.title') }}
        </button>
        <button v-if="canCreate" type="button" class="btn btn-primary" @click="dialogOpen = true">
          <PlusIcon class="size-5" /> {{ t('device.new') }}
        </button>
      </div>
    </div>

    <div v-if="unconfirmed.length" class="rounded-xl bg-yellow-50 p-4 ring-1 ring-yellow-600/20 dark:bg-yellow-500/10 dark:ring-yellow-500/20">
      <p class="text-sm font-semibold text-yellow-800 dark:text-yellow-300">{{ t('discover.waiting', { n: unconfirmed.length }) }}</p>
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
            <th v-for="col in columns" :key="col.key">
              <button type="button" class="inline-flex items-center gap-1 uppercase hover:text-gray-900 dark:hover:text-white" @click="sortBy(col.key)">
                {{ col.label }}
                <ChevronUpDownIcon class="size-4" :class="sortKey === col.key ? 'text-indigo-500' : 'opacity-40'" />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in rows" :key="d.id">
            <td>
              <RouterLink :to="{ name: 'device', params: { id: d.id } }" class="link">{{ d.name }}</RouterLink>
            </td>
            <td class="font-mono text-xs">{{ d.hostname }}</td>
            <td>{{ d.model_name || t(`device.models.${d.model}`) }}</td>
            <td>{{ d.firmware || '—' }}</td>
            <td><DeviceStatusTag :status="d.status" /></td>
            <td class="whitespace-nowrap tabular-nums">{{ formatDateTime(d.last_seen_at, locale) }}</td>
          </tr>
          <tr v-if="loading">
            <td :colspan="columns.length" class="py-8"><UiSpinner class="mx-auto" /></td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="columns.length" class="py-8 text-center text-gray-500">—</td>
          </tr>
        </tbody>
      </table>
    </div>

    <DeviceFormDialog v-model:open="dialogOpen" @saved="load" />
    <DiscoverDialog v-model:open="discoverOpen" @started="watchJob" />
  </div>
</template>
