import { onScopeDispose, ref } from 'vue'

const now = ref(Date.now())
let users = 0
let timer: ReturnType<typeof setInterval> | undefined

/** A clock shared by all relative times; ticks every 30 s while anyone shows one. */
export function useNow() {
  if (users++ === 0) timer = setInterval(() => (now.value = Date.now()), 30_000)
  onScopeDispose(() => {
    if (--users === 0) clearInterval(timer)
  })
  return now
}
