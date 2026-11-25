import { ref } from 'vue'

export interface ColumnState<K extends string = string> {
  shows(key: K): boolean
  toggle(key: K): void
}

/**
 * Which optional columns of a table are shown; remembered per browser.
 * Only the hidden ones are stored, so a column added later is visible by default.
 */
export function useColumns<K extends string>(storageKey: string, hiddenByDefault: readonly K[] = []): ColumnState<K> {
  const key = `cesma.columns.${storageKey}`

  function read(): Set<K> {
    try {
      const stored = localStorage.getItem(key)
      if (stored !== null) return new Set(JSON.parse(stored) as K[])
    } catch {
      /* storage unavailable or broken value: defaults */
    }
    return new Set(hiddenByDefault)
  }

  const hidden = ref(read()) as { value: Set<K> }

  return {
    shows: (column) => !hidden.value.has(column),
    toggle(column) {
      const next = new Set(hidden.value)
      if (!next.delete(column)) next.add(column)
      hidden.value = next
      try {
        localStorage.setItem(key, JSON.stringify([...next]))
      } catch {
        /* storage unavailable */
      }
    },
  }
}
