import { reactive } from 'vue'

export type ToastKind = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  kind: ToastKind
  title: string
  detail?: string
}

const toasts = reactive<Toast[]>([])
let nextId = 1

export function dismissToast(id: number): void {
  const index = toasts.findIndex((t) => t.id === id)
  if (index >= 0) toasts.splice(index, 1)
}

export function showToast(kind: ToastKind, title: string, detail?: string): void {
  const id = nextId++
  toasts.push({ id, kind, title, detail })
  setTimeout(() => dismissToast(id), kind === 'error' ? 7000 : 3000)
}

export function useToasts() {
  return { toasts, show: showToast, dismiss: dismissToast }
}
