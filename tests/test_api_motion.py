import math

import pytest

from spotlab.api.motion import clamp, move, stop, walk
from spotlab.backends.dryrun import DryRunBackend
from spotlab.config import Limits

FIXZEIT = 1_800_000_000.0        # feste Wanduhr fuer die Endzeit-Tests


def _backend(jetzt=None):
    backend = DryRunBackend() if jetzt is None else DryRunBackend(jetzt=jetzt)
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


# ------------------------------------------------- Endzeit: die zwei Uhren
#
# `end_time_secs` ist laut SDK (time_sync.py::robot_timestamp_from_local_secs)
# ein Zeitpunkt in Sekunden seit dem 1.1.1970. Frueher stand hier die nackte
# Konstante 1.0 — jedes Kommando waere am echten Spot als abgelaufen abgewiesen
# worden, der Roboter haette sich nie bewegt.


def test_walk_schickt_einen_zeitpunkt_keine_dauer():
    backend = _backend(jetzt=lambda: FIXZEIT)
    uhr = iter([0.0, 0.0, 2.0])
    walk(
        backend, None, Limits(), vx=0.3, duration=1.0,
        schlaf=lambda _: None, jetzt=lambda: next(uhr), wanduhr=lambda: FIXZEIT,
    )
    assert backend.endzeiten[0] == pytest.approx(FIXZEIT + 1.0)


def test_walk_nimmt_die_wanduhr_nicht_die_monotone_uhr():
    """Die Verwechslung waere derselbe Fehler in neuem Gewand: `time.monotonic`
    zaehlt ab einem beliebigen Bezugspunkt, meist dem Systemstart."""
    backend = _backend(jetzt=lambda: FIXZEIT)
    uhr = iter([0.0, 0.0, 2.0])
    walk(
        backend, None, Limits(), vx=0.3, duration=1.0,
        schlaf=lambda _: None,
        jetzt=lambda: next(uhr),        # monoton, klein
        wanduhr=lambda: FIXZEIT,        # Wanduhr, gross
    )
    assert backend.endzeiten[0] > 1_000_000_000.0


def test_move_setzt_eine_endzeit_gleich_der_geduld():
    """Laeuft `timeout` ab, MUSS das Kommando am Roboter verfallen sein —
    `warte_auf` wirft dann zwar, schickt aber keinen Stopp."""
    backend = _backend(jetzt=lambda: FIXZEIT)
    move(
        backend, None, Limits(), forward=1.0, timeout=12.0,
        schlaf=lambda _: None, wanduhr=lambda: FIXZEIT,
    )
    assert backend.endzeiten[0] == pytest.approx(FIXZEIT + 12.0)


def test_walk_mit_echter_uhr_wird_nicht_abgewiesen():
    """Gegenprobe ohne Attrappe: der Trockenlauf weist abgelaufene Kommandos ab."""
    backend = _backend()
    uhr = iter([0.0, 0.0, 2.0])
    walk(backend, None, Limits(), vx=0.1, duration=1.0,
         schlaf=lambda _: None, jetzt=lambda: next(uhr))
    assert backend.endzeiten[0] > __import__("time").time() - 5


# ------------------------------------------------- Deckel auch bei move()


def _grenze(backend):
    return backend.gesendet[0].synchronized_command.mobility_command.params


def test_move_schickt_den_geschwindigkeitsdeckel_mit():
    """Bei einer Zieltrajektorie waehlt der Roboter sein Tempo selbst —
    Klemmen wie bei walk() liefe ins Leere, es braucht vel_limit."""
    from bosdyn.api.spot import robot_command_pb2 as spot_command_pb2

    backend = _backend()
    move(backend, None, Limits(max_speed=0.25, max_turn_rate=0.4), forward=1.0,
         schlaf=lambda _: None)
    params = spot_command_pb2.MobilityParams()
    _grenze(backend).Unpack(params)
    assert params.vel_limit.max_vel.linear.x == pytest.approx(0.25)
    assert params.vel_limit.max_vel.angular == pytest.approx(0.4)
    # min_vel muss mit: sonst bremst nur die Vorwaertsfahrt.
    assert params.vel_limit.min_vel.linear.x == pytest.approx(-0.25)
    assert params.vel_limit.min_vel.angular == pytest.approx(-0.4)


def test_move_und_autonome_fahrt_teilen_denselben_deckel():
    """Zwei Formulierungen desselben Grenzwerts waeren zwei Gelegenheiten,
    ihn unterschiedlich falsch zu schreiben."""
    from spotlab.backends.mobility import se2_grenze

    grenzen = Limits(max_speed=0.33, max_turn_rate=0.55)
    aus_graphnav = pytest.importorskip(
        "spotlab.backends.real.graphnav"
    ).travel_params(grenzen).velocity_limit
    assert aus_graphnav == se2_grenze(grenzen)


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


def test_walk_ohne_stopp_sendet_einmal_und_kehrt_sofort_zurueck():
    """Fuer Regelschleifen: kein Nachsenden, kein Schlafen, kein Stopp -- das
    Kommando bleibt KOMMANDO_GUELTIGKEIT_S gueltig, dann steht Spot."""
    from spotlab.api import motion
    from spotlab.backends.dryrun import DryRunBackend
    from spotlab.config import Limits

    backend = DryRunBackend()
    backend.power_on()
    geschlafen = []
    motion.walk(backend, None, Limits(), vx=0.3, wz=0.1, stop=False,
                schlaf=lambda s: geschlafen.append(s))
    assert geschlafen == []
    assert len(backend.gesendet) == 1, "genau ein Kommando, kein Stopp"
    kommando = backend.gesendet[-1]
    assert kommando.synchronized_command.mobility_command.HasField("se2_velocity_request")
