# Korrigierer und Gelände — Wandlücken schliessen, den Boden bis an die Wände rechnen

Entwurf vom 07.09.2026. Entscheidungen des Autors im Gespräch:

- **Wo keine Wand ist: A** — dichtes Pauspapier zählt als Wand; wo weder Wand
  noch Punkte sind, endet der Boden nach einem festen Abstand neben dem Weg
  (Vorgabe 2 m), und der Korrigierer meldet die offenen Ränder.
- **Wandlücken: A** — der Korrigierer entscheidet, wo es klar ist (der Roboter
  lief hindurch → Durchgang; Punkte in der Lücke → Wand), zeigt alles in einer
  Liste mit Grund, der Autor kippt, was falsch ist, und drückt „Anwenden".
  Unklare Lücken bleiben ohne Entscheid liegen.
- **Boden: Weg 1** — ein Gelände als eigenes Element, ein Höhenraster, dessen
  Höhe eine Membran über dem Höhenprofil des Wegs ist. Keine Rechtecke bis an
  die Wände, keine Vielecke.

## Befunde, die den Entwurf tragen

- **Die Katakomben nach Stufe 13** (`raeume/Catacombs`): 261 Wandstücke mit
  Lücken an fast jeder Ecke und mitten in den Gängen, ein Boden als Schlauch
  aus 1 Treppe, 10 Rampen und Podesten entlang des Wegs, je Stück eine andere
  Breite, mit Nähten an den Knicken. Neben dem Schlauch liegt der Grund 0, die
  Gänge fallen aber bis 2.4 m ab — der Schlauch schwebt sichtbar über dem
  Grund. Das ist genau, was der Autor sah: „der Boden hat so einen Weg und
  hängt nicht mit den Wänden zusammen".
- **Das Pauspapier** (`welt/pauspapier.py`, PAUS1) speichert nur die Bandpunkte
  (x, y). Den gelaufenen Weg mit seinem Bodenprofil kennt nur die
  Rekonstruktion (`maps/rekonstruktion.py::weg`, `profil`); er verlässt sie
  heute nicht.
- **Die Höhe hat einen Ort:** `welt/hoehe.py::boden_bei` ist die einzige
  Antwort auf „wie hoch ist der Boden hier"; ihr Grundkandidat ist die 0.
  Klippen (`klippen`) entstehen an Rechteckkanten; Ebenen (`ebenen`) aus den
  Bodenhöhen. 2D-Sim, Gitter, MuJoCo, 3D-Sicht und Editor fragen nur dort.
- **MuJoCo kennt Höhenraster** (`hfield`): ein Rechteck mit `nrow × ncol`
  Knoten, Höhen normiert auf `[0, 1]` mal `elevation_z`, Strahlen (`mj_ray`)
  treffen es wie einen Kasten. Die Puppe baut ihre Welt über `mjSpec`
  (`puppe.bau_modell`), Fassung 4, und ignoriert Berührungen mit `floor` und
  Namen aus `BEGEHBAR`.
- **Der Editor** zeichnet 2D über `raumzeichnung.zeichne_raum` mit Ebenen
  (blass, was nicht auf der Ebene liegt) und 3D über `geometrie3d.kaesten_aus_raum`
  in einen Puffer je Raumwechsel; Elemente heissen `("wand", i)`, `("boden", i)`
  usw.; die Rekonstruktion läuft in einem Arbeiter-Thread mit Dialog.

## Ziel

Der Autor rekonstruiert die Katakomben, öffnet „Korrigieren…", sieht die
Liste der Wandlücken mit Vorschlag und Grund, kippt drei Zeilen, drückt
„Anwenden" — und der Raum hat geschlossene Wände, Durchgänge, wo der Roboter
lief, und einen Boden, der jeden Gang bis an die Wände füllt, mit dem
Gefälle des Wegs und weichen Übergängen an den Abzweigungen. Der
aufgezeichnete Weg lässt sich im 2D-Sim und in MuJoCo ohne Anstoss abfahren.
Die Treppe bleibt eine Treppe. Ein Schüler sieht das Gelände in 2D als
schattiertes Relief mit Höhenlinien und in 3D als Fläche, und `spot.state.z`
folgt ihm.

## Nicht-Ziele

- Kein Bearbeiten des Geländes von Hand (keine Knoten ziehen, kein Malen).
  Das Gelände ist gerechnet; wer es anders will, zieht Wände nach und lässt
  den Korrigierer neu laufen.
- Kein Drehen und kein Skalieren des Geländes. Verschieben, Heben und Löschen ja.
- Keine Brücke, keine zwei Böden übereinander im Gelände — es ist eindeutig
  in der Höhe. Was darüber liegt, bleiben Böden (Treppe, Podest, Rampe).
- Kein Gelände in den Vorlagen. Handgezeichnete Räume stehen weiter auf der 0.
- Keine Erkennung von Türen über die Breite oder die Karte; die Signale sind
  der Weg und das Pauspapier, der Rest ist der Autor.
- Keine Änderung an der Rekonstruktion der Wände selbst (RANSAC, Verschmelzen,
  Begradigen); der Korrigierer arbeitet danach, auf dem Raum.

