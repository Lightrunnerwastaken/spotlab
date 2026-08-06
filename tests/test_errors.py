import pytest
from bosdyn.client.auth import InvalidLoginError
from bosdyn.client.exceptions import UnableToConnectToRobotError
from bosdyn.client.lease import ResourceAlreadyClaimedError

from spotlab.errors import BadCredentials, LeaseBusy, NotReachable, SpotlabError, translate


def test_netzfehler_nennt_die_ip():
    fehler = translate(UnableToConnectToRobotError("weg"), ip="192.168.80.3")
    assert isinstance(fehler, NotReachable)
    assert "192.168.80.3" in str(fehler)
    assert "WLAN" in str(fehler)


def test_login_fehler_verweist_auf_login_kommando():
    fehler = translate(InvalidLoginError(response=None))
    assert isinstance(fehler, BadCredentials)
    assert "spotlab login" in str(fehler)


def test_lease_belegt_nennt_die_uebernahme():
    fehler = translate(ResourceAlreadyClaimedError(response=None), ip=None)
    assert isinstance(fehler, LeaseBusy)
    assert "spotlab lease --take" in str(fehler)


def test_originalausnahme_bleibt_als_cause():
    ursprung = UnableToConnectToRobotError("weg")
    fehler = translate(ursprung, ip="1.2.3.4")
    assert fehler.__cause__ is ursprung


def test_unbekannte_ausnahme_wird_nicht_uebersetzt():
    assert translate(ValueError("irgendwas")) is None


def test_alle_spotlab_fehler_haben_deutschen_text():
    assert issubclass(BadCredentials, SpotlabError)
    with pytest.raises(SpotlabError):
        raise BadCredentials("Benutzername oder Passwort stimmt nicht.")
