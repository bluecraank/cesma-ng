<script setup lang="ts">
import { watch } from 'vue'
import UiConfirmHost from '@/components/ui/UiConfirmHost.vue'
import UiToaster from '@/components/ui/UiToaster.vue'
import { setLocale } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import '@/composables/useTheme'

const auth = useAuthStore()
watch(
  () => auth.user?.locale,
  (locale) => locale && setLocale(locale),
  { immediate: true },
)
</script>

<template>
  <RouterView />
  <UiToaster />
  <UiConfirmHost />
</template>
