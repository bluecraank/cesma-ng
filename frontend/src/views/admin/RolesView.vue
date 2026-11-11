<script setup lang="ts">
import { CheckIcon, PencilSquareIcon, PlusIcon, TrashIcon } from '@heroicons/vue/20/solid'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Permission, type Role } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useNotify } from '@/composables/useNotify'

/** Order and grouping of the permissions in the matrix. */
const GROUPS: { key: string; permissions: Permission[] }[] = [
  { key: 'devices', permissions: ['devices.manage', 'ports.edit', 'vlans.manage'] },
  { key: 'backups', permissions: ['backups.run', 'backups.read', 'backups.restore'] },
  { key: 'access', permissions: ['console', 'ssh_keys.push'] },
]

const { t } = useI18n()
const notify = useNotify()
const confirmDelete = useConfirmDelete()

const roles = ref<Role[]>([])
const open = ref(false)
const editing = ref<Role | null>(null)
const form = ref({ name: '', description: '', permissions: [] as Permission[] })

async function load(): Promise<void> {
  await notify.run(async () => {
    roles.value = await api.get<Role[]>('/roles')
  })
}

function edit(role: Role | null): void {
  editing.value = role
  form.value = {
    name: role?.name ?? '',
    description: role?.description ?? '',
    permissions: [...((role?.permissions ?? []) as Permission[])],
  }
  open.value = true
}

function togglePermission(permission: Permission): void {
  const list = form.value.permissions
  form.value.permissions = list.includes(permission) ? list.filter((p) => p !== permission) : [...list, permission]
}

async function save(): Promise<void> {
  const role = editing.value
  const ok = await notify.run(
    () => (role ? api.put(`/roles/${role.id}`, form.value) : api.post('/roles', form.value)),
    t('common.saved'),
  )
  if (ok) {
    open.value = false
    await load()
  }
}

async function remove(role: Role): Promise<void> {
  if (await confirmDelete(role.name)) {
    if (await notify.run(() => api.delete(`/roles/${role.id}`), t('common.deleted'))) await load()
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('roles.title') }}</h1>
        <p class="mt-1 max-w-2xl text-sm text-gray-500 dark:text-gray-400">{{ t('roles.hint') }}</p>
      </div>
      <button type="button" class="btn btn-primary" @click="edit(null)"><PlusIcon class="size-5" /> {{ t('roles.new') }}</button>
    </div>

    <!-- Matrix: one column per role, one row per permission -->
    <div class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>{{ t('roles.permission') }}</th>
            <th v-for="r in roles" :key="r.id" class="text-center">
              <div class="flex items-center justify-center gap-1">
                <span>{{ r.name }}</span>
                <button type="button" class="btn-icon" :title="t('common.edit')" @click="edit(r)"><PencilSquareIcon class="size-4" /></button>
                <button v-if="!r.builtin" type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="remove(r)">
                  <TrashIcon class="size-4" />
                </button>
              </div>
              <div class="text-xs font-normal text-gray-500 normal-case">{{ r.description }}</div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <div class="font-medium text-gray-900 dark:text-white">{{ t('roles.perm.view') }}</div>
              <div class="text-xs text-gray-500">{{ t('roles.permHint.view') }}</div>
            </td>
            <td v-for="r in roles" :key="r.id" class="text-center"><CheckIcon class="mx-auto size-5 text-green-600" /></td>
          </tr>
          <template v-for="g in GROUPS" :key="g.key">
            <tr v-for="p in g.permissions" :key="p">
              <td>
                <div class="font-medium text-gray-900 dark:text-white">{{ t(`roles.perm.${p}`) }}</div>
                <div class="text-xs text-gray-500">{{ t(`roles.permHint.${p}`) }}</div>
              </td>
              <td v-for="r in roles" :key="r.id" class="text-center">
                <CheckIcon v-if="r.permissions.includes(p)" class="mx-auto size-5 text-green-600" />
                <span v-else class="text-gray-300 dark:text-gray-600">—</span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <UiDialog v-model:open="open" wide :title="editing ? editing.name : t('roles.new')">
      <form id="role-form" class="space-y-5" @submit.prevent="save">
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="field">
            <label class="label" for="r-name">{{ t('roles.name') }}</label>
            <input id="r-name" v-model="form.name" class="input" required maxlength="100" />
          </div>
          <div class="field">
            <label class="label" for="r-desc">{{ t('ports.description') }}</label>
            <input id="r-desc" v-model="form.description" class="input" maxlength="255" />
          </div>
        </div>
        <fieldset v-for="g in GROUPS" :key="g.key" class="space-y-2">
          <legend class="label mb-1">{{ t(`roles.group.${g.key}`) }}</legend>
          <label v-for="p in g.permissions" :key="p" class="flex cursor-pointer items-start gap-3 rounded-md p-2 hover:bg-gray-50 dark:hover:bg-white/5">
            <input type="checkbox" class="mt-0.5 accent-brand-600" :checked="form.permissions.includes(p)" @change="togglePermission(p)" />
            <span>
              <span class="block text-sm font-medium">{{ t(`roles.perm.${p}`) }}</span>
              <span class="block text-xs text-gray-500">{{ t(`roles.permHint.${p}`) }}</span>
            </span>
          </label>
        </fieldset>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="role-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
