<script setup lang="ts">
/** Front panel view of all switches: which ports are in use, which are free for a new connection. */
import { ArrowTopRightOnSquareIcon, MapPinIcon, PencilSquareIcon, SignalIcon } from '@heroicons/vue/20/solid'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import type { components } from '@/api/schema'
import SwitchIcon from '@/components/SwitchIcon.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useNotify } from '@/composables/useNotify'
import { useAuthStore } from '@/stores/auth'
import { useSitesStore } from '@/stores/sites'
import { formatDateTime } from '@/utils/format'
import { panelLayout, portLabel } from '@/utils/switchPanel'

type SwitchPorts = components['schemas']['SwitchPortsDeviceOut']
type SwitchPort = components['schemas']['SwitchPortOut']
type State = 'free' | 'up' | 'uplink' | 'down' | 'disabled'
type LinkWatch = components['schemas']['LinkWatchOut']
type LinkUp = components['schemas']['LinkUpOut']

const { t, locale } = useI18n()
const notify = useNotify()
const sites = useSitesStore()
const auth = useAuthStore()

const DAYS = [7, 30, 90, 180, 365]
/** Live state: every port without link counts as free, regardless of how long it has been down. */
const live = ref(false)
const place = ref('') // "" | "b:<id>" | "r:<id>"
const minDays = ref(30)
const includeDisabled = ref(false)
const onlyPoe = ref(false)
const onlyWithFree = ref(false)
const result = ref<SwitchPorts[]>([])
const loading = ref(false)

const buildings = computed(() => sites.current?.buildings ?? [])

function state(p: SwitchPort): State {
  if (p.free && (!onlyPoe.value || p.poe)) return 'free'
  if (p.uplink) return 'uplink'
  if (p.oper_up) return 'up'
  return p.admin_up ? 'down' : 'disabled'
}

const switches = computed(() =>
  result.value
    .map((d) => {
      const counts = { free: 0, up: 0, uplink: 0, down: 0, disabled: 0 }
      for (const p of d.ports) counts[state(p)] += 1
      return { ...d, counts, units: panelLayout(d.ports) }
    })
    .filter((d) => !onlyWithFree.value || d.counts.free),
)
const totalFree = computed(() => switches.value.reduce((sum, d) => sum + d.counts.free, 0))

async function load(): Promise<void> {
  if (sites.currentId === null) return
  loading.value = true
  const params: Record<string, string | number | boolean> = { min_days: live.value ? 0 : minDays.value, include_disabled: includeDisabled.value }
  if (place.value.startsWith('b:')) params.building_id = Number(place.value.slice(2))
  if (place.value.startsWith('r:')) params.room_id = Number(place.value.slice(2))
  await notify.run(async () => {
    result.value = await api.get<SwitchPorts[]>(`/sites/${sites.currentId}/switchports`, params)
  })
  loading.value = false
}

watch(() => sites.currentId, () => (place.value = ''))

/*
 * Port finder: someone plugs a device in somewhere, the viewer sees which port just went up.
 * While switched on, the link states are scanned every few seconds (throttled on the server).
 */
const FINDER_EVERY_MS = 5000
const FINDER_MAX_MS = 15 * 60 * 1000
const finder = ref(false)
const finderSince = ref<string | null>(null)
const finderEvents = ref<LinkUp[]>([])
const finderInfo = ref<{ scannedAt: string | null; unreachable: string[] }>({ scannedAt: null, unreachable: [] })
let finderTimer: ReturnType<typeof setTimeout> | null = null
let finderStarted = 0
const foundPorts = computed(() => new Set(finderEvents.value.filter((e) => e.still_up).map((e) => e.port_id)))

async function finderTick(): Promise<void> {
  if (!finder.value || sites.currentId === null || !finderSince.value) return
  try {
    const res = await api.post<LinkWatch>(`/sites/${sites.currentId}/link-watch`, { since: finderSince.value })
    const before = finderEvents.value.length
    finderEvents.value = res.events
    finderInfo.value = { scannedAt: res.scanned_at, unreachable: res.unreachable }
    if (res.events.length !== before) await load() // show the new link state in the panels
  } catch (err) {
    notify.error(err)
  }
  if (Date.now() - finderStarted > FINDER_MAX_MS) {
    stopFinder()
    return
  }
  if (finder.value) finderTimer = setTimeout(finderTick, FINDER_EVERY_MS)
}

