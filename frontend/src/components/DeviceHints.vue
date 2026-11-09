<script setup lang="ts">
/** Setup problems of one device (missing credentials, unreachable) with what to do. */
import { ExclamationTriangleIcon, XCircleIcon } from '@heroicons/vue/20/solid'
import { useI18n } from 'vue-i18n'
import type { DeviceHint } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

defineProps<{ hints: DeviceHint[] }>()
const { t } = useI18n()
const auth = useAuthStore()
</script>

<template>
  <ul v-if="hints.length" class="space-y-2">
    <li
      v-for="h in hints"
      :key="h.code"
      class="flex gap-3 rounded-lg p-3 text-sm ring-1"
      :class="h.level === 'error' ? 'bg-red-50 text-red-800 ring-red-600/20 dark:bg-red-500/10 dark:text-red-300' : 'bg-yellow-50 text-yellow-800 ring-yellow-600/20 dark:bg-yellow-500/10 dark:text-yellow-300'"
    >
      <XCircleIcon v-if="h.level === 'error'" class="size-5 shrink-0" />
      <ExclamationTriangleIcon v-else class="size-5 shrink-0" />
      <div class="min-w-0">
        <p class="font-medium">{{ t(`hints.${h.code}.title`, { profile: h.detail }) }}</p>
        <p class="mt-0.5 opacity-90">{{ t(`hints.${h.code}.fix`, { profile: h.detail }) }}</p>
        <p v-if="h.detail && ['unreachable', 'never_polled'].includes(h.code)" class="mt-1 font-mono text-xs break-all opacity-80">{{ h.detail }}</p>
        <RouterLink
          v-if="auth.isSuperadmin && !['unreachable', 'never_polled'].includes(h.code)"
          :to="{ name: 'admin-credentials' }"
          class="mt-1 inline-block font-medium underline"
        >
          {{ t('hints.openCredentials') }}
        </RouterLink>
      </div>
    </li>
  </ul>
</template>
