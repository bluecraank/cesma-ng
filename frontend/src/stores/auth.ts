import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, type Permission, type User } from '@/api/client'

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

  /** Every role on a site allows seeing it; the role's permissions allow the rest. */
  function hasSite(siteId: number | null | undefined): boolean {
    if (!user.value || siteId == null) return false
    return user.value.is_superadmin || user.value.site_roles.some((r) => r.site_id === siteId)
  }

  function can(permission: Permission, siteId: number | null | undefined): boolean {
    if (!user.value || siteId == null) return false
    if (user.value.is_superadmin) return true
    const role = user.value.site_roles.find((r) => r.site_id === siteId)
    return role?.permissions.includes(permission) ?? false
  }

  function canAnywhere(permission: Permission): boolean {
    if (!user.value) return false
    return user.value.is_superadmin || user.value.site_roles.some((r) => r.permissions.includes(permission))
  }

  function roleName(siteId: number): string | null {
    return user.value?.site_roles.find((r) => r.site_id === siteId)?.role_name ?? null
  }

  return { user, loaded, isSuperadmin, load, login, logout, hasSite, can, canAnywhere, roleName }
})
