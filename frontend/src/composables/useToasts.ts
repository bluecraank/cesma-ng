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

/**
 * Open modal dialogs, innermost last. A modal <dialog> sits in the browser's top layer above
 * every z-index and makes the page behind it inert, so toasts are shown inside the innermost
 * dialog instead of behind it.
 */
const dialogs = reactive<number[]>([])
let nextDialog = 1

export function openDialog(): number {
  const id = nextDialog++
  dialogs.push(id)
  return id
}

export function closeDialog(id: number): void {
  const index = dialogs.indexOf(id)
  if (index >= 0) dialogs.splice(index, 1)
}

/** The toaster of this host shows the toasts (``null`` = the page, no dialog open). */
export function hostsToasts(host: number | null): boolean {
  return host === null ? dialogs.length === 0 : dialogs[dialogs.length - 1] === host
}

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
