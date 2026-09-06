# spotlab Übungsraum — ein Zimmer für den Sim, Turtle-nah und ehrlich

**Datum:** 2026-09-02
**Status:** Entwurf zur Freigabe
**Umfang:** Stufe 10. Setzt Fundament (1+2), GUI (3) und die Umwelt-Schicht (9)
voraus; baut auf dem Sim-Backend auf, das seit dem 12.08.2026 nach gemessenen
Gangarten fährt.

---

## 1 Zweck

Ein Schüler soll ein Programm schreiben, es **ohne Roboter laufen lassen und
dabei zusehen** — Spot fährt durch ein gezeichnetes Zimmer, hinterlässt eine
Spur, stösst an Wände, findet AprilTags. Turtle-nah im Gefühl, aber mit den
Zeiten und Geschwindigkeiten des echten Geräts.

```python
with spotlab.connect(backend="sim") as spot:
    spot.power_on()
    spot.stand()
    spot.move(forward=2.0)
    for tag in spot.tags():
        print(f"Tag {tag.id}: {tag.distance:.1f} m")
```

Dasselbe Programm läuft danach unverändert am Roboter.

### Vorgefundener Stand

**Der bewegliche Spot existiert bereits.** `backends/sim.py` (486 Z.) führt eine
Pose und integriert sie mit den am 12.08.2026 gemessenen Gangarten:

```python
self._pose = (0.0, 0.0, 0.0)                          # Zeile 73
self._pose = integriere(self._pose, vx, vy, wz, dt)   # Zeile 388
```

`_zum_ziel()` fährt eine Zieltrajektorie ab, statt zu ihr zu springen — eine
Kollisionsprüfung greift also an einer echten Bewegung an, nicht an einem
Sprung.

Was fehlt, ist die **Welt darum**: Wände, Hindernisse, Anstossen, und eine
Ansicht, die beides zeigt.

Nicht nachnutzbar: `maps/geometry.py` (105 Z.) ordnet GraphNav-Wegpunkte an und
kennt keine Wände; `gui/mapplot.py` (89 Z.) zeichnet genau jene Grundrisse.

---

## 2 Entschiedene Grundsatzfragen

**Der Sim ist die Grundlage, nicht ein neues Turtle-Backend.** Ein Programm, das
im Übungsraum funktioniert, soll am Gerät funktionieren. Sofortiges Versetzen
(`move(forward=1)` springt) wäre angenehmer und würde über Zeit und Tempo lügen.

**Ohne Raum bleibt der Sim exakt, was er ist.** `SimBackend(raum=None)` verhält
sich wie heute: leere Welt, `world_objects()` gibt `[]`, kein Gitter. Die neuen
Fähigkeiten meldet er nur mit Raum.

**`welt/` importiert nichts aus `backends/`.** Beim Entwurf zeigte sich: die
Tag-Berechnung bräuchte `richtung()`, das seit Stufe 9 in `backends/base.py`
liegt. Statt eine Kante `welt/ → backends/` zu ziehen, bleibt die Aufteilung
schärfer: **`welt/` beantwortet nur geometrische Fragen** (welche Tags sind von
hier aus sichtbar, mit rohem dx/dy) und **`sim.py` übersetzt** in `Tag` und
`ObstacleGrid`. Das hält `welt/` auf Standardbibliothek plus `tomllib` — und
genau deshalb darf die GUI es importieren, ohne die Regel „kein
`spotlab.backends` unterhalb von `gui/`" zu berühren.

**Nachtrag aus der Umsetzung (02.09.2026):** `raum.py` und `kollision.py` halten
sich an stdlib plus `tomllib`; `wahrnehmung.py` benutzt zusätzlich **numpy**,
weil das Gitter 16 384 Zellen hat und eine reine Python-Schleife rund 0.2 s je
Abruf kostete — bei 2 Hz ein Drittel eines Kerns. Die GUI importiert nur
`raum.py` und zieht damit weiterhin nichts Schweres herein. Zwei Tests halten
beides fest.

**Wände sind Strecken, Hindernisse achsparallele Rechtecke.** Nur Strecken
erlauben einen Durchgang (zwei Strecken mit Lücke); Rechtecke decken Tisch,
Kiste und Stuhlstapel ab und halten die Kollisionsprüfung bei einer Handvoll
Zeilen. Ein gedrehter Tisch ist der erste Fall, für den das nicht reicht.

