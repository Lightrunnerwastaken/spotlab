import pytest

from spotlab.backends.base import Capability, Feedback, SafetyStatus, require
from spotlab.errors import UnsupportedCapability


class Attrappe:
    def __init__(self, koennen):
        self._koennen = koennen

    def capabilities(self):
        return self._koennen


def test_kameras_alias_deckt_alle_drei_arten():
    assert Capability.DEPTH_CAMERAS in Capability.CAMERAS
    assert Capability.GRAY_CAMERAS in Capability.CAMERAS
    assert Capability.COLOR_CAMERAS in Capability.CAMERAS
    assert Capability.LOCOMOTION not in Capability.CAMERAS


def test_require_laesst_vorhandene_faehigkeit_durch():
    require(Attrappe(Capability.LOCOMOTION | Capability.POWER), Capability.LOCOMOTION, "gehen")


def test_require_meldet_fehlende_faehigkeit_auf_deutsch():
    with pytest.raises(UnsupportedCapability) as info:
        require(Attrappe(Capability.LOCOMOTION), Capability.CAMERAS, "Kamerabilder")
    text = str(info.value)
    assert "Kamerabilder" in text
    assert "Backend" in text


def test_require_akzeptiert_teilmenge_bei_alias():
    """Ein Backend mit nur Tiefenkameras erfüllt die Anforderung CAMERAS."""
    require(Attrappe(Capability.DEPTH_CAMERAS), Capability.CAMERAS, "Kamerabilder")


def test_feedback_ist_unveraenderlich():
    rueck = Feedback(done=True, status="steht")
    with pytest.raises(AttributeError):
        rueck.done = False


def test_safety_status_darf_leer_sein():
    zustand = SafetyStatus(lease_holder=None, estop_level=None)
    assert zustand.lease_holder is None
