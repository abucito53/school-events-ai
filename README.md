# Schultermine-KI

Automatisiert das Erfassen von Schulterminen deiner Tochter: Ein dediziertes
Gmail-Konto empfängt gezielt weitergeleitete Schul-Mails (über ein Label),
ein **lokales** KI-Modell (Ollama) extrahiert daraus die Termine, die
automatisch in einen eigenen Google Kalender geschrieben werden, den du in
Proton Calendar abonnierst. Zusätzlich gibt es wöchentlich eine
Zusammenfassungs-Mail.

**Was läuft wo (wichtig, bevor du den Anleitungen folgst):**

| Komponente | Läuft... | Warum |
|---|---|---|
| OAuth2-Login (einmalig) | **immer nativ** | Braucht einen echten Browser, funktioniert nicht headless in Docker |
| Ollama (KI-Modell) | **Docker** | Läuft dort ohne Apple-Silicon-GPU (CPU-only), bei eurer niedrigen Mail-Frequenz aber irrelevant |
| Scheduler (laufender Betrieb: Mails abholen, verarbeiten, Wochenmail) | **Docker** (empfohlen) *oder* nativ | Docker macht diesen Teil plattformunabhängig und cloud-portabel |

Einzige nativ nötige Installation: Python + die Bibliotheken für den
einmaligen Login (Teil 1). Alles andere - Ollama und der laufende Betrieb -
steckt in `docker-compose.yml` (Teil 2).

## Update von einer älteren Version (Ordner-/Package-Rename)

Der Projektordner und das Python-Package hiessen bisher `schultermine-ki` /
`schultermine` - das war der letzte deutsche Rest im sonst englischen Code
und wurde deshalb auf `school-events-ai` / `school_events` umbenannt (Details
siehe "Zur Sprache im Code" weiter unten). Falls du bereits eine ältere
Version am Laufen hast, brauchst du dafür einmalig:

```bash
docker compose down                       # alten Container stoppen
mv schultermine-ki school-events-ai       # Ordner umbenennen
cd school-events-ai
docker compose up -d --build              # neu bauen und starten
```

Nicht betroffen, unverändert: `~/SchulTermine/` (dein Datenordner inkl.
`eingang/`), der Google-Kalender-Name "Schultermine" und alle bereits
synchronisierten Kalendereinträge - dafür sorgt der weiterhin unveränderte,
interne `schultermine_id`-Schlüssel in `calendar_sync.py` (siehe Kommentar
dort). Nur eine alte lokale `calendar/schultermine.ics`-Backup-Datei wird
nicht mehr aktualisiert (kann gelöscht werden, siehe "Wo landen die Daten").

## Architektur im Überblick

```
Schul-Mail
   │  (du leitest sie bewusst weiter, dediziertes Konto = Auswahl)
   ▼
Dediziertes Gmail-Konto ──(OAuth2, nur lesen)──▶ GmailFetcher
   │                                                   │
   │  (oder: du ziehst PDFs/.eml manuell rein)         ▼
   └────────────────────────────────▶ ~/SchulTermine/eingang/
                                                        │
                                                        ▼
                                              InboxProcessor
                                          (Text → lokales Ollama-Modell
                                           via OllamaEventExtractor
                                           → SchoolEvent-Objekte)
                                                        │
                                     ┌──────────────────┼───────────────────┐
                                     ▼                  ▼                   ▼
                          ~/SchulTermine/data/   GoogleCalendarSync   IcsExporter
                          events.json (Archiv)   "Schultermine"       (Backup/Offline)
                                                        │
                                                        ▼
                                          Proton Calendar (Abo der
                                          geheimen iCal-Adresse)

Sonntags zusätzlich: GmailMailer → Zusammenfassungs-Mail (Gmail-API)
```

### Code-Struktur (Package `school_events/`)

