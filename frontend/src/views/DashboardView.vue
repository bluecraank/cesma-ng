<script setup lang="ts">
import { ArrowRightIcon, ExclamationTriangleIcon } from '@heroicons/vue/16/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type AuditEntry, type AuditPage, type Device, type DeviceStatus } from '@/api/client'
import type { components } from '@/api/schema'
import DeviceStatusTag from '@/components/DeviceStatusTag.vue'
import { useNotify } from '@/composables/useNotify'
import { useSitesStore } from '@/stores/sites'
import { auditMessage } from '@/utils/auditMessage'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()

const devices = ref<Device[]>([])
const events = ref<AuditEntry[]>([])
const overview = ref<components['schemas']['SiteOverviewOut'] | null>(null)

/** Second row: network figures. "alert" marks a problem (shown with an icon, not colour alone). */
const figures = computed(() => {
  const o = overview.value
  if (!o) return []
  const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0)
  return [
    {
      key: 'ports',
      to: { name: 'switchports' },
      value: `${o.ports.up} / ${o.ports.total}`,
      detail: t('dashboard.portsDetail', { free: o.ports.free }),
      meter: pct(o.ports.up, o.ports.total),
      alert: false,
    },
    {
      key: 'uplinks',
      to: { name: 'switchports' },
      value: `${o.ports.uplinks - o.ports.uplinks_down} / ${o.ports.uplinks}`,
      detail: o.ports.uplinks_down ? t('dashboard.uplinksDown', o.ports.uplinks_down) : t('dashboard.allUp'),
      alert: o.ports.uplinks_down > 0,
    },
    {
      key: 'clients',
      to: { name: 'clients' },
      value: String(o.clients_active),
      detail: t('dashboard.clientsDetail'),
      alert: false,
    },
    {
      key: 'poe',
      to: { name: 'reports' },
      value: o.poe.ports ? `${o.poe.delivering} / ${o.poe.ports}` : '—',
      detail: o.poe.faults ? t('dashboard.poeFaults', o.poe.faults) : t('dashboard.poeDetail'),
      meter: o.poe.ports ? pct(o.poe.delivering, o.poe.ports) : undefined,
      alert: o.poe.faults > 0,
    },
    {
      key: 'backups',
      to: { name: 'backups' },
      value: String(o.backups.ok_24h),
      detail:
        [
          o.backups.failed_24h ? t('dashboard.backupsFailed', o.backups.failed_24h) : '',
          o.backups.stale ? t('dashboard.backupsStale', o.backups.stale) : '',
        ]
          .filter(Boolean)
          .join(', ') || t('dashboard.backupsOk'),
      alert: o.backups.failed_24h > 0 || o.backups.stale > 0,
    },
    {
      key: 'notifications',
      to: { name: 'notifications' },
      value: String(o.notifications_open),
      detail: t('dashboard.notificationsDetail'),
      alert: o.notifications_open > 0,
    },
    {
      key: 'linkChanges',
      to: { name: 'switchports' },
      value: String(o.link_changes_24h),
      detail: t('dashboard.linkChangesDetail'),
      alert: false,
    },
    {
      key: 'vlans',
      to: { name: 'vlans' },
      value: String(o.vlans),
      detail: t('dashboard.vlansDetail'),
      alert: false,
    },
  ]
})

const STATUSES: { status: DeviceStatus; color: string }[] = [
  { status: 'online', color: 'text-green-600 dark:text-green-400' },
  { status: 'offline', color: 'text-red-600 dark:text-red-400' },
  { status: 'unknown', color: 'text-gray-500 dark:text-gray-400' },
  { status: 'unconfirmed', color: 'text-yellow-600 dark:text-yellow-500' },
]
const counts = computed(() =>
  STATUSES.map((s) => ({ ...s, count: devices.value.filter((d) => d.status === s.status).length })),
)
const problems = computed(() => devices.value.filter((d) => d.status === 'offline' || d.status === 'unconfirmed'))

async function load(): Promise<void> {
  if (sites.currentId === null) return
  await notify.run(async () => {
    const [deviceList, audit, figuresData] = await Promise.all([
      api.get<Device[]>('/devices', { site_id: sites.currentId }),
      api.get<AuditPage>('/audit', { site_id: sites.currentId, limit: 8 }),
      api.get<components['schemas']['SiteOverviewOut']>(`/sites/${sites.currentId}/overview`),
    ])
    devices.value = deviceList
    events.value = audit.items
    overview.value = figuresData
  })
}

