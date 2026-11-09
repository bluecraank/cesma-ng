import { shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'

export interface ConfirmRequest {
  title: string
  message: string
  confirmLabel: string
  cancelLabel: string
  danger: boolean
  resolve: (ok: boolean) => void
}

const pending = shallowRef<ConfirmRequest | null>(null)

/** Promise based confirmation dialog, rendered once by ConfirmHost in App.vue. */
export function useConfirm() {
  function confirm(options: Omit<ConfirmRequest, 'resolve' | 'danger'> & { danger?: boolean }): Promise<boolean> {
    pending.value?.resolve(false)
    return new Promise((resolve) => {
      pending.value = { danger: false, ...options, resolve }
    })
  }

  function answer(ok: boolean): void {
    pending.value?.resolve(ok)
    pending.value = null
  }

  return { pending, confirm, answer }
}

/** The common case: "really delete X?" with translated labels. */
export function useConfirmDelete() {
  const { t } = useI18n()
  const { confirm } = useConfirm()
  return (name: string): Promise<boolean> =>
    confirm({
      title: t('common.delete'),
      message: t('common.confirmDelete', { name }),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      danger: true,
    })
}
