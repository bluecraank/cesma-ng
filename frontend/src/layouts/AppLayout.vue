<script setup lang="ts">
import {
  ArrowRightStartOnRectangleIcon,
  Bars3Icon,
  ArchiveBoxIcon,
  BellIcon,
  ChartBarIcon,
  ClipboardDocumentCheckIcon,
  ShareIcon,
  CommandLineIcon,
  QueueListIcon,
  RectangleStackIcon,
  ShieldCheckIcon,
  CpuChipIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  UserGroupIcon,
  BuildingOffice2Icon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  ClipboardDocumentListIcon,
  HomeIcon,
  KeyIcon,
  MoonIcon,
  ServerStackIcon,
  SunIcon,
  UsersIcon,
  ViewfinderCircleIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import { APP_VERSION } from '@/changelog'
import CesmaLogo from '@/components/CesmaLogo.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import PatchNotesDialog from '@/components/PatchNotesDialog.vue'
import { useTheme } from '@/composables/useTheme'
import { setLocale } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { useSitesStore } from '@/stores/sites'

const { t, locale } = useI18n()
const auth = useAuthStore()
const sites = useSitesStore()
const notifications = useNotificationsStore()
const router = useRouter()
const { theme, toggle } = useTheme()
const mobileOpen = ref(false)
const COLLAPSED_KEY = 'cesma.sidebarCollapsed'
const collapsed = ref(readFlag(COLLAPSED_KEY))
/** Icon-only rail on desktop; the mobile drawer always shows labels. */
const compact = computed(() => collapsed.value && !mobileOpen.value)

function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

watch(collapsed, (value) => {
  try {
    localStorage.setItem(COLLAPSED_KEY, value ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
})
const patchNotesOpen = ref(false)
const searchOpen = ref(false)
const SEEN_VERSION_KEY = 'cesma.seenVersion'

onUnmounted(() => notifications.stop())
watch(() => sites.currentId, () => notifications.refresh())

onMounted(() => {
  void sites.load().then(() => notifications.start())
  // Show the patch notes once after every update (per browser).
  try {
    if (localStorage.getItem(SEEN_VERSION_KEY) !== APP_VERSION) {
      patchNotesOpen.value = true
      localStorage.setItem(SEEN_VERSION_KEY, APP_VERSION)
    }
  } catch {
    /* storage unavailable: do not nag */
  }
})

const sections = computed(() => [
  {
    items: [
      { to: '/', icon: HomeIcon, label: t('nav.dashboard') },
      { to: '/devices', icon: ServerStackIcon, label: t('nav.devices') },
      { to: '/clients', icon: UserGroupIcon, label: t('nav.clients') },
      { to: '/topology', icon: ShareIcon, label: t('nav.topology') },
      { to: '/vlans', icon: QueueListIcon, label: t('nav.vlans') },
      { to: '/backups', icon: ArchiveBoxIcon, label: t('nav.backups') },
      { to: '/notifications', icon: BellIcon, label: t('nav.notifications') },
      { to: '/free-ports', icon: ViewfinderCircleIcon, label: t('nav.freePorts') },
      { to: '/compliance', icon: ClipboardDocumentCheckIcon, label: t('nav.compliance') },
      { to: '/reports', icon: ChartBarIcon, label: t('nav.reports') },
      { to: '/audit', icon: ClipboardDocumentListIcon, label: t('nav.audit') },
    ],
  },
  {
    title: t('nav.administration'),
    items: [
      { to: '/admin/sites', icon: BuildingOffice2Icon, label: t('nav.sites'), show: true },
      { to: '/admin/ssh-keys', icon: CommandLineIcon, label: t('nav.sshKeys'), show: true },
      { to: '/admin/jobs', icon: RectangleStackIcon, label: t('nav.jobs'), show: true },
      { to: '/admin/users', icon: UsersIcon, label: t('nav.users'), show: auth.isSuperadmin },
      { to: '/admin/roles', icon: ShieldCheckIcon, label: t('nav.roles'), show: auth.isSuperadmin },
      { to: '/admin/credentials', icon: KeyIcon, label: t('nav.credentials'), show: auth.isSuperadmin },
      { to: '/admin/mac-types', icon: CpuChipIcon, label: t('nav.macTypes'), show: auth.isSuperadmin },
      { to: '/admin/gateways', icon: GlobeAltIcon, label: t('nav.gateways'), show: auth.isSuperadmin },
    ].filter((item) => item.show),
  },
])

const initials = computed(() =>
  (auth.user?.display_name || auth.user?.username || '?')
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase(),
)

async function switchLocale(): Promise<void> {
  const next = locale.value === 'de' ? 'en' : 'de'
  setLocale(next)
  await api.put('/auth/me/locale', { locale: next }).catch(() => undefined)
}

async function logout(): Promise<void> {
  await auth.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div class="min-h-screen">
    <!-- Mobile backdrop -->
    <div v-if="mobileOpen" class="fixed inset-0 z-40 bg-gray-900/60 lg:hidden" @click="mobileOpen = false" />

    <!-- Sidebar -->
    <aside
      class="fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-gray-900 transition-[transform,width] duration-200 lg:translate-x-0 dark:border-r dark:border-white/10 dark:bg-gray-950"
      :class="[mobileOpen ? 'translate-x-0' : '-translate-x-full', compact && 'lg:w-16']"
    >
      <div class="flex h-16 shrink-0 items-center justify-between gap-2" :class="compact ? 'px-4' : 'px-6'">
        <RouterLink to="/" class="text-white" :title="compact ? 'cesma-ng' : undefined">
          <CesmaLogo :icon-only="compact" />
        </RouterLink>
        <button type="button" class="rounded-md p-1 text-gray-400 hover:text-white lg:hidden" @click="mobileOpen = false">
          <XMarkIcon class="size-6" />
        </button>
      </div>

      <nav class="flex flex-1 flex-col gap-6 overflow-x-hidden overflow-y-auto py-2" :class="compact ? 'px-2' : 'px-4'" @click="mobileOpen = false">
        <div v-for="(section, i) in sections" :key="i">
          <div v-if="section.title && !compact" class="mb-2 px-2 text-xs font-semibold whitespace-nowrap text-gray-500">{{ section.title }}</div>
          <div v-else-if="section.title" class="mx-2 mb-2 border-t border-white/10" />
          <ul class="space-y-1">
            <li v-for="item in section.items" :key="item.to">
              <RouterLink
                :to="item.to"
                class="group flex items-center gap-x-3 rounded-md py-2 text-sm font-medium whitespace-nowrap text-gray-400 hover:bg-white/5 hover:text-white"
                :class="compact ? 'justify-center px-0' : 'px-2'"
                exact-active-class="!bg-white/5 !text-white"
                :title="compact ? item.label : undefined"
              >
                <component :is="item.icon" class="size-5 shrink-0" />
                <span v-if="!compact">{{ item.label }}</span>
              </RouterLink>
            </li>
          </ul>
        </div>
      </nav>

      <div class="flex items-center gap-3 border-t border-white/10 py-4" :class="compact ? 'flex-col px-2' : 'px-6'">
        <div
          class="flex size-8 shrink-0 items-center justify-center rounded-full bg-gray-700 text-xs font-semibold text-white"
          :title="compact ? auth.user?.display_name || auth.user?.username : undefined"
        >
          {{ initials }}
        </div>
        <div v-if="!compact" class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium text-white">{{ auth.user?.display_name || auth.user?.username }}</p>
          <p class="truncate text-xs text-gray-400">{{ auth.user?.is_superadmin ? t('users.superadmin') : auth.user?.username }}</p>
        </div>
        <button type="button" class="rounded-md p-1.5 text-gray-400 hover:bg-white/5 hover:text-white" :title="t('nav.logout')" @click="logout">
          <ArrowRightStartOnRectangleIcon class="size-5" />
        </button>
      </div>
      <button
        type="button"
        class="flex items-center justify-between gap-2 border-t border-white/10 py-2.5 text-xs whitespace-nowrap text-gray-500 hover:bg-white/5 hover:text-gray-300"
        :class="compact ? 'justify-center px-1' : 'px-6'"
        :title="t('patchNotes.title')"
        @click="patchNotesOpen = true"
      >
        <span>{{ compact ? `v${APP_VERSION}` : `cesma-ng v${APP_VERSION}` }}</span>
        <span v-if="!compact">{{ t('patchNotes.link') }}</span>
      </button>
      <button
        type="button"
        class="hidden items-center gap-2 border-t border-white/10 py-2.5 text-xs whitespace-nowrap text-gray-500 hover:bg-white/5 hover:text-gray-300 lg:flex"
        :class="compact ? 'justify-center' : 'px-6'"
        :title="collapsed ? t('nav.expand') : t('nav.collapse')"
        @click="collapsed = !collapsed"
      >
        <ChevronDoubleRightIcon v-if="collapsed" class="size-4" />
        <template v-else><ChevronDoubleLeftIcon class="size-4" /> {{ t('nav.collapse') }}</template>
      </button>
    </aside>

    <PatchNotesDialog v-model:open="patchNotesOpen" />
    <CommandPalette v-model:open="searchOpen" />

    <!-- Main column -->
    <div class="transition-[padding] duration-200" :class="collapsed ? 'lg:pl-16' : 'lg:pl-64'">
      <header
        class="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-gray-200 bg-white/90 px-4 backdrop-blur sm:px-6 lg:px-8 dark:border-white/10 dark:bg-gray-900/90"
      >
        <button type="button" class="btn-icon lg:hidden" aria-label="Menu" @click="mobileOpen = true">
          <Bars3Icon class="size-6" />
        </button>
        <label class="flex items-center gap-2">
          <BuildingOffice2Icon class="hidden size-5 text-gray-400 sm:block" />
          <select v-model="sites.currentId" class="input w-auto min-w-44 font-medium" :aria-label="t('device.site')">
            <option v-if="!sites.sites.length" :value="null">{{ t('nav.noSite') }}</option>
            <option v-for="site in sites.sites" :key="site.id" :value="site.id">{{ site.name }}</option>
          </select>
        </label>
        <button
          type="button"
          class="hidden h-9 w-72 items-center gap-2 rounded-md bg-gray-50 px-3 text-sm text-gray-400 ring-1 ring-gray-200 ring-inset hover:ring-gray-300 md:flex dark:bg-white/5 dark:ring-white/10"
          @click="searchOpen = true"
        >
          <MagnifyingGlassIcon class="size-4" />
          <span class="flex-1 text-left">{{ t('common.search') }}</span>
          <kbd class="rounded border border-gray-200 px-1.5 font-sans text-[10px] dark:border-white/10">{{ t('search.shortcut') }}</kbd>
        </button>
        <div class="flex-1" />
        <button type="button" class="btn-icon md:hidden" :title="t('common.search')" @click="searchOpen = true">
          <MagnifyingGlassIcon class="size-5" />
        </button>
        <RouterLink to="/notifications" class="btn-icon relative" :title="t('nav.notifications')">
          <BellIcon class="size-5" />
          <span
            v-if="notifications.open"
            class="absolute -top-0.5 -right-0.5 flex min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] leading-4 font-semibold text-white"
          >
            {{ notifications.open > 99 ? '99+' : notifications.open }}
          </span>
        </RouterLink>
        <button type="button" class="btn-icon" :title="t('nav.theme')" @click="toggle">
          <SunIcon v-if="theme === 'dark'" class="size-5" />
          <MoonIcon v-else class="size-5" />
        </button>
        <button type="button" class="btn btn-ghost btn-sm uppercase" @click="switchLocale">{{ locale }}</button>
      </header>

      <main class="px-4 py-6 sm:px-6 lg:px-8">
        <RouterView />
      </main>
    </div>
  </div>
</template>