## 1 Das Gelände (`welt/gelaende.py`, Raumformat v4)

### Element

```python
@dataclass(frozen=True)
class Gelaende:
    x0: float          # Weltkoordinate des Knotens (0, 0), links unten
    y0: float
    zelle: float       # Knotenabstand in m (Vorgabe GELAENDE_ZELLE_M = 0.2)
    zeilen: int        # Knoten in y
    spalten: int       # Knoten in x
    hoehen: tuple      # zeilen * spalten Werte, zeilenweise ab y0; None = kein Boden
```

Reine Standardbibliothek. `None` statt NaN im Speicher, damit Räume vergleichbar
bleiben (Verlauf, Tests); die Datei schreibt NaN.

- `knoten(i, j) -> float | None`.
- `hoehe_bei(x, y) -> float | None`: bilinear aus den vier umgebenden Knoten.
  Liegt der Punkt ausserhalb des Knotenrechtecks oder sind alle vier `None`,
  ist es `None`. Sind nur einige `None`, gilt der Wert des nächsten gültigen
  der vier — die Fläche reicht bis an die Zellgrenze, nicht nur bis zum
  letzten Knoten.
- `neigung_bei(x, y) -> (dz/dx, dz/dy)`: zentrale Differenzen über eine
  halbe Zelle, mit `hoehe_bei`; (0, 0) ausserhalb.
- `klippen(gelaende) -> [(x1, y1, x2, y2)]`: zwischen zwei Nachbarknoten
  (rechts, oben) mit mehr als `MAX_STUFE_M` Unterschied liegt die Klippe auf
  der Zellgrenze zwischen ihnen, eine Zelle lang. Ist ein Nachbar `None`, ist
  der Grund dort 0, und die Klippe entsteht, wenn der gültige Knoten mehr als
  `MAX_STUFE_M` über 0 liegt. Aufeinanderfolgende Stücke auf einer Linie
  werden eine Strecke, damit das Gitter (`wahrnehmung._abstaende`) wenige
  Strecken sieht.
- `plateaus(gelaende) -> [float]`: Knoten mit Neigung unter
  `PLATEAU_NEIGUNG_GRAD = 2.0` zu allen vier Nachbarn, gruppiert auf 0.1 m,
  Gruppen ab `PLATEAU_KNOTEN = 50` (2 m² bei 0.2 m), sortiert.
- `umriss(gelaende) -> (x_min, y_min, x_max, y_max)` über die gültigen Knoten,
  für die Hülle.
- `verschoben(gelaende, dx, dy, dz)`: `x0`, `y0` und alle Höhen verschieben.
- `zusammenfassung(gelaende) -> str`: „Gelände · 0.2 m · 3120 Knoten · 0.00 bis 2.40 m".

### Datei

Neben der Raumdatei, wie das Pauspapier: `raeume/<name>.gelaende`, Kennung
`b"GEL1"`, dann `<dddII` für `x0`, `y0`, `zelle`, `zeilen`, `spalten`, dann
`zeilen * spalten` float32 zeilenweise, NaN für `None`. `schreibe(pfad, gelaende)`,
`lies(pfad) -> Gelaende | None` (fehlende Datei → `None`, falsche Kennung →
`SpotlabError` mit dem Rat, den Raum neu zu korrigieren).

In der Raumdatei steht nur der Verweis:

```toml
[raum]
fassung = 4
...

[gelaende]
datei = "Catacombs.gelaende"
```

