import pytest

from spotlab.backends.real.session import ABBAU_SCHRITTE, AUFBAU_SCHRITTE, RealSpot
from spotlab.config import Config, Limits


class FakeRobot:
    def __init__(self, protokoll):
        self.protokoll = protokoll
        self.time_sync = self
        self._powered = False

    def authenticate(self, user, password):
        self.protokoll.append("auth")

    def wait_for_sync(self):
        self.protokoll.append("time_sync")

    def ensure_client(self, name):
        return FakeService(self.protokoll)

    def power_on(self, timeout_sec=20):
        self._powered = True
        self.protokoll.append("power_on")

    def power_off(self, cut_immediately=False, timeout_sec=20):
        self._powered = False
        self.protokoll.append(f"power_off(cut={cut_immediately})")

    def is_powered_on(self):
        return self._powered

    def get_frame_tree_snapshot(self):
        return None

    def get_id(self):
        release = type("R", (), {"version": "4.0"})()
        return type(
            "Id", (), {"serial_number": "SN-1", "nickname": "Spot", "software_release": release}
        )()


class FakeService:
    def __init__(self, protokoll):
        self.protokoll = protokoll
        self.lease_wallet = self

    def get_lease(self, *a):
        return None

    def list_leases(self):
        return []

    def acquire(self, **kw):
        self.protokoll.append("lease_acquire")

    def take(self, **kw):
        self.protokoll.append("lease_take")

    def return_lease(self, *a, **kw):
        self.protokoll.append("lease_return")

    def robot_command(self, command, end_time_secs=None, **kw):
        self.protokoll.append("kommando")
        return "cmd-1"

    def get_robot_state(self):
        from spotlab.backends.dryrun import DryRunBackend

        return DryRunBackend().robot_state()


class FakeEstopGuard:
    def __init__(self, protokoll):
        self.protokoll = protokoll

    def start(self):
        self.protokoll.append("estop")

    def stop(self):
        self.protokoll.append("estop_abmelden")

    def level(self):
        return "frei"


def _cfg():
    return Config(ip="1.2.3.4", username="u", nickname="Spot", limits=Limits())


def _connect(protokoll, take=False):
    return RealSpot.connect(
        _cfg(),
        recorder=None,
        take=take,
        robot_bauen=lambda cfg: FakeRobot(protokoll),
        estop_bauen=lambda client: FakeEstopGuard(protokoll),
        passwort_lesen=lambda user: "geheim",
    )


def test_aufbau_haelt_die_reihenfolge_ein():
    protokoll = []
    _connect(protokoll)
    reihenfolge = [
        s for s in protokoll if s in ("auth", "time_sync", "estop", "lease_acquire")
    ]
    assert reihenfolge == ["auth", "time_sync", "estop", "lease_acquire"]


def test_motoren_bleiben_beim_verbinden_aus():
    protokoll = []
    backend = _connect(protokoll)
    assert "power_on" not in protokoll
    assert backend.is_powered is False


def test_take_wird_durchgereicht():
    protokoll = []
    _connect(protokoll, take=True)
    assert "lease_take" in protokoll and "lease_acquire" not in protokoll


def test_abbau_haelt_die_umgekehrte_reihenfolge_ein():
    protokoll = []
    backend = _connect(protokoll)
    protokoll.clear()
    backend.close()
    assert protokoll == ["kommando", "power_off(cut=False)", "lease_return", "estop_abmelden"]


def test_abbau_laeuft_auch_wenn_ein_schritt_wirft():
    protokoll = []
    backend = _connect(protokoll)

    def kaputt(*a, **kw):
        raise RuntimeError("Verbindung weg")

    backend._robot.power_off = kaputt
    protokoll.clear()
    backend.close()  # darf nicht werfen
    assert "lease_return" in protokoll and "estop_abmelden" in protokoll


def test_abbau_ist_idempotent():
    backend = _connect([])
    backend.close()
    backend.close()


def test_schrittlisten_sind_dokumentiert():
    assert AUFBAU_SCHRITTE[0] == "auth"
    assert ABBAU_SCHRITTE[-1] == "verbindung_schliessen"


# ------------------------------------------------- Rollback beim Aufbau (S1.5)


