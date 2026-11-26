/** Unsaved input anywhere on the page: the browser asks before reloading or closing the tab. */
const unsaved = new Set<symbol>()

function onBeforeUnload(event: BeforeUnloadEvent): void {
  event.preventDefault()
  // older browsers need returnValue set
  event.returnValue = ''
}

export function setUnsaved(id: symbol, value: boolean): void {
  const before = unsaved.size
  if (value) unsaved.add(id)
  else unsaved.delete(id)
  if (!before && unsaved.size) window.addEventListener('beforeunload', onBeforeUnload)
  if (before && !unsaved.size) window.removeEventListener('beforeunload', onBeforeUnload)
}
