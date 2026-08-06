import math

import pytest

from spotlab.api.motion import clamp, move, stop, walk
from spotlab.backends.dryrun import DryRunBackend
from spotlab.config import Limits


def _backend():
    backend = DryRunBackend()
    backend.power_on()
    return backend


def test_geschwindigkeit_wird_geklemmt_nicht_abgewiesen():
    vx, vy, wz = clamp(5.0, 0.0, 9.0, Limits(max_speed=0.6, max_turn_rate=0.8))
    assert vx == 0.6 and wz == 0.8


def test_klemmen_erhaelt_die_richtung():
    vx, vy, _ = clamp(3.0, 4.0, 0.0, Limits(max_speed=0.5, max_turn_rate=0.8))
    assert math.isclose(math.hypot(vx, vy), 0.5, rel_tol=1e-9)
    assert math.isclose(vx / vy, 3 / 4, rel_tol=1e-9)


def test_negative_werte_werden_symmetrisch_geklemmt():
    vx, _, wz = clamp(-5.0, 0.0, -9.0, Limits(max_speed=0.6, max_turn_rate=0.8))
    assert vx == -0.6 and wz == -0.8


def test_walk_baut_geschwindigkeitskommandos_und_sendet_nach():
    backend = _backend()
    uhr = iter([0.0, 0.0, 0.5, 1.0, 1.5])
    walk(
        backend, None, Limits(), vx=0.3, duration=1.2,
        schlaf=lambda _: None, jetzt=lambda: next(uhr),
    )
    assert len(backend.gesendet) >= 2  # nachgesendet, nicht einmalig
    mobility = backend.gesendet[0].synchronized_command.mobility_command
    assert mobility.HasField("se2_velocity_request")
    assert math.isclose(mobility.se2_velocity_request.velocity.linear.x, 0.3, rel_tol=1e-6)


def test_walk_beendet_mit_stopp():
    backend = _backend()
    uhr = iter([0.0, 0.0, 2.0])
    walk(
        backend, None, Limits(), vx=0.3, duration=1.0,
        schlaf=lambda _: None, jetzt=lambda: next(uhr),
    )
    # stop_command() ist ein FULL-BODY-Stopp, kein synchronized_command
    letztes = backend.gesendet[-1].full_body_command
    assert letztes.HasField("stop_request")


def test_move_baut_eine_trajektorie():
    backend = _backend()
    move(backend, None, Limits(), forward=1.0, schlaf=lambda _: None)
    mobility = backend.gesendet[0].synchronized_command.mobility_command
    assert mobility.HasField("se2_trajectory_request")


def test_move_rechnet_grad_in_bogenmass():
    backend = _backend()
    move(backend, None, Limits(), turn=90.0, schlaf=lambda _: None)
    ziel = backend.gesendet[0].synchronized_command.mobility_command.se2_trajectory_request
    punkt = ziel.trajectory.points[0].pose
    assert math.isclose(punkt.angle, math.pi / 2, rel_tol=1e-6)


def test_move_ohne_ziel_macht_nichts():
    backend = _backend()
    move(backend, None, Limits(), schlaf=lambda _: None)
    assert backend.gesendet == []


def test_stop_baut_ein_stopp_kommando():
    """stop_command() des SDK ist ein Full-Body-Stopp — das ist der echte Anhalte-Befehl."""
    backend = _backend()
    stop(backend, None)
    assert backend.gesendet[0].full_body_command.HasField("stop_request")


def test_bewegung_ohne_faehigkeit_wird_verweigert():
    from spotlab.backends.base import Capability
    from spotlab.errors import UnsupportedCapability

    class OhneBeine(DryRunBackend):
        def capabilities(self):
            return Capability.POWER

    backend = OhneBeine()
    backend.power_on()
    with pytest.raises(UnsupportedCapability):
        walk(
            backend, None, Limits(), vx=0.1, duration=0.1,
            schlaf=lambda _: None, jetzt=lambda: 0.0,
        )
