# spotlab Anbindung — fremde Projekte, Panels und ein MCP-Server

**Datum:** 2026-08-07
**Status:** Entwurf zur Freigabe
**Umfang:** Stufe 6. Setzt Fundament (1+2), GUI (3), GraphNav (4) und Editor (5) voraus.
Der Sim-Adapter (`spotlab[sim]`) kommt danach und ist hier ausdrücklich nicht enthalten.

---

## 1 Zweck

spotlab kann bisher nur mit sich selbst reden. Projekte sind Ordner in der Werkstatt, Läufe
gehören zu Skripten daraus, und wer von aussen etwas zeigen oder auslesen will, hat keinen Weg.

Diese Stufe öffnet drei Türen für **fremde Projekte** — Projekte mit eigenem Repo, eigenem
Zweck und eigener Abhängigkeitslage:

1. **Andocken.** Ein Projekt beschreibt sich in einer `spotlab.toml` und wird bei spotlab
   registriert.
2. **Zeigen.** Es schreibt **Panels** — Kennzahlen, Tabellen, Reihen, Bilder, Text —, die in
   einer eigenen Ansicht erscheinen.
3. **Auslesen.** Ein **MCP-Server** gibt einem Agenten Zugriff auf Läufe, Karten und
   Zustandsreihen — und darf registrierte Skripte starten, **erzwungen ohne Roboter**.

Erster Kunde ist das Maturaarbeits-Repo `matura-spot`
(`D:\Users\janis\Documents\Matura\matura-spot`): MuJoCo-Simulation des Spot mit
Explorationsschicht. Sein Zweck an spotlab ist zweiseitig — Ergebnisse zeigen, und echte
Messreihen vom Schul-Spot herausziehen, um die Simulation daran zu eichen (AF 4 der Arbeit).

### Vorgefundener Stand

`matura-spot` schreibt je Experiment nach `notes/experimente/<lauf_id>/`:

- `ergebnisse.json` — Umgebung (git-Commit, Versionen), Konfiguration, Kennzahlen mit
  95-%-Konfidenzintervallen (`success_ci95`, `collision_rate_ci95`, …)
- `ergebnisse.md` — dieselben Zahlen als Tabelle plus Deutung
- dazu unter `out/` mp4-Videos und png-Einzelbilder

Seine Skripte laufen über `argparse` (`scripts/experiment_baseline.py --episoden 20
--archiv`). Ein Baseline-Lauf dauert rund elf Minuten über zwanzig Episoden.

**Das ist alles Datenlage, keine Oberfläche** — und der Grund, warum deklarative Panels für
den ersten Kunden vollständig ausreichen.

In spotlab vorhanden und wiederverwendet: `record/read.py` (`RunSummary`, `read_run`,
`list_runs`), `maps/store.py` (`MapInfo`, `karten`, `finde`, `lade_graph`),
`workshop/launcher.py` (`start_script`), `workshop/control.py` (`stoppe_freundlich`,
`ist_aktiv`), `workshop/doctor.py` (`diagnose`), `gui/watcher.py` (`RunWatcher`).

`mcp` ist **nicht** installiert; `tomllib` ist ab Python 3.11 in der Standardbibliothek.

---

## 2 Entschiedene Grundsatzfragen

