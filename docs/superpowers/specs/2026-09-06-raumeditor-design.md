# Raumeditor — Räume bauen, in 3D sehen, aus Karten rekonstruieren

Entwurf vom 06.09.2026. Entscheidungen des Autors im Gespräch:

- **Alles in einem Zug**, Reihenfolge **Bauen → 3D-Sicht → Rekonstruktion**.
- **Wände bleiben Linien** (Segmente mit Dicke und Höhe je Raum); dazu kommen
  **Blöcke** (drehbare Kästen mit Höhe) und Tags mit Hängehöhe.
- **3D per OpenGL** (`QOpenGLWidget` + PyOpenGL), mit **Rückfall auf 2D**, nie
  ein schwarzes Fenster.
- **Rekonstruktion aus der Punktwolke** der GraphNav-Karte, die Wolke bleibt als
  **Pauspapier** im Editor; der Pfad-Schlauch ist der Notnagel ohne Wolken.
- **Griffe und Blender-Tasten**, dieselbe Logik darunter; bearbeitet wird in 2D
  und 3D gleich.
- Architektur **„ein Modell, zwei Sichten, Logik ohne Qt"**.

Der Tab „Übungsraum" wird durch den Tab **„Raumeditor"** ersetzt; das
Übungsfenster (Live-Spur eines Laufs) bleibt.

Vorarbeit des Autors: `D:\Users\janis\Documents\Spot Projects\src\map_viewer`
(Plotly-Viewer für GraphNav-Karten; die Transformationskette der Punktwolken
in `transformer.py::compute_point_clouds` wird übernommen). Fixture für die
Rekonstruktion: `Spot Projects\maps\map_catacombs_01` — 107 verankerte
Wegpunkte, 28 × 25 m, ~12 000 Punkte je Schnappschuss, 31 AprilTags.

## Ziel

Ein Schüler baut in der GUI aus Wänden, Blöcken und Tags ein Zimmer, sieht es
in 2D und 3D, setzt den Start und fährt darin — mit `backend="sim"` und
`backend="mujoco"`, ohne dass sich am Schülerprogramm etwas ändert. Der Autor
lädt eine echte GraphNav-Karte der Schule, bekommt daraus einen Raum mit Wänden
und den echten Tags, zieht im Editor nach, was die Automatik falsch hatte, und
lässt die Sim durch den echten Gang laufen.

## Nicht-Ziele

- Keine schwebenden Blöcke, keine Rampen, Treppen, Zylinder, keine Decke, kein
  zweites Stockwerk. Blöcke stehen auf dem Boden.
- Keine Texturen, kein Robotermesh in der Editor-3D-Sicht; keine Live-3D-Ansicht
  des Laufs im Editor — das bleibt Übungsfenster plus `ansicht.jpg`.
- Die Rekonstruktion liefert **nur Wände und Tags**. Ein Tisch in der Wolke wird
  zu kurzen Wandstücken; Blöcke daraus zu machen ist Handarbeit im Editor.
  Möbelerkennung ist ein eigenes Projekt.
- Kein Verlauf über Sitzungen, kein gemeinsames Bearbeiten, keine Dicke oder
  Höhe je einzelner Wand (eine halbhohe Trennwand ist ein Block).

---

## 1 Raumformat v2 (`welt/raum.py`)

`welt/` bleibt **reine Standardbibliothek** — deshalb darf die GUI es
importieren. Alle Elemente sind unveränderliche Dataclasses; jede Bearbeitung
erzeugt einen neuen `Raum`.

```python
@dataclass(frozen=True)
class Wand:
    x1: float; y1: float; x2: float; y2: float          # Meter, Weltframe

@dataclass(frozen=True)
class Block:
    name: str
    x: float; y: float                                  # Mitte
    breite: float; tiefe: float; hoehe: float           # breite entlang der eigenen x-Achse
    drehung: float = 0.0                                # Grad, links positiv

@dataclass(frozen=True)
class RaumTag:
    id: int
    x: float; y: float
    grad: float                                         # Blickrichtung, Grad
    hoehe: float = 0.30                                 # Hängehöhe der Tagmitte

@dataclass(frozen=True)
class Raum:
    name: str
    beschreibung: str
    start: tuple                                        # (x, y, grad)
    waende: tuple                                       # Wand, ...
    bloecke: tuple                                      # Block, ...
    tags: tuple                                         # RaumTag, ...
    groesse: tuple | None = None                        # (breite, hoehe) oder None
    wand_dicke: float = 0.06
    wand_hoehe: float = 1.0
```

