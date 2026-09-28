# Physikmodus Stufe B — Sitzen, Aufstehen, Körperhaltung: Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, keine Sub-Agenten — Nutzerwunsch). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der Physikmodus sitzt am Anfang, steht über die gemessene Gelenkbahn auf, setzt sich hin, schaltet
beim `power_off` ab und hält im Stand eine befohlene Körperhaltung.

**Architecture:** Die Daten (mittlere Aufstehbahn) zieht spotlab aus echten Läufen; matura-spot bekommt eine
wörtliche Kopie, ein Modul `spotsim/haltung.py`, Übergänge in `SpotSdkSim` und die Haltung als MPC-Ziel im
Kraftregler. spotlab adaptiert Start, Rückmeldung, `power_on/off` und `pose()` und erkennt die Fähigkeit an
`spotsim.HALTUNG_FASSUNG`.

**Tech Stack:** Python 3.13 (Miniconda), MuJoCo, bosdyn-client, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-28-physik-haltung-design.md`

## Global Constraints

- Interpreter: `C:/Users/janis/miniconda3/python.exe`; Tests `-m pytest … -q -p no:cacheprovider`; Lint `-m ruff check .`.
- spotlab-Arbeitskopie `D:\Users\janis\Documents\Matura\spotlab\.worktrees\haltung` (Branch `feat/physik-haltung`).
- matura-spot-Arbeitskopie `D:\Users\janis\Documents\Matura\matura-spot-haltung` (Branch `feat/haltung` von
  `sim-module-nachtragen`); die fremden, nicht committeten Dateien im Hauptcheckout NIE anfassen.
- Tests gegen die Arbeitskopien: `PYTHONPATH=<spotlab-wt>/src;<matura-wt>/src` — sonst lädt Python die
  installierten Hauptcheckouts. Unterprozess-Tests setzen PYTHONPATH selbst.
- `haltung="stehend"` (Vorgabe von `SpotSdkSim`) bleibt bitgleich: Gates und Nachspielen unverändert.
- Gemessen (Spec): Hub 0.41 m, Aufstehen 0.9 s nach 0.28 s; Sitz hx 0.52/0.57, hy 1.40, kn −2.80 (gekappt auf
  Modellgrenze −2.7929). Annahmen: H2 Hinsetzen = Umkehr, H3 Haltungswechsel in 1 s.
- API-Grenzen `pose()`: Roll/Nick ±20°, Gier ±30°, Höhe ±0.15 m.
- Commit-Nachrichten deutsch mit ue/ae, Absatz „Tests:“, Trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Kein Push ohne „push …“ des Nutzers. matura-spot hat kein Remote.

---

### Task 1: spotlab — Aufstehbahn aus echten Läufen (`kalibrierung/haltung.py`)

**Files:**
- Create: `src/spotlab/kalibrierung/haltung.py`, `src/spotlab/kalibrierung/daten/haltung.json` (erzeugt)
- Test: `tests/test_kalibrierung_haltung.py`

**Interfaces:**
- Produces: `GELENKE` (12 Namen `fl.hx`… in Reihenfolge fl, fr, hl, hr × hx, hy, kn), `PUNKTE = 11`,
  `aufstehvorgaenge(lauf_dir) -> list[dict(verzug_s, dauer_s, hub_m, bahn: list[list[float]])]`,
  `haltung(lauf_dirs) -> dict(verzug_s, dauer_s, hub_m, gelenke, bahn, anzahl, herkunft)`, `DATEI`,
  `main(argv)` (`python -m spotlab.kalibrierung.haltung <runs-Ordner>…`).

- [ ] **Step 1: Test mit einem gebauten Lauf** (lauf.json backend real, ein `kommando` stand bei t=10,
  zustand.jsonl 10 Hz: z 0.10 bis t=10.2, linear auf 0.51 bis t=11.2, dann ruhig; Gelenke linear von Sitz
  auf Stand). Erwartet: ein Vorgang, `verzug_s` ≈ 0.2, `dauer_s` ≈ 1.0 (± 0.1), `hub_m` ≈ 0.41, Bahn[0]
  = Sitzgelenke, Bahn[-1] = Standgelenke (± 0.02). Zweiter Test: ein Lauf mit backend `mujoco` zählt nicht;
  ein `stand` aus dem Stehen (Hub < 0.2 m) zählt nicht.

```python
def _lauf(tmp_path, backend="real", hub=0.41):
    d = tmp_path / "20260101T000000Z_x"; d.mkdir()
    (d / "lauf.json").write_text(json.dumps({"backend": backend}), encoding="utf-8")
    (d / "ereignisse.jsonl").write_text(json.dumps(
        {"t": 10.0, "art": "kommando", "daten": {"name": "stand"}}) + "\n", encoding="utf-8")
    zeilen = []
    for i in range(0, 160):
        t = 9.0 + i * 0.1
        u = min(1.0, max(0.0, (t - 10.2) / 1.0))
        gel = {n: {"position": SITZ[k] + u * (STAND[k] - SITZ[k])} for k, n in enumerate(haltung.GELENKE)}
        zeilen.append(json.dumps({"t": t, "daten": {"z": 0.10 + u * hub, "joints": gel}}))
    (d / "zustand.jsonl").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return d
