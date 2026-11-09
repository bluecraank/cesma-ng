import {
  CameraIcon,
  ComputerDesktopIcon,
  CpuChipIcon,
  DevicePhoneMobileIcon,
  PhoneIcon,
  PrinterIcon,
  ServerIcon,
  TvIcon,
  WifiIcon,
} from '@heroicons/vue/24/outline'

/** Icons selectable for MAC types (must match MAC_TYPE_ICONS in the backend). */
export const MAC_TYPE_ICONS = {
  device: DevicePhoneMobileIcon,
  phone: PhoneIcon,
  printer: PrinterIcon,
  computer: ComputerDesktopIcon,
  camera: CameraIcon,
  wifi: WifiIcon,
  server: ServerIcon,
  tv: TvIcon,
  iot: CpuChipIcon,
} as const

export type MacTypeIconName = keyof typeof MAC_TYPE_ICONS