**Der Roboter ist ein Kreis mit 0.35 m Radius.** Vereinfachung von Spots
Grundfläche (~1.1 × 0.5 m), im Docstring als solche benannt: ein Kreis kann sich
nicht seitlich durch eine schmale Lücke drehen, ein echter Spot schon.
*Geändert 06.09.2026:* 0.27 m — eine Gitterzelle unter dem Vorgabe-Rand von
`ObstacleGrid.is_free` (0.3 m). Mit 0.35 m blieb ein Programm, das der freien
Strecke des Gitters folgte, an der Türkante hängen; was das Gitter frei nennt,
muss im Sim begehbar sein (`welt/kollision.py`, `tests/test_welt_kollision.py`).

**Anstossen hält an, es bricht nicht ab.** Der echte Spot wirft keine Ausnahme,
wenn er vor einem Hindernis stehen bleibt. Ein Sim, der das täte, verspräche
etwas, das die Wirklichkeit nicht hält.

**Meter und Grad, links positiv** — dieselben Einheiten wie `move(turn=…)`. Wer
`spot.move(turn=90)` kennt, liest eine Raumdatei ohne Umrechnung.

**Die Ansicht startet keine Programme selbst**, sondern ruft denselben Weg wie
die Ansicht „Projekte". Grund ist die Invariante aus CLAUDE.md: *genau ein Lauf*
ist der, auf den Stopp und NOT-AUS zeigen.

---

## 3 Architektur

```
   welt/                        reine Geometrie, stdlib + tomllib
   ├── raum.py         Raum, Hindernis, RaumTag; laden aus TOML
   ├── kollision.py    darf ich von A nach B? Sichtlinie frei?
   ├── wahrnehmung.py  sichtbare Tags (roh), Abstandsgitter
   └── vorlagen/       leer.toml, moebliert.toml, durchgang.toml
            │                                    │
            │ (Geometrie)                        │ (liest TOML)
            ▼                                    ▼
   backends/sim.py                        gui/views/uebungsraum.py
   uebersetzt in Tag / ObstacleGrid       zeichnet, waehlt Start
            │                                    ▲
            ▼                                    │ liest Lauf-Verzeichnis
   zustand.jsonl (pose 10 Hz) ──────────────────┘
   ereignisse.jsonl (angestossen)
```

### Die Schichtregel

`welt/` kennt weder Qt noch bosdyn noch `backends/` noch `api/`. Es beantwortet
Fragen über Punkte, Strecken und Rechtecke. Alles, was eine spotlab-Form daraus
macht, tut `sim.py`; alles, was daraus Pixel macht, tut die Ansicht.

### Warum kein eigenes Backend

Erwogen und verworfen: eine Hülle, die `SimBackend` umschliesst und die Pose
nachträglich korrigiert. Kollision muss *während* der Integration entschieden
werden; eine Hülle liesse den Sim ankommen und setzte ihn dann zurück — er
glaubte dann, er stehe woanders, als er steht.

---

## 4 Komponenten

### 4.1 `welt/raum.py` — das Datenmodell

```python
@dataclass(frozen=True)
class Hindernis:
    name: str
    rechteck: tuple      # (x, y, breite, hoehe), achsparallel, Meter

@dataclass(frozen=True)
class RaumTag:
    id: int
    x: float
    y: float
    grad: float          # Blickrichtung des Tags

@dataclass(frozen=True)
class Raum:
    name: str
    beschreibung: str
    groesse: tuple       # (breite, hoehe) in Metern
    start: tuple         # (x, y, grad) — Standard-Startpose
    waende: tuple        # ((x1, y1, x2, y2), …)
    hindernisse: tuple
    tags: tuple
```

`raum_laden(name, workspace=None)` sucht **erst im Arbeitsordner**
(`<arbeitsordner>/raeume/<name>.toml`), dann im Paket. Eigene Räume sind damit
vorgesehen, ohne heute gebaut zu werden — später kostet es einen Ordner, keinen
Umbau.

### 4.2 Die drei Vorlagen

| Datei | Inhalt | wofür |
|---|---|---|
| `leer.toml` | vier Wände, ein Tag | erste Schritte: fahren, drehen, Tag finden |
| `moebliert.toml` | Tisch, zwei Stapel, zwei Tags | ausweichen, `obstacles()` benutzen |
| `durchgang.toml` | zwei Räume, **0.9 m** Türlücke, Tag im zweiten | hinausfahren |

