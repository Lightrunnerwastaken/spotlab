# Höhe, Rampen und Treppen — Räume mit Ebenen, Sim mit Gefälle, Treppen erkennen

Entwurf vom 06.09.2026. Entscheidungen des Autors im Gespräch:

- **Treppengang: C** — die Puppe spielt jetzt den ebenen Gang ab, Körperhöhe
  und Neigung folgen dem Boden, der Lauf sagt „Treppengang nicht gemessen";
  B6 (Treppe hoch, rückwärts runter) kommt in den Messfahrt-Ablauf, damit der
  Tausch gegen die Messung vorbereitet ist.
- **Ebenen in 2D: A** — abgeleitet aus den Bodenhöhen des Raums, keine
  benannten Stockwerke. Was auf einer anderen Ebene liegt, wird blass gezeichnet.
- **Gefälle der Katakomben: A** — der Gang fällt wirklich ab; die
  Rekonstruktion baut Rampen aus den Wegpunkthöhen.
- **Falsch herum auf der Treppe: A** — der Sim verweigert (vorwärts hoch,
  rückwärts runter), Ereignis `treppe_verweigert`; was der echte Spot tut, ist
  Abnahmepunkt A25.
- **Weg 1** — ein Element `Boden`, Höhe je Element, eine Höhenfunktion in
  `welt/`; kein Höhenraster, keine Stockwerke mit Verbindern.

## Befunde, die den Entwurf tragen

- **Die Katakomben-Karte** (`Spot Projects\maps\map_catacombs_01`) spannt
  2.4 m Höhe. Sechs Kanten tragen `annotations.stairs.state ==
  ANNOTATION_STATE_SET`; die Treppe steigt 1.30 m über 1.6 m Grundriss
  (~39°) und wurde hoch und wieder hinunter gelaufen. Daneben fällt der Gang
  sanft von +0.5 auf −1.8 m über rund 40 Wegpunkte. Die Kanten tragen
  `direction_constraint` (hier NONE, einmal NO_TURN) und keine
  Mobility-Parameter.
- **Der echte Spot** kennt `MobilityParams.stairs_mode` (OFF, ON, AUTO,
  PROHIBITED) und `stair_hint`; erkannte Treppen führt er als Weltobjekt mit
  `staircase_properties` (`StraightStaircase`: `from_ko_tform_stairs`,
  `stairs`, `bottom_landing`, `top_landing`; `StaircaseWithLandings`). Das ist
  derselbe Kanal wie `spot.world_objects()`. Vorwärts hoch, rückwärts runter
  ist die Regel von Boston Dynamics.
- **Die Puppe** (`spotsim/puppe.py`, Fassung 3) kennt nur die Bodenebene
  `floor` bei z = 0, setzt die Körperhöhe aus den Gelenken (tiefster Fuss auf
  dem Boden) und spielt gemessene ebene Gänge ab. Ihr Tiefengitter
  (`spotsim/local_grid.py::belegung_aus_tiefe`) hält alles zwischen 5 cm und
  1.2 m ÜBER z = 0 für ein Hindernis — auf einer Treppe wäre jede Stufe eine
  Wand.
- **Der 2D-Sim** führt `z` und `pitch` schon: `State.z`, `State.pitch`,
  `zustand.jsonl` schreibt `z`, `roll`, `pitch` in jeder Zeile. Der Sim setzt
  dort heute die konstante Standhöhe und 0. `pose` bleibt `(x, y, yaw)`.

## Ziel

Ein Schüler baut ein Zimmer mit einem Podest, einer Rampe oder einer Treppe,
sieht es in 2D (je Ebene) und 3D, fährt darin mit `backend="sim"` und
`backend="mujoco"`, und Spot folgt dem Boden — hinauf, hinunter, mit Neigung.
Ein Programm findet die Treppe mit `spot.stairs()`, steigt vorwärts hinauf und
rückwärts hinab; nimmt es sie falsch herum, bleibt Spot stehen und der Lauf sagt
warum. Der Autor rekonstruiert die Katakomben samt Treppe und Gefälle aus der
Karte und lässt die Sim den Gang hinunter und die Treppe hinauf fahren.

## Nicht-Ziele

- Kein freies Gelände, keine Höhenraster, keine Zylinder oder Keile jenseits
  des gedrehten Rechtecks; Böden sind Rechtecke mit linearem Anstieg.
- Kein gemessener Treppengang in dieser Stufe — die Puppe spielt den ebenen
  Gang ab, Füsse tauchen auf Stufen ein, und der Lauf sagt es (`treppengang:
  "nicht gemessen"`). B6 liefert die Messung später.
- Keine Physik: Rutschen an Rampen, Stolpern an Stufen, Kippen an Kanten gibt
  es nicht. Eine Absturzkante hält wie eine Wand.
- Keine Brücken in MuJoCo: ein Podest füllt den Raum bis zum tiefsten Boden
  aus, damit seine Kante eine sichtbare Wand ist; ein Gang UNTER einem Podest
  ist in der 3D-Welt zu, in der 2D-Rechnung frei. Steht in der Doku.
- Keine Stufen aus der Punktwolke: Stufenzahl aus Anstieg / 0.17 m.
- Keine Decke, keine Wendeltreppe, keine Treppe mit Zwischenpodest als ein
  Element (zwei Treppen und ein Podest).
- Keine Treppen-Wegpunkte für GraphNav; die autonome Fahrt am Roboter bleibt
  unverändert (der Roboter folgt seinen eigenen Kantenannotationen).

---

## 1 Raumformat v3 (`welt/raum.py`)

`welt/` bleibt Standardbibliothek. Alle Elemente unveränderlich.

