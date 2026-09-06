# Übungsraum 3D — Wiedergabe statt Regelung (Weg A)

Entwurf vom 06.09.2026. Entscheidung des Autors im Gespräch: **Weg A**. Die
Beine fahren die gemessenen Gelenkverläufe ab, der Körper folgt der gemessenen
Antwort auf Kommandos, Physik nur noch für Kollision und Sensorik. Kein eigener
Regler, kein RL — der Lokomotionsregler von Boston Dynamics ist geschlossen,
und ein Sim, der die **Ergebnisse** dieses Reglers reproduziert, ist für
„virtuell programmieren und testen" das Richtige.

Gegenstück in `matura-spot`: RESEARCH DECISION 2026-09-06 in
`notes/VISION_simulation.md`. Die Physik-Sim dort (`SpotSdkSim`, Gates G1–G9)
bleibt unverändert; die Wiedergabe steht daneben, nicht an ihrer Stelle.

## Ziel

Ein Schülerprogramm, das heute im 2D-Übungsraum läuft, läuft **unverändert**
mit `backend="mujoco"` in einem 3D-Zimmer: derselbe Menagerie-Spot wie in der
Maturaarbeit, echte Tiefen- und Graukameras, ein Hindernisgitter aus Tiefe
(mit Verdeckung und unbekannten Zellen — wie am Roboter), AprilTags mit
Sichtlinie und Kamerablickfeld, Kollision an der echten Geometrie. Das
Übungsfenster zeigt die Fahrt als gerendertes Bild.

## Nicht-Ziele

- Keine Physik der Beine, kein Umfallen, kein Rutschen, keine Treppe. Das ist
  Weg B und bleibt in `matura-spot`.
- Keine Fisheye-Verzeichnung (MuJoCo rendert Lochkamera; gemessene Intrinsik).
- Kein Ersatz der 2D-Ansicht: sie bleibt, ohne MuJoCo, für jeden Laptop.

## Was gemessen ist — und was nicht

| Grösse | Quelle | Status |
|---|---|---|
| Gelenkwinkel je Gangphase, Duty, Zyklusdauer | `kalibrierung/daten/gang.json`, 24 Stützstellen 0.07–0.85 m/s, Messfahrt 12.08.2026 | **gemessen** |
| Körperantwort auf `move(forward=1.0)` und `move(turn=90)` | zwei bzw. ein kommandierter Lauf vom 02.09.2026 (`spotProjects/run/runs/20260902T15*`) | **gemessen**, nur diese zwei Punkte |
| Antwort auf andere Strecken/Winkel | Trapezprofil mit den gemessenen Beschleunigungen | **Annahme**, Real-Prozedur: `gates_real.py` hinter A1 |
| Gitter 128×128 × 3 cm, INT16, Skala 0.001, `unknown_cells` | echte `LocalGridResponse` vom 12.08.2026 (`out/beobachtung/*/gitter/`) | **gemessen** — bestätigt die bisherige Annahme in `spotsim/local_grid.py` |
| Kamera-Intrinsik, Auflösungen, Tiefenskala 999 | Steckbrief 12.08.2026 | **gemessen** |
| Kameraposen am Körper | aus der Menagerie-Geometrie geschätzt | Annahme (Werkzeug `spot-lab/tools/kamera_extrinsics.py` liest sie am Gerät) |
| Tag-Reichweite 3.0 m | Schätzung | Annahme, Real-Prozedur A22 |
| Standhöhe | folgt aus den gemessenen Winkeln über die Modell-Kinematik (Füsse am Boden) | **abgeleitet**; die Differenz zur gemessenen `hoehe_m` wird berichtet, nicht versteckt |

Was nicht gemessen ist, steht als `null` oder `0.0` in der Aufzeichnung —
dieselbe Regel wie im 2D-Sim: Gelenklasten 0.0, kein `terrain`.

## Architektur

```
spotlab                                   matura-spot (spotsim)
────────────────────────────────          ──────────────────────────────────
backends/sim.py   SimBackend  ──erbt──►   (nichts)
backends/mujoco.py MujocoBackend ──ruft──► puppe.py  SpotPuppe
   Kommandos, Ziele, Gangphase,              qpos setzen, Kollision, Kameras,
   Antwortmodell, Aufzeichnung               Gitter, Tags, Ansicht rendern
kalibrierung/antwort.py  Antwortmodell    sensors.py, local_grid.py (bestehend)
welt/raum.py  Raum  ──welt_aus_raum──►    puppe.Welt (Quader + Tags, reine Daten)
```