Die Türlücke ist mit 0.9 m bewusst grosszügig: bei einem Roboterradius von
0.35 m bliebe sonst zu wenig Spiel, und die Kreisvereinfachung (§2) würde zur
Auslegungsfrage statt zu einer Nebensächlichkeit. *(Seit 06.09.2026 ist der
Radius 0.27 m, siehe §2; die 0.9 m bleiben.)*

```toml
[raum]
name         = "Möbliert"
beschreibung = "Ein Zimmer mit Tisch und zwei Stuhlstapeln."
groesse      = [6.0, 4.0]
start        = [1.0, 1.0, 0.0]
waende = [
    [0.0, 0.0, 6.0, 0.0], [6.0, 0.0, 6.0, 4.0],
    [6.0, 4.0, 0.0, 4.0], [0.0, 4.0, 0.0, 0.0],
]
hindernisse = [
    { name = "Tisch",       rechteck = [2.5, 1.5, 1.2, 0.8] },
    { name = "Stuhlstapel", rechteck = [4.5, 2.8, 0.6, 0.6] },
]

[[tag]]
id = 1
pose = [5.9, 2.0, 180.0]
```

### 4.3 `welt/kollision.py` — darf ich dorthin?

```python
ROBOTER_RADIUS_M = 0.35
MAX_SCHRITT_M = 0.10

def frei(raum, x, y): ...              # Abstand zu allem >= Radius?
def bewege(raum, von, nach): ...       # (pose, angestossen_an|None)
def sicht_frei(raum, a, b): ...        # Strecke schneidet keine Wand?
```

`bewege` zerlegt Schritte über `MAX_SCHRITT_M` und prüft jeden einzeln. Grund:
`dt` kommt aus der Wanduhr und hängt daran, wie oft ein Skript den Zustand
abfragt — bei einer halben Sekunde und 0.5 m/s wären das 25 cm. Das bliebe zwar
unter dem Durchmesser, aber die Zusicherung „kein Programm fährt durch eine
Wand" soll nicht von der Abfragehäufigkeit abhängen.

Die Drehung ist von der Kollision **ausgenommen**: ein Kreis, der sich dreht,
überstreicht keine neue Fläche. Ein Spot, der in einer Ecke steht, kann sich
also herausdrehen — was er in Wirklichkeit auch kann.

### 4.4 `welt/wahrnehmung.py` — was von hier aus zu sehen ist

```python
TAG_REICHWEITE_M = 3.0     # geschaetzt; Abnahmepunkt A22 misst den echten Wert
GITTER_ZELLEN = 128
GITTER_ZELLE_M = 0.03

def sichtbare_tags(raum, pose): ...    # [(RaumTag, dx, dy), …] im Koerperframe
def abstandsgitter(raum, pose): ...    # (werte, bekannt) als Listen
```

**Kein Blickfeld-Kegel.** Der echte Spot hat fünf Kameras und sieht rundum; ein
Kegel wäre eine erfundene Einschränkung. Ein Tag zählt, wenn er in Reichweite
ist und die Sichtlinie frei.

Das Gitter hat die Masse des echten LocalGrid: 128 × 128 à 3 cm ≈ **3.84 m
Kantenlänge**, der Roboter in der Mitte — es reicht also nur **1.92 m** weit und
erfasst in einem 6 × 4-m-Zimmer nicht die gegenüberliegende Wand. Das ist so
gewollt: der echte LocalGrid kann es auch nicht.

**Unbekannt ist, was verdeckt ist.** Zellen, deren Sichtlinie durch eine Wand
oder ein Hindernis läuft, kommen als unbekannt zurück, nicht als frei — sie
füllen die `known`-Maske, die `ObstacleGrid` seit Stufe 9 trägt. Der Roboter
weiss dadurch nicht, was hinter dem Tisch liegt, genau wie in Wirklichkeit.

Die **Tag-Reichweite (3.0 m) ist grösser als die halbe Gitterkante (1.92 m)** —
Spot sieht ein Fiducial also weiter, als sein Hindernisgitter reicht. Auch das
entspricht dem Gerät: zwei verschiedene Sensoren mit verschiedenen Reichweiten.

### 4.5 `backends/sim.py` — die Übersetzung

Erweiterung um rund 30 Zeilen:

- `__init__(…, raum=None, start=None)`; mit `start` beginnt die Pose dort statt
  bei `(0, 0, 0)`, damit Raum- und odom-Koordinaten zusammenfallen.
