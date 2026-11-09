<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DeviceStatus } from '@/api/client'

const props = defineProps<{ status: DeviceStatus }>()
const { t } = useI18n()

const style = computed(
  () =>
    ({
      online: ['badge-green', 'fill-green-500'],
      offline: ['badge-red', 'fill-red-500'],
      unconfirmed: ['badge-yellow', 'fill-yellow-500'],
      unknown: ['badge-gray', 'fill-gray-400'],
    })[props.status],
)
</script>

<template>
  <span class="badge" :class="style[0]">
    <svg class="size-1.5" :class="style[1]" viewBox="0 0 6 6" aria-hidden="true"><circle cx="3" cy="3" r="3" /></svg>
    {{ t(`device.statuses.${status}`) }}
  </span>
</template>