`raum_speichern` schreibt `fassung = 4` und den Abschnitt nur, wenn ein Gelände
da ist, und schreibt die Binärdatei daneben; ohne Gelände löscht es eine
liegengebliebene `.gelaende`-Datei desselben Namens. `raum_laden_pfad` liest den
Verweis relativ zur Raumdatei; fehlt die Datei, gibt es einen `SpotlabError`
(„Gelände-Datei fehlt — den Raum neu korrigieren oder den Abschnitt
[gelaende] entfernen"). `Raum` bekommt `gelaende: Gelaende | None = None`;
`huelle` nimmt den Umriss des Geländes mit.

## 2 Höhe, Klippen, Ebenen, Kollision, Gitter

- **`boden_bei`:** der Grundkandidat ist `(gelaende.hoehe_bei(x, y), None)`,
  wenn es ein Gelände gibt und der Wert nicht `None` ist, sonst `(0.0, None)`.
  Sonst bleibt alles: Böden darüber, `z_nahe`, `ohne`. Eine Treppe auf dem
  Gelände gewinnt gegen die Rampe des Geländes unter ihr, weil beide gleich
  hoch sind und der Boden den Vorzug hat.
- **`neigung_bei`:** auf dem Grund mit Gelände `gelaende.neigung_bei`; `nick_grad`
  folgt daraus. Ein Roboter, der ein Gefälle hinunterfährt, nickt also auch
  ohne Rampe.
- **`klippen(raum)`:** die Klippen der Böden wie bisher plus
  `gelaende.klippen`. Der Boden-Teil fragt weiter `boden_bei` mit `ohne`, sieht
  also das Gelände als Grund neben einem Boden — ein Podest auf 1.0 m über
  einem Gelände auf 0.9 m hat keine Klippe.
- **`ebenen(raum)`:** 0.0, die Böden wie bisher, dazu `plateaus(gelaende)`.
- **`boden_z(raum)`:** `min(0.0, tiefster Boden, tiefster Geländeknoten)`.
- **`kollision.klippen_von`:** merkt sich das letzte Ergebnis je
  `(raum.boeden, raum.gelaende)` (Identität; beide unveränderlich), damit der
  Editor bei jeder Mausbewegung nicht 45 000 Knoten abläuft. `hindernis_bei`,
  `bewege_mit_hoehe`, `wahrnehmung.abstandsgitter` bleiben: sie sehen Klippen
  als Strecken.
- **`bearbeitung.pruefe`:** „Wand 12 schwebt 0.4 m über dem Gelände" bzw.
  „steckt 0.4 m im Gelände", wenn `|wand.z − Grund unter der Mitte| > MAX_STUFE_M`.

## 3 Der Weg im Pauspapier (PAUS2) und die Rekonstruktion

`welt/pauspapier.py`: Format `PAUS2` = Kennung, uint32 Punkte, float32-Paare,
uint32 Wegpunkte, float32-Tripel (x, y, Bodenhöhe) im Raumrahmen. `schreibe(pfad,
punkte, weg=())`; `lies(pfad)` gibt weiter die Punkte; neu `lies_weg(pfad) ->
[(x, y, z)]`, bei PAUS1 leer. Beide Kennungen werden gelesen.

`maps/rekonstruktion.py`: `Ergebnis` bekommt `weg: list` — die Wegpunkte in
Laufreihenfolge (`weg(graph)`), durch `Ausrichtung.punkt` gedreht und
verschoben, Bodenhöhe = `profil − z_min`, also dieselbe Höhe, die Böden und
Tags tragen. Sonst ändert sich an der Rekonstruktion nichts: sie liefert
weiter den Schlauch; der Korrigierer macht daraus das Gelände. Der Bericht
der Rekonstruktion endet mit dem Hinweis „Weiter mit Korrigieren…: Lücken
schliessen, Gelände bauen".

`gui/raumeditor/tab.py` hält `_weg` neben `_pauspapier`, speichert beides in
`_schreibe` und lädt beides in `waehle_raum`.

## 4 Sichten

### 2D (`gui/raumzeichnung.py`, `gui/raumeditor/sicht2d.py`)

`gelaende_bild(gelaende, palette, ebene=None) -> QImage`: ein Pixel je Knoten,
Zeile 0 oben (y-Achse der Sicht zeigt nach oben, also Zeilen gespiegelt).
Farbe = `theme.mische(palette.flaeche, palette.gedaempft, 0.15 + 0.45 · t)` mit
`t = (h − h_min) / (h_max − h_min)`; Höhenlinie alle `HOEHENLINIE_M = 0.25`:
ein Knoten, dessen `floor(h / 0.25)` sich vom rechten oder oberen Nachbarn
unterscheidet, wird `palette.gedaempft`. Knoten ohne Boden sind durchsichtig.
Mit `ebene` werden Knoten ausserhalb `ebene ± 0.3` in `palette.blass`
gezeichnet. `theme.mische(a, b, t)` ist neu und die einzige Stelle, die
Farben mischt — die Regel „Farben nur aus `gui/theme.py`" bleibt.

`Sicht2D` hält das Bild je `(gelaende, ebene)` (Identität) und zeichnet es in
`paintEvent` nach dem Raster und vor dem Pauspapier mit `drawImage` auf das
Rechteck des Knotengitters (Alpha 200). `zeichne_raum` bleibt unberührt; das
Gelände ist kein Element der Schleifen dort.

Neu in `Sicht2D`: `setze_markierung(strecken)` — gestrichelte Strecken in
`palette.akzent` mit Punkten an den Enden, für die gewählte Lücke des
Korrigierers; `setze_kandidaten(strecken)` — dünn gestrichelt in
`palette.gedaempft`, alle anderen; `setze_offen(punkte)` — Punkte in
`palette.warnung`, die offenen Ränder. Alle drei leert `tab._setze`.

### 3D (`gui/raumeditor/geometrie3d.py`, `sicht3d.py`)

`gelaende_dreiecke(gelaende, band_m=0.25) -> [(band, vertices)]`: je Zelle mit
vier gültigen Knoten zwei Dreiecke, mit drei gültigen eines, keines darunter;
je Dreieck die Normale aus dem Kreuzprodukt; gruppiert nach Höhenband
`floor(mittlere Höhe / band_m)`. `kaesten_aus_raum` hängt sie als
`(("gelaende", band), vertices)` VOR die Böden an (sie liegen unter allem);
`_elementfarbe` gibt für `("gelaende", k)` `theme.mische(palette.rand,
palette.text, min(0.35, 0.05 · k))`; `treffer` (Anklicken in 3D) übergeht
Gelände-Schlüssel; `bodenraster` liegt weiter auf `boden_z`.

### MuJoCo (`backends/mujoco.py`, `spotsim/puppe.py` — Fassung 5)

`puppe.Welt` bekommt `gelaende: Gelaende | None`, wobei `puppe.Gelaende(x0, y0,
zelle, hoehen)` ein numpy-Feld `(zeilen, spalten)` mit NaN trägt.
`bau_modell` legt für ein Gelände ein `hfield` an: `nrow = zeilen`, `ncol =
spalten`, `size = (rx, ry, z_max, 0.05)` mit `rx = (spalten − 1) · zelle / 2`,
`ry = (zeilen − 1) · zelle / 2`, Daten = `nan_to_num(hoehen − boden_z) /
z_max`, Geom `gelaende` vom Typ `mjGEOM_HFIELD` bei `(x0 + rx, y0 + ry,
boden_z)`. Ist `z_max ≤ 0` (alles eben auf der Bodenebene), gibt es kein
hfield. `BEGEHBAR` bekommt `"gelaende"`; Berührungen damit zählen wie mit
`floor`. `FASSUNG = 5`, `PUPPE_FASSUNG = 5` in spotlab.

Die Zeilenrichtung der hfield-Daten (erste Zeile bei `−ry` oder bei `+ry`)
klärt ein Test: er baut ein Gelände, das nur nach +y ansteigt, schiesst
einen Strahl senkrecht auf drei Stellen und vergleicht mit `hoehe_bei`. Die
Puppe misst am Gelände; die Körperhöhe setzt weiter spotlab aus `boden_bei`.

`welt_aus_raum` übergibt `raum.gelaende` als `puppe.Gelaende`
(`None` → NaN). Das Tiefengitter der Puppe misst gegen das hfield, seine
Sprungregel (`MAX_STUFE_M`) gilt unverändert.

## 5 Editor

### Bearbeitung (`welt/bearbeitung.py`)

Schlüssel `("gelaende", 0)`. `element` gibt `raum.gelaende`, `lage` die Mitte des
Umrisses, `FELDER["gelaende"] = ()` (nur lesend). `verschiebe` verschiebt `x0,
y0`, `hebe` alle Höhen, `loesche` setzt `gelaende=None`; `drehe`, `skaliere`,
`dupliziere`, `ziehe_ecke` übergehen den Schlüssel, `treffer` liefert ihn nie
(Anklicken wählt, was darauf steht). `pruefe` wie in § 2.

### Steuerung und Tab (`gui/raumeditor/steuerung.py`, `tab.py`)

`alle()` enthält `("gelaende", 0)`, wenn es ein Gelände gibt; `_beschrifte`
gibt `zusammenfassung(gelaende)`; die Eigenschaften zeigen dieselbe Zeile als
`QLabel` und den Hinweis „gerechnet aus Wänden, Weg und Pauspapier — nicht von
Hand zu ändern". `_zeige` ruft `klippen_von`, wenn Böden ODER Gelände da sind.
Neuer Knopf „Korrigieren…" unter „Rekonstruieren…", öffnet den Dialog aus § 8.

## 6 Der Korrigierer: Wände (`welt/korrektur.py`, Standardbibliothek)

```python
@dataclass(frozen=True)
class Luecke:
    art: str          # "luecke" | "ecke" | "anschluss" | "kreuzt"
    waende: tuple     # Indizes im Raum: (i, j) bzw. (i,) bei "kreuzt"
    enden: tuple      # je Wand das Ende, das rueckt: 1 oder 2; () bei "kreuzt"
    ziel: tuple       # (x, y): wohin die Enden ruecken (bei "kreuzt": Wandmitte)
    strecken: tuple   # [(x1, y1, x2, y2)]: was Wand wuerde (bei "kreuzt": die Wand)
    laenge: float     # Summe der Strecken
    vorschlag: str    # "wand" | "durchgang" | "loeschen" | "unklar"
    grund: str
```

`finde_luecken(raum, weg=(), pauspapier=(), max_luecke=MAX_LUECKE_M,
winkel_grad=15.0) -> [Luecke]`, sortiert nach Länge:

1. **Kandidaten je Wandende** E (jede Wand zwei Enden), gegen jede andere Wand j,
   nur Abstände bis `MAX_LUECKE_M = 1.5`:
   - *luecke*: Winkel der Wände ≤ 15°, ein Ende F von j ist das nächste; Ziel F,
     Strecke E–F.
   - *ecke*: Winkel 90° ± 15°, Schnittpunkt S der Geraden; `|E−S| ≤ 1.5` und für
     das nächste Ende F von j `|F−S| ≤ 1.5`; Ziel S, Strecken E–S und F–S; beide
     Enden rücken.
   - *anschluss*: der Fusspunkt P von E auf der Strecke j liegt innen
     (Parameter 0.05..0.95), `|E−P| ≤ 1.5`, Winkel 90° ± 25°; Ziel P, Strecke E–P.
   - Ausgeschlossen: Strecken unter 0.02 m (berühren sich schon) und Strecken,
     die eine dritte Wand kreuzen.
   Je Ende bleibt der kürzeste Kandidat; ein Paar (E, F) erscheint einmal.
2. **kreuzt:** jede Wand, die eine Strecke des Wegs schneidet. Ziel: Wandmitte,
   Strecke: die Wand, Vorschlag „loeschen", Grund „kreuzt den Weg des Roboters".
3. **Vorschlag** je Kandidat aus § 1:
   - eine Wegstrecke schneidet eine der Strecken → `durchgang`, „der Roboter
     lief hindurch";
   - sonst: die Strecken werden alle 0.05 m abgetastet; eine Probe „hat
     Punkte", wenn im 0.1-m-Zellenindex des Pauspapiers ihre Zelle oder eine
     der acht Nachbarzellen mindestens 2 Punkte hält; ab 60 % Proben mit
     Punkten → `wand`, „Punkte in der Lücke";
   - sonst `unklar`, „kein Weg, keine Punkte — bitte entscheiden".
   Ohne Weg und Pauspapier ist jeder Kandidat unklar.

`wende_an(raum, luecken, entscheide) -> Raum` mit `entscheide: {index:
"wand" | "durchgang" | "loeschen" | "lassen"}`: `wand` rückt die genannten
Enden auf das Ziel (Wände bleiben getrennte Elemente, sie berühren sich am
Ziel — kein Verschmelzen, keine Indexverschiebung), `loeschen` merkt die Wand
vor und löscht am Ende alle vorgemerkten; `durchgang` und `lassen` tun nichts.
Ein Ende, das zweimal rückt (zwei Lücken am selben Ende gibt es nicht, an
derselben Wand schon), rückt in Listenreihenfolge. Das `z` der Wände bleibt.

`uebernimm_gelaende(raum, gelaende, boeden_aufloesen: bool) -> Raum`: setzt das
Gelände, löscht bei `boeden_aufloesen` alle Böden ohne Stufen (Rampen und
Podeste), und setzt `z` jeder Wand und jedes Tags auf den Grund unter ihrer
Mitte (`gelaende.hoehe_bei`; `None` → unverändert), Treppen behalten ihr `z`.

## 7 Der Korrigierer: Gelände (`maps/gelaende_bau.py`, numpy)

```python
@dataclass(frozen=True)
class Einstellungen:
    zelle: float = GELAENDE_ZELLE_M      # 0.2
    abstand: float = 2.0                 # Boden neben dem Weg, wo nichts aufhaelt
    punkte_je_zelle: int = 5             # ab hier sperrt das Pauspapier eine Zelle
    min_fleck: int = 3                   # kleinere gesperrte Flecken sind Rauschen
    profil_toleranz: float = 0.10        # Douglas-Peucker auf dem Wegprofil
    hoechstens_iterationen: int = 3000
    genau_m: float = 0.001

@dataclass(frozen=True)
class Ergebnis:
    gelaende: Gelaende
    offene_raender: list      # [(x, y)] Zellmitten am Flutrand ohne Wand
    bericht: dict             # knoten, region, gesperrt, offen (Anzahl Läufe),
                              # z_min, z_max, iterationen, dauer_s
```

`baue_gelaende(raum, weg, pauspapier, einstellungen=None, fortschritt=None) ->
Ergebnis`; `weg` sind `(x, y, z)` in Laufreihenfolge, mindestens zwei Punkte,
sonst `SpotlabError("Kein Weg gespeichert — das Gelände braucht den
gelaufenen Weg aus der Rekonstruktion.")`.

1. **Gitter** über der Hülle des Raums, erweitert um Weg und Pauspapier, plus
   1 m Rand; Knoten `(x0 + j · zelle, y0 + i · zelle)`.
2. **Gesperrt:** Zellen, deren Mitte näher als `max(wand_dicke, zelle) / 2` an
   einer Wand liegt; Zellen in einem Block; Zellen mit mindestens
   `punkte_je_zelle` Pauspapier-Punkten. Gesperrte Zusammenhänge nur aus
   Pauspapier unter `min_fleck` Zellen werden frei (Rauschen). Zellen des Wegs
   sind immer frei — der Roboter war dort.
3. **Weg:** jede Wegstrecke wird in Zellen abgetastet; das Profil `(s, z)` des
   Wegs wird nach Douglas-Peucker (`profil_toleranz`) geglättet und linear
   entlang der Strecken gelegt; eine Wegzelle bekommt den Mittelwert ihrer
   Proben. Wegzellen sind Dirichlet-Zellen.
4. **Region:** Abstand jeder Zellmitte zur Wegpolylinie (je Strecke vektorisiert);
   Flutfüllung von den Wegzellen über freie Zellen mit Abstand ≤ `abstand`.
   Danach werden Löcher gefüllt: freie Zellen ausserhalb der Region, die vom
   Gitterrand aus über Nicht-Regionszellen nicht erreichbar sind, kommen dazu
   (eingeschlossene Räume gehören zum Boden).
5. **Offene Ränder:** Regionszellen mit einem freien Nachbarn ausserhalb der
   Region. Zusammenhängende Läufe davon zählt der Bericht als `offen`.
6. **Membran:** Startwert je Regionszelle = Höhe der nächsten Wegzelle
   (Flutreihenfolge). Dann Über-Relaxation in Rot-Schwarz-Ordnung, `ω = 2 /
   (1 + sin(π / N))` mit `N = max(zeilen, spalten)`; jede freie Regionszelle
   wird `(1 − ω) · h + ω · Mittel der gültigen Nachbarn` (Neumann am Rand:
   nur Nachbarn in der Region), Wegzellen bleiben fest. Ende bei
   `max |Δh| < genau_m` oder `hoechstens_iterationen`.
7. **Null:** der tiefste Regionsknoten wird 0; `bericht["verschiebung"]` sagt,
   um wie viel alles rückte (bei einem Weg aus der Rekonstruktion 0, weil sein
   tiefster Punkt schon 0 ist und die Membran zwischen ihren Stützwerten bleibt).
8. **Gelände** mit `None` ausserhalb der Region.

Knoten und Zellen: das Raster ist ein Knotenraster; „Zelle" meint hier die
Umgebung eines Knotens (`zelle × zelle` um ihn). Sperren, Fluten und Membran
laufen auf den Knoten.

`fortschritt(text)` wird je Schritt gerufen („Sperren", „Fluten", „Membran 120
Iterationen"). Laufzeit Katakomben (etwa 230 × 200 Knoten): unter 2 s.

## 8 Dialog „Korrigieren…" (`gui/raumeditor/korrektur_dialog.py`)

`KorrekturDialog(eltern, raum, weg, pauspapier)`, nicht modal (`show()`), damit
die 2D-Sicht daneben bedienbar bleibt. Signale: `markiere(list)` (Strecken der
gewählten Zeile), `kandidaten(list)` (alle Strecken), `angewendet(object)`
(ein `Korrektur`-Ergebnis).

Oben eine Tabelle, je Zeile eine `Luecke`: Nr, Art (Lücke / Ecke / Anschluss /
Kreuzt), Länge in m, Vorschlag als `QComboBox` (Wand / Durchgang / lassen;
bei Kreuzt: Löschen / lassen; „unklar" wird als „lassen" vorgewählt und in
der Grund-Spalte gesagt), Grund. Zeilenwahl → `markiere`. Darunter:
`QCheckBox` „Gelände bauen" (nur mit Weg; sonst aus, mit Text „Kein Weg
gespeichert — nur die Wände"), `QDoubleSpinBox` „Boden bis … m neben dem
Weg" (0.5..6.0, Vorgabe 2.0), `QCheckBox` „n Rampen und m Podeste ins
Gelände übernehmen" (vorgewählt, wenn ein Weg da ist). Fortschrittszeile,
Knöpfe „Anwenden" und „Schliessen".

„Anwenden": erst `wende_an` mit den Entscheiden der Tabelle (sofort), dann —
wenn angehakt — `GelaendeArbeiter(QThread)` mit `baue_gelaende` auf dem
korrigierten Raum, danach `uebernimm_gelaende`. Ergebnis:

```python
@dataclass(frozen=True)
class Korrektur:
    raum: Raum
    offene_raender: list
    bericht: dict   # waende_verbunden, durchgaenge, geloescht, gelaende (bericht aus § 7 | None)
```

Der Tab übernimmt den Raum als EINEN Verlaufsschritt (`steuerung.uebernimm`,
ein neuer öffentlicher Name für `_uebernimm`), zeigt die offenen Ränder
(`setze_offen`), leert Markierung und Kandidaten und meldet: „Korrigiert: 12
Wände verbunden, 7 Durchgänge, 2 Wände gelöscht · Gelände 3120 Knoten, 0.00
bis 2.40 m, 4 offene Ränder". Der Dialog schliesst sich nach dem Anwenden.
Ctrl+Z macht die ganze Korrektur rückgängig.

## 9 Fehler und Meldungen

- Kein Weg (handgezeichneter Raum, altes Pauspapier PAUS1): Dialog bietet nur
  die Wände; das Gelände-Häkchen ist aus und erklärt sich.
- Keine Kandidaten und kein Weg: der Dialog sagt „Nichts zu korrigieren" und
  bietet nur Schliessen.
- `baue_gelaende` scheitert (numpy fehlt, Speicher): der Fehler steht in der
  Fortschrittszeile, die Wände sind trotzdem angewendet — als eigener
  Verlaufsschritt.
- Gelände-Datei fehlt beim Laden: `SpotlabError` wie in § 1; der Editor zeigt ihn
  in der Meldung, der Raum wird nicht geladen.
- Vorlagen mit `[gelaende]` gibt es nicht; ein Raum mit Gelände lässt sich
  wie jeder andere unter neuem Namen speichern (Binärdatei wird mitgeschrieben).

## 10 Tests

- `test_welt_gelaende.py`: `hoehe_bei` bilinear (Mitte von vier Knoten = Mittel),
  am Rand (drei gültige Knoten → nächster gültiger), ausserhalb `None`;
  `klippen` an einem Sprung von 0.5 m (eine Strecke, zusammengefasst), am
  Rand über 0.25 m, keine bei 0.2 m; `plateaus` auf zwei Ebenen mit Rampe
  dazwischen → zwei Werte; Datei hin und zurück (NaN ↔ None); `verschoben`.
- `test_welt_raum.py`: Raum mit Gelände speichern und laden (`fassung = 4`,
  `[gelaende]`, Binärdatei daneben); ohne Gelände keine Spur davon; fehlende
  Binärdatei → `SpotlabError`; `huelle` mit Gelände.
- `test_welt_hoehe.py`: `boden_bei` auf dem Gelände, Treppe auf dem Gelände
  gewinnt, `nick_grad` auf dem Gefälle, `ebenen` mit Plateaus, `boden_z`.
- `test_welt_kollision.py` / `test_welt_wahrnehmung.py`: eine Geländekante
  über 0.25 m hält den Roboter (`bewege_mit_hoehe` → „Kante"), das Gitter
  meldet sie als belegt; `klippen_von` liefert bei gleichem Raum dasselbe
  Objekt (Memo).
- `test_welt_pauspapier.py`: PAUS2 mit Weg hin und zurück; PAUS1 lesbar, Weg leer.
- `test_welt_bearbeitung.py`: Schlüssel `("gelaende", 0)`: verschieben, heben,
  löschen; drehen lässt es unberührt; `pruefe` meldet die schwebende Wand.
- `test_welt_korrektur.py`: drei Wände als U mit Tür und ein Weg durch die
  Tür — die Tür wird Durchgang (Grund Weg), die zwei Bruchstellen werden
  Wand (Grund Punkte), die Ecke schliesst (beide Enden auf S); Anschluss an
  eine Wandmitte; „kreuzt" für eine Wand quer über den Weg; ohne Weg und
  Punkte alles unklar; `wende_an` mit gemischten Entscheiden; keine
  Kandidaten durch eine dritte Wand hindurch; `uebernimm_gelaende` löscht
  Rampen und Podeste, nicht die Treppe, setzt `z` der Wände.
- `test_maps_gelaende_bau.py`: L-Gang 2 m breit mit Wänden, Weg mit 4° im einen
  Schenkel, eine 1-m-Lücke ohne Punkte im anderen: Gelände bis an die Wände
  (jede Regionszelle näher als 0.3 m an einer Wand oder mit gesperrtem
  Nachbarn), quer eben (Streuung je Querschnitt < 1 cm), längs 4° (±0.5°),
  genau ein offener Rand an der Lücke, keine Klippe entlang des Wegs, Weg
  durch eine gesperrte Zelle bleibt frei, Rauschfleck aus 2 Zellen sperrt
  nicht, Loch hinter einer Wandinsel wird gefüllt, tiefster Knoten 0.
- `test_maps_rekonstruktion.py`: `Ergebnis.weg` in Raumkoordinaten mit
  Bodenhöhe 0 im unteren Gang und 1.0 im oberen (synthetische Karte).
- `test_gui_raumzeichnung.py` / `test_gui_raumeditor_sicht2d.py`: `gelaende_bild`
  hat die Knotenmasse, Höhenlinien-Pixel an der 0.25-Grenze, blass ausserhalb
  der Ebene, durchsichtig ohne Boden; `setze_markierung` zeichnet ohne Fehler.
- `test_gui_raumeditor_geometrie3d.py`: `gelaende_dreiecke` zählt 2 Dreiecke
  je voller Zelle, 1 bei drei Knoten, Normale zeigt nach oben, Bänder stimmen.
- `test_backend_mujoco.py`: `welt_aus_raum` übergibt ein `Gelaende`;
  Fassung 5. matura-spot `test_puppe.py`: hfield-Höhe per Strahl an drei
  Stellen gegen das Raster (Zeilenrichtung), Berührung mit `gelaende` zählt
  nicht als Anstoss, `FASSUNG == 5`.
- `test_gui_raumeditor_korrektur.py` (Qt offscreen): Tabelle zeigt die
  Kandidaten mit Vorschlag und Grund, Zeilenwahl sendet `markiere`, Anwenden
  ohne Gelände ändert die Wände und einen Verlaufsschritt, mit Gelände
  (Arbeiter abgewartet) setzt `raum.gelaende`, Ctrl+Z stellt den alten Raum
  her; „Kein Weg" schaltet das Häkchen aus.
- `test_gui_raumeditor.py`: Listenzeile „Gelände · …", Eigenschaften nur
  lesend, Entf löscht es, Knopf „Korrigieren…" öffnet den Dialog.
- **Katakomben** (`skipif` ohne Karte, Laufzeit < 20 s): rekonstruieren,
  `finde_luecken` → mindestens 60 % der Kandidaten haben einen Vorschlag,
  `wende_an` mit den Vorschlägen, `baue_gelaende` → Gelände deckt jede Wegzelle,
  `bewege_mit_hoehe` entlang des gesamten Wegs (0.1-m-Schritte, `z_nahe`
  mitgeführt) ohne Anstoss und ohne Kante; der Weg im 2D-Sim (Backend
  `sim`, `walk` von Wegpunkt zu Wegpunkt) endet ohne `anstoss`-Ereignis.

## 11 Abnahme

- **A28 — Katakomben korrigiert:** Rekonstruieren, Korrigieren mit den
  Vorschlägen, unter `katakomben` speichern. In 2D den Weg mit `spot.move`
  nachfahren (Beispiel aus dem Abnahmeprotokoll), dann in MuJoCo; Bild aus
  der 3D-Sicht ins Protokoll. Erwartung: kein Anstoss, `spot.state.z` folgt
  dem Gefälle, die Treppe steht auf dem Gelände.

## 12 Etappen

1. **Gelände-Kern:** `welt/gelaende.py`, Raumformat v4 mit Datei, `boden_bei`,
   `neigung_bei`, `klippen`, `ebenen`, `boden_z`, Memo in `klippen_von`,
   `pruefe`, Pauspapier PAUS2 mit Weg, `Ergebnis.weg` und Tab (`_weg`).
2. **Sichten:** 2D-Bild mit Höhenlinien und Ebenen, Markierungen in `Sicht2D`,
   3D-Dreiecke, MuJoCo hfield und Puppe Fassung 5, Bearbeitung mit
   `("gelaende", 0)`, Listenzeile und Eigenschaften.
3. **Korrigierer:** `welt/korrektur.py`, `maps/gelaende_bau.py`, Dialog, Knopf,
   Katakomben-Test, README, ABNAHME A28, CLAUDE.md, Erinnerung.

## 13 Neue Regeln für CLAUDE.md

- **Der Grund ist das Gelände, wo es eines gibt, sonst 0** — und nur
  `boden_bei` entscheidet das. Kein Modul fragt `raum.gelaende` nach der Höhe
  an einem Punkt, ausser über `hoehe.py`.
- **Das Gelände wird nie von Hand gesetzt.** Es kommt aus `maps/gelaende_bau.py`,
  aus Wänden, Weg und Pauspapier. Wer es anders will, zieht Wände nach und
  lässt den Korrigierer neu laufen.
- **PAUS2 trägt den Weg** mit Bodenhöhe im Raumrahmen; er ist die Stütze des
  Geländes und das Signal „der Roboter lief hindurch". PAUS1 bleibt lesbar.
- **Farben mischt nur `theme.mische`.**

## 14 Nachträge beim Bau (07.09.2026)

- **Pauspapier-Punkte sperren nur den Rand.** Dichte Flecken mitten im Gang
  (Tiefen-Artefakte, die die Sichtprüfung für die Wände längst verworfen hatte,
  im Pauspapier aber liegen) rissen 991 Klippen in das erste Gelände der
  Katakomben. Jetzt wird alles Boden, was der Gitterrand über freie Knoten nicht
  erreicht (§ 7 Schritt 5); gesperrte Zusammenhänge am Rand — die Wand selbst,
  ein Punktband — bekommen nach der Membran die Nachbarhöhe **kopiert**, sie
  rechnen nicht mit: als Membranknoten leitete eine Wand Höhe an sich entlang
  und verzerrte den Gang daneben um Zentimeter. Freie Taschen hinter einem
  Punktband bekommen danach ebenfalls eine Kopie.
- **Zwei Fahrten durch denselben Gang mit bis zu 0.7 m Drift** (Auf- und
  Abstieg an der Treppe, Schleifen) rissen Klippen zwischen den Fahrspuren.
  Die Wegknoten mitteln sich vor der Membran im Umkreis von 1 m
  (`glaettung`; 0.5 m liess zwei Spuren 0.5 m nebeneinander getrennt). Weiche
  Stützen (gewichtetes Mittel aus Nachbarn und Profil) waren der erste Versuch;
  sie verzerrten den Querschnitt und sind verworfen.
- **Eine Flächenglättung** (ein Fünf-Punkte-Mittel, `glaettung_flaeche`) nach
  der Membran: am Ende eines Wegstummels auf tieferem Niveau setzte die Membran
  sonst eine 0.26-m-Stufe gegen das Nachbarniveau.
- **Geländeklippen unter einem Boden zählen nicht** (`hoehe.klippen`,
  stückweise je Zelle): die Treppe deckt das Gelände, das die Rekonstruktion
  darunter zur Rampe faltet.
- **Treppen stehen mit Fuss und Kopf auf dem Gelände**: `uebernimm_gelaende`
  setzt `z` und `anstieg` aus der Geländehöhe an beiden Enden; sonst lag der
  Kopf 0.3 m neben dem Boden dahinter.
- **Der Boden fliesst durch eine offene Lücke hinaus**, bis `abstand` neben dem
  Weg; der offene Rand liegt dann draussen. Gewollt: die Lücke ist eine
  Entscheidung, die der Autor in der Liste trifft.
- **Am Ende einer Stütze ist die Membran nicht exakt quer eben** (harmonische
  Lösung um das Ende der Wegstütze, etwa 3 cm auf 1 m im 2-m-Gang) — kein
  Hindernis, und die Tests sagen es so.
- `douglas_peucker` zog nach `welt/polylinie.py` (Standardbibliothek), damit
  `maps/gelaende_bau.py` ohne bosdyn auskommt.
- Das Gelände ist in 3D heller als die Böden (`mische(rand, text, 0.25 + 0.05·k)`),
  sonst setzte sich ein Podest darauf nicht ab.
- **Katakomben (07.09.2026):** 73 Kandidaten — 70 Wand, 1 Durchgang, 2 unklar;
  Gelände rund 6900 Knoten, 0 bis 2.3 m, 12 offene Ränder, 25 Rampen und Podeste
  gehen auf, die Treppe bleibt; der aufgezeichnete Weg läuft mit
  `bewege_mit_hoehe` ohne Anstoss durch (`tests/test_katakomben_korrektur.py`,
  rund 25 s inklusive Rekonstruktion).
