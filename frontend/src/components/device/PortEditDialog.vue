<script setup lang="ts">
import { ArrowUturnLeftIcon, ExclamationTriangleIcon, MagnifyingGlassIcon } from '@heroicons/vue/20/solid'
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
/** Membership of one VLAN; "mixed" only as the start state when several ports differ. */
type Member = 'none' | 'untagged' | 'tagged' | 'mixed'
const CHOICES = ['none', 'untagged', 'tagged'] as const

const profiles = ref<PortProfile[]>([])
const profileId = ref<number | null>(null)
const description = ref('')
const enabled = ref<Tri>('keep')
const members = ref<Record<number, Member>>({})
const untaggedTouched = ref(false)
const filter = ref('')
const onlyAssigned = ref(false)
const plan = ref<ChangePlan | null>(null)
const busy = ref(false)

const single = computed(() => (props.ports.length === 1 ? props.ports[0] : null))
const title = computed(() =>
  single.value ? `${t('ports.port')} ${single.value.name}` : t('change.editPorts', { n: props.ports.length }),
)

function memberOf(port: Port, vid: number): Member {
  if (port.untagged_vlans.includes(vid)) return 'untagged'
  return port.tagged_vlans.includes(vid) ? 'tagged' : 'none'
}

/** State of every VLAN over all selected ports. */
const initial = computed<Record<number, Member>>(() => {
  const result: Record<number, Member> = {}
  for (const v of props.vlans) {
    const states = new Set(props.ports.map((p) => memberOf(p, v.vid)))
    result[v.vid] = states.size === 1 ? [...states][0]! : 'mixed'
  }
  return result
})

watch(open, async (isOpen) => {
  if (!isOpen) return
  plan.value = null
  profileId.value = null
  enabled.value = 'keep'
  description.value = single.value?.description ?? ''
  members.value = { ...initial.value }
  untaggedTouched.value = false
  filter.value = ''
  onlyAssigned.value = props.vlans.length > 12
  profiles.value = await api.get<PortProfile[]>(`/sites/${props.siteId}/port-profiles`).catch(() => [])
})

// Any edit invalidates the preview.
watch([profileId, description, enabled, members], () => (plan.value = null), { deep: true })

function set(vid: number, value: Member): void {
  const next = { ...members.value }
  if (value === 'untagged' || next[vid] === 'untagged') untaggedTouched.value = true
  // A port has one untagged VLAN: choosing another one replaces it.
  if (value === 'untagged') {
    for (const [other, state] of Object.entries(next)) if (state === 'untagged') next[Number(other)] = 'none'
  }
  next[vid] = value
  members.value = next
}

function reset(vid: number): void {
  members.value = { ...members.value, [vid]: initial.value[vid] ?? 'none' }
}

const changed = (vid: number): boolean => members.value[vid] !== initial.value[vid]
const untaggedNow = computed(() => props.vlans.find((v) => members.value[v.vid] === 'untagged'))
const untaggedLabel = computed(() => {
  if (untaggedNow.value) return `${untaggedNow.value.vid} ${untaggedNow.value.name}`
  const differs = new Set(props.ports.map((p) => p.untagged_vlans[0] ?? 0)).size > 1
  return !untaggedTouched.value && differs ? t('change.mixed') : '—'
})
const taggedNow = computed(() => props.vlans.filter((v) => members.value[v.vid] === 'tagged'))
const changedCount = computed(() => props.vlans.filter((v) => changed(v.vid)).length)

const shownVlans = computed(() => {
  const q = filter.value.trim().toLowerCase()
  return props.vlans.filter(
    (v) =>
      (!q || String(v.vid).startsWith(q) || v.name.toLowerCase().includes(q)) &&
      (!onlyAssigned.value || q || members.value[v.vid] !== 'none' || initial.value[v.vid] !== 'none'),
  )
})