Konventionen wie überall in der Schüler-API: Meter, Grad, links positiv.
`groesse` ist **optional**; fehlt sie, liefert `huelle(raum)` die Bounding-Box
aller Elemente plus 0.5 m Rand — für die Rekonstruktion wäre eine Pflichtangabe
lästig. Die alten Felder `Hindernis` und `raum.hindernisse` verschwinden; ihre
Benutzer (`kollision`, `wahrnehmung`, `mujoco.welt_aus_raum`, `raumplot`)
lernen Blöcke.

### Datei

```toml
[raum]
name         = "Durchgang"
beschreibung = "Zwei Zimmer, verbunden durch eine Tür."
start        = [1.0, 2.0, 0.0]
groesse      = [9.0, 4.0]          # optional
wand_dicke   = 0.06                # optional, Vorgabe
wand_hoehe   = 1.0                 # optional, Vorgabe
waende = [
    [0.0, 0.0, 9.0, 0.0],
]

[[block]]
name    = "Kiste"
mitte   = [2.35, 3.15]
groesse = [0.7, 0.7, 0.75]         # breite, tiefe, hoehe
drehung = 0.0

[[tag]]
id    = 3
pose  = [8.9, 2.0, 180.0]
hoehe = 0.30                       # optional
```

**Kompatibilität**: `hindernisse = [{name, rechteck=[x, y, b, h]}]` wird weiter
gelesen und zu Blöcken übersetzt (Mitte = Ecke + halbe Kante, Drehung 0, Höhe
0.75 m — der heutige `HINDERNIS_HOEHE_M`). Die drei Vorlagen und eigene Räume
laden unverändert; `raum_speichern(raum, pfad)` schreibt immer die neue Form
(TOML von Hand geschrieben, `tomllib` liest nur). Ein Test lädt jede Vorlage,
speichert sie und lädt sie wieder: gleicher `Raum`.

### Ablage

- Vorlagen im Paket (`welt/vorlagen/`), schreibgeschützt; „Vorlage laden"
  öffnet eine Kopie ohne Namen.
- Eigene Räume unter `<arbeitsordner>/raeume/<name>.toml` — der Pfad, den
  `raum_laden(name, workspace)` heute zuerst prüft. `cfg.raum` bleibt ein Name;
  der Name eines eigenen Raums ist der Dateistamm.
- Das Pauspapier einer Rekonstruktion liegt daneben als `<name>.pauspapier`:
  Kennung `b"PAUS1"`, `uint32` Anzahl, dann `float32`-Paare (x, y) in Metern,
  Weltframe des Raums. Gelesen und geschrieben mit `struct`/`array`. Höchstens
  200 000 Punkte (~1.6 MB). Fehlt die Datei, gibt es kein Pauspapier — kein
  Fehler.

---

## 2 Bearbeitung (`welt/bearbeitung.py`, ohne Qt)

### Schlüssel und Auswahl

Ein Element wird über einen Schlüssel angesprochen: `("wand", i)`,
`("block", i)`, `("tag", i)`, `("start",)`. Eine Auswahl ist ein `frozenset`
solcher Schlüssel. Indizes beziehen sich auf den `Raum`, aus dem sie stammen;
`loesche` gibt deshalb den neuen Raum **und** die leere Auswahl zurück.

### Operationen (jede gibt einen neuen `Raum` zurück)

```python
verschiebe(raum, auswahl, dx, dy)
drehe(raum, auswahl, grad, um=None)        # um: (x, y); None = Mitte der Auswahl
skaliere(raum, auswahl, fx, fy, fz, um=None)
dupliziere(raum, auswahl) -> (raum, neue_auswahl)     # Kopie 0.5 m nach rechts oben
loesche(raum, auswahl) -> (raum, frozenset())
neue_wand(raum, x1, y1, x2, y2) -> (raum, schluessel)
neuer_block(raum, x, y, breite, tiefe, hoehe=0.75, name=None) -> (raum, schluessel)
neuer_tag(raum, x, y, grad=0.0) -> (raum, schluessel)  # id = kleinste freie Nummer ab 1
setze_start(raum, x, y, grad)
setze_feld(raum, schluessel, feld, wert)                # Zahlenfelder der Eigenschaften
mitte(raum, auswahl) -> (x, y)
```

