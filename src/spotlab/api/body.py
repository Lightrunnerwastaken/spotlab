"""Koerperausrichtung im Stand, Winkel in Grad wie move(turn=...)."""

import math

from bosdyn.client.robot_command import RobotCommandBuilder
from bosdyn.geometry import EulerZXY

from spotlab.api.convenience import zahl
from spotlab.api.features import supports
from spotlab.api.posture import warte_auf
from spotlab.errors import UnsupportedCapability


def pose(spot, roll=0.0, pitch=0.0, yaw=0.0, height=0.0, timeout=10.0):
    roll = zahl(roll, 'roll', -20, 20)
    pitch = zahl(pitch, 'pitch', -20, 20)
    yaw = zahl(yaw, 'yaw', -30, 30)
    height = zahl(height, 'height', -.15, .15)
    timeout = zahl(timeout, 'timeout', .1, 60)
    if not supports(spot, 'pose'):
        raise UnsupportedCapability('pose() ist am Roboter und im Trockenlauf verfuegbar; Sim/MuJoCo bilden es noch nicht ab.')
    command = RobotCommandBuilder.synchro_stand_command(
        body_height=height,
        footprint_R_body=EulerZXY(roll=math.radians(roll), pitch=math.radians(pitch), yaw=math.radians(yaw)),
    )
    if spot.recorder is not None:
        spot.recorder.event('kommando', name='pose', roll=roll, pitch=pitch, yaw=yaw, height=height)
    kennung = spot.backend.send_command(command)
    warte_auf(spot.backend, kennung, timeout, 'Koerper ausrichten')
    if spot.recorder is not None:
        spot.recorder.event('rückmeldung', name='pose', status='steht')
