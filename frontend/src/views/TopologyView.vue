<script setup lang="ts">
import { ArrowsPointingOutIcon } from '@heroicons/vue/20/solid'
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import type { components } from '@/api/schema'
import { useNotify } from '@/composables/useNotify'
import { useTheme } from '@/composables/useTheme'
import { useSitesStore } from '@/stores/sites'

type Topology = components['schemas']['TopologyOut']

const { t } = useI18n()
const notify = useNotify()
const router = useRouter()
const sites = useSitesStore()
const { theme } = useTheme()

const container = ref<HTMLDivElement | null>(null)
const showExternal = ref(false)
const counts = ref({ nodes: 0, edges: 0 })
let cy: Core | null = null

const STATUS_COLORS: Record<string, string> = {
  online: '#22c55e',
  offline: '#ef4444',
  unconfirmed: '#eab308',
  unknown: '#9ca3af',
}

function speed(mbps: number | null | undefined): string {
  if (!mbps) return ''
  return mbps >= 1000 ? ` ${mbps / 1000}G` : ` ${mbps}M`
}

function elements(data: Topology): ElementDefinition[] {
  return [
    ...data.nodes.map((n) => ({
      data: { id: n.id, label: n.label, sub: n.model, deviceId: n.device_id, kind: n.kind, color: STATUS_COLORS[n.status] ?? '#9ca3af' },
    })),
    ...data.edges.map((e) => ({
      data: { id: e.id, source: e.source, target: e.target, label: `${e.source_port} ↔ ${e.target_port}${speed(e.speed_mbps)}`, up: e.up },
    })),
  ]
}

function style(): cytoscape.StylesheetJson {
  const dark = theme.value === 'dark'
  const text = dark ? '#e5e7eb' : '#111827'
  const muted = dark ? '#9ca3af' : '#6b7280'
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        label: 'data(label)',
        color: text,
        'font-size': 12,
        'font-weight': 600,
        'text-valign': 'bottom',
        'text-margin-y': 6,
        width: 30,
        height: 30,
        shape: 'round-rectangle',
        'border-width': 2,
        'border-color': dark ? '#111827' : '#ffffff',
      },
    },
    { selector: 'node[kind = "external"]', style: { shape: 'ellipse', width: 16, height: 16, 'font-weight': 400, 'font-size': 10, color: muted, 'background-color': '#818cf8' } },
    {
      selector: 'edge',
      style: {
        width: 2,
        'line-color': dark ? '#4b5563' : '#cbd5e1',
        'curve-style': 'bezier',
        label: 'data(label)',
        'font-size': 9,
        color: muted,
        'text-rotation': 'autorotate',
        'text-background-color': dark ? '#030712' : '#f9fafb',
        'text-background-opacity': 1,
        'text-background-padding': '2px',
      },
    },
    { selector: 'edge[!up]', style: { 'line-color': '#ef4444', 'line-style': 'dashed' } },
    { selector: 'node:selected', style: { 'border-color': '#6366f1', 'border-width': 3 } },
  ]
}

async function load(): Promise<void> {
  if (sites.currentId === null || !container.value) return
  await notify.run(async () => {
    const data = await api.get<Topology>(`/sites/${sites.currentId}/topology`, { include_external: showExternal.value })
    counts.value = { nodes: data.nodes.length, edges: data.edges.length }
    cy?.destroy()
    cy = cytoscape({
      container: container.value,
      elements: elements(data),
      style: style(),
      layout: { name: 'cose', animate: false, padding: 40, nodeRepulsion: () => 8000, idealEdgeLength: () => 140 },
      wheelSensitivity: 0.3,
    })
    cy.on('tap', 'node', (event) => {
      const deviceId = event.target.data('deviceId')
      if (deviceId) void router.push({ name: 'device', params: { id: deviceId }, query: { tab: 'lldp' } })
    })
  })
}

watch([() => sites.currentId, showExternal, container], load, { immediate: true })
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
      <div class="flex items-center gap-4">
        <label class="flex items-center gap-2 text-sm"><input v-model="showExternal" type="checkbox" class="accent-indigo-600" /> {{ t('topology.external') }}</label>
        <button type="button" class="btn btn-secondary" @click="cy?.fit(undefined, 40)"><ArrowsPointingOutIcon class="size-4" /> {{ t('topology.fit') }}</button>
      </div>
    </div>
    <div class="card relative min-h-96 flex-1 overflow-hidden">
      <!-- cytoscape sets position: relative on its container, so it must not be the absolute element -->
      <div class="absolute inset-0"><div ref="container" class="size-full" /></div>
      <div class="absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-md bg-white/80 px-3 py-2 text-xs backdrop-blur dark:bg-gray-900/80">
        <span v-for="(color, status) in STATUS_COLORS" :key="status" class="flex items-center gap-1.5">
          <span class="size-2.5 rounded-sm" :style="{ background: color }" /> {{ t(`device.statuses.${status}`) }}
        </span>
        <span class="flex items-center gap-1.5"><span class="h-0.5 w-4 border-t-2 border-dashed border-red-500" /> {{ t('topology.linkDown') }}</span>
      </div>
    </div>
  </div>
</template>
