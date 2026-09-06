# Übungsraum 3D — Umsetzungsplan

> Wiedereinstieg nach Kontextverdichtung: hier nachsehen, welche Kästchen
> offen sind. Spec: `docs/superpowers/specs/2026-09-06-uebungsraum-3d-design.md`.
> Zweige: spotlab `uebungsraum-3d` (auf `dateibaum-verwalten`), matura-spot
> `wiedergabe-puppe` (auf `main`). Interpreter für beide Repos:
> `C:/Users/janis/miniconda3/python.exe`.

**Ziel:** `backend="mujoco"` lässt ein unverändertes Schülerprogramm im
3D-Zimmer laufen, mit Kameras, Tiefengitter, Tags und Kollision; das
Übungsfenster zeigt das gerenderte Bild.

**Regeln, die überall gelten:** TDD (Test zuerst, RED sehen); `spotsim`
importiert nie `spotlab`; unter `gui/` kein bosdyn/backends/mujoco; Farben nur
aus `theme.py`; Meldungen deutsch, Bezeichner englisch; was nicht gemessen ist,
steht als 0.0/null und wird im Bericht genannt.

---

## matura-spot

### T1 Puppe — Welt und Pose
- [x] `tests/test_puppe.py`: Welt mit einem Quader und einem Tag baut; `setze()` legt den Körper an (x, y, yaw); Standhöhe aus Kinematik liegt zwischen 0.35 und 0.60 m; Stand-Füsse berühren den Boden (|z − r| < 1 cm)
- [x] `src/spotsim/puppe.py`: `Welt`, `bau_modell(welt)`, `SpotPuppe.setze/standhoehe/pose`
- [x] Commit

### T2 Puppe — Kollision, Tags, Ansicht
- [x] Test: Pose in einem Quader → `kollisionen()` nennt `hindernis_0`; frei → leer; Bodenkontakt zählt nicht
- [x] Test: Tag vor dem Roboter sichtbar, hinter einer Wand nicht (Raycast), ausserhalb der Reichweite nicht, von hinten (abgewandt) nicht, seitlich ausserhalb jedes Blickfelds nicht
- [x] Test: `ansicht()` liefert (H, B, 3) uint8, nicht einfarbig
- [x] Test: `gray_image_proto` hat GREYSCALE_U8, 480×640, Fisheye-Intrinsik
- [x] `robot_state_proto(sensors, fusskontakte=None, v_body=None)` — Überschreibungen für die Wiedergabe, Standard unverändert
- [x] Commit

### T3 Gate G10 Gitterformat
- [x] `tests/daten/gitter_real_20260812/000001_obstacle_distance.pb` und `no_step.pb` kopieren (je ~31 KB) + `HERKUNFT.md`
- [x] `tests/test_gitterformat.py`: Sim-Proto gegen die Fixture (Zellen, Zellgrösse, Format, Skala, Frame-Suffix `_local_grid_corner`, `unknown_cells` vorhanden)
- [x] `local_grid.py`-Docstring: Annahme → „bestätigt am 12.08.2026"; G10 in `gates.py`-Katalog
- [x] Commit

### T4 Doku matura-spot
- [x] `notes/VISION_simulation.md`: RESEARCH DECISION 2026-09-06 (Weg A, Puppe neben der Physik)
- [x] `CLAUDE.md`: Regel „Realismus vor Bequemlichkeit" gilt für `SpotSdkSim`/Gates; `puppe.py` ist Wiedergabe gemessener Verläufe und sagt das
- [x] `pyproject.toml`: `scipy` fehlt als Abhängigkeit (local_grid importiert es) → eintragen
- [x] Commit

## spotlab

### T5 Körperantwort
- [x] `tests/test_kalibrierung_antwort.py`: aus einem synthetischen Lauf (Kommando + Rückmeldung + Geschwindigkeitsverlauf) kommen Spitze, Dauer, Beschleunigung; echte Läufe vom 02.09. liefern ≥ 3 Fahrt- und ≥ 1 Drehpunkt; `Antwortmodell.tempo(v, d_rest, dt)` steigt mit a, bremst mit sqrt(2·a·d), überschreitet den Deckel nie
- [x] `src/spotlab/kalibrierung/antwort.py` + `daten/antwort.json` (aus `spotProjects/run/runs`) + `python -m spotlab.kalibrierung.antwort <ordner>`
- [x] Commit

### T6 2D-Sim fährt die Antwort
- [x] Test: `move(forward=1.0)` im Sim dauert 1.8–3.0 s (Sim-Uhr) statt 1/tempo_vorschlag; Tempo überschreitet `limits.max_speed` nie; ausserhalb (1 m/90°) → `bericht()["antwort"]["ausserhalb_der_messung"]`
- [x] `SimBackend._zum_ziel` nutzt das Antwortmodell; bestehende Tests anpassen, die Dauer annehmen
- [x] Commit

### T7 Adapter `backends/mujoco.py`
- [x] Tests (skip ohne spotsim/Asset): Backend läuft `power_on/stand/move` durch; Pose stimmt mit 2D-Rechnung überein; Kollision an einer Wand des Raums `durchgang` → `angestossen`; `local_grid()` liefert `ObstacleGrid` 128×128 mit `known`; `world_objects()` findet Tag 3 im `durchgang` erst durch die Tür; `images()` liefert zehn Quellen; `robot_state()` trägt Fusspositionen ≠ 0
- [x] `src/spotlab/backends/mujoco.py`; `welt_aus_raum(raum)`
- [x] `spotlab/__init__.py`: `"mujoco"` in `OHNE_ROBOTER`, Zweig in `connect()`, `ansicht_ziel`
- [x] `pyproject.toml`: Extra `sim`
- [x] Naht-Test: nur `backends/mujoco.py` importiert `spotsim` (ast)
- [x] Commit

### T8 Gate G11 Wiedergabe
- [x] `tests/test_wiedergabe.py`: Stützstelle 5 Zyklen → Weg ± 2 %, Duty ± 0.1, Eindringen ≤ 1 cm, Standhöhe berichtet
- [x] Commit

### T9 GUI
- [x] Tests: `BACKENDS` enthält „mujoco" nur mit `find_spec("spotsim")`; `RunScanner` meldet `ansicht` bei neuer mtime; `Uebungsfenster.zeige_ansicht` zeigt ein Bild; Übungsraum-Knopf nimmt „mujoco" wenn vorhanden
- [x] `editor/view.py`, `watcher.py`, `uebungsfenster.py`, `app.py`
- [x] Commit; Screenshot mit echtem Lauf

### T10 Abschluss
- [x] README (Übungsraum 3D, Installation `pip install -e .[sim]` + `pip install -e ../matura-spot`), `docs/ABNAHME.md` (A22 wirkt auch auf 3D), Vorlage `uebungsraum.py`
- [x] Volle Suiten beider Repos, ruff; Speicher aktualisieren
- [x] Commit
