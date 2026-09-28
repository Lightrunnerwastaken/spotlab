"""Physikmodus Stufe B: sitzend starten, aufstehen, hinsetzen, abschalten, Körperhaltung (28.09.2026).

Ohne Echtzeit auf der Sim-Uhr. Braucht ein spotsim mit `HALTUNG_FASSUNG >= 1` (matura-spot
ab 28.09.2026); mit einem älteren gilt Stufe A, und das prüft der letzte Test.
"""
import json
import math
from types import SimpleNamespace

import pytest
from bosdyn.client.robot_command import RobotCommandBuilder as B
from bosdyn.geometry import EulerZXY

from spotlab.backends.physics import PhysicsBackend
from spotlab.errors import CommandRejected

spotsim = pytest.importorskip('spotsim')
pytestmark = [
    pytest.mark.skipif(not spotsim.spot_asset_available(), reason='Menagerie fehlt'),
    pytest.mark.skipif(getattr(spotsim, 'HALTUNG_FASSUNG', 0) < 1, reason='spotsim ohne Haltung'),
]


@pytest.fixture
def b():
    backend = PhysicsBackend(autostart=False, realtime=False)
    try:
        yield backend
    finally:
        backend.close()


def _bis(b, key, sim_s):
    ende = b.sim.time + sim_s
    while b.sim.time < ende:
        b.advance(.25)
        rueck = b.command_feedback(key)
        if rueck.done or rueck.rejected:
            return rueck
    return b.command_feedback(key)


def _lage_grad(b):
    w, x, y, z = b.qpos()[3:7]
    return (math.degrees(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))),
            math.degrees(math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))))


def _aufgestanden(b):
    b.power_on()
    rueck = _bis(b, b.send_command(B.synchro_stand_command()), 6)
    assert rueck.done and rueck.status == 'steht', rueck.status


def test_start_sitzend_motoren_aus_bis_power_on(b):
    assert b.kann_sitzen and b.kann_pose
    assert b.sim.haltung == 'aus' and b.qpos()[2] < .2
    b.power_on()
    b.advance(.5)
    assert b.sim.haltung == 'sitzt'


def test_gehen_erst_nach_stand(b):
    b.power_on()
    with pytest.raises(CommandRejected, match=r'stand\(\)'):
        b.send_command(B.synchro_velocity_command(.2, 0, 0), end_time_secs=b.uhr() + 2)
    z_sitz = float(b.qpos()[2])
    _aufgestanden(b)
    assert b.qpos()[2] - z_sitz == pytest.approx(.41, abs=.05)
    x0 = float(b.qpos()[0])
    b.send_command(B.synchro_velocity_command(.3, 0, 0), end_time_secs=b.uhr() + 3)
    b.advance(3)
    assert b.qpos()[0] - x0 > .3 and not b.sim.metrics.fell


def test_sit_meldet_sitzt(b):
    _aufgestanden(b)
    rueck = _bis(b, b.send_command(B.synchro_sit_command()), 8)
    assert rueck.done and rueck.status == 'sitzt', rueck.status
    assert b.qpos()[2] < .2 and b.sim.haltung == 'sitzt'


def test_power_off_setzt_hin_und_schaltet_ab(b):
    from bosdyn.api import robot_state_pb2

    _aufgestanden(b)
    b.power_off()
    b.advance(6)
    assert b.sim.haltung == 'aus' and b.qpos()[2] < .2
    assert b.robot_state().power_state.motor_power_state == robot_state_pb2.PowerState.STATE_OFF


def test_pose_im_stand(b):
    from spotlab.api.features import supports

    assert supports(SimpleNamespace(backend=b, robot=None), 'pose')
    _aufgestanden(b)
    rolle0 = _lage_grad(b)[0]
    kommando = B.synchro_stand_command(footprint_R_body=EulerZXY(roll=math.radians(15)))
    rueck = _bis(b, b.send_command(kommando), 6)
    assert rueck.done and rueck.status == 'steht'
    assert _lage_grad(b)[0] - rolle0 == pytest.approx(15, abs=2)


def test_zu_viel_pose_wird_gekappt_und_gemeldet(tmp_path):
    from spotlab.record.run import RunRecorder

    rec = RunRecorder(tmp_path, None, backend='physics')
    b = PhysicsBackend(recorder=rec, autostart=False, realtime=False)
    try:
        _aufgestanden(b)
        rolle0 = _lage_grad(b)[0]
        kommando = B.synchro_stand_command(footprint_R_body=EulerZXY(roll=math.radians(40)))
        _bis(b, b.send_command(kommando), 6)
        assert _lage_grad(b)[0] - rolle0 == pytest.approx(20, abs=2)
    finally:
        b.close()
        rec.finish('ok')
    zeilen = (rec.dir / 'ereignisse.jsonl').read_text(encoding='utf-8').splitlines()
    grenzen = [json.loads(z)['daten'] for z in zeilen
               if z.strip() and json.loads(z)['daten'].get('name') == 'physik_grenze']
    assert grenzen and grenzen[0]['roll_grad'] == pytest.approx(20, abs=.1)


def test_die_stufenszene_startet_stehend():
    from spotlab.welt.raum import raum_laden

    b = PhysicsBackend(raum=raum_laden('physik_einzelstufe'), start=(0, 0, 0),
                       autostart=False, realtime=False)
    try:
        assert b.sim.haltung == 'steht' and b.qpos()[2] > .4
    finally:
        b.close()


def test_mit_alter_spotsim_fassung_gilt_stufe_a(monkeypatch):
    import spotlab.backends.mujoco as mj

    monkeypatch.setattr(mj, '_haltung_fassung', lambda: 0)
    b = PhysicsBackend(autostart=False, realtime=False)
    try:
        assert b.kann_sitzen is False and b.kann_pose is False
        assert b.sim.haltung == 'steht'
        b.power_on()
        with pytest.raises(Exception, match='Sitzen'):
            b.send_command(B.synchro_sit_command())
    finally:
        b.close()
