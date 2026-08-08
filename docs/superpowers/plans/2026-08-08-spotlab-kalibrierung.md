# spotlab Kalibrier-Infrastruktur Implementierungsplan — Teil 1 (Aufgaben 1–4)

> **Für agentische Arbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development`
> (empfohlen) oder `superpowers:executing-plans`. Schritte sind Checkboxen (`- [ ]`).

**Ziel:** Der echte Spot wird so gemessen, dass der MuJoCo-Sim in `matura-spot` daran
geeicht werden kann: reichere Abtastung, Messfenster mit eigener Rate, und Kennzahlen je
Fenster in `messfenster.json`.

**Architektur:** spotlab misst, `matura-spot` bewertet. Die Gate-Kriterien bleiben dort;
spotlab liefert `messwerte`, nicht das Gate-Protokoll. `messung/` ist Qt-frei und SDK-frei
und liest nur die Aufzeichnung von der Platte.

**Technik:** Python 3.11+, `bosdyn-api` (nur in `api/state.py` und `backends/`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-08-spotlab-kalibrierung-design.md`

**Teil 2 (Aufgaben 5–9):** `docs/superpowers/plans/2026-08-08-spotlab-kalibrierung-teil2.md`

## Globale Vorgaben

Gelten für **jede** Aufgabe:

- **Bestehende Schlüssel in `zustand.jsonl` ändern sich nicht.** `pose` bleibt
  `(x, y, yaw)` mit drei Elementen, `feet` bleibt eine Liste aus vier Wahrheitswerten.
  `gui/views/live.py` liest genau das, und alte Aufzeichnungen müssen lesbar bleiben.
- **Umschlag deutsch (`t`, `art`, `daten`), Nutzdaten englisch** (`battery`, `pose`,
  `velocity`, `joints`, `feet`). Neue Schlüssel in den Nutzdaten sind englisch — so ist es
  heute, und Konsistenz in der Datei wiegt schwerer als eine Regel, die die Datei bricht.
- **Fehlende Messwerte sind `None`, nie 0.** Der Unterschied zwischen „gemessen und null"
  und „nicht gemessen" entscheidet, ob eine Kalibrierung gültig ist.
- **`src/spotlab/messung/` importiert nichts aus `api/`, `backends/`, `gui/` und kein
  `bosdyn`.** `spotlab.errors` ist erlaubt.
- **Kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `src/spotlab/gui/`.**
- Alle Texte an Nutzer deutsch; Meldungen sagen, was zu tun ist.
- Vor jedem Commit: `python -m pytest -q` vollständig grün. **Aus dem spotlab-Verzeichnis
  starten** — `Set-Location "D:\Users\janis\Documents\Matura\spotlab"`.

---

## Aufgabe 1: `api/state.py` — reichere Abtastung

**Dateien:**
- Ändern: `src/spotlab/api/state.py`
- Test: `tests/test_api_state.py` (ergänzen)

**Schnittstellen:**
- Verbraucht: `bosdyn.api.robot_state_pb2`, `frame_helpers`.
- Liefert: `rpy_aus(quaternion) -> (roll, pitch, yaw)`, erweiterte `JointState`,
  `State` mit `z`, `roll`, `pitch`, `t_robot`, `velocity_vision`, `feet_detail`,
  `behavior`, `battery_detail`, `motor_temps`; `as_sample(zustand, reich=False)`.
  Aufgabe 3 ruft `as_sample` mit `reich`, Teil 2 wertet die Felder aus.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `tests/test_api_state.py` anhängen:

```python
import math

from bosdyn.api import robot_state_pb2
from google.protobuf import wrappers_pb2

from spotlab.api.state import as_sample, from_proto, rpy_aus


def _voller_zustand():
    """Ein RobotState mit ALLEN Feldern, die die Kalibrierung braucht."""
    z = robot_state_pb2.RobotState()

    akku = z.battery_states.add()
    akku.charge_percentage.CopyFrom(wrappers_pb2.DoubleValue(value=87.0))
    akku.voltage.CopyFrom(wrappers_pb2.DoubleValue(value=56.2))
    akku.current.CopyFrom(wrappers_pb2.DoubleValue(value=-12.4))
    akku.temperatures.extend([31.0, 32.5])

    motor = z.system_state.motor_temperatures.add()
    motor.name = "fl.hx"
    motor.temperature = 42.0

    z.power_state.motor_power_state = robot_state_pb2.PowerState.STATE_ON
    z.behavior_state.state = robot_state_pb2.BehaviorState.STATE_STEPPING

    k = z.kinematic_state
    k.acquisition_timestamp.seconds = 1786293840
    k.acquisition_timestamp.nanos = 123000000

    gelenk = k.joint_states.add()
    gelenk.name = "fl.hx"
    gelenk.position.CopyFrom(wrappers_pb2.DoubleValue(value=0.1))
    gelenk.velocity.CopyFrom(wrappers_pb2.DoubleValue(value=0.2))
    gelenk.acceleration.CopyFrom(wrappers_pb2.DoubleValue(value=0.3))
    gelenk.load.CopyFrom(wrappers_pb2.DoubleValue(value=12.5))

    k.velocity_of_body_in_odom.linear.x = 0.30
    k.velocity_of_body_in_odom.angular.z = 0.05
    k.velocity_of_body_in_vision.linear.x = 0.28

    fuss = z.foot_state.add()
    fuss.contact = robot_state_pb2.FootState.CONTACT_MADE
    fuss.foot_position_rt_body.x = 0.33
    fuss.foot_position_rt_body.z = -0.42
    fuss.terrain.ground_mu_est = 0.62
    fuss.terrain.foot_slip_distance_rt_frame.x = 0.001
    fuss.terrain.foot_slip_velocity_rt_frame.x = 0.01
    fuss.terrain.ground_contact_normal_rt_frame.z = 1.0
    fuss.terrain.visual_surface_ground_penetration_mean = 0.004

    kante = k.transforms_snapshot.child_to_parent_edge_map["body"]
    kante.parent_frame_name = "odom"
    kante.parent_tform_child.position.x = 1.0
    kante.parent_tform_child.position.y = 2.0
    kante.parent_tform_child.position.z = 0.419
    kante.parent_tform_child.rotation.w = 1.0
    k.transforms_snapshot.child_to_parent_edge_map["odom"].SetInParent()
    return z


def test_rpy_liefert_alle_drei_winkel():
    q = robot_state_pb2.RobotState().kinematic_state  # nur für den Typ
    del q
    from bosdyn.api.geometry_pb2 import Quaternion

    roll, pitch, yaw = rpy_aus(Quaternion(w=1.0, x=0.0, y=0.0, z=0.0))
    assert (roll, pitch, yaw) == (0.0, 0.0, 0.0)

    # 90° um z
    halb = math.sqrt(0.5)
    _r, _p, yaw = rpy_aus(Quaternion(w=halb, x=0.0, y=0.0, z=halb))
    assert yaw == pytest.approx(math.pi / 2, abs=1e-9)

    # 30° Roll
    roll, _p, _y = rpy_aus(Quaternion(w=math.cos(math.radians(15)),
                                      x=math.sin(math.radians(15)), y=0.0, z=0.0))
    assert roll == pytest.approx(math.radians(30), abs=1e-9)


def test_hoehe_und_neigung_kommen_an():
    """G1 misst Körperhöhe und Neigung — beides fehlte bisher vollständig."""
    s = from_proto(_voller_zustand())
    assert s.z == pytest.approx(0.419)
    assert s.roll == pytest.approx(0.0)
    assert s.pitch == pytest.approx(0.0)
    assert s.pose == pytest.approx((1.0, 2.0, 0.0))


def test_roboterzeitstempel():
    s = from_proto(_voller_zustand())
    assert s.t_robot == pytest.approx(1786293840.123, abs=1e-6)


def test_gelenk_mit_beschleunigung_und_last():
    s = from_proto(_voller_zustand())
    g = s.joints["fl.hx"]
    assert (g.position, g.velocity, g.acceleration, g.load) == pytest.approx(
        (0.1, 0.2, 0.3, 12.5)
    )


def test_fuss_terrain():
    s = from_proto(_voller_zustand())
    fuss = s.feet_detail[0]
    assert fuss["kontakt"] is True
    assert fuss["mu"] == pytest.approx(0.62)
    assert fuss["slip_weg"][0] == pytest.approx(0.001)
    assert fuss["normal"][2] == pytest.approx(1.0)
    assert fuss["durchdringung"] == pytest.approx(0.004)
    assert fuss["pos"] == pytest.approx([0.33, 0.0, -0.42])


def test_beide_geschwindigkeitsquellen():
    s = from_proto(_voller_zustand())
    assert s.velocity[0] == pytest.approx(0.30)
    assert s.velocity_vision[0] == pytest.approx(0.28)


def test_verhalten_ohne_praefix():
    assert from_proto(_voller_zustand()).behavior == "STEPPING"


def test_akku_und_motortemperaturen():
    s = from_proto(_voller_zustand())
    assert s.battery_detail["spannung"] == pytest.approx(56.2)
    assert s.battery_detail["strom"] == pytest.approx(-12.4)
    assert s.battery_detail["temperaturen"] == pytest.approx([31.0, 32.5])
    assert s.motor_temps["fl.hx"] == pytest.approx(42.0)


def test_ohne_terrain_kein_erfundener_reibwert():
    """Ein erfundener Reibwert 0.0 waere schlimmer als gar keiner — er mittelt sich durch."""
    z = _voller_zustand()
    z.foot_state[0].ClearField("terrain")
    fuss = from_proto(z).feet_detail[0]
    assert "mu" not in fuss
    assert fuss["kontakt"] is True


def test_ohne_zeitstempel_bleibt_null():
    z = _voller_zustand()
    z.kinematic_state.ClearField("acquisition_timestamp")
    assert from_proto(z).t_robot == 0.0


def test_schlanke_abtastung_ist_rueckwaertskompatibel():
    """pose bleibt dreielementig, feet bleibt Wahrheitswerte — die Live-Ansicht liest das."""
    satz = as_sample(_voller_zustand())
    assert len(satz["pose"]) == 3
    assert satz["feet"] == [True]
    assert set(satz) == {
        "battery", "powered", "pose", "velocity", "joints", "feet",
        "t_robot", "z", "roll", "pitch",
    }
    assert set(satz["joints"]["fl.hx"]) == {"position", "velocity", "load"}


def test_reiche_abtastung_hat_die_kalibrierfelder():
    satz = as_sample(_voller_zustand(), reich=True)
    assert set(satz) >= {
        "joint_acc", "velocity_vision", "behavior", "feet_detail",
        "battery_detail", "motor_temps",
    }
    assert satz["joint_acc"]["fl.hx"] == pytest.approx(0.3)
    assert satz["feet_detail"][0]["mu"] == pytest.approx(0.62)


def test_reiche_abtastung_ist_deutlich_groesser():
    import json

    klein = len(json.dumps(as_sample(_voller_zustand())))
    gross = len(json.dumps(as_sample(_voller_zustand(), reich=True)))
    assert gross > klein
```