| # | Frage | Entscheidung | Begründung |
|---|---|---|---|
| B1 | Was ein fremdes Projekt beisteuern darf | **Daten, kein Code.** Deklarative Panels, gezeichnet mit spotlabs eigenen Widgets. | Der GUI-Prozess ist der Prozess mit dem **NOT-AUS-Knopf**. Fremder Qt-Code liefe in demselben Event-Loop; eine Schleife, ein blockierender Ladevorgang oder ein Absturz im Plugin, und der Not-Aus reagiert nicht mehr. Ein Plugin-System dort macht genau die eine Sache kaputt, die nicht kaputtgehen darf. Dazu: der erste Kunde braucht es nicht, und was deklarativ ist, kann ein Agent erzeugen und prüfen, ohne Qt zu können. |
| B2 | Ob der Agent Skripte starten darf | **Ja — aber erzwungen im Trockenlauf.** | Nur anbieten macht den Agenten zum Formularausfüller und schneidet die Schleife ab, die den Nutzen ausmacht: starten, Ergebnis lesen, nachbessern. Ein Bestätigungsdialog wäre trügerisch — was zwanzigmal am Tag kommt, wird weggeklickt und ist dann keine Sicherung mehr, sondern die Illusion einer. |
| B3 | Wie Daten ins Fenster kommen | **Über Dateien in einem Anbindungsordner**, nicht über einen Dienst oder Socket. | spotlab arbeitet schon so: die GUI liest Live-Daten aus dem Lauf-Verzeichnis, nie aus einer Verbindung — deshalb erscheinen auch F5-Läufe aus VS Code. Panels überleben damit den Agenten und die GUI. **Und das Projekt kann direkt schreiben:** ein elfminütiger Experimentlauf zeigt seinen Fortschritt selbst, statt darauf zu warten, dass ein Agent nachfragt. Der MCP-Server wird damit die Tür für den Agenten auf dieselben Daten — nicht ihr Besitzer. |
| B4 | Was „kalibrieren" heisst | **Andocken ist der Weg, die Daten sind der Zweck.** Schreib- **und** Lese-Werkzeuge. | Das Herausziehen echter Zustandsreihen kostet nichts Neues — `record/read.py` liest das Format bereits. Damit lässt sich zum ersten Mal eine Messreihe vom Schul-Spot mit einem Simulationslauf vergleichen, ohne Dateien von Hand zu kopieren. |
| B5 | Wo das Manifest liegt | **`spotlab.toml` im fremden Repo**, hineinkopiert in den Anbindungsordner. | Es gehört zum Projekt: es liegt in dessen git, reist mit, und wer das Repo klont, bekommt die Anbindung mit. Die Kopie macht die GUI unabhängig vom fremden Repo — ist der Ordner weg, bleiben die Panels sichtbar und nur die Skript-Knöpfe gehen aus. |
| B6 | Protokoll selbst bauen oder SDK | **Offizielles `mcp`-Paket als Extra `[mcp]`.** | Selbst gebaut wären es rund 150 Zeilen JSON-RPC über stdin — machbar, aber dann besässen wir die Korrektheit einer fremden, sich bewegenden Spezifikation. Das Extra trifft den Forschungsplatz, nicht die zwanzig Schullaptops. |
| B7 | Umfang der Lese-Werkzeuge | **Struktur und Pfade, keine Massendaten.** | `zustand.jsonl` läuft mit 10 Hz: fünf Minuten sind 3000 Zeilen. Ein Werkzeug, das die zurückgibt, füllt den Kontext des Agenten mit einem Aufruf — und hätte `Read` nachgebaut, schlechter als das Original. Der Agent hat eigene Dateiwerkzeuge und kann damit filtern. |

---

## 3 Architektur

```
gui/views/anbindungen.py                    Ansicht „Anbindungen" (siebter Eintrag)
   │
mcp/   server.py · werkzeuge.py             stdio-Server, Extra [mcp]
   │
anbindung/   manifest.py · speicher.py · panel.py       Qt-frei, SDK-frei
```

`anbindung/` importiert **nichts** aus `api/`, `backends/`, `maps/` oder `gui/` und hält
**keinen Lease-Client und keinen E-Stop-Endpunkt** — dieselbe Bedingung, unter der `maps/`
von der GUI benutzt werden darf. `spotlab.errors` darf es benutzen: `SpotlabError` ist der
Fehlertyp des Hauses, den CLI und GUI bereits abfangen.

> **Korrektur gegenüber dem ersten Entwurf dieser Spec.** Dort stand, `anbindung/` dürfe nur
> die Standardbibliothek benutzen, damit die GUI Panels ohne `bosdyn` lesen könne. Das trägt
> nicht: `spotlab.errors` importiert über `translate.py` und `graphnav.py` selbst `bosdyn`,
> und `gui/views/projects.py` importiert `spotlab.errors` seit Stufe 3. Der SDK ist im
> GUI-Prozess ohnehin geladen, und `bosdyn-client` ist eine unbedingte Abhängigkeit des
> Kerns. Der bestehende Test `test_gui_importiert_kein_bosdyn` prüft Quelltext auf **direkte**
> Importe — er sichert die Lease-Regel, nicht Abwesenheit des SDK aus dem Prozess. Die
> tragfähige Regel ist die von `maps/`, und die steht oben.

