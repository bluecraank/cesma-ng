<script setup lang="ts">
import { computed } from 'vue'
import { MAC_TYPE_ICONS, type MacTypeIconName } from '@/utils/macTypeIcons'

const props = defineProps<{ icon: string | null | undefined }>()
const component = computed(() => (props.icon ? MAC_TYPE_ICONS[props.icon as MacTypeIconName] : null))
</script>

<template>
  <component :is="component" v-if="component" class="size-4 shrink-0 text-indigo-500" />
  <span v-else class="size-4 shrink-0" />
</template>
