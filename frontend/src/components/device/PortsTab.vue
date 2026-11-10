<script setup lang="ts">
import { BoltIcon, ChevronDownIcon, ChevronRightIcon, MagnifyingGlassIcon, PencilSquareIcon, XMarkIcon } from '@heroicons/vue/20/solid'
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type DeviceVlan, type FdbEntry, type Port } from '@/api/client'
import PortEditDialog from './PortEditDialog.vue'
import TrafficChart from './TrafficChart.vue'
import type { components } from '@/api/schema'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{
  deviceId: number
  siteId: number
  ports: Port[]
  vlans: DeviceVlan[]
  canEdit: boolean
  /** scroll to this port, open and highlight it */
  focusPortId?: number | null
  /** also open the edit dialog (VLANs etc.) for the focused port */
  editFocused?: boolean
}>()
const emit = defineEmits<{ changed: [] }>()
const { t, locale } = useI18n()

const search = ref('')
const onlyUp = ref(false)
const onlyUplinks = ref(false)
const expanded = ref<number | null>(null)
const macs = ref<FdbEntry[]>([])
const stats = ref<components['schemas']['PortStatsOut'] | null>(null)
const history = ref<components['schemas']['PortHistoryOut'] | null>(null)
const selected = ref<Set<number>>(new Set())
const editOpen = ref(false)
const editPorts = ref<Port[]>([])

// Shift-click selects the range from the last clicked port (in the visible order).
let anchor: number | null = null
function toggleSelect(id: number, event: MouseEvent): void {
  const next = new Set(selected.value)
  const ids = rows.value.map((p) => p.id)
  if (event.shiftKey && anchor !== null && ids.includes(anchor)) {
    const from = Math.min(ids.indexOf(anchor), ids.indexOf(id))
    const to = Math.max(ids.indexOf(anchor), ids.indexOf(id))
    // The range gets the state of the last clicked port (select or deselect).
    const select = selected.value.has(anchor)
    for (const rangeId of ids.slice(from, to + 1)) {
      if (select) next.add(rangeId)
      else next.delete(rangeId)
    }
  } else if (next.has(id)) next.delete(id)
  else next.add(id)
  anchor = id
  selected.value = next
}

const selectedPorts = computed(() => props.ports.filter((p) => selected.value.has(p.id)))