```python
@dataclass(frozen=True)
class Wand:
    x1: float; y1: float; x2: float; y2: float
    z: float = 0.0            # Unterkante ueber dem Grundboden
    # __iter__ liefert weiterhin (x1, y1, x2, y2) -- alle Aufrufer entpacken vier Werte

@dataclass(frozen=True)
class Block:
    name: str; x: float; y: float; breite: float; tiefe: float
    hoehe: float = BLOCK_HOEHE_M; drehung: float = 0.0
    z: float = 0.0            # Unterkante; steht auf dem Boden, wenn z == Bodenhoehe

@dataclass(frozen=True)
class RaumTag:
    id: int; x: float; y: float; grad: float
    hoehe: float = TAG_HOEHE_M
    z: float = 0.0            # der Tag haengt bei z + hoehe

@dataclass(frozen=True)
class Boden:
    """Ein begehbares Rechteck: Podest (anstieg 0), Rampe (anstieg, keine
    Stufen) oder Treppe (anstieg und stufen). Um die Hochachse gedreht wie
    Block; entlang der EIGENEN x-Achse steigt er von z (Kante bei -breite/2)
    auf z + anstieg (Kante bei +breite/2)."""
    name: str; x: float; y: float; breite: float; tiefe: float
    z: float = 0.0; anstieg: float = 0.0; stufen: int = 0; drehung: float = 0.0

    def ecken(self): ...      # wie Block
    def lokal(self, px, py): ...
    def hoehe_lokal(self, lx):
        """Bodenhoehe an lokaler x-Position, glatt (auch bei Stufen)."""
        return self.z + self.anstieg * (lx / self.breite + 0.5)
    def stufe_lokal(self, lx):
        """Bodenhoehe als Stufe: die Trittflaeche, auf der lx liegt (stufen > 0)."""
    @property
    def art(self):            # "podest" | "rampe" | "treppe"
    @property
    def neigung_grad(self):   # atan(anstieg / breite), 0 fuer Podest
    @property
    def z_oben(self):         # z + anstieg

@dataclass(frozen=True)
class Raum:
    ...                       # wie v2, dazu:
    boeden: tuple = ()        # Boden, ...
```

`Raum.start` bleibt `(x, y, grad)`; die Starthöhe folgt aus `boden_bei`.
`huelle()` nimmt die Ecken der Böden dazu. `MAX_STUFE_M = 0.25` und
`STUFE_VORGABE_M = 0.17` (Steigung einer Normstufe, Annahme) wohnen in
`welt/raum.py`, weil Kollision, Gitter, Editor, Rekonstruktion und Puppe-Welt
dieselbe Zahl brauchen.

### Datei

```toml
[raum]
name = "Treppe"
start = [1.0, 1.5, 0.0]
waende = [
    [0.0, 0.0, 6.0, 0.0],            # vier Werte: z = 0
    [0.0, 3.0, 6.0, 3.0, 1.2],       # fuenf Werte: z = 1.2 (Wand auf dem Podest)
]

[[block]]
name    = "Kiste"
mitte   = [4.5, 1.5]
groesse = [0.6, 0.6, 0.4]
drehung = 0.0
z       = 1.2                        # fehlt -> 0

[[tag]]
id    = 3
pose  = [5.9, 1.5, 180.0]
hoehe = 0.3
z     = 1.2                          # fehlt -> 0

[[boden]]
name    = "Podest"
mitte   = [5.0, 1.5]
groesse = [2.0, 3.0]
z       = 1.2
anstieg = 0.0
stufen  = 0
drehung = 0.0

[[boden]]
name    = "Treppe"
mitte   = [3.0, 1.5]
groesse = [2.0, 1.2]                 # 2 m lang (Anstiegsrichtung), 1.2 m breit
z       = 0.0
anstieg = 1.2
stufen  = 7
drehung = 0.0
```

Lesen: v1 (`hindernisse`), v2 und v3; fehlende `z` sind 0, `boeden` fehlt →
leer. Schreiben: `z` bei Wänden nur als fünfter Wert, wenn ≠ 0; `z` bei Block
und Tag nur, wenn ≠ 0; `[[boden]]`-Tabellen nur, wenn es Böden gibt. Ein Raum
ohne Höhe sieht gespeichert genau aus wie in v2.

## 2 Höhenfunktion (`welt/hoehe.py`, Standardbibliothek)

