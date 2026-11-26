import {
  ArchiveBoxIcon,
  BellIcon,
  BuildingOffice2Icon,
  ChartBarIcon,
  ClipboardDocumentCheckIcon,
  ClipboardDocumentListIcon,
  CommandLineIcon,
  CpuChipIcon,
  GlobeAltIcon,
  HomeIcon,
  KeyIcon,
  QueueListIcon,
  RectangleStackIcon,
  ServerStackIcon,
  ShareIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  UsersIcon,
  ViewfinderCircleIcon,
} from '@heroicons/vue/24/outline'
import { computed, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

export interface NavItem {
  to: string
  icon: Component
  label: string
  /** shows the number of open notifications */
  badge?: 'notifications'
}

export interface NavSection {
  /** stable key, e.g. to remember a collapsed section */
  key: string
  title?: string
  items: NavItem[]
}

/** The menu of the app: sidebar, page jumps in the search and the browser tab title. */
export function useNavigation() {
  const { t } = useI18n()
  const auth = useAuthStore()

  const sections = computed<NavSection[]>(() => [
    {
      key: 'network',
      items: [
        { to: '/', icon: HomeIcon, label: t('nav.dashboard') },
        { to: '/devices', icon: ServerStackIcon, label: t('nav.devices') },
        { to: '/switchports', icon: ViewfinderCircleIcon, label: t('nav.switchports') },
        { to: '/clients', icon: UserGroupIcon, label: t('nav.clients') },
        { to: '/vlans', icon: QueueListIcon, label: t('nav.vlans') },
        { to: '/topology', icon: ShareIcon, label: t('nav.topology') },
        { to: '/backups', icon: ArchiveBoxIcon, label: t('nav.backups') },
      ],
    },
    {
      key: 'monitoring',
      title: t('nav.monitoring'),
      items: [
        { to: '/notifications', icon: BellIcon, label: t('nav.notifications'), badge: 'notifications' },
        { to: '/compliance', icon: ClipboardDocumentCheckIcon, label: t('nav.compliance') },
        { to: '/reports', icon: ChartBarIcon, label: t('nav.reports') },
        { to: '/audit', icon: ClipboardDocumentListIcon, label: t('nav.audit') },
      ],
    },
    {
      key: 'admin',
      title: t('nav.administration'),
      items: [
        { to: '/admin/sites', icon: BuildingOffice2Icon, label: t('nav.sites'), show: true },
        { to: '/admin/jobs', icon: RectangleStackIcon, label: t('nav.jobs'), show: true },
        { to: '/admin/ssh-keys', icon: CommandLineIcon, label: t('nav.sshKeys'), show: true },
        { to: '/admin/users', icon: UsersIcon, label: t('nav.users'), show: auth.isSuperadmin },
        { to: '/admin/roles', icon: ShieldCheckIcon, label: t('nav.roles'), show: auth.isSuperadmin },
        { to: '/admin/credentials', icon: KeyIcon, label: t('nav.credentials'), show: auth.isSuperadmin },
        { to: '/admin/mac-types', icon: CpuChipIcon, label: t('nav.macTypes'), show: auth.isSuperadmin },
        { to: '/admin/gateways', icon: GlobeAltIcon, label: t('nav.gateways'), show: auth.isSuperadmin },
      ]
        .filter((item) => item.show),
    },
  ])

  const items = computed(() => sections.value.flatMap((section) => section.items))

  /** The menu entry a path belongs to: /devices/12 belongs to /devices. */
  function itemFor(path: string): NavItem | undefined {
    return items.value
      .filter((item) => (item.to === '/' ? path === '/' : path === item.to || path.startsWith(`${item.to}/`)))
      .sort((a, b) => b.to.length - a.to.length)[0]
  }

  return { sections, items, itemFor }
}
