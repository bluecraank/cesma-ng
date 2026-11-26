import { computed, onUnmounted, ref } from 'vue'
import type { Job } from '@/api/client'
import { useJobsStore } from '@/stores/jobs'

/**
 * Follows a queued job until it is done. The task list (jobs store) polls it and shows the
 * toast at the end; this only exposes the job's progress and calls ``onFinished``.
 */
export function useJobWatcher(onFinished?: (job: Job) => void) {
  const store = useJobsStore()
  const id = ref<number | null>(null)
  const started = ref<Job | null>(null)
  const job = computed(() => store.jobs.find((j) => j.id === id.value) ?? started.value)

  const stop = store.onFinished((ended) => {
    if (ended.id !== id.value) return
    started.value = ended
    onFinished?.(ended)
  })
  onUnmounted(stop)

  function watch(queued: Job): void {
    id.value = queued.id
    started.value = queued
    store.track(queued)
  }

  return { job, watch }
}
