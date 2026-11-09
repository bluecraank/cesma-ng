import { ref, watchEffect } from 'vue'

type Theme = 'light' | 'dark'
const STORAGE_KEY = 'cesma.theme'

function initialTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const theme = ref<Theme>(initialTheme())

watchEffect(() => {
  document.documentElement.classList.toggle('dark', theme.value === 'dark')
  try {
    localStorage.setItem(STORAGE_KEY, theme.value)
  } catch {
    /* storage unavailable */
  }
})

export function useTheme() {
  return {
    theme,
    toggle: () => (theme.value = theme.value === 'dark' ? 'light' : 'dark'),
  }
}
