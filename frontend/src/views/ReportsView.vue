<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ApiError } from '@/api/client'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useNotify } from '@/composables/useNotify'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

interface Report {
  firmware: { model: string; firmware: string; devices: string[] }[]
  free_ports: { device_id: number; device: string; total: number; free: string[] }[]
  poe: { device_id: number; device: string; ports: number; delivering: number; faults: string[] }[]
  errors: { device_id: number; device: string; port: string; errors: number }[]
  backups: { device_id: number; device: string; last_backup: string | null }[]
}

const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()
const report = ref<Report | null>(null)
const loading = ref(false)
const failed = ref('')

async function load(): Promise<void> {
  if (sites.currentId === null) return
  loading.value = true
  failed.value = ''
  try {
    report.value = await api.get<Report>(`/sites/${sites.currentId}/reports`)
  } catch (err) {
    report.value = null
    failed.value = err instanceof ApiError ? err.message : String(err)
    notify.error(err)
  } finally {
    loading.value = false
  }
}
watch(() => sites.currentId, load, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <h1 class="page-title">{{ t('reports.title') }}</h1>

    <p v-if="sites.currentId === null" class="card p-6 text-sm text-gray-500">{{ t('reports.noSite') }}</p>
    <div v-else-if="failed" class="card flex flex-wrap items-center gap-4 p-6 text-sm">
      <span class="text-red-600 dark:text-red-400">{{ t('reports.failed') }}: {{ failed }}</span>
      <button type="button" class="btn btn-secondary btn-sm" @click="load">{{ t('reports.retry') }}</button>
    </div>
    <UiSpinner v-else-if="loading && !report" class="mx-auto" />

    <div v-if="report && !failed" class="grid gap-6 xl:grid-cols-2">
      <section class="card">
        <h2 class="border-b border-gray-200 px-5 py-4 text-base font-semibold dark:border-white/10">{{ t('reports.firmware') }}</h2>
        <table class="table">
          <tbody>
            <tr v-for="f in report.firmware" :key="f.model + f.firmware">
              <td class="font-medium">{{ f.model }}</td>
              <td class="font-mono text-xs">{{ f.firmware }}</td>
              <td class="text-xs text-gray-500">{{ f.devices.join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2 class="border-b border-gray-200 px-5 py-4 text-base font-semibold dark:border-white/10">{{ t('reports.backups') }}</h2>
        <p v-if="!report.backups.length" class="px-5 py-4 text-sm text-green-700 dark:text-green-400">{{ t('reports.backupsOk') }}</p>
        <table v-else class="table">
          <tbody>
            <tr v-for="b in report.backups" :key="b.device_id">
              <td><RouterLink :to="{ name: 'device', params: { id: b.device_id }, query: { tab: 'backups' } }" class="link">{{ b.device }}</RouterLink></td>
              <td class="text-right text-xs text-red-600 dark:text-red-400">{{ b.last_backup ? formatDateTime(b.last_backup, locale) : t('reports.never') }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2 class="border-b border-gray-200 px-5 py-4 text-base font-semibold dark:border-white/10">{{ t('reports.freePorts') }}</h2>
        <p class="px-5 pt-3 text-xs text-gray-500">{{ t('reports.freePortsHint') }}</p>
        <table class="table">
          <tbody>
            <tr v-for="f in report.free_ports" :key="f.device_id">
              <td><RouterLink :to="{ name: 'device', params: { id: f.device_id } }" class="link">{{ f.device }}</RouterLink></td>
              <td class="w-48">
                <div class="flex items-center gap-2">
                  <div class="h-1.5 flex-1 rounded-full bg-gray-100 dark:bg-white/10">
                    <div class="h-1.5 rounded-full bg-brand-500" :style="{ width: `${f.total ? ((f.total - f.free.length) / f.total) * 100 : 0}%` }" />
                  </div>
                  <span class="text-xs tabular-nums">{{ f.free.length }} / {{ f.total }}</span>
                </div>
              </td>
              <td class="max-w-64 truncate font-mono text-xs text-gray-500" :title="f.free.join(', ')">{{ f.free.join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2 class="border-b border-gray-200 px-5 py-4 text-base font-semibold dark:border-white/10">PoE</h2>
        <table class="table">
          <tbody>
            <tr v-for="p in report.poe" :key="p.device_id">
              <td><RouterLink :to="{ name: 'device', params: { id: p.device_id } }" class="link">{{ p.device }}</RouterLink></td>
              <td class="text-xs tabular-nums">{{ t('reports.poeDelivering', { n: p.delivering, total: p.ports }) }}</td>
              <td><span v-if="p.faults.length" class="badge badge-red">{{ t('reports.poeFaults') }}: {{ p.faults.join(', ') }}</span></td>
            </tr>
            <tr v-if="!report.poe.length"><td class="text-sm text-gray-500">—</td></tr>
          </tbody>
        </table>
      </section>

      <section class="card xl:col-span-2">
        <h2 class="border-b border-gray-200 px-5 py-4 text-base font-semibold dark:border-white/10">{{ t('reports.errors') }}</h2>
        <p v-if="!report.errors.length" class="px-5 py-4 text-sm text-green-700 dark:text-green-400">{{ t('reports.noErrors') }}</p>
        <table v-else class="table">
          <tbody>
            <tr v-for="e in report.errors" :key="`${e.device_id}-${e.port}`">
              <td><RouterLink :to="{ name: 'device', params: { id: e.device_id } }" class="link">{{ e.device }}</RouterLink></td>
              <td class="font-mono">{{ e.port }}</td>
              <td class="text-right font-medium text-red-600 tabular-nums dark:text-red-400">{{ e.errors }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>
