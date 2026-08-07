# spotlab GraphNav — Karten aufzeichnen, ansehen, darauf fahren

**Datum:** 2026-08-07
**Status:** Entwurf zur Freigabe
**Umfang:** Stufe 4. Setzt Fundament (Stufe 1+2) und GUI (Stufe 3) voraus.
GraphNav war dort ausdrücklich Nicht-Ziel; diese Spec hebt das auf.

---

## 1 Zweck

Schülerinnen und Schüler sollen einen Raum als **GraphNav-Karte aufzeichnen**, die Karten
**ansehen und auswählen**, und den Spot darauf **autonom von Wegpunkt zu Wegpunkt fahren**
lassen — mit denselben Regeln, die für den Rest von spotlab gelten: deutscher Klartext bei
Fehlern, aufgezeichnete Läufe, sichere Abbrüche, ein Geschwindigkeitsdeckel.

### Vorgefundener Stand

Das Spot-SDK ist lokal geklont (`C:\Users\janis\spot-sdk`, v5.0.1.1, 90 Beispiele). Die
Referenzen für diese Stufe sind `graph_nav_command_line/recording_command_line.py`
(aufzeichnen), `graph_nav_command_line/graph_nav_command_line.py` (lokalisieren und
navigieren) und `graph_nav_view_map/view_map.py` (Karte zeichnen).

Drei Befunde aus dem SDK, die den Entwurf bestimmen:

1. **Aufzeichnen braucht kein Lease.** Aus dem Beispiel-README: *„The recording_command_line
   example does not require a robot lease, and does not acquire the estop of the robot. It
   passively runs while another service (such as the tablet) controls the robot."* Man fährt
   mit dem Tablet, der Dienst schreibt passiv mit.
2. **`GraphNavClient.write_graph_and_snapshots(ordner)`** speichert eine Karte fertig auf die
   Platte. Ein eigenes Speicherformat wäre überflüssig.
3. **`graph.anchoring.anchors` ist nicht immer befüllt.** `view_map.py` prüft das ausdrücklich
   und zeichnet sonst über die Kantenkette.

---

## 2 Entschiedene Grundsatzfragen

| # | Frage | Entscheidung | Begründung |
|---|---|---|---|
| N1 | SDK-Beispiele startbar machen, oder GraphNav einbauen | **GraphNav einbauen.** Die Beispiele bleiben Referenz zum Nachlesen. | Ein Beispiel-Starter sieht nach viel Funktion aus, liefert aber nichts von dem, was spotlab ausmacht: verständliche Fehler, aufgezeichnete Läufe, sichere Abbrüche. Und ausgerechnet für das wichtigste Beispiel funktioniert er nicht: `recording_command_line.py` ist ein interaktives Menü (`inputs = input('>')` in einer Schleife) und wartet aus einer GUI heraus auf Eingaben, die nie kommen. **Ersatz:** ein Knopf, der den SDK-Beispielordner in VS Code öffnet — zum Lesen taugt das und verspricht nichts Falsches. |
| N2 | Wo das Aufzeichnen lebt | **Panel in der GUI**, Logik Qt-frei in `maps/`. Ein `spotlab record-map` fürs Terminal fällt damit ab. | Aufzeichnen ist eine Sitzung über Minuten, während ein Mensch mit dem Tablet fährt. Eine Bibliotheksfunktion, die darauf wartet, ist keine Bibliotheksfunktion. **Verschiebt bewusst eine Grenze:** die GUI hält während einer Aufnahme eine angemeldete Verbindung. Das bricht H1 nicht — H1 verbietet das *Lease*, und Aufzeichnen braucht keins. |
| N3 | Wie weit die Navigation geht | **Autonome Fahrt, aber unter unseren Regeln:** Geschwindigkeitsdeckel aus `config.toml` als `velocity_limit`, Rückmeldungen übersetzt. | Ohne Fahrt ist eine Karte Dekoration. Und `generate_travel_params(max_distance, max_yaw, velocity_limit)` nimmt eine Grenze entgegen — das SDK-Beispiel nutzt sie nur nicht. Ohne sie führe ein Schüler **autonom schneller als von Hand**, weil unser Deckel nur für `walk()` und `move()` gilt. Die Fahrt ohne Hand am Regler wäre dann die schnellste. |
| N4 | Wo die Karten liegen | **`<arbeitsordner>/karten/<name>/`**, nicht im Projekt. | Eine Karte beschreibt **den Raum, nicht das Projekt**. Zwei Schüler mit zwei Projekten in derselben Turnhalle sollen dieselbe Karte benutzen. Läufe bleiben projektbezogen, weil sie zu einem bestimmten Programm gehören. |
| N5 | Kartenformat | **Unverändert das des SDK** (`graph`, `waypoint_snapshots/`, `edge_snapshots/`), plus eine eigene `karte.json`. | Eine mit spotlab aufgezeichnete Karte lässt sich unverändert an `graph_nav_command_line.py` und `view_map.py` verfüttern, und umgekehrt. Ein eigenes Format hätte diese Brücke abgerissen, ohne etwas zu gewinnen. |
| N6 | Kartenansicht | **2D-Draufsicht auf `QPainter`**, keine neue Abhängigkeit. | `graph_nav_view_map` braucht **VTK** (`requirements.txt`: `numpy`, `vtk`) — eine 3D-Rendering-Bibliothek von rund hundert Megabyte, um Punkte und Linien zu zeichnen. Auf zwanzig Schullaptops steht das in keinem Verhältnis. Gleiche Überlegung wie bei der Tempo-Kurve in Stufe 3. |