```

- [ ] **Step 2:** Test laufen lassen → FAIL (Modul fehlt).
- [ ] **Step 3: Umsetzen.** Bewegungsbeginn `a` = letzte Probe mit |z − z0| ≤ 0.01 (z0 = Median der Sekunde vor
  dem Kommando), Ende `e` = erste Probe, ab der 5 Proben lang max−min von z < 0.005; `verzug_s = t_a − t_kmd`,
  `dauer_s = t_e − t_a`, `hub_m = z_e − z0`, Vorgang nur bei `hub_m > 0.2` und nur `backend == "real"`
  (Erlaubnisliste wie in `kalibrierung/`). Bahn: je Gelenk linear auf u = k/(PUNKTE−1) über [t_a, t_e]
  interpoliert; `haltung()` nimmt je Punkt und Gelenk den Median, dazu Median von verzug/dauer/hub.
  Unlesbare Läufe überspringen (wirft nie). `main` schreibt `DATEI` mit `ensure_ascii=False`, `indent=1`.
- [ ] **Step 4:** Tests grün; dann echt erzeugen:
  `python -m spotlab.kalibrierung.haltung D:\Users\janis\Documents\Matura\spotProjects\Beispiele\runs`
  → Ausgabe Anzahl (≈ 140), Hub ≈ 0.41, Dauer ≈ 1.0, Verzug ≈ 0.2 prüfen; Datei committen.
- [ ] **Step 5: Commit** „Kalibrierung: Aufstehbahn aus echten Laeufen (haltung.json)“.

### Task 2: matura-spot — Arbeitskopie, Daten, `spotsim/haltung.py`

**Files:**
- Setup: `git -C D:\…\matura-spot worktree add ..\matura-spot-haltung -b feat/haltung`, dann Verknüpfung
  der Modelle: `New-Item -ItemType Junction -Path ..\matura-spot-haltung\assets\mujoco_menagerie -Target
  D:\…\matura-spot\assets\mujoco_menagerie` (assets/ ist gitignored).
- Create: `src/spotsim/daten/haltung.json` (Kopie), `src/spotsim/haltung.py`
- Modify: `src/spotsim/__init__.py` (`HALTUNG_FASSUNG = 1`, in `__all__`)
- Test: `tests/test_haltung.py`

**Interfaces:**
- Produces: `ORDNUNG` (Aktuator-/Gelenknamen `fl_hx`…), `Bahn(verzug_s, dauer_s, hub_m, punkte)` mit
  `.sitz`, `.stand`, `.bei(u)`, `lade_bahn(model=None) -> Bahn` (kappt auf `jnt_range`), `gelenke(model, data)
  -> np.ndarray(12)`, `Haltungswechsel(data, bahn, richtung, start_q)` mit `.sollwerte()` und
  `.bahn_zu_ende`, `setze_sitzend(model, data, bahn, einschwingen_s=1.0)`,
  `HALTUNG_RAMPE_S = 1.0`, `HOEHE_GRENZEN_M`, `LAGE_GRENZEN_RAD` (Task 4 füllt sie aus der Messung).

- [ ] **Step 1: Tests:** (a) `daten/haltung.json` ist Byte für Byte gleich spotlab
  `kalibrierung/daten/haltung.json` (Pfad wie in `test_gangplan.py`, skip, wenn spotlab fehlt);
  (b) `lade_bahn(model).punkte` liegt in `jnt_range`; (c) `setze_sitzend` auf `build_sensor_model()`:
  Rumpf-z < 0.2, Rumpf berührt den Boden (Kontakt Rumpf-Geom ↔ `floor`), Roll/Nick < 10°,
  Gelenke ± 0.1 rad an `bahn.sitz`; (d) Aufstehen im Positionsmodus: `Haltungswechsel(…, "auf")`,
  je Takt `data.ctrl = sollwerte()`, 5 × `mj_step` — nach verzug + dauer + 1 s: Hub (z_ende − z_start)
  = bahn.hub_m ± 0.05, Gelenke ± 0.1 rad an `bahn.stand`, nicht gefallen.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Umsetzen** (Kern):

```python
class Haltungswechsel:
    """Positions-Sollwerte über die gemessene Bahn: `auf` vorwärts, `ab` rückwärts (Annahme H2)."""

    def __init__(self, data, bahn, richtung, start_q):
        self.data, self.bahn, self.richtung = data, bahn, richtung
        self.t0 = float(data.time)
        anfang = bahn.bei(0.0 if richtung == "auf" else 1.0)
        self._rest = np.asarray(start_q, dtype=float) - anfang   # klingt stetig ab

    def sollwerte(self):
        u = (float(self.data.time) - self.t0 - self.bahn.verzug_s) / self.bahn.dauer_s
        u = min(1.0, max(0.0, u))
        return self.bahn.bei(u if self.richtung == "auf" else 1.0 - u) + (1.0 - u) * self._rest

    @property
    def bahn_zu_ende(self):
        return float(self.data.time) - self.t0 >= self.bahn.verzug_s + self.bahn.dauer_s
