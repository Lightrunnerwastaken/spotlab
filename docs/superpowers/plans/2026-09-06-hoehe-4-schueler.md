# Höhe, Etappe 4 „Schüler" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `spot.stairs()` in Sim und am Roboter, die Vorlage „treppe", das Beispiel `treppe_steigen.py` (vorwärts hoch, rückwärts runter) mit Tests in 2D und 3D, Abnahmepunkte A25–A27, B6 im Messfahrt-Ablauf, README und CLAUDE.md.

**Architecture:** `Staircase(WorldObject)` in `backends/base.py`, `Capability.STAIRS`, `api/world.py::stairs`, `api/spot.py::stairs`; Sim aus `welt/hoehe.py::treppe_vor` und den Treppen des Raums, Roboter aus `staircase_properties` in `backends/real/wahrnehmung.py`.

**Spec:** `docs/superpowers/specs/2026-09-06-hoehe-treppen-design.md` (§ 7, 10)

## Global Constraints

- Neue Fähigkeit ⇒ `Capability.STAIRS`, `require()`, Abnahmepunkt.
- `api/` protobuf-frei; die Umwandlung wohnt in `backends/real/wahrnehmung.py`.
- Beispielprogramme laufen unverändert in 2D, 3D und am Roboter.

---

### Task 1: `Staircase`, Fähigkeit, Verb

**Files:** Modify `src/spotlab/backends/base.py`, `src/spotlab/api/world.py`, `src/spotlab/api/spot.py`, `src/spotlab/backends/dryrun.py`, `src/spotlab/backends/sim.py`; Tests `tests/test_api_world.py` (oder wo `tags()` geprüft wird), `tests/test_backend_sim.py`.

- [ ] **Tests:** Sim mit Vorlage treppe, Start (1, 2, 0): `stairs()` → eine `Staircase(direction="auf", steps=7, rise_m≈1.2, axis_bearing≈0, distance≈1.5)`; von oben (5.5, 2, 180): `direction == "ab"`; Dryrun → `[]`; `require` ohne Fähigkeit → `UnsupportedCapability`; Protokoll `kommando stairs` mit `treffer`.
- [ ] **Implement:** Dataclass, Flag, `world.stairs(backend, recorder)`, `Spot.stairs()`, `SimBackend.stairs()` (alle Treppen in `TAG_REICHWEITE_M` mit Sicht, `treppe_vor` für die nächste liefert Richtung; für entferntere Richtung aus Nähe zu Fuss/Kopf), `DryRunBackend.stairs()`.
- [ ] Commit `feat(api): spot.stairs() -- Treppen mit Richtung, Stufen und Achse`.

### Task 2: Treppen am Roboter

**Files:** Modify `src/spotlab/backends/real/wahrnehmung.py`, `src/spotlab/backends/real/session.py`; Test `tests/test_backend_real_wahrnehmung.py` (dort, wo `objekte_holen` getestet wird — `grep -rn objekte_holen tests/`).

- [ ] **Tests:** Ein gebautes `WorldObject`-Protobuf mit `staircase_properties.staircase_with_landings` (zwei Stufen à 0.17, Landungen) und Transformbaum `body → staircase`-Frame → `Staircase` mit `steps == 2`, `rise_m ≈ 0.34`, `direction == "auf"`, Peilung aus der Lage.
- [ ] **Implement:** `objekte_holen` wandelt `staircase_properties` (beide Formen: `staircase_with_landings` und ältere `stairs`), `RealSpot.stairs()` liest `world_objects` mit Filter `WORLD_OBJECT_STAIRCASE` (Enumname prüfen: `grep STAIRCASE` in `world_object_pb2`).
- [ ] Commit `feat(real): Treppen aus den Weltobjekten des Roboters`.

### Task 3: Vorlage „treppe" und Beispiel `treppe_steigen.py`

**Files:** Create `src/spotlab/welt/vorlagen/treppe.toml`, `src/spotlab/workshop/beispiele/treppe_steigen.py`; Modify `src/spotlab/workshop/beispiele/README.md`; Tests `tests/test_workshop_beispiele.py`, `tests/test_welt_raum.py` (Vorlage lädt, Start frei, Treppe 7 Stufen à 0.171 m < MAX_STUFE).

- [ ] **Tests:** wie in der Spec § 7: 2D-Lauf ohne `angestossen`/`treppe_verweigert`, `z` im Lauf > 1.0 und am Ende < 0.1, Ausgabe „Oben" und „Unten"; 3D (`skipif spotsim`); falsch herum (`treppe_falsch.py` als Testskript in `tmp_path`, nicht als Beispiel) → `treppe_verweigert` mit `verlangt == "rückwärts runter"`.
- [ ] **Implement** das Beispiel mit denselben Bausteinen wie `durchgang_finden.py` (laufend fahren, `walk(stop=False)`, Zeitgrenze).
- [ ] Commit `feat(beispiele): treppe_steigen.py und Vorlage treppe`.

### Task 4: Abnahme, Messfahrt, Doku

**Files:** Modify `docs/ABNAHME.md` (A25, A26, A27), `matura-spot/notes/MESSFAHRT_ABLAUF.md` (B6 ausformulieren: hoch vorwärts, Messfenster; runter rückwärts, Messfenster; Hinweis, dass die Puppe daraus den Treppengang spielt), `README.md` (Räume mit Höhe, `stairs()`, Treppenregel, `treppen` in config.toml), `CLAUDE.md` (Umsetzungsstand Stufe 13 komplett, Regeln § 12), Gedächtnis (`memory/spotlab-project.md`).

- [ ] Commit `docs: Stufe 13 -- Hoehe, Rampen, Treppen`.

### Task 5: Abschluss

- [ ] Volle Suite beider Repos, ruff; Merge-Menü.
