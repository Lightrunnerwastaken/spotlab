"""Der Geschwindigkeitsdeckel als Protobuf — an genau einer Stelle.

Warum hier und nicht in `api/`: `RobotCommandBuilder.mobility_params()` kennt
gar keinen Parameter `vel_limit` (geprüft an bosdyn-client 5.0.1.2 — die
Signatur führt nur body_height, footprint_R_body, locomotion_hint, stair_hint,
external_force_params, stairs_mode). Das Feld muss direkt am Protobuf gesetzt
werden, und rohe Protobuf-Nachrichten gehören nach Projektregel nicht nach
`api/`. Also bauen die Backends sie, und `api/` reicht das Ergebnis nur durch —
dieselbe Naht wie bei `frame_tree_snapshot()`.

Warum an EINER Stelle: Autonome Fahrt (GraphNav `travel_params`) und
Zieltrajektorie (`move`) brauchen denselben Deckel. Zwei Formulierungen
desselben Grenzwerts wären zwei Gelegenheiten, ihn unterschiedlich falsch zu
schreiben — und die eine, die stimmt, verdeckte die andere.
"""

from bosdyn.api import geometry_pb2
from bosdyn.api.spot import robot_command_pb2 as spot_command_pb2


def se2_grenze(limits):
    """SE2VelocityLimit aus den Konfigurationsgrenzen.

    `min_vel` muss mitgesetzt werden, sonst bremst nur die Vorwärtsfahrt und der
    Roboter fährt rückwärts oder seitwärts ungedeckelt.
    """
    return geometry_pb2.SE2VelocityLimit(
        max_vel=geometry_pb2.SE2Velocity(
            linear=geometry_pb2.Vec2(x=limits.max_speed, y=limits.max_speed),
            angular=limits.max_turn_rate,
        ),
        min_vel=geometry_pb2.SE2Velocity(
            linear=geometry_pb2.Vec2(x=-limits.max_speed, y=-limits.max_speed),
            angular=-limits.max_turn_rate,
        ),
    )


def mit_grenze(limits):
    """MobilityParams, die NICHTS anderes tun als den Deckel zu setzen.

    Bewusst ein nacktes Protobuf statt `RobotCommandBuilder.mobility_params()`:
    jenes setzt zusätzlich eine Körperhöhen-Trajektorie und einen
    Fortbewegungs-Hinweis, die hier niemand bestellt hat. Alles Ungesetzte
    entscheidet der Roboter selbst — das ist die Absicht.
    """
    return spot_command_pb2.MobilityParams(vel_limit=se2_grenze(limits))
