<script setup lang="ts">
import { CommandLineIcon } from '@heroicons/vue/20/solid'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, type DeviceModel } from '@/api/client'
import UiSpinner from '@/components/ui/UiSpinner.vue'
import { useNotify } from '@/composables/useNotify'

const props = defineProps<{ deviceId: number; model: DeviceModel }>()
const { t } = useI18n()
const notify = useNotify()

const QUICK: Record<DeviceModel, string[]> = {
  dell_n1500: ['show vlan', 'show interfaces status', 'show mac address-table', 'show lldp remote-device all', 'show logging'],
  dell_os10: ['show vlan', 'show interface status', 'show mac address-table', 'show lldp neighbors', 'show logging log-file'],
  aruba_os_switch: ['show vlans', 'show interfaces brief', 'show mac-address', 'show lldp info remote-device', 'show logging -r'],
  aruba_cx: ['show vlan', 'show interface brief', 'show mac-address-table', 'show lldp neighbor-info', 'show logging -r'],
}
const quick = computed(() => QUICK[props.model])

const command = ref('')
const output = ref('')
const busy = ref(false)
const history = ref<string[]>([])
let historyIndex = -1

async function run(text = command.value): Promise<void> {
  if (!text.trim()) return
  busy.value = true
  command.value = text
  history.value = [text, ...history.value.filter((h) => h !== text)].slice(0, 30)
  historyIndex = -1
  await notify.run(async () => {
    output.value = (await api.post<{ output: string }>(`/devices/${props.deviceId}/console`, { command: text })).output
  })
  busy.value = false
}

function browse(step: number): void {
  if (!history.value.length) return
  historyIndex = Math.min(Math.max(historyIndex + step, -1), history.value.length - 1)
  command.value = historyIndex === -1 ? '' : history.value[historyIndex] ?? ''
}
</script>

<template>
  <div class="space-y-4">
    <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('console.hint') }}</p>
    <div class="flex flex-wrap gap-2">
      <button v-for="q in quick" :key="q" type="button" class="btn btn-secondary btn-sm font-mono" :disabled="busy" @click="run(q)">{{ q }}</button>
    </div>
    <form class="flex gap-2" @submit.prevent="run()">
      <div class="relative flex-1">
        <CommandLineIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
        <input
          v-model="command"
          class="input pl-8 font-mono"
          placeholder="show …"
          autocomplete="off"
          spellcheck="false"
          @keydown.up.prevent="browse(1)"
          @keydown.down.prevent="browse(-1)"
        />
      </div>
      <button type="submit" class="btn btn-primary" :disabled="busy || !command.trim()">
        <UiSpinner v-if="busy" /> {{ t('console.run') }}
      </button>
    </form>
    <pre class="max-h-[60vh] min-h-48 overflow-auto rounded-lg bg-gray-950 p-4 font-mono text-xs leading-relaxed text-gray-100">{{ output || t('console.empty') }}</pre>
  </div>
</template>
