<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type CredentialProfile, type Job } from '@/api/client'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ started: [job: Job] }>()
const { t } = useI18n()
const notify = useNotify()
const auth = useAuthStore()
const sites = useSitesStore()

const cidr = ref('')
const profileId = ref<number | null>(null)
const profiles = ref<CredentialProfile[]>([])

watch(open, async (isOpen) => {
  if (isOpen && auth.isSuperadmin) profiles.value = await api.get<CredentialProfile[]>('/credential-profiles').catch(() => [])
})

async function start(): Promise<void> {
  const ok = await notify.run(async () => {
    const job = await api.post<Job>('/jobs', {
      kind: 'discover',
      site_id: sites.currentId,
      cidr: cidr.value,
      credential_profile_id: profileId.value,
    })
    emit('started', job)
  }, t('discover.started'))
  if (ok) open.value = false
}
</script>

<template>
  <UiDialog v-model:open="open" :title="t('discover.title')">
    <form id="discover-form" class="space-y-4" @submit.prevent="start">
      <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('discover.hint') }}</p>
      <div class="field">
        <label class="label" for="dc-cidr">{{ t('discover.network') }}</label>
        <input id="dc-cidr" v-model="cidr" class="input font-mono" placeholder="10.0.10.0/24" required />
      </div>
      <div v-if="auth.isSuperadmin" class="field">
        <label class="label" for="dc-cred">{{ t('device.credentials') }}</label>
        <select id="dc-cred" v-model="profileId" class="input">
          <option :value="null">{{ t('common.none') }} (public)</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
    </form>
    <template #footer>
      <button type="button" class="btn btn-secondary" @click="open = false">{{ t('common.cancel') }}</button>
      <button type="submit" form="discover-form" class="btn btn-primary">{{ t('discover.start') }}</button>
    </template>
  </UiDialog>
</template>