- `capabilities()` meldet mit Raum zusätzlich `WORLD_OBJECTS | LOCAL_GRID`.
- `world_objects()` / `local_grid()` bauen aus dem Rohergebnis von
  `welt/wahrnehmung.py` die Datenklassen — hier, nicht dort, weil `richtung()`
  in `backends/base.py` wohnt (§2).
- In `_fortschreiben` eine Zeile:

```python
neu = integriere(self._pose, vx, vy, wz, dt)
self._pose, angestossen = self._bewege(self._pose, neu)
```

`_bewege` gibt ohne Raum unverändert `(neu, None)` zurück.

### 4.6 Das Anstoss-Ereignis

Beim **ersten** versperrten Schritt eine Zeile, danach Schweigen bis zur
nächsten freien Bewegung:

```json
{"art": "angestossen", "daten": {"x": 2.41, "y": 1.02, "hindernis": "Tisch"}}
```

Ohne diese Flanke schriebe ein Programm, das zehn Sekunden gegen eine Wand
drückt, hundert gleiche Zeilen und machte das Protokoll unlesbar.

### 4.7 Ansicht „Übungsraum"

Neunte Ansicht. Links die Zeichnung, rechts Raumwahl, Startpose und der
Startknopf.

- Wände als Linien, Hindernisse gefüllt, Tags als nummerierte Marken, Spot als
  Kreis mit Blickstrich, Spur gepunktet, Anstösse als Kreuz
- Klick setzt die Startposition, Ziehen die Blickrichtung
- Gemerkt wird sie in `config.toml` als `raum` und `raum_start` — wie die aktive
  Karte, damit sie auch für Läufe aus VS Code gilt
- Der Startknopf **delegiert** an die Ansicht „Projekte" (§2)
- Beginnt ein Sim-Lauf, holt sich die Ansicht nach vorn

Gezeichnet wird von `gui/raumplot.py` (neu). Farben ausschliesslich aus
`theme.py`.

---

## 5 Datenfluss

**Beim Verbinden:**

```
connect(backend="sim")
  → Raum und Startpose aus config.toml (oder Argument)
  → raum_laden()
  → SimBackend(raum=…, start=…)
  → recorder.event("verbunden", backend="sim", raum="moebliert")
```

**Während der Fahrt:**

```
_fortschreiben()  → integriere → welt.bewege → Pose
                                     └→ bei Sperre: Ereignis "angestossen" (einmal)
Abtaster (10 Hz)  → zustand.jsonl: pose = (x, y, yaw)
```

**In der Ansicht:**

```
uebungsraum.py → liest ereignisse.jsonl  (Raumname, Anstösse)
               → raum_laden(name)        (Geometrie)
               → liest zustand.jsonl     (Spur)
               → raumplot
```

Die GUI berührt weder Roboter noch Backend.

---

## 6 Fehlerbehandlung

| Lage | Verhalten |
|---|---|
| Raumdatei fehlt | `SpotlabError` mit den vorhandenen Namen — dieselbe Form wie bei einer fehlenden Karte |
| Raumdatei kaputt (TOML, fehlende Felder) | `SpotlabError`, die das FELD nennt, nicht nur die Datei |
| Startpose liegt in einer Wand | Beim Setzen abgewiesen, mit Hinweis; die Ansicht markiert unzulässige Stellen beim Klicken |
| Anstossen | Pose bleibt stehen, ein Ereignis, Programm läuft weiter |
| `obstacles()` ohne Raum | `UnsupportedCapability` mit deutschem Text — wie heute |
| Lauf-Verzeichnis ohne `pose` | Ansicht zeigt den Raum ohne Spur, keine Ausnahme |
| Halbe letzte jsonl-Zeile | übersprungen, wie in `record/read.py` |

---

## 7 Prüfung

Alles ohne Roboter, die Geometrie zusätzlich ohne Qt.

- `test_welt_raum.py` — TOML lesen, fehlende Felder, Suchreihenfolge
  Arbeitsordner vor Paket, alle drei Vorlagen laden und sind stimmig (Startpose
  liegt frei, Türlücke breiter als der Durchmesser)
- `test_welt_kollision.py` — Strecke gegen Wand samt Grenzfällen (parallel,
  berührend, Schnittpunkt hinter dem Ziel), Zerlegung langer Schritte, Drehen
  in der Ecke bleibt erlaubt, Hindernis blockiert
- `test_welt_wahrnehmung.py` — Tag hinter einer Wand wird **nicht** gemeldet,
  Tag knapp ausser Reichweite ebenfalls nicht, Gitter kennt die Wand, **verdeckte
  Zellen sind unbekannt statt frei**, und das Gitter reicht nicht weiter als
  seine halbe Kante
