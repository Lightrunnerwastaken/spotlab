from spotlab.config import Config, Limits
from spotlab.workshop.doctor import STUFEN, diagnose


class GesunderRobot:
    def __init__(self):
        self.time_sync = self

    def authenticate(self, user, pw):
        pass

    def wait_for_sync(self):
        pass

    def ensure_client(self, name):
        return self

    def get_status(self):
        from bosdyn.api import estop_pb2

        return estop_pb2.EstopSystemStatus(stop_level=estop_pb2.ESTOP_LEVEL_NONE)

    def list_leases(self):
        return []

    def get_robot_state(self):
        from spotlab.backends.dryrun import DryRunBackend

        return DryRunBackend().robot_state()


def _cfg():
    return Config(ip="1.2.3.4", username="u", nickname="Spot", limits=Limits())


def test_gesunder_spot_besteht_alle_stufen():
    pruefungen = diagnose(
        _cfg(), robot_bauen=lambda cfg: GesunderRobot(), passwort_lesen=lambda u: "x"
    )
    assert [p.name for p in pruefungen] == list(STUFEN)
    assert all(p.ok for p in pruefungen)


def test_ohne_konfiguration_bricht_es_sofort_ab(tmp_path, monkeypatch):
    """Muss auch dann gelten, wenn auf diesem Rechner eine echte Konfiguration liegt."""
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "gibtsnicht.toml")
    pruefungen = diagnose(None)
    assert len(pruefungen) == 1
    assert pruefungen[0].ok is False
    assert "spotlab login" in pruefungen[0].rat


def test_netzfehler_stoppt_die_kette():
    from bosdyn.client.exceptions import UnableToConnectToRobotError

    def kaputt(cfg):
        raise UnableToConnectToRobotError("weg")

    pruefungen = diagnose(_cfg(), robot_bauen=kaputt, passwort_lesen=lambda u: "x")
    assert [p.name for p in pruefungen] == ["Konfiguration", "Netz"]
    assert pruefungen[-1].ok is False
    assert "WLAN" in pruefungen[-1].rat


def test_falsches_passwort_wird_benannt():
    from bosdyn.client.auth import InvalidLoginError

    class SchlechterLogin(GesunderRobot):
        def authenticate(self, user, pw):
            raise InvalidLoginError(response=None)

    pruefungen = diagnose(
        _cfg(), robot_bauen=lambda cfg: SchlechterLogin(), passwort_lesen=lambda u: "x"
    )
    assert pruefungen[-1].name == "Anmeldung" and not pruefungen[-1].ok


def test_belegtes_lease_ist_kein_fehler_sondern_ein_hinweis():
    from bosdyn.api import lease_pb2

    class Belegt(GesunderRobot):
        def list_leases(self):
            r = lease_pb2.LeaseResource(resource="body")
            r.lease_owner.client_name = "spotlab/anna@laptop7"
            return [r]

    pruefungen = diagnose(
        _cfg(), robot_bauen=lambda cfg: Belegt(), passwort_lesen=lambda u: "x"
    )
    lease = [p for p in pruefungen if p.name == "Lease"][0]
    assert lease.ok is False
    assert "anna" in lease.detail
