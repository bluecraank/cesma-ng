import { describe, expect, it } from 'vitest'
import { auditMessage } from '@/utils/auditMessage'

describe('auditMessage', () => {
  it.each([
    ['auth.login', 'Login', 'Anmeldung'],
    ['auth.login', 'Login (SSO)', 'Anmeldung (SSO)'],
    ['auth.login_failed', 'Login failed', 'Anmeldung fehlgeschlagen'],
    ['backup.failed', 'Backup of sw-1 failed: [Errno 11001] getaddrinfo failed', 'Backup von sw-1 fehlgeschlagen: [Errno 11001] getaddrinfo failed'],
    ['backup.restore', 'sw-1: backup of 2026-11-09 15:43 restored', 'sw-1: Backup vom 2026-11-09 15:43 wiederhergestellt'],
    ['building.update', 'Building renamed to Haus B', 'Gebäude umbenannt in Haus B'],
    ['compliance.save', 'Configuration rule NTP gesetzt saved', 'Konfigurationsregel NTP gesetzt gespeichert'],
    ['credentials.update', 'Credential profile Standard saved', 'Zugangsprofil Standard gespeichert'],
    ['device.create', 'Device sw-1 (10.0.0.1) created', 'Gerät sw-1 (10.0.0.1) angelegt'],
    ['device.discovered', 'New switch found: sw-1 (10.0.0.1, N1548P)', 'Neuer Switch gefunden: sw-1 (10.0.0.1, N1548P)'],
    ['device.hostname', 'Hostname of sw-1 set to core-1 on the switch', 'Hostname von sw-1 auf dem Switch gesetzt: core-1'],
    ['device.offline', 'sw-1 is not reachable: timeout', 'sw-1 ist nicht erreichbar: timeout'],
    ['device.online', 'sw-1 is reachable again', 'sw-1 ist wieder erreichbar'],
    ['device.rebooted', 'sw-1 was restarted', 'sw-1 wurde neu gestartet'],
    ['device.rename_failed', 'sw-1: denied', 'Umbenennen von sw-1 fehlgeschlagen: denied'],
    ['gateway.save', 'SNMP gateway fw-1 (10.0.0.254) saved', 'SNMP-Gateway fw-1 (10.0.0.254) gespeichert'],
    ['job.backup', 'Job backup #12 queued', 'Auftrag Backup #12 eingeplant'],
    ['legacy.import', 'Import from cesma-on-premise: devices 3, sites 1', 'Import aus cesma-on-premise: devices 3, sites 1'],
    ['mac_type.save', 'MAC type 00:20:6b = Drucker', 'MAC-Typ gespeichert: 00:20:6b = Drucker'],
    ['port.update', 'sw-eg-02: 1 changed', 'sw-eg-02: 1 geändert'],
    ['port.update', 'sw-eg-02: 1, 2, 3 changed', 'sw-eg-02: 1, 2, 3 geändert'],
    ['port.update_failed', 'sw-1: timeout', 'Portänderung an sw-1 fehlgeschlagen: timeout'],
    ['ssh_key.add', 'SSH key Laptop (SHA256:abc) added', 'SSH-Schlüssel Laptop (SHA256:abc) hinzugefügt'],
    ['ssh_keys.push', '2 SSH keys uploaded to sw-1', '2 SSH-Schlüssel auf sw-1 übertragen'],
    ['user.update', 'User alice changed', 'Benutzer alice geändert'],
    ['vlan.delete', 'VLAN 120 Voice deleted', 'VLAN 120 Voice gelöscht'],
    ['vlan.import', '12 VLANs imported from switches', '12 VLANs von den Switches übernommen'],
    ['vlan.sync', 'sw-1: 1 VLAN change(s) applied', 'sw-1: 1 VLAN-Änderung angewendet'],
    ['vlan.sync', 'sw-1: 3 VLAN change(s) applied', 'sw-1: 3 VLAN-Änderungen angewendet'],
  ])('%s: %s', (action, message, german) => expect(auditMessage({ action, message }, 'de')).toBe(german))

  it('keeps commands and unknown messages unchanged', () => {
    expect(auditMessage({ action: 'console.command', message: 'sw-1: show vlans' }, 'de')).toBe('sw-1: show vlans')
    expect(auditMessage({ action: 'device.create', message: 'something else' }, 'de')).toBe('something else')
    expect(auditMessage({ action: 'new.action', message: 'Text' }, 'de')).toBe('Text')
  })

  it('leaves English untouched', () => {
    expect(auditMessage({ action: 'device.rebooted', message: 'sw-1 was restarted' }, 'en')).toBe('sw-1 was restarted')
  })
})