```

  `setze_sitzend`: Sitzgelenke in `qpos`, `qvel = 0`, Rumpf-z von 0.30 in 5-mm-Schritten senken, bis
  `mj_forward` einen Bodenkontakt eines Roboter-Geoms meldet; dann `einschwingen_s` mit `ctrl = bahn.sitz`
  (Positionsmodus). Einmalige Anfangsbedingung — danach schreibt nur `mj_step` die Basis.
- [ ] **Step 4:** grün; Aufstehen rendern (`sensors`-Zimmerkamera oder `puppe.zimmerkamera`) und ansehen.
- [ ] **Step 5: Commit** „feat(haltung): Aufstehen ueber die gemessene Gelenkbahn, Sitzen als Startzustand“.

### Task 3: matura-spot — Übergänge in `SpotSdkSim`

**Files:**
- Modify: `src/spotsim/sdk_sim.py`
- Test: `tests/test_sdk_haltung.py`

**Interfaces:**
- Consumes: Task 2.
- Produces: `SpotSdkSim(..., haltung="stehend"|"sitzend")`; Eigenschaft `sim.haltung` ∈ {"steht", "sitzt",
  "steht_auf", "setzt_sich", "aus"}; `sim.motoren(an: bool)`.

- [ ] **Step 1: Tests** (`SPOTSIM_REGLER` Vorgabe kraft, Sim-Uhr): sitzend gebaut → `haltung == "sitzt"`,
  z < 0.2; `stand_command` → nach ≤ 3 s „steht“, z-Hub 0.41 ± 0.05; danach Gehbefehl 0.3 m/s 3 s → geht
  (Kraftregler), kein Sturz; `sit_command` → nach ≤ 4 s „sitzt“, Sitzgelenke ± 0.1 rad; Gehbefehl im Sitzen
  → steht zuerst auf, geht dann; `motoren(False)` im Sitzen → „aus“, Drehmoment 0, z ändert sich < 3 cm;
  `motoren(True)` → „sitzt“. **Bitgleich-Probe:** `haltung="stehend"`, feste Befehlsfolge (0.5 m/s 2 s,
  Drehen 0.6 rad/s 2 s, Stopp 2 s) → `qpos` identisch mit dem Wert, den derselbe Test im Hauptcheckout
  (vor der Änderung) liefert: Referenz einmal mit `PYTHONPATH=D:\…\matura-spot\src` erzeugen und als
  `tests/daten/bitgleich_stehend.npy` ablegen.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Umsetzen.** Im Konstruktor nach `stand_referenz` (Stand wird weiter im Stehen gemessen):
  `self._bahn = lade_bahn(model)`, `self._haltung = "steht"`, `self._wechsel = None`,
  `self._motoren_an = True`; bei `haltung == "sitzend"`: `setze_sitzend(...)`, `self._haltung = "sitzt"`.
  In `run` nach der Berechnung von `geht` (vor `kriechen`):

```python
            if self._haltung_tick(sp, geht, on_tick):
                continue
