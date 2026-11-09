<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type AuditEntry, type AuditPage, type Device, type DeviceStatus } from '@/api/client'
import DeviceStatusTag from '@/components/DeviceStatusTag.vue'
import { useNotify } from '@/composables/useNotify'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()

const devices = ref<Device[]>([])
const events = ref<AuditEntry[]>([])

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
    const [deviceList, audit] = await Promise.all([
      api.get<Device[]>('/devices', { site_id: sites.currentId }),
      api.get<AuditPage>('/audit', { site_id: sites.currentId, limit: 8 }),
    ])
    devices.value = deviceList
    events.value = audit.items
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

    <dl class="grid grid-cols-2 gap-4 lg:grid-cols-5">
      <div class="card px-5 py-4">
        <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">{{ t('dashboard.devices') }}</dt>
        <dd class="mt-1 text-3xl font-semibold tracking-tight">{{ devices.length }}</dd>
      </div>
      <div v-for="c in counts" :key="c.status" class="card px-5 py-4">
        <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">{{ t(`dashboard.${c.status}`) }}</dt>
        <dd class="mt-1 text-3xl font-semibold tracking-tight" :class="c.count ? c.color : ''">{{ c.count }}</dd>
      </div>
    </dl>

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
        <h2 class="border-b border-gray-200 px-5 py-4 text-base font-semibold dark:border-white/10">{{ t('dashboard.recent') }}</h2>
        <ul class="divide-y divide-gray-100 dark:divide-white/5">
          <li v-for="e in events" :key="e.id" class="flex flex-col gap-0.5 px-5 py-3 sm:flex-row sm:items-center sm:gap-4">
            <span class="w-36 shrink-0 text-xs text-gray-500 tabular-nums dark:text-gray-400">{{ formatDateTime(e.created_at, locale) }}</span>
            <span class="flex-1 text-sm">{{ e.message || e.action }}</span>
            <span class="text-xs text-gray-500 dark:text-gray-400">{{ e.actor_name }}</span>
          </li>
          <li v-if="!events.length" class="px-5 py-6 text-sm text-gray-500">—</li>
        </ul>
      </section>
    </div>
  </div>
</template>