Am Kopf der Datei muss `import pytest` stehen (falls noch nicht vorhanden).

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_api_state.py -q
```

Erwartet: `ImportError: cannot import name 'rpy_aus'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/api/state.py` — Kopf und Datenklassen:

```python
"""Roboterzustand als handliche Datenklasse — und als flache Abtastung für zustand.jsonl.

Die flache Form ist die Kalibrierdatenquelle für Real→Sim: kommandierte gegen
gemessene Geschwindigkeit, Gelenkverläufe, Fusskontakt-Timing, Reibwerte.

Zwei Umfänge: schlank (jeder Lauf, 10 Hz) und reich (nur im Messfenster). Die
schlanken Schlüssel sind unverändert die von Stufe 1 — die Live-Ansicht und alte
Aufzeichnungen hängen daran.
"""

import math
from dataclasses import dataclass, field

from bosdyn.api import robot_state_pb2
from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, get_a_tform_b


@dataclass(frozen=True)
class JointState:
    position: float
    velocity: float
    load: float
    acceleration: float = 0.0


@dataclass(frozen=True)
class State:
    battery: float
    powered: bool
    pose: tuple                      # (x, y, yaw) — unverändert dreielementig
    velocity: tuple
    joints: dict
    feet: tuple
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    t_robot: float = 0.0             # rohe Roboteruhr, NICHT umgerechnet
    velocity_vision: tuple = (0.0, 0.0, 0.0)
    feet_detail: tuple = ()
    behavior: str = ""
    battery_detail: dict = field(default_factory=dict)
    motor_temps: dict = field(default_factory=dict)
```

Die Winkelfunktion ersetzt `_yaw_aus`; **die Yaw-Formel bleibt bitgleich**, damit
bestehende Tests und alte Aufzeichnungen dieselben Werte sehen:

```python
def rpy_aus(quaternion):
    """Roll, Pitch, Yaw aus einem Quaternion. Yaw wie bisher, Roll und Pitch neu."""
    w, x, y, z = quaternion.w, quaternion.x, quaternion.y, quaternion.z
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    # asin klemmen: numerisches Rauschen kann |sin| knapp über 1 treiben
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return roll, pitch, yaw
```

Die Hilfsfunktionen für die neuen Blöcke:

```python
def _sekunden(zeitstempel):
    return zeitstempel.seconds + zeitstempel.nanos * 1e-9


def _vec(v):
    return [v.x, v.y, v.z]


def _fuss_detail(fuss):
    eintrag = {
        "pos": _vec(fuss.foot_position_rt_body),
        "kontakt": fuss.contact == robot_state_pb2.FootState.CONTACT_MADE,
    }
    # Ohne Kontakt liefert der Roboter kein Terrain. Ein erfundener Reibwert 0.0
    # waere schlimmer als gar keiner: er mittelt sich durch jede Auswertung.
    if fuss.HasField("terrain"):
        gelaende = fuss.terrain
        eintrag.update(
            {
                "mu": gelaende.ground_mu_est,
                "slip_weg": _vec(gelaende.foot_slip_distance_rt_frame),
                "slip_tempo": _vec(gelaende.foot_slip_velocity_rt_frame),
                "normal": _vec(gelaende.ground_contact_normal_rt_frame),
                "durchdringung": gelaende.visual_surface_ground_penetration_mean,
            }
        )
    return eintrag