---

## 3 Architektur

```
gui/views/maps.py · gui/mapplot.py       Ansicht „Karten" (Aufnahme + Liste + Draufsicht)
   │
maps/            session.py · store.py · geometry.py      Qt-frei, LEASELOS
   │
backends/real/   verbindung.py · graphnav.py
api/navigation.py                        Verben fürs Schülerskript
```

### Die Schichtregel, präzisiert

Bisher gilt: **kein `import bosdyn` und kein `import spotlab.backends` unterhalb von
`gui/`.** Das bleibt unverändert.

Neu darf `gui/` das Paket `spotlab.maps` benutzen. `maps/` ist **per Bauart leaselos**:
dort gibt es keinen Lease-Client und keinen E-Stop-Endpunkt. Der Grund für die alte Regel
war nie „die GUI darf nicht mit dem Roboter reden" — `doctor` tut das seit Stufe 1 —,
sondern „die GUI darf keine Kontrolle an sich reissen". Das gilt weiter und wird als Test
festgehalten.

### Gemeinsamer Verbindungsaufbau

`RealSpot.connect` macht heute Auth und Zeitsync selbst; die Aufzeichnungssitzung braucht
genau dasselbe, aber ohne E-Stop und Lease. Statt das zu verdoppeln, wandern die ersten
beiden Schritte nach `backends/real/verbindung.py::verbinde(cfg, …)`, und beide benutzen
sie. Damit bleibt die Fehlerübersetzung an einer Stelle.

### Neue Fähigkeit

`Capability.GRAPH_NAV`. Das GraphNav-Teil des Backend-Protokolls ist **ausdrücklich
optional** — nur `RealSpot` erfüllt es, der Trockenlauf deklariert es nicht und
implementiert die Verfahren gar nicht. `api/navigation.py` prüft die Fähigkeit als Erstes,
also läuft ein Trockenlauf nie in ein fehlendes Verfahren, sondern in einen Klartext-Fehler.

---

## 4 Komponenten

### 4.1 `maps/session.py` — die Aufzeichnungssitzung

```python
@dataclass(frozen=True)
class RecordingStatus:
    laeuft: bool
    wegpunkte: int
    kanten: int
    meldung: str

class RecordingSession:
    @classmethod
    def connect(cls, cfg, verbinder=None) -> "RecordingSession"
    def start(self, graph_leeren=False) -> None
    def waypoint(self, name: str) -> str          # gibt die Wegpunkt-ID zurück
    def status(self) -> RecordingStatus
    def stop(self) -> None
    def download(self, ziel: Path) -> Path
    def close(self) -> None
```

