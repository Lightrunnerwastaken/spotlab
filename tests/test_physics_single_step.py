"""End-to-end: SDK-Protobuf -> Physik-Backend -> Einzelstufenplaner."""
import time

import numpy as np
import pytest
from bosdyn.client.robot_command import RobotCommandBuilder as B

from spotlab.backends.physics import PhysicsBackend
from spotlab.errors import UnsupportedCapability
from spotlab.welt.raum import Boden, Raum

spotsim = pytest.importorskip('spotsim')
pytestmark = pytest.mark.skipif(not spotsim.spot_asset_available(), reason='Menagerie fehlt')


def room():
    return Raum('Einzelstufe', '6 cm', (0, 0, 0),
                boeden=(Boden('Podest', .9, 0, .9, 2, z=.06),))


def test_sdk_up_and_backward_down():
    b = PhysicsBackend(raum=room(), autostart=False, realtime=False)
    try:
        b.power_on()
        b.send_command(B.synchro_velocity_command(.02, 0, 0), end_time_secs=time.time()+120)
        for _ in range(28):
            b.advance(.001)
        feet = b.sim.stepper.pc.feet_world
        assert np.min(feet[:, 2]) > .065
        assert not b.sim.metrics.fell
        b.send_command(B.synchro_velocity_command(-.02, 0, 0), end_time_secs=time.time()+120)
        for _ in range(28):
            b.advance(.001)
        assert np.max(b.sim.stepper.pc.feet_world[:, 2]) < .05
        key = b.send_command(B.stop_command())
        b.advance(1)
        assert b.command_feedback(key).done
        assert np.linalg.norm(b.sim.data.qvel[:2]) < .04
        assert b.bericht()['terrain_source'] == 'scene_oracle'
        assert b.bericht()['modell_masse_kg'] < 60
    finally:
        b.close()


def test_step_mode_rejects_turning_and_high_platform():
    b = PhysicsBackend(raum=room(), autostart=False, realtime=False)
    try:
        b.power_on()
        with pytest.raises(UnsupportedCapability, match='kein Drehen'):
            b.send_command(B.synchro_velocity_command(.01, 0, .1), end_time_secs=time.time()+10)
    finally:
        b.close()
    high = Raum('hoch', '', (0, 0, 0), boeden=(Boden('Podest', .9, 0, .9, 2, z=.17),))
    with pytest.raises(UnsupportedCapability):
        PhysicsBackend(raum=high)
