<script setup lang="ts">
import {
  ArrowDownTrayIcon,
  ArrowPathRoundedSquareIcon,
  ExclamationTriangleIcon,
  PencilSquareIcon,
  PlusIcon,
  TrashIcon,
} from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type ChangePlan, type Job, type PortProfile, type SiteVlan, type SiteVlanIn } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import UiToggle from '@/components/ui/UiToggle.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useJobWatcher } from '@/composables/useJobWatcher'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'

const { t } = useI18n()
const notify = useNotify()
const confirmDelete = useConfirmDelete()
const auth = useAuthStore()
const sites = useSitesStore()

const tab = ref<'vlans' | 'profiles'>('vlans')
const vlans = ref<SiteVlan[]>([])
const profiles = ref<PortProfile[]>([])
const canAdmin = computed(() => auth.canAdmin(sites.currentId))
const base = computed(() => `/sites/${sites.currentId}`)

async function load(): Promise<void> {
  if (sites.currentId === null) return
  await notify.run(async () => {
    ;[vlans.value, profiles.value] = await Promise.all([
      api.get<SiteVlan[]>(`${base.value}/vlans`),
      api.get<PortProfile[]>(`${base.value}/port-profiles`),
    ])
  })
}
watch(() => sites.currentId, load, { immediate: true })

// --- VLAN dialog ---
const vlanOpen = ref(false)
const vlanId = ref<number | null>(null)
const vlanForm = ref<SiteVlanIn>(emptyVlan())
function emptyVlan(): SiteVlanIn {
  return { vid: 2, name: '', description: '', ip_range: null, is_client_vlan: true, scan_enabled: false, sync_enabled: true }
}
function editVlan(v: SiteVlan | null): void {
  vlanId.value = v?.id ?? null
  vlanForm.value = v
    ? { vid: v.vid, name: v.name, description: v.description, ip_range: v.ip_range, is_client_vlan: v.is_client_vlan, scan_enabled: v.scan_enabled, sync_enabled: v.sync_enabled }
    : emptyVlan()
  vlanOpen.value = true
}
async function saveVlan(): Promise<void> {
  const body = { ...vlanForm.value, ip_range: vlanForm.value.ip_range || null }
  const ok = await notify.run(
    () => (vlanId.value ? api.put(`${base.value}/vlans/${vlanId.value}`, body) : api.post(`${base.value}/vlans`, body)),
    t('common.saved'),
  )
  if (ok) {
    vlanOpen.value = false
    await load()
  }
}
async function removeVlan(v: SiteVlan): Promise<void> {
  if (await confirmDelete(`VLAN ${v.vid} ${v.name}`)) {
    if (await notify.run(() => api.delete(`${base.value}/vlans/${v.id}`), t('common.deleted'))) await load()
  }
}
async function importVlans(): Promise<void> {
  await notify.run(async () => {
    const result = await api.post<{ imported: number }>(`${base.value}/vlans/import`)
    notify.success(t('siteVlans.imported', { n: result.imported }))
    await load()
  })
}

// --- Sync ---
const syncOpen = ref(false)
const deleteExtra = ref(false)
const tagUplinks = ref(false)
const plans = ref<ChangePlan[]>([])
const planning = ref(false)
const { job, watch: watchJob } = useJobWatcher(() => load())
const changesTotal = computed(() => plans.value.reduce((n, p) => n + p.operations, 0))

async function planSync(): Promise<void> {
  syncOpen.value = true
  planning.value = true
  await notify.run(async () => {
    plans.value = await api.post<ChangePlan[]>(`${base.value}/vlans/sync/plan`, {
      delete_extra: deleteExtra.value,
      tag_uplinks: tagUplinks.value,
    })
  })
  planning.value = false
}
watch([deleteExtra, tagUplinks], () => syncOpen.value && planSync())

