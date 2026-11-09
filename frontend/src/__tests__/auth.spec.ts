import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import type { User } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

function user(overrides: Partial<User>): User {
  return {
    id: 1, username: 'bob', display_name: 'Bob', email: null, is_superadmin: false,
    is_active: true, locale: 'de', last_login_at: null, site_roles: [], ...overrides,
  }
}

describe('auth store permissions', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('superadmin administers every site', () => {
    const auth = useAuthStore()
    auth.user = user({ is_superadmin: true })
    expect(auth.canAdmin(42)).toBe(true)
  })

  it('site roles decide per site', () => {
    const auth = useAuthStore()
    auth.user = user({ site_roles: [{ site_id: 1, role: 'admin' }, { site_id: 2, role: 'viewer' }] })
    expect(auth.canAdmin(1)).toBe(true)
    expect(auth.canAdmin(2)).toBe(false)
    expect(auth.roleFor(3)).toBeNull()
    expect(auth.canAdmin(null)).toBe(false)
  })
})