class _LeaseVerweigert(FakeService):
    def acquire(self, **kw):
        self.protokoll.append("lease_versuch")
        raise RuntimeError("Lease ist belegt")


class _RobotMitLeaseFehler(FakeRobot):
    def ensure_client(self, name):
        if "lease" in name.lower():
            return _LeaseVerweigert(self.protokoll)
        return FakeService(self.protokoll)


def test_gescheiterter_aufbau_meldet_den_estop_wieder_ab():
    """Scheitert ein spaeterer Aufbauschritt, darf kein registrierter Endpunkt
    und kein Keepalive-Thread zurueckbleiben.

    Sonst haelt ein Prozess, der gar keine Sitzung hat, den Not-Aus des
    Roboters -- und der naechste Schueler findet einen scheinbar defekten Spot,
    oder schlimmer: einen, dessen Not-Aus an einem toten Thread haengt.
    """
    protokoll = []
    with pytest.raises(RuntimeError):
        RealSpot.connect(
            _cfg(),
            robot_bauen=lambda cfg: _RobotMitLeaseFehler(protokoll),
            estop_bauen=lambda client: FakeEstopGuard(protokoll),
            passwort_lesen=lambda user: "geheim",
        )
    assert "estop" in protokoll, "Vorbedingung: der E-Stop war registriert"
    assert "estop_abmelden" in protokoll, (
        "Der E-Stop-Endpunkt blieb nach dem gescheiterten Aufbau registriert: "
        + str(protokoll)
    )


def test_rollback_verschluckt_den_urspruenglichen_fehler_nicht():
    """Der Schueler muss erfahren, WORAN es lag -- nicht an einem Folgefehler."""
    protokoll = []
    with pytest.raises(RuntimeError, match="Lease ist belegt"):
        RealSpot.connect(
            _cfg(),
            robot_bauen=lambda cfg: _RobotMitLeaseFehler(protokoll),
            estop_bauen=lambda client: FakeEstopGuard(protokoll),
            passwort_lesen=lambda user: "geheim",
        )


def test_scheitert_der_rollback_bleibt_der_erste_fehler_stehen():
    """Ein kaputtes stop() darf die eigentliche Ursache nicht ueberschreiben."""

    class KaputteWache(FakeEstopGuard):
        def stop(self):
            self.protokoll.append("estop_abmelden_gescheitert")
            raise RuntimeError("Abmelden ging auch schief")

    protokoll = []
    with pytest.raises(RuntimeError, match="Lease ist belegt"):
        RealSpot.connect(
            _cfg(),
            robot_bauen=lambda cfg: _RobotMitLeaseFehler(protokoll),
            estop_bauen=lambda client: KaputteWache(protokoll),
            passwort_lesen=lambda user: "geheim",
        )
    assert "estop_abmelden_gescheitert" in protokoll


def test_ctrl_c_waehrend_des_aufbaus_meldet_den_estop_ab():
    """Der haeufigste Abbruch ueberhaupt -- und er ist KEINE Exception.

    Faengt der Rollback nur `Exception`, bleibt bei Strg-C der Endpunkt samt
    Keepalive-Thread registriert, waehrend der Prozess stirbt.
    """

    class LeaseAbgebrochen(FakeService):
        def acquire(self, **kw):
            raise KeyboardInterrupt()

    class RobotMitAbbruch(FakeRobot):
        def ensure_client(self, name):
            if "lease" in name.lower():
                return LeaseAbgebrochen(self.protokoll)
            return FakeService(self.protokoll)

    protokoll = []
    with pytest.raises(KeyboardInterrupt):
        RealSpot.connect(
            _cfg(),
            robot_bauen=lambda cfg: RobotMitAbbruch(protokoll),
            estop_bauen=lambda client: FakeEstopGuard(protokoll),
            passwort_lesen=lambda user: "geheim",
        )
    assert "estop_abmelden" in protokoll, str(protokoll)