- `drehe`: eine Wand dreht ihre Endpunkte um den Drehpunkt; ein Block dreht
  seine Mitte um den Drehpunkt und addiert `grad` zu `drehung`; Tag und Start
  drehen Lage und Blick.
- `skaliere`: Wände skalieren ihre Endpunkte in der Ebene um den Drehpunkt
  (`fz` ohne Wirkung); Blöcke skalieren Mitte um den Drehpunkt und Grösse
  (`breite·fx`, `tiefe·fy`, `hoehe·fz`); Tags und Start nur die Lage. Grössen
  bleiben ≥ 0.05 m.
- Blocknamen: `neuer_block` ohne Namen vergibt „Block 1", „Block 2", …
  (kleinste freie Nummer).

### Einrasten und Fang

`raste(wert, raster)` rundet; Vorgaben **0.05 m** für Lagen, **5°** für Winkel.
Beim Ziehen mit `Ctrl` (die Sicht übergibt `frei=True`) entfällt das Rasten.
Wandenden **fangen** sich an anderen Wandenden innerhalb **0.10 m**
(`fange_ende(raum, x, y, ausser=schluessel)`), damit Ecken schliessen.

### Treffertest

`treffer(raum, x, y, toleranz)` gibt den nächsten Schlüssel oder `None`: Wände
über den Abstand zur Strecke (≤ Toleranz + halbe Dicke), Blöcke über
Punkt-im-gedrehten-Rechteck (plus Toleranz), Tags und Start über den Radius
(0.15 m + Toleranz). Bei mehreren Treffern gewinnt der kleinere Abstand; bei
Gleichstand Start > Tag > Block > Wand (das Kleinere liegt oben).
`im_rahmen(raum, x1, y1, x2, y2)` liefert alle Schlüssel, deren Mitte im
Rechteck liegt (Rahmenauswahl).

### Modus — die Blender-Tasten als Zustandsautomat

```python
class Modus:
    RUHE, BEWEGEN, DREHEN, SKALIEREN
    def beginne(self, art, raum, auswahl, zeiger)   # zeiger: (x, y) Meter auf dem Boden
    def zeiger(self, x, y, frei=False)              # Mausbewegung -> Vorschau
    def taste(self, name)                           # "x"/"y"/"z", Ziffern, ".", "-", Backspace
    def vorschau(self) -> Raum
    def bestaetige(self) -> Raum                    # zurueck in RUHE
    def abbruch(self) -> Raum                       # der Raum von beginne()
```

- **BEWEGEN**: Versatz = Zeiger − Zeiger beim Beginn; Achssperre `X`/`Y` nullt
  die andere Komponente, `Z` ist hier ohne Wirkung. Getippte Zahl gilt entlang
  der gesperrten Achse (ohne Sperre: entlang x). Gerastet auf 0.05 m, mit
  `frei` nicht.
- **DREHEN**: Winkel = Winkel(Zeiger − Drehpunkt) − Winkel beim Beginn,
  gerastet auf 5°; getippte Zahl = Grad. Drehpunkt = `mitte(raum, auswahl)`.
- **SKALIEREN**: Faktor = |Zeiger − Drehpunkt| / |Zeiger beim Beginn −
  Drehpunkt|, gleichmässig in x und y; `X` nur `fx`, `Y` nur `fy`, `Z` nur
  `fz` (Höhe). Getippte Zahl = Faktor. Gerastet auf 0.05.
- Eine zweite Achstaste hebt die Sperre auf; `Backspace` löscht die Zahl.
- Die Sicht liefert nur Tasten und Zeiger in Metern; der Automat kennt keine
  Pixel. So arbeiten 2D und 3D identisch, und der Automat ist ohne Fenster
  testbar (`G X 1.5 Enter` als Tastenfolge).

### Verlauf

`Verlauf(grenze=200)`: `merke(raum)`, `zurueck() -> Raum | None`,
`vor() -> Raum | None`, `aktuell`. Jede **bestätigte** Änderung ist ein
Schnappschuss; während eines Ziehens oder eines offenen Modus entsteht keiner.
Ein `merke` nach `zurueck` verwirft die Vor-Schritte.

### Prüfung

`pruefe(raum) -> list[str]`: Start in einer Wand oder einem Block (über
`kollision.hindernis_bei`), Blöcke mit einer Kante < 0.05 m, Wände der Länge
< 0.05 m, doppelte Tag-Nummern, Tags in einem Block. Der Editor zeigt die
Liste live. Ein Start im Hindernis verhindert das Speichern **nicht**, aber
den Start des Laufs (Abschnitt 7).

