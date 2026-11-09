<script setup lang="ts">
import { PencilSquareIcon, PlusIcon, TrashIcon } from '@heroicons/vue/20/solid'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type MacType } from '@/api/client'
import MacTypeIcon from '@/components/MacTypeIcon.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useNotify } from '@/composables/useNotify'
import { MAC_TYPE_ICONS } from '@/utils/macTypeIcons'

const { t } = useI18n()
const notify = useNotify()
const confirmDelete = useConfirmDelete()

const types = ref<MacType[]>([])
const open = ref(false)
const editingId = ref<number | null>(null)
const form = ref({ prefix: '', name: '', icon: 'device' })

async function load(): Promise<void> {
  await notify.run(async () => {
    types.value = await api.get<MacType[]>('/mac-types')
  })
}

function edit(type: MacType | null): void {
  editingId.value = type?.id ?? null
  form.value = type ? { prefix: type.prefix, name: type.name, icon: type.icon } : { prefix: '', name: '', icon: 'device' }
  open.value = true
}

async function save(): Promise<void> {
  const ok = await notify.run(
    () => (editingId.value ? api.put(`/mac-types/${editingId.value}`, form.value) : api.post('/mac-types', form.value)),
    t('common.saved'),
  )
  if (ok) {
    open.value = false
    await load()
  }
}

async function remove(type: MacType): Promise<void> {
  if (await confirmDelete(`${type.prefix} ${type.name}`)) {
    if (await notify.run(() => api.delete(`/mac-types/${type.id}`), t('common.deleted'))) await load()
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="page-title">{{ t('macTypes.title') }}</h1>
      <button type="button" class="btn btn-primary" @click="edit(null)"><PlusIcon class="size-5" /> {{ t('macTypes.new') }}</button>
    </div>

    <div class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>{{ t('macTypes.prefix') }}</th>
            <th>{{ t('common.name') }}</th>
            <th>{{ t('macTypes.icon') }}</th>
            <th class="w-20"><span class="sr-only">{{ t('common.actions') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="mt in types" :key="mt.id">
            <td class="font-mono">{{ mt.prefix }}</td>
            <td class="font-medium text-gray-900 dark:text-white">{{ mt.name }}</td>
            <td><MacTypeIcon :icon="mt.icon" /></td>
            <td class="whitespace-nowrap">
              <button type="button" class="btn-icon" :title="t('common.edit')" @click="edit(mt)"><PencilSquareIcon class="size-4" /></button>
              <button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="remove(mt)"><TrashIcon class="size-4" /></button>
            </td>
          </tr>
          <tr v-if="!types.length"><td colspan="4" class="py-8 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>
    </div>

    <UiDialog v-model:open="open" :title="editingId ? form.name : t('macTypes.new')">
      <form id="mactype-form" class="space-y-4" @submit.prevent="save">
        <div class="field">
          <label class="label" for="mt-prefix">{{ t('macTypes.prefix') }}</label>
          <input id="mt-prefix" v-model="form.prefix" class="input font-mono" required />
          <p class="hint">{{ t('macTypes.prefixHint') }}</p>
        </div>
        <div class="field">
          <label class="label" for="mt-name">{{ t('common.name') }}</label>
          <input id="mt-name" v-model="form.name" class="input" required />
        </div>
        <div class="field">
          <span class="label">{{ t('macTypes.icon') }}</span>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="(icon, name) in MAC_TYPE_ICONS"
              :key="name"
              type="button"
              class="rounded-md p-2 ring-1"
              :class="form.icon === name ? 'bg-indigo-50 ring-indigo-500 dark:bg-indigo-500/10' : 'ring-gray-200 hover:bg-gray-50 dark:ring-white/10 dark:hover:bg-white/5'"
              :title="name"
              @click="form.icon = name"
            >
              <component :is="icon" class="size-5 text-indigo-500" />
            </button>
          </div>
        </div>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="mactype-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
