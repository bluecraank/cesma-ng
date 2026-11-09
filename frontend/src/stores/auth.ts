import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, type SiteRole, type User } from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loaded = ref(false)

  const isSuperadmin = computed(() => user.value?.is_superadmin ?? false)

  async function load(): Promise<void> {
    try {
      user.value = await api.get<User>('/auth/me')
    } catch {
      // No session: maybe a reverse proxy (SSO) already authenticated the user.
      user.value = await api.post<User>('/auth/sso').catch(() => null)
    } finally {
      loaded.value = true
    }
  }

  async function login(username: string, password: string): Promise<void> {
    user.value = await api.post<User>('/auth/login', { username, password })
  }

  async function logout(): Promise<void> {
    await api.post('/auth/logout').catch(() => undefined)
    user.value = null
  }

  function roleFor(siteId: number): SiteRole | null {
    if (!user.value) return null
    if (user.value.is_superadmin) return 'admin'
    return user.value.site_roles.find((r) => r.site_id === siteId)?.role ?? null
  }

  function canAdmin(siteId: number | null | undefined): boolean {
    return siteId != null && roleFor(siteId) === 'admin'
  }

  return { user, loaded, isSuperadmin, load, login, logout, roleFor, canAdmin }
})
