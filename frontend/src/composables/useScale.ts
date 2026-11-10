import { ref, watchEffect } from 'vue'

/**
 * Own display scale, independent of Windows scaling and browser zoom (stored per browser).
 * All sizes are rem based, so changing the root font size scales the whole interface.
 */
export const SCALES = [75, 80, 90, 100, 110, 125, 150] as const
const STORAGE_KEY = 'cesma.scale'

function initialScale(): number {
  try {
    const stored = Number(localStorage.getItem(STORAGE_KEY))
    if ((SCALES as readonly number[]).includes(stored)) return stored
  } catch {
    /* storage unavailable */
  }
  return 100
}

const scale = ref(initialScale())

watchEffect(() => {
  document.documentElement.style.fontSize = scale.value === 100 ? '' : `${scale.value}%`
  try {
    localStorage.setItem(STORAGE_KEY, String(scale.value))
  } catch {
    /* storage unavailable */
  }
})

function step(direction: 1 | -1): void {
  const i = SCALES.indexOf(scale.value as (typeof SCALES)[number])
  const next = SCALES[Math.min(SCALES.length - 1, Math.max(0, (i < 0 ? SCALES.indexOf(100) : i) + direction))]
  scale.value = next ?? 100
}

export function useScale() {
  return { scale, smaller: () => step(-1), larger: () => step(1), reset: () => (scale.value = 100) }
}
