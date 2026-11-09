<script setup lang="ts">
/** Renames the switch itself (hostname) and the device in cesma-ng, with a preview. */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type ApplyResult, type ChangePlan, type Device } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useNotify } from '@/composables/useNotify'

const props = defineProps<{ device: Device }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ renamed: [] }>()
const { t } = useI18n()
const notify = useNotify()

const name = ref('')
const plan = ref<ChangePlan | null>(null)
const busy = ref(false)

watch(open, (isOpen) => {
  if (!isOpen) return
  name.value = props.device.sys_name || props.device.name
  plan.value = null
})
watch(name, () => (plan.value = null))

async function preview(): Promise<void> {
  busy.value = true
  await notify.run(async () => {
    plan.value = await api.post<ChangePlan>(`/devices/${props.device.id}/rename/plan`, { name: name.value })
  })
  busy.value = false
}

async function apply(): Promise<void> {
  busy.value = true
  const ok = await notify.run(async () => {
    const result = await api.post<ApplyResult>(`/devices/${props.device.id}/rename/apply`, { name: name.value })
    const simulated = result.log.some((line) => line.startsWith('[simulated]'))
    notify.success(simulated ? `${t('change.applied')} – ${t('change.simulated')}` : t('change.applied'))
  })
  busy.value = false
  if (ok) {
    open.value = false
    emit('renamed')
  }
}
</script>

<template>
  <UiDialog v-model:open="open" :title="t('rename.title')">
    <form id="rename-form" class="space-y-4" @submit.prevent="plan ? apply() : preview()">
      <p class="text-sm text-gray-600 dark:text-gray-400">{{ t('rename.hint') }}</p>
      <div class="field">
        <label class="label" for="rename-name">{{ t('rename.name') }}</label>
        <input id="rename-name" v-model="name" class="input font-mono" required maxlength="63" pattern="[A-Za-z0-9][A-Za-z0-9._\-]*" autocomplete="off" />
        <p class="text-xs text-gray-500">{{ t('rename.rules') }}</p>
      </div>
      <div class="text-xs text-gray-500">{{ t('rename.current') }}: <span class="font-mono">{{ device.sys_name || '—' }}</span></div>
      <div v-if="plan">
        <p v-if="!plan.operations" class="text-sm text-gray-500">{{ t('rename.onlyCesma') }}</p>
        <template v-else>
          <p class="label mb-1.5">{{ t('change.commands') }}</p>
          <pre class="overflow-auto rounded-md bg-gray-900 p-3 font-mono text-xs text-green-300">{{ plan.commands.join('\n') }}</pre>
        </template>
      </div>
    </form>
    <template #footer>
      <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
      <button type="submit" form="rename-form" class="btn btn-primary" :disabled="busy || !name">
        <UiSpinner v-if="busy" /> {{ plan ? t('change.apply') : t('change.preview') }}
      </button>
    </template>
  </UiDialog>
</template>
