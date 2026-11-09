<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { MagnifyingGlassCircleIcon } from '@heroicons/vue/20/solid'
import { api, type CredentialProfile, type DetectResult, type Device, type DeviceIn, type DeviceModel } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'

const props = defineProps<{ device?: Device | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [device: Device] }>()

const { t } = useI18n()
const notify = useNotify()
const auth = useAuthStore()
const sites = useSitesStore()

const MODELS: DeviceModel[] = ['dell_n1500', 'dell_os10', 'aruba_os_switch', 'aruba_cx']
const siteOptions = computed(() => sites.sites.filter((s) => auth.canAdmin(s.id)))
const roomOptions = computed(() => sites.rooms(form.value.site_id))

const profiles = ref<CredentialProfile[]>([])
const busy = ref(false)
const detecting = ref(false)

/** Ask the switch via SNMP which model it is and pre-fill the form. */
async function detectModel(): Promise<void> {
  if (!form.value.hostname) return
  detecting.value = true
  await notify.run(async () => {
    const result = await api.post<DetectResult>('/devices/detect', {
      hostname: form.value.hostname,
      credential_profile_id: form.value.credential_profile_id,
    })
    if (result.model) {
      form.value.model = result.model
      if (!form.value.name && result.sys_name) form.value.name = result.sys_name
      notify.success(t('detect.found', { model: result.model_name || t(`device.models.${result.model}`) }))
    } else {
      notify.error(t('detect.unknown', { oid: result.sys_object_id }))
    }
  })
  detecting.value = false
}

function empty(): DeviceIn {
  return {
    name: '',
    hostname: '',
    model: 'dell_n1500',
    site_id: sites.currentId ?? 0,
    room_id: null,
    credential_profile_id: null,
    location_note: '',
  }
}

const form = ref<DeviceIn>(empty())

watch(open, async (isOpen) => {
  if (!isOpen) return
  const d = props.device
  form.value = d
    ? {
        name: d.name,
        hostname: d.hostname,
        model: d.model,
        site_id: d.site_id,
        room_id: d.room_id,
        credential_profile_id: d.credential_profile_id,
        location_note: d.location_note,
      }
    : empty()
  // Only super admins may list profiles; others keep the profile assigned by an admin.
  if (auth.isSuperadmin) profiles.value = await api.get<CredentialProfile[]>('/credential-profiles')
})

watch(
  () => form.value.site_id,
  () => {
    if (!roomOptions.value.some((r) => r.id === form.value.room_id)) form.value.room_id = null
  },
)

async function save(): Promise<void> {
  busy.value = true
  const ok = await notify.run(async () => {
    const saved = props.device
      ? await api.patch<Device>(`/devices/${props.device.id}`, form.value)
      : await api.post<Device>('/devices', form.value)
    emit('saved', saved)
  }, t('common.saved'))
  busy.value = false
  if (ok) open.value = false
}
</script>

<template>
  <UiDialog v-model:open="open" :title="device ? device.name : t('device.new')">
    <form id="device-form" class="grid grid-cols-1 gap-4 sm:grid-cols-2" @submit.prevent="save">
      <div class="field">
        <label class="label" for="d-name">{{ t('common.name') }}</label>
        <input id="d-name" v-model="form.name" class="input" required />
      </div>
      <div class="field">
        <label class="label" for="d-host">{{ t('device.hostname') }}</label>
        <input id="d-host" v-model="form.hostname" class="input font-mono" required />
      </div>
      <div class="field sm:col-span-2">
        <label class="label" for="d-model">{{ t('device.model') }}</label>
        <div class="flex gap-2">
          <select id="d-model" v-model="form.model" class="input">
            <option v-for="m in MODELS" :key="m" :value="m">{{ t(`device.models.${m}`) }}</option>
          </select>
          <button type="button" class="btn btn-secondary shrink-0" :disabled="!form.hostname || detecting" @click="detectModel">
            <UiSpinner v-if="detecting" />
            <MagnifyingGlassCircleIcon v-else class="size-4" />
            {{ t('detect.button') }}
          </button>
        </div>
      </div>
      <div class="field">
        <label class="label" for="d-site">{{ t('device.site') }}</label>
        <select id="d-site" v-model="form.site_id" class="input">
          <option v-for="s in siteOptions" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="field">
        <label class="label" for="d-room">{{ t('device.room') }}</label>
        <select id="d-room" v-model="form.room_id" class="input">
          <option :value="null">{{ t('common.none') }}</option>
          <option v-for="r in roomOptions" :key="r.id" :value="r.id">{{ r.label }}</option>
        </select>
      </div>
      <div v-if="auth.isSuperadmin" class="field sm:col-span-2">
        <label class="label" for="d-cred">{{ t('device.credentials') }}</label>
        <select id="d-cred" v-model="form.credential_profile_id" class="input">
          <option :value="null">{{ t('common.none') }}</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
      <div class="field sm:col-span-2">
        <label class="label" for="d-loc">{{ t('device.location') }}</label>
        <input id="d-loc" v-model="form.location_note" class="input" />
      </div>
    </form>
    <template #footer>
      <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
      <button type="submit" form="device-form" class="btn btn-primary" :disabled="busy">
        <UiSpinner v-if="busy" />
        {{ t('common.save') }}
      </button>
    </template>
  </UiDialog>
</template>
