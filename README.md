# cesma-ng

cesma-ng ist eine webbasierte Verwaltung für Netzwerk-Switches. Sie ist eine komplette Neuentwicklung von `cesma-on-premise`.

**Unterstützte Switches:**

| Modell | Typ | Lesen | Schreiben | Backup / Restore | SSH-Schlüssel |
|---|---|---|---|---|---|
| Dell N1548P (DNOS 6) | `dell_n1500` | SNMP | SSH-CLI | SSH / – | – |
| Dell PowerSwitch OS10 | `dell_os10` | SNMP | SSH-CLI | SSH / – | – |
| HP 2530-48G (ArubaOS-Switch) | `aruba_os_switch` | SNMP | REST | REST / REST | SFTP + REST |
| HPE Aruba CX (AOS-CX) | `aruba_cx` | SNMP | REST | REST / REST | REST |

Das Modell wird beim Anlegen über die sysObjectID erkannt (Knopf „Erkennen“).

**Getestet:**
- Die Lese-Treiber sind gegen anonymisierte Mitschnitte echter Switches getestet (`backend/tests/fixtures/snmp`).
- Die Schreib-Befehle sind durch Golden-Tests festgelegt (`tests/test_writers.py`).
- An echter Hardware sind sie noch nicht abgenommen.
- Für die Aruba CX gibt es noch keinen Mitschnitt.

## Funktionen

Die Änderungen pro Version stehen im [CHANGELOG](CHANGELOG.md). Die Anwendung zeigt sie nach Updates als „Neuigkeiten“ an.

- **Anmeldung:**
  - Active Directory (LDAP) mit verschachtelten Gruppen
  - optional SSO über einen Reverse-Proxy
  - Rollen mit einzelnen Rechten pro Standort, dazu Superadmin
  - Notfall-Passwort, wenn LDAP nicht erreichbar ist
- **Inventar:**
  - Standorte, Gebäude, Räume, Geräte und Zugangsprofile; die Geheimnisse sind verschlüsselt gespeichert
  - automatische Erkennung neuer Switches
- **Abfragen im Hintergrund:**
  - Ports mit VLANs, PoE und Link-Wechseln
  - VLANs, MAC-Tabelle, ARP, LLDP-Nachbarn
  - Portstatistik
- **Änderungen** (immer mit Vorschau der exakten Befehle):
  - Ports, auch mehrere auf einmal und per Port-Profil
  - VLAN-Abgleich pro Standort, optional mit Tagging auf Uplinks
  - SSH-Schlüssel der Benutzer (pro Standort nach Recht „SSH-Zugang“)
  - Switch umbenennen (Hostname auf dem Gerät)
  - Backup-Wiederherstellung
- **Backups:** täglich, mit Vergleich, Download und Wochenbericht per Mail.
- **Clients:** Suche nach MAC, IP, Hostname, VLAN oder Port. Dazu Hersteller (IEEE), MAC-Typen, Verlauf, DNS und SNMP-Gateways.
- **Überblick:**
  - Topologie-Karte
  - Berichte: Firmware, freie Ports, PoE, Fehler, Backups
  - Benachrichtigungen
  - Audit-Log mit alten und neuen Werten
  - Konfigurationsregeln, geprüft gegen die Backups
  - freie Ports pro Gebäude/Raum
  - Port-Verlauf: Link- und Konfigurationsänderungen, angeschlossene Geräte
  - globale Suche (Strg+K)
  - Konsole für lesende Befehle

## Betrieb mit Docker Compose

```bash
cp .env.example .env    # CESMA_SECRET_KEY, POSTGRES_PASSWORD, LDAP und Adresse eintragen
docker compose up -d --build
```

| Container | Aufgabe |
|---|---|
| `db` | PostgreSQL 17 |
| `api` | FastAPI-Backend; führt beim Start die Datenbankmigrationen aus |
| `worker` | Abfragen der Switches, Backups, VLAN-Abgleich und andere Aufträge, geplante Aufgaben |
| `web` | Caddy: Oberfläche, Weiterleitung von `/api` an das Backend, HTTPS |

- **`CESMA_SECRET_KEY`** verschlüsselt alle gespeicherten Geheimnisse (Switch-Zugangsdaten, Backups). Wird er geändert, sind sie nicht mehr lesbar.
- **Erster Login:** Wer sich als Erstes anmeldet, wird Superadmin. Alle anderen bekommen ihre Rechte unter *Verwaltung → Benutzer*.
- **Die wichtigsten Einstellungen** stehen mit Erklärung in [.env.example](.env.example): LDAP, SSO, Mail und Abfrage-Intervalle.
- **Adresse und Ports:** `CESMA_SITE_ADDRESS` enthält alle Namen und IPs, unter denen die Oberfläche aufgerufen wird. Wer per IP aufruft, setzt zusätzlich `CESMA_DEFAULT_SNI` auf diese IP. Andere Ports als 80/443: `CESMA_HTTP_PORT` und `CESMA_HTTPS_PORT`.