**Abhängigkeitsregeln, beide erhalten:**

- `spotsim` importiert **nie** `spotlab`. Die Puppe kennt weder Gänge noch
  Kommandos; sie bekommt Pose und zwölf Winkel gesagt und liefert Wahrnehmung.
- `spotlab` importiert `spotsim` **nur** in `backends/mujoco.py`, hinter dem
  Extra `spotlab[sim]`. Fehlt es, sagt die Fehlermeldung, was zu tun ist.
- Unterhalb von `gui/` weiterhin kein `bosdyn`, kein `spotlab.backends`, kein
  MuJoCo. Das Übungsfenster liest ein Bild aus dem Lauf-Verzeichnis.

### `spotsim/puppe.py`

- `Welt(boxen, tags)` — reine Daten: Quader `(name, x, y, z, hx, hy, hz)` und
  Tags `(id, x, y, z, yaw)`. Gebaut über `mjSpec` auf `build_sensor_spec()`,
  damit die fünf Kamerapaare da sind. Tags sind dünne Quader mit Body
  `tag_<id>`.
- `SpotPuppe(welt=None)`:
  - `setze(x, y, yaw, gelenke, hoehe=None)` — Freigelenk und zwölf Winkel
    schreiben, `mj_forward`. Ohne `hoehe`: Körperhöhe aus der Kinematik, tiefster
    Fuss auf dem Boden (Fussradius berücksichtigt).
  - `kollisionen()` — Kontaktpaare Roboter × Welt, ohne Boden. Namen der
    getroffenen Körper (`wand_*`, `hindernis_*`, `tag_*`).
  - `standhoehe(gelenke)` — die abgeleitete Höhe, für den Bericht.
  - `sichtbare_tags(reichweite_m, max_schraeg_grad)` — Tag in Reichweite, im
    horizontalen Blickfeld einer Graukamera (aus der Intrinsik), zur Kamera
    gewandt, **Sichtlinie per `mj_ray`** von der Kamera zum Tag-Zentrum.
  - `local_grid(typ)`, `depth_image(name)`, `gray_image(name)`,
    `robot_state(fusskontakte, v_body)`, `frame_tree_snapshot()` — dünne
    Hüllen über `sensors.py`/`local_grid.py`; `gray_image_proto` neu, spiegelt
    `depth_image_proto`.
  - `ansicht(breite, hoehe)` — RGB-Bild einer festen Zimmerkamera, die den
    ganzen Raum zeigt.
- Alle Renderer entstehen im Thread des ersten Aufrufs und werden nur dort
  benutzt; die Puppe führt ein `threading.Lock` um Zustand und Renderer.

### `spotlab/backends/mujoco.py`

`MujocoBackend(SimBackend)` überschreibt genau das, was 3D besser kann:

| Methode | 2D-Sim | MujocoBackend |
|---|---|---|
| `_bewege_gegen_welt` | Kreis 0.35 m gegen Segmente | Puppe setzen, `kollisionen()` prüfen, in Teilschritten ≤ 0.10 m wie `welt/kollision.bewege`; Drehen immer erlaubt; `angestossen`-Flanke unverändert |
| `local_grid` | Abstandsgitter aus der Raumgeometrie | Tiefenbilder → `local_grid_proto` → `gitter_aus()` (derselbe Entpacker wie am echten Spot) |
| `world_objects` | Reichweite + Sichtlinie in 2D | Reichweite + Kamerablickfeld + Ausrichtung + `mj_ray` |
| `image_sources`/`images` | keine Kameras | fünf Tiefen- und fünf Graukameras als `ImageResponse` |
| `robot_state` | Winkel aus dem Gangmodell, Füsse `-hoehe` | dazu Fusspositionen aus der Kinematik, IMU der Puppe |
| `frame_tree_snapshot` | odom/body | Puppe (odom = Welt = Raumkoordinaten, dazu Kamera-Frames) |
| `capabilities` | LOCOMOTION/POSTURE/POWER (+WORLD_OBJECTS/LOCAL_GRID mit Raum) | dazu DEPTH_CAMERAS/GRAY_CAMERAS |