---

## 3 Der Tab „Raumeditor" (`gui/raumeditor/`)

### Schnittstelle zu `app.py`

Dieselbe wie heute `UebungsraumView`, damit Startknopf, die Invariante
„genau ein Lauf" und die Spur nach dem Lauf unverändert verdrahtet bleiben:

| Signal / Methode | Bedeutung |
|---|---|
| `meldung(str)` | Statuszeile |
| `config_gespeichert(object)` | Raum/Start in die Konfiguration übernommen |
| `start_gewuenscht()` | Startknopf; `app.py` erzwingt `mujoco`/`sim` und startet über den Editor |
| `setze_laeuft(bool)` | Knopf zeigt Start/Stopp |
| `setze_arbeitsordner(pfad)`, `setze_config(cfg)` | wie heute |
| `waehle_raum(name)` | Raum nach Name laden (Vorlage oder eigener) |
| `raum()`, `raumname()`, `startpose()` | für Umgebung des Laufs und Übungsfenster |
| `lade(lauf_verzeichnis)` | Spur und Anstösse nach dem Lauf einzeichnen |

Ein Test hält diese Schnittstelle fest.

### Aufbau

Links eine Werkzeugleiste, in der Mitte die Sicht mit dem Umschalter
**2D | 3D** (auch `Tab`), rechts Elementliste, Eigenschaften, Hinweise; unten
der Knopf „▶ Offene Datei starten" / „■ Stopp" wie heute.

**Werkzeuge**: Auswählen · Wand · Block · Tag · Start. Datei: Neu, Vorlage
laden…, Öffnen…, Speichern (`Ctrl+S`), Speichern unter…, Rekonstruieren…
(Etappe 3). Ein Stern im Tab-Titel zeigt ungespeicherte Änderungen.

- **Wand**: Klick setzt den Anfang, jeder weitere Klick schliesst eine Wand ab
  und beginnt die nächste; `Esc` oder rechte Maustaste beendet die Kette.
  Wandenden fangen sich (Abschnitt 2).
- **Block**: Rechteck aufziehen (Höhe 0.75 m, Name automatisch).
- **Tag**: Klick setzt einen Tag mit der nächsten freien Nummer, Blick 0°.
- **Start**: Klick setzt die Lage, Ziehen beim Setzen dreht den Blick.

**Griffe in 2D** am ausgewählten Element: Fläche ziehen bewegt; Wände haben
ziehbare Endpunkte; Blöcke Eckgriffe (Grösse, Seitenverhältnis frei) und
einen Drehring; Tag und Start einen Drehring. Rahmen aufziehen im leeren
Bereich wählt mehrere; `Shift`-Klick ergänzt; Klick ins Leere leert.

**Tasten** (beide Sichten):

| Taste | Wirkung |
|---|---|
| `G` / `R` / `S` | Bewegen / Drehen / Skalieren der Auswahl (Modus) |
| `X` / `Y` / `Z` | Achssperre im Modus |
| Ziffern, `.`, `-`, `Backspace` | Zahleneingabe im Modus |
| `Enter` / Linksklick | bestätigen; `Esc` / Rechtsklick abbrechen |
| `Shift+D` | duplizieren (und gleich Bewegen) |
| `Entf` | löschen |
| `Ctrl+Z` / `Ctrl+Y` | zurück / vor |
| `A` | alles auswählen, `Alt+A` nichts |
| `Home` | alles zeigen |
| `Tab` | 2D ↔ 3D |
| `Ctrl+S` | speichern |

**Eigenschaften**: Zahlenfelder je Elementart — Wand: `x1 y1 x2 y2`; Block:
Name, Mitte, Breite, Tiefe, Höhe, Drehung; Tag: Nummer, Lage, Blick, Höhe;
Start: Lage, Blick; ohne Auswahl der Raum: Name, Beschreibung, Wanddicke,
Wandhöhe. Jede Eingabe geht durch `setze_feld` und den Verlauf.

**Elementliste**: alle Elemente mit Art und Name/Nummer; Klick wählt,
Doppelklick auf einen Block benennt um.

**Hinweise**: das Ergebnis von `pruefe(raum)`, nach jeder Änderung.

