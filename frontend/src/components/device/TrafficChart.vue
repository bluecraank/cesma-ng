<script setup lang="ts">
/** Small inline traffic chart (in/out bit/s) for one port; no chart library needed. */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

interface Point {
  at: string
  in_bps: number
  out_bps: number
  in_errors: number
  out_errors: number
}

const props = defineProps<{ points: Point[]; speedMbps: number | null }>()
const { t, locale } = useI18n()

const W = 560
const H = 90
const max = computed(() => Math.max(1, ...props.points.flatMap((p) => [p.in_bps, p.out_bps])))

function path(key: 'in_bps' | 'out_bps'): string {
  const n = props.points.length
  if (n < 2) return ''
  return props.points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${((i / (n - 1)) * W).toFixed(1)},${(H - (p[key] / max.value) * (H - 4)).toFixed(1)}`)
    .join(' ')
}

function rate(bps: number): string {
  if (bps >= 1e9) return `${(bps / 1e9).toFixed(2)} Gbit/s`
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(1)} Mbit/s`
  if (bps >= 1e3) return `${(bps / 1e3).toFixed(0)} kbit/s`
  return `${bps} bit/s`
}

const last = computed(() => props.points[props.points.length - 1])
const peak = computed(() => Math.max(0, ...props.points.flatMap((p) => [p.in_bps, p.out_bps])))
const errors = computed(() => props.points.reduce((n, p) => n + p.in_errors + p.out_errors, 0))
const utilization = computed(() =>
  props.speedMbps && last.value ? Math.round((Math.max(last.value.in_bps, last.value.out_bps) / (props.speedMbps * 1e6)) * 100) : null,
)
const range = computed(() => {
  const first = props.points[0]
  if (!first || !last.value) return ''
  const f = (iso: string) => new Date(iso).toLocaleString(locale.value, { dateStyle: 'short', timeStyle: 'short' })
  return `${f(first.at)} – ${f(last.value.at)}`
})
</script>

<template>
  <div>
    <p v-if="points.length < 2" class="text-xs text-gray-500">{{ t('stats.noData') }}</p>
    <template v-else>
      <svg :viewBox="`0 0 ${W} ${H}`" class="h-24 w-full max-w-xl" preserveAspectRatio="none" role="img" :aria-label="t('stats.title')">
        <path :d="path('in_bps')" fill="none" class="stroke-indigo-500" stroke-width="1.5" vector-effect="non-scaling-stroke" />
        <path :d="path('out_bps')" fill="none" class="stroke-emerald-500" stroke-width="1.5" vector-effect="non-scaling-stroke" />
      </svg>
      <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
        <span class="flex items-center gap-1"><span class="h-0.5 w-3 bg-indigo-500" /> In {{ rate(last?.in_bps ?? 0) }}</span>
        <span class="flex items-center gap-1"><span class="h-0.5 w-3 bg-emerald-500" /> Out {{ rate(last?.out_bps ?? 0) }}</span>
        <span>{{ t('stats.peak') }} {{ rate(peak) }}</span>
        <span v-if="utilization !== null">{{ t('stats.utilization') }} {{ utilization }} %</span>
        <span :class="{ 'font-medium text-red-600 dark:text-red-400': errors }">{{ t('stats.errors') }} {{ errors }}</span>
        <span>{{ range }}</span>
      </div>
    </template>
  </div>
</template>