// Jump to a port: reset the filters, open it and scroll it into the middle of the screen.
const highlighted = ref<number | null>(null)
watch(
  () => [props.focusPortId, props.ports.length] as const,
  async ([id]) => {
    const port = props.ports.find((p) => p.id === id)
    if (!port || highlighted.value === port.id) return
    search.value = ''
    onlyUp.value = false
    onlyUplinks.value = false
    highlighted.value = port.id
    void toggle(port)
    if (props.editFocused && props.canEdit) edit([port])
    await nextTick()
    document.getElementById(`port-${port.id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  },
  { immediate: true },
)

function toggleAll(): void {
  selected.value = selected.value.size === rows.value.length ? new Set() : new Set(rows.value.map((p) => p.id))
}

function edit(ports: Port[]): void {
  editPorts.value = ports
  editOpen.value = true
}

function onApplied(): void {
  selected.value = new Set()
  emit('changed')
}

const rows = computed(() => {
  const q = search.value.trim().toLowerCase()
  return props.ports.filter(
    (p) =>
      (!onlyUp.value || p.oper_up) &&
      (!onlyUplinks.value || p.is_uplink) &&
      (!q ||
        [p.name, p.description, p.neighbor ?? '', ...p.untagged_vlans.map(String), ...p.tagged_vlans.map(String)].some((v) =>
          v.toLowerCase().includes(q),
        )),
  )
})

async function toggle(port: Port): Promise<void> {
  if (expanded.value === port.id) {
    expanded.value = null
    return
  }
  expanded.value = port.id
  stats.value = null
  history.value = null
  ;[macs.value, stats.value, history.value] = await Promise.all([
    port.mac_count ? api.get<FdbEntry[]>(`/devices/${props.deviceId}/fdb`, { port_id: port.id }) : Promise.resolve([]),
    api.get<components['schemas']['PortStatsOut']>(`/devices/${props.deviceId}/ports/${port.id}/stats`).catch(() => null),
    api.get<components['schemas']['PortHistoryOut']>(`/devices/${props.deviceId}/ports/${port.id}/history`).catch(() => null),
  ])
}

/** "description: alt → neu, untagged: 10 → 20" */
function describeChange(old: unknown, now: unknown): string {
  const before = (old ?? {}) as Record<string, unknown>
  const after = (now ?? {}) as Record<string, unknown>
  const show = (v: unknown): string => (Array.isArray(v) ? v.join(', ') || '—' : v === null || v === '' ? '—' : String(v))
  return Object.keys(after)
    .map((key) => `${t(`history.fields.${key}`)}: ${show(before[key])} → ${show(after[key])}`)
    .join(' · ')
}

const EVENT_STYLE: Record<string, string> = {
  link_up: 'bg-green-500',
  link_down: 'bg-gray-400',
  speed: 'bg-amber-500',
  configured: 'bg-indigo-500',
  changed: 'bg-orange-500',
}

function speed(mbps: number | null): string {
  if (!mbps) return ''
  return mbps >= 1000 ? `${mbps / 1000}G` : `${mbps}M`
}

function vlanList(vids: number[], max = 6): string {
  return vids.length > max ? `${vids.slice(0, max).join(', ')} +${vids.length - max}` : vids.join(', ')
}

const poeBadge = { delivering: 'badge-green', searching: 'badge-gray', disabled: 'badge-gray', fault: 'badge-red' } as const
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-4">
      <div class="relative">
        <MagnifyingGlassIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
        <input v-model="search" class="input w-64 pl-8" :placeholder="t('common.search')" />
      </div>
      <label class="flex items-center gap-2 text-sm"><input v-model="onlyUp" type="checkbox" class="rounded accent-indigo-600" /> {{ t('ports.onlyUp') }}</label>
      <label class="flex items-center gap-2 text-sm"><input v-model="onlyUplinks" type="checkbox" class="rounded accent-indigo-600" /> {{ t('ports.onlyUplinks') }}</label>
      <span class="ml-auto text-sm text-gray-500 dark:text-gray-400">{{ rows.length }} / {{ ports.length }}</span>
    </div>

    <!-- Selection bar: stays visible while scrolling through long port lists -->
    <div
      v-if="canEdit && selected.size"
      class="sticky top-16 z-10 flex flex-wrap items-center gap-3 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm text-white shadow-lg"
    >
      <span class="font-medium">{{ t('change.selected', { n: selected.size }) }}</span>
      <span class="truncate font-mono text-xs text-indigo-100">{{ selectedPorts.map((p) => p.name).join(', ') }}</span>
      <span class="hidden text-xs text-indigo-200 lg:inline">{{ t('change.shiftHint') }}</span>
      <div class="ml-auto flex gap-2">
        <button type="button" class="btn btn-sm bg-white text-indigo-700 hover:bg-indigo-50" @click="edit(selectedPorts)">
          <PencilSquareIcon class="size-4" /> {{ t('change.editPorts', { n: selected.size }) }}
        </button>
        <button type="button" class="rounded-md p-1.5 text-indigo-100 hover:bg-white/10" :title="t('change.clearSelection')" @click="selected = new Set()">
          <XMarkIcon class="size-4" />
        </button>
      </div>
    </div>

    <p v-if="!ports.length" class="card p-6 text-sm text-gray-500">{{ t('ports.noData') }}</p>

    <div v-else class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th v-if="canEdit" class="w-6">
              <input type="checkbox" class="accent-indigo-600" :title="t('change.selectAll')" :checked="selected.size > 0 && selected.size === rows.length" @change="toggleAll" />
            </th>
            <th class="w-6" />
            <th>{{ t('ports.port') }}</th>
            <th>{{ t('ports.status') }}</th>
            <th>{{ t('ports.description') }}</th>
            <th>{{ t('ports.untagged') }}</th>
            <th>{{ t('ports.tagged') }}</th>
            <th>{{ t('ports.poe') }}</th>
            <th>{{ t('ports.neighbor') }}</th>
            <th class="text-right">{{ t('ports.macs') }}</th>
            <th>{{ t('ports.lastChange') }}</th>
            <th v-if="canEdit" class="w-8" />
          </tr>
        </thead>
        <tbody>
          <template v-for="p in rows" :key="p.id">
            <tr
              :id="`port-${p.id}`"
              class="cursor-pointer scroll-mt-32"
              :class="{
                'bg-indigo-50/50 dark:bg-indigo-500/5': selected.has(p.id),
                'outline-2 -outline-offset-2 outline-amber-400 bg-amber-50 dark:bg-amber-400/10': highlighted === p.id,
              }"
              @click="toggle(p)"
            >
              <td v-if="canEdit" class="select-none" @click.stop="toggleSelect(p.id, $event)">
                <input type="checkbox" class="pointer-events-none accent-indigo-600" :checked="selected.has(p.id)" tabindex="-1" />
              </td>
              <td class="text-gray-400">
                <ChevronDownIcon v-if="expanded === p.id" class="size-4" />
                <ChevronRightIcon v-else class="size-4" />
              </td>
              <td class="font-mono font-medium whitespace-nowrap text-gray-900 dark:text-white">
                {{ p.name }}
                <span v-if="p.kind === 'lag'" class="badge badge-indigo ml-1 font-sans">{{ t('ports.lag') }}</span>
                <span v-else-if="p.is_uplink" class="badge badge-blue ml-1 font-sans">{{ t('ports.uplink') }}</span>
              </td>
              <td class="whitespace-nowrap">
                <span v-if="!p.admin_up" class="badge badge-gray">{{ t('ports.adminDown') }}</span>
                <span v-else-if="p.oper_up" class="badge badge-green">{{ t('ports.up') }} {{ speed(p.speed_mbps) }}</span>
                <span v-else class="badge badge-gray">{{ t('ports.down') }}</span>
              </td>
              <td class="max-w-56 truncate" :title="p.description">{{ p.description }}</td>
              <td class="font-mono text-xs whitespace-nowrap">
                {{ p.untagged_vlans.join(', ') }}
              </td>
              <td class="font-mono text-xs" :title="p.tagged_vlans.join(', ')">{{ vlanList(p.tagged_vlans) }}</td>
              <td>
                <span v-if="p.poe" class="badge" :class="poeBadge[p.poe]">
                  <BoltIcon v-if="p.poe === 'delivering'" class="size-3" />{{ t(`ports.poeStates.${p.poe}`) }}
                </span>
              </td>
              <td class="max-w-48 truncate" @click.stop>
                <RouterLink v-if="p.neighbor_device_id" :to="{ name: 'device', params: { id: p.neighbor_device_id } }" class="link">{{ p.neighbor }}</RouterLink>
                <span v-else :title="p.neighbor ?? ''">{{ p.neighbor }}</span>
              </td>
              <td class="text-right tabular-nums">{{ p.mac_count || '' }}</td>
              <td class="text-xs whitespace-nowrap text-gray-500 tabular-nums dark:text-gray-400">
                {{ p.last_change_at ? formatDateTime(p.last_change_at, locale) : '' }}
              </td>
              <td v-if="canEdit" @click.stop>
                <button type="button" class="btn-icon" :title="t('change.edit')" @click="edit([p])"><PencilSquareIcon class="size-4" /></button>
              </td>
            </tr>
            <tr v-if="expanded === p.id" class="bg-gray-50 hover:bg-gray-50 dark:bg-white/[0.02]">
              <td :colspan="canEdit ? 2 : 1" />
              <td :colspan="canEdit ? 10 : 9" class="py-3">
                <div class="grid gap-x-8 gap-y-1 text-xs sm:grid-cols-2 lg:grid-cols-4">
                  <div><span class="text-gray-500">ifIndex:</span> {{ p.if_index }}</div>
                  <div><span class="text-gray-500">PVID:</span> {{ p.pvid ?? '—' }}</div>
                  <div><span class="text-gray-500">MAC:</span> <span class="font-mono">{{ p.mac_address ?? '—' }}</span></div>
                  <div><span class="text-gray-500">{{ t('ports.tagged') }}:</span> {{ p.tagged_vlans.join(', ') || '—' }}</div>
                </div>
                <TrafficChart v-if="stats" class="mt-3" :points="stats.points" :speed-mbps="stats.speed_mbps" />
                <table v-if="macs.length" class="mt-3 text-xs">
                  <tr v-for="m in macs" :key="`${m.vid}-${m.mac_address}`">
                    <td class="py-0.5 pr-6 font-mono">{{ m.mac_address }}</td>
                    <td class="py-0.5 pr-6">VLAN {{ m.vid ?? '?' }}</td>
                    <td class="py-0.5 font-mono">{{ m.ip_addresses.join(', ') }}</td>
                  </tr>
                </table>
                <div v-if="history" class="mt-4 grid gap-6 lg:grid-cols-2">
                  <div>
                    <p class="mb-2 text-xs font-semibold tracking-wide text-gray-500 uppercase">{{ t('history.events') }}</p>
                    <ol v-if="history.events.length" class="max-h-64 space-y-1.5 overflow-y-auto pr-2 text-xs">
                      <li v-for="(e, i) in history.events" :key="i" class="flex gap-2">
                        <span class="mt-1 size-2 shrink-0 rounded-full" :class="EVENT_STYLE[e.kind] ?? 'bg-gray-400'" />
                        <span class="w-28 shrink-0 text-gray-500 tabular-nums">{{ formatDateTime(e.at, locale) }}</span>
                        <span class="min-w-0">
                          <span class="font-medium">{{ t(`history.kinds.${e.kind}`) }}</span>
                          <template v-if="e.kind === 'speed'"> {{ speed(e.old as number) || '—' }} → {{ speed(e.new as number) }}</template>
                          <template v-else-if="e.new"> – {{ describeChange(e.old, e.new) }}</template>
                          <span v-if="e.actor" class="text-gray-500"> ({{ e.actor }})</span>
                        </span>
                      </li>
                    </ol>
                    <p v-else class="text-xs text-gray-500">{{ t('history.noEvents') }}</p>
                  </div>
                  <div>
                    <p class="mb-2 text-xs font-semibold tracking-wide text-gray-500 uppercase">{{ t('history.devices') }}</p>
                    <table v-if="history.devices.length" class="w-full text-xs">
                      <tr v-for="d in history.devices" :key="d.mac_address" class="align-top">
                        <td class="py-0.5 pr-3 font-mono">{{ d.mac_address }}</td>
                        <td class="py-0.5 pr-3">
                          {{ d.hostname || d.ip_address || '' }}
                          <span v-if="d.vendor" class="block text-gray-500">{{ d.vendor }}</span>
                        </td>
                        <td class="py-0.5 text-right whitespace-nowrap text-gray-500 tabular-nums">
                          {{ formatDateTime(d.first_seen_at, locale) }} – {{ formatDateTime(d.last_seen_at, locale) }}
                        </td>
                      </tr>
                    </table>
                    <p v-else class="text-xs text-gray-500">{{ t('history.noDevices') }}</p>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <PortEditDialog v-model:open="editOpen" :device-id="deviceId" :site-id="siteId" :ports="editPorts" :vlans="vlans" @applied="onApplied" />
  </div>
</template>
