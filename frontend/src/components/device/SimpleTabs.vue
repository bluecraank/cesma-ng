<script setup lang="ts">
/** The VLAN, MAC, neighbour and poll status tabs of a device: plain read-only tables. */
import { MagnifyingGlassIcon } from '@heroicons/vue/20/solid'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DeviceVlan, FdbEntry, LldpNeighbor, PollState } from '@/api/client'
import UiCsvButton from '@/components/ui/UiCsvButton.vue'
import UiSortTh from '@/components/ui/UiSortTh.vue'
import { useTableSort } from '@/composables/useTableSort'
import { downloadCsv } from '@/utils/csv'
import { formatDateTime } from '@/utils/format'
import { vlanMatcher } from '@/utils/vlanFilter'

const props = defineProps<{
  tab: 'vlans' | 'fdb' | 'lldp' | 'poll'
  vlans?: DeviceVlan[]
  fdb?: FdbEntry[]
  lldp?: LldpNeighbor[]
  poll?: PollState[]
  /** for the name of the CSV file */
  deviceName?: string
}>()
const { t, locale } = useI18n()
const search = ref('')

watch(() => props.tab, () => (search.value = ''))

const has = (q: string, ...values: (string | null | undefined)[]): boolean => values.some((v) => v?.toLowerCase().includes(q))

const vlanFiltered = computed(() => {
  const matches = vlanMatcher(search.value)
  return (props.vlans ?? []).filter((v) => matches(v.vid, v.name))
})
const { sort: vlanSort, sorted: vlanRows } = useTableSort(() => vlanFiltered.value, {
  vid: (v) => v.vid,
  name: (v) => v.name,
  untagged: (v) => v.untagged_ports,
  tagged: (v) => v.tagged_ports,
})

const fdbFiltered = computed(() => {
  const q = search.value.trim().toLowerCase()
  const rows = props.fdb ?? []
  return q ? rows.filter((e) => has(q, e.mac_address, e.port_name, String(e.vid ?? ''), ...e.ip_addresses)) : rows
})
const { sort: fdbSort, sorted: fdbRows } = useTableSort(() => fdbFiltered.value, {
  mac: (e) => e.mac_address,
  vid: (e) => e.vid,
  port: (e) => e.port_name,
  ip: (e) => e.ip_addresses[0],
})

const lldpFiltered = computed(() => {
  const q = search.value.trim().toLowerCase()
  const rows = props.lldp ?? []
  return q
    ? rows.filter((n) => has(q, n.local_port_name, n.system_name, n.chassis_id, n.remote_port, n.remote_port_description, n.management_address, n.system_description))
    : rows
})
const { sort: lldpSort, sorted: lldpRows } = useTableSort(() => lldpFiltered.value, {
  localPort: (n) => n.local_port_name,
  system: (n) => n.system_name || n.chassis_id,
  remotePort: (n) => n.remote_port_description || n.remote_port,
  address: (n) => n.management_address,
  model: (n) => n.system_description,
})

function exportCsv(): void {
  const file = `${props.tab}-${props.deviceName ?? ''}`
  if (props.tab === 'vlans') {
    downloadCsv(
      file,
      [t('vlans.vid'), t('common.name'), t('vlans.untaggedPorts'), t('vlans.taggedPorts')],
      vlanRows.value.map((v) => [v.vid, v.name, v.untagged_ports, v.tagged_ports]),
    )
  } else if (props.tab === 'fdb') {
    downloadCsv(
      file,
      [t('fdb.mac'), t('fdb.vlan'), t('ports.port'), t('fdb.ip')],
      fdbRows.value.map((e) => [e.mac_address, e.vid, e.port_name, e.ip_addresses.join(', ')]),
    )
  } else {
    downloadCsv(
      file,
      [t('lldp.localPort'), t('lldp.system'), t('lldp.remotePort'), t('lldp.address'), t('device.model')],
      lldpRows.value.map((n) => [n.local_port_name, n.system_name || n.chassis_id, n.remote_port_description || n.remote_port, n.management_address, n.system_description]),
    )
  }
}