```python
MAX_STUFE_M      # re-exportiert aus raum.py
KOERPER_BAND_M = (0.10, 0.70)      # was den Koerper trifft, ueber dem Boden unter ihm
TREPPE_SICHT_M = 1.5               # bis hierhin gilt eine Treppe als "vor dem Roboter"
TREPPE_WINKEL_GRAD = 45.0          # Achse der Treppe gegen die Fahrtrichtung

def boden_bei(raum, x, y, z_nahe=0.0, ohne=None):
    """(z, boden | None): der Boden unter dem Punkt.

    Kandidaten: der Grundboden (0.0) und jeder Boden, der den Punkt enthaelt
    (in seinem Rahmen, glatt nach hoehe_lokal). Gewaehlt wird der mit der
    kleinsten |z - z_nahe|; bei Gleichstand der hoehere. `ohne` schliesst
    einen Boden aus (fuer Kanten: was liegt NEBEN diesem Boden?).
    """

def neigung_bei(raum, x, y, z_nahe=0.0):
    """(dz/dx, dz/dy) im Weltframe des Bodens unter dem Punkt; (0, 0) auf Podest und Grund."""

def nick_grad(raum, x, y, yaw, z_nahe=0.0):
    """Nickwinkel in Grad entlang der Fahrtrichtung (positiv = Nase hoch), aus neigung_bei."""

def ebenen(raum):
    """Sortierte, auf 0.1 m gerundete Bodenhoehen: 0.0, jedes z und jedes z_oben der Boeden."""

def hoehenband(element, raum):
    """(unten, oben) eines Elements: Wand z..z+wand_hoehe, Block z..z+hoehe,
    Tag z+hoehe (Punkt), Boden min(z, z_oben)..max(z, z_oben)."""

def auf_ebene(element, raum, ebene, toleranz=0.3):
    """Schneidet das Hoehenband die Ebene (± toleranz)? Boeden: beruehrt ihr Band die Ebene."""

def klippen(raum, schritt=0.05):
    """[(x1, y1, x2, y2)]: Kantenstuecke, an denen der Boden um mehr als MAX_STUFE_M
    springt. Je Boden werden die vier Kanten in `schritt`-Stuecken abgetastet;
    innen gilt hoehe_lokal, aussen boden_bei(..., ohne=boden) bei der eigenen
    Hoehe als z_nahe. |innen - aussen| > MAX_STUFE_M -> das Stueck ist Klippe.
    Die Rampe hat so keine Klippe am Fuss und keine am Kopf, aber an den Seiten,
    sobald sie hoeher als eine Stufe ueber dem Nachbarboden liegt."""

def treppe_vor(raum, x, y, grad, z_nahe=0.0):
    """Die naechste Treppe, deren Fusskante oder Kopfkante innerhalb TREPPE_SICHT_M
    vor dem Roboter liegt: (boden, richtung, abstand, peilung_grad, achsenwinkel_grad)
    oder None. `richtung` ist "auf" (der Roboter steht am Fuss) oder "ab" (am Kopf);
    `achsenwinkel_grad` der Winkel zwischen Fahrtrichtung und Bergauf-Achse (0 = die
    Nase zeigt bergauf, 180 = bergab). Sichtlinie muss frei sein (kollision.sicht_frei)."""

def treppe_erlaubt(richtung, vx, achsenwinkel_grad):
    """Die Regel: aufwaerts nur vorwaerts mit Nase bergauf (vx > 0 und Winkel <= 45),
    abwaerts nur rueckwaerts mit Nase bergauf (vx < 0 und Winkel <= 45).
    Gibt (erlaubt, verlangt) mit verlangt in {"vorwärts hoch", "rückwärts runter"}."""
```

Böden dürfen sich überlappen (Brücke): `boden_bei` mit `z_nahe` löst das, und
ein Roboter, der von unten kommt, bleibt unten. Die einzige Stelle, die das
NICHT kann, ist die MuJoCo-Welt (Nicht-Ziel).

## 3 Kollision und Gitter mit Höhe

**Die Regel:** ein Hindernis ist ein Höhensprung über `MAX_STUFE_M`. Sie steht
in `welt/hoehe.py` (Klippen) und `welt/kollision.py` (Körperband) und gilt
wörtlich auch für das Tiefengitter der Puppe (§ 4).

`kollision.hindernis_bei(raum, x, y, radius, z=None)`: ohne `z` wie bisher
(alte Aufrufer, Tests); mit `z` zählt eine Wand oder ein Block nur, wenn sein
Höhenband `[z + 0.10, z + 0.70]` schneidet. Dazu Klippen: liegt eine
Klippenkante näher als `radius`, ist das Hindernis `"Kante"`. `bewege(raum,
von, nach, z=None)` führt die Höhe mit: nach jedem Teilschritt `boden_bei` mit
der bisherigen Höhe als `z_nahe`; springt der Boden um mehr als eine Stufe
(auch das ist eine Klippe, nur aus der Innensicht), bleibt Spot am letzten
guten Punkt. Rückgabe wird `((x, y, yaw), z, hindernis)`. `sicht_frei` bleibt
zweidimensional (ein Podest verdeckt keinen Tag; Annahme, im Bericht).

`wahrnehmung.abstandsgitter(raum, pose, z=0.0)`: Wände und Blöcke wie bisher,
aber nur die mit schneidendem Band; Klippen als Strecken mit Dicke 0 dazu. Die
Klippen werden je Raum einmal berechnet (`klippen` ist reine Geometrie ohne
Pose) — der Sim hält sie in `_klippen`, der Editor braucht sie nicht.
`sichtbare_tags` prüft zusätzlich, dass der Tag nicht mehr als 1.5 m über oder
unter dem Roboter hängt (Annahme; A22 misst die Reichweite ohnehin).

## 4 Fahrt in beiden Sims

### 2D (`backends/sim.py`)

Neue Felder `self._z` (Boden unter der Körpermitte) und `self._nick_grad`.
Beim Verbinden: `self._z, _ = boden_bei(raum, x, y, 0.0)` am Start.
`_fortschreiben` ruft `bewege(..., z=self._z)` und übernimmt die Höhe; danach
`self._nick_grad = nick_grad(...)`. `frame_tree_snapshot` schreibt
`position.z = self._z + self._hoehe` und die Rotation aus Yaw UND Nick (Quaternion
`yaw ∘ pitch`, Nick um die Körper-y-Achse, Vorzeichen so, dass `State.pitch` bei
Nase hoch positiv ist — wie `rpy_aus` es liest). `robot_state` setzt
`foot_position_rt_body.z = -self._hoehe` weiter (die Füsse stehen auf dem
Boden, der Körper ist um `_hoehe` darüber). `_hoehenversatz` aus
`stand(height=…)` addiert wie bisher.

