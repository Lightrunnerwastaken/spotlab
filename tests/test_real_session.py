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
