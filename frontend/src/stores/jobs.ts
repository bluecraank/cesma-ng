import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, type Job } from '@/api/client'
import { i18n } from '@/i18n'
import { showToast } from '@/composables/useToasts'
import { useAuthStore } from './auth'

/** How many recent jobs the task list shows. */
const LIMIT = 30
const FAST_MS = 1500 // while something waits or runs
const SLOW_MS = 15_000 // otherwise: jobs of other users still show up

type Listener = (job: Job) => void

const active = (job: Job): boolean => job.status === 'pending' || job.status === 'running'

/**
 * Recent jobs of every visible site, for the task list at the bottom (like vCenter's
 * "Recent Tasks"). Polls quickly while a job waits or runs; tells listeners when one ends.
 */
export const useJobsStore = defineStore('jobs', () => {
  const jobs = ref<Job[]>([])
  /** jobs seen waiting or running in this browser tab: only those report their end */
  const watched = new Set<number>()
  const listeners = new Set<Listener>()
  let timer: ReturnType<typeof setTimeout> | undefined
  let running = false

  const activeCount = computed(() => jobs.value.filter(active).length)

  function schedule(): void {
    clearTimeout(timer)
    if (!running) return
    timer = setTimeout(refresh, activeCount.value || watched.size ? FAST_MS : SLOW_MS)
  }

  async function refresh(): Promise<void> {
    if (document.visibilityState === 'hidden' && !watched.size) return schedule()
    try {
      const latest = await api.get<Job[]>('/jobs', { limit: LIMIT })
      // a watched job that dropped out of the list is fetched on its own
      const missing = [...watched].filter((id) => !latest.some((j) => j.id === id))
      const extra = await Promise.all(missing.map((id) => api.get<Job>(`/jobs/${id}`).catch(() => null)))
      const all = [...latest, ...extra.filter((j): j is Job => j !== null)]
      for (const job of all) {
        if (active(job)) watched.add(job.id)
        else if (watched.delete(job.id)) finished(job)
      }
      jobs.value = latest
    } catch {
      /* keep the last list; the next poll tries again */
    }
    schedule()
  }

  function finished(job: Job): void {
    for (const listener of listeners) listener(job)
    // own jobs report their end; other users' jobs only appear in the list
    if (job.created_by !== useAuthStore().user?.username) return
    const { t } = i18n.global
    const kind = t(`jobs.kinds.${job.kind}`)
    const what = job.summary ? `${kind}: ${job.summary}` : kind
    if (job.status === 'done') showToast('success', t('jobs.finished', { kind: what }))
    else showToast('error', t('jobs.failed', { kind: what }), job.error ?? undefined)
  }

  /** A job was just queued: show it at once and follow it closely. */
  function track(job: Job): void {
    watched.add(job.id)
    jobs.value = [job, ...jobs.value.filter((j) => j.id !== job.id)].slice(0, LIMIT)
    clearTimeout(timer)
    timer = setTimeout(refresh, 500)
  }

  /** Called whenever a job ends (done or failed); returns the unsubscribe function. */
  function onFinished(listener: Listener): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  }

  function start(): void {
    running = true
    void refresh()
  }

  function stop(): void {
    running = false
    clearTimeout(timer)
  }

  return { jobs, activeCount, refresh, track, onFinished, start, stop }
})