Die Treppenregel in `_bewege_gegen_welt` (2D) und in
`MujocoBackend._bewege_gegen_welt` über eine gemeinsame Hilfe
`SimBackend._pruefe_treppe(von, nach)`: liegt `treppe_vor(...)` und tritt der
Schritt in die Treppe ein (Fusskante oder Kopfkante wird überschritten), gilt
`treppe_erlaubt(richtung, vx, achsenwinkel)`. Verboten → Pose bleibt am
letzten guten Punkt, einmal je Flanke (wie `angestossen`) das Ereignis
`treppe_verweigert` mit `x, y, treppe, richtung, verlangt`, und `_meldung`
merkt sich den Text `„Treppe {name}: {richtung} geht nur {verlangt}."`, den
`command_feedback` als Status liefert. Mit `treppen = "aus"` in der
Konfiguration sind Treppen und Rampen Klippen (`klippen(raum, alles=True)`),
und `treppe_vor` liefert trotzdem — `stairs()` sieht sie, fahren darf man nicht.

`bericht()` bekommt `"hoehe": {"boeden": n, "treppen": n, "rampen": n,
"ebenen": [...], "treppengang": "nicht gemessen" | "eben"}`; das
`verbunden`-Ereignis bekommt `treppengang` als eigenes Feld, wenn der Raum
Treppen hat.

### Treppenmodus (`config.py`, `backends/mobility.py`)

`Limits.treppen: str = "auto"` (`"auto" | "aus"`), in `config.toml` unter
`[limits] treppen = "auto"` — ein Sicherheitswert wie die Deckel, deshalb dort
(beim Bau so entschieden; die Spec sagte `[sicherheit]`). Ein anderer Wert
ist `ConfigBroken`. `mobility.mit_grenze(limits)` liest `limits.treppen` und setzt
`stairs_mode = STAIRS_MODE_AUTO` bzw. `STAIRS_MODE_OFF`. Alle drei Wege
(`walk`, `move`, autonome Fahrt) nehmen `mit_grenze`, also gilt der Schalter
überall. Kein `stair_hint`: das ist eine Angabe für einen konkreten Schritt,
die der Roboter selbst besser weiss.

### MuJoCo (`backends/mujoco.py`, `spotsim/puppe.py` — Fassung 4)

`Quader` bekommt `pitch: float = 0.0` (Bogenmass, Neigung um die eigene
y-Achse, positiv = das +x-Ende hebt sich). `Welt` bekommt `boden_z: float =
0.0`; `bau_modell` setzt die Ebene `floor` auf diese Höhe. `Puppe.setze(x, y,
yaw, gelenke, hoehe=None, pitch=0.0)`: Quaternion aus Yaw und Nick, `hoehe` ist
die absolute Körperhöhe (Aufrufer: Bodenhöhe + `standhoehe`). `FASSUNG = 4`,
`PUPPE_FASSUNG = 4`.

`welt_aus_raum(raum, puppe)` baut je Boden:

- Podest: ein Kasten von `boden_z` bis `z` (fällt weg, wenn `z <= boden_z`).
- Rampe: ein geneigter Kasten (Dicke `RAMPE_DICKE_M = 0.20`, Oberkante auf
  der Rampenlinie) plus ein Füllkasten von `boden_z` bis `min(z, z_oben)` —
  mit Absicht keine Keilfüllung darunter: der Keil ist von unten sichtbar
  offen, das ist der dokumentierte Brückenmangel in kleiner Form.
- Treppe: je Stufe ein Kasten von `boden_z` bis zur Trittfläche; Tiefe
  `breite / stufen`, Steigung `anstieg / stufen`.
- Wände, Blöcke, Tags mit ihrem `z`.

`boden_z = min(0, alle z, alle z_oben)`; eine Welt ohne Böden bleibt wie
heute (Ebene bei 0, keine Kästen). `_synchronisiere` setzt
`puppe.setze(x, y, yaw, winkel, hoehe=self._z + standhoehe(winkel),
pitch=radians(self._nick_grad))`. Die Kollisionsprüfung der Puppe
(`kollisionen()`) ignoriert Berührungen mit Böden und Stufen ebenso wie mit
`floor`: ihre Namen beginnen mit `boden_` und `stufe_`. Eine Wand oder Kiste
auf einem Podest trifft wie bisher.

Das Tiefengitter (`spotsim/local_grid.py::belegung_aus_tiefe`) wechselt auf die
Sprungregel: je Zelle die höchste Punkthöhe unterhalb `OBSTACLE_MAX_H` über dem
Boden unter dem Körper (`b_pos.z - standhoehe`, vom Aufrufer als `boden_z`
mitgegeben); belegt ist eine Zelle, deren Höhe sich von einer bekannten
Nachbarzelle (4er-Nachbarschaft) um mehr als `MAX_STUFE_M` unterscheidet — die
höhere der beiden. Dazu bleibt: Punkte über `OBSTACLE_MAX_H` fallen weg. Ohne
Nachbarn (einzelne Zelle) gilt die alte Regel gegen den eigenen Boden. Damit
ist eine Stufe von 17 cm frei, eine Wand belegt, eine Klippe belegt, eine Rampe
frei. `MAX_STUFE_M` steht in spotsim als eigene Konstante mit demselben Wert
und einem Test in spotlab, der beide vergleicht (`tests/test_naht_spotsim.py`).

`zimmerkamera` schaut auf die mittlere Bodenhöhe statt auf 0. Die
`Zimmeransicht` und `film_aus_lauf` interpolieren `z` und `pitch` aus
`zustand.jsonl` mit (beide Felder gibt es dort).

## 5 Editor

### Bearbeitung (`welt/bearbeitung.py`)

