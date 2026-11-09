<script setup lang="ts">
import { PencilSquareIcon, PlusIcon, TrashIcon } from '@heroicons/vue/20/solid'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type CredentialProfile, type CredentialProfileIn } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiToggle from '@/components/ui/UiToggle.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useNotify } from '@/composables/useNotify'

const { t } = useI18n()
const notify = useNotify()
const confirmDelete = useConfirmDelete()

const SECRET_KEYS = [
  'snmp_community',
  'snmp_v3_auth_password',
  'snmp_v3_priv_password',
  'api_password',
  'ssh_password',
  'ssh_private_key',
  'enable_password',
] as const

const profiles = ref<CredentialProfile[]>([])
const editingId = ref<number | null>(null)
const open = ref(false)
const form = ref<CredentialProfileIn>(emptyForm())

function emptyForm(): CredentialProfileIn {
  return { name: '', snmp_version: 'v2c', verify_tls: false, api_https: true }
}

async function load(): Promise<void> {
  await notify.run(async () => {
    profiles.value = await api.get<CredentialProfile[]>('/credential-profiles')
  })
}

function edit(profile: CredentialProfile | null): void {
  editingId.value = profile?.id ?? null
  form.value = profile
    ? {
        name: profile.name,
        snmp_version: profile.snmp_version,
        snmp_v3_username: profile.snmp_v3_username,
        snmp_v3_auth_protocol: profile.snmp_v3_auth_protocol,
        snmp_v3_priv_protocol: profile.snmp_v3_priv_protocol,
        api_username: profile.api_username,
        ssh_username: profile.ssh_username,
        verify_tls: profile.verify_tls,
        api_https: profile.api_https,
      }
    : emptyForm()
  open.value = true
}

/** Empty secret inputs mean "unchanged" in this form, so they are not sent. */
function payload(): CredentialProfileIn {
  const body: Record<string, unknown> = { ...form.value }
  for (const key of SECRET_KEYS) if (!body[key]) delete body[key]
  return body as CredentialProfileIn
}

async function save(): Promise<void> {
  const ok = await notify.run(
    () =>
      editingId.value === null
        ? api.post('/credential-profiles', payload())
        : api.put(`/credential-profiles/${editingId.value}`, payload()),
    t('common.saved'),
  )
  if (ok) {
    open.value = false
    await load()
  }
}

