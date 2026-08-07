import pytest

from spotlab.backends.real.verbindung import verbinde
from spotlab.config import Config, Limits
from spotlab.errors import BadCredentials, TimeSyncFailed


class FakeRobot:
    def __init__(self, protokoll, auth_fehler=None, sync_fehler=None):
        self.protokoll = protokoll
        self.time_sync = self
        self._auth_fehler = auth_fehler
        self._sync_fehler = sync_fehler

    def authenticate(self, user, password):
        if self._auth_fehler:
            raise self._auth_fehler
        self.protokoll.append("auth")

    def wait_for_sync(self):
        if self._sync_fehler:
            raise self._sync_fehler
        self.protokoll.append("time_sync")


def _cfg():
    return Config(ip="1.2.3.4", username="u", nickname="Spot", limits=Limits())


def test_reihenfolge_auth_dann_zeitsync():
    protokoll = []
    verbinde(_cfg(), robot_bauen=lambda c: FakeRobot(protokoll), passwort_lesen=lambda u: "x")
    assert protokoll == ["auth", "time_sync"]


def test_kein_lease_und_kein_estop():
    """verbinde() macht NUR Auth und Zeitsync — sonst wäre es nicht leaselos."""
    protokoll = []
    verbinde(_cfg(), robot_bauen=lambda c: FakeRobot(protokoll), passwort_lesen=lambda u: "x")
    assert "estop" not in protokoll and "lease" not in protokoll


def test_falsches_passwort_wird_uebersetzt():
    from bosdyn.client.auth import InvalidLoginError

    with pytest.raises(BadCredentials):
        verbinde(
            _cfg(),
            robot_bauen=lambda c: FakeRobot([], auth_fehler=InvalidLoginError(response=None)),
            passwort_lesen=lambda u: "x",
        )


def test_zeitsync_fehler_wird_uebersetzt():
    with pytest.raises(TimeSyncFailed) as info:
        verbinde(
            _cfg(),
            robot_bauen=lambda c: FakeRobot([], sync_fehler=RuntimeError("weg")),
            passwort_lesen=lambda u: "x",
        )
    assert "Uhr" in str(info.value)
