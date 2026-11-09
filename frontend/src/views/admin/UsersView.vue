<script setup lang="ts">
import { PencilSquareIcon } from '@heroicons/vue/20/solid'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Role, type User } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiToggle from '@/components/ui/UiToggle.vue'
import { useNotify } from '@/composables/useNotify'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()

const users = ref<User[]>([])
const editing = ref<User | null>(null)
const dialogOpen = ref(false)
const roles = ref<Role[]>([])
const form = ref({ is_superadmin: false, is_active: true, roles: {} as Record<number, number | ''>, password: '', clearPassword: false })

function siteName(id: number): string {
  return sites.sites.find((s) => s.id === id)?.name ?? `#${id}`
}

async function load(): Promise<void> {
  await notify.run(async () => {
    ;[users.value, roles.value] = await Promise.all([api.get<User[]>('/users'), api.get<Role[]>('/roles')])
  })
}

function edit(user: User): void {
  editing.value = user
  form.value = {
    is_superadmin: user.is_superadmin,
    is_active: user.is_active,
    roles: Object.fromEntries(sites.sites.map((s) => [s.id, user.site_roles.find((r) => r.site_id === s.id)?.role_id ?? ''])),
    password: '',
    clearPassword: false,
  }
  dialogOpen.value = true
}

async function save(): Promise<void> {
  const user = editing.value
  if (!user) return
  const site_roles = Object.fromEntries(Object.entries(form.value.roles).filter(([, role]) => role !== ''))
  const body: Record<string, unknown> = { is_superadmin: form.value.is_superadmin, is_active: form.value.is_active, site_roles }
  if (form.value.password) body.local_password = form.value.password
  else if (form.value.clearPassword) body.local_password = ''
  const ok = await notify.run(() => api.patch(`/users/${user.id}`, body), t('common.saved'))
  if (ok) {
    dialogOpen.value = false
    await load()
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <h1 class="page-title">{{ t('users.title') }}</h1>

    <div class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>{{ t('users.username') }}</th>
            <th>{{ t('users.siteRoles') }}</th>
            <th>{{ t('users.active') }}</th>
            <th>{{ t('users.lastLogin') }}</th>
            <th class="w-10"><span class="sr-only">{{ t('common.actions') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>
              <div class="font-medium text-gray-900 dark:text-white">{{ u.display_name || u.username }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ u.username }}<template v-if="u.email"> · {{ u.email }}</template></div>
              <span v-if="u.has_local_password" class="badge badge-yellow mt-1" :title="t('users.emergencyHint')">{{ t('users.emergency') }}</span>
            </td>
            <td>
              <span v-if="u.is_superadmin" class="badge badge-indigo">{{ t('users.superadmin') }}</span>
              <div v-else class="flex flex-wrap gap-1">
                <span v-for="r in u.site_roles" :key="r.site_id" class="badge" :class="r.permissions.length ? 'badge-blue' : 'badge-gray'">
                  {{ siteName(r.site_id) }}: {{ r.role_name }}
                </span>
                <span v-if="!u.site_roles.length" class="text-gray-400">{{ t('users.noAccess') }}</span>
              </div>
            </td>
            <td>
              <span class="badge" :class="u.is_active ? 'badge-green' : 'badge-gray'">{{ u.is_active ? t('common.yes') : t('common.no') }}</span>
            </td>
            <td class="whitespace-nowrap tabular-nums">{{ formatDateTime(u.last_login_at, locale) }}</td>
            <td>
              <button type="button" class="btn-icon" :title="t('common.edit')" @click="edit(u)">
                <PencilSquareIcon class="size-4" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <UiDialog v-model:open="dialogOpen" :title="editing?.display_name || editing?.username">
      <form id="user-form" class="space-y-5" @submit.prevent="save">
        <UiToggle v-model="form.is_superadmin" :label="t('users.superadmin')" />
        <UiToggle v-model="form.is_active" :label="t('users.active')" />
        <div v-if="!form.is_superadmin" class="space-y-3">
          <h3 class="text-sm font-semibold">{{ t('users.siteRoles') }}</h3>
          <div v-for="site in sites.sites" :key="site.id" class="flex items-center justify-between gap-4">
            <label class="text-sm" :for="`role-${site.id}`">{{ site.name }}</label>
            <select :id="`role-${site.id}`" v-model="form.roles[site.id]" class="input w-48">
              <option value="">{{ t('users.noAccess') }}</option>
              <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
          </div>
          <RouterLink :to="{ name: 'admin-roles' }" class="link text-xs">{{ t('users.manageRoles') }}</RouterLink>
        </div>
        <div class="space-y-2 border-t border-gray-200 pt-4 dark:border-white/10">
          <h3 class="text-sm font-semibold">{{ t('users.emergency') }}</h3>
          <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('users.emergencyHint') }}</p>
          <input
            v-model="form.password"
            type="password"
            class="input"
            autocomplete="new-password"
            minlength="12"
            :placeholder="editing?.has_local_password ? t('users.emergencyKeep') : t('users.emergencyNew')"
          />
          <label v-if="editing?.has_local_password" class="flex items-center gap-2 text-sm">
            <input v-model="form.clearPassword" type="checkbox" class="accent-indigo-600" :disabled="!!form.password" /> {{ t('users.emergencyRemove') }}
          </label>
        </div>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="dialogOpen = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="user-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
