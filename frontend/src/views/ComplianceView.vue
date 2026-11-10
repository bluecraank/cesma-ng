<script setup lang="ts">
/** Configuration rules checked against the latest backup of every switch. */
import { CheckCircleIcon, MinusCircleIcon, PencilSquareIcon, PlusIcon, TrashIcon, XCircleIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type DeviceModel } from '@/api/client'
import type { components } from '@/api/schema'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useConfirmDelete } from '@/composables/useConfirm'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

type Compliance = components['schemas']['ComplianceOut']
type Rule = components['schemas']['ComplianceRuleOut']
type Result = components['schemas']['ComplianceResultOut']

const MODELS: DeviceModel[] = ['dell_n1500', 'dell_os10', 'aruba_os_switch', 'aruba_cx']
/** Starting points for common rules (the pattern is a regular expression per line). */
const EXAMPLES = [
  { name: 'NTP-Server', mode: 'require', pattern: '^\\s*(sntp|ntp) server' },
  { name: 'Kein Telnet', mode: 'forbid', pattern: '^\\s*(telnet-server|ip telnet server enable)' },
  { name: 'Syslog-Server', mode: 'require', pattern: '^\\s*(logging|syslog) ' },
  { name: 'SNMP nicht "public"', mode: 'forbid', pattern: 'community "?public' },
] as const

const { t, locale } = useI18n()
const notify = useNotify()
const auth = useAuthStore()
const sites = useSitesStore()
const confirmDelete = useConfirmDelete()

const data = ref<Compliance | null>(null)
/** Disabled rules are not in the matrix; super administrators can switch them on again. */
const disabledRules = ref<Rule[]>([])
const loading = ref(false)
const onlyFailing = ref(false)
const detail = ref<{ device: string; rule: Rule; result: Result } | null>(null)
const detailOpen = ref(false)

const ruleOpen = ref(false)
const editing = ref<Rule | null>(null)
const form = ref({ name: '', description: '', mode: 'require' as 'require' | 'forbid', pattern: '', models: [] as DeviceModel[], enabled: true })

async function load(): Promise<void> {
  if (sites.currentId === null) return
  loading.value = true
  await notify.run(async () => {
    data.value = await api.get<Compliance>(`/sites/${sites.currentId}/compliance`)
    if (auth.isSuperadmin) disabledRules.value = (await api.get<Rule[]>('/compliance-rules')).filter((r) => !r.enabled)
  })
  loading.value = false
}

const rules = computed(() => data.value?.rules ?? [])
const resultOf = (device: Compliance['devices'][number], ruleId: number): Result | undefined =>
  device.results.find((r) => r.rule_id === ruleId)
const failing = (device: Compliance['devices'][number]): number => device.results.filter((r) => r.passed === false).length
const devices = computed(() => (data.value?.devices ?? []).filter((d) => !onlyFailing.value || failing(d)))
const summary = computed(() => {
  const all = data.value?.devices ?? []
  return { failing: all.filter((d) => failing(d)).length, total: all.length, noBackup: all.filter((d) => !d.backup_at).length }
})

function show(device: Compliance['devices'][number], rule: Rule): void {
  const result = resultOf(device, rule.id)
  if (!result) return
  detail.value = { device: device.device_name, rule, result }
  detailOpen.value = true
}

function editRule(rule: Rule | null, example?: (typeof EXAMPLES)[number]): void {
  editing.value = rule
  form.value = rule
    ? { name: rule.name, description: rule.description, mode: rule.mode, pattern: rule.pattern, models: [...rule.models] as DeviceModel[], enabled: rule.enabled }
    : { name: example?.name ?? '', description: '', mode: example?.mode ?? 'require', pattern: example?.pattern ?? '', models: [], enabled: true }
  ruleOpen.value = true
}

async function saveRule(): Promise<void> {
  const rule = editing.value
  const ok = await notify.run(
    () => (rule ? api.put(`/compliance-rules/${rule.id}`, form.value) : api.post('/compliance-rules', form.value)),
    t('common.saved'),
  )
  if (ok) {
    ruleOpen.value = false
    await load()
  }
}