```

```python
    def _haltung_tick(self, sp, geht, on_tick):
        """Motoren aus, Sitzen, Aufstehen: True, wenn der Takt davon verbraucht ist."""
        if not self._motoren_an:
            self._schritte(np.zeros(12), on_tick, "aus", drehmoment=True)
            return True
        if self._wechsel is not None:
            self._wechsel_tick(on_tick)
            return True
        if self._haltung == "sitzt":
            if sp.mode is Mode.STAND or geht:
                self._beginne_wechsel("auf")
            else:
                self._schritte(self._bahn.sitz, on_tick, "sitzt")
            return True
        if sp.mode is Mode.SIT:
            self._zum_stand_anhalten(on_tick)      # Kraftregler/Trab anhalten, dann Positionsmodus
            self._beginne_wechsel("ab")
            return True
        return False
```

  `_wechsel_tick`: `ctrl = wechsel.sollwerte()`, `CONTROL_DECIMATION` Schritte, `_fell_check`; fertig,
  wenn `bahn_zu_ende` und ruhig (|v_xy| < 0.04, |ω| < 0.15): „auf“ → `self._haltung = "steht"`,
  Posture-Sync wie in `_exit_kraft` (`pc.q_targets = ctrl`, Anker, Offset, Gier), `self._kraft = None`;
  „ab“ → „sitzt“. `_zum_stand_anhalten`: bei `_kraft` wie `_exit_kraft` bis „standing“, dann
  `aktuatoren.position()`, `ctrl = self._kraft.q`, `self._kraft = None`; bei `_trot` `_exit_trot`.
  `motoren(False)`: lazily `Aktuatoren` bauen, `drehmoment()`, `_kraft = _trot = _wechsel = None`,
  Haltung danach „sitzt“; `motoren(True)`: `position()`. `haltung`-Eigenschaft gibt „aus“, wenn aus.
- [ ] **Step 4:** grün; `tests/test_gates.py` (QUICK) und `tests/test_sdk_*` grün.
- [ ] **Step 5: Commit** „feat(sdk_sim): sitzend starten, aufstehen, hinsetzen, Motoren aus“.

### Task 4: matura-spot — Körperhaltung im Stand

**Files:**
- Modify: `src/spotsim/interpreter.py` (Setpoints `roll`, `pitch`, `yaw`), `src/spotsim/kraftregler.py`
  (`setze_haltung`, Rampe, MPC-Ziel), `src/spotsim/sdk_sim.py` (`_kraft_tick` reicht die Haltung durch),
  `src/spotsim/haltung.py` (Grenzen nach Messung)
- Test: `tests/test_interpreter.py` (ergänzen), `tests/test_kraft_haltung.py`

**Interfaces:**
- Produces: `Setpoints.roll/pitch/yaw` (rad, aus `footprint_R_body` über `bosdyn.geometry.to_euler_zxy`;
  ein ungesetztes Quaternion (Norm < 1e-9) ist neutral); `KraftRegler.setze_haltung(hoehe, lage)`;
  `haltung.HOEHE_GRENZEN_M`, `haltung.LAGE_GRENZEN_RAD` (roll, pitch, yaw je ±).

- [ ] **Step 1: Tests:** Interpreter liest roll 0.2/pitch −0.1/yaw 0.3 aus `synchro_stand_command(
  footprint_R_body=EulerZXY(...))`; Kraftregler im Stand: jede der acht Messposen (Roll ±15°, Nick ±15°,
  Gier ±20°, Höhe ±0.1 m) nach 1.5 s auf ± 2° / ± 1 cm, Füsse rutschen ≤ 2 cm, zurück auf neutral;
  beim Gehen ist die Haltung neutral (Rampe zurück).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Umsetzen.** `setze_haltung` startet bei neuem Ziel eine lineare Rampe über
  `HALTUNG_RAMPE_S` vom jetzigen Wert (Annahme H3). In `_mpc` die Gier-Verankerung auf die Gier OHNE
  befohlene Körperdrehung beziehen, sonst zieht der Anker den Körper weiter:

```python
        h, rolle, nick, gier_v = self._haltung_jetzt()
        bezug = rpy[2] - gier_v
        bezug = self.gier_soll + _wickeln(bezug - self.gier_soll)
        self.gier_soll = bezug + float(np.clip(self.gier_soll - bezug, -GIER_FENSTER, GIER_FENSTER))
        rpy[2] = bezug + gier_v
        gier_ist = bezug
        ...
            ziel[k, 0], ziel[k, 1] = rolle, nick
            ziel[k, 2] = psi + gier_v
            ziel[k, 5] = self.z_ziel + h
            fuesse[k] = geplant - np.array([ort[0], ort[1], self.z_ziel + h])
