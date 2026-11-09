<script setup lang="ts">
import { ArrowPathIcon, ChevronLeftIcon, KeyIcon, PencilSquareIcon, TagIcon, TrashIcon } from '@heroicons/vue/20/solid'
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api, type Backup, type Device, type DeviceHint, type DeviceVlan, type FdbEntry, type Job, type LldpNeighbor, type PollState, type Port } from '@/api/client'
import DeviceFormDialog from '@/components/DeviceFormDialog.vue'
import BackupList from '@/components/BackupList.vue'
import ConsoleTab from '@/components/device/ConsoleTab.vue'
import DeviceHints from '@/components/DeviceHints.vue'
import DeviceStatusTag from '@/components/DeviceStatusTag.vue'
import PortsTab from '@/components/device/PortsTab.vue'
import RenameDialog from '@/components/device/RenameDialog.vue'
import SimpleTabs from '@/components/device/SimpleTabs.vue'
import { useConfirm, useConfirmDelete } from '@/composables/useConfirm'
import { useJobWatcher } from '@/composables/useJobWatcher'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime, formatUptime } from '@/utils/format'

type Tab = 'ports' | 'vlans' | 'fdb' | 'lldp' | 'backups' | 'console' | 'poll' | 'details'
const ALL_TABS: Tab[] = ['ports', 'vlans', 'fdb', 'lldp', 'backups', 'console', 'poll', 'details']

const props = defineProps<{ id: number }>()
const { t, locale } = useI18n()
const notify = useNotify()
const confirmDelete = useConfirmDelete()
const { confirm } = useConfirm()
const { watch: watchJob } = useJobWatcher()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const sites = useSitesStore()

const device = ref<Device | null>(null)
const ports = ref<Port[]>([])
const vlans = ref<DeviceVlan[]>([])
const fdb = ref<FdbEntry[]>([])
const lldp = ref<LldpNeighbor[]>([])
const poll = ref<PollState[]>([])
const backups = ref<Backup[]>([])
const hints = ref<DeviceHint[]>([])
const editOpen = ref(false)
const renameOpen = ref(false)
const refreshing = ref(false)

// The tab lives in the URL so links and reloads keep it.
const tab = computed<Tab>({
  get: () => (TABS.value.includes(route.query.tab as Tab) ? (route.query.tab as Tab) : 'ports'),
  set: (value) => void router.replace({ query: { ...route.query, tab: value } }),
})
const tabLabels = computed<Record<Tab, string>>(() => ({
  ports: `${t('ports.title')} (${ports.value.length})`,
  vlans: `${t('vlans.title')} (${vlans.value.length})`,
  fdb: `${t('fdb.title')} (${fdb.value.length})`,
  lldp: `${t('lldp.title')} (${lldp.value.length})`,
  backups: t('backups.title'),
  console: t('console.title'),
  poll: t('poll.title'),
  details: t('device.details'),
}))

const siteId = computed(() => device.value?.site_id)
const canManage = computed(() => auth.can('devices.manage', siteId.value))
const canEditPorts = computed(() => auth.can('ports.edit', siteId.value))
const canPushKeys = computed(() => auth.can('ssh_keys.push', siteId.value) && !!device.value?.supports_ssh_keys)
const TABS = computed(() => ALL_TABS.filter((name) => name !== 'console' || auth.can('console', siteId.value)))
const roomLabel = computed(
  () => sites.rooms(device.value?.site_id ?? null).find((r) => r.id === device.value?.room_id)?.label,
)
// ?port=<id> scrolls to that port (links from the client list)
const focusPortId = computed(() => (route.query.port ? Number(route.query.port) : null))
const portsUp = computed(() => ports.value.filter((p) => p.oper_up).length)

const facts = computed(() => {
  const d = device.value
  if (!d) return []
  return [
    { label: t('device.hostname'), value: d.hostname, mono: true },
    { label: t('device.ip'), value: d.ip_address, mono: true },
    { label: t('device.dns'), value: d.dns_name, mono: true },
    { label: t('device.model'), value: d.model_name || t(`device.models.${d.model}`) },
    { label: t('device.firmware'), value: d.firmware },
    { label: t('device.serial'), value: d.serial_number, mono: true },
    { label: 'MAC', value: d.mac_address, mono: true },
    { label: 'sysName', value: d.sys_name },
    { label: t('device.uptime'), value: formatUptime(d.uptime_seconds) },
    { label: t('device.lastSeen'), value: formatDateTime(d.last_seen_at, locale.value) },
    { label: t('device.room'), value: roomLabel.value },
    { label: t('device.location'), value: d.location_note },
  ]
})

async function load(): Promise<void> {
  await notify.run(async () => {
    const base = `/devices/${props.id}`
    const [d, p, v, f, l, s, b] = await Promise.all([
      api.get<Device>(base),
      api.get<Port[]>(`${base}/ports`),
      api.get<DeviceVlan[]>(`${base}/vlans`),
      api.get<FdbEntry[]>(`${base}/fdb`),
      api.get<LldpNeighbor[]>(`${base}/lldp`),
      api.get<PollState[]>(`${base}/poll-state`),
      api.get<Backup[]>('/backups', { device_id: props.id }),
    ])
    device.value = d
    ports.value = p
    vlans.value = v
    fdb.value = f
    lldp.value = l
    poll.value = s
    backups.value = b
    hints.value = (await api.get<DeviceHint[]>(`/sites/${d.site_id}/device-hints`).catch(() => [])).filter((h) => h.device_id === d.id)
  })
}

