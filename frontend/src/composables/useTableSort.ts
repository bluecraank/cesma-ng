import { computed, reactive, type ComputedRef } from 'vue'
import { useQuerySort } from '@/composables/useQueryState'

export type SortValue = string | number | boolean | null | undefined

export interface SortState<K extends string = string> {
  /** null: the order the rows came in */
  key: K | null
  asc: boolean
  toggle(key: K): void
}

const isEmpty = (v: SortValue): v is null | undefined | '' => v === null || v === undefined || v === ''

/** Numbers by value, text naturally ("1/1/9" before "1/1/10", 10.0.0.9 before 10.0.0.10). */
function compare(a: SortValue, b: SortValue): number {
  if (typeof a === 'string' || typeof b === 'string') return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
  return Number(a) - Number(b)
}

/**
 * Client-side sorting for a table. `columns` maps a column key to the value to sort by.
 * Rows without a value always end up at the bottom, whatever the direction.
 * With ``query`` the sorting is kept in the URL under that name (?sort=-name).
 */
export function useTableSort<T, K extends string>(
  rows: () => readonly T[],
  columns: Record<K, (row: T) => SortValue>,
  initial: NoInfer<K> | null = null,
  initialAsc = true,
  query?: string,
): { sort: SortState<K>; sorted: ComputedRef<T[]> } {
  const sort = reactive({
    key: initial,
    asc: initialAsc,
    toggle(key: K) {
      sort.asc = sort.key === key ? !sort.asc : true
      sort.key = key
    },
  }) as SortState<K>
  if (query) useQuerySort(sort, Object.keys(columns) as K[], query)

  const sorted = computed(() => {
    const list = [...rows()]
    if (sort.key === null) return list
    const value = columns[sort.key]
    const dir = sort.asc ? 1 : -1
    return list.sort((x, y) => {
      const a = value(x)
      const b = value(y)
      if (isEmpty(a) || isEmpty(b)) return Number(isEmpty(a)) - Number(isEmpty(b))
      return compare(a, b) * dir
    })
  })

  return { sort, sorted }
}