def _verhalten(zustand):
    try:
        name = robot_state_pb2.BehaviorState.State.Name(zustand.behavior_state.state)
    except ValueError:
        return ""
    return name.removeprefix("STATE_")


def _akku_detail(zustand):
    if not zustand.battery_states:
        return {}
    akku = zustand.battery_states[0]
    return {
        "spannung": akku.voltage.value,
        "strom": akku.current.value,
        "temperaturen": list(akku.temperatures),
    }
```

`from_proto` wird erweitert — die bestehende Pose-Ermittlung bleibt, ergänzt um z und rpy:

```python
def from_proto(zustand):
    akku = zustand.battery_states[0].charge_percentage.value if zustand.battery_states else 0.0
    kinematik = zustand.kinematic_state

    x = y = z_hoehe = roll = pitch = yaw = 0.0
    try:
        odom_tform_body = get_a_tform_b(
            kinematik.transforms_snapshot, ODOM_FRAME_NAME, BODY_FRAME_NAME
        )
        if odom_tform_body is not None:
            x = odom_tform_body.position.x
            y = odom_tform_body.position.y
            z_hoehe = odom_tform_body.position.z
            roll, pitch, yaw = rpy_aus(odom_tform_body.rotation)
    except Exception:  # Schnappschuss unvollständig — Pose bleibt Ursprung
        pass

    geschwindigkeit = kinematik.velocity_of_body_in_odom
    sicht = kinematik.velocity_of_body_in_vision
    return State(
        battery=akku,
        powered=zustand.power_state.motor_power_state == robot_state_pb2.PowerState.STATE_ON,
        pose=(x, y, yaw),
        velocity=(geschwindigkeit.linear.x, geschwindigkeit.linear.y,
                  geschwindigkeit.angular.z),
        joints={
            g.name: JointState(
                g.position.value, g.velocity.value, g.load.value, g.acceleration.value
            )
            for g in kinematik.joint_states
        },
        feet=tuple(
            f.contact == robot_state_pb2.FootState.CONTACT_MADE for f in zustand.foot_state
        ),
        z=z_hoehe,
        roll=roll,
        pitch=pitch,
        t_robot=_sekunden(kinematik.acquisition_timestamp),
        velocity_vision=(sicht.linear.x, sicht.linear.y, sicht.angular.z),
        feet_detail=tuple(_fuss_detail(f) for f in zustand.foot_state),
        behavior=_verhalten(zustand),
        battery_detail=_akku_detail(zustand),
        motor_temps={m.name: m.temperature for m in zustand.system_state.motor_temperatures},
    )
```

Und die flache Form:

```python
def as_sample(zustand, reich=False):
    """Flache Abtastung für zustand.jsonl.

    `reich=True` nur im Messfenster: rund das Neunfache an Bytes, und 50 RPCs
    pro Sekunde ueber WLAN sind in einem Schuelerlauf nichts, was jemand ansieht.
    """
    s = from_proto(zustand)
    satz = {
        "battery": s.battery,
        "powered": s.powered,
        "pose": list(s.pose),
        "velocity": list(s.velocity),
        "joints": {
            name: {"position": g.position, "velocity": g.velocity, "load": g.load}
            for name, g in s.joints.items()
        },
        "feet": list(s.feet),
        # Immer dabei: vier Zahlen, und ohne sie ist G1 nicht messbar.
        "t_robot": s.t_robot,
        "z": s.z,
        "roll": s.roll,
        "pitch": s.pitch,
    }
    if not reich:
        return satz
    satz.update(
        {
            "joint_acc": {name: g.acceleration for name, g in s.joints.items()},
            "velocity_vision": list(s.velocity_vision),
            "behavior": s.behavior,
            "feet_detail": [dict(f) for f in s.feet_detail],
            "battery_detail": dict(s.battery_detail),
            "motor_temps": dict(s.motor_temps),
        }
    )
    return satz
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_api_state.py -q
python -m pytest -q
```

Erwartet: beide grün. Schlägt ein alter Test fehl, weil `State(...)` positionell gebaut
wird, die neuen Felder haben Standardwerte — dann steht die Reihenfolge falsch und die
neuen Felder gehören ans Ende.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/api/state.py tests/test_api_state.py
git commit -m "feat(api): Hoehe, Neigung, Roboterzeit, Fuss-Terrain in der Abtastung"
```

---

## Aufgabe 2: `backends/dryrun.py` — plausible Werte für die neuen Felder