```

  `SpotSdkSim.run`: im Modus STAND `lage = (sp.roll, sp.pitch, sp.yaw)`, sonst `(0, 0, 0)`; Höhe wie
  bisher. **Grenzen messen:** API-Extreme (Roll/Nick ±20°, Gier ±30°, Höhe ±0.15 m) je 3 s halten;
  was hält (± 2° / ± 1 cm, kein Sturz, Rutschen ≤ 2 cm), wird `LAGE_GRENZEN_RAD` / `HOEHE_GRENZEN_M`,
  sonst der grösste gehaltene Wert; Tabelle für `notes/ENTWURF_haltung.md` notieren. Ohne Haltung
  (0, 0, 0, 0) rechnet `_mpc` wie vorher → Bitgleich-Probe aus Task 3 bleibt grün.
- [ ] **Step 4:** grün (inkl. Bitgleich-Probe); Posen rendern und ansehen.
- [ ] **Step 5: Commit** „feat(kraft): Koerperhaltung im Stand als MPC-Ziel, Rampe 1 s“.

### Task 5: matura-spot — Gate G12 „Haltung“, Entwurf, Abnahme im Repo

**Files:**
- Modify: `src/spotsim/gates.py` (`_run_haltung`, `_check_haltung`, `GateSpec(gid="G12", …)`, QUICK)
- Create: `notes/ENTWURF_haltung.md` (H1–H4 als RESEARCH DECISIONS, Messung der Grenzen, Messplan A41)
- Modify: `CLAUDE.md` (Regel: Haltung über gemessene Bahn; Start sitzend nur für Aufrufer mit `haltung=`),
  `notes/VISION_simulation.md` (ein Absatz), `notes/REALISMUS_GATES.md` (Zeile G12)
- Test: `tests/test_gates.py` (G12 im Katalog und in QUICK)

- [ ] **Step 1:** `test_katalog_vollstaendig` + ein Test `test_g12_haltung` (FAIL: fehlt).
- [ ] **Step 2: Umsetzen:** `_run_haltung`: `SpotSdkSim(haltung="sitzend")`, stand → z je Takt (100 Hz)
  mitschreiben, Hub und Dauer wie in spotlab bestimmen (1 cm / 5 mm über 50 ms); acht Posen; sit →
  Sitzgelenke, Rumpfkontakt, Roll/Nick. `_check_haltung`: Hub 0.41 ± 0.05 m, Dauer 0.9 ± 0.2 s, kein Sturz,
  Standgelenke ± 0.1; Posen ± 2° / ± 1 cm, Rutschen ≤ 2 cm; Sitzgelenke ± 0.1, Rumpf liegt auf,
  Roll/Nick < 10°. `assumption`: H2 und H3; `real_procedure`: spotlab `Beispiele/haltung_messen.py` (A41).
- [ ] **Step 3:** grün; volle matura-spot-Suite grün; `python scripts/realismus_gates.py` für G1–G12,
  Ergebnis wie Baseline `20260925T100636Z_924af45-gemessen-kraft` plus G12 bestanden.
- [ ] **Step 4: Commit** „feat(gates): G12 Haltung; Entwurf H1-H4“.

### Task 6: spotlab — Adapter

**Files:**
- Modify: `src/spotlab/backends/physics.py`, `src/spotlab/api/features.py`, `src/spotlab/api/body.py`
  (Meldung), `src/spotlab/backends/mujoco.py` (`_physik_laden` reicht `HALTUNG_FASSUNG` durch)
- Modify tests, die ohne `stand()` fahren: `tests/test_backend_physics.py`, `tests/test_physics_normal.py`,
  `tests/test_api_motion.py` → `PhysicsBackend(..., haltung="stehend")`
- Test: `tests/test_physics_haltung.py`

**Interfaces:**
- Consumes: `spotsim.HALTUNG_FASSUNG`, `SpotSdkSim(haltung=…)`, `sim.haltung`, `sim.motoren(an)`,
  `haltung.HOEHE_GRENZEN_M`, `haltung.LAGE_GRENZEN_RAD`, `haltung.HALTUNG_RAMPE_S`.
- Produces: `PhysicsBackend(..., haltung=None)` (None → „sitzend“ in ebenen Räumen mit Fassung ≥ 1,
  sonst „stehend“), Instanzmerkmale `kann_sitzen`, `kann_pose`.

- [ ] **Step 1: Tests** (`realtime=False`, Sim-Uhr): Start sitzend (z < 0.2), Gehbefehl → `CommandRejected`
  mit „stand()“; `power_on` + `stand` → Rückmeldung „steht“, z-Hub ≈ 0.41; `pose` über `api/body.pose` mit
  Roll 15° → nach Rückmeldung Roll 15 ± 2°; Roll 40° → gekappt + Ereignis `physik_grenze` (echter
  RunRecorder); `sit` → „sitzt“ (Rückmeldung „sitzt“, nicht „steht“); `power_off` → sitzt, dann Motoren aus
  (`sim.haltung == "aus"`); Stufenszene startet stehend; ohne `HALTUNG_FASSUNG` (monkeypatch) →
  `kann_sitzen is False` und Verhalten aus Stufe A (Test aus `test_physics_normal` bleibt grün).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Umsetzen.**
  - `__init__`: Fassung aus `_physik_laden()`; `haltung` bestimmen; `SpotSdkSim`/`TerrainSdkSim` nur mit
    `haltung=` aufrufen, wenn Fassung ≥ 1; `self.kann_sitzen = self.kann_pose = fassung >= 1`; bei Start
    sitzend `sim.motoren(False)` (Motoren aus bis `power_on`).
  - `power_on`: über `_call` `sim.motoren(True)`; `power_off`: pending Sitzkommando + Merker
    `_aus_nach_sitzen`; `_tick` schaltet `sim.motoren(False)`, sobald `sim.haltung == "sitzt"`.
  - `send_command`: `sit_request` annehmen, wenn `kann_sitzen`; Stehkommando mit Haltung annehmen, wenn
    `kann_pose` (Winkel über `to_euler_zxy`, auf Grenzen gekappt → neues `synchro_stand_command`, Ereignis
    `physik_grenze`); Geh-/Zielbefehle, solange `sim.haltung in ("sitzt", "setzt_sich", "aus")` →
    `CommandRejected("Spot sitzt — zuerst stand() aufrufen.")`; Geschwindigkeiten mit Körperhaltung weiter
    abgewiesen (neutral beim Gehen).
  - Rückmeldung in `_tick`: für ein Sitzkommando fertig bei `sim.haltung == "sitzt"` + `RUHE_S` → „sitzt“;
    für Stehen zusätzlich `sim.haltung == "steht"`; für ein Stehkommando mit Haltung erst nach
    `HALTUNG_RAMPE_S`.
  - `features.supports('pose')`: `… or getattr(spot.backend, 'kann_pose', False)`; `HINWEIS` und
    `hinweis_zur_gueltigkeit` nennen Sitzen/Aufstehen/Haltung und die zwei Annahmen.
- [ ] **Step 4:** Tests grün; `test_backend_physics`, `test_physics_normal`, `test_api_motion`,
  `test_physics_single_step`, `test_physics_stairs` grün (Unterprozess-Tests mit PYTHONPATH auf BEIDE
  Arbeitskopien); Echtzeitfaktor beim Aufstehen im Worker ≥ 1 (Sonde: 5 s Sim-Zeit ≤ 5.5 s Wanduhr).
- [ ] **Step 5: Commit** „Physik: sitzend starten, aufstehen, hinsetzen, Koerperhaltung“.

### Task 7: spotlab — Messprogramm, Release, Doku, Zusammenführen

**Files:**
- Create: `src/spotlab/workshop/beispiele/haltung_messen.py` (`messe(spot, schlaf=time.sleep)`; aufstehen,
  3 s; je Pose (Roll ±15°, Nick ±15°, Gier ±20°, Höhe ±0.1 m) `pose`, 3 s, neutral, 2 s; `sit`; 5 s)
- Modify: `tools/schueler_release.py` (`MODULES` + `haltung`; prüfen und nachtragen, was der Kraftregler
  seit dem 24.09.2026 braucht: `aktuator gangplan mpc schwung kraftregler`, dazu `daten/gang.json` und
  `daten/haltung.json` als Paketdaten), `CLAUDE.md`, `docs/PHYSICS.md`, `docs/API.md`, `docs/ABNAHME.md`
  (A41), Spec-Zeile „Stand nach dem Bau“
- Test: `tests/test_physics_haltung.py` (`messe` mit DryRun-Spot und `schlaf=lambda s: None`: Ereignisfolge
  stand, 8 × pose + neutral, sit), `tests/test_schueler_release.py` (Erlaubnisliste enthält die Module)

- [ ] **Step 1:** Tests → FAIL; **Step 2:** umsetzen; Release-Bau in einen temporären Ordner (`--modelle`
  weglassen, wenn das Werkzeug es erlaubt) und prüfen, dass das Sim-Wheel `spotsim/haltung.py`,
  `spotsim/kraftregler.py` und `spotsim/daten/*.json` enthält.
- [ ] **Step 3:** Volle Suiten: matura-spot (Arbeitskopie) und spotlab (PYTHONPATH auf beide), ruff in
  beiden. Zentrale-Prozesstest und `test_connect_process_render_and_teardown` grün.
- [ ] **Step 4: Zusammenführen:** matura-spot `feat/haltung` per ff in `sim-module-nachtragen`
  (Hauptcheckout hat fremde, nicht committete Dateien — ff ändert sie nicht; vorher `git status` prüfen),
  dann spotlab ff in `main`; Arbeitskopien entfernen (Junction zuerst löschen, sie zeigt auf die echten
  Modelle: `Remove-Item` NUR auf den Link, nie rekursiv). Gedächtnis nachführen; Bericht; Push nur auf
  Anweisung.