| Modul | Verantwortlichkeit |
|---|---|
| `config.py` | Lädt `config.yaml` in typisierte Dataclasses (`AppConfig`, `Paths`, ...) |
| `models.py` | `SchoolEvent`-Dataclass, Umwandlung LLM-JSON ↔ Objekt ↔ Speicher-JSON |
| `content.py` | `ContentExtractor`: liest PDF/.eml, liefert Text fürs LLM |
| `ollama_client.py` | `OllamaEventExtractor`: schickt Text an Ollama, parst Antwort zu `SchoolEvent`s |
| `store.py` | `EventRepository`, `JsonSet`: Persistenz (events.json, Dedup-Listen) |
| `google_auth.py` | `GoogleAuthenticator`: OAuth2-Login, Token-Refresh, API-Clients |
| `gmail_fetcher.py` | `GmailFetcher`: holt gelabelte Mails per API |
| `gmail_mailer.py` | `GmailMailer`: verschickt die Wochenmail per API |
| `calendar_sync.py` | `GoogleCalendarSync`: schreibt Termine in den Google Kalender |
| `ics_export.py` | `IcsExporter`: lokale `.ics`-Backup-Datei |
| `inbox_processor.py` | `InboxProcessor`: orchestriert obige Klassen für einen Verarbeitungslauf |
| `summary.py` | `WeeklySummaryBuilder`: baut den Text der Wochenmail |
| `scheduler.py` | `Scheduler`: zeitgesteuerte Endlosschleife (ersetzt launchd/cron) |
| `app.py` | `Application`: verdrahtet alle Klassen anhand der Config |
| `cli.py` | Kommandozeilenbefehle (`login`, `fetch`, `process`, `weekly`, `scheduler`) |
| `logging_config.py` | Zentrale Logging-Konfiguration (Format, Log-Level) |

Jede Klasse hat genau eine Aufgabe und bekommt ihre Abhängigkeiten im
Konstruktor übergeben (`Application` in `app.py` verdrahtet das) - keine
globalen Funktionen, die sich kreuz und quer gegenseitig aufrufen.

**Kontrollprinzip:** Nur Mails, die du bewusst an die dedizierte Adresse
weiterleitest (oder Dateien, die du manuell in `eingang/` legst), werden je
gesehen. Kein Zugriff auf dein privates Hauptkonto.

**Datenschutz:** PDF-/Mail-Inhalte gehen nie an einen Cloud-KI-Anbieter,
nur an dein lokal laufendes Ollama. Google wird ausschliesslich für das
dedizierte Konto genutzt (E-Mail-Label lesen, Kalender befüllen, Mail
senden) - mit einem auf diese drei Rechte beschränkten, jederzeit
widerrufbaren OAuth2-Token statt einem Passwort.

---

## Teil 1 (nativ, einmalig): Dediziertes Gmail-Konto + OAuth2 einrichten

### 1.1 Neues Gmail-Konto anlegen

Ein separates, kostenloses Konto nur für dieses Projekt (nicht dein
privates) - z.B. `deinname.schultermine@gmail.com`.

### 1.2 Kein zusätzlicher Schritt nötig (Standardfall)

Da das Konto aus 1.1 rein dediziert ist und du ohnehin nur relevante
Schul-Mails dorthin weiterleitest, reicht der normale Posteingang als
Auswahl - `config.yaml` ist bereits standardmässig auf `label_name: "INBOX"`
eingestellt, das liest einfach alles, was in diesem Konto ankommt. Kein
Gmail-Filter, kein Label nötig.

**Nur falls du dasselbe Konto zusätzlich für anderes nutzt** und gezielt
filtern willst, kannst du optional ein eigenes Label + einen Gmail-Filter
einrichten:

1. In Gmail: Einstellungen → **Alle Einstellungen anzeigen** → Tab
   **Filter und blockierte Adressen** → **Neuen Filter erstellen**.
2. Feld "An" (To): die Adresse des Kontos selbst, oder ein passendes Kriterium.
3. **Label anwenden** → **Neues Label erstellen** → Name z.B. `Schule-KI`.
4. Filter erstellen.
5. In `config.yaml`: `label_name: "Schule-KI"` statt `"INBOX"` eintragen.

### 1.3 Google-Cloud-Projekt + OAuth2-Zugangsdaten erstellen

1. Gehe zu https://console.cloud.google.com, logge dich mit dem
   **dedizierten** Konto ein, erstelle ein neues Projekt (z.B.
   "school-events-ai").
2. **APIs & Dienste → Bibliothek**: aktiviere **Gmail API** und
   **Google Calendar API**.
3. **APIs & Dienste → OAuth-Zustimmungsbildschirm**:
   - Nutzertyp: **Extern** (für ein privates Testprojekt völlig ausreichend)
   - App-Name, Support-E-Mail, Entwickler-E-Mail ausfüllen
   - Scopes: nicht zwingend hier hinzufügen (das Skript fordert sie selbst an)
   - **Testnutzer**: trage die dedizierte Gmail-Adresse selbst als Testnutzer
     ein - dadurch bleibt die App im "Testing"-Status, was für ein
     Ein-Personen-Projekt reicht (keine Google-Verifizierung nötig).