async function remove(profile: CredentialProfile): Promise<void> {
  if (!(await confirmDelete(profile.name))) return
  if (await notify.run(() => api.delete(`/credential-profiles/${profile.id}`), t('common.deleted'))) await load()
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="page-title">{{ t('credentials.title') }}</h1>
      <button type="button" class="btn btn-primary" @click="edit(null)">
        <PlusIcon class="size-5" /> {{ t('credentials.new') }}
      </button>
    </div>

    <div class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>{{ t('common.name') }}</th>
            <th>{{ t('credentials.snmp') }}</th>
            <th>{{ t('credentials.api') }}</th>
            <th>{{ t('credentials.ssh') }}</th>
            <th>{{ t('credentials.secretsSet') }}</th>
            <th class="w-20"><span class="sr-only">{{ t('common.actions') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in profiles" :key="p.id">
            <td class="font-medium text-gray-900 dark:text-white">{{ p.name }}</td>
            <td><span class="badge badge-gray">{{ p.snmp_version }}</span></td>
            <td>{{ p.api_username || '—' }}</td>
            <td>{{ p.ssh_username || '—' }}</td>
            <td>
              <div class="flex flex-wrap gap-1">
                <span v-for="s in p.secrets_set" :key="s" class="badge badge-gray font-mono">{{ s }}</span>
              </div>
            </td>
            <td class="whitespace-nowrap">
              <button type="button" class="btn-icon" :title="t('common.edit')" @click="edit(p)"><PencilSquareIcon class="size-4" /></button>
              <button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="remove(p)"><TrashIcon class="size-4" /></button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <UiDialog v-model:open="open" wide :title="form.name || t('credentials.new')">
      <form id="cred-form" class="space-y-6" autocomplete="off" @submit.prevent="save">
        <div class="field">
          <label class="label" for="c-name">{{ t('common.name') }}</label>
          <input id="c-name" v-model="form.name" class="input" required />
        </div>

        <fieldset class="space-y-4 rounded-lg border border-gray-200 p-4 dark:border-white/10">
          <legend class="px-1 text-sm font-semibold">{{ t('credentials.snmp') }}</legend>
          <div class="inline-flex rounded-md shadow-xs">
            <button
              v-for="v in ['v2c', 'v3'] as const"
              :key="v"
              type="button"
              class="px-3 py-1.5 text-sm font-semibold ring-1 ring-gray-300 ring-inset first:rounded-l-md last:rounded-r-md dark:ring-white/10"
              :class="form.snmp_version === v ? 'bg-indigo-600 text-white ring-indigo-600' : 'bg-white text-gray-900 hover:bg-gray-50 dark:bg-white/5 dark:text-white'"
              @click="form.snmp_version = v"
            >
              {{ v }}
            </button>
          </div>
          <div v-if="form.snmp_version === 'v2c'" class="field">
            <label class="label" for="c-comm">{{ t('credentials.community') }}</label>
            <input id="c-comm" v-model="form.snmp_community" type="password" class="input" :placeholder="t('credentials.secretHint')" />
          </div>
          <div v-else class="grid gap-4 sm:grid-cols-2">
            <div class="field sm:col-span-2">
              <label class="label" for="c-v3u">{{ t('credentials.username') }}</label>
              <input id="c-v3u" v-model="form.snmp_v3_username" class="input" />
            </div>
            <div class="field">
              <label class="label" for="c-ap">{{ t('credentials.authProtocol') }}</label>
              <select id="c-ap" v-model="form.snmp_v3_auth_protocol" class="input">
                <option v-for="o in ['SHA', 'SHA256', 'SHA512', 'MD5']" :key="o" :value="o">{{ o }}</option>
              </select>
            </div>
            <div class="field">
              <label class="label" for="c-apw">{{ t('credentials.authPassword') }}</label>
              <input id="c-apw" v-model="form.snmp_v3_auth_password" type="password" class="input" :placeholder="t('credentials.secretHint')" />
            </div>
            <div class="field">
              <label class="label" for="c-pp">{{ t('credentials.privProtocol') }}</label>
              <select id="c-pp" v-model="form.snmp_v3_priv_protocol" class="input">
                <option v-for="o in ['AES', 'AES256', 'DES']" :key="o" :value="o">{{ o }}</option>
              </select>
            </div>
            <div class="field">
              <label class="label" for="c-ppw">{{ t('credentials.privPassword') }}</label>
              <input id="c-ppw" v-model="form.snmp_v3_priv_password" type="password" class="input" :placeholder="t('credentials.secretHint')" />
            </div>
          </div>
        </fieldset>

        <fieldset class="grid gap-4 rounded-lg border border-gray-200 p-4 sm:grid-cols-2 dark:border-white/10">
          <legend class="px-1 text-sm font-semibold">{{ t('credentials.api') }}</legend>
          <div class="field">
            <label class="label" for="c-au">{{ t('credentials.username') }}</label>
            <input id="c-au" v-model="form.api_username" class="input" />
          </div>
          <div class="field">
            <label class="label" for="c-apw2">{{ t('credentials.password') }}</label>
            <input id="c-apw2" v-model="form.api_password" type="password" class="input" :placeholder="t('credentials.secretHint')" />
          </div>
          <div class="flex flex-wrap gap-6 sm:col-span-2">
            <UiToggle v-model="form.api_https" :label="t('credentials.apiHttps')" />
            <UiToggle v-model="form.verify_tls" :label="t('credentials.verifyTls')" />
          </div>
        </fieldset>

        <fieldset class="grid gap-4 rounded-lg border border-gray-200 p-4 sm:grid-cols-2 dark:border-white/10">
          <legend class="px-1 text-sm font-semibold">{{ t('credentials.ssh') }}</legend>
          <div class="field">
            <label class="label" for="c-su">{{ t('credentials.username') }}</label>
            <input id="c-su" v-model="form.ssh_username" class="input" />
          </div>
          <div class="field">
            <label class="label" for="c-spw">{{ t('credentials.password') }}</label>
            <input id="c-spw" v-model="form.ssh_password" type="password" class="input" :placeholder="t('credentials.secretHint')" />
          </div>
          <div class="field sm:col-span-2">
            <label class="label" for="c-en">{{ t('credentials.enablePassword') }}</label>
            <input id="c-en" v-model="form.enable_password" type="password" class="input" :placeholder="t('credentials.secretHint')" />
          </div>
          <div class="field sm:col-span-2">
            <label class="label" for="c-key">{{ t('credentials.privateKey') }}</label>
            <textarea id="c-key" v-model="form.ssh_private_key" rows="3" class="input font-mono text-xs" :placeholder="t('credentials.secretHint')" />
          </div>
        </fieldset>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="cred-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