`mcp/werkzeuge.py` ist die Schicht, die `anbindung/` mit `record/`, `maps/` und `workshop/`
verbindet. **Die Werkzeuge sind gewöhnliche Funktionen**; `mcp/server.py` meldet sie nur beim
Protokoll an. Damit sind sie ohne Server und ohne Agent prüfbar.

### Wo die Läufe eines fremden Projekts landen — und warum das ein Fallstrick ist

`start_script` startet mit `cwd=<skriptordner>`, und `connect()` legt Läufe unter
`<skriptordner>/runs/` an. Für ein fremdes Projekt heisst das:
`matura-spot/scripts/runs/<lauf-id>/`.

Der `RunWatcher` der GUI durchsucht heute `<arbeitsordner>/*/runs/*`. **Ein Lauf eines
fremden Projekts liegt ausserhalb des Arbeitsordners und würde nie gefunden** — „Live-Lauf"
bliebe leer, obwohl der Lauf läuft.

Das ist derselbe Fehler wie in Stufe 3, wo der Watcher den Arbeitsordner statt der
Lauf-Verzeichnisse durchsuchte und die Live-Ansicht in der Klasse leer geblieben wäre.

**Gegenmassnahme, präzise statt breit:** Das Manifest nennt jede Skriptdatei, also ist ihr
Lauf-Verzeichnis bekannt — `Path(datei).parent / "runs"`. `gui/watcher.py::lauf_verzeichnisse`
nimmt zusätzlich zu `<arbeitsordner>/*/runs/*` die aus den Anbindungen abgeleiteten
Verzeichnisse auf. Kein rekursives Absuchen fremder Repos, nur die Ordner, die im Manifest
stehen. Dasselbe Ableiten benutzt `laeufe_auflisten` im MCP-Server.

**Die Suche liegt an genau einer Stelle**, in einem Qt-freien `laufsuche.py`. `gui/watcher.py`
ist zwar Qt-frei geschrieben, importiert aber PySide6 — der MCP-Server könnte die Funktion
dort nicht benutzen, ohne Qt hereinzuziehen, und stünde dann vor der Wahl, sie nachzubauen.
Zwei Suchen mit verschiedenen Ergebnissen wären der alte Fehler in neuem Gewand.

**Ein Regressionstest hält das fest**, weil hier zum zweiten Mal dieselbe Klasse Fehler droht.

### Keine neue Fähigkeit

Es kommt kein Eintrag in `Capability` und kein `require()`: das Andocken ist keine
Roboterfähigkeit.

---

## 4 Komponenten

### 4.1 `anbindung/manifest.py` — die Projektbeschreibung

```python
@dataclass(frozen=True)
class Skript:
    name: str
    datei: Path             # absolut, aufgelöst gegen das Projektverzeichnis
    argumente: tuple[str, ...]
    roboter: bool           # fährt dieses Skript den echten Spot?
    beschreibung: str

@dataclass(frozen=True)
class Manifest:
    name: str
    beschreibung: str
    projekt: Path           # Verzeichnis, in dem spotlab.toml liegt
    skripte: tuple[Skript, ...]

DATEINAME = "spotlab.toml"

def lies(projektpfad: Path) -> Manifest       # wirft ManifestFehler
def als_json(manifest: Manifest) -> dict
def aus_json(daten: dict) -> Manifest
```

Format:

```toml
[projekt]
name = "matura-spot"
beschreibung = "MuJoCo-Simulation des Spot für die Maturaarbeit"

[[skript]]
name = "Baseline, 20 Episoden"
datei = "scripts/experiment_baseline.py"
argumente = ["--episoden", "20", "--archiv"]
roboter = false
beschreibung = "Frontier-Exploration, schreibt ergebnisse.json"
```

Gelesen mit `tomllib` aus der Standardbibliothek. `name` und `datei` sind Pflicht;
`argumente` ist leer, `roboter` ist `false`, `beschreibung` ist `""`, wenn sie fehlen.

**`roboter` hat keinen Standardwert `true`.** Das wäre die vorsichtigere Voreinstellung und
wäre trotzdem falsch: sie machte den häufigen Fall — ein Skript ohne Roboterbezug — zur
Ausnahme, und Leute schrieben dann überall `roboter = false` hin, ohne nachzudenken. Die
Sicherheit hängt an der Schranke in 4.7, nicht an diesem Feld.