Kein Lease, kein E-Stop — nur Auth, Zeitsync, `GraphNavRecordingServiceClient` und
`GraphNavClient` fürs Herunterladen.

**Zwei Fälle, die abgefangen werden**, weil sie sonst als englischer Statuscode beim
Schüler landen:

- **`STATUS_MISSING_FIDUCIALS`** — der Fehler, der beim ersten Versuch garantiert kommt.
- **`STATUS_NOT_LOCALIZED_TO_EXISTING_MAP`** — es liegt noch eine alte Karte auf dem
  Roboter. `start(graph_leeren=True)` räumt sie weg; die GUI bietet das an, statt den
  Schüler raten zu lassen.

`status()` wird während der Aufnahme im Sekundentakt abgefragt: eine Aufnahme, bei der man
minutenlang nichts sieht, wirkt kaputt.

### 4.2 `maps/store.py` — Karten ablegen und finden

```python
@dataclass(frozen=True)
class MapInfo:
    name: str
    dir: Path
    aufgezeichnet: str | None
    roboter: str | None
    wegpunkte: int
    kanten: int

KARTEN_ORDNER = "karten"

def karten_wurzel(workspace) -> Path
def speichere_metadaten(kartenordner, name, roboter, graph) -> None
def karten(workspace) -> list[MapInfo]          # neueste zuerst
def lade_graph(kartenordner) -> map_pb2.Graph
def loesche(kartenordner) -> None
def sicherer_name(name) -> str
```

Auf der Platte:

```
<arbeitsordner>/karten/turnhalle/
  graph                  ← vom SDK
  waypoint_snapshots/…   ← vom SDK
  edge_snapshots/…       ← vom SDK
  karte.json             ← von uns
```

`karte.json` trägt nur, was das SDK nicht speichert: Name, Aufnahmezeitpunkt, Roboter,
Anzahl Wegpunkte und Kanten, spotlab-Version. Eine beschädigte `karte.json` macht die Karte
nicht unbrauchbar — `karten()` fällt dann auf die Werte aus dem Graphen zurück.

**Namensinkonsequenz, bewusst:** der Ordner heisst `karten/`, während Läufe in `runs/`
liegen. Der Unterschied ist gewollt: innerhalb einer Karte sind die Unterverzeichnisse vom
SDK vorgegeben und englisch, ein deutscher Aussenname trennt sichtbar „unseres" von
„deren".

### 4.3 `maps/geometry.py` — Positionen für die Ansicht

```python
@dataclass(frozen=True)
class Punkt:
    id: str
    name: str          # Annotationsname, sonst ""
    x: float
    y: float

@dataclass(frozen=True)
class Grundriss:
    punkte: list[Punkt]
    kanten: list[tuple[str, str]]
    quelle: str        # "anker" | "kette" | "leer"
    hinweis: str

def grundriss(graph) -> Grundriss
```

**Zwei Wege**, weil `anchoring` nicht immer befüllt ist:

1. **Anker vorhanden** — Positionen aus `anchor.seed_tform_waypoint.position`. Der
   genauere Weg, weil die Anker global optimiert sind. `quelle="anker"`.
2. **Sonst** — ab einem Wurzel-Wegpunkt die Kantenkette ablaufen und `edge.from_tform_to`
   aufmultiplizieren, wie `view_map.py` ohne `-a`. `quelle="kette"`.

Fällt auch das aus (leerer Graph, Graph ohne Kanten mit mehr als einem Wegpunkt), ist
`quelle="leer"` und `hinweis` sagt im Klartext warum — statt eine leere Fläche zu zeigen.

Bei `quelle="kette"` trägt `hinweis` den Satz, dass sich über lange Ketten Rundungsfehler
sammeln und eine Schleife sich sichtbar nicht schliessen kann. **Das ist keine Fehlfunktion,
sondern die Eigenschaft dieser Darstellung** — ohne den Hinweis sucht ein Schüler den Fehler
bei sich.

