"""Physik-Adapter: echte Kontakte, Zeit und getrennte GUI-Zugriffe."""
import time

import numpy as np
import pytest
from bosdyn.client.robot_command import RobotCommandBuilder as B

from spotlab.backends.physics import PhysicsBackend
from spotlab.errors import CommandRejected, NotPowered, UnsupportedCapability

spotsim = pytest.importorskip('spotsim')
pytestmark = pytest.mark.skipif(not spotsim.spot_asset_available(), reason='Menagerie fehlt')


@pytest.fixture
def backend():
    b = PhysicsBackend(autostart=False, realtime=False)
    try:
        yield b
    finally:
        b.close()


def test_stand_is_carried_by_contacts_and_reads_do_not_step(backend):
    b = backend
    with pytest.raises(NotPowered):
        b.send_command(B.synchro_stand_command())
    b.power_on()
    key = b.send_command(B.synchro_stand_command())
    b.advance(1)
    assert b.command_feedback(key).done
    assert .3 < b.qpos()[2] < .55
    q = b.qpos()
    t = b.sim.time
    for _ in range(20):
        b.robot_state()
        b.frame_tree_snapshot()
    assert b.sim.time == t
    np.testing.assert_array_equal(b.qpos(), q)
    assert any(b.sim.sensors.foot_contacts().values())


def test_walk_and_stop_use_physics_and_measured_feedback(backend):
    b = backend
    b.power_on()
    before = b.qpos().copy()
    b.send_command(B.synchro_velocity_command(.15, 0, 0), end_time_secs=time.time()+60)
    b.advance(6)
    assert b.qpos()[0] - before[0] > .1
    assert not b.sim.metrics.fell
    key = b.send_command(B.stop_command())
    b.advance(5)
    assert np.linalg.norm(b.sim.data.qvel[:2]) < .04
    assert b.command_feedback(key).done


def test_unsupported_commands_do_not_fake_success(backend):
    b = backend
    b.power_on()
    for cmd in (B.synchro_sit_command(), B.synchro_stand_command(body_height=.1)):
        with pytest.raises(UnsupportedCapability):
            b.send_command(cmd)
    with pytest.raises(CommandRejected):
        b.send_command(B.synchro_velocity_command(.1, 0, 0), end_time_secs=time.time()-1)


def test_velocity_expiry_uses_wall_clock_even_when_sim_is_slow(backend, monkeypatch):
    b = backend
    b.power_on()
    wall = time.time()
    monkeypatch.setattr('spotlab.backends.physics.time.time', lambda: wall)
    b.send_command(B.synchro_velocity_command(.15, 0, 0), end_time_secs=wall+.5)
    b.advance(.2)
    wall += 1
    b.advance(5)
    assert np.linalg.norm(b.sim.data.qvel[:2]) < .04


def test_terrain_is_explicitly_not_validated():
    from spotlab.welt.raum import raum_laden

    with pytest.raises(UnsupportedCapability, match='ebenen Raum'):
        PhysicsBackend(raum=raum_laden('treppe'))


def test_start_yaw_is_degrees():
    b = PhysicsBackend(start=(1, 2, 90), autostart=False, realtime=False)
    try:
        q = b.qpos()[3:7]
        yaw = np.arctan2(2*(q[0]*q[3]+q[1]*q[2]), 1-2*(q[2]**2+q[3]**2))
        assert yaw == pytest.approx(np.pi/2, abs=.05)
    finally:
        b.close()


def test_worker_advances_without_sensor_polling_and_closes():
    b = PhysicsBackend()
    try:
        first = b.robot_state().kinematic_state.acquisition_timestamp
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            time.sleep(.05)
            last = b.robot_state().kinematic_state.acquisition_timestamp
            if last.seconds + last.nanos/1e9 > first.seconds + first.nanos/1e9 + .2:
                break
        else:
            pytest.fail('Worker hat Physikzeit nicht weitergerechnet')
        assert b._error is None
    finally:
        b.close()
    assert not b._thread.is_alive()


def test_connect_process_render_and_teardown(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root/'src'), SPOTLAB_NUR_TROCKEN='1',
               SPOTLAB_RAUM='', SPOTLAB_RAUM_START='', PYTHONDONTWRITEBYTECODE='1')
    code = '''import time
from spotlab import connect
with connect(backend="physics", runs_dir="runs", config_path="missing.toml") as spot:
    spot.power_on()
    spot.stand(timeout=5)
    print(spot.state.z)
    time.sleep(.4)
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    runs = list((tmp_path/'runs').glob('*/lauf.json'))
    assert len(runs) == 1
    record = json.loads(runs[0].read_text(encoding='utf-8'))
    assert record['backend'] == 'physics'
    assert (runs[0].parent/'ansicht.jpg').is_file()


def test_failed_physics_start_closes_record(tmp_path):
    from spotlab import connect

    with pytest.raises(UnsupportedCapability):
        with connect(backend='physics', raum='treppe', runs_dir=tmp_path,
                     config_path=tmp_path/'missing.toml'):
            pytest.fail('Hoehenraum wurde akzeptiert')
    records = list(tmp_path.glob('*/lauf.json'))
    assert len(records) == 1
    assert 'fehler' in records[0].read_text(encoding='utf-8')