**Warum:** Ohne sie lässt sich die ganze Kette — Messfahrt, Fensterauswertung, Vergleich —
nicht ohne Roboter üben, und die erste echte Messfahrt wäre zugleich der erste Test. Am
Spot-Termin ist dafür keine Zeit.

**Dateien:**
- Ändern: `src/spotlab/backends/dryrun.py`
- Test: `tests/test_dryrun.py` (ergänzen; falls anders benannt, in die bestehende Datei)

**Schnittstellen:**
- Liefert: `DryRunBackend.robot_state()` füllt zusätzlich `acquisition_timestamp`, Körperhöhe,
  Gelenk-`acceleration`, `foot_state[].terrain`, `behavior_state`, Batteriedetails,
  Motortemperaturen.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_trockenlauf_liefert_die_kalibrierfelder():
    """Sonst waere die erste echte Messfahrt zugleich der erste Test."""
    from spotlab.api.state import from_proto
    from spotlab.backends.dryrun import DryRunBackend

    s = from_proto(DryRunBackend().robot_state())
    assert 0.35 < s.z < 0.50                      # plausible Standhöhe
    assert s.t_robot > 0
    assert len(s.feet_detail) == 4
    assert all(0.3 < f["mu"] < 1.0 for f in s.feet_detail if f["kontakt"])
    assert s.behavior in ("STANDING", "STEPPING", "TRANSITION")
    assert s.battery_detail["spannung"] > 0
    assert len(s.motor_temps) == 12


def test_trockenlauf_zeitstempel_laeuft_weiter():
    from spotlab.backends.dryrun import DryRunBackend

    from spotlab.api.state import from_proto

    backend = DryRunBackend()
    erst = from_proto(backend.robot_state()).t_robot
    zweit = from_proto(backend.robot_state()).t_robot
    assert zweit > erst
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Erwartet: `assert 0.35 < 0.0 < 0.50` schlägt fehl.

- [ ] **Schritt 3: Umsetzen**

In `src/spotlab/backends/dryrun.py`, `robot_state()` ergänzen. Die Werte sind erfunden und
die Aufzeichnung sagt das — `backend: "dryrun"` steht in `lauf.json`:

```python
    def robot_state(self):
        zustand = robot_state_pb2.RobotState()
        akku = zustand.battery_states.add()
        akku.charge_percentage.CopyFrom(wrappers_pb2.DoubleValue(value=87.0))
        akku.voltage.CopyFrom(wrappers_pb2.DoubleValue(value=56.2))
        akku.current.CopyFrom(wrappers_pb2.DoubleValue(value=-12.4))
        akku.temperatures.extend([31.0, 32.5])
        for name in GELENKE:
            motor = zustand.system_state.motor_temperatures.add()
            motor.name = name
            motor.temperature = 40.0

        zustand.power_state.motor_power_state = (
            robot_state_pb2.PowerState.STATE_ON
            if self._powered
            else robot_state_pb2.PowerState.STATE_OFF
        )
        zustand.behavior_state.state = (
            robot_state_pb2.BehaviorState.STATE_STANDING
            if self._powered
            else robot_state_pb2.BehaviorState.STATE_NOT_READY
        )

        jetzt = time.time()
        zustand.kinematic_state.acquisition_timestamp.FromNanoseconds(int(jetzt * 1e9))

        for name in GELENKE:
            gelenk = zustand.kinematic_state.joint_states.add()
            gelenk.name = name
            gelenk.position.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.velocity.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.acceleration.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))
            gelenk.load.CopyFrom(wrappers_pb2.DoubleValue(value=0.0))

        for _ in range(4):
            fuss = zustand.foot_state.add()
            fuss.contact = robot_state_pb2.FootState.CONTACT_MADE
            fuss.foot_position_rt_body.z = -STANDHOEHE
            fuss.terrain.ground_mu_est = 0.6
            fuss.terrain.ground_contact_normal_rt_frame.z = 1.0

        zustand.kinematic_state.transforms_snapshot.CopyFrom(self.frame_tree_snapshot())
        return zustand
```

Oben im Modul `import time` ergänzen und die Standhöhe als Konstante:

```python
STANDHOEHE = 0.42       # m, plausible Standhöhe des echten Spot
```

`frame_tree_snapshot` setzt die Körperhöhe:

```python
    def frame_tree_snapshot(self):
        schnappschuss = geometry_pb2.FrameTreeSnapshot()
        schnappschuss.child_to_parent_edge_map[VISION_FRAME_NAME].CopyFrom(
            geometry_pb2.FrameTreeSnapshot.ParentEdge()
        )
        schnappschuss.child_to_parent_edge_map[ODOM_FRAME_NAME].CopyFrom(
            _identitaets_kante(VISION_FRAME_NAME)
        )
        koerper = _identitaets_kante(ODOM_FRAME_NAME)
        koerper.parent_tform_child.position.z = STANDHOEHE
        schnappschuss.child_to_parent_edge_map[BODY_FRAME_NAME].CopyFrom(koerper)
        return schnappschuss
```

