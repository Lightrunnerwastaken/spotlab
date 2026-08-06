"""Bewegung auf zwei Ebenen.

move()  — relative Zieltrajektorie: „geh einen Meter" ohne Zeitintegration.
walk()  — Geschwindigkeitskommando des SDK, Andockpunkt für Regelschleifen
          und spätere neuronale Netze.

Der Geschwindigkeitsdeckel klemmt und weist nicht ab: ein Tippfehler soll
langsam sein, nicht knallen.
"""

import math
import time

from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.api.posture import warte_auf
from spotlab.backends.base import Capability, require

NACHSENDE_INTERVALL_S = 0.4
KOMMANDO_GUELTIGKEIT_S = 1.0


def clamp(vx, vy, wz, limits):
    """Klemmt auf die Konfigurationsgrenzen und erhält dabei die Fahrtrichtung."""
    betrag = math.hypot(vx, vy)
    if betrag > limits.max_speed and betrag > 0.0:
        faktor = limits.max_speed / betrag
        vx, vy = vx * faktor, vy * faktor
    wz = max(-limits.max_turn_rate, min(limits.max_turn_rate, wz))
    return float(vx), float(vy), float(wz)


def walk(
    backend,
    recorder,
    limits,
    vx=0.0,
    vy=0.0,
    wz=0.0,
    duration=1.0,
    schlaf=time.sleep,
    jetzt=time.monotonic,
):
    """Fährt `duration` Sekunden mit der gegebenen Geschwindigkeit.

    Geschwindigkeitskommandos verfallen beim echten Spot — deshalb sendet diese
    Funktion laufend nach. Genau das soll kein Schüler selbst bauen müssen.
    """
    require(backend, Capability.LOCOMOTION, "gehen")
    vx, vy, wz = clamp(vx, vy, wz, limits)
    if recorder is not None:
        recorder.event("kommando", name="walk", vx=vx, vy=vy, wz=wz, duration=duration)

    ende = jetzt() + float(duration)
    while jetzt() < ende:
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(v_x=vx, v_y=vy, v_rot=wz),
            end_time_secs=KOMMANDO_GUELTIGKEIT_S,
        )
        schlaf(NACHSENDE_INTERVALL_S)
    stop(backend, recorder)


def move(backend, recorder, limits, forward=0.0, left=0.0, turn=0.0, timeout=30.0,
         schlaf=time.sleep):
    """Relatives Ziel im Körperframe. `turn` in GRAD (Schülerfreundlichkeit)."""
    require(backend, Capability.LOCOMOTION, "gehen")
    if forward == 0.0 and left == 0.0 and turn == 0.0:
        return
    winkel = math.radians(float(turn))
    if recorder is not None:
        recorder.event(
            "kommando",
            name="move",
            forward=float(forward),
            left=float(left),
            turn_grad=float(turn),
        )
    kommando = RobotCommandBuilder.synchro_trajectory_command_in_body_frame(
        goal_x_rt_body=float(forward),
        goal_y_rt_body=float(left),
        goal_heading_rt_body=winkel,
        frame_tree_snapshot=backend.frame_tree_snapshot(),
    )
    kennung = backend.send_command(kommando)
    warte_auf(backend, kennung, timeout, "ankommen", schlaf)
    if recorder is not None:
        recorder.event("rückmeldung", name="move", status="angekommen")


def stop(backend, recorder):
    require(backend, Capability.LOCOMOTION, "anhalten")
    if recorder is not None:
        recorder.event("kommando", name="stop")
    backend.send_command(RobotCommandBuilder.stop_command())
