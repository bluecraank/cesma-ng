import { onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type Job } from '@/api/client'
import { showToast } from './useToasts'

/** Follows a queued job until it is done; shows a toast at the end. */
export function useJobWatcher(onFinished?: (job: Job) => void) {
  const { t } = useI18n()
  const job = ref<Job | null>(null)
  let timer: ReturnType<typeof setTimeout> | undefined

  async function poll(id: number): Promise<void> {
    try {
      job.value = await api.get<Job>(`/jobs/${id}`)
    } catch {
      timer = setTimeout(() => poll(id), 3000)
      return
    }
    if (job.value.status === 'done' || job.value.status === 'failed') {
      const kind = t(`jobs.kinds.${job.value.kind}`)
      if (job.value.status === 'done') showToast('success', t('jobs.finished', { kind }))
      else showToast('error', t('jobs.failed', { kind }), job.value.error ?? undefined)
      onFinished?.(job.value)
      return
    }
    timer = setTimeout(() => poll(id), 1500)
  }

  function watch(started: Job): void {
    clearTimeout(timer)
    job.value = started
    void poll(started.id)
  }

  onUnmounted(() => clearTimeout(timer))
  return { job, watch }
}
