<script setup lang="ts">
/** The VLAN, MAC, neighbour and poll status tabs of a device: plain read-only tables. */
import { MagnifyingGlassIcon } from '@heroicons/vue/20/solid'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DeviceVlan, FdbEntry, LldpNeighbor, PollState } from '@/api/client'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{
  tab: 'vlans' | 'fdb' | 'lldp' | 'poll'
  vlans?: DeviceVlan[]
  fdb?: FdbEntry[]
  lldp?: LldpNeighbor[]
  poll?: PollState[]
}>()
const { t, locale } = useI18n()
const search = ref('')

const fdbRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  const rows = props.fdb ?? []
  return q
    ? rows.filter((e) => [e.mac_address, e.port_name ?? '', String(e.vid ?? ''), ...e.ip_addresses].some((v) => v.toLowerCase().includes(q)))
    : rows
})
</script>

<template>
  <div class="space-y-4">
    <div v-if="tab === 'fdb'" class="flex items-center gap-4">
      <div class="relative">
        <MagnifyingGlassIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
        <input v-model="search" class="input w-72 pl-8" :placeholder="t('common.search')" />
      </div>
      <span class="ml-auto text-sm text-gray-500">{{ fdbRows.length }} / {{ fdb?.length ?? 0 }}</span>
    </div>

    <div class="card table-wrap">
      <table v-if="tab === 'vlans'" class="table">
        <thead>
          <tr>
            <th>{{ t('vlans.vid') }}</th>
            <th>{{ t('common.name') }}</th>
            <th class="text-right">{{ t('vlans.untaggedPorts') }}</th>
            <th class="text-right">{{ t('vlans.taggedPorts') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in vlans" :key="v.vid">
            <td class="font-medium">{{ v.vid }}</td>
            <td>{{ v.name }}</td>
            <td class="text-right tabular-nums">{{ v.untagged_ports }}</td>
            <td class="text-right tabular-nums">{{ v.tagged_ports }}</td>
          </tr>
        </tbody>
      </table>

      <table v-else-if="tab === 'fdb'" class="table">
        <thead>
          <tr>
            <th>{{ t('fdb.mac') }}</th>
            <th>{{ t('fdb.vlan') }}</th>
            <th>{{ t('ports.port') }}</th>
            <th>{{ t('fdb.ip') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in fdbRows" :key="`${e.vid}-${e.mac_address}`">
            <td class="font-mono text-xs">{{ e.mac_address }}</td>
            <td class="tabular-nums">{{ e.vid ?? '—' }}</td>
            <td>{{ e.port_name ?? '—' }}</td>
            <td>{{ e.ip_addresses.join(', ') }}</td>
          </tr>
        </tbody>
      </table>

      <table v-else-if="tab === 'lldp'" class="table">
        <thead>
          <tr>
            <th>{{ t('lldp.localPort') }}</th>
            <th>{{ t('lldp.system') }}</th>
            <th>{{ t('lldp.remotePort') }}</th>
            <th>{{ t('lldp.address') }}</th>
            <th>{{ t('device.model') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="n in lldp" :key="n.id">
            <td>{{ n.local_port_name }}</td>
            <td>
              <RouterLink v-if="n.remote_device_id" :to="{ name: 'device', params: { id: n.remote_device_id } }" class="link">
                {{ n.system_name || n.chassis_id }}
              </RouterLink>
              <span v-else>{{ n.system_name || n.chassis_id }}</span>
            </td>
            <td>{{ n.remote_port_description || n.remote_port }}</td>
            <td class="font-mono text-xs">{{ n.management_address ?? '' }}</td>
            <td class="max-w-80 truncate text-xs text-gray-500" :title="n.system_description">{{ n.system_description }}</td>
          </tr>
          <tr v-if="!lldp?.length"><td colspan="5" class="py-6 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>

      <table v-else class="table">
        <thead>
          <tr>
            <th>{{ t('poll.task') }}</th>
            <th>{{ t('poll.lastSuccess') }}</th>
            <th>{{ t('poll.nextRun') }}</th>
            <th class="text-right">{{ t('poll.duration') }}</th>
            <th class="text-right">{{ t('poll.failures') }}</th>
            <th>{{ t('poll.error') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in poll" :key="s.task">
            <td class="font-medium">{{ t(`poll.tasks.${s.task}`) }}</td>
            <td class="whitespace-nowrap tabular-nums">{{ formatDateTime(s.last_success_at, locale) }}</td>
            <td class="whitespace-nowrap tabular-nums">{{ formatDateTime(s.next_due_at, locale) }}</td>
            <td class="text-right tabular-nums">{{ s.last_duration_ms != null ? `${s.last_duration_ms} ms` : '—' }}</td>
            <td class="text-right tabular-nums" :class="{ 'text-red-600 dark:text-red-400': s.failures }">{{ s.failures }}</td>
            <td class="max-w-96 text-xs break-words text-red-600 dark:text-red-400">{{ s.last_error }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
