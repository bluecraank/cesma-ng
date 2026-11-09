<script setup lang="ts">
import { ExclamationCircleIcon } from '@heroicons/vue/20/solid'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import CesmaLogo from '@/components/CesmaLogo.vue'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = null
  try {
    await auth.login(username.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect.startsWith('/') ? redirect : '/')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('login.failed')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen flex-col justify-center px-6 py-12">
    <div class="mx-auto flex w-full max-w-sm flex-col items-center gap-4">
      <h1 class="text-gray-900 dark:text-white"><CesmaLogo size="lg" /></h1>
      <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('login.title') }}</p>
    </div>

    <form class="card mx-auto mt-8 w-full max-w-sm space-y-5 p-6 sm:p-8" @submit.prevent="submit">
      <div v-if="error" class="flex gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-400">
        <ExclamationCircleIcon class="size-5 shrink-0" />
        {{ error }}
      </div>
      <div class="field">
        <label class="label" for="username">{{ t('login.username') }}</label>
        <input id="username" v-model="username" class="input" autocomplete="username" autofocus required />
      </div>
      <div class="field">
        <label class="label" for="password">{{ t('login.password') }}</label>
        <input id="password" v-model="password" type="password" class="input" autocomplete="current-password" required />
      </div>
      <button type="submit" class="btn btn-primary w-full" :disabled="busy">
        <UiSpinner v-if="busy" />
        {{ t('login.submit') }}
      </button>
    </form>
  </div>
</template>