function startFinder(): void {
  finder.value = true
  finderStarted = Date.now()
  finderSince.value = new Date().toISOString()
  finderEvents.value = []
  finderInfo.value = { scannedAt: null, unreachable: [] }
  void finderTick()
}

function stopFinder(): void {
  finder.value = false
  if (finderTimer) clearTimeout(finderTimer)
  finderTimer = null
}

watch(() => sites.currentId, stopFinder)
onBeforeUnmount(stopFinder)

function time(value: string): string {
  return new Date(value).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
watch([() => sites.currentId, place, minDays, live, includeDisabled], load, { immediate: true })

/** Colours are fixed (not theme dependent) because the panel itself is always dark. */
const STYLE: Record<State, string> = {
  free: 'bg-green-500 text-white ring-2 ring-green-300 ring-inset hover:bg-green-400',
  up: 'bg-sky-600 text-white hover:bg-sky-500',
  uplink: 'bg-violet-600 text-white hover:bg-violet-500',
  down: 'bg-gray-600 text-gray-200 hover:bg-gray-500',
  disabled: 'bg-gray-800 text-gray-500 line-through ring-1 ring-red-500/60 ring-inset hover:bg-gray-700',
}
const LEGEND: State[] = ['free', 'up', 'uplink', 'down', 'disabled']

function speed(mbps: number | null): string {
  if (!mbps) return ''
  return mbps >= 1000 ? `${mbps / 1000} Gbit/s` : `${mbps} Mbit/s`
}

/** Hover card: shown immediately (the native title tooltip is slow and plain). */
const hover = ref<{ port: SwitchPort; x: number; y: number; above: boolean } | null>(null)

function showHover(port: SwitchPort, event: MouseEvent): void {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const above = rect.bottom > window.innerHeight - 260
  const x = Math.min(Math.max(rect.left + rect.width / 2, 170), window.innerWidth - 170)
  hover.value = { port, x, y: above ? rect.top - 8 : rect.bottom + 8, above }
}

function facts(p: SwitchPort): string[] {
  return [
    p.description,
    p.untagged_vlans.length ? `VLAN ${p.untagged_vlans.join(', ')}${p.tagged_count ? ` ${t('switchports.tagged', { n: p.tagged_count })}` : ''}` : '',
    p.oper_up ? speed(p.speed_mbps) : '',
    p.poe ? 'PoE' : '',
    !p.oper_up ? (p.down_since ? `${t('switchports.downSince')} ${formatDateTime(p.down_since, locale.value)}` : t('switchports.downSinceStart')) : '',
    !p.connected.length && p.last_device_at ? `${t('switchports.lastDevice')} ${formatDateTime(p.last_device_at, locale.value)}` : '',
  ].filter(Boolean)
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="page-title">{{ t('switchports.title') }}</h1>
      <p class="mt-1 max-w-3xl text-sm text-gray-500 dark:text-gray-400">{{ t('switchports.hint') }}</p>
    </div>

    <div class="card flex flex-wrap items-end gap-4 p-4">
      <div class="field">
        <label class="label" for="sp-place">{{ t('switchports.place') }}</label>
        <select id="sp-place" v-model="place" class="input w-64">
          <option value="">{{ t('switchports.allPlaces') }}</option>
          <template v-for="b in buildings" :key="b.id">
            <option :value="`b:${b.id}`">{{ b.name }}</option>
            <option v-for="r in b.rooms" :key="r.id" :value="`r:${r.id}`">&nbsp;&nbsp;{{ b.name }} · {{ r.name }}</option>
          </template>
        </select>
      </div>
      <div class="field">
        <label class="label" for="sp-days">{{ t('switchports.freeAfter') }}</label>
        <div class="flex items-center gap-3">
          <select id="sp-days" v-model="minDays" class="input w-40 disabled:cursor-not-allowed disabled:opacity-50" :disabled="live">
            <option v-for="d in DAYS" :key="d" :value="d">{{ t('switchports.days', { n: d }) }}</option>
          </select>
          <label class="flex items-center gap-2 text-sm whitespace-nowrap" :title="t('switchports.liveHint')">
            <input v-model="live" type="checkbox" class="accent-indigo-600" /> {{ t('switchports.live') }}
          </label>
        </div>
      </div>
      <div class="flex flex-col gap-1 pb-1 text-sm">
        <label class="flex items-center gap-2"><input v-model="onlyPoe" type="checkbox" class="accent-indigo-600" /> {{ t('switchports.onlyPoe') }}</label>
        <label class="flex items-center gap-2"><input v-model="includeDisabled" type="checkbox" class="accent-indigo-600" /> {{ t('switchports.includeDisabled') }}</label>
      </div>
      <label class="flex items-center gap-2 pb-1 text-sm"><input v-model="onlyWithFree" type="checkbox" class="accent-indigo-600" /> {{ t('switchports.onlyWithFree') }}</label>
      <span class="ml-auto pb-1 text-sm text-gray-500 dark:text-gray-400">{{ t('switchports.summary', { free: totalFree, switches: switches.length }) }}</span>
    </div>

    <!-- port finder -->
    <section class="card p-4" :class="finder && 'ring-2 ring-amber-400'">
      <div class="flex flex-wrap items-center gap-4">
        <SignalIcon class="size-6 shrink-0" :class="finder ? 'animate-pulse text-amber-500' : 'text-gray-400'" />
        <div class="min-w-0 flex-1">
          <p class="font-semibold">{{ t('finder.title') }}</p>
          <p class="text-sm text-gray-500 dark:text-gray-400">
            <template v-if="!finder">{{ t('finder.hint') }}</template>
            <template v-else>
              {{ t('finder.running') }}
              <span v-if="finderInfo.scannedAt"> · {{ t('finder.lastScan', { time: time(finderInfo.scannedAt) }) }}</span>
            </template>
          </p>
        </div>
        <button type="button" class="btn" :class="finder ? 'btn-secondary' : 'btn-primary'" @click="finder ? stopFinder() : startFinder()">
          {{ finder ? t('finder.stop') : t('finder.start') }}
        </button>
      </div>
      <p v-if="finder && finderInfo.unreachable.length" class="mt-3 text-xs text-amber-700 dark:text-amber-400">
        {{ t('finder.unreachable', { names: finderInfo.unreachable.join(', ') }) }}
      </p>
      <div v-if="finder || finderEvents.length" class="mt-4 space-y-2">
        <p v-if="!finderEvents.length" class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <UiSpinner class="size-4" /> {{ t('finder.waiting') }}
        </p>
        <div
          v-for="e in finderEvents"
          :key="e.port_id"
          class="flex flex-wrap items-start gap-x-6 gap-y-2 rounded-lg p-3 ring-1"
          :class="e.still_up ? 'ring-amber-300 dark:ring-amber-500/40' : 'opacity-60 ring-gray-200 dark:ring-white/10'"
        >
          <div class="min-w-48">
            <p class="text-lg font-semibold">
              {{ e.device_name }} · <span class="font-mono">{{ e.port }}</span>
            </p>
            <p class="text-xs text-gray-500 dark:text-gray-400">
              {{ time(e.at) }}
              <template v-if="e.building || e.room"> · {{ [e.building, e.room].filter(Boolean).join(' · ') }}</template>
              <template v-if="e.untagged_vlans.length"> · VLAN {{ e.untagged_vlans.join(', ') }}</template>
              <template v-if="e.tagged_vlans.length"> · {{ t('finder.tagged') }} {{ e.tagged_vlans.length > 8 ? `${e.tagged_vlans.slice(0, 8).join(', ')} +${e.tagged_vlans.length - 8}` : e.tagged_vlans.join(', ') }}</template>
            </p>
            <span v-if="e.link_ups > 1" class="badge badge-yellow mt-1 mr-1" :title="t('finder.flappingHint')">{{ t('finder.linkUps', { n: e.link_ups }) }}</span>
            <span v-if="!e.still_up" class="badge badge-gray mt-1">{{ t('finder.downAgain') }}</span>
            <span v-else-if="e.uplink" class="badge badge-indigo mt-1">Uplink</span>
          </div>
          <div class="min-w-0 flex-1 text-sm">
            <p v-if="e.still_up && !e.connected.length" class="flex items-center gap-2 text-gray-500 dark:text-gray-400">
              <UiSpinner class="size-4" /> {{ t('finder.noMacYet') }}
            </p>
            <div v-for="c in e.connected" :key="c.mac_address" class="mb-1">
              <span class="font-medium">{{ c.hostname || c.ip_address || c.vendor || c.mac_address }}</span>
              <span class="ml-2 font-mono text-xs text-gray-500 dark:text-gray-400">
                {{ [c.hostname || c.ip_address ? c.mac_address : null, c.ip_address && c.hostname ? c.ip_address : null, c.hostname || c.ip_address ? c.vendor : null].filter(Boolean).join(' · ') || (c.vendor ? c.mac_address : '') }}
              </span>
            </div>
            <p v-if="e.mac_count > e.connected.length" class="text-xs text-gray-500">{{ t('switchports.moreDevices', { n: e.mac_count - e.connected.length }) }}</p>
          </div>
          <div class="flex shrink-0 flex-col gap-2 sm:items-end">
            <RouterLink
              v-if="auth.can('ports.edit', sites.currentId)"
              :to="{ name: 'device', params: { id: e.device_id }, query: { tab: 'ports', port: e.port_id, edit: '1' } }"
              class="btn btn-primary btn-sm"
            >
              <PencilSquareIcon class="size-4" /> {{ t('finder.editPort') }}
            </RouterLink>
            <RouterLink
              :to="{ name: 'device', params: { id: e.device_id }, query: { tab: 'ports', port: e.port_id } }"
              class="btn btn-secondary btn-sm"
            >
              <ArrowTopRightOnSquareIcon class="size-4" /> {{ t('finder.openPort') }}
            </RouterLink>
          </div>
        </div>
      </div>
    </section>

    <div class="flex flex-wrap items-center gap-4 text-xs text-gray-600 dark:text-gray-400">
      <span v-for="s in LEGEND" :key="s" class="flex items-center gap-1.5">
        <span class="inline-block size-3.5 rounded-sm" :class="STYLE[s]" />
        {{ t(`switchports.legend.${s}`) }}
      </span>
      <span class="flex items-center gap-1.5"><span class="inline-block size-1.5 rounded-full bg-amber-400" /> PoE</span>
    </div>

    <UiSpinner v-if="loading && !result.length" class="mx-auto" />
    <p v-else-if="!switches.length" class="card p-6 text-sm text-gray-500">{{ t('switchports.none') }}</p>

    <section v-for="d in switches" :key="d.device_id" class="card">
      <header class="flex flex-wrap items-center gap-3 border-b border-gray-200 px-5 py-3 dark:border-white/10">
        <SwitchIcon :model="d.model" :status="d.status" />
        <RouterLink :to="{ name: 'device', params: { id: d.device_id } }" class="link font-semibold">{{ d.device_name }}</RouterLink>
        <span v-if="d.model_name" class="text-sm text-gray-500 dark:text-gray-400">{{ d.model_name }}</span>
        <span v-if="d.building || d.room" class="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">
          <MapPinIcon class="size-4" /> {{ [d.building, d.room].filter(Boolean).join(' · ') }}
        </span>
        <span class="ml-auto flex gap-2 text-xs">
          <span class="badge" :class="d.counts.free ? 'badge-green' : 'badge-gray'">{{ t('switchports.free', { n: d.counts.free }) }}</span>
          <span class="badge badge-blue">{{ t('switchports.active', { n: d.counts.up + d.counts.uplink }) }}</span>
          <span class="badge badge-gray">{{ t('switchports.ports', { n: d.ports.length }) }}</span>
        </span>
      </header>

      <div class="overflow-x-auto p-4">
        <div class="inline-flex min-w-max flex-col gap-2 rounded-lg bg-gray-800 p-2 2xl:p-3 shadow-inner ring-1 ring-black/20 dark:bg-gray-950 dark:ring-white/10">
          <div v-for="unit in d.units" :key="unit.unit" class="flex items-center gap-3 2xl:gap-5">
            <span v-if="d.units.length > 1" class="w-4 text-center font-mono text-[0.625rem] text-gray-400" :title="t('switchports.unit')">{{ unit.unit }}</span>
            <div v-for="block in unit.blocks" :key="block.key" class="flex">
              <div v-for="(col, ci) in block.columns" :key="ci" class="flex flex-col gap-0.5 2xl:gap-1" :class="ci > 0 ? (ci % 6 === 0 ? 'ml-2 2xl:ml-3' : 'ml-0.5 2xl:ml-1') : ''">
                <template v-for="(p, ri) in col" :key="ri">
                  <RouterLink
                    v-if="p"
                    :to="{ name: 'device', params: { id: d.device_id }, query: { tab: 'ports', port: p.id } }"
                    class="relative flex h-6 w-6 2xl:h-7 2xl:w-8 items-center justify-center rounded-sm font-mono text-[0.5625rem] 2xl:text-[0.625rem] leading-none font-semibold transition"
                    :class="[STYLE[state(p)], foundPorts.has(p.id) && 'z-10 animate-pulse ring-4 ring-amber-400']"
                    @mouseenter="showHover(p, $event)"
                    @mouseleave="hover = null"
                    @focus="showHover(p, $event as unknown as MouseEvent)"
                    @blur="hover = null"
                  >
                    {{ portLabel(p.name) }}
                    <span v-if="p.poe" class="absolute top-0.5 right-0.5 size-1.5 rounded-full bg-amber-400" />
                  </RouterLink>
                  <span v-else class="h-6 w-6 2xl:h-7 2xl:w-8" />
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- hover card -->
    <div
      v-if="hover"
      class="pointer-events-none fixed z-50 w-80 -translate-x-1/2 rounded-lg bg-white p-3 text-sm shadow-xl ring-1 ring-gray-900/10 dark:bg-gray-800 dark:ring-white/10"
      :class="hover.above ? '-translate-y-full' : ''"
      :style="{ left: `${hover.x}px`, top: `${hover.y}px` }"
    >
      <div class="flex items-center justify-between gap-3">
        <span class="font-mono font-semibold">{{ hover.port.name }}</span>
        <span class="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
          <span class="inline-block size-2.5 rounded-sm" :class="STYLE[state(hover.port)]" />
          {{ t(`switchports.legend.${state(hover.port)}`) }}
        </span>
      </div>
      <p v-for="line in facts(hover.port)" :key="line" class="mt-0.5 text-xs text-gray-600 dark:text-gray-300">{{ line }}</p>

      <div v-if="hover.port.neighbor || hover.port.connected.length" class="mt-2 border-t border-gray-100 pt-2 dark:border-white/10">
        <p class="mb-1 text-[0.6875rem] font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">{{ t('switchports.connected') }}</p>
        <p v-if="hover.port.neighbor" class="text-xs"><span class="badge badge-indigo mr-1">LLDP</span>{{ hover.port.neighbor }}</p>
        <div v-for="c in hover.port.connected" :key="c.mac_address" class="mt-1 text-xs">
          <span class="font-medium">{{ c.hostname || c.ip_address || c.vendor || c.mac_address }}</span>
          <span class="block font-mono text-[0.6875rem] text-gray-500 dark:text-gray-400">
            {{ [c.hostname || c.ip_address ? c.mac_address : null, c.hostname || c.ip_address ? c.vendor : null, c.hostname ? c.ip_address : null].filter(Boolean).join(' · ') || c.mac_address }}
          </span>
        </div>
        <p v-if="hover.port.mac_count > hover.port.connected.length" class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t('switchports.moreDevices', { n: hover.port.mac_count - hover.port.connected.length }) }}
        </p>
      </div>
      <p v-else-if="hover.port.oper_up && !hover.port.uplink" class="mt-2 text-xs text-gray-500 dark:text-gray-400">{{ t('switchports.noDevice') }}</p>
    </div>
  </div>
</template>
