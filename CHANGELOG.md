# Changelog

Alle nennenswerten Änderungen an cesma-ng werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt hält sich an [Semantic Versioning](https://semver.org/lang/de/).
Die Neuigkeiten in der Anwendung werden aus dieser Datei erzeugt.

## [Unreleased]

### Behoben

- Docker: eigene Ports für die Oberfläche (`CESMA_HTTP_PORT`, `CESMA_HTTPS_PORT`); die Weiterleitung von HTTP auf HTTPS nutzt jetzt den eingestellten Port statt immer 443
- Docker: Aufruf per IP-Adresse funktioniert (`CESMA_DEFAULT_SNI`), vorher brach der Verbindungsaufbau mit einem SSL-Fehler ab
- Topologie blieb weiß: die Zeichenfläche hatte die Höhe 0

## [0.3.0] - 2026-11-09

### Hinzugefügt

- Seitenleiste lässt sich einklappen (merkt sich die Einstellung)
- Geräteseite mit Reitern: Ports (mit VLANs, PoE, Nachbar, MACs pro Port), VLANs, MAC-Adressen mit IP, LLDP-Nachbarn, Abfragestatus
- Knopf „Jetzt abfragen“ auf der Geräteseite
- Benachrichtigungen mit Glocke und Zähler in der Kopfzeile, einzeln oder alle als erledigt markieren
- Knopf „Erkennen“ beim Anlegen eines Geräts: Modell wird per SNMP ermittelt
- Uplinks werden automatisch erkannt (LAG, LLDP-Nachbar ist ein Switch, viele getaggte VLANs)
- Clients: Suche nach MAC (jedes Format, auch Teilstücke), IP, Hostname, VLAN, Switch oder Port; Ort ist immer der Access-Port, nie ein Uplink
- Client-Verlauf: erstmals und zuletzt gesehen, auch nachdem ein Gerät verschwunden ist (Aufbewahrung 8 Wochen)
- Hersteller der MAC-Adressen aus der IEEE-Liste (wöchentlich aktualisiert), Hostnamen per Reverse-DNS
- MAC-Typen mit Symbol (z. B. Telefon, Drucker) und SNMP-Gateways als Quelle für IP-Adressen
- Globale Suche mit Strg+K oder „/“: Geräte, Port-Beschreibungen, Clients und VLANs
- Ports ändern (Beschreibung, aktiv/deaktiviert, untagged/tagged VLANs) mit Vorschau der exakten Befehle vor dem Ausführen; mehrere Ports gleichzeitig
- Warnungen in der Vorschau: Uplink betroffen, Uplink abschalten (rot), VLAN existiert nicht auf dem Switch
- Port-Profile: benannte Vorlagen (z. B. „Büro: untagged 10, tagged 20“) mit einem Klick auf Ports anwenden
- Soll-VLANs pro Standort mit Anzeige „auf X von Y Switches“, Übernahme der vorhandenen VLANs von den Switches
- VLAN-Abgleich mit Vorschau pro Switch, optional überzählige VLANs löschen (nie VLAN 1, Warnung wenn noch in Benutzung)
- Schreiben für alle vier Modelle: Dell N1500 und OS10 per SSH-CLI, HP/Aruba 2530 und Aruba CX per REST-API (vorher: Dell OS10 nur lesend)
- Backups: täglich automatisch, „Jetzt sichern“, Download, Vergleich mit der vorherigen Version, Kennzeichnung „geändert“; die neuesten 5 pro Gerät bleiben immer erhalten
- Wöchentlicher Backup-Bericht per Mail
- SSH-Schlüssel verwalten und auf Switches übertragen (mindestens zwei Schlüssel)
- Aufträge (VLAN-Abgleich, Backup, SSH-Schlüssel) laufen im Hintergrund mit Fortschritt und Protokoll
- Zugangsprofil: HTTP oder HTTPS für die REST-API wählbar
- Simulationsmodus für Entwicklung und Demo: Geräte aus Mitschnitten, Änderungen werden nur angezeigt, nie gesendet
- Topologie: Karte der Switch-Verbindungen aus LLDP mit Portnamen und Geschwindigkeit, ausgefallene Verbindungen rot, optional weitere LLDP-Nachbarn (APs, Telefone); Klick öffnet das Gerät
- VLAN-Abgleich optional mit „VLANs auch auf Uplinks taggen“ (fügt nur hinzu, entfernt nie)
- Portstatistik: Datenverkehr, Spitze, Auslastung und Fehler pro Port (24 h) für alle Modelle per SNMP, 14 Tage aufbewahrt
- SSO über einen Reverse-Proxy (z. B. Authentik) per HTTP-Header; nur von vertrauenswürdigen Proxy-Adressen, Benutzer wird zusätzlich im LDAP geprüft
- Docker Compose: eigener Container für den Hintergrunddienst
- Konsole auf der Geräteseite: nur lesende Befehle (show, ping, traceroute) mit Schnellbefehlen pro Modell und Verlauf; jeder Befehl im Protokoll
- Automatische Erkennung neuer Switches über die ARP-Tabellen (Hersteller Dell/HP/Aruba, Modell per SNMP geprüft) und manuelle Netzsuche für einen IP-Bereich; Funde erscheinen als „Unbestätigt“ und lassen sich übernehmen oder verwerfen (verworfene werden nicht erneut gefunden)
- Ping-Sweep für VLANs mit „Scannen“, damit Router die Clients lernen
- Berichte: Firmware-Stände, freie Ports pro Switch, PoE-Nutzung, Ports mit Fehlern, Geräte ohne aktuelles Backup
- Backup wiederherstellen (HP/Aruba 2530 und Aruba CX), Bestätigung durch Eingabe des Gerätenamens
- Datenübernahme aus cesma-on-premise: `cesma import-legacy` (Standorte, Gebäude, Räume, Geräte mit Zugangsdaten, VLANs, MAC-Typen, SNMP-Gateways, SSH-Schlüssel, optional Backups)

### Geändert

- Neue Switches bekommen das Zugangsprofil des Switches, der sie gemeldet hat (vorher: Passwort „public“)

### Sicherheit

- Backup-Download nur für Standort-Administratoren (Backups enthalten Geheimnisse der Switches)
- Rechte werden bei Hintergrund-Aufträgen beim Ausführen erneut geprüft

### Geändert

- Versionierung nach Semantic Versioning, Changelog nach Keep a Changelog

## [0.2.0] - 2026-11-09

### Hinzugefügt

- Switch-Treiber für Dell N1500, Dell OS10, HP/Aruba 2530 und Aruba CX (SNMP)
- Automatische Modellerkennung über die sysObjectID
- Hintergrunddienst fragt Ports, VLANs, MAC-Tabelle, ARP und LLDP-Nachbarn ab
- Benachrichtigungen: Gerät nicht erreichbar, wieder erreichbar, Neustart, Uplink down/up, Geschwindigkeitswechsel
- Versionsanzeige im Menü und Neuigkeiten-Fenster nach Updates
- Logo von cesma-on-premise

### Geändert

- Neue Oberfläche im Tailwind-Stil

## [0.1.0] - 2026-11-09

### Hinzugefügt

- Anmeldung über Active Directory (LDAP), Rollen und Rechte pro Standort
- Standorte, Gebäude, Räume und Geräte verwalten
- Zugangsprofile mit verschlüsselt gespeicherten Zugangsdaten
- Audit-Log mit alten und neuen Werten
- Deutsch/Englisch, Hell-/Dunkelmodus

[Unreleased]: https://github.com/bluecraank/cesma-ng/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/bluecraank/cesma-ng/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bluecraank/cesma-ng/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bluecraank/cesma-ng/releases/tag/v0.1.0