### Geplante Aufgaben (Worker)

| Aufgabe | Intervall |
|---|---|
| Inventar (System, Ports, VLANs) | 2 min |
| MAC-Tabelle, ARP, Portzähler | 5 min |
| LLDP | 60 min |
| SNMP-Gateways (ARP) | 1 min |
| Clients zuordnen, DNS | 5 min |
| Ping-Sweep der VLANs mit „Scannen“ | 5 min |
| Suche nach neuen Switches | 15 min |
| Backup aller Switches | täglich (`CESMA_BACKUP_TIME`, Standard 22:30) |
| Backup-Bericht per Mail | sonntags 22:00 |
| MAC-Herstellerliste (IEEE) | sonntags 05:00 und beim ersten Start |
| Aufräumen | täglich 04:00 |

Aufräumen bedeutet:
- Audit-Log nach 8 Wochen
- Benachrichtigungen nach 6 Wochen
- Clients nach 8 Wochen
- Backups nach 4 Wochen (die neuesten 5 pro Gerät bleiben immer)
- Portstatistik nach 14 Tagen
- Port-Verlauf nach 90 Tagen

Bei unerreichbaren Geräten verlängert sich der Abstand der Abfragen automatisch (Backoff). Nach zwei fehlgeschlagenen Inventar-Abfragen gilt ein Gerät als offline und es gibt eine Benachrichtigung.

### Benutzer auf der Kommandozeile

```bash
docker compose exec api cesma users
docker compose exec api cesma set-superadmin <benutzer> [--revoke]
docker compose exec api cesma set-password <benutzer> [--superadmin]   # Notfall-Passwort
```

### Daten aus cesma-on-premise übernehmen

```bash
docker compose exec api cesma import-legacy \
  --mysql "mysql://cesma:PASSWORT@alter-server:3306/cesma" \
  --app-key "base64:…"       # APP_KEY aus der .env von cesma-on-premise
  --api-user admin            # API_USERNAME von cesma-on-premise
  [--with-backups]
```

- **Was übernommen wird:**
  - Standorte, Gebäude und Räume
  - Geräte; der alte Typ wird dem neuen Modell zugeordnet, und gleiche Benutzer/Passwort-Kombinationen werden zu einem Zugangsprofil
  - Standort-VLANs, MAC-Typen, SNMP-Gateways und SSH-Schlüssel
  - optional die Backups
- **Was nicht übernommen wird:** Benutzer und Rechte. Jeder meldet sich einmal an, dann vergibt ein Superadmin die Standorte.

## Rollen und Rechte

Benutzer bekommen **pro Standort eine Rolle**. Jede Rolle darf den Standort ansehen und Abfragen anstoßen; alles Weitere legen ihre Rechte fest. Rollen werden unter *Systemeinstellungen → Rollen* angelegt.

| Recht | Erlaubt |
|---|---|
| Geräte verwalten | Geräte anlegen, ändern, umbenennen, löschen; Gebäude, Räume; Switch-Suche |
| Ports ändern | Beschreibung, aktiv/deaktiviert, VLANs von Ports |
| VLANs verwalten | Soll-VLANs, Port-Profile, VLAN-Abgleich |
| Backups starten / herunterladen / wiederherstellen | jeweils einzeln; Herunterladen zeigt Geheimnisse der Switches |
| Konsole | lesende Befehle auf dem Switch |
| SSH-Schlüssel übertragen | die Schlüssel auf die Switches schreiben |
| SSH-Zugang | die eigenen SSH-Schlüssel des Benutzers kommen auf die Switches des Standorts |

- **Vorgegebene Rollen:** „Lesen“ (keine Rechte) und „Administrator“ (alle). Beide sind bearbeitbar, aber nicht löschbar.
- **Superadmin:** darf alles, auch Standorte, Benutzer, Rollen, Zugangsprofile, MAC-Typen und Gateways.
- **Prüfung:** Die Rechte prüft das Backend in den Service-Funktionen. Hintergrund-Aufträge prüfen beim Ausführen erneut die Rechte dessen, der sie gestartet hat.

### Notfall-Zugang ohne LDAP

Ein Superadmin kann Benutzern ein **Notfall-Passwort** geben (*Benutzer → Bearbeiten*). Es wird nur angenommen, wenn LDAP nicht erreichbar ist, und jede Anmeldung damit steht im Protokoll.

Funktioniert LDAP noch gar nicht (Ersteinrichtung), auf dem Server:

```bash
docker compose exec api cesma set-password <benutzer> --superadmin
```