`ManifestFehler` nennt **Datei und Feld**: „In `…/spotlab.toml` fehlt bei Skript 2 das Feld
`datei`."

### 4.2 `anbindung/speicher.py` — der Anbindungsordner

```
<arbeitsordner>/anbindungen/<name>/
    anbindung.json          Manifest-Kopie, Quellpfad, Zeitpunkt
    panels/<name>.json
```

```python
@dataclass(frozen=True)
class Anbindung:
    name: str
    ordner: Path
    manifest: Manifest
    quelle: Path            # wo spotlab.toml lag
    angebunden: str         # ISO-Zeitstempel
    vorhanden: bool         # existiert die Quelle noch?

def wurzel(workspace: Path) -> Path
def binde_an(workspace: Path, projektpfad: Path) -> Anbindung
def anbindungen(workspace: Path) -> list[Anbindung]
def finde(workspace: Path, name: str) -> Anbindung
def loese(workspace: Path, name: str) -> None
def lauf_verzeichnisse_von(anbindung: Anbindung) -> list[Path]
```

Der Ordnername entsteht über `sicherer_name` — dieselbe Regel wie bei Karten
(`re.sub(r"[^\w.-]+", "-", …)`), damit ein Projektname mit Schrägstrich keinen Ordner
ausserhalb anlegt.

**Die Funktion zieht dafür nach `spotlab/pfade.py` um**, und `maps/store.py` importiert sie
von dort. Sie aus `maps/store.py` zu importieren hiesse, die Anbindung an die
GraphNav-Ablage zu koppeln — für eine fünfzeilige Regex, die mit Karten nichts zu tun hat.
Sie zu kopieren hiesse, zwei Umsetzungen zu haben, die auseinanderlaufen können. Ein
gemeinsamer Ort löst beides; `maps/store.py` behält den Namen als Re-Export, damit
bestehende Importe und Tests unverändert laufen.

`binde_an` ist **idempotent**: erneutes Anbinden erneuert `anbindung.json` und lässt die
Panels stehen. Ein Agent, der nach jeder Manifeständerung neu anbindet, verliert nichts.

`vorhanden` wird beim Lesen geprüft, nicht gespeichert.

### 4.3 `anbindung/panel.py` — die fünf Arten

```python
ARTEN = ("kennzahlen", "tabelle", "reihe", "bild", "text")

@dataclass(frozen=True)
class Panel:
    name: str               # Dateiname ohne .json
    titel: str
    art: str
    stand: str              # ISO-Zeitstempel
    inhalt: object          # je nach Art, siehe unten
    fehler: str | None      # gesetzt, wenn die Datei unbrauchbar war

def schreibe(anbindung, name, art, titel, inhalt, jetzt=None) -> Path
def lies(pfad: Path) -> Panel           # wirft nie
def panels(anbindung) -> list[Panel]
def entferne(anbindung, name) -> bool
def bild_erlaubt(pfad: Path, anbindung: Anbindung) -> bool
```

| Art | `inhalt` | Gezeichnet als |
|---|---|---|
| `kennzahlen` | `[{"name", "wert", "hinweis"}]` | Kacheln wie in „Live-Lauf" |
| `tabelle` | `{"spalten": [...], "zeilen": [[...]]}` | `QTableWidget` wie in „Läufe" |
| `reihe` | `{"x": [...], "y": [...], "x_name", "y_name"}` | `QPainter`-Kurve wie `gui/mapplot.py` |
| `bild` | `{"pfad": "..."}` | Bild, eingepasst |
| `text` | `{"absaetze": [...]}` | Fliesstext |

**`lies` wirft nie.** Bei kaputtem JSON, unbekannter Art oder fehlenden Feldern kommt ein
`Panel` mit gesetztem `fehler` zurück, und die Ansicht zeichnet dafür eine Fehlerkarte. Der
Grund ist nicht Bequemlichkeit: ein Panel, das im Sekundentakt überschrieben wird, ist
regelmässig für Millisekunden halb geschrieben. Eine Ansicht, die daran leer wird, flackert
im Betrieb — und ein Projekt, das *ein* kaputtes Panel schreibt, darf nicht die Anzeige der
anderen vier löschen.

