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


def test_verhaltensfehler_sagt_was_zu_tun_ist():
    """Lauf 20260911T162238Z: `stand()` scheiterte, spotlab meldete 'vom naechsten
    Kommando ueberschrieben' -- die wahre Ursache stand nur in diagnose.log:
    `BehaviorFaultError`. Ein Verhaltensfehler loescht sich nicht von selbst, und
    der Roboter nimmt bis dahin KEIN Kommando an. Das muss die Meldung sagen."""
    from bosdyn.client.robot_command import BehaviorFaultError

    from spotlab.errors import CommandRejected

    fehler = translate(BehaviorFaultError(response=None))
    assert isinstance(fehler, CommandRejected)
    assert "Verhaltensfehler" in str(fehler)
    assert "Tablet" in str(fehler)


# ---------------------------------------- power_on und die Motorfreigabe
#
# Beta-Prüfung 23.09.2026 (p20, p20b): der häufigste Fehler am Gerät --
# power_on() bei gedrücktem Not-Aus am Tablet -- kam roh und englisch durch
# („EstoppedError: Cannot power on while estopped“). `EstopEngaged` und
# `BatteryEmpty` gab es, benutzt hat sie niemand.


def _power(name):
    from bosdyn.client import power

    return getattr(power, name)(response=None, error_message="roh")


def _fall(klasse, ziel, *woerter):
    return pytest.param(klasse, ziel, woerter, id=klasse)


@pytest.mark.parametrize("klasse, ziel, woerter", [
    _fall("EstoppedError", "EstopEngaged", "Not-Aus", "freigeben", "spotlab doctor"),
    _fall("FaultedError", "NotPowered", "Tablet", "quittieren"),
    _fall("BatteryMissingError", "BatteryEmpty", "Akku", "einsetzen"),
    _fall("ShorePowerConnectedError", "NotPowered", "Ladekabel", "abziehen"),
    _fall("KeepaliveMotorsOffError", "NotPowered", "Keepalive", "Tablet"),
])
def test_power_fehler_sagen_was_zu_tun_ist(klasse, ziel, woerter):
    import spotlab.errors as E

    ursprung = _power(klasse)
    fehler = translate(ursprung)
    assert type(fehler).__name__ == ziel
    assert isinstance(fehler, SpotlabError)
    assert fehler.__cause__ is ursprung
    for wort in woerter:
        assert wort in str(fehler), (wort, str(fehler))
    assert "Cannot" not in str(fehler)                          # deutsch, nicht roh
    assert isinstance(fehler, getattr(E, ziel))


def test_kommando_ohne_motoren_nennt_power_on():
    from bosdyn.client.robot_command import NotPoweredOnError

    from spotlab.errors import NotPowered

    fehler = translate(NotPoweredOnError(response=None, error_message="roh"))
    assert isinstance(fehler, NotPowered)
    assert "spot.power_on()" in str(fehler)


def test_eine_ungueltige_anfrage_nennt_den_grund_und_behauptet_keinen_roboterfehler():
    """`InvalidRequestError` heisst laut SDK: die Argumente sind falsch, unabhängig
    vom Zustand des Roboters. Neustarten hilft also nicht -- das muss die Meldung sagen."""
    from bosdyn.client.exceptions import InvalidRequestError

    from spotlab.errors import CommandRejected

    fehler = translate(InvalidRequestError(response=None, error_message="body_height out of range"))
    assert isinstance(fehler, CommandRejected)
    assert "body_height out of range" in str(fehler)
    assert "spot.send()" in str(fehler)
