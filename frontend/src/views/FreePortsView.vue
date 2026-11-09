<script setup lang="ts">
/** Find a port for a new connection: access ports that are down and had no device for a while. */
import { BoltIcon, MapPinIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import type { components } from '@/api/schema'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useNotify } from '@/composables/useNotify'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'

type FreeDevice = components['schemas']['FreePortsDeviceOut']

const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()

const DAYS = [0, 7, 30, 90, 180, 365]
const place = ref('')  // "" | "b:<id>" | "r:<id>"
const minDays = ref(30)
const includeDisabled = ref(false)
const onlyPoe = ref(false)
const result = ref<FreeDevice[]>([])
const loading = ref(false)

const buildings = computed(() => sites.current?.buildings ?? [])
const shown = computed(() =>
  result.value
    .map((d) => ({ ...d, ports: d.ports.filter((p) => !onlyPoe.value || p.poe) }))
    .filter((d) => d.ports.length),
)
const total = computed(() => shown.value.reduce((sum, d) => sum + d.ports.length, 0))

async function load(): Promise<void> {
  if (sites.currentId === null) return
  loading.value = true
  const params: Record<string, string | number | boolean> = { min_days: minDays.value, include_disabled: includeDisabled.value }
  if (place.value.startsWith('b:')) params.building_id = Number(place.value.slice(2))
  if (place.value.startsWith('r:')) params.room_id = Number(place.value.slice(2))
  await notify.run(async () => {
    result.value = await api.get<FreeDevice[]>(`/sites/${sites.currentId}/free-ports`, params)
  })
  loading.value = false
}

watch(() => sites.currentId, () => (place.value = ''))
watch([() => sites.currentId, place, minDays, includeDisabled], load, { immediate: true })
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="page-title">{{ t('freePorts.title') }}</h1>
      <p class="mt-1 max-w-3xl text-sm text-gray-500 dark:text-gray-400">{{ t('freePorts.hint') }}</p>
    </div>

    <div class="card flex flex-wrap items-end gap-4 p-4">
      <div class="field">
        <label class="label" for="fp-place">{{ t('freePorts.place') }}</label>
        <select id="fp-place" v-model="place" class="input w-64">
          <option value="">{{ t('freePorts.allPlaces') }}</option>
          <template v-for="b in buildings" :key="b.id">
            <option :value="`b:${b.id}`">{{ b.name }}</option>
            <option v-for="r in b.rooms" :key="r.id" :value="`r:${r.id}`">&nbsp;&nbsp;{{ b.name }} · {{ r.name }}</option>
          </template>
        </select>
      </div>
      <div class="field">
        <label class="label" for="fp-days">{{ t('freePorts.unusedFor') }}</label>
        <select id="fp-days" v-model="minDays" class="input w-48">
          <option v-for="d in DAYS" :key="d" :value="d">{{ d === 0 ? t('freePorts.now') : t('freePorts.days', { n: d }) }}</option>
        </select>
      </div>
      <label class="flex items-center gap-2 pb-2 text-sm"><input v-model="onlyPoe" type="checkbox" class="accent-indigo-600" /> {{ t('freePorts.onlyPoe') }}</label>
      <label class="flex items-center gap-2 pb-2 text-sm"><input v-model="includeDisabled" type="checkbox" class="accent-indigo-600" /> {{ t('freePorts.includeDisabled') }}</label>
      <span class="ml-auto pb-2 text-sm text-gray-500 dark:text-gray-400">{{ t('freePorts.found', { n: total }) }}</span>
    </div>

    <UiSpinner v-if="loading" class="mx-auto" />
    <p v-else-if="!shown.length" class="card p-6 text-sm text-gray-500">{{ t('freePorts.none') }}</p>

    <section v-for="d in shown" v-else :key="d.device_id" class="card">
      <header class="flex flex-wrap items-center gap-3 border-b border-gray-200 px-5 py-3 dark:border-white/10">
        <RouterLink :to="{ name: 'device', params: { id: d.device_id } }" class="link font-semibold">{{ d.device_name }}</RouterLink>
        <span v-if="d.building || d.room" class="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">
          <MapPinIcon class="size-4" /> {{ [d.building, d.room].filter(Boolean).join(' · ') }}
        </span>
        <span class="ml-auto badge badge-green">{{ t('freePorts.count', { n: d.ports.length }) }}</span>
      </header>
      <div class="flex flex-wrap gap-2 p-4">
        <RouterLink
          v-for="p in d.ports"
          :key="p.id"
          :to="{ name: 'device', params: { id: d.device_id }, query: { tab: 'ports', port: p.id } }"
          class="group rounded-lg px-3 py-2 text-sm ring-1 ring-gray-200 hover:bg-indigo-50 hover:ring-indigo-300 dark:ring-white/10 dark:hover:bg-indigo-500/10"
          :title="[
            p.description,
            p.down_since ? `${t('freePorts.downSince')} ${formatDateTime(p.down_since, locale)}` : t('freePorts.downSinceStart'),
            p.last_device_at ? `${t('freePorts.lastDevice')} ${formatDateTime(p.last_device_at, locale)}` : '',
          ].filter(Boolean).join('\n')"
        >
          <span class="flex items-center gap-1 font-mono font-semibold">
            {{ p.name }}
            <BoltIcon v-if="p.poe" class="size-3.5 text-amber-500" />
          </span>
          <span class="block text-xs text-gray-500 dark:text-gray-400">
            <template v-if="!p.admin_up">{{ t('ports.adminDown') }}</template>
            <template v-else-if="p.untagged_vlans.length">VLAN {{ p.untagged_vlans.join(', ') }}</template>
            <template v-else>&nbsp;</template>
          </span>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
