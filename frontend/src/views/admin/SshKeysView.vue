<script setup lang="ts">
import { ArrowUpTrayIcon, PlusIcon, TrashIcon } from '@heroicons/vue/20/solid'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Job, type SshKey } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useConfirm, useConfirmDelete } from '@/composables/useConfirm'
import { useJobWatcher } from '@/composables/useJobWatcher'
import { useNotify } from '@/composables/useNotify'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()
const notify = useNotify()
const confirmDelete = useConfirmDelete()
const { confirm } = useConfirm()
const sites = useSitesStore()
const { watch: watchJob } = useJobWatcher()

const keys = ref<SshKey[]>([])
const open = ref(false)
const form = ref({ description: '', key: '' })

async function load(): Promise<void> {
  await notify.run(async () => {
    keys.value = await api.get<SshKey[]>('/ssh-keys')
  })
}

async function add(): Promise<void> {
  if (await notify.run(() => api.post('/ssh-keys', form.value), t('common.saved'))) {
    open.value = false
    form.value = { description: '', key: '' }
    await load()
  }
}

async function remove(key: SshKey): Promise<void> {
  if (await confirmDelete(key.description)) {
    if (await notify.run(() => api.delete(`/ssh-keys/${key.id}`), t('common.deleted'))) await load()
  }
}

async function push(): Promise<void> {
  const ok = await confirm({
    title: t('sshKeys.push'),
    message: `${t('sshKeys.pushHint')} (${sites.current?.name ?? ''})`,
    confirmLabel: t('sshKeys.push'),
    cancelLabel: t('common.cancel'),
    danger: true,
  })
  if (!ok) return
  await notify.run(async () => {
    watchJob(await api.post<Job>('/jobs', { kind: 'ssh_keys', site_id: sites.currentId }))
    notify.success(t('sshKeys.pushed'))
  })
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('sshKeys.title') }}</h1>
        <p class="mt-1 max-w-2xl text-sm text-gray-500 dark:text-gray-400">{{ t('sshKeys.hint') }}</p>
      </div>
      <div class="flex gap-2">
        <button type="button" class="btn btn-secondary" :disabled="keys.length < 2 || !sites.currentId" @click="push">
          <ArrowUpTrayIcon class="size-4" /> {{ t('sshKeys.push') }}
        </button>
        <button type="button" class="btn btn-primary" @click="open = true"><PlusIcon class="size-5" /> {{ t('sshKeys.new') }}</button>
      </div>
    </div>

    <div class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>{{ t('ports.description') }}</th>
            <th>{{ t('sshKeys.fingerprint') }}</th>
            <th>{{ t('audit.time') }}</th>
            <th class="w-10" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="k in keys" :key="k.id">
            <td class="font-medium text-gray-900 dark:text-white">{{ k.description }}<div class="font-mono text-xs text-gray-500">{{ k.key.split(' ')[0] }}</div></td>
            <td class="font-mono text-xs">{{ k.fingerprint }}</td>
            <td class="whitespace-nowrap">{{ formatDateTime(k.created_at, locale) }}</td>
            <td><button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="remove(k)"><TrashIcon class="size-4" /></button></td>
          </tr>
          <tr v-if="!keys.length"><td colspan="4" class="py-8 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>
    </div>

    <UiDialog v-model:open="open" wide :title="t('sshKeys.new')">
      <form id="key-form" class="space-y-4" @submit.prevent="add">
        <div class="field">
          <label class="label" for="k-desc">{{ t('ports.description') }}</label>
          <input id="k-desc" v-model="form.description" class="input" required />
        </div>
        <div class="field">
          <label class="label" for="k-key">{{ t('sshKeys.key') }}</label>
          <textarea id="k-key" v-model="form.key" rows="4" class="input font-mono text-xs" placeholder="ssh-ed25519 AAAA… user@host" required />
        </div>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="key-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