**Achtung:** ein bestehender Test könnte prüfen, dass die Körperpose im Trockenlauf der
Ursprung ist. Findet sich einer, gehört er angepasst — die Höhe ist jetzt Absicht.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest -q
```

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/backends/dryrun.py tests/
git commit -m "feat(dryrun): plausible Kalibrierfelder, damit die Kette ohne Roboter uebbar ist"
```

---

## Aufgabe 3: `record/sampler.py` — Rate und Umfang zur Laufzeit

**Dateien:**
- Ändern: `src/spotlab/record/sampler.py`
- Test: `tests/test_record_sampler.py` (ergänzen)

**Schnittstellen:**
- Verbraucht: `as_sample(zustand, reich)` aus Aufgabe 1.
- Liefert: `StateSampler.setze_takt(hz, reich)`, `StateSampler.takt() -> (hz, reich)`.
  Aufgabe 4 ruft beide.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_takt_umschalten_wirkt(qapp=None):
    from spotlab.record.sampler import StateSampler

    abtaster = StateSampler(_FakeBackend(), _FakeRecorder(), hz=10.0)
    assert abtaster.takt() == (10.0, False)
    abtaster.setze_takt(50.0, True)
    assert abtaster.takt() == (50.0, True)


def test_reicher_takt_schreibt_reiche_saetze():
    from spotlab.record.sampler import StateSampler

    recorder = _FakeRecorder()
    abtaster = StateSampler(_FakeBackend(), recorder, hz=1000.0)
    abtaster.setze_takt(1000.0, True)
    abtaster.start()
    time.sleep(0.05)
    abtaster.stop()
    assert recorder.proben, "keine Abtastung"
    assert "feet_detail" in recorder.proben[-1]


def test_schlanker_takt_schreibt_schlanke_saetze():
    from spotlab.record.sampler import StateSampler

    recorder = _FakeRecorder()
    abtaster = StateSampler(_FakeBackend(), recorder, hz=1000.0)
    abtaster.start()
    time.sleep(0.05)
    abtaster.stop()
    assert recorder.proben
    assert "feet_detail" not in recorder.proben[-1]


def test_langsamer_backend_erzeugt_keine_bursts():
    """Nichts wird nachgeholt — sonst saehen Bursts in der Auswertung wie Dynamik aus."""
    from spotlab.record.sampler import StateSampler

    class Langsam(_FakeBackend):
        def robot_state(self):
            time.sleep(0.02)
            return super().robot_state()

    recorder = _FakeRecorder()
    abtaster = StateSampler(Langsam(), recorder, hz=1000.0)   # Soll 1 ms, Ist ~20 ms
    abtaster.start()
    time.sleep(0.2)
    abtaster.stop()
    # Bei echtem Nachholen kaemen zum Schluss viele Saetze fast gleichzeitig.
    assert 5 <= len(recorder.proben) <= 25, len(recorder.proben)
```

Die Attrappen am Kopf der Datei (falls dort noch keine gleichwertigen stehen):

```python
class _FakeBackend:
    def robot_state(self):
        from spotlab.backends.dryrun import DryRunBackend

        return DryRunBackend().robot_state()


class _FakeRecorder:
    def __init__(self):
        self.proben = []
        self.dir = Path(tempfile.mkdtemp())

    def sample(self, daten):
        self.proben.append(daten)
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Erwartet: `AttributeError: 'StateSampler' object has no attribute 'takt'`.

- [ ] **Schritt 3: Umsetzen**

```python
class StateSampler:
    def __init__(self, backend, recorder, hz=10.0):
        self._backend = backend
        self._recorder = recorder
        self._takt_sperre = threading.Lock()
        self._hz = float(hz)
        self._periode = 1.0 / self._hz
        self._reich = False
        self._stopp = threading.Event()
        self._thread = None
        self._stopp_datei = recorder.dir / STOPP_DATEI
        self._abbruch_gemeldet = False

    def setze_takt(self, hz, reich):
        """Wirkt ab dem naechsten Tick. Vom Messfenster gerufen."""
        with self._takt_sperre:
            self._hz = float(hz)
            self._periode = 1.0 / self._hz
            self._reich = bool(reich)

    def takt(self):
        with self._takt_sperre:
            return self._hz, self._reich
```

Die Schleife liest Takt und Umfang **bei jedem Durchlauf**:

