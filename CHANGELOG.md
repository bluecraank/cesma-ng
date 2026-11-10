# Changelog

Alle nennenswerten Änderungen an cesma-ng werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt hält sich an [Semantic Versioning](https://semver.org/lang/de/).
Die Neuigkeiten in der Anwendung werden aus dieser Datei erzeugt.

## [Unreleased]

## [0.7.1] - 2026-11-10

### Geändert

- Seitenleiste einklappen per Pfeil rechts neben dem Logo (statt unten in der Leiste)
- Scrollbalken der Seitenleiste schmal und dunkel, passend zum Menü

### Behoben

- Dark Mode: aufgeklappte Auswahllisten waren weiß auf weiß; Listen, Scrollbalken und andere Bedienelemente des Browsers folgen jetzt dem Farbschema

### Entfernt

- Eigene Anzeigegröße wieder entfernt; die Darstellung folgt wieder nur der Windows-Skalierung bzw. dem Browser-Zoom (Strg + / Strg −)

## [0.7.0] - 2026-11-10

### Hinzugefügt

- Eigene Anzeigegröße: oben rechts mit − / + zwischen 75 % und 150 % einstellen, Klick auf die Prozentzahl setzt auf 100 % zurück; gilt zusätzlich zur Windows-Skalierung und wird pro Browser gespeichert

## [0.6.2] - 2026-11-10

### Behoben

- Switchports: auf kleineren Bildschirmen bzw. mit Windows-Skalierung (z. B. 150 %) passten 48/56-Port-Switches nicht in die Breite; die Ports werden dort jetzt etwas kleiner dargestellt

## [0.6.1] - 2026-11-10

### Geändert

- Switchports: statt der Auswahl „sofort“ gibt es neben „Frei, wenn unbenutzt seit“ einen Haken „Live-Zustand“ – dann gilt jeder Port ohne Link als frei

## [0.6.0] - 2026-11-10

### Hinzugefügt

- Switchports: Frontansicht aller Switches wie am Gerät – ungerade Ports oben, gerade unten, Uplink-/SFP-Ports als eigener Block, Stack-Einheiten untereinander; Farben für frei, Link aktiv, Uplink, kein Link und deaktiviert, PoE-Punkt, Details beim Überfahren, Klick öffnet den Port

### Geändert

- „Freie Ports“ ist in der Switchport-Ansicht aufgegangen: freie Ports sind dort grün markiert, mit denselben Filtern (Gebäude/Raum, unbenutzt seit, PoE, deaktivierte Ports) und optional nur Switches mit freien Ports
- Tabellenköpfe bleiben beim Scrollen sichtbar; lange Tabellen scrollen innerhalb ihrer Karte

## [0.5.0] - 2026-11-09

### Hinzugefügt

- Konfigurationsregeln: Regeln wie „NTP-Server gesetzt“ oder „kein Telnet“ (regulärer Ausdruck, „muss enthalten“ / „darf nicht enthalten“, optional nur für bestimmte Modelle) werden gegen das neueste Backup jedes Switches geprüft; Übersicht als Matrix mit den passenden Zeilen (nur für Benutzer, die Backups herunterladen dürfen)
- Freie Ports: Access-Ports ohne Link, an denen seit einer wählbaren Zeit kein Gerät war, gefiltert nach Gebäude oder Raum und optional nur PoE; Klick springt zum Port
- Port-Verlauf (aufgeklappter Port): Link up/down, Geschwindigkeitswechsel, Änderungen in cesma-ng (mit Benutzer) und direkt am Switch (mit alt/neu), dazu alle Geräte, die an diesem Port waren (MAC, Hersteller, IP/Hostname, erstmals/zuletzt gesehen); 90 Tage aufbewahrt (`CESMA_RETENTION_PORT_HISTORY_DAYS`)

## [0.4.0] - 2026-11-09

### Hinzugefügt

- Rollen und Rechte: frei definierbare Rollen mit einzelnen Rechten (Geräte verwalten, Ports ändern, VLANs verwalten, Backups starten/herunterladen/wiederherstellen, Konsole, SSH-Schlüssel übertragen, SSH-Zugang); Übersicht als Matrix unter *Systemeinstellungen → Rollen*
- Notfall-Passwort pro Benutzer: Anmeldung, wenn LDAP nicht erreichbar ist; auch per `cesma set-password <benutzer>` (legt den Benutzer bei Bedarf an)
- Fehlermeldung beim Login nennt die Ursache, wenn LDAP nicht geht (Dienstkonto abgelehnt, Zertifikat nicht vertraut, Server nicht erreichbar, Suchbasis falsch)
- SSH-Schlüssel gehören Benutzern: jeder verwaltet seine eigenen; auf die Switches kommen die Schlüssel der Benutzer mit dem Recht „SSH-Zugang“ am Standort
- SSH-Schlüssel per Knopf auf einen einzelnen Switch übertragen (Geräteseite)
- Switch umbenennen: setzt den Hostnamen auf dem Switch und den Namen in cesma-ng, mit Vorschau der Befehle
- Geräteliste: Symbol pro Switch (Hersteller, Status), IP-Adresse und DNS-Name
- Hinweise bei Geräten mit fehlenden Zugangsdaten (kein Zugangsprofil, kein SSH- oder API-Login, keine SNMP-Community) oder die nicht erreichbar sind, mit der Fehlermeldung und was zu tun ist
- Ports: Bereich mit Shift+Klick auswählen, Auswahl-Leiste mit allen gewählten Ports
- VLANs am Port: pro VLAN „Aus / Untagged / Tagged“ wählen, Suche, Markierung geänderter Zeilen; bei mehreren Ports bleiben unterschiedliche Einstellungen („gemischt“) unangetastet
- Port-Profile: Tagged-VLANs mit Vorschlägen beim Tippen und Anzeige der VLAN-Namen; Bereiche wie 100-105
- Klick auf den Ort eines Clients (und Treffer der globalen Suche) springt direkt zum Port und hebt ihn hervor
- Link „Port-Profile verwalten“ im Port-Dialog

### Geändert

- Aufträge und SSH-Schlüssel stehen unter *Systemeinstellungen* (vorher *Verwaltung*)
- Die bisherigen Rollen heißen „Lesen“ und „Administrator“ und sind bearbeitbar; bestehende Rechte bleiben erhalten
- SSH-Schlüssel aus cesma-on-premise haben keinen Besitzer und kommen weiter auf alle Switches

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

[Unreleased]: https://github.com/bluecraank/cesma-ng/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/bluecraank/cesma-ng/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/bluecraank/cesma-ng/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bluecraank/cesma-ng/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/bluecraank/cesma-ng/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bluecraank/cesma-ng/releases/tag/v0.1.0
