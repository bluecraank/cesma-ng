<script setup lang="ts">
/**
 * The task list at the bottom of every page (like "Recent Tasks" in vCenter): recent jobs of
 * all visible sites, who started them, when, and how far they got. Folds down to one line.
 */
import { CheckCircleIcon, ChevronDownIcon, ChevronRightIcon, ChevronUpIcon, ClockIcon, XCircleIcon } from '@heroicons/vue/20/solid'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Job } from '@/api/client'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import UiTime from '@/components/ui/UiTime.vue'
import { useJobsStore } from '@/stores/jobs'
import { useSitesStore } from '@/stores/sites'

const { t } = useI18n()
const store = useJobsStore()
const sites = useSitesStore()

const OPEN_KEY = 'cesma.taskPanel'
const open = ref(readOpen())
function readOpen(): boolean {
  try {
    return localStorage.getItem(OPEN_KEY) === '1'
  } catch {
    return false
  }
}
watch(open, (value) => {
  try {
    localStorage.setItem(OPEN_KEY, value ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
})

// The page keeps its last lines and the toasts stay above the panel: its height as CSS variable.
const root = ref<HTMLElement | null>(null)
let observer: ResizeObserver | undefined
onMounted(() => {
  store.start()
  observer = new ResizeObserver(([entry]) => {
    const height = entry?.borderBoxSize?.[0]?.blockSize ?? root.value?.offsetHeight ?? 0
    document.documentElement.style.setProperty('--taskbar-h', `${Math.ceil(height)}px`)
  })
  if (root.value) observer.observe(root.value)
})
onUnmounted(() => {
  store.stop()
  observer?.disconnect()
  document.documentElement.style.removeProperty('--taskbar-h')
})

const running = computed(() => store.jobs.filter((j) => j.status === 'running').length)
const waiting = computed(() => store.jobs.filter((j) => j.status === 'pending').length)
const latest = computed(() => store.jobs[0])
const manySites = computed(() => sites.sites.length > 1)
/** the job whose log is shown below its row */
const expanded = ref<number | null>(null)
/** failed switches are marked red in the log */
const logLines = (job: Job): string[] => (job.log || '—').trimEnd().split('\n')
const toggleLog = (job: Job): void => {
  expanded.value = expanded.value === job.id ? null : job.id
}

const siteName = (job: Job): string => sites.sites.find((s) => s.id === job.site_id)?.name ?? '—'
const icons = { done: CheckCircleIcon, failed: XCircleIcon, pending: ClockIcon } as const
const iconColor = { done: 'text-green-500', failed: 'text-red-500', pending: 'text-gray-400' } as const

function duration(job: Job): string {
  if (!job.started_at || !job.finished_at) return '—'
  const seconds = Math.max(0, Math.round((Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000))
  if (seconds < 60) return `${seconds} s`
  const minutes = Math.floor(seconds / 60)
  return minutes < 60 ? `${minutes} min ${seconds % 60} s` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}
</script>

<template>
  <section
    ref="root"
    class="fixed right-0 bottom-0 left-0 z-20 border-t border-gray-200 bg-white/95 backdrop-blur transition-[left] duration-200 dark:border-white/10 dark:bg-gray-900/95"
    :aria-label="t('tasks.title')"
  >
    <button
      type="button"
      class="flex h-9 w-full items-center gap-3 px-4 text-left text-xs sm:px-6 lg:px-8"
      :aria-expanded="open"
      @click="open = !open"
    >
      <ChevronDownIcon v-if="open" class="size-4 text-gray-400" />
      <ChevronUpIcon v-else class="size-4 text-gray-400" />
      <span class="font-semibold text-gray-700 dark:text-gray-200">{{ t('tasks.title') }}</span>
      <span v-if="running" class="flex items-center gap-1.5 text-brand-600 dark:text-brand-400">
        <UiSpinner class="size-3.5" /> {{ t('tasks.running', running) }}
      </span>
      <span v-if="waiting" class="text-gray-500 dark:text-gray-400">{{ t('tasks.waiting', waiting) }}</span>
      <span v-if="!running && !waiting && latest" class="flex min-w-0 items-center gap-1.5 text-gray-500 dark:text-gray-400">
        <component :is="icons[latest.status as keyof typeof icons] ?? ClockIcon" class="size-3.5 shrink-0" :class="iconColor[latest.status as keyof typeof iconColor]" />
        <span class="truncate">{{ t(`jobs.kinds.${latest.kind}`) }}<template v-if="latest.summary"> · {{ latest.summary }}</template></span>
        <UiTime class="shrink-0" :value="latest.finished_at ?? latest.created_at" />
      </span>
      <span class="flex-1" />
      <RouterLink v-if="open" to="/jobs" class="link" @click.stop>{{ t('tasks.all') }}</RouterLink>
    </button>

    <div v-if="open" class="max-h-56 overflow-auto border-t border-gray-100 dark:border-white/5">
      <table class="min-w-full text-xs">
        <thead class="sticky top-0 bg-gray-50 text-left text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          <tr>
            <th class="py-1.5 pr-3 pl-4 font-medium sm:pl-6 lg:pl-8">{{ t('tasks.task') }}</th>
            <th class="px-3 py-1.5 font-medium">{{ t('tasks.target') }}</th>
            <th v-if="manySites" class="px-3 py-1.5 font-medium">{{ t('device.site') }}</th>
            <th class="w-48 px-3 py-1.5 font-medium">{{ t('device.status') }}</th>
            <th class="px-3 py-1.5 font-medium">{{ t('tasks.by') }}</th>
            <th class="px-3 py-1.5 font-medium">{{ t('tasks.queued') }}</th>
            <th class="py-1.5 pr-4 pl-3 font-medium sm:pr-6 lg:pr-8">{{ t('tasks.duration') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100 dark:divide-white/5">
          <template v-for="job in store.jobs" :key="job.id">
            <tr
              class="cursor-pointer text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-white/[0.03]"
              :title="t('tasks.showLog')"
              :aria-expanded="expanded === job.id"
              @click="toggleLog(job)"
            >
              <td class="py-1.5 pr-3 pl-4 font-medium whitespace-nowrap sm:pl-6 lg:pl-8">
                <span class="inline-flex items-center gap-1">
                  <ChevronDownIcon v-if="expanded === job.id" class="size-3.5 text-gray-400" />
                  <ChevronRightIcon v-else class="size-3.5 text-gray-400" />
                  {{ t(`jobs.kinds.${job.kind}`) }}
                </span>
              </td>
              <td class="max-w-xs truncate px-3 py-1.5" :title="job.summary">
                <RouterLink v-if="job.device_id" :to="`/devices/${job.device_id}`" class="link font-normal" @click.stop>{{ job.summary }}</RouterLink>
                <span v-else>{{ job.summary || '—' }}</span>
              </td>
              <td v-if="manySites" class="px-3 py-1.5 whitespace-nowrap">{{ siteName(job) }}</td>
              <td class="px-3 py-1.5">
                <div v-if="job.status === 'running'" class="flex items-center gap-2">
                  <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-white/10">
                    <div class="h-1.5 rounded-full bg-brand-500 transition-all" :style="{ width: `${Math.max(job.progress, 5)}%` }" />
                  </div>
                  <span class="w-9 text-right tabular-nums">{{ job.progress }} %</span>
                </div>
                <span v-else class="flex items-center gap-1.5" :title="job.error ?? undefined">
                  <component :is="icons[job.status as keyof typeof icons] ?? ClockIcon" class="size-4 shrink-0" :class="iconColor[job.status as keyof typeof iconColor]" />
                  <span class="truncate" :class="job.status === 'failed' && 'text-red-600 dark:text-red-400'">
                    {{ job.status === 'failed' && job.error ? job.error : t(`jobs.statuses.${job.status}`) }}
                  </span>
                </span>
              </td>
              <td class="px-3 py-1.5 whitespace-nowrap">{{ job.created_by }}</td>
              <td class="px-3 py-1.5 whitespace-nowrap"><UiTime :value="job.created_at" /></td>
              <td class="py-1.5 pr-4 pl-3 whitespace-nowrap tabular-nums sm:pr-6 lg:pr-8">{{ duration(job) }}</td>
            </tr>
            <tr v-if="expanded === job.id">
              <td colspan="7" class="px-4 pb-2 sm:px-6 lg:px-8">
                <pre class="max-h-48 overflow-auto rounded-md bg-gray-900 p-2.5 font-mono text-xs leading-relaxed text-gray-200"><span
                v-for="(line, i) in logLines(job)"
                :key="i"
                :class="line.includes('FAILED') && 'text-red-400'"
              >{{ line }}
</span></pre>
                <RouterLink :to="{ name: 'jobs', query: { job: job.id } }" class="link mt-1 inline-block">{{ t('tasks.openJob') }}</RouterLink>
              </td>
            </tr>
          </template>
          <tr v-if="!store.jobs.length">
            <td colspan="7" class="py-4 text-center text-gray-500">{{ t('tasks.empty') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