**Geschrieben wird atomar**: erst in `<name>.json.neu`, dann `os.replace`. Damit sieht ein
Leser nie eine halbe Datei. Das schwächt die vorige Regel nicht ab — sie fängt fremde
Schreiber ab, die das nicht tun.

**Farben stehen nicht im Panel.** Ein Panel wählt keine Farbe; sonst gibt es einen
Hell/Dunkel-Modus, in dem fremde Daten unlesbar sind. Die Regel „Farben nur aus `theme.py`"
gilt unverändert.

**`bild_erlaubt`** lässt nur Pfade **unterhalb des Projektverzeichnisses oder des
Anbindungsordners** zu (`Path.resolve().is_relative_to`). Dieselbe Regel und derselbe Grund
wie bei den anklickbaren Tracebacks in Stufe 5: eine Datei, die sagt „zeig das hier", darf
nicht auf Beliebiges im Dateisystem deuten.

### 4.4 `mcp/werkzeuge.py` — zwölf gewöhnliche Funktionen

```python
# Anbinden
def projekt_anbinden(pfad: str) -> dict
def anbindungen_auflisten() -> list[dict]
def panel_setzen(projekt: str, name: str, art: str, titel: str, inhalt: object) -> dict
def panel_entfernen(projekt: str, name: str) -> dict

# Ausführen
def skript_starten(projekt: str, name: str) -> dict      # Trockenlauf erzwungen
def lauf_stoppen(lauf_id: str) -> dict

# Lesen
def laeufe_auflisten(projekt: str | None = None, anzahl: int = 20) -> list[dict]
def lauf_lesen(lauf_id: str) -> dict
def zustand_zusammenfassen(lauf_id: str) -> dict
def karten_auflisten() -> list[dict]
def karte_lesen(name: str) -> dict
def spot_pruefen() -> list[dict]
```

Jede Funktion nimmt und liefert nur JSON-fähige Werte und findet den Arbeitsordner über
`load_config()`. Fehlt die Konfiguration, ist die Antwort ein `{"fehler": "…"}` mit dem
Hinweis auf `spotlab login` — kein Absturz im Protokoll.

**Eine Lauf-Kennung wird überall gleich aufgelöst.** Läufe liegen an zwei Orten — unter
`<arbeitsordner>/<projekt>/runs/` und unter `<skriptordner>/runs/` eines angebundenen
Projekts. `laeufe_auflisten`, `lauf_lesen`, `zustand_zusammenfassen` und `lauf_stoppen`
benutzen dafür **dieselbe Auflösung** wie der Watcher aus Abschnitt 3. Zwei Suchen mit
verschiedenen Ergebnissen wären genau der Fehler, den Stufe 3 schon einmal hatte.

**`lauf_lesen` liefert Struktur und Pfade**, nicht Inhalte: Kennung, Ergebnis, Dauer,
Backend, Skript, Ereigniszahl, Abtastungszahl — und die absoluten Pfade auf `zustand.jsonl`,
`ereignisse.jsonl` und `bilder/`. Wer die Reihe wirklich braucht, liest sie mit den eigenen
Dateiwerkzeugen.

**`zustand_zusammenfassen` ist die begründete Ausnahme.** Es beantwortet genau das, wofür man
sonst die ganze Datei laden müsste, und liefert:

- Dauer, Anzahl Abtastungen, tatsächliche mittlere Abtastrate
- gefahrene Strecke, Spitzentempo, Spitzen-Drehrate
- Akku am Anfang und am Ende
- **Abtastlücken**: jede Pause über 0.2 s — dem Doppelten des Solltakts von 10 Hz aus
  `record/sampler.py` — mit Zeitpunkt und Länge

Der letzte Punkt ist der eigentliche Zweck. Für die Real→Sim-Eichung macht eine unbemerkte
Lücke in der Messreihe den Vergleich still ungültig; sie muss vor der ersten Zahl sichtbar
sein, nicht nach der letzten.

**`skript_starten`** schlägt den Weg über `workshop/launcher.py::start_script`, ergänzt um die
Argumente aus dem Manifest und die Schranke aus 4.7. Es kehrt sofort zurück und liefert die
Lauf-Kennung; der Agent verfolgt den Lauf über `lauf_lesen`. Bei `roboter = true` startet es
gar nicht erst und antwortet: „Dieses Skript fährt den echten Spot. Starte es selbst im
Fenster unter ‚Anbindungen'."

