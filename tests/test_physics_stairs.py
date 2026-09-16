"""Positionsabhaengige GUI-Beispielroute ueber echte SDK-Kommandos, offline."""

import numpy as np
import pytest
from bosdyn.client.robot_command import RobotCommandBuilder as B

from spotlab.backends import physics
from spotlab.backends.physics import PhysicsBackend
from spotlab.errors import UnsupportedCapability
from spotlab.welt.raum import Boden, Raum, raum_laden
from tests_zeitgrenzen import simuhr

spotsim = pytest.importorskip('spotsim')
pytestmark = pytest.mark.skipif(not spotsim.spot_asset_available(), reason='Menagerie fehlt')


# 120 Beinschritte, 411 s Sim-Zeit, 194 s Wanduhr allein (09.09.2026; 260 s neben einer
# laufenden Suite am 16.09.2026). Unter der Last dreier paralleler Suiten bekam der
# Prozess rund ein Sechstel eines Kerns: ein Beinschritt dauert dann etwa 7 s Wanduhr,
# und eine Frist `time.time()+30` je Kommando laeuft innerhalb weniger Schritte ab --
# dasselbe Muster wie in test_physics_single_step, deshalb dieselbe Sim-Uhr. Die Marke
# ist das Netz gegen Haengen, kein Mass fuer die Sache.
@pytest.mark.timeout(3600)
def test_three_stairs_route_and_stop(monkeypatch):
    b = PhysicsBackend(raum=raum_laden('physik_treppe_3stufen'), autostart=False, realtime=False)
    uhr = simuhr(b)
    monkeypatch.setattr(physics, 'time', uhr)
    try:
        b.power_on()
        for target, direction in ((1.75, 1), (-.03, -1)):
            count = 0
            while direction*(b.qpos()[0]-target) < 0:
                b.send_command(B.synchro_velocity_command(direction*.02, 0, 0),
                               end_time_secs=uhr.time()+30)
                b.advance(.001)
                count += 1
                assert count < 85
            key = b.send_command(B.synchro_stand_command())
            b.advance(2)
            assert b.command_feedback(key).done
            feet = np.array([b.sim.data.geom_xpos[b.sim.stepper.pc.legs.foot_geom[leg]]
                             for leg in ('fl', 'fr', 'hl', 'hr')])
            if direction > 0:
                assert np.min(feet[:, 2]) > .134
            else:
                assert np.max(feet[:, 2]) < .05
        assert not b.sim.metrics.fell
        assert min(r.min_support_margin for r in b.sim.stepper.results) >= .03
    finally:
        b.close()


def test_ordinary_stairs_remain_rejected():
    room = Raum('hoch', '', (0, 0, 0), boeden=(Boden('Treppe', 1, 0, 2, 2, z=0, anstieg=.6, stufen=3),))
    with pytest.raises(UnsupportedCapability):
        PhysicsBackend(raum=room, autostart=False)
    with pytest.raises(UnsupportedCapability, match='Start'):
        PhysicsBackend(raum=raum_laden('physik_treppe_3stufen'), start=(.02, 0, 0), autostart=False)