const count = computed(() =>
  props.tab === 'vlans'
    ? `${vlanRows.value.length} / ${props.vlans?.length ?? 0}`
    : props.tab === 'fdb'
      ? `${fdbRows.value.length} / ${props.fdb?.length ?? 0}`
      : `${lldpRows.value.length} / ${props.lldp?.length ?? 0}`,
)
</script>

<template>
  <div class="space-y-4">
    <div v-if="tab !== 'poll'" class="flex items-center gap-4">
      <div class="relative">
        <MagnifyingGlassIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
        <input v-model="search" class="input w-72 pl-8" :placeholder="tab === 'vlans' ? t('vlans.search') : t('common.search')" />
      </div>
      <span class="ml-auto text-sm text-gray-500">{{ count }}</span>
      <UiCsvButton @click="exportCsv" />
    </div>

    <div class="card table-wrap">
      <table v-if="tab === 'vlans'" class="table">
        <thead>
          <tr>
            <UiSortTh :sort="vlanSort" column="vid">{{ t('vlans.vid') }}</UiSortTh>
            <UiSortTh :sort="vlanSort" column="name">{{ t('common.name') }}</UiSortTh>
            <UiSortTh :sort="vlanSort" column="untagged" class="!text-right">{{ t('vlans.untaggedPorts') }}</UiSortTh>
            <UiSortTh :sort="vlanSort" column="tagged" class="!text-right">{{ t('vlans.taggedPorts') }}</UiSortTh>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in vlanRows" :key="v.vid">
            <td class="font-medium">{{ v.vid }}</td>
            <td>{{ v.name }}</td>
            <td class="text-right tabular-nums">{{ v.untagged_ports }}</td>
            <td class="text-right tabular-nums">{{ v.tagged_ports }}</td>
          </tr>
          <tr v-if="!vlanRows.length"><td colspan="4" class="py-6 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>

      <table v-else-if="tab === 'fdb'" class="table">
        <thead>
          <tr>
            <UiSortTh :sort="fdbSort" column="mac">{{ t('fdb.mac') }}</UiSortTh>
            <UiSortTh :sort="fdbSort" column="vid">{{ t('fdb.vlan') }}</UiSortTh>
            <UiSortTh :sort="fdbSort" column="port">{{ t('ports.port') }}</UiSortTh>
            <UiSortTh :sort="fdbSort" column="ip">{{ t('fdb.ip') }}</UiSortTh>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in fdbRows" :key="`${e.vid}-${e.mac_address}`">
            <td class="font-mono text-xs">{{ e.mac_address }}</td>
            <td class="tabular-nums">{{ e.vid ?? '—' }}</td>
            <td>{{ e.port_name ?? '—' }}</td>
            <td>{{ e.ip_addresses.join(', ') }}</td>
          </tr>
          <tr v-if="!fdbRows.length"><td colspan="4" class="py-6 text-center text-gray-500">—</td></tr>
        </tbody>
      </table>

      <table v-else-if="tab === 'lldp'" class="table">
        <thead>
          <tr>
            <UiSortTh :sort="lldpSort" column="localPort">{{ t('lldp.localPort') }}</UiSortTh>
            <UiSortTh :sort="lldpSort" column="system">{{ t('lldp.system') }}</UiSortTh>
            <UiSortTh :sort="lldpSort" column="remotePort">{{ t('lldp.remotePort') }}</UiSortTh>
            <UiSortTh :sort="lldpSort" column="address">{{ t('lldp.address') }}</UiSortTh>
            <UiSortTh :sort="lldpSort" column="model">{{ t('device.model') }}</UiSortTh>
          </tr>
        </thead>
        <tbody>
          <tr v-for="n in lldpRows" :key="n.id">
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
          <tr v-if="!lldpRows.length"><td colspan="5" class="py-6 text-center text-gray-500">—</td></tr>
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