**Der Server schreibt nie in das fremde Projekt.** Er liest dessen Manifest und schreibt
ausschliesslich unterhalb von `anbindungen/`.

### 4.5 `mcp/server.py` — der stdio-Server

Gestartet als `spotlab mcp`; ein neuer Unterbefehl in `cli.py`. Er meldet die zwölf Funktionen
aus 4.4 beim `mcp`-Paket an, mit deutschen Beschreibungen und JSON-Schemata, und läuft über
stdin/stdout.

Fehlt das Extra, sagt `spotlab mcp` das mit dem Installationsbefehl statt mit einem
`ImportError`.

Er braucht **weder GUI noch Roboter** — nur den Arbeitsordner.

### 4.6 `gui/views/anbindungen.py` — die Ansicht

Siebter Eintrag der Seitenleiste, vor „Spot" (das ist Einrichtung und bleibt letztes).
Reihenfolge: Projekte · Code · Live-Lauf · Läufe · Karten · Anbindungen · Spot.

Links die Liste der angebundenen Projekte, rechts oben die Skript-Knöpfe, darunter die Panels
in einem Rollbereich.

Der Leitsatz führt sich fort: „Code" zeigt, was das Programm sagt; „Live-Lauf", was der
Roboter tut; **„Anbindungen", was ein fremdes Projekt zu sagen hat.**

Die Ansicht beobachtet `anbindungen/*/panels/*.json` mit einem `QFileSystemWatcher` und
zeichnet betroffene Panels neu. Ein Knopf „Projekt anbinden…" öffnet einen Ordnerdialog —
Andocken darf man auch ohne Agent.

Skript-Knöpfe der GUI kennen **keine Trockenlauf-Schranke**: dort sitzt ein Mensch vor dem
NOT-AUS, und ein Häkchen „Trockenlauf" wie in „Projekte" reicht. Die Schranke gilt für den
Agenten, nicht für den Menschen.

Ist `vorhanden` falsch, sind die Skript-Knöpfe abgeschaltet und ein Hinweis nennt den alten
Pfad. Die Panels bleiben sichtbar.

### 4.7 Die Trockenlauf-Schranke

Zwei Lagen, weil sie verschiedene Fehler abfangen.

**Erste Lage — das Manifest.** `skript_starten` weigert sich bei `roboter = true`, bevor
etwas läuft, mit einer Meldung, die sagt was zu tun ist. Sie gibt die gute Erklärung.

**Zweite Lage — die Umgebung.** Der Start setzt `SPOTLAB_NUR_TROCKEN=1`, und `connect()`
liest das als **Verbot**:

```python
ENV_NUR_TROCKEN = "SPOTLAB_NUR_TROCKEN"
...
art = backend or os.environ.get(ENV_BACKEND) or (cfg.default_backend if cfg else "dryrun")
if os.environ.get(ENV_NUR_TROCKEN) == "1" and art != "dryrun":
    raise SpotlabError(
        "Dieser Lauf wurde ohne Roboter gestartet und darf keinen anfordern. "
        "Starte das Programm im Fenster unter „Anbindungen“, wenn der Spot fahren soll."
    )
```

**Warum beide Lagen nötig sind:** `SPOTLAB_BACKEND` allein genügt nicht. Heute gilt
`art = backend or os.environ.get(ENV_BACKEND) or …` — ein Skript mit
`spotlab.connect(backend="real")` **überschreibt die Umgebungsvariable** und käme an den
Roboter. Die bestehende Variable ist eine Vorgabe, keine Schranke. Und das Manifest ist eine
Behauptung: **ein veraltetes oder falsches `roboter = false` darf den Roboter nicht bewegen
können.**

**Abgewiesen, nicht stillschweigend heruntergestuft.** Ein Skript, das glaubt, es fahre den
echten Spot, während es im Trockenlauf steckt, meldet Unsinn, und niemand merkt es.

Die Schranke ist danach für alles nützlich, was ohne Aufsicht läuft.

### 4.8 `workshop/launcher.py` — Argumente