- `test_backend_sim.py` (erweitert) — ohne Raum unverändertes Verhalten,
  mit Raum die neuen Fähigkeiten, Anstoss-Ereignis genau einmal
- `test_gui_uebungsraum.py` — Zeichnung gegen einen vorbereiteten Raum, Klick →
  Startpose, Ansicht gegen ein vorbereitetes Lauf-Verzeichnis, und über `ast`:
  **kein `bosdyn`, kein `spotlab.backends`**
- Ein Test hält fest, dass `welt/` weder Qt noch bosdyn noch `backends` noch
  `api` importiert — die Schichtregel aus §2 reisst sonst still

---

## 8 Abnahme am Gerät

**Diese Stufe hat keine eigene.** Sie berührt keinen Roboter: kein Lease, kein
Not-Aus-Endpunkt, keine Verbindung — dieselbe Regel wie für `maps/` und
`beobachtung/`, und ein Test hält sie fest.

Sie **verbraucht** allerdings ein Ergebnis vom Gerät: `TAG_REICHWEITE_M = 3.0`
ist geschätzt, und **A22** misst den wahren Wert. Bis dahin ist die Zahl als
Schätzung gekennzeichnet; danach wird sie ersetzt, und der Übungsraum wird
dadurch wahrheitsgetreuer, ohne dass sich Code ändert.

---

## 9 Nicht-Ziele

- **Physik.** Kein Umkippen, kein Rutschen, keine Treppen. Der Sim bleibt eine
  Interpolation gemessener Gangarten.
- **Gedrehte Hindernisse.** Achsparallele Rechtecke, bis ein Fall auftritt.
- **Eigene Räume in der GUI zeichnen.** Der Ladepfad ist vorbereitet, ein
  Editor nicht.
- **Kamerabilder.** Der Sim liefert weiterhin keine — ein erfundenes Bild wäre
  schlimmer als gar keins.
- **Mehrere Roboter.**
- **Zeitraffer.** Erwogen; er verdoppelt die Zusicherungen und wartet, bis der
  einfache Fall steht.

---

## 10 Offene Annahmen

- **Tag-Reichweite 3.0 m** ist geschätzt — A22, siehe §8.
- **Roboterradius 0.35 m** ist aus der Grundfläche abgeleitet, nicht gemessen.
  Er ist bewusst konservativ: lieber bleibt der Sim einmal zu früh stehen.
- **Die Drehung ist kollisionsfrei.** Für einen Kreis stimmt das exakt, für
  einen 1.1 m langen Spot nicht. In einer engen Ecke ist der Sim damit
  optimistischer als die Wirklichkeit.
- **Das Gitter reicht 1.92 m, die Tag-Sicht 3.0 m.** Ein Schüler kann also
  einen Tag sehen, zu dem das Hindernisgitter noch nichts sagt. Am Gerät ist es
  genauso — zwei Sensoren, zwei Reichweiten —, aber es überrascht beim ersten
  Mal.
- **Ob `dt` je über 0.5 s springt**, hängt an Schülerskripten (lange
  `time.sleep`). Die Zerlegung in §4.3 macht die Frage für die Kollision
  gegenstandslos, nicht aber für die Spur: die Ansicht zeichnet dann eine
  längere Gerade zwischen zwei Punkten, als tatsächlich gefahren wurde.

---

## 11 Abhängigkeiten

- **Voraus:** Fundament (1+2), GUI (3), Umwelt (9) für `ObstacleGrid`, `Tag`
  und die `known`-Maske; das Sim-Backend vom 12.08.2026.
- **Neu:** keine Pakete. `tomllib` ist Standardbibliothek ab 3.11, numpy und
  PySide6 sind bereits Abhängigkeiten.
- **Nachgelagert:** `matura-spot` ist nicht betroffen. Der Übungsraum ist
  Unterricht, nicht Forschung — die MuJoCo-Simulation bleibt dort.

### Reihenfolge

1. `welt/raum.py` + Vorlagen (ohne sie lässt sich nichts prüfen)
2. `welt/kollision.py`
3. `welt/wahrnehmung.py`
4. `backends/sim.py` — Übersetzung und Einhängen
5. `gui/raumplot.py` + Ansicht „Übungsraum"
6. README und `spotlab new`-Vorlage um ein Beispielprogramm ergänzen