Nach jedem `_fortschreiben` wird die Puppe synchronisiert: Pose aus
`self._pose`, Winkel aus `modell.gelenke(tempo, wz, phase)`. Steht der Roboter
still, gelten die Winkel der Phase 0 der langsamsten Gangart — es gibt keine
gemessene Stand-Haltung, das steht so im Bericht.

**Ansicht:** liegt `ansicht_ziel` vor, rendert das Backend im Thread, der es
erzeugt hat (der Schülerprozess), höchstens 10-mal je Sekunde ein Bild und
schreibt es atomar als `<lauf>/ansicht.jpg` (temporär + `os.replace`). Kein
Strom von Dateien: ein Zehn-Minuten-Lauf hinterliesse sonst 180 MB.

### `spotlab/kalibrierung/antwort.py`

Aus **kommandierten** Läufen (`backend == "real"`): je `move`-Kommando das
Fenster bis zur Rückmeldung, daraus Spitzentempo, Dauer, Beschleunigung
(lineare Anpassung der ansteigenden Flanke bis 80 % der Spitze) und
Verzögerung; für `turn` dasselbe mit der Drehrate. Ergebnis
`daten/antwort.json` mit Herkunft je Punkt.

`Antwortmodell`: Trapezprofil. Für ein Ziel im Abstand `d` mit Deckel `v_max`:

```
v ← min(v_max, v + a·dt, sqrt(2·a_brems·d_rest))
```

Deterministisch, ohne Zeitbuchführung; dieselbe Regel für die Drehung.
Damit ersetzt das Modell `tempo_vorschlag` (bisher ein eingestandener
Platzhalter) in `SimBackend._zum_ziel` — **2D und 3D** fahren ab jetzt die
gemessene Antwort. Ausserhalb der gemessenen Punkte (1 m, 90°) ist das
Profil eine Annahme und `bericht()` sagt das.

### Kopplung

- Backend-Name `"mujoco"`; in `OHNE_ROBOTER` (Erlaubnisliste) eingetragen;
  `connect()` behandelt ihn wie `sim` (Raum aus Argument, Umgebung,
  Konfiguration) und übergibt `ansicht_ziel=recorder.dir / "ansicht.jpg"`.
- `pyproject.toml`: Extra `sim = ["mujoco>=3.9,<4", "scipy>=1.12,<2",
  "numpy>=2,<3"]`; `spotsim` selbst wird aus `../matura-spot` editierbar
  installiert (kein PyPI-Paket). `backends/mujoco.py` prüft
  `spotsim.puppe.FASSUNG`.
- GUI: „Wo läuft es?" bekommt „Übungsraum 3D (MuJoCo)", angezeigt nur, wenn
  `importlib.util.find_spec("spotsim")` etwas findet. Der Startknopf im
  Übungsraum nimmt 3D, wenn es installiert ist, sonst 2D.
- `RunScanner` meldet `("ansicht", pfad)`, wenn sich die Änderungszeit von
  `ansicht.jpg` ändert; `Uebungsfenster.zeige_ansicht(pfad)` zeigt das Bild
  über der Zeichnung.

## Gates

- **G10 Gitterformat** (matura-spot, `tests/test_gitterformat.py`): eine echte
  `LocalGridResponse` vom 12.08.2026 liegt als Fixture unter `tests/daten/`;
  das Sim-Gitter muss in Zellenzahl, Zellgrösse, `cell_format`,
  `cell_value_scale`, Frame-Namensschema und Vorhandensein von
  `unknown_cells` übereinstimmen. Kodierung darf RAW statt RLE sein (beide
  Leser verstehen beides).
- **G11 Wiedergabe** (spotlab, `tests/test_wiedergabe.py`, übersprungen ohne
  `spotsim`/Asset): die Puppe fährt eine Stützstelle fünf Zyklen lang.
  Zurückgelegter Weg = tempo·t ± 2 %; Bodenkontakt-Anteil je Bein = gemessene
  Duty ± 0.1; Standfüsse dringen höchstens 1 cm in den Boden; die
  Kinematik-Standhöhe wird gegen `hoehe_m` **berichtet**.
- **Naht-Gate**: `backends/mujoco.py` ist die einzige Datei unter
  `src/spotlab/`, die `spotsim` importiert (per `ast`).

## Schritte

Der Plan in `docs/superpowers/plans/2026-09-06-uebungsraum-3d.md`. Reihenfolge:
Puppe → Antwort → Adapter → Gates → GUI → Doku. Jeder Schritt hinterlässt
ein grünes Repo.
