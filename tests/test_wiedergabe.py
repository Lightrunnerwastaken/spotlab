"""Gate G11: die Wiedergabe gegen die Aufzeichnung, aus der sie stammt.

Die Puppe faehrt eine gemessene Stuetzstelle fuenf Zyklen lang. Wenn sie die
Messung wiedergibt, muss der zurueckgelegte Weg tempo * t sein, der
Bodenkontakt je Bein der gemessenen Duty entsprechen, und kein Standfuss darf
im Boden versinken. Die Standhoehe aus der Kinematik wird gegen die gemessene
BERICHTET -- ihre Differenz sagt, wie gut das Menagerie-Modell zum Schul-Spot
passt (06.09.2026: 2-8 mm).

Uebersprungen ohne spotsim oder Asset, wie test_backend_mujoco.py.
"""

import math

import pytest

spotsim = pytest.importorskip("spotsim")

from spotlab.kalibrierung.modell import lade_modell  # noqa: E402

pytestmark = pytest.mark.skipif(
    not spotsim.spot_asset_available(),
    reason="Menagerie-Asset fehlt -- python scripts/fetch_menagerie.py in matura-spot",
)

ZYKLEN = 5
TAKT_S = 0.02
WEG_TOLERANZ = 0.02          # 2 % von tempo * t
DUTY_TOLERANZ = 0.10
EINDRINGEN_M = 0.01


class Uhr:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def weiter(self, sekunden):
        self.t += sekunden


def _stuetzstellen():
    modell = lade_modell()
    fahren = modell.fahren
    return [fahren[0], fahren[len(fahren) // 2], fahren[-1]]


@pytest.mark.parametrize("stelle", _stuetzstellen(), ids=lambda s: f"{s['tempo_m_s']:.2f}m_s")
def test_die_wiedergabe_trifft_die_messung(stelle):
    from bosdyn.client.robot_command import RobotCommandBuilder

    from spotlab.backends.mujoco import MujocoBackend

    tempo = stelle["tempo_m_s"]
    dauer = ZYKLEN * stelle["zyklusdauer_s"]
    uhr = Uhr()
    backend = MujocoBackend(jetzt=uhr, start=(0.0, 0.0, 0.0))
    backend.power_on()

    kontakte = {bein: 0 for bein in ("fl", "fr", "hl", "hr")}
    versunken = 0.0
    proben = 0
    ende = uhr.t + dauer
    while uhr.t < ende:
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(v_x=tempo, v_y=0.0, v_rot=0.0),
            end_time_secs=uhr.t + 1.0,
        )
        zustand = backend.robot_state()
        fuesse = zustand.foot_state
        for bein, fuss in zip(("fl", "fr", "hl", "hr"), fuesse):
            steht = fuss.contact == fuss.CONTACT_MADE
            kontakte[bein] += steht
            if steht:
                # Fuss in Weltkoordinaten: Koerperhoehe + Fuss im Koerperframe.
                z_welt = backend.puppe.pose()[3] + fuss.foot_position_rt_body.z
                versunken = max(versunken, backend.puppe.legs.foot_radius - z_welt)
        proben += 1
        uhr.weiter(TAKT_S)

    x, _y, _yaw, hoehe = backend.puppe.pose()
    assert x == pytest.approx(tempo * dauer, rel=WEG_TOLERANZ), "Weg != tempo * t"
    for i, bein in enumerate(("fl", "fr", "hl", "hr")):
        duty = kontakte[bein] / proben
        assert abs(duty - stelle["duty"][i]) <= DUTY_TOLERANZ, (
            f"{bein}: Bodenkontakt {duty:.2f} statt gemessen {stelle['duty'][i]:.2f}"
        )
    assert versunken <= EINDRINGEN_M, f"ein Standfuss versinkt {versunken * 100:.1f} cm"

    bericht = backend.bericht()["puppe"]
    abweichung = abs(bericht["standhoehe_kinematik_m"] - bericht["standhoehe_gemessen_m"])
    assert abweichung < 0.02, f"Standhoehe Kinematik vs Messung: {abweichung * 1000:.0f} mm"
    assert 0.40 < hoehe < 0.60


def test_die_zyklusdauer_wird_eingehalten():
    """Fuenf Zyklen lang fahren -> die Gangphase hat fuenfmal umgeschlagen."""
    from bosdyn.client.robot_command import RobotCommandBuilder

    from spotlab.backends.mujoco import MujocoBackend

    stelle = _stuetzstellen()[1]
    uhr = Uhr()
    backend = MujocoBackend(jetzt=uhr, start=(0.0, 0.0, 0.0))
    backend.power_on()
    umschlaege, letzte = 0, 0.0
    ende = uhr.t + ZYKLEN * stelle["zyklusdauer_s"] + 1e-6
    while uhr.t < ende:
        backend.send_command(
            RobotCommandBuilder.synchro_velocity_command(
                v_x=stelle["tempo_m_s"], v_y=0.0, v_rot=0.0),
            end_time_secs=uhr.t + 1.0,
        )
        backend.robot_state()
        if backend._phase < letzte:
            umschlaege += 1
        letzte = backend._phase
        uhr.weiter(TAKT_S)
    assert umschlaege in (ZYKLEN - 1, ZYKLEN), umschlaege
    assert math.isfinite(letzte)
