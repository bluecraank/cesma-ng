import { ref, watch, type Ref } from 'vue'
import { useRouter, type LocationQueryRaw, type Router } from 'vue-router'
import type { SortState } from '@/composables/useTableSort'

// Several filters change at once (e.g. "reset"): collect them and replace the URL once.
let pending: LocationQueryRaw | null = null

function patchQuery(router: Router, patch: LocationQueryRaw): void {
  if (pending) {
    Object.assign(pending, patch)
    return
  }
  pending = { ...patch }
  queueMicrotask(() => {
    const current = router.currentRoute.value
    const query = { ...current.query, ...pending }
    pending = null
    for (const key of Object.keys(query)) if (query[key] === undefined) delete query[key]
    void router.replace({ path: current.path, query, hash: current.hash })
  })
}

/**
 * A filter kept in the URL (?name=value): it survives reloads and "back", and the link can be
 * shared. The default value is left out of the URL.
 */
export function useQueryParam(name: string, fallback = ''): Ref<string> {
  const router = useRouter()
  const raw = router.currentRoute.value.query[name]
  const value = ref(typeof raw === 'string' ? raw : fallback)
  watch(value, (v) => patchQuery(router, { [name]: v === fallback ? undefined : v }))
  return value
}

/** A number in the URL; anything not in ``allowed`` (if given) falls back to the default. */
export function useQueryNumber(name: string, fallback: number, allowed?: readonly number[]): Ref<number> {
  const router = useRouter()
  const raw = Number(router.currentRoute.value.query[name])
  const valid = Number.isFinite(raw) && router.currentRoute.value.query[name] !== undefined && (!allowed || allowed.includes(raw))
  const value = ref(valid ? raw : fallback)
  watch(value, (v) => patchQuery(router, { [name]: v === fallback ? undefined : String(v) }))
  return value
}

/** A yes/no filter in the URL (?name=1). */
export function useQueryFlag(name: string, fallback = false): Ref<boolean> {
  const router = useRouter()
  const raw = router.currentRoute.value.query[name]
  const value = ref(raw === '1' ? true : raw === '0' ? false : fallback)
  watch(value, (v) => patchQuery(router, { [name]: v === fallback ? undefined : v ? '1' : '0' }))
  return value
}

/** Keeps the sorting of a table in the URL: ?sort=name, ?sort=-name for descending. */
export function useQuerySort<K extends string>(sort: SortState<K>, keys: readonly K[], name = 'sort'): void {
  const router = useRouter()
  const raw = router.currentRoute.value.query[name]
  const initial = { key: sort.key, asc: sort.asc }
  if (typeof raw === 'string') {
    const asc = !raw.startsWith('-')
    const key = (asc ? raw : raw.slice(1)) as K
    if (keys.includes(key)) {
      sort.key = key
      sort.asc = asc
    }
  }
  watch(
    () => [sort.key, sort.asc] as const,
    ([key, asc]) => {
      const isDefault = key === initial.key && asc === initial.asc
      patchQuery(router, { [name]: isDefault || key === null ? undefined : `${asc ? '' : '-'}${key}` })
    },
  )
}