`start_script(pfad, dryrun=False, argumente=(), nur_trocken=False, starter=subprocess.Popen)`.

Die Argumente werden **als Liste** an `Popen` gereicht, nie über eine Shell zusammengesetzt.
`nur_trocken=True` setzt zusätzlich `SPOTLAB_NUR_TROCKEN=1`.

Ohne Argumente wären die Skripte des ersten Kunden unbrauchbar: dort läuft alles über
`argparse`.

---

## 5 Datenfluss

**Andocken:**

```
Agent → projekt_anbinden("D:/…/matura-spot")
          → manifest.lies()  (tomllib)
          → speicher.binde_an()  legt anbindungen/matura-spot/ an
          → GUI sieht den Ordner, zeigt das Projekt
```

**Zeigen — zwei gleichwertige Wege auf dieselbe Datei:**

```
Agent  → panel_setzen(...) ─┐
                             ├→ anbindungen/<projekt>/panels/<name>.json → GUI
Skript → panel.schreibe(...)┘
```

**Starten und Auslesen:**

```
Agent → skript_starten("matura-spot", "Baseline, 20 Episoden")
          → start_script(datei, argumente=[...], nur_trocken=True)
          → connect() im Kindprozess legt <skriptordner>/runs/<id>/ an
          → RunWatcher findet es (Verzeichnis aus dem Manifest abgeleitet)
          → „Live-Lauf" füllt sich wie bei jedem anderen Lauf
Agent → lauf_lesen(id) → Ergebnis und Pfade
Agent → (eigene Dateiwerkzeuge) → zustand.jsonl im Detail
```

---

## 6 Fehlerbehandlung

| Lage | Verhalten |
|---|---|
| `spotlab.toml` fehlt | „In `<pfad>` liegt keine `spotlab.toml`." |
| `spotlab.toml` unvollständig | Meldung nennt Datei, Skriptnummer und fehlendes Feld |
| Projektordner verschwunden | Panels bleiben, Skript-Knöpfe aus, Hinweis nennt den alten Pfad |
| Panel-JSON kaputt oder halb geschrieben | **Nur dieses** Panel zeigt eine Fehlerkarte |
| Unbekannte Panel-Art | Fehlerkarte, die die fünf bekannten Arten nennt |
| Bildpfad zeigt aus dem Projekt heraus | Nicht geladen, ehrlicher Hinweis statt leerem Rahmen |
| Skriptdatei existiert nicht mehr | Meldung mit Pfad; der Knopf bleibt sichtbar |
| Skript mit `roboter = true` über MCP | Start verweigert, Meldung nennt den Weg über das Fenster |
| Skript umgeht das Manifest und fordert `real` | `connect()` wirft (4.7) |
| Keine Konfiguration | `{"fehler": "…", "hinweis": "spotlab login"}`, kein Absturz |
| `mcp` nicht installiert | `spotlab mcp` nennt den Installationsbefehl |

---

## 7 Prüfung

**Qt-frei, ohne Server** — `anbindung/`:
Manifest lesen samt fehlender Felder und Standardwerte; Pfade werden gegen das
Projektverzeichnis aufgelöst; `binde_an` ist idempotent und lässt Panels stehen;
`sicherer_name` verhindert Ausbruch aus `anbindungen/` (der bestehende Test in
`test_maps_store.py` läuft über den Re-Export weiter); Panel schreiben und lesen im Kreis;
**kaputtes JSON ergibt ein Panel mit `fehler` statt einer Ausnahme**; unbekannte Art ebenso;
`bild_erlaubt` lässt einen Pfad aus dem Projekt zu und einen daneben nicht; atomares
Schreiben hinterlässt keine `.neu`-Datei.

Dazu ein Schichttest wie in Stufe 5, aber auf die **richtige** Regel gerichtet: kein
Quelltext unter `anbindung/` enthält `import bosdyn`, `spotlab.backends`, `spotlab.api`,
`spotlab.maps` oder `spotlab.gui`.

**MCP-Werkzeuge als Funktionen**, gegen einen Arbeitsordner in `tmp_path`: jedes Werkzeug
liefert JSON-fähige Werte; `lauf_lesen` gibt Pfade und **keine Dateiinhalte**;
`zustand_zusammenfassen` findet eine künstlich eingebaute Abtastlücke; `skript_starten`
verweigert bei `roboter = true`.