def test_gescheiterter_aufbau_gibt_auch_das_lease_zurueck():
    """Lease erfolgreich, spaeterer Schritt kaputt: beides muss zurueck."""

    class RobotOhneKennung(FakeRobot):
        def get_id(self):
            raise RuntimeError("get_id kaputt")

    class Aufzeichnung:
        def __init__(self):
            self.ereignisse = []

        def event(self, art, **daten):
            self.ereignisse.append(art)

        def set_robot_info(self, **kw):
            raise AssertionError("wird nie erreicht")

    protokoll = []
    with pytest.raises(RuntimeError, match="get_id kaputt"):
        RealSpot.connect(
            _cfg(),
            recorder=Aufzeichnung(),
            robot_bauen=lambda cfg: RobotOhneKennung(protokoll),
            estop_bauen=lambda client: FakeEstopGuard(protokoll),
            passwort_lesen=lambda user: "geheim",
        )
    assert "lease_acquire" in protokoll, "Vorbedingung: das Lease war geholt"
    assert "lease_return" in protokoll, str(protokoll)
    assert "estop_abmelden" in protokoll, str(protokoll)


# --------------------------------------------- Abbau gegen Strg-C (S1.6)
#
# `_versuche` fing nur `Exception`. Ein KeyboardInterrupt im ERSTEN Abbauschritt
# (Bewegung stoppen) sprang damit aus close() heraus: power_off, Lease-Rueckgabe
# und E-Stop-Abmeldung liefen nie. Der Prozess starb, die Keepalives starben,
# der Roboter schnitt die Motorleistung ab -- und ein stehender Spot faellt dabei
# um, statt sich hinzusetzen.


class _AbbruchBeimStoppen(FakeService):
    def robot_command(self, command, end_time_secs=None, **kw):
        self.protokoll.append("kommando_abgebrochen")
        raise KeyboardInterrupt()


class _RobotAbbruchBeimStoppen(FakeRobot):
    def ensure_client(self, name):
        if "command" in name.lower():
            return _AbbruchBeimStoppen(self.protokoll)
        return FakeService(self.protokoll)


def test_strg_c_im_ersten_abbauschritt_stoppt_den_abbau_nicht():
    protokoll = []
    spot = RealSpot.connect(
        _cfg(),
        robot_bauen=lambda cfg: _RobotAbbruchBeimStoppen(protokoll),
        estop_bauen=lambda client: FakeEstopGuard(protokoll),
        passwort_lesen=lambda user: "geheim",
    )
    with pytest.raises(KeyboardInterrupt):
        spot.close()
    # Alle vier Schritte muessen trotzdem gelaufen sein.
    assert "kommando_abgebrochen" in protokoll
    assert any(s.startswith("power_off") for s in protokoll), str(protokoll)
    assert "lease_return" in protokoll, str(protokoll)
    assert "estop_abmelden" in protokoll, str(protokoll)


def test_der_abbruch_geht_nach_dem_abbau_weiter_nach_oben():
    """Verschlucken waere schlimmer als das Problem: der Lauf wuerde als 'ok'
    verbucht, obwohl ihn jemand abgebrochen hat."""
    protokoll = []
    spot = RealSpot.connect(
        _cfg(),
        robot_bauen=lambda cfg: _RobotAbbruchBeimStoppen(protokoll),
        estop_bauen=lambda client: FakeEstopGuard(protokoll),
        passwort_lesen=lambda user: "geheim",
    )
    with pytest.raises(KeyboardInterrupt):
        spot.close()


def test_gewoehnliche_fehler_bleiben_stumm():
    """Die bestehende Zusicherung: ein fehlgeschlagener Schritt darf die
    folgenden nicht verhindern UND close() nicht zum Werfen bringen."""

    class KommandoKaputt(FakeService):
        def robot_command(self, command, end_time_secs=None, **kw):
            raise RuntimeError("Funk weg")

    class RobotKommandoKaputt(FakeRobot):
        def ensure_client(self, name):
            if "command" in name.lower():
                return KommandoKaputt(self.protokoll)
            return FakeService(self.protokoll)

    protokoll = []
    spot = RealSpot.connect(
        _cfg(),
        robot_bauen=lambda cfg: RobotKommandoKaputt(protokoll),
        estop_bauen=lambda client: FakeEstopGuard(protokoll),
        passwort_lesen=lambda user: "geheim",
    )
    spot.close()          # wirft nicht
    assert "estop_abmelden" in protokoll