async function startSync(): Promise<void> {
  await notify.run(async () => {
    const started = await api.post<Job>('/jobs', {
      kind: 'vlan_sync',
      site_id: sites.currentId,
      delete_extra: deleteExtra.value,
      tag_uplinks: tagUplinks.value,
    })
    notify.success(t('siteVlans.syncStarted'))
    watchJob(started)
    syncOpen.value = false
  })
}

// --- Port profiles ---
const profileOpen = ref(false)
const profileId = ref<number | null>(null)
const profileForm = ref({ name: '', untagged_vid: null as number | null, tagged: '', description: '' })
function editProfile(p: PortProfile | null): void {
  profileId.value = p?.id ?? null
  profileForm.value = p
    ? { name: p.name, untagged_vid: p.untagged_vid, tagged: p.tagged_vids.join(', '), description: p.description ?? '' }
    : { name: '', untagged_vid: null, tagged: '', description: '' }
  profileOpen.value = true
}
async function saveProfile(): Promise<void> {
  const f = profileForm.value
  const body = {
    name: f.name,
    untagged_vid: f.untagged_vid,
    tagged_vids: f.tagged.split(/[\s,;]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n) && n > 0 && n < 4095),
    description: f.description || null,
  }
  const ok = await notify.run(
    () => (profileId.value ? api.put(`${base.value}/port-profiles/${profileId.value}`, body) : api.post(`${base.value}/port-profiles`, body)),
    t('common.saved'),
  )
  if (ok) {
    profileOpen.value = false
    await load()
  }
}
async function removeProfile(p: PortProfile): Promise<void> {
  if (await confirmDelete(p.name)) {
    if (await notify.run(() => api.delete(`${base.value}/port-profiles/${p.id}`), t('common.deleted'))) await load()
  }
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('siteVlans.title') }}</h1>
        <p class="mt-1 max-w-2xl text-sm text-gray-500 dark:text-gray-400">{{ t('siteVlans.hint') }}</p>
      </div>
      <div v-if="canAdmin && tab === 'vlans'" class="flex flex-wrap gap-2">
        <button type="button" class="btn btn-secondary" @click="importVlans"><ArrowDownTrayIcon class="size-4" /> {{ t('siteVlans.import') }}</button>
        <button type="button" class="btn btn-secondary" @click="planSync"><ArrowPathRoundedSquareIcon class="size-4" /> {{ t('siteVlans.sync') }}</button>
        <button type="button" class="btn btn-primary" @click="editVlan(null)"><PlusIcon class="size-5" /> {{ t('siteVlans.new') }}</button>
      </div>
      <button v-else-if="canAdmin" type="button" class="btn btn-primary" @click="editProfile(null)"><PlusIcon class="size-5" /> {{ t('siteVlans.newProfile') }}</button>
    </div>

    <div v-if="job && (job.status === 'pending' || job.status === 'running')" class="card flex items-center gap-4 p-4">
      <UiSpinner />
      <div class="flex-1">
        <p class="text-sm font-medium">{{ t('jobs.kinds.vlan_sync') }} · {{ t(`jobs.statuses.${job.status}`) }}</p>
        <div class="mt-2 h-1.5 rounded-full bg-gray-100 dark:bg-white/10"><div class="h-1.5 rounded-full bg-indigo-500 transition-all" :style="{ width: `${job.progress}%` }" /></div>
      </div>
    </div>

    <nav class="-mb-px flex gap-6 border-b border-gray-200 dark:border-white/10">
      <button
        v-for="name in (['vlans', 'profiles'] as const)"
        :key="name"
        type="button"
        class="border-b-2 px-1 py-3 text-sm font-medium"
        :class="tab === name ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'"
        @click="tab = name"
      >
        {{ name === 'vlans' ? `${t('siteVlans.title')} (${vlans.length})` : `${t('siteVlans.profiles')} (${profiles.length})` }}
      </button>
    </nav>

    <div v-if="tab === 'vlans'" class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>VID</th>
            <th>{{ t('common.name') }}</th>
            <th>{{ t('siteVlans.ipRange') }}</th>
            <th>{{ t('siteVlans.presence') }}</th>
            <th />
            <th v-if="canAdmin" class="w-20" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in vlans" :key="v.id">
            <td class="font-mono font-medium">{{ v.vid }}</td>
            <td>
              <div class="font-medium text-gray-900 dark:text-white">{{ v.name }}</div>
              <div v-if="v.description" class="text-xs text-gray-500">{{ v.description }}</div>
            </td>
            <td class="font-mono text-xs">{{ v.ip_range ?? '' }}</td>
            <td class="whitespace-nowrap">
              <span class="badge" :class="v.devices_with_vlan === v.device_count ? 'badge-green' : 'badge-yellow'">{{ v.devices_with_vlan }} / {{ v.device_count }}</span>
              <span v-if="v.devices_name_mismatch" class="badge badge-yellow ml-1">{{ t('siteVlans.mismatch', { n: v.devices_name_mismatch }) }}</span>
            </td>
            <td class="space-x-1 whitespace-nowrap">
              <span v-if="v.is_client_vlan" class="badge badge-gray">{{ t('siteVlans.clientVlan') }}</span>
              <span v-if="v.scan_enabled" class="badge badge-blue">{{ t('siteVlans.scan') }}</span>
              <span v-if="!v.sync_enabled" class="badge badge-gray line-through">{{ t('siteVlans.syncEnabled') }}</span>
            </td>
            <td v-if="canAdmin" class="whitespace-nowrap">
              <button type="button" class="btn-icon" :title="t('common.edit')" @click="editVlan(v)"><PencilSquareIcon class="size-4" /></button>
              <button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="removeVlan(v)"><TrashIcon class="size-4" /></button>
            </td>
          </tr>
          <tr v-if="!vlans.length"><td colspan="6" class="py-8 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>
    </div>

    <div v-else class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>{{ t('common.name') }}</th>
            <th>{{ t('siteVlans.untagged') }}</th>
            <th>{{ t('siteVlans.tagged') }}</th>
            <th>{{ t('siteVlans.portDescription') }}</th>
            <th v-if="canAdmin" class="w-20" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in profiles" :key="p.id">
            <td class="font-medium text-gray-900 dark:text-white">{{ p.name }}</td>
            <td class="font-mono">{{ p.untagged_vid ?? '–' }}</td>
            <td class="font-mono text-xs">{{ p.tagged_vids.join(', ') }}</td>
            <td>{{ p.description ?? '' }}</td>
            <td v-if="canAdmin" class="whitespace-nowrap">
              <button type="button" class="btn-icon" :title="t('common.edit')" @click="editProfile(p)"><PencilSquareIcon class="size-4" /></button>
              <button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="removeProfile(p)"><TrashIcon class="size-4" /></button>
            </td>
          </tr>
          <tr v-if="!profiles.length"><td colspan="5" class="py-8 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>
    </div>

    <UiDialog v-model:open="vlanOpen" :title="vlanId ? `VLAN ${vlanForm.vid}` : t('siteVlans.new')">
      <form id="vlan-form" class="grid gap-4 sm:grid-cols-3" @submit.prevent="saveVlan">
        <div class="field">
          <label class="label" for="v-vid">VID</label>
          <input id="v-vid" v-model.number="vlanForm.vid" type="number" min="1" max="4094" class="input" required />
        </div>
        <div class="field sm:col-span-2">
          <label class="label" for="v-name">{{ t('common.name') }}</label>
          <input id="v-name" v-model="vlanForm.name" class="input" maxlength="32" required />
        </div>
        <div class="field sm:col-span-3">
          <label class="label" for="v-desc">{{ t('ports.description') }}</label>
          <input id="v-desc" v-model="vlanForm.description" class="input" />
        </div>
        <div class="field sm:col-span-3">
          <label class="label" for="v-ip">{{ t('siteVlans.ipRange') }}</label>
          <input id="v-ip" v-model="vlanForm.ip_range" class="input font-mono" placeholder="10.1.20.0/24" />
        </div>
        <div class="flex flex-wrap gap-6 sm:col-span-3">
          <UiToggle v-model="vlanForm.sync_enabled" :label="t('siteVlans.syncEnabled')" />
          <UiToggle v-model="vlanForm.is_client_vlan" :label="t('siteVlans.clientVlan')" />
          <UiToggle v-model="vlanForm.scan_enabled" :label="t('siteVlans.scan')" />
        </div>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="vlanOpen = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="vlan-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>

    <UiDialog v-model:open="syncOpen" wide :title="t('siteVlans.sync')">
      <div class="space-y-4">
        <label class="flex items-start gap-2 text-sm">
          <input v-model="tagUplinks" type="checkbox" class="mt-0.5 accent-orange-600" />
          <span><span class="font-medium">{{ t('siteVlans.tagUplinks') }}</span><br /><span class="text-gray-500">{{ t('siteVlans.tagUplinksHint') }}</span></span>
        </label>
        <label class="flex items-start gap-2 text-sm">
          <input v-model="deleteExtra" type="checkbox" class="mt-0.5 accent-red-600" />
          <span><span class="font-medium">{{ t('siteVlans.deleteExtra') }}</span><br /><span class="text-gray-500">{{ t('siteVlans.deleteExtraHint') }}</span></span>
        </label>
        <div v-if="planning" class="flex justify-center py-6"><UiSpinner /></div>
        <p v-else-if="!changesTotal" class="rounded-md bg-green-50 p-3 text-sm text-green-800 dark:bg-green-500/10 dark:text-green-300">{{ t('siteVlans.allInSync') }}</p>
        <template v-else>
          <section v-for="p in plans.filter((x) => x.operations || x.warnings.length)" :key="p.device_id">
            <h3 class="text-sm font-semibold">{{ p.device_name }} <span class="font-normal text-gray-500">· {{ p.operations }}</span></h3>
            <p v-for="w in p.warnings" :key="w" class="mt-1 flex gap-1.5 text-xs text-yellow-700 dark:text-yellow-400"><ExclamationTriangleIcon class="size-4" /> {{ w }}</p>
            <pre v-if="p.commands.length" class="mt-1.5 max-h-40 overflow-auto rounded-md bg-gray-900 p-3 font-mono text-xs text-green-300">{{ p.commands.join('\n') }}</pre>
          </section>
        </template>
      </div>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="syncOpen = false">{{ t('common.cancel') }}</button>
        <button type="button" class="btn" :class="deleteExtra || tagUplinks ? 'btn-danger' : 'btn-primary'" :disabled="planning || !changesTotal" @click="startSync">
          {{ t('siteVlans.syncStart') }}
        </button>
      </template>
    </UiDialog>

    <UiDialog v-model:open="profileOpen" :title="profileId ? profileForm.name : t('siteVlans.newProfile')">
      <form id="profile-form" class="space-y-4" @submit.prevent="saveProfile">
        <div class="field">
          <label class="label" for="pp-name">{{ t('common.name') }}</label>
          <input id="pp-name" v-model="profileForm.name" class="input" required />
        </div>
        <div class="field">
          <label class="label" for="pp-untagged">{{ t('siteVlans.untagged') }}</label>
          <select id="pp-untagged" v-model="profileForm.untagged_vid" class="input">
            <option :value="null">{{ t('change.none') }}</option>
            <option v-for="v in vlans" :key="v.vid" :value="v.vid">{{ v.vid }} {{ v.name }}</option>
          </select>
        </div>
        <div class="field">
          <label class="label" for="pp-tagged">{{ t('siteVlans.tagged') }}</label>
          <input id="pp-tagged" v-model="profileForm.tagged" class="input font-mono" />
          <p class="hint">{{ t('siteVlans.taggedHint') }}</p>
        </div>
        <div class="field">
          <label class="label" for="pp-desc">{{ t('siteVlans.portDescription') }}</label>
          <input id="pp-desc" v-model="profileForm.description" class="input" />
        </div>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="profileOpen = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="profile-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