function body(): Record<string, unknown> {
  const data: Record<string, unknown> = { port_ids: props.ports.map((p) => p.id) }
  if (enabled.value !== 'keep') data.enabled = enabled.value === 'on'
  if (profileId.value !== null) return { ...data, profile_id: profileId.value }
  if (single.value && description.value !== single.value.description) data.description = description.value
  if (untaggedTouched.value) {
    if (untaggedNow.value) data.untagged = untaggedNow.value.vid
    else data.clear_untagged = true
  }
  const add: number[] = []
  const remove: number[] = []
  for (const v of props.vlans) {
    if (!changed(v.vid)) continue
    const now = members.value[v.vid]
    if (now === 'tagged') add.push(v.vid)
    else if (now === 'none' && initial.value[v.vid] !== 'untagged') remove.push(v.vid)
  }
  if (add.length) data.add_tagged = add
  if (remove.length) data.remove_tagged = remove
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

const choiceClass: Record<(typeof CHOICES)[number], string> = {
  none: 'bg-gray-600 text-white ring-gray-600 dark:bg-gray-500',
  untagged: 'bg-emerald-600 text-white ring-emerald-600',
  tagged: 'bg-indigo-600 text-white ring-indigo-600',
}
</script>

<template>
  <UiDialog v-model:open="open" wide :title="title">
    <div class="space-y-5">
      <p v-if="!single" class="font-mono text-xs text-gray-500 dark:text-gray-400">{{ ports.map((p) => p.name).join(', ') }}</p>

      <div class="field">
        <div class="flex items-baseline justify-between">
          <label class="label" for="pe-profile">{{ t('change.profile') }}</label>
          <RouterLink :to="{ name: 'vlans', query: { tab: 'profiles' } }" class="link text-xs">{{ t('change.manageProfiles') }}</RouterLink>
        </div>
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

        <section class="space-y-3">
          <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span class="label">{{ t('vlans.title') }}</span>
            <span class="text-sm">
              <span class="badge badge-green">U</span> {{ untaggedLabel }}
            </span>
            <span class="text-sm">
              <span class="badge badge-indigo">T</span> {{ taggedNow.length ? taggedNow.map((v) => v.vid).join(', ') : '—' }}
            </span>
            <span v-if="changedCount" class="badge badge-yellow">{{ t('change.changedCount', { n: changedCount }) }}</span>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('change.vlanHint') }}</p>

          <div class="flex flex-wrap items-center gap-3">
            <div class="relative">
              <MagnifyingGlassIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
              <input v-model="filter" class="input w-56 pl-8" :placeholder="t('change.vlanFilter')" />
            </div>
            <label class="flex items-center gap-2 text-sm"><input v-model="onlyAssigned" type="checkbox" class="accent-indigo-600" /> {{ t('change.onlyAssigned') }}</label>
          </div>

          <ul class="max-h-80 divide-y divide-gray-100 overflow-y-auto rounded-lg border border-gray-200 dark:divide-white/5 dark:border-white/10">
            <li
              v-for="v in shownVlans"
              :key="v.vid"
              class="flex items-center gap-3 px-3 py-1.5"
              :class="changed(v.vid) ? 'bg-amber-50 dark:bg-amber-400/10' : ''"
            >
              <span class="w-12 font-mono text-sm font-medium text-gray-900 dark:text-white">{{ v.vid }}</span>
              <span class="min-w-0 flex-1 truncate text-sm text-gray-600 dark:text-gray-300">{{ v.name }}</span>
              <span v-if="members[v.vid] === 'mixed'" class="badge badge-gray" :title="t('change.mixedHint')">{{ t('change.mixed') }}</span>
              <button
                v-if="changed(v.vid)"
                type="button"
                class="btn-icon"
                :title="t('change.reset')"
                @click="reset(v.vid)"
              >
                <ArrowUturnLeftIcon class="size-4" />
              </button>
              <div class="inline-flex rounded-md shadow-xs">
                <button
                  v-for="c in CHOICES"
                  :key="c"
                  type="button"
                  class="px-2.5 py-1 text-xs font-medium ring-1 ring-gray-300 ring-inset first:rounded-l-md last:rounded-r-md dark:ring-white/10"
                  :class="members[v.vid] === c ? choiceClass[c] : 'bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10'"
                  @click="set(v.vid, c)"
                >
                  {{ t(`change.member.${c}`) }}
                </button>
              </div>
            </li>
            <li v-if="!shownVlans.length" class="px-3 py-4 text-center text-sm text-gray-500">—</li>
          </ul>
        </section>
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
