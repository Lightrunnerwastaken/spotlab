"""Das Sim-Backend antwortet auf walk() wie der echte Spot: gemessen, nicht sofort.

Latenz, Anlauf aus dem Stand, Anfahren und Auslaufen, keine Drehung auf der
Stelle unter der Schwelle (kalibrierung/tempoantwort.py, 60 kommandierte Laeufe).
"""

import math

import pytest
from bosdyn.api import robot_state_pb2
from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, get_a_tform_b
from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.backends.sim import SimBackend
from spotlab.kalibrierung.tempoantwort import lade_modell

M = lade_modell()


class Uhr:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def weiter(self, sekunden):
        self.t += sekunden


@pytest.fixture
def uhr():
    return Uhr()


def _sim(uhr):
    b = SimBackend(jetzt=uhr)
    b.power_on()
    return b


def _senden(backend, uhr, vx=0.0, vy=0.0, wz=0.0, sekunden=1.0, schritt=0.1):
    """Wie fahren.py/folgen.py: alle 0.1 s nachsenden, Gueltigkeit 1 s."""
    ende = uhr.t + sekunden
    while uhr.t < ende - 1e-9:
        backend.send_command(RobotCommandBuilder.synchro_velocity_command(v_x=vx, v_y=vy, v_rot=wz),
                             end_time_secs=uhr.t + 1.0)
        uhr.weiter(schritt)
    return backend.robot_state()


def _lage(backend):
    backend.robot_state()
    p = get_a_tform_b(backend.frame_tree_snapshot(), ODOM_FRAME_NAME, BODY_FRAME_NAME)
    return p.position.x, p.position.y, 2 * math.atan2(p.rotation.z, p.rotation.w)


def _tempo(zustand):
    return zustand.kinematic_state.velocity_of_body_in_odom


def test_aus_dem_stand_bewegt_er_sich_erst_nach_latenz_und_anlauf(uhr):
    b = _sim(uhr)
    b.send_command(RobotCommandBuilder.synchro_velocity_command(v_x=0.4, v_y=0.0, v_rot=0.0),
                   end_time_secs=uhr.t + 1.0)
    uhr.weiter(M.latenz_s + M.anlauf_s - 0.02)
    zustand = b.robot_state()
    assert _lage(b)[0] == pytest.approx(0.0, abs=1e-9)
    assert zustand.behavior_state.state == robot_state_pb2.BehaviorState.STATE_STANDING
    uhr.weiter(0.4)
    assert _lage(b)[0] > 0.01


def test_gemeldet_wird_das_ist_tempo_nicht_das_kommando(uhr):
    b = _sim(uhr)
    zustand = _senden(b, uhr, vx=0.4, sekunden=0.4)
    assert 0.0 < _tempo(zustand).linear.x < 0.4 * 0.7


def test_nach_dem_stopp_laeuft_er_aus_und_steht(uhr):
    b = _sim(uhr)
    _senden(b, uhr, vx=0.4, sekunden=3.0)
    x_stopp = _lage(b)[0]
    b.send_command(RobotCommandBuilder.stop_command())
    uhr.weiter(3.0)
    zustand = b.robot_state()
    nachlauf = _lage(b)[0] - x_stopp
    erwartet = 0.4 * M.ziel(0.4, 0, 0)[0][0] / 0.4 * (M.latenz_s + M.tau["gehen"][1])
    assert nachlauf == pytest.approx(erwartet, rel=0.25)
    assert _tempo(zustand).linear.x == 0.0
    assert zustand.behavior_state.state == robot_state_pb2.BehaviorState.STATE_STANDING


def test_das_tempo_erreicht_den_gemessenen_anteil(uhr):
    b = _sim(uhr)
    zustand = _senden(b, uhr, vx=0.2, sekunden=4.0)
    assert _tempo(zustand).linear.x == pytest.approx(0.2 * M.ziel(0.2, 0, 0)[0][0] / 0.2, rel=0.02)
    assert _tempo(zustand).linear.x < 0.2 * 0.95


def test_reines_drehen_unter_der_schwelle_dreht_nicht(uhr):
    b = _sim(uhr)
    _senden(b, uhr, wz=0.1, sekunden=3.0)
    assert _lage(b)[2] == pytest.approx(0.0, abs=1e-9)
    assert b.bericht()["tempoantwort"]["befehle_unter_drehschwelle"] == 30


def test_ueber_der_schwelle_dreht_er(uhr):
    b = _sim(uhr)
    _senden(b, uhr, wz=0.2, sekunden=3.0)
    assert _lage(b)[2] > 0.4


def test_beim_gehen_dreht_er_auch_langsam(uhr):
    b = _sim(uhr)
    _senden(b, uhr, vx=0.3, wz=0.05, sekunden=3.0)
    assert _lage(b)[2] > 0.1


def test_ohne_nachschub_steht_er_nach_dem_auslaufen(uhr):
    """Ablauf wirkt wie ein Stopp: kurzer Nachlauf, dann steht er -- fuer immer."""
    b = _sim(uhr)
    _senden(b, uhr, vx=0.3, sekunden=2.0)
    uhr.weiter(3.0)
    danach = _lage(b)[0]
    uhr.weiter(10.0)
    assert _lage(b)[0] == pytest.approx(danach, abs=1e-9)


def test_langsamer_als_gemessen_zaehlt_als_ausserhalb(uhr):
    b = _sim(uhr)
    _senden(b, uhr, vx=0.1, sekunden=1.0)
    _senden(b, uhr, vx=0.4, sekunden=1.0)
    assert b.bericht()["tempoantwort"]["befehle_ausserhalb_der_messung"] == 10


def test_sitzen_haelt_sofort_an(uhr):
    b = _sim(uhr)
    _senden(b, uhr, vx=0.4, sekunden=2.0)
    b.send_command(RobotCommandBuilder.synchro_sit_command())
    x = _lage(b)[0]
    uhr.weiter(2.0)
    assert _lage(b)[0] == pytest.approx(x, abs=1e-9)


def test_der_bericht_nennt_die_parameter(uhr):
    b = _sim(uhr)
    t = b.bericht()["tempoantwort"]
    assert t["latenz_s"] == pytest.approx(M.latenz_s, abs=1e-3)
    assert t["drehschwelle_rad_s"] == pytest.approx(M.drehschwelle_rad_s, abs=1e-3)
