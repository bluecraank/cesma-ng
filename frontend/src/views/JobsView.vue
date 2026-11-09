<script setup lang="ts">
import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/vue/20/solid'
import { onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Job } from '@/api/client'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()
const sites = useSitesStore()
const jobs = ref<Job[]>([])
const expanded = ref<number | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

const badge = { pending: 'badge-gray', running: 'badge-blue', done: 'badge-green', failed: 'badge-red' } as const

async function load(): Promise<void> {
  clearTimeout(timer)
  jobs.value = await api.get<Job[]>('/jobs', { site_id: sites.currentId }).catch(() => jobs.value)
  // refresh while something is running
  if (jobs.value.some((j) => j.status === 'pending' || j.status === 'running')) timer = setTimeout(load, 2000)
}

watch(() => sites.currentId, load, { immediate: true })
onUnmounted(() => clearTimeout(timer))
</script>

<template>
  <div class="space-y-6">
    <h1 class="page-title">{{ t('jobs.title') }}</h1>
    <div class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th class="w-6" />
            <th>{{ t('audit.time') }}</th>
            <th>{{ t('audit.action') }}</th>
            <th>{{ t('device.status') }}</th>
            <th>{{ t('audit.actor') }}</th>
            <th>{{ t('poll.error') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="j in jobs" :key="j.id">
            <tr class="cursor-pointer" @click="expanded = expanded === j.id ? null : j.id">
              <td class="text-gray-400">
                <ChevronDownIcon v-if="expanded === j.id" class="size-4" />
                <ChevronRightIcon v-else class="size-4" />
              </td>
              <td class="whitespace-nowrap tabular-nums">{{ formatDateTime(j.created_at, locale) }}</td>
              <td class="font-medium">{{ t(`jobs.kinds.${j.kind}`) }} <span class="text-xs text-gray-400">#{{ j.id }}</span></td>
              <td class="whitespace-nowrap">
                <span class="badge" :class="badge[j.status as keyof typeof badge]">{{ t(`jobs.statuses.${j.status}`) }}</span>
                <span v-if="j.status === 'running'" class="ml-2 text-xs tabular-nums">{{ j.progress }} %</span>
              </td>
              <td>{{ j.created_by }}</td>
              <td class="max-w-md text-xs text-red-600 dark:text-red-400">{{ j.error }}</td>
            </tr>
            <tr v-if="expanded === j.id" class="hover:bg-transparent">
              <td />
              <td colspan="5">
                <pre class="max-h-72 overflow-auto rounded-md bg-gray-900 p-3 font-mono text-xs text-gray-200">{{ j.log || '—' }}</pre>
              </td>
            </tr>
          </template>
          <tr v-if="!jobs.length"><td colspan="6" class="py-8 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