**Lauf**: der Startknopf startet den Raum, der offen ist. Ungespeicherte
Änderungen werden vorher gespeichert; ein Raum ohne Namen fragt nach einem
(Dialog, Ablage in `raeume/`). Der Lauf läuft im Übungsfenster; danach ruft
`app.py` `lade(lauf)`, und der Editor zeichnet Spur und Anstösse — in 2D und 3D.
Während ein Lauf läuft, ist der Editor bedienbar, aber der Startknopf heisst
„Stopp" (wie heute).

### 2D-Sicht (`sicht2d.py`)

QPainter-Widget mit Zoom (Rad, um den Zeiger) und Schwenken (mittlere Taste),
5-cm-Raster (fein) und 1-m-Raster (kräftig), Wände als Balken mit Dicke,
Blöcke als gedrehte Rechtecke mit Namen, Tags als Quadrat mit Pfeil und
Nummer, Start als Kreis (`ROBOTER_RADIUS_M`) mit Blickstrich, das Pauspapier
als kleine graue Punkte darunter, Spur gepunktet, Anstösse als Kreuz. Auswahl
in Akzentfarbe mit Griffen. Farben nur aus `theme.py`.

Das Zeichnen der Raumgeometrie wandert in **`gui/raumzeichnung.py`**
(`zeichne_raum(maler, raum, meter_zu_schirm, palette)`,
`zeichne_spur(...)`, `zeichne_spot(...)`), das auch `raumplot.py` (Übungsfenster,
Live-Spur) benutzt — sonst lernten zwei Zeichner die Drehung getrennt.
`raumplot.py` bleibt für das Übungsfenster; `views/uebungsraum.py` entfällt.

---

## 4 Die 3D-Sicht (`gui/raumeditor/sicht3d.py`)

`QOpenGLWidget` + PyOpenGL. Anforderung **OpenGL 3.3 Core**, MSAA 4×,
Tiefenpuffer 24 Bit (`QSurfaceFormat` am Widget, vor dem ersten `show`).
PyOpenGL wird **nur hier** und erst beim Erzeugen der Sicht importiert; fehlt
das Paket, gilt der Rückfall.

**Gezeichnet wird** mit einem Shaderprogramm (Lambert + Umgebungslicht,
Farbe je Element): Boden als 1-m-Raster, Wände und Blöcke als Kästen
(Theme-Farben `flaeche`/`rand`, Auswahl in `akzent` plus Kantenlinien), Tags
als Tafeln 0.15 × 0.15 m mit Blickpfeil, Spot am Start als Körperkasten
1.1 × 0.5 × 0.2 m mit Oberkante 0.6 m und Blickpfeil, das Pauspapier als
Punkte (`GL_POINTS`, 2 px), die Spur als Linienzug 1 cm über dem Boden,
Anstösse als Kreuze. Beschriftungen (Blocknamen, Tag-Nummern) malt QPainter
nach dem GL-Bild darüber (`paintGL` → `QPainter(self)` nach `glFlush`).

**Kamera**: Orbit um ein Ziel (anfangs Raummitte, Höhe 0) — linke Taste dreht
(Azimut/Elevation, Elevation 5°–89°), mittlere oder rechte Taste schwenkt in
der Bodenebene, Rad zoomt (Abstand 1–60 m), `Home` rahmt alles.
Perspektive 50° vertikal.

**Auswahl per Klick**: ein Farb-ID-Durchgang in einen Offscreen-Framebuffer
(jedes Element eine eigene Farbe, 24 Bit Index), ein Pixel lesen — kein
eigener Strahl gegen Kästen. Für den Modus wird der Mausstrahl mit der
Bodenebene `z = 0` geschnitten; ab da ist es dieselbe Meterbewegung wie in 2D.
`Shift`-Klick ergänzt die Auswahl; Rahmenauswahl gibt es in 3D nicht.

**Geometrie** wird bei jeder Raumänderung als ein Vertex-Puffer neu gebaut
(ein paar hundert Kästen — unkritisch); das Pauspapier einmal je Datei.

**Rückfall**: scheitert der Kontext (`context().isValid()` falsch, Version
< 3.3, PyOpenGL fehlt, Shader kompiliert nicht), zeigt die Sicht statt des
Bilds eine Tafel: Grund, und der Hinweis „`QT_OPENGL=software` setzen, dann
spotlab neu starten". Der Umschalter 2D | 3D bleibt grau. Alles andere
funktioniert. Kein schwarzes Fenster.

**Abhängigkeit**: `PyOpenGL>=3.1,<4` im Extra `[gui]`.

---

## 5 Sim, Gitter, Puppe