- Schlüssel `("boden", i)`; Rang zwischen Block und Wand.
- `neuer_boden(raum, x, y, breite, tiefe, z=0.0, anstieg=0.0, stufen=0, name=None)`.
- `verschiebe`, `drehe`, `skaliere`, `dupliziere`, `loesche`, `treffer`,
  `im_rahmen`, `griffe`, `ziehe_ecke`, `drehring_lage` behandeln Böden wie
  Blöcke (Ecken, Mitte, Drehung).
- `hebe(raum, auswahl, dz)`: `z` aller gewählten Elemente um `dz` (Start
  ausgenommen). Das ist Blender „G, dann Z".
- `FELDER` bekommt `z` für Wand, Block, Tag, Boden und `anstieg`, `stufen` für
  Boden. `setze_feld` prüft `stufen >= 0` (ganzzahlig) und `abs(anstieg) <=
  breite * 2`.
- `pruefe(raum)`: „Der Start steht an einer Kante" (Klippe näher als der
  Radius), „Boden {name} hat keine Fläche", „Treppe {name}: Stufe von
  {rise:.2f} m ist höher als {MAX_STUFE_M} m" (Anstieg / Stufen > MAX_STUFE).

### Steuerung (`gui/raumeditor/steuerung.py`)

- `WERKZEUGE += ("boden",)`: Rechteck aufziehen wie beim Block; `z` = gewählte
  Ebene, `anstieg = 0`, `stufen = 0`. Aus dem Podest macht das Zahlenfeld eine
  Rampe oder Treppe.
- `ebene: float | None` (None = alle); `setze_ebene(wert)`.
  `neuer_block`/`neuer_tag`/`neuer_boden`/`neue_wand` bekommen `z = ebene or 0`.
- Bewegen mit Achssperre `z`: `Modus.taste("z")` sperrt in der Höhe; `vorschau`
  ruft `hebe` mit dem Rasterwert der Mausbewegung in y (Bildschirm hoch = höher).
- `hinweise()` zeigt die neuen Prüfungen.

### 2D-Sicht (`gui/raumeditor/sicht2d.py`, `gui/raumzeichnung.py`)

- `zeichne_raum(..., ebene=None)`: Elemente, die `auf_ebene` verneint, mit der
  Blass-Stufe `palette.blass` (neues Feld in `theme.Palette`, beide Modi).
- Böden: helle Fläche, Rand in `gedaempft`; bei Anstieg ein Pfeil bergauf und
  die Beschriftung `"{z:.2f}→{z_oben:.2f}"` in der Mitte; Treppe mit einer
  Linie je Stufe quer zur Achse. Klippen als kurze Zackenlinie (Kammlinie) in
  `warnung`, damit man Absturzkanten sieht.
- Die Ebenenwahl ist ein `QComboBox` im Kopf der Sicht (Tab), gespeist aus
  `ebenen(raum)`, Eintrag „alle" voran; Wechsel → `steuerung.setze_ebene`.
- Die Spur des Übungsfensters (`raumplot.py`) zeichnet Böden und die Klippen
  ebenso; die Zeile zeigt `Höhe {z:.2f} m, Neigung {nick:.0f}°`.

### 3D-Sicht (`gui/raumeditor/geometrie3d.py`)

- `kasten(x, y, z, hx, hy, hz, yaw_grad=0.0, pitch_grad=0.0)`.
- `kaesten_aus_raum` nimmt dieselbe Zerlegung wie `welt_aus_raum`: eine
  gemeinsame, GL- und MuJoCo-freie Funktion `welt/hoehe.py::kaesten_fuer(boden,
  boden_z)` liefert `[(name, x, y, z_mitte, hx, hy, hz, yaw_grad, pitch_grad)]`;
  MuJoCo und die 3D-Sicht rufen sie beide. Ein Test hält fest, dass beide
  Seiten dieselben Kästen bekommen.
- `bodenraster` liegt auf `boden_z` des Raums; der Spot am Start steht auf
  `boden_bei(start)`.

## 6 Rekonstruktion (`maps/rekonstruktion.py`)

Neue Schritte nach den Wänden, vor `ausrichten` (das jetzt auch Böden dreht
und verschiebt, z bleibt):

1. **Höhenprofil.** Je Wegpunkt `boden[wp]` (gibt es schon) im Seed-Rahmen.
   Der gelaufene Weg ist die Reihenfolge der `creation_time`; zwischen zwei
   aufeinanderfolgenden Wegpunkten gilt die Kante, wenn es eine gibt.
2. **Treppen.** Kanten mit `stairs.state == ANNOTATION_STATE_SET` werden zu
   Ketten (aufeinanderfolgend im Weg); je Kette eine Treppe von `z_unten =
   boden[erster]` bis `z_oben = boden[letzter]`, Achse vom ersten zum letzten
   Wegpunkt, Länge = Grundrissabstand, `stufen = round(|anstieg| /
   STUFE_VORGABE_M)`, mindestens 1. Breite: die Ausdehnung der Bandpunkte quer
   zur Achse innerhalb der Kettenlänge (5.–95. Perzentil), Rückfall 1.2 m.
   Anstieg negativ → Achse umdrehen, damit `anstieg > 0`.
3. **Rampen.** Das Profil `(s, z)` entlang des Wegs ohne Treppenketten wird
   mit Douglas-Peucker (Toleranz 0.10 m) vereinfacht. Jedes Stück mit Länge
   ≥ 2 m und |Gefälle| > 2° wird eine Rampe entlang des Stücks; Breite = 2 ×
   kleinster Wandabstand vom Stückmittelpunkt (nach dem Wändefinden), gedeckelt
   3 m, Rückfall 2 m. Flache Stücke ergeben keine Rampe.