let reloadTimer: ReturnType<typeof setTimeout> | undefined
async function refresh(): Promise<void> {
  refreshing.value = true
  if (await notify.run(() => api.post(`/devices/${props.id}/poll`), t('poll.refreshed'))) {
    // The worker picks the request up within seconds; reload twice to show the result.
    reloadTimer = setTimeout(load, 4000)
    setTimeout(async () => {
      await load()
      refreshing.value = false
    }, 9000)
  } else {
    refreshing.value = false
  }
}
onUnmounted(() => clearTimeout(reloadTimer))

/** Uploads the SSH keys of all users with SSH access to this site onto this one switch. */
async function pushKeys(): Promise<void> {
  const d = device.value
  if (!d) return
  const ok = await confirm({
    title: t('sshKeys.push'),
    message: t('sshKeys.pushDevice', { device: d.name }),
    confirmLabel: t('sshKeys.push'),
    cancelLabel: t('common.cancel'),
    danger: true,
  })
  if (!ok) return
  await notify.run(async () => {
    watchJob(await api.post<Job>('/jobs', { kind: 'ssh_keys', site_id: d.site_id, device_ids: [d.id] }))
    notify.success(t('sshKeys.pushed'))
  })
}

async function remove(): Promise<void> {
  const d = device.value
  if (!d || !(await confirmDelete(d.name))) return
  if (await notify.run(() => api.delete(`/devices/${d.id}`), t('common.deleted'))) {
    await router.push({ name: 'devices' })
  }
}

watch(() => props.id, load, { immediate: true })
</script>

<template>
  <div v-if="device" class="space-y-6">
    <RouterLink :to="{ name: 'devices' }" class="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white">
      <ChevronLeftIcon class="size-4" /> {{ t('device.title') }}
    </RouterLink>

    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <h1 class="page-title">{{ device.name }}</h1>
          <DeviceStatusTag :status="device.status" />
        </div>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {{ device.model_name || t(`device.models.${device.model}`) }}
          <template v-if="device.firmware"> · {{ device.firmware }}</template>
          <template v-if="ports.length"> · {{ portsUp }}/{{ ports.length }} {{ t('ports.up') }}</template>
          <template v-if="device.uptime_seconds"> · {{ t('device.uptime') }} {{ formatUptime(device.uptime_seconds) }}</template>
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="btn btn-secondary" :disabled="refreshing" @click="refresh">
          <ArrowPathIcon class="size-4" :class="{ 'animate-spin': refreshing }" /> {{ t('poll.refresh') }}
        </button>
        <button v-if="canPushKeys" type="button" class="btn btn-secondary" @click="pushKeys">
          <KeyIcon class="size-4" /> {{ t('sshKeys.pushOne') }}
        </button>
        <template v-if="canManage">
          <button type="button" class="btn btn-secondary" @click="renameOpen = true">
            <TagIcon class="size-4" /> {{ t('rename.title') }}
          </button>
          <button type="button" class="btn btn-secondary" @click="editOpen = true">
            <PencilSquareIcon class="size-4" /> {{ t('common.edit') }}
          </button>
          <button type="button" class="btn btn-secondary text-red-600 dark:text-red-400" @click="remove">
            <TrashIcon class="size-4" /> {{ t('common.delete') }}
          </button>
        </template>
      </div>
    </div>

    <DeviceHints :hints="hints" />

    <nav class="-mb-px flex gap-6 overflow-x-auto border-b border-gray-200 dark:border-white/10">
      <button
        v-for="name in TABS"
        :key="name"
        type="button"
        class="border-b-2 px-1 py-3 text-sm font-medium whitespace-nowrap"
        :class="
          tab === name
            ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
            : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
        "
        @click="tab = name"
      >
        {{ tabLabels[name] }}
      </button>
    </nav>

    <PortsTab
      v-if="tab === 'ports'"
      :device-id="device.id"
      :site-id="device.site_id"
      :ports="ports"
      :vlans="vlans"
      :can-edit="canEditPorts"
      :focus-port-id="focusPortId"
      @changed="load"
    />
    <ConsoleTab v-else-if="tab === 'console'" :device-id="device.id" :model="device.model" />
    <BackupList v-else-if="tab === 'backups'" :backups="backups" />
    <SimpleTabs v-else-if="tab !== 'details'" :tab="tab" :vlans="vlans" :fdb="fdb" :lldp="lldp" :poll="poll" />
    <section v-else class="card">
      <dl class="grid grid-cols-1 divide-y divide-gray-100 sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-3 dark:divide-white/5">
        <div v-for="f in facts" :key="f.label" class="px-5 py-3">
          <dt class="text-xs font-medium text-gray-500 dark:text-gray-400">{{ f.label }}</dt>
          <dd class="mt-1 text-sm break-words" :class="{ 'font-mono': f.mono }">{{ f.value || '—' }}</dd>
        </div>
      </dl>
    </section>

    <RenameDialog v-model:open="renameOpen" :device="device" @renamed="load" />
    <DeviceFormDialog v-model:open="editOpen" :device="device" @saved="(d) => (device = d)" />
  </div>
</template>