### 4.4 `backends/real/graphnav.py` — der optionale Protokollteil

```python
def upload_map(robot, graph, waypoint_snapshots, edge_snapshots) -> None
def clear_map(robot) -> None
def localize(robot, fiducial=True) -> str          # Wegpunkt-ID der Verortung
def navigate_step(robot, waypoint_id, dauer_s, travel_params, command_id=None) -> int
def navigation_status(robot, command_id) -> NavStatus
def graph_on_robot(robot) -> map_pb2.Graph
```

`NavStatus` ist ein schmaler Typ `(fertig: bool, status: str, gescheitert: bool)` — dieselbe
Naht wie `Feedback` in Stufe 1, damit `api/` protobuf-frei bleibt.

### 4.5 `api/navigation.py` — die Verben

```python
spot.load_map(name_oder_pfad) -> Map     # auf den Roboter laden
spot.localize()                          # über das nächste Fiducial verorten
spot.navigate_to(ziel, timeout=120.0)    # autonom hinfahren
spot.waypoints() -> list[str]            # benannte Marken der geladenen Karte
```

`load_map("turnhalle")` sucht in `<workspace>/karten/`; ein Pfad wird direkt benutzt.
**Ohne Argument** nimmt es die in der GUI gewählte Karte aus `[maps] active`. Ist weder das
eine noch das andere gesetzt, sagt der Fehler das und nennt die vorhandenen Karten.

Dafür bekommt `Config` das Feld `active_map: str = ""`, geschrieben als `[maps] active` —
dieselbe Mechanik wie `workspace` in Stufe 3.

`navigate_to(ziel)` löst `ziel` gegen die bei der Aufnahme gesetzten Namen
(`waypoint.annotations.name`) auf. Unbekannt ⇒ Fehler, der **die vorhandenen Namen
aufzählt**.

**Zwei Dinge übernimmt die Bibliothek:**

- **Nachsenden.** Navigationskommandos verfallen wie Geschwindigkeitskommandos. Das
  SDK-Beispiel schickt `navigate_to` mit einer Sekunde Gültigkeit in einer Schleife und
  fragt dazwischen `navigation_feedback` ab. Dieselbe Mechanik wie unser `walk()`, dieselbe
  Begründung: einmal in der Bibliothek statt in jedem Skript.
- **Geschwindigkeitsdeckel.** `generate_travel_params` bekommt ein `velocity_limit` aus
  `config.toml` — dasselbe, das für `walk()` und `move()` gilt.

Jeder Schritt geht in den Ereignisstrom: `kommando` beim Start, `rückmeldung` bei
Statuswechsel, `fehler` beim Scheitern. Damit ist eine autonome Fahrt genauso nachvollziehbar
wie eine gefahrene.

### 4.6 Ansicht „Karten"

Fünfter Eintrag in der Seitenleiste, drei Bereiche:

**Aufnahme** — Knöpfe *Aufnahme starten*, *Wegpunkt setzen* (mit Namensfeld), *Aufnahme
beenden und speichern*. Daneben laufend der Stand aus `status()`. Vor dem Start der Hinweis,
dass der Spot ein Fiducial sehen muss und dass man ihn **mit dem Tablet** fährt.

**Liste** — die Karten aus `store.karten()`, mit Aufnahmezeitpunkt und Grösse.

**Draufsicht** — `gui/mapplot.py`, ein `QPainter`-Widget wie die Tempo-Kurve: Wegpunkte als
Punkte, Kanten als Linien, benannte Marken beschriftet, massstabsgetreu eingepasst. Der
`hinweis` aus dem `Grundriss` steht darunter.

**Auswählen.** Ein *Als aktive Karte setzen*-Knopf schreibt den Namen nach `config.toml`
unter `[maps] active`. Damit lädt `spot.load_map()` **ohne Argument** genau diese Karte —
die Auswahl in der GUI hat also eine echte Wirkung im Skript, ohne dass die GUI selbst etwas
auf den Roboter lädt.

