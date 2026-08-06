"""Roboterzustand als handliche Datenklasse — und als flache Abtastung für zustand.jsonl.

Die flache Form ist die Kalibrierdatenquelle für Real→Sim: kommandierte gegen
gemessene Geschwindigkeit, Gelenkverläufe, Fusskontakt-Timing.
"""

import math
from dataclasses import dataclass

from bosdyn.api import robot_state_pb2
from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, get_a_tform_b


@dataclass(frozen=True)
class JointState:
    position: float
    velocity: float
    load: float


@dataclass(frozen=True)
class State:
    battery: float
    powered: bool
    pose: tuple
    velocity: tuple
    joints: dict
    feet: tuple


def _yaw_aus(quaternion):
    w, x, y, z = quaternion.w, quaternion.x, quaternion.y, quaternion.z
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def from_proto(zustand):
    akku = zustand.battery_states[0].charge_percentage.value if zustand.battery_states else 0.0
    kinematik = zustand.kinematic_state

    x = y = yaw = 0.0
    try:
        odom_tform_body = get_a_tform_b(
            kinematik.transforms_snapshot, ODOM_FRAME_NAME, BODY_FRAME_NAME
        )
        if odom_tform_body is not None:
            x = odom_tform_body.position.x
            y = odom_tform_body.position.y
            yaw = _yaw_aus(odom_tform_body.rotation)
    except Exception:  # Schnappschuss unvollständig — Pose bleibt Ursprung
        pass

    geschwindigkeit = kinematik.velocity_of_body_in_odom
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
            g.name: JointState(g.position.value, g.velocity.value, g.load.value)
            for g in kinematik.joint_states
        },
        feet=tuple(
            f.contact == robot_state_pb2.FootState.CONTACT_MADE for f in zustand.foot_state
        ),
    )


def as_sample(zustand):
    s = from_proto(zustand)
    return {
        "battery": s.battery,
        "powered": s.powered,
        "pose": list(s.pose),
        "velocity": list(s.velocity),
        "joints": {
            name: {"position": g.position, "velocity": g.velocity, "load": g.load}
            for name, g in s.joints.items()
        },
        "feet": list(s.feet),
    }
