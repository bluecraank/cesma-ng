<script setup lang="ts">
/**
 * LLDP topology as a star: the core switch in the centre, the switches behind it in rings.
 * The layout is computed (not simulated), so it is fast and looks the same after every reload.
 */
import { ArrowsPointingOutIcon } from '@heroicons/vue/20/solid'
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import type { components } from '@/api/schema'
import { useNotify } from '@/composables/useNotify'
import { useTheme } from '@/composables/useTheme'
import { useSitesStore } from '@/stores/sites'
import { starLayout } from '@/utils/starLayout'

type Topology = components['schemas']['TopologyOut']

const { t } = useI18n()
const notify = useNotify()
const router = useRouter()
const sites = useSitesStore()
const { theme } = useTheme()

const container = ref<HTMLDivElement | null>(null)
const showExternal = ref(false)
const data = ref<Topology | null>(null)
const center = ref('') // "" = automatic
let cy: Core | null = null

const counts = computed(() => ({ nodes: data.value?.nodes.length ?? 0, edges: data.value?.edges.length ?? 0 }))
const switches = computed(() =>
  (data.value?.nodes ?? []).filter((n) => n.kind === 'switch').sort((a, b) => a.label.localeCompare(b.label)),
)

const STATUS_COLORS: Record<string, string> = {
  online: '#22c55e',
  offline: '#ef4444',
  unconfirmed: '#eab308',
  unknown: '#9ca3af',
}

const centerKey = (): string => `cesma.topologyCenter.${sites.currentId}`
function readCenter(): string {
  try {
    return localStorage.getItem(centerKey()) ?? ''
  } catch {
    return ''
  }
}
function saveCenter(value: string): void {
  try {
    if (value) localStorage.setItem(centerKey(), value)
    else localStorage.removeItem(centerKey())
  } catch {
    /* storage unavailable */
  }
}

function speed(mbps: number | null | undefined): string {
  if (!mbps) return ''
  return mbps >= 1000 ? ` ${mbps / 1000}G` : ` ${mbps}M`
}

/** One line per switch pair; parallel links (LAG members) are listed in the label. */
function mergedEdges(topology: Topology): ElementDefinition[] {
  const pairs = new Map<string, { source: string; target: string; ports: string[]; down: boolean }>()
  for (const e of [...topology.edges].sort((a, b) => a.id.localeCompare(b.id))) {
    const [source, target] = [e.source, e.target].sort() as [string, string]
    const flipped = source !== e.source
    const key = `${source}|${target}`
    const entry = pairs.get(key) ?? { source, target, ports: [], down: false }
    entry.ports.push((flipped ? `${e.target_port} ↔ ${e.source_port}` : `${e.source_port} ↔ ${e.target_port}`) + speed(e.speed_mbps))
    entry.down ||= !e.up
    pairs.set(key, entry)
  }
  return [...pairs.entries()].map(([key, p]) => ({
    data: {
      id: key,
      source: p.source,
      target: p.target,
      label: p.ports.length > 3 ? `${t('topology.links', { n: p.ports.length })}: ${p.ports.slice(0, 2).join(', ')} …` : p.ports.join('\n'),
      count: p.ports.length,
      up: !p.down,
    },
  }))
}

function style(): cytoscape.StylesheetJson {
  const dark = theme.value === 'dark'
  const text = dark ? '#e5e7eb' : '#111827'
  const muted = dark ? '#9ca3af' : '#6b7280'
  const bg = dark ? '#030712' : '#f9fafb'
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        label: 'data(label)',
        color: text,
        'font-size': 13,
        'font-weight': 600,
        'text-valign': 'bottom',
        'text-margin-y': 7,
        'text-background-color': bg,
        'text-background-opacity': 0.85,
        'text-background-padding': '2px',
        'text-background-shape': 'roundrectangle',
        width: 34,
        height: 34,
        shape: 'round-rectangle',
        'border-width': 3,
        'border-color': dark ? '#1f2937' : '#ffffff',
      },
    },
    { selector: 'node.root', style: { width: 50, height: 50, 'font-size': 15, 'border-color': '#2b5fae', 'border-width': 4 } },
    {
      selector: 'node[kind = "external"]',
      style: { shape: 'ellipse', width: 18, height: 18, 'font-weight': 400, 'font-size': 11, color: muted, 'background-color': '#92b9e6' },
    },
    {
      selector: 'edge',
      style: {
        width: 'mapData(count, 1, 4, 2.5, 6)',
        'line-color': dark ? '#64748b' : '#94a3b8',
        'curve-style': 'straight',
        label: 'data(label)',
        'font-size': 10,
        'min-zoomed-font-size': 12, // port names only when zoomed in (or highlighted)
        color: muted,
        'text-wrap': 'wrap',
        'text-rotation': 'autorotate',
        'text-background-color': bg,
        'text-background-opacity': 1,
        'text-background-padding': '2px',
      },
    },
    { selector: 'edge[!up]', style: { 'line-color': '#ef4444', 'line-style': 'dashed' } },
    { selector: '.faded', style: { opacity: 0.15 } },
    { selector: 'edge.highlight', style: { 'line-color': '#2b5fae', 'min-zoomed-font-size': 0, color: text, 'z-index': 10 } },
    { selector: 'edge.highlight[!up]', style: { 'line-color': '#ef4444' } },
    { selector: 'node.highlight', style: { 'border-color': '#2b5fae' } },
  ]
}