Die GUI lädt die Karte **nicht** hoch. Grund und offene Annahme dazu in Abschnitt 10.

---

## 5 Datenfluss

```
Aufzeichnen (leaselos)                     Navigieren (Lease + Not-Aus)
──────────────────────                     ────────────────────────────
GUI „Karten"                               Schülerskript
   │ maps/session.py                          │ api/navigation.py
   ▼                                          ▼
Recording-Service ──► write_graph_        backends/real/graphnav.py
                      and_snapshots           │
   │                                          ▼
   ▼                                       GraphNav-Service
<arbeitsordner>/karten/<name>/  ──────────────┘  (load_map lädt von dort hoch)
   │
   ▼
maps/geometry.py ──► gui/mapplot.py
```

---

## 6 Fehlerbehandlung

| Status | Was der Schüler liest |
|---|---|
| `MISSING_FIDUCIALS` | „Der Spot sieht kein Fiducial. Stell ihn so hin, dass eine Markierung im Bild ist, und starte die Aufnahme neu." |
| `NOT_LOCALIZED_TO_EXISTING_MAP` | „Auf dem Roboter liegt noch eine andere Karte. Beim Starten ‚Karte auf dem Roboter leeren' ankreuzen." |
| `NO_LOCALIZATION` | „Der Spot weiss nicht, wo er ist — rufe zuerst `spot.localize()` auf." |
| `LOST` | „Der Spot hat sich auf der Karte verloren. Fahr ihn zurück zu einem Fiducial und verorte neu." |
| `STUCK` | „Der Spot kommt nicht weiter. Steht etwas im Weg?" |
| `NO_ROUTE` | „Von hier führt kein Weg zu ‚<ziel>'." |
| `ROBOT_IMPAIRED` | „Der Roboter meldet eine Störung — prüfe mit `spotlab doctor`." |
| `COMMAND_TIMED_OUT` | „Das Navigationskommando ist abgelaufen. Das ist ein Fehler in spotlab, bitte melden." |
| Ziel unbekannt | „Den Wegpunkt ‚<ziel>' gibt es nicht. Vorhanden: start, kueche, fenster." |
| Kein Arbeitsordner | „Es ist kein Arbeitsordner gesetzt. Wähle einen in der Ansicht ‚Projekte'." |

Scheitert eine Fahrt, wird der Fehler geworfen und der Abbau von `connect()` erledigt den
Rest: stoppen, hinsetzen, Motoren aus, Lease frei. **Die bestehende Invariante gilt
unverändert.**

---

## 7 Prüfung

**Ohne Roboter** — und das ist erfreulich viel, weil sich `map_pb2.Graph` im Test von Hand
bauen lässt:

- `maps/geometry.py`: Anker-Weg · Kettenweg · leerer Graph · Graph mit einem Wegpunkt ohne
  Kanten · Graph mit Wegpunkten ohne Anker aber mit Kanten · Namen aus Annotationen ·
  `hinweis` bei `quelle="kette"` gesetzt
- `maps/store.py`: schreiben → auflisten → lesen → löschen · Namen entschärfen · beschädigte
  `karte.json` fällt auf Graphwerte zurück · fehlender Kartenordner ergibt leere Liste
- `maps/session.py`: gegen eine Attrappe des Recording-Clients — Reihenfolge start/waypoint/
  stop/download · `MISSING_FIDUCIALS` wird übersetzt · `graph_leeren=True` ruft `clear_graph`
- Übersetzungstabelle: pro Zeile ein Test
- `api/navigation.py` gegen ein Attrappen-Backend: Namensauflösung · unbekanntes Ziel zählt
  vorhandene auf · **`velocity_limit` aus der Konfiguration landet in den `TravelParams`** ·
  Kommando wird nachgesendet · `REACHED_GOAL` beendet · `LOST` und `STUCK` werfen Klartext