Vier Stellen, dieselbe Drehung, ein Prinzip: **ein Punkt wird in den Rahmen
des Blocks gedreht, danach rechnet alles wie bisher achsparallel.**

- `welt/kollision.py`: `hindernis_bei` prüft Wände als Strecken mit Abstand
  `radius + wand_dicke/2` und Blöcke über den gedrehten Punkt
  (`_im_blockrahmen(block, x, y)`), dann Punkt-Rechteck-Abstand wie bisher.
  Die Sichtlinie (`sichtlinie`) schneidet gegen die vier gedrehten Kanten des
  Blocks (`block_kanten(block)`), Wände wie bisher.
- `welt/wahrnehmung.py`: `_abstaende` vektorisiert — Wände minus halbe Dicke
  (auf ≥ 0 begrenzt), Blöcke über gedrehte Koordinatenfelder; die
  Bekannt-Maske über dieselben Kanten.
- `backends/mujoco.py::welt_aus_raum`: eine Wand wird ein Kasten mit ihrer
  Länge, `wand_dicke`, `wand_hoehe` **und Drehung** `atan2(dy, dx)`; ein Block
  ein Kasten `breite × tiefe × hoehe` mit `drehung`; ein Tag eine Marke auf
  seiner `hoehe`. Die Konstanten `WAND_HOEHE_M`, `WAND_DICKE_M`,
  `HINDERNIS_HOEHE_M`, `TAG_HOEHE_M` entfallen aus `mujoco.py` — die Werte
  stehen im Raum.
- matura-spot `spotsim/puppe.py`: `Quader` bekommt `yaw: float = 0.0`,
  `bau_modell` setzt `b.quat = _quat_yaw(q.yaw)`; `PUPPE_FASSUNG = 3` in
  beiden Repos. Test: ein um 45° gedrehter Kasten kollidiert dort, wo seine
  gedrehte Ecke ist, und nicht dort, wo seine Hülle wäre; ein Tag hinter ihm
  ist unsichtbar.

Übungsfenster, 2D-Sim, Tempo, Antwort, Aufzeichnung bleiben; `angestossen`
nennt weiter den Blocknamen bzw. „Wand".

---

## 6 Rekonstruktion (`maps/rekonstruktion.py`)

Darf bosdyn und numpy wie `maps/` heute. Die GUI ruft sie in einem
Arbeiter-`QThread` (Muster `MapsView._worker`) und bekommt `Ergebnis(raum,
pauspapier, bericht)` zurück — sie sieht nie ein Protobuf.

**Eingabe**: `rekonstruiere(kartenordner, einstellungen) -> Ergebnis`.
Ein Kartenordner aus `karten/` oder ein beliebiger Ordner mit `graph` und
`waypoint_snapshots/`.

```python
@dataclass(frozen=True)
class Einstellungen:
    band: tuple = (0.3, 1.6)        # Meter über dem Boden
    zelle: float = 0.05             # Belegungsgitter
    mindestens_punkte: int = 3      # je Zelle
    inlier: float = 0.06            # RANSAC-Abstand
    min_laenge: float = 0.5         # Segmente darunter fallen weg
    luecke: float = 0.4             # Segment wird an grösseren Lücken geteilt
    ausrichten: bool = True         # häufigste Wandrichtung -> x-Achse
    schlauch_breite: float = 2.0    # Notnagel ohne Wolken
    pauspapier_max: int = 200_000
```

**Schritte**

1. Wegpunktposen im Seed-Rahmen aus `graph.anchoring.anchors`
   (`seed_tform_waypoint`); fehlen Anker, über die Kantenkette wie
   `maps/geometry._aus_kette` — der Bericht sagt es.
2. Punktwolke je Schnappschuss in den Weltrahmen: Punkte `float32 × 3` aus
   `snapshot.point_cloud.data`; `odom_tform_cloud = get_a_tform_b(
   cloud.source.transforms_snapshot, ODOM, cloud.source.frame_name_sensor)`,
   `waypoint_tform_cloud = waypoint.waypoint_tform_ko · odom_tform_cloud`,
   `welt = seed_tform_waypoint · waypoint_tform_cloud` — die Kette aus
   `map_viewer/transformer.py`.
3. Bodenhöhe = 5. Perzentil aller z; behalten werden Punkte mit
   `boden + band[0] ≤ z ≤ boden + band[1]`.
4. Belegungsgitter mit `zelle`; belegt ab `mindestens_punkte`. Die Bandpunkte,
   auf `pauspapier_max` gleichmässig gedünnt, werden das Pauspapier.
