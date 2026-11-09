import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import type { User } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

function user(overrides: Partial<User>): User {
  return {
    id: 1, username: 'bob', display_name: 'Bob', email: null, is_superadmin: false,
    is_active: true, locale: 'de', last_login_at: null, has_local_password: false, site_roles: [], ...overrides,
  }
}

describe('auth store permissions', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('superadmin may do everything everywhere', () => {
    const auth = useAuthStore()
    auth.user = user({ is_superadmin: true })
    expect(auth.can('console', 42)).toBe(true)
    expect(auth.hasSite(42)).toBe(true)
  })

  it('the role on a site decides per permission', () => {
    const auth = useAuthStore()
    auth.user = user({
      site_roles: [
        { site_id: 1, role_id: 3, role_name: 'Ports', permissions: ['ports.edit'] },
        { site_id: 2, role_id: 1, role_name: 'Lesen', permissions: [] },
      ],
    })
    expect(auth.can('ports.edit', 1)).toBe(true)
    expect(auth.can('console', 1)).toBe(false)
    expect(auth.can('ports.edit', 2)).toBe(false)
    expect(auth.hasSite(2)).toBe(true)
    expect(auth.hasSite(3)).toBe(false)
    expect(auth.can('ports.edit', null)).toBe(false)
    expect(auth.canAnywhere('ports.edit')).toBe(true)
    expect(auth.roleName(1)).toBe('Ports')
  })
})
