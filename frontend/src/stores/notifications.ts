import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api/client'
import { useSitesStore } from './sites'

/** Number of open notifications for the header badge, refreshed periodically. */
export const useNotificationsStore = defineStore('notifications', () => {
  const open = ref(0)
  let timer: ReturnType<typeof setInterval> | undefined

  async function refresh(): Promise<void> {
    const sites = useSitesStore()
    try {
      open.value = (await api.get<{ open: number }>('/notifications/count', { site_id: sites.currentId })).open
    } catch {
      /* keep the last value; errors are shown elsewhere */
    }
  }

  function start(intervalMs = 30_000): void {
    stop()
    void refresh()
    timer = setInterval(refresh, intervalMs)
  }

  function stop(): void {
    clearInterval(timer)
  }

  return { open, refresh, start, stop }
})
