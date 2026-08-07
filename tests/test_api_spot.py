import pytest

from spotlab.api.spot import Spot
from spotlab.backends.dryrun import DryRunBackend
from spotlab.config import Limits
from spotlab.errors import NotPowered


def _spot(**kw):
    return Spot(DryRunBackend(), recorder=None, limits=Limits(), **kw)


def test_verben_sind_verkettbar():
    spot = _spot()
    spot.power_on()
    spot.stand(schlaf=lambda _: None)
    spot.stop()
    assert spot.is_powered is True


def test_stand_ohne_strom_sagt_was_zu_tun_ist():
    spot = _spot()
    with pytest.raises(NotPowered) as info:
        spot.stand(schlaf=lambda _: None)
    assert "power_on" in str(info.value)


def test_battery_kommt_aus_dem_zustand():
    assert _spot().battery == 87.0


def test_state_liefert_datenklasse():
    zustand = _spot().state
    assert zustand.battery == 87.0
    assert len(zustand.joints) == 12


def test_send_reicht_rohes_protobuf_durch():
    from bosdyn.client.robot_command import RobotCommandBuilder

    spot = _spot()
    spot.power_on()
    spot.send(RobotCommandBuilder.synchro_stand_command())
    assert len(spot.backend.gesendet) == 1


def test_close_schaltet_ab():
    spot = _spot()
    spot.power_on()
    spot.close()
    assert spot.is_powered is False


def test_navigate_ohne_karte_sagt_was_zu_tun_ist():
    from spotlab.errors import SpotlabError

    spot = _spot()
    with pytest.raises(SpotlabError) as info:
        spot.navigate_to("kueche")
    assert "load_map" in str(info.value)


def test_waypoints_ohne_karte_ist_leer():
    assert _spot().waypoints() == []