5. Wände: RANSAC-Linien über die Mitten der belegten Zellen (Inlier ≤
   `inlier`, so lange, bis weniger als 20 Zellen übrig sind oder eine Linie
   weniger als 10 Inlier hat); jede Linie wird entlang ihrer Richtung an
   Lücken > `luecke` in Segmente geteilt — **so entstehen Türen**; Segmente
   < `min_laenge` fallen weg; kollineare Nachbarn (Winkel ≤ 5°, Abstand
   ≤ 0.2 m) werden verschmolzen. Endpunkte auf 1 cm gerundet.
6. Ausrichten: Histogramm der Segmentrichtungen modulo 90° (gewichtet mit der
   Länge), Drehung um den Hauptwinkel, danach liegt die häufigste Richtung
   auf x. Die Drehung wird auf Wände, Tags, Start **und** das Pauspapier
   angewandt; der Raum wird so verschoben, dass die Hülle bei (0.5, 0.5)
   beginnt.
7. Tags aus `graph.anchoring.objects` (`seed_tform_object`): Lage aus der
   Translation, `hoehe` = z − Boden, Blick aus der Normalen der Tag-Ebene
   nach der Fiducial-Rahmen-Definition des SDK (z-Achse aus der Tag-Fläche
   heraus) — die Zuordnung wird am Abnahmetest gegen die Katakomben-Karte
   geprüft, bevor sie als richtig gilt. Tags nur in Schnappschüssen:
   `seed_tform_waypoint · waypoint_tform_ko · odom_tform_object`.
8. Start = Pose des ersten Wegpunkts (x, y, Gieren).
9. Bericht: Wegpunkte, Schnappschüsse (gelesen/fehlend), Punkte gesamt und im
   Band, Zellen belegt, Linien gefunden, Segmente behalten/verworfen, Tags,
   Ausrichtwinkel, Quelle der Posen (Anker/Kette), Laufzeit.

**Notnagel ohne Wolken** (`schlauch(graph, breite)`): je Kante zwei Wände im
Abstand ±`breite/2` links und rechts der Kante; benachbarte Schlauchwände
werden nicht verschmolzen (das übernimmt der Editor). Wird genommen, wenn
keine Schnappschüsse Punkte tragen; der Bericht sagt es.