- Fähigkeitsprüfung: `navigate_to` gegen `dryrun` ⇒ `UnsupportedCapability`
- `config.py`: `active_map` überlebt Schreiben und Lesen; `load_map()` ohne Argument nimmt
  sie; ohne gesetzte Karte kommt Klartext mit Aufzählung
- Schichtregel: kein `import bosdyn` unter `gui/`; **kein Lease- und kein E-Stop-Client
  unter `maps/`** (neuer Test, hält N2 fest)
- GUI offscreen: Ansicht baut sich · Liste füllt sich · Draufsicht zeichnet mit und ohne
  Anker · leerer Grundriss zeigt den Hinweis

---

## 8 Abnahme am Gerät

| # | Prüfung | Erwartung |
|---|---|---|
| **A12** | **Fiducials** — vorhanden, aufgehängt, wird eine erkannt? | *Voraussetzung für A13–A16.* Ohne Fiducial ist diese ganze Stufe nicht benutzbar. |
| **A13** | Karte aufzeichnen: mit dem Tablet durch den Raum fahren | Wegpunkte entstehen laufend und die GUI zeigt den Zähler steigen; benannte Marken landen im Graphen; der Download enthält `graph` und für jeden Wegpunkt einen Schnappschuss |
| **A14** | **Gegenprobe zur Interoperabilität**: dieselbe Karte in spotlab **und** mit `view_map.py` aus dem SDK öffnen | Beide zeigen dieselbe Anordnung. Bestätigt Format (N5) und Geometrie (4.3) auf einen Schlag |
| **A15** | Lokalisieren nach einem Neustart des Roboters | `spot.localize()` findet die Verortung über das Fiducial |
| **A16** | **Autonome Fahrt.** *Freifläche und Aufsicht nötig.* | Route wird erreicht; **die aus `zustand.jsonl` gemessene Geschwindigkeit bleibt unter dem Deckel aus `config.toml`**; der Not-Aus wirkt während der Fahrt |

A16 prüft den Punkt, auf den es ankommt: dass unsere Grenze wirklich greift und nicht nur im
Code steht. Die Messung kommt dabei aus der Aufzeichnung, die seit Stufe 1 ohnehin läuft.

---

## 9 Nicht-Ziele

Autowalk-Missionen · Area Callbacks · Docking · GPS · 3D-Punktwolken-Ansicht ·
Anker-Optimierung (`graph_nav_anchoring_optimization`) · Treppen ·
`navigate_to_anchor` (Fahrt zu freien Koordinaten statt zu Wegpunkten) ·
Karten zusammenführen · Beispiel-Starter für die SDK-Beispiele (siehe N1).

---

## 10 Offene Annahmen

**Braucht `upload_graph` ein Lease?** Nicht verifiziert. Die Signatur ist
`upload_graph(lease=None, graph=…)`, das Lease also formal optional — aber
`graph_nav_command_line.py` legt seinen gesamten Ablauf in ein
`LeaseKeepAlive(lease_client, must_acquire=True, return_at_exit=True)` (Zeile 577), das
Hochladen eingeschlossen. Ob der Dienst es erzwingt, geht daraus nicht hervor.

*Auflösung:* wir laden ausschliesslich aus dem Skript hoch, wo ohnehin ein Lease liegt.
Diese Entscheidung ist **unabhängig von der Antwort korrekt** und macht die Prüfung
unnötig. Sollte sich später zeigen, dass leaseloses Hochladen zulässig ist, könnte die GUI
das Auswählen zu einem echten Hochladen ausbauen — nötig ist es nicht.

**Was der Aufzeichnungsdienst automatisch tut.** Wie dicht der Dienst von selbst Wegpunkte
setzt und wann er Schleifen schliesst, ist nicht dokumentiert festgelegt und wird in A13
beobachtet statt angenommen. Die GUI zeigt deshalb den Zähler, statt eine Erwartung zu
formulieren.

---

## 11 Abhängigkeiten

**Keine neuen.** GraphNav ist Teil von `bosdyn-client`, das seit Stufe 1 installiert ist;
gezeichnet wird mit `QPainter` aus dem bereits vorhandenen PySide6.