**Zwei Tests mit echten Prozessen** — die Regel, an der „In VS Code öffnen" durch die ganze
Suite gerutscht ist:

1. **Die Schranke.** Ein Skript mit `spotlab.connect(backend="real")` wird mit gesetztem
   `SPOTLAB_NUR_TROCKEN=1` gestartet und **muss scheitern**, mit der deutschen Meldung im
   Text. Hier hängt mehr daran als eine Fehlermeldung.
2. **Der Server.** `spotlab mcp` wird als Unterprozess gestartet, macht den
   `initialize`-Handshake und listet seine Werkzeuge. Übersprungen mit `skipif`, wenn `mcp`
   fehlt.

**Ein Regressionstest für den Watcher:** ein Lauf in einem Projektordner **ausserhalb** des
Arbeitsordners wird gefunden, weil das Manifest ihn nennt. Ohne ihn bliebe „Live-Lauf" bei
fremden Projekten leer — derselbe Fehler wie in Stufe 3.

**GUI offscreen:** alle fünf Arten zeichnen; ein kaputtes Panel neben vier heilen lässt die
vier stehen; bei fehlender Quelle sind die Skript-Knöpfe aus und die Panels da.

---

## 8 Abnahme am Gerät

**Kein neuer Punkt.** Dass ein Agent den Roboter nicht bewegen kann, ist vollständig in
Software beweisbar — der Unterprozess-Test aus Abschnitt 7 deckt den ganzen Weg von
`skript_starten` bis `connect()` ab. Einen Punkt in `ABNAHME.md` aufzunehmen, den ein Test
schon beweist, würde die Liste entwerten: sie ist die Liste dessen, was **kein** Test zeigen
kann.

---

## 9 Nicht-Ziele

- **MCP über Netz und Mehrbenutzerbetrieb.** stdio, lokal, ein Laptop — wie der Rest von spotlab.
- **Der Agent am echten Spot.** Siehe B2 und 4.7.
- **Beliebiger Qt-Code aus fremden Projekten.** Siehe B1; das ist der Prozess mit dem NOT-AUS.
- **Eine Diagrammbibliothek.** Fünf Arten. Wer mehr braucht, schreibt ein Bild.
- **Schreibzugriff ins fremde Projekt.** Was dort zu ändern ist, ändert der Agent mit seinen
  eigenen Werkzeugen, wo git es sieht.
- **Der Sim-Adapter `spotlab[sim]`.** Kommt danach, als eigene Stufe.
- **Änderungen an `matura-spot`.** Eine `spotlab.toml` und ein paar Zeilen zum Panelschreiben
  gehören in dessen Repo, nicht hierher.

---

## 10 Annahmen

1. **Der Agent hat eigene Dateiwerkzeuge.** Darauf beruht B7. Trifft das für einen Klienten
   nicht zu, fehlt ihm der Zugriff auf rohe Zustandsreihen — die Zusammenfassung bleibt.
2. **`matura-spot` läuft in derselben Python-Umgebung wie spotlab**, sonst findet
   `start_script` seine Abhängigkeiten nicht. `_umgebung()` reicht `sys.path` des
   Elternprozesses weiter; bei getrennten Umgebungen bräuchte das Manifest später ein Feld
   `interpreter`. **Bewusst nicht jetzt gebaut** — beide Repos laufen heute auf demselben
   Python 3.13.9.
3. **Das `mcp`-Paket bietet eine stabile Registrierung für Funktionen mit JSON-Schema.**
   Trifft das nicht zu, bleibt der Weg über einen selbst gebauten stdio-Server offen; die
   Werkzeuge aus 4.4 sind davon unberührt, weil sie gewöhnliche Funktionen sind.

---

## 11 Abhängigkeiten

| Paket | Wo | Pflicht |
|---|---|---|
| `mcp>=1.2` | neues Extra `[mcp]` | nur für `spotlab mcp` |

`tomllib` ist ab Python 3.11 in der Standardbibliothek; die Untergrenze des Projekts ist
3.11. Der Kern und das Extra `[gui]` bekommen **keine** neue Abhängigkeit — `anbindung/`
braucht ausser `spotlab.errors` nichts, was nicht schon da ist.