4. **Ebenen.** Bandpunkte unter `boden + 0.15` je Schnappschuss sind
   Bodenpunkte; je 0.25-m-Zelle die mittlere Bodenhöhe. Zellen werden nach
   Höhe in Plateaus gebündelt (Nachbarn mit |Δz| ≤ MAX_STUFE gehören
   zusammen; Zellen unter Rampen und Treppen fallen weg). Das TIEFSTE Plateau
   ist die Höhe 0; alle anderen Höhen verschieben sich um dieselbe Zahl,
   auch Treppen, Rampen, Tags und der Start. (Beim Bau von Etappe 1 geändert:
   der Grundboden liegt überall bei 0 und Böden liegen darauf — ein Boden
   unter dem Grundboden wäre in der Rechnung unerreichbar und in MuJoCo
   verschüttet. `boden_bei` wählt ohne `z_nahe` den höchsten Boden, mit
   `z_nahe` den höchsten erreichbaren, sonst den nächsten.) Jedes andere Plateau wird gierig
   in achsparallele Rechtecke ≥ 0.5 m zerlegt (grösstes Rechteck aus den
   freien Zellen, abziehen, wiederholen; höchstens `MAX_BOEDEN = 60` je
   Plateau); jedes Rechteck ein Podest mit der Plateauhöhe. Das geschieht im
   AUSGERICHTETEN Rahmen, damit die Rechtecke zu den Wänden passen — also
   nach `ausrichten`, mit denselben Drehungen.
5. **Bericht:** `boeden`, `treppen`, `rampen`, `ebenen` (Liste), `gefaelle_grad`
   (grösstes Rampengefälle), `stufe_m` (STUFE_VORGABE_M) und Hinweis, wenn
   Treppen ohne Punktwolken-Breite entstanden.

Die synthetische Karte im Test bekommt eine Treppe (zwei Kanten mit
`stairs`-Annotation, 1.0 m Anstieg) und einen Gang mit 4° Gefälle über 5 m;
der Katakomben-Test verlangt ≥ 1 Treppe mit Anstieg 1.2–1.4 m und ein
grösstes Gefälle zwischen 1° und 8°.

## 7 Schüler-Schnittstelle und Verhalten

### `spot.stairs()` (`api/spot.py`, `api/world.py`, `backends/base.py`)

```python
@dataclass(frozen=True)
class Staircase(WorldObject):
    direction: str      # "auf" | "ab" -- aus Sicht des Roboters
    steps: int
    rise_m: float       # Gesamtanstieg, positiv
    axis_bearing: float # Peilung der Bergauf-Achse in Grad, links positiv
```

`kind = "staircase"`, `Capability.STAIRS`; `world.stairs(backend, recorder)`
protokolliert `treffer`, `richtungen`, `distanzen`. Im Sim: aus
`treppe_vor` und, darüber hinaus, aus allen Treppen des Raums innerhalb
`TAG_REICHWEITE_M` mit freier Sichtlinie (die nächste zuerst). Am Roboter:
`wahrnehmung.objekte_holen` wandelt `staircase_properties`: Lage aus
`from_ko_tform_stairs` über den Transformbaum in den Körperframe; `steps =
len(stairs)`, `rise_m = Σ rise`; `direction` „auf", wenn die untere Landung
näher am Körper liegt als die obere; `axis_bearing` aus der x-Achse des
Treppenrahmens. `DryRunBackend` liefert `[]`.

`State` bleibt: `z` und `pitch` sind da und tragen jetzt echte Werte.

### Beispiel und Vorlage (`workshop/beispiele/treppe_steigen.py`, `welt/vorlagen/treppe.toml`)

