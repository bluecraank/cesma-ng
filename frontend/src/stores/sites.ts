import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { api, type Site } from '@/api/client'

const STORAGE_KEY = 'cesma.currentSite'

function readStoredSite(): number | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value ? Number(value) : null
  } catch {
    return null
  }
}

/** Sites visible to the user and the currently selected one (remembered per browser). */
export const useSitesStore = defineStore('sites', () => {
  const sites = ref<Site[]>([])
  const currentId = ref<number | null>(readStoredSite())

  const current = computed(() => sites.value.find((s) => s.id === currentId.value) ?? null)

  watch(currentId, (id) => {
    try {
      if (id === null) localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, String(id))
    } catch {
      /* storage unavailable */
    }
  })

  async function load(): Promise<void> {
    sites.value = await api.get<Site[]>('/sites')
    if (!sites.value.some((s) => s.id === currentId.value)) {
      currentId.value = sites.value[0]?.id ?? null
    }
  }

  function rooms(siteId: number | null): { id: number; label: string }[] {
    const site = sites.value.find((s) => s.id === siteId)
    return (site?.buildings ?? []).flatMap((b) =>
      b.rooms.map((r) => ({ id: r.id, label: `${b.name} / ${r.name}` })),
    )
  }

  return { sites, currentId, current, load, rooms }
})
