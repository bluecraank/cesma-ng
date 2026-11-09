import type { components } from './schema'

type Schemas = components['schemas']
export type User = Schemas['UserOut']
export type Site = Schemas['SiteOut']
export type Building = Schemas['BuildingOut']
export type Room = Schemas['RoomOut']
export type Device = Schemas['DeviceOut']
export type DeviceIn = Schemas['DeviceIn']
export type DeviceUpdate = Schemas['DeviceUpdate']
export type DeviceModel = Device['model']
export type DeviceStatus = Device['status']
export type SiteRole = Schemas['SiteRoleOut']['role']
export type CredentialProfile = Schemas['CredentialProfileOut']
export type CredentialProfileIn = Schemas['CredentialProfileIn']
export type AuditEntry = Schemas['AuditEntryOut']
export type AuditPage = Schemas['Page_AuditEntryOut_']
export type Port = Schemas['PortOut']
export type DeviceVlan = Schemas['DeviceVlanOut']
export type FdbEntry = Schemas['FdbEntryOut']
export type LldpNeighbor = Schemas['LldpNeighborOut']
export type PollState = Schemas['PollStateOut']
export type DetectResult = Schemas['DetectResult']
export type Notification = Schemas['NotificationOut']
export type ClientRow = Schemas['ClientOut']
export type ClientPage = Schemas['Page_ClientOut_']
export type MacType = Schemas['MacTypeOut']
export type Gateway = Schemas['GatewayOut']
export type SearchHit = Schemas['SearchHit']
export type ChangePlan = Schemas['ChangePlanOut']
export type ApplyResult = Schemas['ApplyResult']
export type SiteVlan = Schemas['SiteVlanOut']
export type SiteVlanIn = Schemas['SiteVlanIn']
export type PortProfile = Schemas['PortProfileOut']
export type Backup = Schemas['BackupOut']
export type Job = Schemas['JobOut']
export type SshKey = Schemas['SshKeyOut']

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

let onUnauthorized: () => void = () => {}

/** Called on every 401 response (session expired) — wired to the router in main.ts. */
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const url = new URL(`/api/v1${path}`, window.location.origin)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== '') url.searchParams.set(key, String(value))
  }
  const response = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: {
      'X-Requested-With': 'cesma',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (response.status === 401 && !path.startsWith('/auth/')) onUnauthorized()
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
  return (response.status === 204 ? undefined : await response.json()) as T
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg ?? '').join(', ')
    }
  } catch {
    /* not JSON */
  }
  return response.statusText || `HTTP ${response.status}`
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, undefined, query),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  delete: (path: string) => request<void>('DELETE', path),
}
