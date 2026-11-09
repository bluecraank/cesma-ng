<script setup lang="ts">
/** Small switch symbol: colour by vendor, dot by status (front of the device list). */
import { computed } from 'vue'
import type { DeviceModel, DeviceStatus } from '@/api/client'

const props = defineProps<{ model: DeviceModel; status: DeviceStatus; title?: string }>()

const VENDOR: Record<DeviceModel, { tile: string; label: string }> = {
  dell_n1500: { tile: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', label: 'N' },
  dell_os10: { tile: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300', label: '10' },
  aruba_os_switch: { tile: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300', label: 'HP' },
  aruba_cx: { tile: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300', label: 'CX' },
}
const DOT: Record<DeviceStatus, string> = {
  online: 'bg-green-500',
  offline: 'bg-red-500',
  unconfirmed: 'bg-yellow-400',
  unknown: 'bg-gray-400',
}
const vendor = computed(() => VENDOR[props.model] ?? VENDOR.dell_n1500)
</script>

<template>
  <span class="relative inline-flex size-9 shrink-0 flex-col items-center justify-center rounded-lg" :class="vendor.tile" :title="title">
    <!-- front panel with two rows of ports -->
    <svg viewBox="0 0 24 12" class="h-3 w-6" aria-hidden="true">
      <rect x="0.75" y="0.75" width="22.5" height="10.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5" />
      <g fill="currentColor">
        <rect v-for="i in 6" :key="`a${i}`" :x="2 + (i - 1) * 3.4" y="3" width="2.2" height="2" rx="0.4" />
        <rect v-for="i in 6" :key="`b${i}`" :x="2 + (i - 1) * 3.4" y="7" width="2.2" height="2" rx="0.4" />
      </g>
    </svg>
    <span class="mt-0.5 text-[9px] leading-none font-bold">{{ vendor.label }}</span>
    <span class="absolute -top-0.5 -right-0.5 size-2.5 rounded-full ring-2 ring-white dark:ring-gray-900" :class="DOT[status]" />
  </span>
</template>
