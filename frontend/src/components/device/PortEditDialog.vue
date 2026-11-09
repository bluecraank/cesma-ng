<script setup lang="ts">
import { ExclamationTriangleIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type ApplyResult, type ChangePlan, type DeviceVlan, type Port, type PortProfile } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useNotify } from '@/composables/useNotify'

const props = defineProps<{ deviceId: number; siteId: number; ports: Port[]; vlans: DeviceVlan[] }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ applied: [] }>()

const { t } = useI18n()
const notify = useNotify()

type Tri = 'keep' | 'on' | 'off'
const profiles = ref<PortProfile[]>([])
const profileId = ref<number | null>(null)
const description = ref('')
const enabled = ref<Tri>('keep')
const editVlans = ref(false)
const untagged = ref<number | null>(null)
const tagged = ref<number[]>([])
const plan = ref<ChangePlan | null>(null)
const busy = ref(false)

const single = computed(() => (props.ports.length === 1 ? props.ports[0] : null))
const title = computed(() =>
  single.value ? `${t('ports.port')} ${single.value.name}` : t('change.editPorts', { n: props.ports.length }),
)

watch(open, async (isOpen) => {
  if (!isOpen) return
  plan.value = null
  profileId.value = null
  enabled.value = 'keep'
  description.value = single.value?.description ?? ''
  editVlans.value = false
  untagged.value = single.value?.untagged_vlans[0] ?? null
  tagged.value = [...(single.value?.tagged_vlans ?? [])]
  profiles.value = await api.get<PortProfile[]>(`/sites/${props.siteId}/port-profiles`).catch(() => [])
})

// Any edit invalidates the preview.
watch([profileId, description, enabled, editVlans, untagged, tagged], () => (plan.value = null), { deep: true })

function body(): Record<string, unknown> {
  const data: Record<string, unknown> = { port_ids: props.ports.map((p) => p.id) }
  if (enabled.value !== 'keep') data.enabled = enabled.value === 'on'
  if (profileId.value !== null) return { ...data, profile_id: profileId.value }
  if (single.value && description.value !== single.value.description) data.description = description.value
  if (editVlans.value) {
    if (untagged.value === null) data.clear_untagged = true
    else data.untagged = untagged.value
    data.tagged = tagged.value
  }
  return data
}

async function preview(): Promise<void> {
  busy.value = true
  await notify.run(async () => {
    plan.value = await api.post<ChangePlan>(`/devices/${props.deviceId}/ports/plan`, body())
  })
  busy.value = false
}

async function apply(): Promise<void> {
  busy.value = true
  const ok = await notify.run(async () => {
    const result = await api.post<ApplyResult>(`/devices/${props.deviceId}/ports/apply`, body())
    const simulated = result.log.some((line) => line.startsWith('[simulated]'))
    notify.success(simulated ? `${t('change.applied')} – ${t('change.simulated')}` : t('change.applied'))
  })
  busy.value = false
  if (ok) {
    open.value = false
    emit('applied')
  }
}

function toggleTagged(vid: number): void {
  tagged.value = tagged.value.includes(vid) ? tagged.value.filter((v) => v !== vid) : [...tagged.value, vid].sort((a, b) => a - b)
}
</script>

