<script setup lang="ts">
import { SparklesIcon } from '@heroicons/vue/24/outline'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { APP_VERSION, CHANGELOG } from '@/changelog'
import UiDialog from '@/components/ui/UiDialog.vue'

const open = defineModel<boolean>('open', { required: true })
const { t, locale } = useI18n()

const releases = computed(() =>
  CHANGELOG.map((r) => ({
    ...r,
    dateLabel: r.date ? new Date(r.date).toLocaleDateString(locale.value, { dateStyle: 'medium' }) : '',
  })),
)
</script>

<template>
  <UiDialog v-model:open="open" wide :title="t('patchNotes.title')">
    <div class="space-y-8">
      <section v-for="release in releases" :key="release.version">
        <div class="flex items-baseline gap-3">
          <h3 class="text-base font-semibold">v{{ release.version }}</h3>
          <span v-if="release.version === APP_VERSION" class="badge badge-brand">
            <SparklesIcon class="size-3.5" /> {{ t('patchNotes.current') }}
          </span>
          <span class="ml-auto text-xs text-gray-500 dark:text-gray-400">{{ release.dateLabel }}</span>
        </div>
        <div v-for="section in release.sections" :key="section.title" class="mt-3">
          <h4 class="text-sm font-semibold text-gray-900 dark:text-white">{{ section.title }}</h4>
          <ul class="mt-2 space-y-1.5">
            <li v-for="item in section.items" :key="item" class="flex gap-2 text-sm text-gray-700 dark:text-gray-300">
              <span class="mt-2 size-1.5 shrink-0 rounded-full bg-brand-500" />
              {{ item }}
            </li>
          </ul>
        </div>
      </section>
    </div>
    <template #footer>
      <button type="button" class="btn btn-primary" @click="open = false">{{ t('patchNotes.close') }}</button>
    </template>
  </UiDialog>
</template>
