<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useNow } from '@/composables/useNow'
import { formatDateTime, formatRelative } from '@/utils/format'

/** A point in time as "vor 5 Min."; the exact date and time are in the tooltip. */
const props = defineProps<{ value: string | null | undefined; empty?: string }>()
const { locale } = useI18n()
const now = useNow()
const text = computed(() => (props.value ? formatRelative(props.value, locale.value, now.value) : (props.empty ?? '—')))
const exact = computed(() => (props.value ? formatDateTime(props.value, locale.value) : undefined))
</script>

<template>
  <time :datetime="value ?? undefined" :title="exact" class="tabular-nums">{{ text }}</time>
</template>
