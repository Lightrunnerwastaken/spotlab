# Höhe, Etappe 3 „Rekonstruktion" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aus einer GraphNav-Karte Treppen (aus den Treppenkanten des SDK), Rampen (aus dem Höhenprofil des Wegs) und Ebenen (Podeste aus den Bodenzellen der Punktwolke) rekonstruieren; das grösste Plateau ist Höhe 0; Bericht und Dialog nennen die Zahlen.

**Architecture:** Neue Funktionen in `maps/rekonstruktion.py` nach dem Wändefinden und rund um `ausrichten`; die synthetische Karte im Test bekommt Höhe und Treppenannotationen.

**Tech Stack:** numpy, bosdyn-Protobufs (nur hier), `welt/raum.py::Boden`.

**Spec:** `docs/superpowers/specs/2026-09-06-hoehe-treppen-design.md` (§ 6)

## Global Constraints

- Protobufs nur unter `maps/` und `backends/`. Die GUI bekommt `Raum`, Punkte, Bericht.
- Katakomben-Test mit `skipif`, wenn der Ordner fehlt; Laufzeit unter 15 s.
- Alles in `Einstellungen` mit Vorgaben: `stufe=STUFE_VORGABE_M`, `rampe_min_laenge=2.0`, `rampe_min_grad=2.0`, `profil_toleranz=0.10`, `ebenen_zelle=0.25`, `max_boeden=60`, `treppen_breite=1.2`.

---

### Task 1: Synthetische Karte mit Höhe, Treppe und Rampe

**Files:** Modify `tests/test_maps_rekonstruktion.py` (Fixture-Generator).

- [ ] Die Fixture bekommt Parameter `hoehen` (z je Wegpunkt), `treppen_kanten` (Kantenindizes mit `stairs.state = SET`), und die Wolken je Wegpunkt tragen Bodenpunkte auf `z` des Wegpunkts minus 0.54 sowie die Wände darüber. Gang A: 5 Wegpunkte auf 0.0; Treppe: zwei Kanten, +0.5 m je Kante; Gang B: 4 Wegpunkte auf 1.0; Rampe: 5 Wegpunkte über 5 m von 1.0 auf 1.35 (4°). Ein Test prüft nur die Fixture (Höhenprofil wie bestellt).
- [ ] Commit `test(maps): synthetische Karte mit Treppe und Rampe`.

### Task 2: Höhenprofil und Treppen

**Files:** Modify `src/spotlab/maps/rekonstruktion.py`; Test `tests/test_maps_rekonstruktion.py`.

**Interfaces:** `weg(graph) -> [wp_id]` (Aufnahmereihenfolge), `treppen_aus(graph, posen_, boeden, band, e) -> [Boden]`, `Einstellungen.stufe`, `.treppen_breite`.

- [ ] **Tests:** `treppen_aus` auf der Fixture → eine Treppe mit `anstieg ≈ 1.0`, `stufen == 6`, Achse entlang der Kanten, Breite aus den Bandpunkten (Fixture-Gang 2 m → ≈ 2.0, Toleranz 0.3), `z ≈ 0`.
- [ ] **Implement:** Treppenkanten als Kette in Wegfolge; Achse vom ersten zum letzten Wegpunkt; Breite: Bandpunkte im Rechteck der Kette, quer projiziert, 5.–95. Perzentil, sonst `treppen_breite`; negativer Anstieg → Achse drehen (`drehung += 180`).
- [ ] Commit `feat(maps): Treppen aus den Treppenkanten der Karte`.

### Task 3: Rampen aus dem Profil

**Interfaces:** `douglas_peucker(punkte, toleranz) -> [index]`, `rampen_aus(weg_, posen_, boeden, treppen, waende, e) -> [Boden]`.

- [ ] **Tests:** `douglas_peucker` auf einer Geraden mit Knick → zwei Stücke; `rampen_aus` auf der Fixture → eine Rampe mit `neigung_grad ≈ 4` (±1), Länge ≈ 5, Breite ≈ Gangbreite; kein Rampen-Stück im flachen Gang.
- [ ] **Implement:** Profil `(s, z)` entlang des Wegs ohne Treppenketten; Stücke ≥ `rampe_min_laenge` und |Gefälle| > `rampe_min_grad`; Breite = 2 × min. Wandabstand des Stückmittelpunkts (aus `waende`), gedeckelt 3.0, Rückfall 2.0.
- [ ] Commit `feat(maps): Rampen aus dem Hoehenprofil des Wegs`.

### Task 4: Ebenen und Nullhöhe

**Interfaces:** `ebenen_aus(bodenpunkte, treppen, rampen, e) -> ([Boden], verschiebung)`, `groesstes_rechteck(zellen) -> (i0, j0, i1, j1)`.

- [ ] **Tests:** Fixture → das grössere Plateau (Gang A) wird 0, Gang B ein Podest mit `z ≈ 1.0` (ein oder zwei Rechtecke); alle Tags und der Start um dieselbe Verschiebung; `groesstes_rechteck` auf einem L-Muster.
- [ ] **Implement:** Bodenpunkte je Schnappschuss (`z < boden + 0.15`), 0.25-m-Zellen mit Mittelhöhe (im ausgerichteten Rahmen — die Punkte werden mit `ausrichten` mitgedreht: `ausrichten` gibt die Drehung zurück, die Bodenpunkte werden danach gedreht); Plateaus per Flutfüllung (|Δz| ≤ MAX_STUFE); Zellen unter Treppen/Rampen raus; grösstes Plateau → Höhe 0; gierige Zerlegung mit `groesstes_rechteck` (Histogramm-Verfahren), Abbruch bei < 0.5 m Kante oder `max_boeden`.
- [ ] Commit `feat(maps): Ebenen als Podeste, groesstes Plateau ist Hoehe 0`.

### Task 5: Zusammenbau, Bericht, Dialog

**Files:** Modify `src/spotlab/maps/rekonstruktion.py::rekonstruiere`, `src/spotlab/gui/raumeditor/rekonstruktion_dialog.py`; Tests `tests/test_maps_rekonstruktion.py`, `tests/test_gui_raumeditor_rekonstruktion.py`.

- [ ] **Tests:** `rekonstruiere(fixture)` → `raum.boeden` enthält Treppe, Rampe, Podest; `bericht` hat `treppen == 1`, `rampen == 1`, `boeden >= 3`, `ebenen == [0.0, 1.0]`, `gefaelle_grad ≈ 4`; Katakomben (`skipif`): `treppen >= 1`, eine Treppe mit `1.2 <= anstieg <= 1.4`, `1 <= gefaelle_grad <= 8`, Dauer < 15 s; Dialog-Vorschau nennt „Treppen", „Rampen", „Ebenen".
- [ ] **Implement:** Reihenfolge in `rekonstruiere`: Wände → Treppen → Rampen → `ausrichten` (dreht Wände, Tags, Start, Pauspapier, Böden, Bodenpunkte) → `begradige` → Ebenen (Podeste, Verschiebung aller z) → Raum. Hinweis bei Höhensprüngen ohne Treppenmarkierung.
- [ ] Commit `feat(maps): Rekonstruktion mit Treppen, Rampen und Ebenen`.

### Task 6: Abschluss

- [ ] Katakomben einmal rekonstruieren, Bild aus dem Editor (3D) an den Autor; Suite, ruff; `CLAUDE.md` Umsetzungsstand „Etappe 3". Commit `docs: Stufe 13 Etappe 3 -- Rekonstruktion mit Hoehe`.