async function removeRule(rule: Rule): Promise<void> {
  if (await confirmDelete(rule.name)) {
    if (await notify.run(() => api.delete(`/compliance-rules/${rule.id}`), t('common.deleted'))) await load()
  }
}

watch(() => sites.currentId, load, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('compliance.title') }}</h1>
        <p class="mt-1 max-w-3xl text-sm text-gray-500 dark:text-gray-400">{{ t('compliance.hint') }}</p>
      </div>
      <div v-if="auth.isSuperadmin" class="flex flex-wrap gap-2">
        <button type="button" class="btn btn-primary" @click="editRule(null)"><PlusIcon class="size-5" /> {{ t('compliance.newRule') }}</button>
      </div>
    </div>

    <UiSpinner v-if="loading && !data" class="mx-auto" />
    <template v-else-if="data">
      <div v-if="!rules.length" class="card space-y-3 p-6 text-sm">
        <p class="text-gray-500">{{ t('compliance.noRules') }}</p>
        <div v-if="auth.isSuperadmin" class="flex flex-wrap gap-2">
          <button v-for="ex in EXAMPLES" :key="ex.name" type="button" class="btn btn-secondary btn-sm" @click="editRule(null, ex)">
            <PlusIcon class="size-4" /> {{ ex.name }}
          </button>
        </div>
      </div>

      <template v-else>
        <div class="flex flex-wrap items-center gap-4 text-sm">
          <span v-if="summary.failing" class="badge badge-red">{{ t('compliance.failing', { n: summary.failing, total: summary.total }) }}</span>
          <span v-else class="badge badge-green">{{ t('compliance.allOk') }}</span>
          <span v-if="summary.noBackup" class="text-gray-500">{{ t('compliance.noBackup', { n: summary.noBackup }) }}</span>
          <label class="ml-auto flex items-center gap-2"><input v-model="onlyFailing" type="checkbox" class="accent-brand-600" /> {{ t('compliance.onlyFailing') }}</label>
        </div>

        <div class="card table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>{{ t('device.title') }}</th>
                <th v-for="r in rules" :key="r.id" class="text-center normal-case">
                  <div class="flex items-center justify-center gap-1">
                    <span :title="`${r.mode === 'require' ? t('compliance.require') : t('compliance.forbid')}: ${r.pattern}`">{{ r.name }}</span>
                    <template v-if="auth.isSuperadmin">
                      <button type="button" class="btn-icon" :title="t('common.edit')" @click="editRule(r)"><PencilSquareIcon class="size-3.5" /></button>
                      <button type="button" class="btn-icon hover:!text-red-600" :title="t('common.delete')" @click="removeRule(r)"><TrashIcon class="size-3.5" /></button>
                    </template>
                  </div>
                </th>
                <th>{{ t('compliance.checked') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in devices" :key="d.device_id">
                <td><RouterLink :to="{ name: 'device', params: { id: d.device_id } }" class="link">{{ d.device_name }}</RouterLink></td>
                <td v-for="r in rules" :key="r.id" class="text-center">
                  <template v-if="resultOf(d, r.id)">
                    <button v-if="resultOf(d, r.id)?.passed === true" type="button" :title="t('compliance.passed')" @click="show(d, r)">
                      <CheckCircleIcon class="mx-auto size-5 text-green-600" />
                    </button>
                    <button v-else-if="resultOf(d, r.id)?.passed === false" type="button" :title="t('compliance.failed')" @click="show(d, r)">
                      <XCircleIcon class="mx-auto size-5 text-red-600" />
                    </button>
                    <MinusCircleIcon v-else class="mx-auto size-5 text-gray-300 dark:text-gray-600" :title="t('compliance.noBackupYet')" />
                  </template>
                  <span v-else class="text-xs text-gray-400" :title="t('compliance.notApplicable')">n/a</span>
                </td>
                <td class="text-xs whitespace-nowrap text-gray-500 tabular-nums">
                  {{ d.backup_at ? formatDateTime(d.backup_at, locale) : t('compliance.noBackupYet') }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>

    <p v-if="disabledRules.length" class="flex flex-wrap items-center gap-2 text-sm text-gray-500">
      {{ t('compliance.disabled') }}:
      <button v-for="r in disabledRules" :key="r.id" type="button" class="badge badge-gray hover:underline" @click="editRule(r)">{{ r.name }}</button>
    </p>

    <UiDialog v-model:open="detailOpen" :title="detail ? `${detail.device}: ${detail.rule.name}` : ''">
      <div v-if="detail" class="space-y-3 text-sm">
        <p>
          <span class="badge" :class="detail.result.passed ? 'badge-green' : 'badge-red'">
            {{ detail.result.passed ? t('compliance.passed') : t('compliance.failed') }}
          </span>
          {{ detail.rule.mode === 'require' ? t('compliance.require') : t('compliance.forbid') }}:
          <code class="rounded bg-gray-100 px-1 dark:bg-white/10">{{ detail.rule.pattern }}</code>
        </p>
        <p v-if="detail.rule.description" class="text-gray-600 dark:text-gray-400">{{ detail.rule.description }}</p>
        <div v-if="detail.result.lines.length">
          <p class="label mb-1">{{ t('compliance.lines') }}</p>
          <pre class="overflow-auto rounded-md bg-gray-900 p-3 font-mono text-xs text-green-300">{{ detail.result.lines.join('\n') }}</pre>
        </div>
        <p v-else-if="detail.result.passed !== null && !auth.can('backups.read', sites.currentId)" class="text-xs text-gray-500">{{ t('compliance.linesHidden') }}</p>
      </div>
    </UiDialog>

    <UiDialog v-model:open="ruleOpen" wide :title="editing ? editing.name : t('compliance.newRule')">
      <form id="rule-form" class="space-y-4" @submit.prevent="saveRule">
        <div class="grid gap-4 sm:grid-cols-2">
          <div class="field">
            <label class="label" for="cr-name">{{ t('common.name') }}</label>
            <input id="cr-name" v-model="form.name" class="input" required maxlength="100" />
          </div>
          <div class="field">
            <label class="label" for="cr-mode">{{ t('compliance.mode') }}</label>
            <select id="cr-mode" v-model="form.mode" class="input">
              <option value="require">{{ t('compliance.require') }}</option>
              <option value="forbid">{{ t('compliance.forbid') }}</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label class="label" for="cr-pattern">{{ t('compliance.pattern') }}</label>
          <input id="cr-pattern" v-model="form.pattern" class="input font-mono" required maxlength="500" />
          <p class="hint">{{ t('compliance.patternHint') }}</p>
        </div>
        <div class="field">
          <label class="label" for="cr-desc">{{ t('ports.description') }}</label>
          <input id="cr-desc" v-model="form.description" class="input" maxlength="255" />
        </div>
        <fieldset class="field">
          <legend class="label">{{ t('compliance.models') }}</legend>
          <div class="flex flex-wrap gap-4">
            <label v-for="m in MODELS" :key="m" class="flex items-center gap-2 text-sm">
              <input v-model="form.models" type="checkbox" :value="m" class="accent-brand-600" /> {{ t(`device.models.${m}`) }}
            </label>
          </div>
          <p class="hint">{{ t('compliance.modelsHint') }}</p>
        </fieldset>
        <label class="flex items-center gap-2 text-sm"><input v-model="form.enabled" type="checkbox" class="accent-brand-600" /> {{ t('compliance.enabled') }}</label>
      </form>
      <template #footer>
        <button type="button" class="btn btn-secondary" @click="ruleOpen = false">{{ t('common.cancel') }}</button>
        <button type="submit" form="rule-form" class="btn btn-primary">{{ t('common.save') }}</button>
      </template>
    </UiDialog>
  </div>
</template>