```python
    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            with self._takt_sperre:
                periode, reich = self._periode, self._reich
            self._pruefe_stopp()
            try:
                self._recorder.sample(as_sample(self._backend.robot_state(), reich=reich))
            except Exception:  # Abtastung darf den Lauf nie kippen
                self._stopp.wait(periode)
                continue
            # Nichts nachholen: dauert die RPC laenger als die Periode, laeuft die
            # Schleife eben langsamer. Ein Nachholen erzeugte Bursts, die in der
            # Auswertung wie echte Dynamik aussehen.
            rest = periode - (time.monotonic() - beginn)
            if rest > 0:
                self._stopp.wait(rest)
```

**Das Nicht-Nachholen war schon richtig** — `rest > 0` gab es bereits. Der Kommentar hält
fest, warum, damit es niemand „optimiert".

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_record_sampler.py -q
```

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/record/sampler.py tests/test_record_sampler.py
git commit -m "feat(record): Abtastrate und -umfang zur Laufzeit umschaltbar"
```

---

## Aufgabe 4: Das Messfenster

**Dateien:**
- Ändern: `src/spotlab/record/events.py` (neue Art)
- Ändern: `src/spotlab/api/spot.py` (`messfenster`, `sampler`)
- Ändern: `src/spotlab/__init__.py` (Abtaster vor `Spot` bauen und durchreichen)
- Test: `tests/test_messfenster.py`

**Schnittstellen:**
- Verbraucht: `StateSampler.setze_takt`/`takt` (Aufgabe 3).
- Liefert: `Spot.messfenster(name, hz=50.0, **felder)` als Kontextmanager;
  Ereignisart `"messfenster"` mit `phase` (`"start"`/`"ende"`), `name`, `hz_soll` und den
  freien Feldern. Teil 2 wertet genau diese Ereignisse aus.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_messfenster.py`:

```python
import pytest

from spotlab.api.spot import Spot
from spotlab.backends.dryrun import DryRunBackend
from spotlab.errors import SpotlabError
from spotlab.record.events import ARTEN


class _Recorder:
    def __init__(self):
        self.ereignisse = []
        self.dir = None

    def event(self, art, **daten):
        assert art in ARTEN, f"unbekannte Ereignisart: {art}"
        self.ereignisse.append((art, daten))


class _Abtaster:
    def __init__(self):
        self._takt = (10.0, False)
        self.verlauf = []

    def setze_takt(self, hz, reich):
        self._takt = (hz, reich)
        self.verlauf.append((hz, reich))

    def takt(self):
        return self._takt


def _spot(recorder=None, abtaster=None):
    return Spot(DryRunBackend(), recorder=recorder, sampler=abtaster)


def test_messfenster_ist_eine_erlaubte_ereignisart():
    assert "messfenster" in ARTEN


def test_marken_werden_geschrieben():
    recorder = _Recorder()
    with _spot(recorder).messfenster("G3", stuetzstelle="0.30", hz=50):
        pass
    arten = [a for a, _ in recorder.ereignisse]
    assert arten == ["messfenster", "messfenster"]
    start, ende = (d for _a, d in recorder.ereignisse)
    assert start["phase"] == "start"
    assert start["name"] == "G3"
    assert start["hz_soll"] == 50
    assert start["stuetzstelle"] == "0.30"
    assert ende["phase"] == "ende"
    assert ende["name"] == "G3"


def test_takt_wird_gehoben_und_zurueckgestellt():
    abtaster = _Abtaster()
    with _spot(_Recorder(), abtaster).messfenster("G1", hz=50):
        assert abtaster.takt() == (50, True)
    assert abtaster.takt() == (10.0, False)


def test_ausnahme_schliesst_das_fenster_trotzdem():
    """Sonst bliebe der Lauf fuer immer auf 50 Hz und das Fenster ohne Ende."""
    recorder, abtaster = _Recorder(), _Abtaster()
    spot = _spot(recorder, abtaster)
    with pytest.raises(ValueError):
        with spot.messfenster("G6", hz=50):
            raise ValueError("Stoss danebengegangen")
    assert abtaster.takt() == (10.0, False)
    assert [d["phase"] for _a, d in recorder.ereignisse] == ["start", "ende"]


def test_verschachtelte_fenster_sind_verboten():
    spot = _spot(_Recorder(), _Abtaster())
    with spot.messfenster("aussen"):
        with pytest.raises(SpotlabError) as fehler:
            with spot.messfenster("innen"):
                pass
    assert "aussen" in str(fehler.value)


def test_nach_ausnahme_ist_wieder_ein_fenster_moeglich():
    spot = _spot(_Recorder(), _Abtaster())
    with pytest.raises(ValueError):
        with spot.messfenster("erstes"):
            raise ValueError
    with spot.messfenster("zweites"):
        pass


