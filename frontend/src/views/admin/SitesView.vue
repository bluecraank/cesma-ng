<script setup lang="ts">
import { BuildingOffice2Icon, CubeIcon, MapPinIcon } from '@heroicons/vue/24/outline'
import { PencilSquareIcon, PlusIcon, TrashIcon } from '@heroicons/vue/20/solid'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'

const { t } = useI18n()
const notify = useNotify()
const confirmDelete = useConfirmDelete()
const auth = useAuthStore()
const sites = useSitesStore()

/** One dialog for every create/rename: it only needs a title and what to call on submit. */
interface NameDialog {
  title: string
  name: string
  submit: (name: string) => Promise<unknown>
}
const dialog = ref<NameDialog | null>(null)
const dialogOpen = ref(false)

function openDialog(title: string, submit: NameDialog['submit'], name = ''): void {
  dialog.value = { title, name, submit }
  dialogOpen.value = true
}

async function submitDialog(): Promise<void> {
  const d = dialog.value
  if (!d) return
  if (await notify.run(() => d.submit(d.name), t('common.saved'))) {
    dialogOpen.value = false
    await sites.load()
  }
}

async function remove(name: string, path: string): Promise<void> {
  if (!(await confirmDelete(name))) return
  if (await notify.run(() => api.delete(path), t('common.deleted'))) await sites.load()
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="page-title">{{ t('sites.title') }}</h1>
      <button
        v-if="auth.isSuperadmin"
        type="button"
        class="btn btn-primary"
        @click="openDialog(t('sites.newSite'), (name) => api.post('/sites', { name }))"
      >
        <PlusIcon class="size-5" /> {{ t('sites.newSite') }}
      </button>
    </div>

    <div class="grid gap-6 xl:grid-cols-2">
      <section v-for="site in sites.sites" :key="site.id" class="card">
        <header class="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-3 dark:border-white/10">
          <h2 class="flex items-center gap-2 text-base font-semibold">
            <MapPinIcon class="size-5 text-indigo-500" /> {{ site.name }}
          </h2>
          <div v-if="auth.can('devices.manage', site.id)" class="flex items-center gap-1">
            <button type="button" class="btn btn-ghost btn-sm" @click="openDialog(t('sites.newBuilding'), (name) => api.post(`/sites/${site.id}/buildings`, { name }))">
              <PlusIcon class="size-4" /> {{ t('sites.newBuilding') }}
            </button>
            <button type="button" class="btn-icon" :title="t('common.edit')" @click="openDialog(site.name, (name) => api.patch(`/sites/${site.id}`, { name }), site.name)">
              <PencilSquareIcon class="size-4" />
            </button>
            <button v-if="auth.isSuperadmin" type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="remove(site.name, `/sites/${site.id}`)">
              <TrashIcon class="size-4" />
            </button>
          </div>
        </header>

        <ul class="divide-y divide-gray-100 dark:divide-white/5">
          <li v-for="building in site.buildings" :key="building.id" class="px-5 py-3">
            <div class="group flex items-center justify-between gap-3">
              <span class="flex items-center gap-2 text-sm font-medium">
                <BuildingOffice2Icon class="size-5 text-gray-400" /> {{ building.name }}
              </span>
              <div v-if="auth.can('devices.manage', site.id)" class="flex items-center gap-1">
                <button type="button" class="btn btn-ghost btn-sm" @click="openDialog(t('sites.newRoom'), (name) => api.post(`/buildings/${building.id}/rooms`, { name }))">
                  <PlusIcon class="size-4" /> {{ t('sites.newRoom') }}
                </button>
                <button type="button" class="btn-icon" :title="t('common.edit')" @click="openDialog(building.name, (name) => api.patch(`/buildings/${building.id}`, { name }), building.name)">
                  <PencilSquareIcon class="size-4" />
                </button>
                <button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="remove(building.name, `/buildings/${building.id}`)">
                  <TrashIcon class="size-4" />
                </button>
              </div>
            </div>
            <ul class="mt-2 ml-7 space-y-1 border-l border-gray-200 pl-4 dark:border-white/10">
              <li v-for="room in building.rooms" :key="room.id" class="flex items-center justify-between gap-3 text-sm">
                <span class="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                  <CubeIcon class="size-4 text-gray-400" /> {{ room.name }}
                </span>
                <div v-if="auth.can('devices.manage', site.id)" class="flex items-center gap-1">
                  <button type="button" class="btn-icon" :title="t('common.edit')" @click="openDialog(room.name, (name) => api.patch(`/rooms/${room.id}`, { name }), room.name)">
                    <PencilSquareIcon class="size-4" />
                  </button>
                  <button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="remove(room.name, `/rooms/${room.id}`)">
                    <TrashIcon class="size-4" />
                  </button>
                </div>
              </li>
              <li v-if="!building.rooms.length" class="text-sm text-gray-400">—</li>
            </ul>
          </li>
          <li v-if="!site.buildings.length" class="px-5 py-4 text-sm text-gray-400">—</li>
        </ul>
      </section>
    </div>

    <UiDialog v-model:open="dialogOpen" :title="dialog?.title">
      <form v-if="dialog" id="name-form" class="field" @submit.prevent="submitDialog">
        <label class="label" for="name-input">{{ t('common.name') }}</label>
        <input id="name-input" v-model="dialog.name" class="input" autofocus required />
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="dialogOpen = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="name-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