Vorlage „treppe": 7 × 4 m, Start (1, 2, 0), Treppe 2 m lang ab x = 2.5 auf
1.2 m mit 7 Stufen, Podest 2 × 4 m ab x = 4.5 auf 1.2 m, Tag 3 an der Wand
oben (x = 6.9). Das Beispiel: `stairs()` bis eine Treppe „auf" in Sicht ist,
auf `axis_bearing` drehen, vorwärts fahren, bis `spot.state.z` um mehr als
1 m gestiegen ist und die Treppe hinter ihm liegt (`stairs()` meldet „ab"),
Tag ausgeben, umdrehen (180°), rückwärts fahren, bis `z` wieder unten ist,
setzen. Ausgabe „Oben" und „Unten". Der Test fährt es in 2D und 3D wie
`durchgang_finden` und prüft: keine `angestossen`, keine `treppe_verweigert`,
`z` in der Mitte des Laufs > 1.0, am Ende < 0.1. Ein zweiter Test startet ein
Programm, das vorwärts hinunterfährt, und erwartet `treppe_verweigert` mit
`verlangt == "rückwärts runter"`.

## 8 Fehler und Meldungen

- `treppe_verweigert` → Status im `command_feedback`: „Treppe {name}: abwärts
  geht nur rückwärts — drehe dich um und fahre mit `walk(vx=-0.2)`." bzw.
  „… aufwärts geht nur vorwärts."
- `pruefe`: „Der Start steht an einer Kante — verschiebe ihn oder setze einen
  Boden davor." „Treppe {name}: 0.40 m je Stufe ist höher als 0.25 m — mehr
  Stufen oder weniger Anstieg."
- `config.toml` `treppen = "vielleicht"` → `ConfigBroken` mit „treppen muss
  auto oder aus sein".
- Rekonstruktion ohne Treppenannotationen, aber mit Sprüngen > MAX_STUFE im
  Profil: Hinweis „{n} Höhensprünge ohne Treppenmarkierung — im Editor eine
  Treppe setzen".
- Ein Raum mit Böden in einem alten spotlab (v2-Leser) ignoriert `[[boden]]`
  still; deshalb schreibt `raum_speichern` `fassung = 3` in `[raum]`, und der
  v3-Leser warnt nicht, der v2-Leser kannte das Feld nicht. (Es gibt keinen
  v2-Leser mehr im Umlauf; das Feld dient der Nachvollziehbarkeit.)

## 9 Tests

- `test_welt_raum.py`: v3 rund, v2 bleibt gleich (Datei identisch, wenn keine
  Höhe), `Boden.hoehe_lokal`, `stufe_lokal`, `art`, gedrehte Ecken.
- `test_welt_hoehe.py`: `boden_bei` mit Podest, Rampe, Brücke (z_nahe
  entscheidet), `neigung_bei` auf gedrehter Rampe, `ebenen`, `auf_ebene`,
  `klippen` (Rampe: Seiten ab 0.25 m, kein Fuss, kein Kopf; Podest: alle vier
  Kanten; Treppe an Podest: keine Kopfkante), `treppe_vor` (auf/ab, Winkel),
  `treppe_erlaubt` (vier Kombinationen), `kaesten_fuer`.
- `test_welt_kollision.py`: Körperband (Block auf dem Podest trifft unten
  nicht), Klippe hält, `bewege` folgt der Rampe (z steigt), Sprung hält.
- `test_welt_wahrnehmung.py`: Klippe im Gitter belegt, Treppe frei, Tag auf
  dem Podest von unten unsichtbar bei > 1.5 m.
- `test_backend_sim.py` (neu oder erweitert): Rampe hoch → `State.z` steigt,
  `pitch` > 0; Treppe falsch herum → `treppe_verweigert` einmal je Flanke und
  Status; `treppen = "aus"` → Treppe ist Klippe; Ereignisart im echten
  `RunRecorder`.
- `test_backend_mujoco.py`: `welt_aus_raum` mit Podest, Rampe (pitch), Treppe
  (7 Kästen), `boden_z`; `kaesten_fuer` gleich in 3D-Sicht und Welt.
- matura-spot `test_puppe.py`: `setze(pitch=…)` dreht den Körper; Kasten mit
  `pitch` steht geneigt; `floor` auf `boden_z`; `test_local_grid.py`: Stufe
  17 cm frei, Wand belegt, Klippe belegt (synthetische Tiefenszene).
- `test_welt_bearbeitung.py`, `test_gui_raumeditor_steuerung.py`: Boden-
  Werkzeug, `hebe` mit Z-Sperre, Felder, Ebene setzt z, Prüfungen.
- `test_gui_raumzeichnung.py`, `test_gui_raumeditor_sicht2d.py`: Ebene blass,
  Treppe zeichnet Stufenlinien (grab stürzt nicht), Kammlinie.
- `test_gui_raumeditor_geometrie3d.py`: `kasten` mit pitch, Raster auf
  `boden_z`.
- `test_maps_rekonstruktion.py`: synthetische Treppe und Rampe; Katakomben
  skipif.
- `test_api_world.py` / `test_backend_real_wahrnehmung.py`: `Staircase` aus
  einem gebauten `WorldObject`-Protobuf mit `staircase_properties`.
- `test_workshop_beispiele.py`: `treppe_steigen.py` in 2D und 3D, falsch
  herum.
- `test_config.py`: `treppen`.
- `test_naht_spotsim.py`: `MAX_STUFE_M` gleich in beiden Paketen, Fassung 4.

## 10 Abnahme und Messfahrt

- **A25** Treppenmodus am Gerät: `treppen = "auto"`, vor einer echten Treppe
  `walk(vx=0.2)` bergauf und `walk(vx=-0.2)` rückwärts bergab; danach
  absichtlich vorwärts bergab — was tut der Roboter? Ergebnis in die
  Treppenregel übernehmen (§ 4).
- **A26** `spot.stairs()` vor derselben Treppe: `direction`, `steps`,
  `rise_m`, `axis_bearing` gegen Augenschein.
- **A27** `spot.obstacles()` auf der Treppe und an ihrer Kante: sind Stufen
  im echten `obstacle_distance` frei, ist die Kante belegt?
- **B6** in `matura-spot/notes/MESSFAHRT_ABLAUF.md`: „Treppe hoch, rückwärts
  runter" mit dem Beobachter, Messfenster je Richtung — die Datei, aus der
  die Puppe später den Treppengang spielt.

## 11 Etappen

1. **Höhe im Kern:** Raumformat v3, `welt/hoehe.py`, Kollision, Gitter, 2D-Sim
   (z, Nick, Treppenregel, Ereignis), Treppenmodus in Konfiguration und
   Mobility-Parametern, MuJoCo-Welt und Puppe Fassung 4 samt Tiefengitter.
2. **Editor:** Bearbeitung, Steuerung, Ebenen, 2D-Zeichnung, 3D-Kästen,
   Übungsfenster.
3. **Rekonstruktion:** Höhenprofil, Treppen, Rampen, Ebenen, Bericht, Dialog.
4. **Schüler:** `stairs()`, Beispiel, Vorlage, Abnahme, Messfahrt-Ablauf,
   README, CLAUDE.md.

## 12 Neue Regeln für CLAUDE.md

- **Ein Hindernis ist ein Höhensprung über `MAX_STUFE_M`.** Dieselbe Zahl in
  `welt/raum.py` und `spotsim/local_grid.py`, geprüft in `test_naht_spotsim`;
  Kollision (Körperband, Klippen), 2D-Gitter und Tiefengitter der Puppe
  formulieren nur sie.
- **Höhe nach einem Prinzip:** `boden_bei(raum, x, y, z_nahe)` ist die einzige
  Antwort auf „wie hoch ist der Boden hier"; 2D-Sim, MuJoCo, 3D-Sicht,
  Ebenen und Prüfungen rufen sie. `kaesten_fuer` ist die einzige Zerlegung
  eines Bodens in Kästen (MuJoCo und 3D-Sicht).
- **Die Puppe spielt auf der Treppe den ebenen Gang** und sagt es
  (`treppengang: "nicht gemessen"`). Ein Treppengang kommt aus B6, nie aus
  einer erfundenen Kurve.
- **Vorwärts hoch, rückwärts runter — der Sim verweigert den Rest**
  (`treppe_verweigert`), bis A25 etwas anderes ergibt.
- **`treppen` in der Konfiguration gilt an einer Stelle:** `mobility.mit_grenze`
  setzt `stairs_mode`, der Sim liest denselben Wert.

## 13 Nachträge beim Bau von Etappe 1 (06.09.2026)

- **Die Treppenregel ist „Nase bergauf".** `treppe_erlaubt(richtung, vx, winkel)`
  erlaubt jede Fahrt, solange die Nase innerhalb 45° zur Bergauf-Achse zeigt —
  vorwärts hoch und rückwärts runter sind beide „Nase bergauf", die anderen
  beiden Kombinationen sind verboten; `richtung` bestimmt nur, was die Meldung
  verlangt. Die Prüfung heisst `SimBackend._treppe_verweigert(von, nach)` und
  greift, sobald der Schritt auf die Treppe führt oder ihre Kante näher als den
  Roboterradius bringt.
- **Eine Nick-Konvention:** Drehung um y nach der Rechte-Hand-Regel, Nase hoch
  ist NEGATIV — `nick_grad`, `kaesten_fuer` (`pitch_grad`), `Quader.pitch`,
  `Puppe.setze(pitch=…)` und `State.pitch` sprechen dieselbe Sprache; § 4 sagte
  noch „positiv = Nase hoch".
- **`bewege()` bleibt; neu ist `bewege_mit_hoehe(raum, von, nach, z, klippen_)`**
  mit Rückgabe `((x, y, yaw), z, hindernis)`. `hindernis_bei` bekommt `z=` und
  `klippen_=` als optionale Parameter; ohne sie verhält sich alles wie in Stufe 12.
- **`boden_bei(raum, x, y, z_nahe=None)`:** ohne `z_nahe` der höchste Boden,
  mit `z_nahe` der höchste erreichbare (innerhalb `MAX_STUFE_M`), sonst der
  nächste. Der Grundboden liegt überall bei 0 und Böden liegen darauf; ein
  Boden unter 0 ist eine Prüfmeldung im Editor, und die Rekonstruktion macht
  das TIEFSTE Plateau zur Höhe 0 (§ 6 sagte „das grösste").
- **Treppenmodus:** `Limits.treppen` unter `[limits]`, nicht `[sicherheit]`.
- **Tiefengitter der Puppe:** belegt ist eine gesehene Zelle, die vom Boden
  unter dem Roboter nicht über Sprünge bis `MAX_STUFE_M` erreichbar ist
  (Flutfüllung), und nur Strahlen in Bodennähe räumen frei — der Boden hinter
  einer hohen Kante ist von oben nicht sichtbar und bleibt unbekannt (§ 4
  formulierte die Regel als Nachbarsprung; die Flutfüllung ist dieselbe Regel
  mit Anschluss an den eigenen Boden).

## 14 Nachträge beim Bau von Etappe 3 (06.09.2026)

- **Das Höhenprofil kommt aus den Wegpunkten**, nicht aus dem Boden je
  Schnappschuss (§ 6 Schritt 1): auf einer Treppe zeigt die Wolke immer auch
  den Fuss, und das 5. Perzentil bliebe unten. `profil()` = Wegpunkt-z minus
  `KOERPER_UEBER_BODEN_M`; die Böden je Schnappschuss bleiben für das Band der
  Wände. Tags tragen `hoehe` über dem Profil und `z` = Profil.
- **Ebenen als Schlauch entlang des Wegs**, nicht aus Bodenzellen der Wolke
  (§ 6 Schritt 4): jedes ebene Profilstück über dem tiefsten Boden wird je
  gerader Teilstrecke ein Podest so breit wie der Gang (Bandpunkte quer zur
  Achse, 20. Perzentil je Seite, Vorgabe 2 m, Deckel 3 m). Das deckt, was
  gefahren wurde; Räume abseits des Wegs zieht man im Editor nach. Kurze
  Teilstrecken (< 1 m) gehen im Nachbarn auf, damit der Schlauch keine
  Lücke hat.
- **Dieselbe Treppe hoch und runter ist eine:** `verschmelze_treppen` behält
  bei überlappenden Treppen (Mitte ≤ 1 m, Achse ≤ 30°) die mit dem grösseren
  Anstieg. Die Katakomben trugen sie zweimal (+1.78 m, −1.39 m, Drift).
- **`ausrichten` gibt `(waende, tags, start, pauspapier, boeden, Ausrichtung)`**
  zurück; Böden drehen und verschieben mit, `z` bleibt.
- Der Bericht trägt `boeden`, `treppen`, `rampen`, `ebenen`, `gefaelle_grad`,
  `stufe_m`; der Dialog zeigt sie, die Vorschau nennt Treppen und Rampen.
