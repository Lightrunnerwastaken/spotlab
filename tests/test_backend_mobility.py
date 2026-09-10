"""Der Nickwinkel beim Gehen -- und sein Vorzeichen.

Die Konvention gilt im ganzen Projekt: Drehung um y nach der Rechte-Hand-Regel,
NASE HOCH IST NEGATIV. So liest `api/state.py::rpy_aus` den echten Spot, so
rechnet MuJoCo. Ein Vorzeichenfehler hier waere besonders teuer: der
Gesichts-Finder rechnet mit dem GEMESSENEN Nick, also muessen Befehl und
Rueckmessung dieselbe Sprache sprechen.
"""

import math

import pytest
from bosdyn.client.math_helpers import Quat

from spotlab.api.state import rpy_aus
from spotlab.backends.mobility import koerperneigung, mit_grenze, se2_grenze
from spotlab.config import Limits


def _nase_zeigt_auf(nick_grad):
    """z-Komponente der Blickrichtung nach dieser Drehung. Positiv = hoch."""
    q = koerperneigung(nick_grad).base_offset_rt_footprint.points[0].pose.rotation
    return Quat(q.w, q.x, q.y, q.z).transform_point(1.0, 0.0, 0.0)[2]


@pytest.mark.parametrize("nick_grad, hoch", [(-15.0, True), (-5.0, True), (15.0, False)])
def test_negativer_nick_hebt_die_nase(nick_grad, hoch):
    z = _nase_zeigt_auf(nick_grad)
    assert (z > 0.01) is hoch, f"nick_grad {nick_grad} zeigt auf z={z:+.3f}"


def test_ohne_nick_schaut_er_geradeaus():
    assert _nase_zeigt_auf(0.0) == pytest.approx(0.0, abs=1e-9)


def test_der_befohlene_nick_kommt_so_zurueck_wie_state_ihn_liest():
    """Die Naht, an der der Gesichts-Finder haengt: Befehl und Rueckmessung
    muessen dasselbe Vorzeichen tragen."""
    q = koerperneigung(-15.0).base_offset_rt_footprint.points[0].pose.rotation
    _, pitch, _ = rpy_aus(q)
    assert math.degrees(pitch) == pytest.approx(-15.0, abs=0.01)


def test_die_neigung_steht_im_richtigen_feld():
    """`body_pose` waere falsch -- das wirkt laut Protokoll NUR mit einem
    Stehkommando. `base_offset_rt_footprint` wirkt beim Gehen."""
    steuerung = koerperneigung(-10.0)
    assert steuerung.HasField("base_offset_rt_footprint")
    assert not steuerung.HasField("body_pose")
    assert len(steuerung.base_offset_rt_footprint.points) == 1


def test_ohne_nick_bleiben_die_parameter_wie_bisher():
    params = mit_grenze(Limits())
    assert not params.HasField("body_control")
    assert params.vel_limit == se2_grenze(Limits())


def test_mit_nick_kommt_die_koerperlage_dazu_ohne_den_deckel_zu_verlieren():
    params = mit_grenze(Limits(max_speed=0.7), nick_grad=-10.0)
    assert params.HasField("body_control")
    assert params.vel_limit.max_vel.linear.x == pytest.approx(0.7)
    assert params.stairs_mode == mit_grenze(Limits(max_speed=0.7)).stairs_mode