4. **APIs & Dienste → Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID**:
   - Anwendungstyp: **Desktop-App**
   - Namen vergeben, erstellen
   - JSON herunterladen, als `credentials.json` im Projektordner speichern

**Hinweis zu "Testing"-Status:** Da die App unverifiziert bleibt, zeigt
Google beim ersten Login eine Warnung ("Diese App wurde nicht verifiziert")
- das ist normal für private Projekte, unter "Erweitert" → "Zu
school-events-ai wechseln (unsicher)" bestätigen (bzw. zum Namen, den du in
1.3 für dein Google-Cloud-Projekt gewählt hast). Da du selbst als Testnutzer
eingetragen bist, funktioniert der Zugriff dauerhaft; falls Google-seitige
Token-Ablauf-Richtlinien für unverifizierte Apps sich ändern, reicht ein
erneuter Login (siehe 1.4), um ein neues Token zu holen.

### 1.4 Ersten Login durchführen (einmalig, ausserhalb Docker)

Der OAuth2-Login öffnet einen Browser und braucht dafür einen echten
Desktop - das funktioniert nicht headless in Docker. Deshalb einmalig nativ:

```bash
cd school-events-ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# config.yaml öffnen und send_to (+ ggf. weitere Werte) eintragen

python3 -m school_events login
```

`login` macht ausschliesslich das: öffnet ein Browserfenster → mit dem
dedizierten Konto einloggen → Rechte bestätigen. Kein Mail-Abruf, keine
Verarbeitung - nur der Login, als eigener, klar benannter Befehl (statt als
Nebeneffekt von `fetch`, wie in einer früheren Version dieses Projekts).
Danach liegt ein `token.json` im Projektordner - das enthält den
Refresh-Token und wird von da an automatisch erneuert, auch innerhalb von
Docker (kein erneuter Login mehr nötig, ausser der Zugriff wird
widerrufen).

---

## Teil 2 (Docker): Ollama + Scheduler starten

Voraussetzung: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
installiert, Teil 1 abgeschlossen (`token.json` existiert).

```bash
cd school-events-ai
# config.yaml: ollama.url auf "http://ollama:11434" setzen (Docker-Servicename),
# paths.base_dir auf "/data/SchulTermine" setzen (siehe Kommentare in der Datei)

docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:14b   # einmalig: Modell laden

docker compose logs -f     # laufende Ausgabe mitverfolgen
```

Bei eurer Frequenz von ca. einer Mail alle 2-3 Wochen spielt Geschwindigkeit
keine Rolle - deshalb ein grösseres, genaueres Modell (`qwen2.5:14b`, ca.
9 GB) statt eines kleinen, schnellen, obwohl Ollama hier ohne
Apple-Silicon-GPU-Beschleunigung läuft (Docker Desktop auf macOS hat keinen
GPU-Zugriff, das Modell läuft auf der CPU - bei eurer Nutzung unerheblich,
eine Anfrage dauert dann eben ein bis zwei Minuten statt Sekunden). Falls
dir das doch zu langsam ist, tut es auch `llama3.1:8b` (in `config.yaml`
unter `ollama.model` anpassen und mit
`docker compose exec ollama ollama pull llama3.1:8b` laden).

Das war's. Der `school-events`-Container prüft stündlich das Gmail-Label und
den `eingang/`-Ordner (einstellbar über `scheduler.fetch_interval_minutes`
in `config.yaml`), verarbeitet Neues über den `ollama`-Container,
aktualisiert den Google Kalender, und schickt sonntags 18:30 Uhr die
Wochenzusammenfassung. Alle Daten liegen weiterhin unter `~/SchulTermine/`
auf deinem Mac (per Volume eingebunden), unabhängig vom Container. Die
Modellgewichte liegen in einem Docker-Volume (`ollama_data`) und überleben
Neustarts/Rebuilds.

Stoppen:
```bash
docker compose down
```

**Später in die Cloud umziehen:** Denselben Ordner (`school-events-ai/`
inkl. `config.yaml`, `credentials.json`, `token.json`) auf einen
Linux-Server kopieren, `docker compose up -d` - fertig, ohne jede Anpassung
(Ollama läuft dort identisch containerisiert mit).

### Alternative: nativ ohne Docker

Falls du (noch) kein Docker willst: Ollama separat nativ installieren
(`brew install ollama && brew services start ollama && ollama pull
qwen2.5:14b`), `ollama.url` in `config.yaml` auf `http://localhost:11434`
setzen, dann läuft derselbe Scheduler auch direkt in der venv:

```bash
source venv/bin/activate
python3 -m school_events scheduler
```

Läuft im Vordergrund - eher zum Testen gedacht, da es beim Schliessen des
Terminals stoppt (im Gegensatz zu `restart: unless-stopped` in Docker).

---

## Manuelles Testen einzelner Schritte

```bash
source venv/bin/activate
python3 -m school_events login      # nur Login/Token erneuern, sonst nichts
python3 -m school_events fetch      # holt neue Mails ab (Standard: gesamter Posteingang)
python3 -m school_events process    # verarbeitet alles in eingang/, aktualisiert den Kalender
python3 -m school_events weekly     # verschickt die Wochenübersicht sofort
```

**Detaillierte Logs für die Fehlersuche:** Jeder Befehl akzeptiert
`--log-level DEBUG` - zeigt dann u.a. genau, was an Ollama geschickt wird,
wie lange die Antwort dauert, und den rohen Antworttext, falls das
JSON-Parsing mal fehlschlägt:

```bash
docker compose exec school-events python3 -m school_events process --log-level DEBUG
```

(In Docker läuft der Scheduler standardmässig mit `--log-level INFO` -
sichtbar in `docker compose logs -f school-events`.)

**Zur Sprache im Code:** Kommentare, Docstrings und Log-Meldungen im
`school_events/`-Package sind auf Englisch. Ausnahme sind Texte, die direkt
bei dir landen - Kalendereinträge, die Wochenmail, der Extraktions-Prompt
ans LLM - die bleiben bewusst Deutsch, da es sich um Inhalte für dich
(bzw. deine Familie) handelt, nicht um Code.

## Proton Calendar mit dem Google Kalender verbinden (einmalig)

1. Im dedizierten Google-Konto: Google Kalender öffnen → links bei
   "Meine Kalender" den Kalender **Schultermine** suchen (wird beim ersten
   Lauf automatisch angelegt) → Drei-Punkte-Menü → **Einstellungen und
   Freigabe**.
2. Ganz unten: **Kalender integrieren** → **Geheime Adresse im
   iCal-Format** kopieren.
3. In Proton Calendar: **Kalender hinzufügen** → **Von URL abonnieren** →
   die kopierte Adresse einfügen.

Proton ruft diese Adresse fortan selbstständig in regelmässigen Abständen
ab (Intervall wird von Proton vorgegeben, i.d.R. mehrmals täglich) - kein
manueller Import mehr nötig. Die URL ist ein langer, nicht erratbarer
Zufallswert - nicht öffentlich auffindbar, aber technisch von aussen
abrufbar (das ist bei "Kalender abonnieren" bei jedem Anbieter so).

## Wo landen die Daten

Alles unter `~/SchulTermine/`:
- `eingang/` - hier landen neue PDFs/Mails (automatisch oder manuell), leert
  sich nach Verarbeitung
- `originals/` - archivierte Originaldateien
- `data/events.json` - alle erkannten Termine, strukturiert
- `data/processed_hashes.json`, `data/gmail_fetched_ids.json` - Dedup-Status
- `calendar/school-events.ics` - lokale Backup-Kopie (zusätzlich zum Google
  Kalender, falls du sie einmal offline brauchst; hiess vor dem Projekt-Rename
  `schultermine.ics` - eine allfällige alte Datei mit diesem Namen kannst du
  löschen)

## Grenzen dieser Lösung

- Gescannte PDFs (reine Bilder ohne Text) können aktuell nicht gelesen
  werden. Bei Bedarf lässt sich OCR (z.B. `ocrmypdf`) ergänzen.
- Die Qualität der Extraktion hängt vom Modell ab. `qwen2.5:14b` ist bei
  strukturierter Extraktion und Deutsch zuverlässig; bei Bedarf lässt sich
  jederzeit ein anderes Ollama-Modell eintragen.
- Die HTML→Text-Umwandlung für E-Mail-Bodies ist bewusst einfach gehalten;
  bei stark verschachteltem HTML kann das Ergebnis unsauber sein.
- Google-OAuth2-Scope `calendar` ist recht breit (voller Kalenderzugriff im
  dedizierten Konto); lässt sich bei Bedarf auf granularere Scopes
  einschränken, sobald Google diese für Kalendererstellung stabil anbietet.
- Fürs iPhone unterwegs gibt es aktuell keine eigene Lösung - am einfachsten
  ist, Schul-Mails von unterwegs direkt an die dedizierte Gmail-Adresse
  weiterzuleiten (funktioniert in jeder Mail-App).
