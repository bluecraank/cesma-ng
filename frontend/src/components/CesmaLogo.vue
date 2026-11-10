<script setup lang="ts">
import '@fontsource/kdam-thmor-pro/latin-400.css'

/** Logo of cesma-on-premise (MDI "console-line" + Kdam Thmor Pro), continued as cesma-ng. */
withDefaults(defineProps<{ size?: 'md' | 'lg'; iconOnly?: boolean }>(), { size: 'md', iconOnly: false })

// Material Design Icons "console-line" (Apache 2.0)
const CONSOLE_LINE =
  'M13,19V16H21V19H13M8.5,13L2.47,7H6.71L11.67,11.95C12.25,12.54 12.25,13.5 11.67,14.07L6.74,19H2.5L8.5,13Z'
</script>

<template>
  <span class="inline-flex items-center gap-1.5 font-[Kdam_Thmor_Pro] leading-none" :class="size === 'lg' ? 'text-4xl' : 'text-2xl'">
    <svg viewBox="0 0 24 24" class="shrink-0 fill-current" :class="size === 'lg' ? 'size-10' : 'size-7'" aria-hidden="true">
      <path :d="CONSOLE_LINE" />
    </svg>
    <span v-if="!iconOnly">cesma<span class="text-brand-400">-ng</span></span>
  </span>
</template>
