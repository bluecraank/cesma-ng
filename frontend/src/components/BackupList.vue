<script setup lang="ts">
/** Backup table, used on the backups page (whole site) and on the device page. */
import { ArrowDownTrayIcon, ArrowUturnLeftIcon, ArrowsRightLeftIcon } from '@heroicons/vue/20/solid'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Backup, type Job } from '@/api/client'
import { useJobWatcher } from '@/composables/useJobWatcher'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ backups: Backup[]; showDevice?: boolean }>()
const auth = useAuthStore()
const { t, locale } = useI18n()
const notify = useNotify()

const diffOpen = ref(false)
const diffText = ref('')
const diffTitle = ref('')
const { watch: watchJob } = useJobWatcher()

// Restoring overwrites the running configuration: confirm by typing the device name.
const restoreOf = ref<Backup | null>(null)
const restoreOpen = ref(false)
const confirmName = ref('')

function askRestore(backup: Backup): void {
  restoreOf.value = backup
  confirmName.value = ''
  restoreOpen.value = true
}

async function restore(): Promise<void> {
  const b = restoreOf.value
  if (!b || confirmName.value !== b.device_name) return
  const ok = await notify.run(async () => {
    watchJob(await api.post<Job>('/jobs', { kind: 'restore', site_id: b.site_id, backup_id: b.id }))
  }, t('backups.restoreStarted'))
  if (ok) restoreOpen.value = false
}

function previousOf(backup: Backup): Backup | undefined {
  return props.backups.find((b) => b.device_id === backup.device_id && b.status === 'ok' && b.created_at < backup.created_at)
}

async function showDiff(backup: Backup): Promise<void> {
  const previous = previousOf(backup)
  if (!previous) return
  await notify.run(async () => {
    const result = await api.get<{ diff: string }>('/backups/diff', { old: previous.id, new: backup.id })
    diffText.value = result.diff
    diffTitle.value = `${backup.device_name}: ${formatDateTime(previous.created_at, locale.value)} → ${formatDateTime(backup.created_at, locale.value)}`
    diffOpen.value = true
  })
}

function lineClass(line: string): string {
  if (line.startsWith('+') && !line.startsWith('+++')) return 'text-green-400'
  if (line.startsWith('-') && !line.startsWith('---')) return 'text-red-400'
  if (line.startsWith('@@')) return 'text-brand-300'
  return 'text-gray-300'
}

function size(bytes: number): string {
  return bytes > 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`
}
</script>

<template>
  <div class="card table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>{{ t('audit.time') }}</th>
          <th v-if="showDevice">{{ t('device.title') }}</th>
          <th>{{ t('device.status') }}</th>
          <th class="text-right">{{ t('backups.size') }}</th>
          <th>{{ t('backups.by') }}</th>
          <th class="w-24" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in backups" :key="b.id">
          <td class="whitespace-nowrap tabular-nums">{{ formatDateTime(b.created_at, locale) }}</td>
          <td v-if="showDevice">
            <RouterLink :to="{ name: 'device', params: { id: b.device_id }, query: { tab: 'backups' } }" class="link">{{ b.device_name }}</RouterLink>
          </td>
          <td>
            <span v-if="b.status === 'failed'" class="badge badge-red" :title="b.error ?? ''">{{ t('jobs.statuses.failed') }}</span>
            <span v-else-if="b.changed" class="badge badge-brand">{{ t('backups.changed') }}</span>
            <span v-else class="badge badge-gray">{{ t('backups.unchanged') }}</span>
            <p v-if="b.error" class="mt-1 max-w-md text-xs text-red-600 dark:text-red-400">{{ b.error }}</p>
          </td>
          <td class="text-right tabular-nums">{{ b.status === 'ok' ? size(b.size) : '' }}</td>
          <td class="text-xs">{{ b.created_by }}</td>
          <td class="whitespace-nowrap">
            <template v-if="b.status === 'ok' && auth.can('backups.read', b.site_id)">
              <button v-if="b.changed && previousOf(b)" type="button" class="btn-icon" :title="t('backups.diff')" @click="showDiff(b)">
                <ArrowsRightLeftIcon class="size-4" />
              </button>
              <a :href="`/api/v1/backups/${b.id}/config`" class="btn-icon inline-flex" :title="t('backups.download')">
                <ArrowDownTrayIcon class="size-4" />
              </a>
              <button v-if="auth.can('backups.restore', b.site_id)" type="button" class="btn-icon hover:!text-orange-600" :title="t('backups.restore')" @click="askRestore(b)">
                <ArrowUturnLeftIcon class="size-4" />
              </button>
            </template>
          </td>
        </tr>
        <tr v-if="!backups.length"><td :colspan="showDevice ? 6 : 5" class="py-8 text-center text-gray-500">—</td></tr>
      </tbody>
    </table>

    <UiDialog v-model:open="restoreOpen" :title="t('backups.restore')">
      <form id="restore-form" class="space-y-4" @submit.prevent="restore">
        <p class="rounded-md bg-orange-50 p-3 text-sm text-orange-800 dark:bg-orange-500/10 dark:text-orange-300">
          {{ t('backups.restoreWarning', { device: restoreOf?.device_name }) }}
        </p>
        <div class="field">
          <label class="label" for="restore-confirm">{{ t('backups.restoreConfirm', { device: restoreOf?.device_name }) }}</label>
          <input id="restore-confirm" v-model="confirmName" class="input" autocomplete="off" />
        </div>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="restoreOpen = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="restore-form" class="btn btn-danger" :disabled="confirmName !== restoreOf?.device_name">{{ t('backups.restore') }}</button>
      </template>
    </UiDialog>

    <UiDialog v-model:open="diffOpen" wide :title="diffTitle">
      <pre v-if="diffText" class="max-h-[60vh] overflow-auto rounded-md bg-gray-900 p-3 font-mono text-xs leading-relaxed"><span v-for="(line, i) in diffText.split('\n')" :key="i" :class="lineClass(line)">{{ line }}
</span></pre>
      <p v-else class="text-sm text-gray-500">{{ t('backups.noDiff') }}</p>
    </UiDialog>
  </div>
</template>
