"""Roboterzustand als handliche Datenklasse — und als flache Abtastung für zustand.jsonl.

Die flache Form ist die Kalibrierdatenquelle für Real→Sim: kommandierte gegen
gemessene Geschwindigkeit, Gelenkverläufe mit Drehmoment, Fusskontakt-Timing,
Reibwerte.

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
    faults: dict = field(default_factory=dict)


def rpy_aus(quaternion):
    """Roll, Pitch, Yaw aus einem Quaternion. Die Yaw-Formel ist bitgleich zu früher."""
    w, x, y, z = quaternion.w, quaternion.x, quaternion.y, quaternion.z
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    # asin klemmen: numerisches Rauschen kann |sin| knapp über 1 treiben
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return roll, pitch, yaw


def _name_von(enum_typ, wert):
    """Enum-Namen statt Zahl — eine 3 sagt in fünf Jahren niemandem mehr etwas."""
    try:
        return enum_typ.Name(wert)
    except (ValueError, KeyError):
        return str(wert)


def _fehler(zustand):
    """Fehlerzustände des Roboters, rein tatsächlich.

    G2, G3 und G4 fordern „kein Sturz" als Kriterium; die reale Aufzeichnung
    hatte dafür kein Gegenstück. Ein Roboter, der wegen eines Behavior Fault
    stehenbleibt, sah in den Daten aus wie einer, der einfach langsam war.

    Kein Werturteil, keine Schwellen — was ein Fehler für ein Gate bedeutet,
    entscheidet matura-spot. Leere Listen sind eine MESSUNG („keine Fehler"),
    kein fehlender Wert.
    """
    from bosdyn.api import robot_state_pb2 as rs

    return {
        "behavior": [
            {
                "id": f.behavior_fault_id,
                "ursache": _name_von(rs.BehaviorFault.Cause, f.cause),
                "status": _name_von(rs.BehaviorFault.Status, f.status),
            }
            for f in zustand.behavior_fault_state.faults
        ],
        "system": [
            {
                "name": f.name,
                "schwere": _name_von(rs.SystemFault.Severity, f.severity),
                "code": f.code,
            }
            for f in zustand.system_fault_state.faults
        ],
        "service": [
            {
                "name": f.fault_id.fault_name,
                "schwere": _name_von(rs.ServiceFault.Severity, f.severity),
            }
            for f in zustand.service_fault_state.faults
        ],
    }


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
        velocity=(
            geschwindigkeit.linear.x,
            geschwindigkeit.linear.y,
            geschwindigkeit.angular.z,
        ),
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
        faults=_fehler(zustand),
    )


def as_sample(zustand, reich=False):
    """Flache Abtastung für zustand.jsonl.

    `reich=True` nur im Messfenster: rund das Neunfache an Bytes, und 50 RPCs je
    Sekunde über WLAN sind in einem Schülerlauf Last für Daten, die niemand ansieht.
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
        # Immer dabei: vier Zahlen, und ohne sie ist G1 (Höhe, Neigung) nicht messbar.
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
            # Nur im reichen Satz: Messfenster sind reich, und genau dort gilt
            # das Sturz-Kriterium der Gates. Der schlanke Satz bleibt so
            # schmal, wie er seit Stufe 1 ist.
            "faults": dict(s.faults),
        }
    )
    return satz
