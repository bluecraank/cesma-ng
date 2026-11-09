<script setup lang="ts">
import { PencilSquareIcon, PlusIcon, TrashIcon } from '@heroicons/vue/20/solid'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type CredentialProfile, type Gateway } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiToggle from '@/components/ui/UiToggle.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useNotify } from '@/composables/useNotify'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()
const notify = useNotify()
const confirmDelete = useConfirmDelete()

const gateways = ref<Gateway[]>([])
const profiles = ref<CredentialProfile[]>([])
const open = ref(false)
const editingId = ref<number | null>(null)
const form = ref({ name: '', hostname: '', credential_profile_id: null as number | null, enabled: true })

async function load(): Promise<void> {
  await notify.run(async () => {
    ;[gateways.value, profiles.value] = await Promise.all([
      api.get<Gateway[]>('/gateways'),
      api.get<CredentialProfile[]>('/credential-profiles'),
    ])
  })
}

function edit(g: Gateway | null): void {
  editingId.value = g?.id ?? null
  form.value = g
    ? { name: g.name, hostname: g.hostname, credential_profile_id: g.credential_profile_id, enabled: g.enabled }
    : { name: '', hostname: '', credential_profile_id: null, enabled: true }
  open.value = true
}

async function save(): Promise<void> {
  const ok = await notify.run(
    () => (editingId.value ? api.put(`/gateways/${editingId.value}`, form.value) : api.post('/gateways', form.value)),
    t('common.saved'),
  )
  if (ok) {
    open.value = false
    await load()
  }
}

async function remove(g: Gateway): Promise<void> {
  if (await confirmDelete(g.name)) {
    if (await notify.run(() => api.delete(`/gateways/${g.id}`), t('common.deleted'))) await load()
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('gateways.title') }}</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t('gateways.hint') }}</p>
      </div>
      <button type="button" class="btn btn-primary" @click="edit(null)"><PlusIcon class="size-5" /> {{ t('gateways.new') }}</button>
    </div>

    <div class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>{{ t('common.name') }}</th>
            <th>{{ t('device.hostname') }}</th>
            <th>{{ t('gateways.enabled') }}</th>
            <th class="text-right">{{ t('gateways.entries') }}</th>
            <th>{{ t('gateways.lastPolled') }}</th>
            <th class="w-20"><span class="sr-only">{{ t('common.actions') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in gateways" :key="g.id">
            <td class="font-medium text-gray-900 dark:text-white">{{ g.name }}</td>
            <td class="font-mono text-xs">{{ g.hostname }}</td>
            <td><span class="badge" :class="g.enabled ? 'badge-green' : 'badge-gray'">{{ g.enabled ? t('common.yes') : t('common.no') }}</span></td>
            <td class="text-right tabular-nums">{{ g.entries }}</td>
            <td class="whitespace-nowrap">
              {{ formatDateTime(g.last_polled_at, locale) }}
              <p v-if="g.last_error" class="text-xs text-red-600 dark:text-red-400">{{ g.last_error }}</p>
            </td>
            <td class="whitespace-nowrap">
              <button type="button" class="btn-icon" :title="t('common.edit')" @click="edit(g)"><PencilSquareIcon class="size-4" /></button>
              <button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="remove(g)"><TrashIcon class="size-4" /></button>
            </td>
          </tr>
          <tr v-if="!gateways.length"><td colspan="6" class="py-8 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>
    </div>

    <UiDialog v-model:open="open" :title="editingId ? form.name : t('gateways.new')">
      <form id="gw-form" class="space-y-4" @submit.prevent="save">
        <div class="field">
          <label class="label" for="gw-name">{{ t('common.name') }}</label>
          <input id="gw-name" v-model="form.name" class="input" required />
        </div>
        <div class="field">
          <label class="label" for="gw-host">{{ t('device.hostname') }}</label>
          <input id="gw-host" v-model="form.hostname" class="input font-mono" required />
        </div>
        <div class="field">
          <label class="label" for="gw-cred">{{ t('device.credentials') }}</label>
          <select id="gw-cred" v-model="form.credential_profile_id" class="input">
            <option :value="null">{{ t('common.none') }}</option>
            <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <UiToggle v-model="form.enabled" :label="t('gateways.enabled')" />
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="gw-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