**Dialog** im Editor („Rekonstruieren…"): Karte wählen (Liste aus `karten/`
plus „Ordner wählen…"), die Einstellungen als Felder, „Vorschau" rechnet im
Thread (Knopf gesperrt, Fortschritt „Schnappschuss 37/107"), das Ergebnis
öffnet sich als neuer, ungespeicherter Raum mit Pauspapier; der Bericht steht
im Dialog. Ein zweiter Klick auf „Vorschau" ersetzt den Vorschlag.

---

## 7 Fehler

Meldungen sagen, was zu tun ist, und behaupten keine ungeprüfte Ursache.

- Kaputte Raumdatei → `SpotlabError` mit Datei und Feld (wie heute).
  Speichern scheitert → Meldung mit Pfad und Grund.
- Kein GL → Tafel mit Grund und dem `QT_OPENGL=software`-Hinweis; 2D bleibt.
- Rekonstruktion: ohne Anker → Kantenkette, Hinweis `HINWEIS_KETTE`; ohne
  Wolken → Schlauch, Hinweis; fehlende Schnappschüsse → Zahl im Bericht; kein
  `graph` → `SpotlabError` „Das ist kein Kartenordner: es fehlt die Datei
  `graph`."
- Lauf starten mit Start im Hindernis → abgelehnt, Meldung „Der Start steht in
  ‚Tisch'. Verschiebe ihn im Raumeditor." (aus `pruefe`).
- Lauf starten mit Raum ohne Namen → Dialog nach dem Namen; Abbruch bricht den
  Start ab.

---

## 8 Tests

**Ohne Qt** (der grösste Teil):

- `raum.py`: Rundreise Laden → Speichern → Laden für jede Vorlage; alte
  Schreibweise → Blöcke; `groesse` optional; `huelle`.
- `bearbeitung.py`: jede Operation mit Zahlenbeispielen (eine Wand um 90° um
  ihren Mittelpunkt, ein Block um 45° um einen fremden Punkt, Skalieren mit
  Achssperre), Rasten, Fang, `treffer` mit Vorrang, `im_rahmen`, `Verlauf`
  (Grenze, `merke` nach `zurueck`), `Modus` als Tastenfolgen (`G X 1.5 Enter`,
  `R 90 Enter`, `S Z 2 Enter`, `Esc`), `pruefe`.
- `kollision.py`, `wahrnehmung.py`: gedrehter Block (die Ecke trifft, die
  Hülle nicht), Wanddicke, Sichtlinie gegen gedrehte Kanten.
- `backends/mujoco.py`: `welt_aus_raum` mit Drehung (Naht-Test gegen
  `spotsim.puppe.Quader.yaw`); matura-spot: gedrehter Kasten in Kollision und
  Sicht, `PUPPE_FASSUNG = 3`.
- `maps/rekonstruktion.py`: **synthetische Karte** als Fixture — ein erzeugter
  `Graph` (sechs Wegpunkte, Anker, `waypoint_tform_ko`, ein Schnappschuss je
  Wegpunkt mit Punktwolke), die Wolken aus bekannten Wänden gesampelt (Gang
  4 × 2 m mit einer Tür von 0.9 m, ein Kasten, ein Tag); die Rekonstruktion
  findet die Wände auf 10 cm, die Türlücke, den Tag auf 10 cm und 10°;
  Schlauch ohne Wolken; Pauspapier-Rundreise.
- Abnahmetest gegen die echte Katakomben-Karte (`skipif`, wenn der Ordner
  fehlt): 31 Tags, mindestens 20 Wände, Laufzeit < 30 s.

**Qt offscreen**:

- Schnittstelle des Tabs zu `app.py` (Signale und Methoden vorhanden).
- 2D: synthetischer Klick wählt das richtige Element; Ziehen bewegt; Wandkette
  zeichnen; Zahlenfeld → Modell → Verlauf; Speichern → Datei → `raum_laden`.
- 3D: unter `offscreen` entsteht meist kein 3.3-Kontext — dann prüft der Test
  den **Rückfall** (Tafel sichtbar, Umschalter grau). Farb-ID-Picking und ein
  gerendertes Bild (Mitte des Bilds ist nicht Hintergrundfarbe) laufen nur, wo
  ein Kontext zustande kommt (`skip` mit Grund).
- Rekonstruktions-Dialog: Arbeiter liefert Ergebnis, Raum öffnet sich,
  Bericht steht.

**Grenzen als Tests**: kein `bosdyn`/`mujoco`/`spotsim` unter `gui/`
(besteht); `welt/` importiert nur Standardbibliothek (neu, per `ast`);
`OpenGL` wird unter `gui/` nur in `sicht3d.py` importiert (neu); Protobufs
(`bosdyn.api`) nur unter `maps/` und `backends/` (neu).

**Abnahme am Gerät** (`docs/ABNAHME.md`): einen rekonstruierten
Katakomben-Raum in 3D laufen lassen; die Blickrichtungen der Tags gegen die
echten Tags im Gang prüfen.

---

## 9 Etappen

1. **Bauen**: Raumformat v2 und `raum_speichern`, `bearbeitung.py`,
   `raumzeichnung.py`, Tab mit 2D-Sicht, Griffen, Tasten, Eigenschaften,
   Liste, Hinweisen; Drehung in `kollision`, `wahrnehmung`, `welt_aus_raum`
   und in der Puppe; Übungsraum-Tab ersetzt; README, CLAUDE.md, ABNAHME.
   Ergebnis: Räume bauen, speichern, darin fahren — 2D und 3D-Sim.
2. **3D-Sicht**: `sicht3d.py`, Rückfall, PyOpenGL im Extra, Picking, Spur.
3. **Rekonstruieren**: `maps/rekonstruktion.py`, Dialog, Pauspapier in beiden
   Sichten, synthetische Fixture, Abnahmetest.

Jede Etappe bekommt einen eigenen Implementierungsplan, endet mit grüner Suite
und Merge.

## 10 Neue Regeln für CLAUDE.md

- `welt/` bleibt Standardbibliothek — der Grund, warum die GUI es importieren
  darf; `tests/test_welt_grenzen.py` hält das fest.
- PyOpenGL nur in `gui/raumeditor/sicht3d.py`, verzögert importiert; ohne das
  Paket läuft der Editor in 2D.
- Protobufs nur in `maps/` und `backends/`; die GUI bekommt `Raum`, Punkte
  und Bericht.
- Der Editor arbeitet auf unveränderlichen Räumen; Undo ist eine Liste von
  Schnappschüssen, kein Kommando-Muster.