<template>
  <UiDialog v-model:open="open" wide :title="title">
    <div class="space-y-5">
      <div class="field">
        <label class="label" for="pe-profile">{{ t('change.profile') }}</label>
        <select id="pe-profile" v-model="profileId" class="input">
          <option :value="null">{{ t('change.noProfile') }}</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">
            {{ p.name }} (U {{ p.untagged_vid ?? '–' }}{{ p.tagged_vids.length ? ` / T ${p.tagged_vids.join(',')}` : '' }})
          </option>
        </select>
      </div>

      <template v-if="profileId === null">
        <div v-if="single" class="field">
          <label class="label" for="pe-desc">{{ t('ports.description') }}</label>
          <input id="pe-desc" v-model="description" class="input" maxlength="200" />
        </div>

        <label class="flex items-center gap-2 text-sm font-medium">
          <input v-model="editVlans" type="checkbox" class="accent-indigo-600" /> {{ t('vlans.title') }}
        </label>
        <div v-if="editVlans" class="space-y-4 rounded-lg border border-gray-200 p-4 dark:border-white/10">
          <div class="field">
            <label class="label" for="pe-untagged">{{ t('ports.untagged') }}</label>
            <select id="pe-untagged" v-model="untagged" class="input">
              <option :value="null">{{ t('change.none') }}</option>
              <option v-for="v in vlans" :key="v.vid" :value="v.vid">{{ v.vid }} {{ v.name }}</option>
            </select>
          </div>
          <div class="field">
            <span class="label">{{ t('ports.tagged') }}</span>
            <div class="grid max-h-48 grid-cols-2 gap-1 overflow-y-auto sm:grid-cols-3">
              <label v-for="v in vlans" :key="v.vid" class="flex items-center gap-2 truncate text-sm" :class="{ 'opacity-40': v.vid === untagged }">
                <input
                  type="checkbox"
                  class="accent-indigo-600"
                  :checked="tagged.includes(v.vid)"
                  :disabled="v.vid === untagged"
                  @change="toggleTagged(v.vid)"
                />
                <span class="font-mono">{{ v.vid }}</span> <span class="truncate text-gray-500">{{ v.name }}</span>
              </label>
            </div>
          </div>
        </div>
      </template>

      <div class="field">
        <span class="label">{{ t('ports.status') }}</span>
        <div class="inline-flex w-fit rounded-md shadow-xs">
          <button
            v-for="option in (['keep', 'on', 'off'] as const)"
            :key="option"
            type="button"
            class="px-3 py-1.5 text-sm font-medium ring-1 ring-gray-300 ring-inset first:rounded-l-md last:rounded-r-md dark:ring-white/10"
            :class="enabled === option ? 'bg-indigo-600 text-white ring-indigo-600' : 'bg-white hover:bg-gray-50 dark:bg-white/5'"
            @click="enabled = option"
          >
            {{ option === 'keep' ? t('change.unchanged') : option === 'on' ? t('change.enabled') : t('change.disabled') }}
          </button>
        </div>
      </div>

      <div v-if="plan" class="space-y-3">
        <div v-for="w in plan.warnings" :key="w" class="flex gap-2 rounded-md p-3 text-sm" :class="w.startsWith('DANGER') ? 'bg-red-50 text-red-800 dark:bg-red-500/10 dark:text-red-300' : 'bg-yellow-50 text-yellow-800 dark:bg-yellow-500/10 dark:text-yellow-300'">
          <ExclamationTriangleIcon class="size-5 shrink-0" /> {{ w }}
        </div>
        <p v-if="!plan.operations" class="text-sm text-gray-500">{{ t('change.nothing') }}</p>
        <div v-else>
          <p class="label mb-1.5">{{ t('change.commands') }}</p>
          <pre class="max-h-64 overflow-auto rounded-md bg-gray-900 p-3 font-mono text-xs leading-relaxed text-green-300">{{ plan.commands.join('\n') }}</pre>
        </div>
      </div>
    </div>

    <template #footer>
      <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
      <button v-if="!plan" type="button" class="btn btn-primary" :disabled="busy" @click="preview">
        <UiSpinner v-if="busy" /> {{ t('change.preview') }}
      </button>
      <button
        v-else
        type="button"
        class="btn"
        :class="plan.warnings.some((w) => w.startsWith('DANGER')) ? 'btn-danger' : 'btn-primary'"
        :disabled="busy || !plan.operations"
        @click="apply"
      >
        <UiSpinner v-if="busy" /> {{ t('change.apply') }}
      </button>
    </template>
  </UiDialog>
</template>