function render(): void {
  if (!data.value || !container.value) return
  const topology = data.value
  const edges = mergedEdges(topology)
  const { positions, roots } = starLayout(
    topology.nodes.map((n) => n.id),
    edges.map((e) => [e.data.source as string, e.data.target as string]),
    { root: center.value || null, leaves: topology.nodes.filter((n) => n.kind !== 'switch').map((n) => n.id) },
  )
  const elements: ElementDefinition[] = [
    ...topology.nodes.map((n) => ({
      data: { id: n.id, label: n.label, deviceId: n.device_id, kind: n.kind, color: STATUS_COLORS[n.status] ?? '#9ca3af' },
      position: positions.get(n.id) ?? { x: 0, y: 0 },
      classes: roots.includes(n.id) ? 'root' : '',
    })),
    ...edges,
  ]
  cy?.destroy()
  cy = cytoscape({
    container: container.value,
    elements,
    style: style(),
    layout: { name: 'preset', fit: true, padding: 60 },
    minZoom: 0.1,
    maxZoom: 3,
    wheelSensitivity: 0.4,
    textureOnViewport: true, // smooth panning/zooming with many nodes
    boxSelectionEnabled: false,
  })
  cy.on('tap', 'node', (event) => {
    const deviceId = event.target.data('deviceId')
    if (deviceId) void router.push({ name: 'device', params: { id: deviceId }, query: { tab: 'lldp' } })
  })
  // hovering a switch shows its links and neighbours, everything else fades
  cy.on('mouseover', 'node', (event) => {
    const hood = event.target.closedNeighborhood()
    cy!.elements().not(hood).addClass('faded')
    hood.edges().addClass('highlight')
    hood.nodes().addClass('highlight')
  })
  cy.on('mouseout', 'node', () => cy!.elements().removeClass('faded highlight'))
}

async function load(): Promise<void> {
  if (sites.currentId === null) return
  await notify.run(async () => {
    data.value = await api.get<Topology>(`/sites/${sites.currentId}/topology`, { include_external: showExternal.value })
  })
}

watch(
  () => sites.currentId,
  () => (center.value = readCenter()),
  { immediate: true },
)
watch(center, saveCenter)
watch([() => sites.currentId, showExternal], load, { immediate: true })
watch([data, center, container], render)
watch(theme, () => cy?.style(style()))
onBeforeUnmount(() => cy?.destroy())
</script>

<template>
  <div class="flex h-[calc(100vh-8rem)] flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="page-title">{{ t('topology.title') }}</h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t('topology.hint', counts) }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-4">
        <label class="flex items-center gap-2 text-sm">
          {{ t('topology.center') }}
          <select v-model="center" class="input w-56">
            <option value="">{{ t('topology.auto') }}</option>
            <option v-for="n in switches" :key="n.id" :value="n.id">{{ n.label }}</option>
          </select>
        </label>
        <label class="flex items-center gap-2 text-sm"><input v-model="showExternal" type="checkbox" class="accent-brand-600" /> {{ t('topology.external') }}</label>
        <button type="button" class="btn btn-secondary" @click="cy?.fit(undefined, 60)"><ArrowsPointingOutIcon class="size-4" /> {{ t('topology.fit') }}</button>
      </div>
    </div>
    <div class="card relative min-h-96 flex-1 overflow-hidden">
      <!-- cytoscape sets position: relative on its container, so it must not be the absolute element -->
      <div class="absolute inset-0"><div ref="container" class="size-full" /></div>
      <div class="absolute bottom-3 left-3 flex flex-wrap items-center gap-3 rounded-md bg-white/80 px-3 py-2 text-xs backdrop-blur dark:bg-gray-900/80">
        <span v-for="(color, status) in STATUS_COLORS" :key="status" class="flex items-center gap-1.5">
          <span class="size-2.5 rounded-sm" :style="{ background: color }" /> {{ t(`device.statuses.${status}`) }}
        </span>
        <span class="flex items-center gap-1.5"><span class="h-0.5 w-4 border-t-2 border-dashed border-red-500" /> {{ t('topology.linkDown') }}</span>
        <span class="text-gray-500 dark:text-gray-400">· {{ t('topology.labelsHint') }}</span>
      </div>
    </div>
  </div>
</template>
