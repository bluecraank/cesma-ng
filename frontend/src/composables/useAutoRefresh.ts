import { onMounted, onUnmounted, type Ref } from 'vue'

/**
 * Runs ``reload`` every ``intervalMs`` while the tab is visible and ``enabled`` is on.
 * A hidden tab does not poll; coming back to it reloads at once when the data is stale.
 */
export function useAutoRefresh(reload: () => Promise<unknown>, enabled: Ref<boolean>, intervalMs = 30_000): void {
  let timer: ReturnType<typeof setInterval> | undefined
  let running = false
  let lastRun = Date.now()

  async function tick(): Promise<void> {
    if (running || document.hidden || !enabled.value) return
    running = true
    try {
      await reload()
    } finally {
      running = false
      lastRun = Date.now()
    }
  }

  function onVisibility(): void {
    if (!document.hidden && Date.now() - lastRun >= intervalMs) void tick()
  }

  onMounted(() => {
    timer = setInterval(() => void tick(), intervalMs)
    document.addEventListener('visibilitychange', onVisibility)
  })
  onUnmounted(() => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibility)
  })
}