Das legt den Benutzer bei Bedarf an. Die Anmeldung damit klappt, solange LDAP nicht erreichbar oder falsch eingerichtet ist; die Fehlermeldung beim Login nennt dann die Ursache.

## Entwicklung

**Voraussetzungen:** Python ≥ 3.12 und Node ≥ 22.

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"       # Linux/macOS: .venv/bin/pip
.venv/Scripts/alembic upgrade head          # SQLite-Datei backend/cesma.db
CESMA_AUTH_BACKEND=dev CESMA_DEV_USERS="admin:admin" CESMA_COOKIE_SECURE=false \
CESMA_SNMP_SIMULATOR_DIR=tests/fixtures/snmp \
  .venv/Scripts/uvicorn app.main:create_app --factory

# Hintergrunddienst (zweites Terminal)
CESMA_SNMP_SIMULATOR_DIR=tests/fixtures/snmp .venv/Scripts/python -m app.jobs.worker

# Frontend (drittes Terminal)
cd frontend && npm install && npm run dev    # http://localhost:5173
```

- **Simulator:** Mit `CESMA_SNMP_SIMULATOR_DIR` werden Geräte, deren Hostname einem Mitschnitt entspricht, aus dem Mitschnitt beantwortet: `dell-n1548p`, `dell-os10`, `hp-2530-48g`. Änderungen an diesen Geräten werden nur angezeigt, nie gesendet.
- **In Produktion gesperrt:** sowohl der Simulator als auch das Dev-Login.

**Prüfungen** (dieselben wie in der CI):

| Bereich | Befehle |
|---|---|
| Backend | `ruff check app tests`, `ruff format --check app tests`, `mypy app`, `pytest` |
| Frontend | `npm run lint`, `npm test`, `npm run build` |

**API-Typen:** Die Typen der Oberfläche kommen aus dem OpenAPI-Schema. Nach jeder API-Änderung:

```bash
cd backend && python scripts/export_openapi.py && cd ../frontend && npm run gen:api
```

**Neue Mitschnitte:**
- `backend/scripts/snmp_record.py` zeichnet einen Switch auf, nur lesend.
- `backend/scripts/anonymize_snmprec.py` macht daraus Test-Fixtures, ohne Namen, MACs, IPs oder Seriennummern.
- Die Rohdaten (`mitschnitte/`) werden nicht eingecheckt.

**Versionierung:**
- [Semantic Versioning](https://semver.org/lang/de/) und [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).
- Änderungen kommen unter `[Unreleased]`.
- Beim Release bekommen `frontend/package.json` und `backend/pyproject.toml` dieselbe Version.

## Architektur

```
backend/app/
  core/        Konfiguration, DB, Verschlüsselung, Domain-Fehler
  models/      SQLAlchemy-Modelle (durchgängig Fremdschlüssel, Zeitstempel in UTC)
  domain/      reine Datenklassen: Switch-Daten, Änderungen (Operationen), MAC-Helfer
  drivers/     mib.py (Standard-MIBs), base.py/vendors.py (Lesen), writers.py (Schreiben), registry.py
  transports/  SNMP (pysnmp + Mitschnitte), SSH-CLI (asyncssh), HTTP (httpx) – jeweils mit Test-Doubles
  services/    Anwendungslogik inkl. Rechteprüfung und Audit-Log, ohne HTTP
  api/v1/      dünne FastAPI-Router
  jobs/        Worker und Zeitplan
frontend/src/
  api/         fetch-Client und aus OpenAPI erzeugte Typen
  components/  Oberflächen-Bausteine (ui/ = Basiskomponenten im Tailwind-Stil)
  views/       Seiten; stores/ Pinia; i18n/ Deutsch/Englisch
```

**Grundsätze:**
- **Treiber** fassen nie die Datenbank an. Lesen läuft über Standard-MIBs; Herstellerunterschiede sind kleine überschreibbare Methoden.
- **Änderungen sind Daten** (`domain/changes.py`): Ein Service berechnet die Differenz, der Writer rendert sie für die Vorschau und führt genau das Gerenderte aus.
- **Services** bekommen einen `Caller` (Benutzer und IP) und prüfen selbst Rechte. Jede Änderung schreibt einen Audit-Eintrag.

**Sicherheit:**
- **Sessions:** Cookie mit HttpOnly, Secure und SameSite=Strict, dazu ein CSRF-Header.
- **Geheimnisse und Backups:** Zugangsdaten werden nie über die API zurückgegeben. Backups (mit Geheimnissen der Switches) können nur Standort-Administratoren laden.
- **Konsole:** nur lesende Befehle, über eine Positivliste.
- **SSO:** nur von vertrauenswürdigen Proxy-Adressen.
