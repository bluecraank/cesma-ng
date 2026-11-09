import { createI18n } from 'vue-i18n'
import de from './de'
import en from './en'

export type Locale = 'de' | 'en'

export const i18n = createI18n({
  legacy: false,
  locale: 'de',
  fallbackLocale: 'en',
  messages: { de, en },
  datetimeFormats: {
    de: { short: { dateStyle: 'short', timeStyle: 'short' } },
    en: { short: { dateStyle: 'short', timeStyle: 'short' } },
  },
})

export function setLocale(locale: string): void {
  if (locale === 'de' || locale === 'en') {
    i18n.global.locale.value = locale
    document.documentElement.lang = locale
  }
}
