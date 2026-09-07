"""Regressionen: Beobachten darf weder Fahrt verlieren noch Erfolg erfinden."""

import math
import threading

import pytest
from bosdyn.client.robot_command import RobotCommandBuilder as B

from spotlab.backends.sim import SimBackend


class Uhr:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture(params=['sim', 'mujoco'])
def roboter(request):
    uhr = Uhr()
    cls = SimBackend
    if request.param == 'mujoco':
        spotsim = pytest.importorskip('spotsim')
        if not spotsim.spot_asset_available():
            pytest.skip('Menagerie fehlt')
        from spotlab.backends.mujoco import MujocoBackend

        cls = MujocoBackend
    b = cls(jetzt=uhr)
    b.power_on()
    yield b, uhr
    b.close()


def ziel(b, uhr, strecke=1.0, dauer=30.0):
    return b.send_command(
        B.synchro_trajectory_command_in_body_frame(strecke, 0, 0, b.frame_tree_snapshot()),
        end_time_secs=uhr.t + dauer,
    )


def test_ablauf_integriert_gueltigen_anteil_und_meldet_stillstand(roboter):
    b, uhr = roboter
    b.send_command(B.synchro_velocity_command(.3, 0, 0), end_time_secs=uhr.t + 1)
    uhr.t += 1.1
    s = b.robot_state()
    assert b._pose[0] == pytest.approx(.3, abs=1e-6)
    assert s.kinematic_state.velocity_of_body_in_odom.linear.x == 0
    uhr.t += 10
    b.robot_state()
    assert b._pose[0] == pytest.approx(.3, abs=1e-6)


def test_unerreichtes_ziel_ist_nach_ablauf_abgelehnt(roboter):
    b, uhr = roboter
    k = ziel(b, uhr, dauer=.1)
    uhr.t += .2
    rueck = b.command_feedback(k)
    assert rueck.rejected and not rueck.done
    assert 'abgelaufen' in rueck.status
    assert b.command_feedback(k) == rueck


def test_ersetztes_ziel_erbt_nicht_den_erfolg_des_neuen(roboter):
    b, uhr = roboter
    alt = ziel(b, uhr)
    neu = ziel(b, uhr, strecke=.2)
    uhr.t += 5
    assert b.command_feedback(neu).done
    assert b.command_feedback(alt).rejected


def test_ausschalten_beendet_ziel(roboter):
    b, uhr = roboter
    k = ziel(b, uhr)
    b.power_off()
    b.power_on()
    uhr.t += 5
    assert b.command_feedback(k).rejected
    assert b._pose[0] == 0


def test_grobe_und_feine_abfragen_liefern_denselben_verlauf():
    positionen = []
    for dt in (.02, .1, .25, 1., .037):
        uhr = Uhr()
        b = SimBackend(jetzt=uhr)
        b.power_on()
        ziel(b, uhr)
        for i in range(1, math.ceil(2 / dt) + 1):
            uhr.t = 1_000_000 + min(2, i * dt)
            b.robot_state()
        positionen.append(b._pose[0])
    assert max(positionen) - min(positionen) < .002
    assert all(0 < p <= 1 for p in positionen)


def test_startverzug_wird_nicht_rueckwirkend_gefahren():
    uhr = Uhr()
    b = SimBackend(jetzt=uhr)
    b.power_on()
    ziel(b, uhr)
    uhr.t = b._ziel_ab
    b.robot_state()
    assert b._pose[0] == 0


def test_odom_geschwindigkeit_ist_weltfest(roboter):
    b, uhr = roboter
    b._pose = (0, 0, math.pi / 2)
    b.send_command(B.synchro_velocity_command(.3, 0, 0), end_time_secs=uhr.t + 1)
    uhr.t += .5
    v = b.robot_state().kinematic_state.velocity_of_body_in_odom.linear
    assert v.x == pytest.approx(0, abs=1e-8)
    assert v.y == pytest.approx(.3, abs=1e-8)


def test_frame_snapshot_zieht_bewegung_vor_folgeziel_nach(roboter):
    b, uhr = roboter
    b.send_command(B.synchro_velocity_command(.3, 0, 0), end_time_secs=uhr.t + 1)
    uhr.t += .5
    ziel(b, uhr)
    assert b._ziel[0] == pytest.approx(1.15, abs=1e-6)


def test_rueckwaertssprung_wird_nicht_doppelt_integriert():
    uhr = Uhr()
    b = SimBackend(jetzt=uhr)
    b.power_on()
    b.send_command(B.synchro_velocity_command(.3, 0, 0), end_time_secs=uhr.t + 10)
    for t in (1, .5, 1, 2):
        uhr.t = 1_000_000 + t
        b.robot_state()
    assert b._pose[0] == pytest.approx(.6, abs=1e-6)


def test_kollision_ist_eine_gesperrte_transaktion(roboter):
    b, uhr = roboter
    eingetreten = threading.Event()
    freigabe = threading.Event()
    fehler = []
    original = b._bewege_gegen_welt

    def pause(von, nach):
        eingetreten.set()
        if not freigabe.wait(5):
            raise TimeoutError('Testfreigabe fehlt')
        return original(von, nach)

    def lesen():
        try:
            b.robot_state()
        except Exception as exc:
            fehler.append(exc)

    b._bewege_gegen_welt = pause
    b.send_command(B.synchro_velocity_command(.3, 0, 0), end_time_secs=uhr.t + 1)
    uhr.t += .1
    thread = threading.Thread(target=lesen)
    thread.start()
    try:
        assert eingetreten.wait(5)
        sperren = [b._sperre]
        if hasattr(b, 'puppe'):
            sperren.append(b.puppe.lock)
        for sperre in sperren:
            erworben = sperre.acquire(blocking=False)
            if erworben:
                sperre.release()
            assert not erworben, 'Zwischenpose darf weder Skript noch Renderer sehen'
    finally:
        freigabe.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert not fehler
    assert b._pose[0] == pytest.approx(.03, abs=1e-6)
