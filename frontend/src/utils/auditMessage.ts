/**
 * German display text for audit log entries.
 *
 * The backend stores one English sentence per entry. Translating when displaying also covers
 * entries that already exist. Names, commands and technical error details stay as recorded; a
 * message that matches no rule is shown unchanged. The patterns mirror the audit.record() calls
 * of the backend.
 */

type Groups = Record<string, string>
type Rule = [pattern: RegExp, german: (g: Groups) => string]

const JOB_KINDS: Record<string, string> = {
  backup: 'Backup',
  discover: 'Netzsuche',
  restore: 'Wiederherstellung',
  ssh_keys: 'SSH-Schlüssel',
  vlan_sync: 'VLAN-Abgleich',
}

/** "<Word(s)> <name> deleted": the prefix length is fixed per action, so it is part of the pattern. */
function named(prefix: string, label: string, verb: string, german: string): Rule {
  return [new RegExp(`^${prefix} (?<name>.+) ${verb}$`, 's'), (g) => `${label} ${g.name} ${german}`]
}

const RULES: Record<string, Rule> = {
  'auth.emergency_login': [/^Login with emergency password/, () => 'Anmeldung mit Notfall-Passwort (Verzeichnis nicht erreichbar)'],
  'auth.login_failed': [/^Login failed$/, () => 'Anmeldung fehlgeschlagen'],
  'auth.sso_rejected': [/^SSO header from untrusted address (?<ip>.+)$/s, (g) => `SSO-Header von nicht vertrauenswürdiger Adresse ${g.ip}`],
  'backup.failed': [/^Backup of (?<device>.+?) failed: (?<error>.+)$/s, (g) => `Backup von ${g.device} fehlgeschlagen: ${g.error}`],
  'backup.restore': [/^(?<device>.+): backup of (?<date>.+) restored$/s, (g) => `${g.device}: Backup vom ${g.date} wiederhergestellt`],
  'building.create': named('Building', 'Gebäude', 'created', 'angelegt'),
  'building.delete': named('Building', 'Gebäude', 'deleted', 'gelöscht'),
  'building.update': [/^Building renamed to (?<name>.+)$/s, (g) => `Gebäude umbenannt in ${g.name}`],
  'compliance.delete': named('Configuration rule', 'Konfigurationsregel', 'deleted', 'gelöscht'),
  'compliance.save': named('Configuration rule', 'Konfigurationsregel', 'saved', 'gespeichert'),
  'credentials.create': named('Credential profile', 'Zugangsprofil', 'saved', 'gespeichert'),
  'credentials.delete': named('Credential profile', 'Zugangsprofil', 'deleted', 'gelöscht'),
  'credentials.update': named('Credential profile', 'Zugangsprofil', 'saved', 'gespeichert'),
  'device.create': named('Device', 'Gerät', 'created', 'angelegt'),
  'device.delete': named('Device', 'Gerät', 'deleted', 'gelöscht'),
  'device.discovered': [/^New switch found: (?<details>.+)$/s, (g) => `Neuer Switch gefunden: ${g.details}`],
  'device.hostname': [/^Hostname of (?<device>.+) set to (?<name>.+) on the switch$/s, (g) => `Hostname von ${g.device} auf dem Switch gesetzt: ${g.name}`],
  'device.offline': [/^(?<device>.+?) is not reachable: (?<error>.+)$/s, (g) => `${g.device} ist nicht erreichbar: ${g.error}`],
  'device.online': [/^(?<device>.+) is reachable again$/s, (g) => `${g.device} ist wieder erreichbar`],
  'device.rebooted': [/^(?<device>.+) was restarted$/s, (g) => `${g.device} wurde neu gestartet`],
  'device.rename_failed': [/^(?<device>.+?): (?<error>.+)$/s, (g) => `Umbenennen von ${g.device} fehlgeschlagen: ${g.error}`],
  'device.update': named('Device', 'Gerät', 'changed', 'geändert'),
  'gateway.delete': named('SNMP gateway', 'SNMP-Gateway', 'deleted', 'gelöscht'),
  'gateway.save': named('SNMP gateway', 'SNMP-Gateway', 'saved', 'gespeichert'),
  'legacy.import': [/^Import from cesma-on-premise: (?<counts>.+)$/s, (g) => `Import aus cesma-on-premise: ${g.counts}`],
  'mac_type.delete': named('MAC type', 'MAC-Typ', 'deleted', 'gelöscht'),
  'mac_type.save': [/^MAC type (?<details>.+)$/s, (g) => `MAC-Typ gespeichert: ${g.details}`],
  'port.update': [/^(?<device>.+?): (?<ports>.+) changed$/s, (g) => `${g.device}: ${g.ports} geändert`],
  'port.update_failed': [/^(?<device>.+?): (?<error>.+)$/s, (g) => `Portänderung an ${g.device} fehlgeschlagen: ${g.error}`],
  'port_profile.delete': named('Port profile', 'Port-Profil', 'deleted', 'gelöscht'),
  'port_profile.save': named('Port profile', 'Port-Profil', 'saved', 'gespeichert'),
  'role.delete': named('Role', 'Rolle', 'deleted', 'gelöscht'),
  'role.save': named('Role', 'Rolle', 'saved', 'gespeichert'),
  'room.create': named('Room', 'Raum', 'created', 'angelegt'),
  'room.delete': named('Room', 'Raum', 'deleted', 'gelöscht'),
  'room.update': [/^Room renamed to (?<name>.+)$/s, (g) => `Raum umbenannt in ${g.name}`],
  'site.create': named('Site', 'Standort', 'created', 'angelegt'),
  'site.delete': named('Site', 'Standort', 'deleted', 'gelöscht'),
  'site.update': [/^Site renamed to (?<name>.+)$/s, (g) => `Standort umbenannt in ${g.name}`],
  'ssh_key.add': [/^SSH key (?<name>.+) added$/s, (g) => `SSH-Schlüssel ${g.name} hinzugefügt`],
  'ssh_key.delete': named('SSH key', 'SSH-Schlüssel', 'deleted', 'gelöscht'),
  'ssh_keys.push': [/^(?<n>\d+) SSH keys uploaded to (?<device>.+)$/s, (g) => `${g.n} SSH-Schlüssel auf ${g.device} übertragen`],
  'user.update': named('User', 'Benutzer', 'changed', 'geändert'),
  'vlan.delete': named('VLAN', 'VLAN', 'deleted', 'gelöscht'),
  'vlan.import': [/^(?<n>\d+) VLANs imported from switches$/, (g) => `${g.n} VLANs von den Switches übernommen`],
  'vlan.save': named('VLAN', 'VLAN', 'saved', 'gespeichert'),
  'vlan.sync': [/^(?<device>.+): (?<n>\d+) VLAN change\(s\) applied$/s, (g) => `${g.device}: ${g.n} VLAN-${g.n === '1' ? 'Änderung' : 'Änderungen'} angewendet`],
}

const LOGINS: Record<string, string> = {
  Login: 'Anmeldung',
  'Emergency login': 'Anmeldung mit Notfall-Passwort',
  'Login (SSO)': 'Anmeldung (SSO)',
}

const JOB = /^Job (?<kind>\S+) #(?<id>\d+) queued$/

export function auditMessage(entry: { action: string; message: string }, locale: string): string {
  const { action, message } = entry
  if (locale !== 'de') return message
  if (action === 'auth.login') return LOGINS[message] ?? message
  if (action.startsWith('job.')) {
    const job = JOB.exec(message)?.groups
    return job ? `Auftrag ${JOB_KINDS[job.kind!] ?? job.kind} #${job.id} eingeplant` : message
  }
  const rule = RULES[action]
  const groups = rule?.[0].exec(message)
  return rule && groups ? rule[1](groups.groups ?? {}) : message
}
