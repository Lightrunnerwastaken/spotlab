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

    def get_config(self):
        """Gesund heisst hier auch: kein zurueckgelassener spotlab-Endpunkt."""
        from bosdyn.api import estop_pb2

        return estop_pb2.EstopConfig(unique_id="c0")

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


# ------------------------------------------------------- Zustandsstrom (Stufe 7)


class _RobotMit:
    def __init__(self, namen):
        self._namen = namen

    def list_services(self):
        return [type("Dienst", (), {"name": n})() for n in self._namen]


def test_zustandsstrom_ist_eine_stufe():
    assert "Zustandsstrom" in STUFEN
    assert STUFEN.index("Zustandsstrom") == STUFEN.index("Zeitsync") + 1


def test_zustandsstrom_vorhanden():
    from spotlab.workshop.doctor import _zustandsstrom

    pruefung = _zustandsstrom(_RobotMit(["robot-state", "robot-state-streaming"]))
    assert pruefung.ok is True
    assert "verfügbar" in pruefung.detail


def test_zustandsstrom_fehlt_ist_kein_fehler():
    """Die Zeile beantwortet eine Frage — ein rotes Kreuz waere eine Falschaussage."""
    from spotlab.workshop.doctor import _zustandsstrom

    pruefung = _zustandsstrom(_RobotMit(["robot-state"]))
    assert pruefung.ok is True
    assert "Lizenz" in pruefung.rat


def test_zustandsstrom_bei_fehlender_liste():
    from spotlab.workshop.doctor import _zustandsstrom

    class Kaputt:
        def list_services(self):
            raise RuntimeError("keine Verbindung")

    pruefung = _zustandsstrom(Kaputt())
    assert pruefung.ok is True
    assert "nicht ermittelbar" in pruefung.detail


# ------------------------------------- zurueckgelassener Endpunkt (A3, S1.13)
#
# EstopGuard.stop() meldet den Endpunkt ab; bleibt er stehen, wertet der Roboter
# ihn beim naechsten Timeout als ausgeloest und der naechste Schueler findet
# einen scheinbar defekten Spot. Abnahmepunkt A3 verlangt genau das zu pruefen --
# bisher fragte doctor nur den aggregierten Systemstatus ab und haette einen
# zurueckgelassenen Endpunkt nie gesehen.

from bosdyn.api import estop_pb2  # noqa: E402


class RobotMitEndpunkten(GesunderRobot):
    def __init__(self, endpunkte=(), frische=None):
        super().__init__()
        self._endpunkte = list(endpunkte)
        self._frische = dict(frische or {})

    def get_config(self):
        cfg = estop_pb2.EstopConfig(unique_id="c0")
        for name in self._endpunkte:
            cfg.endpoints.add().name = name
        return cfg

    def get_status(self):
        status = estop_pb2.EstopSystemStatus(stop_level=estop_pb2.ESTOP_LEVEL_NONE)
        for name in self._endpunkte:
            eintrag = status.endpoints.add()
            eintrag.endpoint.name = name
            seit = self._frische.get(name)
            if seit is not None:
                eintrag.time_since_valid_response.FromNanoseconds(int(seit * 1e9))
        return status


def _stufe(robot, name):
    pruefungen = diagnose(
        _cfg(), robot_bauen=lambda cfg: robot, passwort_lesen=lambda u: "x"
    )
    treffer = [p for p in pruefungen if p.name == name]
    assert treffer, f"Stufe {name!r} fehlt: {[p.name for p in pruefungen]}"
    return treffer[0]


def test_sauber_abgemeldet_ist_gruen():
    pruefung = _stufe(
        RobotMitEndpunkten(endpunkte=("Tablet",), frische={"Tablet": 0.2}),
        "Not-Aus-Endpunkt",
    )
    assert pruefung.ok is True
    assert "kein" in pruefung.detail.lower()


def test_zurueckgelassener_endpunkt_wird_gemeldet():
    """Der Fall nach einem harten Abbruch -- er steht noch da und ist stumm."""
    pruefung = _stufe(
        RobotMitEndpunkten(endpunkte=("Tablet", "spotlab"), frische={"Tablet": 0.2}),
        "Not-Aus-Endpunkt",
    )
    assert pruefung.ok is False
    assert "zurückgeblieben" in pruefung.detail or "zurückgelassen" in pruefung.detail
    # Und der Rat muss beruhigen, statt zu erschrecken: es heilt sich selbst.
    assert "ersetzt" in pruefung.rat


def test_lebender_anderer_lauf_wird_anders_benannt():
    """Kein Defekt, sondern ein belegter Roboter -- die Meldung muss das trennen."""
    pruefung = _stufe(
        RobotMitEndpunkten(
            endpunkte=("Tablet", "spotlab"), frische={"Tablet": 0.2, "spotlab": 0.3}
        ),
        "Not-Aus-Endpunkt",
    )
    assert pruefung.ok is False
    assert "läuft" in pruefung.detail.lower() or "anderer" in pruefung.detail.lower()
    assert "zurückgeblieben" not in pruefung.detail


def test_die_stufe_steht_direkt_hinter_dem_not_aus():
    assert STUFEN.index("Not-Aus-Endpunkt") == STUFEN.index("Not-Aus") + 1