def test_ohne_abtaster_schreibt_es_nur_marken():
    """Ein direkt gebauter Spot (Test, Attrappe) darf daran nicht scheitern."""
    recorder = _Recorder()
    with _spot(recorder).messfenster("G1"):
        pass
    assert len(recorder.ereignisse) == 2


def test_ohne_recorder_faellt_nichts_um():
    with _spot().messfenster("G1"):
        pass


def test_reservierte_feldnamen_werden_abgewiesen():
    spot = _spot(_Recorder(), _Abtaster())
    for verboten in ("phase", "name", "hz_soll"):
        with pytest.raises(SpotlabError):
            with spot.messfenster("G1", **{verboten: "x"}):
                pass
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_messfenster.py -q
```

Erwartet: `assert "messfenster" in ARTEN` schlägt fehl.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/record/events.py` — die neue Art in die Menge:

```python
ARTEN = frozenset(
    {
        "verbunden",
        "power_on",
        "power_off",
        "kommando",
        "rückmeldung",
        "bild",
        "messfenster",
        "fehler",
        "lease_verloren",
        "lease_übernommen",
        "ende",
    }
)
```

`src/spotlab/api/spot.py` — Import und Konstruktor:

```python
import contextlib

from spotlab.api import motion, navigation, perception, posture
from spotlab.api.state import from_proto
from spotlab.config import Limits
from spotlab.errors import SpotlabError

RESERVIERT = ("phase", "name", "hz_soll")


class Spot:
    def __init__(self, backend, recorder=None, limits=None, robot=None,
                 workspace=None, active_map=None, sampler=None):
        self.backend = backend
        self.recorder = recorder
        self.limits = limits or Limits()
        self.sampler = sampler
        self._robot = robot
        self._karte = None
        self._workspace = workspace
        self._active_map = active_map
        self._fenster_offen = None
```

Und die Methode, ans Ende der Klasse vor `close()`:

```python
    @contextlib.contextmanager
    def messfenster(self, name, hz=50.0, **felder):
        """Markiert ein Messfenster und tastet darin dicht und vollständig ab.

        Innerhalb des Blocks laeuft die Abtastung mit `hz` und schreibt den
        vollen Umfang; danach wieder wie zuvor. Die Marken landen als Ereignisse
        in der Aufzeichnung, damit spaeter feststeht, welche Abtastungen zu
        welcher Bedingung gehoeren.

            with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
                spot.walk(vx=0.30, duration=8.0)
        """
        doppelt = [k for k in RESERVIERT if k in felder]
        if doppelt:
            raise SpotlabError(
                f"Die Feldnamen {', '.join(doppelt)} sind im Messfenster belegt. "
                "Nimm einen anderen Namen."
            )
        if self._fenster_offen is not None:
            raise SpotlabError(
                f"Es ist schon ein Messfenster offen: „{self._fenster_offen}“. "
                "Verschachtelte Fenster wären in der Auswertung nicht auseinanderzuhalten."
            )

        self._fenster_offen = name
        vorher = self.sampler.takt() if self.sampler is not None else None
        if self.recorder is not None:
            self.recorder.event("messfenster", phase="start", name=name, hz_soll=hz, **felder)
        if self.sampler is not None:
            self.sampler.setze_takt(hz, True)
        try:
            yield
        finally:
            # Ohne finally bliebe der Lauf nach einer Ausnahme fuer immer auf 50 Hz
            # und das Fenster ohne Ende.
            if self.sampler is not None and vorher is not None:
                self.sampler.setze_takt(*vorher)
            if self.recorder is not None:
                self.recorder.event("messfenster", phase="ende", name=name, **felder)
            self._fenster_offen = None
```

`src/spotlab/__init__.py` — den Abtaster **vor** dem `Spot` bauen und durchreichen. Bisher:

```python
    spot = Spot(unten, recorder=recorder, limits=grenzen, robot=roher_roboter, ...)
    abtaster = StateSampler(unten, recorder)
    abtaster.start()
```

Neu:

```python
    abtaster = StateSampler(unten, recorder)
    spot = Spot(
        unten,
        recorder=recorder,
        limits=grenzen,
        robot=roher_roboter,
        workspace=(cfg.workspace if cfg else None),
        active_map=(cfg.active_map if cfg else None),
        sampler=abtaster,
    )
    abtaster.start()
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_messfenster.py -q
python -m pytest -q
```

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/record/events.py src/spotlab/api/spot.py src/spotlab/__init__.py tests/test_messfenster.py
git commit -m "feat(api): Messfenster als Kontextmanager mit eigener Abtastrate"
```

---

**Ende Teil 1.** Weiter mit `docs/superpowers/plans/2026-08-08-spotlab-kalibrierung-teil2.md`
(Aufgaben 5–9: Fenstererkennung, Kennzahlen, Lückenmelder, Doktor-Zeile, Dokumentation).
