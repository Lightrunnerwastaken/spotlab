import json
import math

import pytest
from bosdyn.api import robot_state_pb2
from bosdyn.api.geometry_pb2 import Quaternion
from google.protobuf import wrappers_pb2

from spotlab.api.state import as_sample, from_proto, rpy_aus
from spotlab.backends.dryrun import DryRunBackend


def test_zustand_aus_protobuf():
    backend = DryRunBackend()
    backend.power_on()
    zustand = from_proto(backend.robot_state())
    assert zustand.battery == 87.0
    assert zustand.powered is True
    assert len(zustand.joints) == 12
    assert zustand.joints["fl.hx"].position == 0.0
    assert zustand.feet == (True, True, True, True)


def test_pose_aus_identitaet_ist_ursprung():
    zustand = from_proto(DryRunBackend().robot_state())
    x, y, yaw = zustand.pose
    assert (x, y) == (0.0, 0.0)
    assert math.isclose(yaw, 0.0, abs_tol=1e-9)


def test_abtastung_ist_flach_und_json_faehig():
    probe = as_sample(DryRunBackend().robot_state())
    json.dumps(probe)  # darf nicht werfen
    assert probe["battery"] == 87.0
    assert probe["pose"] == [0.0, 0.0, 0.0]
    assert probe["joints"]["fl.hy"]["position"] == 0.0
    assert probe["feet"] == [True, True, True, True]


# --------------------------------------------------------- Kalibrierfelder (Stufe 7)


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
    roll, pitch, yaw = rpy_aus(Quaternion(w=1.0, x=0.0, y=0.0, z=0.0))
    assert (roll, pitch, yaw) == (0.0, 0.0, 0.0)

    halb = math.sqrt(0.5)
    _r, _p, yaw = rpy_aus(Quaternion(w=halb, x=0.0, y=0.0, z=halb))
    assert yaw == pytest.approx(math.pi / 2, abs=1e-9)

    roll, _p, _y = rpy_aus(
        Quaternion(w=math.cos(math.radians(15)), x=math.sin(math.radians(15)), y=0.0, z=0.0)
    )
    assert roll == pytest.approx(math.radians(30), abs=1e-9)


def test_hoehe_und_neigung_kommen_an():
    """G1 misst Körperhöhe und Neigung — beides fehlte bisher vollständig."""
    s = from_proto(_voller_zustand())
    assert s.z == pytest.approx(0.419)
    assert s.roll == pytest.approx(0.0)
    assert s.pitch == pytest.approx(0.0)
    assert s.pose == pytest.approx((1.0, 2.0, 0.0))


def test_roboterzeitstempel():
    assert from_proto(_voller_zustand()).t_robot == pytest.approx(1786293840.123, abs=1e-6)


def test_gelenk_mit_beschleunigung_und_last():
    g = from_proto(_voller_zustand()).joints["fl.hx"]
    assert (g.position, g.velocity, g.acceleration, g.load) == pytest.approx(
        (0.1, 0.2, 0.3, 12.5)
    )


def test_fuss_terrain():
    fuss = from_proto(_voller_zustand()).feet_detail[0]
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
    klein = len(json.dumps(as_sample(_voller_zustand())))
    gross = len(json.dumps(as_sample(_voller_zustand(), reich=True)))
    assert gross > klein


# ============================================== S3.5 Hardwarefehler ohne Sturz
#
# G2, G3 und G4 fordern "kein Sturz" als Kriterium. Die reale Aufzeichnung
# lieferte dafuer bisher kein Gegenstueck: behavior_fault_state,
# system_fault_state und service_fault_state wurden nie gelesen. Ein Roboter,
# der wegen eines Behavior Fault stehenbleibt, sah in den Daten aus wie einer,
# der einfach langsam war.


def _mit_fehlern():
    from bosdyn.api import robot_state_pb2

    from spotlab.backends.dryrun import DryRunBackend

    zustand = DryRunBackend().robot_state()
    bf = zustand.behavior_fault_state.faults.add()
    bf.behavior_fault_id = 7
    bf.cause = robot_state_pb2.BehaviorFault.CAUSE_FALL
    bf.status = robot_state_pb2.BehaviorFault.STATUS_UNCLEARABLE
    sf = zustand.system_fault_state.faults.add()
    sf.name = "hip motor hot"
    sf.severity = robot_state_pb2.SystemFault.SEVERITY_WARN
    sf.code = 42
    return zustand


def test_fehlerzustaende_landen_im_reichen_satz():
    from spotlab.api.state import as_sample

    satz = as_sample(_mit_fehlern(), reich=True)
    assert satz["faults"]["behavior"] == [
        {"id": 7, "ursache": "CAUSE_FALL", "status": "STATUS_UNCLEARABLE"}
    ]
    assert satz["faults"]["system"] == [
        {"name": "hip motor hot", "schwere": "SEVERITY_WARN", "code": 42}
    ]
    assert satz["faults"]["service"] == []


def test_keine_fehler_ist_eine_gemessene_leere_liste():
    """Unterschied zwischen "gemessen und keine" und "nicht gemessen" --
    er entscheidet, ob eine Kalibrierung gueltig ist."""
    from spotlab.api.state import as_sample
    from spotlab.backends.dryrun import DryRunBackend

    satz = as_sample(DryRunBackend().robot_state(), reich=True)
    assert satz["faults"] == {"behavior": [], "system": [], "service": []}


def test_der_schlanke_satz_traegt_keine_fehlerlisten():
    """Bestehende Schluessel in zustand.jsonl aendern sich nicht, und 50 RPCs
    je Sekunde sollen nicht dicker werden als noetig. Messfenster sind reich --
    genau dort gilt das Sturz-Kriterium."""
    from spotlab.api.state import as_sample

    assert "faults" not in as_sample(_mit_fehlern(), reich=False)


def test_der_zustand_kennt_die_fehler_auch_direkt():
    from spotlab.api.state import from_proto

    s = from_proto(_mit_fehlern())
    assert s.faults["behavior"][0]["ursache"] == "CAUSE_FALL"
