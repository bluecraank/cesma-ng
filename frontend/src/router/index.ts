import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    superadmin?: boolean
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        { path: '', name: 'dashboard', component: () => import('@/views/DashboardView.vue') },
        { path: 'devices', name: 'devices', component: () => import('@/views/DevicesView.vue') },
        {
          path: 'devices/:id',
          name: 'device',
          component: () => import('@/views/DeviceDetailView.vue'),
          props: (route) => ({ id: Number(route.params.id) }),
        },
        { path: 'clients', name: 'clients', component: () => import('@/views/ClientsView.vue') },
        { path: 'topology', name: 'topology', component: () => import('@/views/TopologyView.vue') },
        { path: 'vlans', name: 'vlans', component: () => import('@/views/VlansView.vue') },
        { path: 'backups', name: 'backups', component: () => import('@/views/BackupsView.vue') },
        { path: 'reports', name: 'reports', component: () => import('@/views/ReportsView.vue') },
        { path: 'switchports', name: 'switchports', component: () => import('@/views/SwitchportsView.vue') },
        { path: 'free-ports', redirect: '/switchports' },
        { path: 'compliance', name: 'compliance', component: () => import('@/views/ComplianceView.vue') },
        { path: 'admin/jobs', name: 'jobs', component: () => import('@/views/JobsView.vue') },
        { path: 'jobs', redirect: '/admin/jobs' },
        { path: 'audit', name: 'audit', component: () => import('@/views/AuditView.vue') },
        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/views/NotificationsView.vue'),
        },
        {
          path: 'admin/sites',
          name: 'admin-sites',
          component: () => import('@/views/admin/SitesView.vue'),
        },
        {
          path: 'admin/users',
          name: 'admin-users',
          component: () => import('@/views/admin/UsersView.vue'),
          meta: { superadmin: true },
        },
        {
          path: 'admin/mac-types',
          name: 'admin-mac-types',
          component: () => import('@/views/admin/MacTypesView.vue'),
          meta: { superadmin: true },
        },
        {
          path: 'admin/gateways',
          name: 'admin-gateways',
          component: () => import('@/views/admin/GatewaysView.vue'),
          meta: { superadmin: true },
        },
        {
          // every user manages their own keys here
          path: 'admin/ssh-keys',
          name: 'admin-ssh-keys',
          component: () => import('@/views/admin/SshKeysView.vue'),
        },
        {
          path: 'admin/roles',
          name: 'admin-roles',
          component: () => import('@/views/admin/RolesView.vue'),
          meta: { superadmin: true },
        },
        {
          path: 'admin/credentials',
          name: 'admin-credentials',
          component: () => import('@/views/admin/CredentialsView.vue'),
          meta: { superadmin: true },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) await auth.load()
  if (to.meta.public) return auth.user && to.name === 'login' ? { name: 'dashboard' } : true
  if (!auth.user) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.superadmin && !auth.isSuperadmin) return { name: 'dashboard' }
  return true
})