watch(() => sites.currentId, load, { immediate: true })
</script>

<template>
  <div class="space-y-8">
    <div>
      <h1 class="page-title">{{ t('nav.dashboard') }}</h1>
      <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ sites.current?.name }}</p>
    </div>

    <div class="grid grid-cols-2 gap-4 lg:grid-cols-5">
      <RouterLink :to="{ name: 'devices' }" class="card px-5 py-4 transition hover:ring-gray-300 dark:hover:ring-white/20">
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('dashboard.devices') }}</p>
        <p class="mt-1 text-2xl font-semibold tabular-nums">{{ devices.length }}</p>
      </RouterLink>
      <RouterLink
        v-for="c in counts"
        :key="c.status"
        :to="{ name: 'devices', query: { status: c.status } }"
        class="card px-5 py-4 transition hover:ring-gray-300 dark:hover:ring-white/20"
      >
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ t(`dashboard.${c.status}`) }}</p>
        <p class="mt-1 text-2xl font-semibold tabular-nums" :class="c.count ? c.color : ''">{{ c.count }}</p>
      </RouterLink>
    </div>

    <div v-if="figures.length" class="grid grid-cols-2 gap-4 md:grid-cols-4">
      <RouterLink
        v-for="f in figures"
        :key="f.key"
        :to="f.to"
        class="card flex flex-col px-5 py-4 transition hover:ring-gray-300 dark:hover:ring-white/20"
      >
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ t(`dashboard.figures.${f.key}`) }}</p>
        <p class="mt-1 text-2xl font-semibold text-gray-900 tabular-nums dark:text-white">{{ f.value }}</p>
        <div v-if="f.meter !== undefined" class="mt-2 h-1 rounded-full bg-gray-100 dark:bg-white/10" role="meter" :aria-valuenow="f.meter" aria-valuemin="0" aria-valuemax="100">
          <div class="h-1 rounded-full bg-brand-500" :style="{ width: `${f.meter}%` }" />
        </div>
        <p class="mt-2 flex items-center gap-1 text-xs" :class="f.alert ? 'text-red-700 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'">
          <ExclamationTriangleIcon v-if="f.alert" class="size-3.5 shrink-0" />
          {{ f.detail }}
        </p>
      </RouterLink>
    </div>

    <div class="grid gap-6 xl:grid-cols-2">
      <section v-if="problems.length" class="card">
        <h2 class="border-b border-gray-200 px-5 py-4 text-base font-semibold dark:border-white/10">
          {{ t('dashboard.offline') }} / {{ t('dashboard.unconfirmed') }}
        </h2>
        <ul class="divide-y divide-gray-100 dark:divide-white/5">
          <li v-for="d in problems" :key="d.id" class="flex items-center justify-between gap-3 px-5 py-3">
            <RouterLink :to="{ name: 'device', params: { id: d.id } }" class="link">{{ d.name }}</RouterLink>
            <DeviceStatusTag :status="d.status" />
          </li>
        </ul>
      </section>

      <section class="card" :class="{ 'xl:col-span-2': !problems.length }">
        <div class="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-4 dark:border-white/10">
          <h2 class="text-base font-semibold">{{ t('dashboard.recent') }}</h2>
          <RouterLink :to="{ name: 'audit' }" class="link inline-flex items-center gap-1 text-sm">
            {{ t('dashboard.allEvents') }} <ArrowRightIcon class="size-4" />
          </RouterLink>
        </div>
        <ul class="divide-y divide-gray-100 dark:divide-white/5">
          <li v-for="e in events" :key="e.id" class="flex flex-col gap-0.5 px-5 py-3 sm:flex-row sm:items-center sm:gap-4">
            <span class="w-36 shrink-0 text-xs text-gray-500 tabular-nums dark:text-gray-400">{{ formatDateTime(e.created_at, locale) }}</span>
            <span class="flex-1 text-sm">{{ auditMessage(e, locale) || e.action }}</span>
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ e.actor_name }}</span>
          </li>
          <li v-if="!events.length" class="px-5 py-6 text-sm text-gray-500">—</li>
        </ul>
      </section>
    </div>
  </div>
</template>
