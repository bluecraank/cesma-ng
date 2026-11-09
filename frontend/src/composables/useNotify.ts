import { useI18n } from 'vue-i18n'
import { ApiError } from '@/api/client'
import { showToast } from './useToasts'

/** Toast helpers so views do not repeat error handling. */
export function useNotify() {
  const { t } = useI18n()

  function success(title: string): void {
    showToast('success', title)
  }

  function error(err: unknown): void {
    const detail = err instanceof ApiError ? err.message : String(err)
    showToast('error', t('common.error'), detail)
  }

  /** Runs an action, shows a success toast or the error. Returns whether it succeeded. */
  async function run(action: () => Promise<unknown>, successMessage?: string): Promise<boolean> {
    try {
      await action()
      if (successMessage) success(successMessage)
      return true
    } catch (err) {
      error(err)
      return false
    }
  }

  return { success, error, run }
}
