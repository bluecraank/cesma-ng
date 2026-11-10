<script setup lang="ts">
import { CheckIcon } from '@heroicons/vue/20/solid'
import { BellAlertIcon, ExclamationTriangleIcon, InformationCircleIcon, XCircleIcon } from '@heroicons/vue/24/outline'
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Notification } from '@/api/client'
import { useNotify } from '@/composables/useNotify'
import { useNotificationsStore } from '@/stores/notifications'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()
const counter = useNotificationsStore()

const items = ref<Notification[]>([])
const showAll = ref(false)

const icons = { critical: XCircleIcon, warning: ExclamationTriangleIcon, info: InformationCircleIcon }
const colors = {
  critical: 'text-red-500',
  warning: 'text-yellow-500',
  info: 'text-brand-500',
}

async function load(): Promise<void> {
  await notify.run(async () => {
    items.value = await api.get<Notification[]>('/notifications', {
      site_id: sites.currentId,
      include_acknowledged: showAll.value,
    })
  })
  void counter.refresh()
}

async function acknowledge(n: Notification): Promise<void> {
  if (await notify.run(() => api.post(`/notifications/${n.id}/acknowledge`))) await load()
}

async function acknowledgeAll(): Promise<void> {
  if (sites.currentId === null) return
  if (await notify.run(() => api.post(`/notifications/acknowledge-all?site_id=${sites.currentId}`))) await load()
}

watch([() => sites.currentId, showAll], load, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="page-title">{{ t('notifications.title') }}</h1>
      <div class="flex items-center gap-4">
        <label class="flex items-center gap-2 text-sm"><input v-model="showAll" type="checkbox" class="accent-brand-600" /> {{ t('notifications.showAll') }}</label>
        <button type="button" class="btn btn-secondary" :disabled="!items.some((n) => !n.acknowledged_at)" @click="acknowledgeAll">
          <CheckIcon class="size-4" /> {{ t('notifications.acknowledgeAll') }}
        </button>
      </div>
    </div>

    <div v-if="!items.length" class="card flex flex-col items-center gap-3 py-12 text-gray-500">
      <BellAlertIcon class="size-10 text-gray-300 dark:text-gray-600" />
      {{ t('notifications.empty') }}
    </div>

    <ul v-else class="card divide-y divide-gray-100 dark:divide-white/5">
      <li v-for="n in items" :key="n.id" class="flex items-start gap-4 px-5 py-4" :class="{ 'opacity-60': n.acknowledged_at }">
        <component :is="icons[n.severity]" class="mt-0.5 size-6 shrink-0" :class="colors[n.severity]" />
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium text-gray-900 dark:text-white">{{ n.message }}</p>
          <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {{ formatDateTime(n.created_at, locale) }}
            <template v-if="n.device_id">
              ·
              <RouterLink :to="{ name: 'device', params: { id: n.device_id } }" class="link">{{ t('device.details') }}</RouterLink>
            </template>
            <template v-if="n.acknowledged_at"> · {{ t('notifications.acknowledgedBy', { user: n.acknowledged_by }) }}</template>
          </p>
        </div>
        <button v-if="!n.acknowledged_at" type="button" class="btn btn-secondary btn-sm" @click="acknowledge(n)">
          <CheckIcon class="size-4" /> {{ t('notifications.acknowledge') }}
        </button>
      </li>
    </ul>
  </div>
</template>
