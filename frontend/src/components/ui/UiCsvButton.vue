<script setup lang="ts">
/** "CSV" button of a table: exports what is currently shown (filtered and sorted). */
import { ArrowDownTrayIcon } from '@heroicons/vue/20/solid'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <button type="button" class="btn btn-secondary" :title="t('common.csvHint')">
    <slot><ArrowDownTrayIcon class="size-4" /></slot> CSV
  </button>
</template>
