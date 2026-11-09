<script setup lang="ts">
import { CloudArrowUpIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Backup, type Job } from '@/api/client'
import BackupList from '@/components/BackupList.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useJobWatcher } from '@/composables/useJobWatcher'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'

const { t } = useI18n()
const notify = useNotify()
const auth = useAuthStore()
const sites = useSitesStore()
const backups = ref<Backup[]>([])
const canRun = computed(() => auth.can('backups.run', sites.currentId))
const { job, watch: watchJob } = useJobWatcher(() => load())

async function load(): Promise<void> {
  if (sites.currentId === null) return
  await notify.run(async () => {
    backups.value = await api.get<Backup[]>('/backups', { site_id: sites.currentId })
  })
}

async function backupNow(): Promise<void> {
  await notify.run(async () => {
    watchJob(await api.post<Job>('/jobs', { kind: 'backup', site_id: sites.currentId }))
    notify.success(t('backups.started'))
  })
}

watch(() => sites.currentId, load, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="page-title">{{ t('backups.title') }}</h1>
      <button v-if="canRun" type="button" class="btn btn-primary" :disabled="job?.status === 'running' || job?.status === 'pending'" @click="backupNow">
        <UiSpinner v-if="job?.status === 'running' || job?.status === 'pending'" />
        <CloudArrowUpIcon v-else class="size-4" />
        {{ t('backups.now') }}
      </button>
    </div>
    <BackupList :backups="backups" show-device />
  </div>
</template>
