# spotlab Fundament — Implementierungsplan, Teil 3 (Echtes Backend, Werkstatt, CLI)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Fortsetzung von `2026-08-06-spotlab-fundament-teil2.md`. **Global Constraints** aus Teil 1 gelten unverändert weiter.

**Umfang:** Tasks 13–21 — der echte Spot, die Werkstatt-Kommandos, die Kommandozeile und die Abnahme-Doku.

---

## Task 13: E-Stop mit Koexistenz — der Sperrpunkt A1

**Files:**
- Create: `src/spotlab/backends/real/__init__.py`, `src/spotlab/backends/real/estop.py`, `tests/test_real_estop.py`

**Interfaces:**
- Consumes: `bosdyn.client.estop`, `bosdyn.api.estop_pb2`
- Produces:
  - `ENDPOINT_NAME = "spotlab"`, `ESTOP_TIMEOUT_S = 5.0`
  - `register_coexisting(endpoint) -> str` — registriert den Endpunkt **zusätzlich** zur bestehenden Konfiguration, gibt die neue Config-ID zurück
  - `EstopGuard(client, name=ENDPOINT_NAME, timeout=ESTOP_TIMEOUT_S)` mit `.start() -> None`, `.stop() -> None`, `.level() -> str`
  - `LEVEL_NAMEN: dict[int, str]` — Protobuf-Level → deutscher Klartext

**Warum das der wichtigste Task des Plans ist:** die SDK-Bequemlichkeit `EstopEndpoint.force_simple_setup()` trägt im eigenen Docstring *„Replaces the existing estop configuration with a single-endpoint configuration."* Sie **entfernt den Endpunkt des Tablets**. Damit wäre der physische Not-Aus in der Hand der Aufsichtsperson wirkungslos, solange ein Schülerskript läuft. `register_coexisting` liest stattdessen die aktive Konfiguration, hängt den eigenen Endpunkt an und schreibt die *erweiterte* Konfiguration zurück.

- [ ] **Step 1: Test schreiben** — `tests/test_real_estop.py`

```python
import pytest
from bosdyn.api import estop_pb2
from bosdyn.client.estop import EstopEndpoint

from spotlab.backends.real.estop import ENDPOINT_NAME, LEVEL_NAMEN, register_coexisting


class FakeEstopClient:
    """Bildet get_config/set_config/register des echten EstopClient nach."""

    def __init__(self, bestehende_namen=("Tablet",)):
        self.config = estop_pb2.EstopConfig(unique_id="config-0")
        for name in bestehende_namen:
            ep = self.config.endpoints.add()
            ep.name = name
            ep.role = "PDB_rooted"
            ep.unique_id = f"ep-{name}"
        self.gesetzte_configs = []

    def get_config(self):
        return self.config

    def set_config(self, neue_config, target_config_id):
        assert target_config_id == self.config.unique_id
        self.gesetzte_configs.append(neue_config)
        angewandt = estop_pb2.EstopConfig()
        angewandt.CopyFrom(neue_config)
        angewandt.unique_id = "config-1"
        for i, ep in enumerate(angewandt.endpoints):
            if not ep.unique_id:
                ep.unique_id = f"ep-neu-{i}"
        self.config = angewandt
        return angewandt

    def register(self, target_config_id, endpoint):
        for ep in self.config.endpoints:
            if ep.name == endpoint._name:
                return ep
        raise AssertionError("Endpunkt nicht in der Konfiguration")

    # von EstopEndpoint.register über endpoint.stop() aufgerufen
    def check_in(self, *args, **kwargs):
        return None


def _endpoint(client):
    return EstopEndpoint(client=client, name=ENDPOINT_NAME, estop_timeout=5.0,
                         first_checkin=False)


def test_bestehender_tablet_endpunkt_bleibt_erhalten():
    client = FakeEstopClient(bestehende_namen=("Tablet",))
    register_coexisting(_endpoint(client))
    namen = [ep.name for ep in client.config.endpoints]
    assert "Tablet" in namen
    assert ENDPOINT_NAME in namen


def test_eigener_endpunkt_wird_angehaengt_nicht_ersetzt():
    client = FakeEstopClient(bestehende_namen=("Tablet", "Controller"))
    register_coexisting(_endpoint(client))
    assert len(client.config.endpoints) == 3


def test_stale_eigener_endpunkt_wird_ersetzt_nicht_verdoppelt():
    """Nach einem Absturz steht 'spotlab' noch in der Konfiguration."""
    client = FakeEstopClient(bestehende_namen=("Tablet", ENDPOINT_NAME))
    register_coexisting(_endpoint(client))
    namen = [ep.name for ep in client.config.endpoints]
    assert namen.count(ENDPOINT_NAME) == 1
    assert "Tablet" in namen


def test_neue_config_id_wird_zurueckgegeben():
    client = FakeEstopClient()
    assert register_coexisting(_endpoint(client)) == "config-1"


def test_endpunkt_uebernimmt_seine_unique_id():
    client = FakeEstopClient()
    endpunkt = _endpoint(client)
    register_coexisting(endpunkt)
    assert endpunkt.unique_id


def test_leere_konfiguration_funktioniert_auch():
    client = FakeEstopClient(bestehende_namen=())
    register_coexisting(_endpoint(client))
    assert [ep.name for ep in client.config.endpoints] == [ENDPOINT_NAME]


def test_level_namen_sind_deutsch():
    assert "frei" in LEVEL_NAMEN[estop_pb2.ESTOP_LEVEL_NONE].lower()
    assert LEVEL_NAMEN[estop_pb2.ESTOP_LEVEL_CUT]
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_real_estop.py -v`

- [ ] **Step 3: `backends/real/estop.py` implementieren**

```python
"""Not-Aus — mit Koexistenz statt Verdrängung.

`EstopEndpoint.force_simple_setup()` des SDK ersetzt laut eigenem Docstring die
bestehende Konfiguration durch eine mit nur EINEM Endpunkt. In einem Schulraum
hiesse das: solange ein Schülerskript läuft, ist der physische Not-Aus in der
Hand der Aufsichtsperson wirkungslos. Deshalb registrieren wir ZUSÄTZLICH.
"""

from bosdyn.api import estop_pb2
from bosdyn.client.estop import EstopEndpoint, EstopKeepAlive

ENDPOINT_NAME = "spotlab"
ESTOP_TIMEOUT_S = 5.0

LEVEL_NAMEN = {
    estop_pb2.ESTOP_LEVEL_UNKNOWN: "unbekannt",
    estop_pb2.ESTOP_LEVEL_CUT: "ausgelöst (Motoren aus)",
    estop_pb2.ESTOP_LEVEL_SETTLE_THEN_CUT: "wird ausgelöst (setzt sich ab)",
    estop_pb2.ESTOP_LEVEL_NONE: "frei",
}


def register_coexisting(endpoint):
    """Hängt `endpoint` an die aktive E-Stop-Konfiguration an, ohne andere zu entfernen.

    Ein bereits vorhandener Endpunkt gleichen Namens (Rest eines abgestürzten
    Laufs) wird ersetzt statt verdoppelt.
    """
    client = endpoint.client
    aktiv = client.get_config()

    neu = estop_pb2.EstopConfig()
    for bestehend in aktiv.endpoints:
        if bestehend.name == endpoint._name:
            continue                                   # stale eigener Endpunkt
        neu.endpoints.add().CopyFrom(bestehend)
    neu.endpoints.add().CopyFrom(endpoint.to_proto())

    angewandt = client.set_config(neu, aktiv.unique_id)
    for ep in angewandt.endpoints:
        if ep.name == endpoint._name:
            endpoint.from_proto(ep)
            break
    endpoint.register(angewandt.unique_id)
    return angewandt.unique_id


class EstopGuard:
    """Registriert den Endpunkt, hält das Keepalive, meldet den Level."""

    def __init__(self, client, name=ENDPOINT_NAME, timeout=ESTOP_TIMEOUT_S):
        self._client = client
        self._name = name
        self._timeout = timeout
        self._endpoint = None
        self._keepalive = None

    def start(self):
        self._endpoint = EstopEndpoint(client=self._client, name=self._name,
                                       estop_timeout=self._timeout)
        register_coexisting(self._endpoint)
        self._keepalive = EstopKeepAlive(self._endpoint)
        self._keepalive.allow()

    def level(self):
        status = self._client.get_status()
        return LEVEL_NAMEN.get(status.stop_level, "unbekannt")

    def stop(self):
        """Sauber abmelden: erst Keepalive beenden, dann Endpunkt deregistrieren.

        Ohne die Deregistrierung bliebe unser Endpunkt in der Konfiguration
        stehen und der Roboter würde ihn beim nächsten Timeout als ausgelöst
        werten — der nächste Schüler fände einen scheinbar defekten Spot.
        """
        if self._keepalive is not None:
            try:
                self._keepalive.shutdown()
            finally:
                self._keepalive = None
        if self._endpoint is not None:
            try:
                self._endpoint.deregister()
            except Exception:
                pass                                   # Abbau darf nie werfen
            finally:
                self._endpoint = None
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_real_estop.py -v`, erwartet 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends/real tests/test_real_estop.py && git commit -m "feat(estop): Koexistenz-Registrierung statt force_simple_setup (Sperrpunkt A1)"
```

---

## Task 14: Lease mit Halternamen und Verlusterkennung

**Files:**
- Create: `src/spotlab/backends/real/lease.py`, `tests/test_real_lease.py`

**Interfaces:**
- Produces:
  - `client_name() -> str` → `spotlab/<benutzer>@<rechner>`
  - `holder_of(lease_client, resource="body") -> str | None`
  - `LeaseGuard(lease_client, take=False, on_lost=None)` mit `.start()`, `.stop()`, `.lost -> bool`, `.raise_if_lost()`

- [ ] **Step 1: Test schreiben** — `tests/test_real_lease.py`

```python
import pytest
from bosdyn.api import lease_pb2
from bosdyn.client.lease import ResourceAlreadyClaimedError

from spotlab.backends.real.lease import LeaseGuard, client_name, holder_of
from spotlab.errors import LeaseBusy, LeaseLost


class FakeLeaseClient:
    def __init__(self, besitzer=None, blockiert=False):
        self._besitzer = besitzer
        self._blockiert = blockiert
        self.acquired = self.taken = self.returned = 0
        self.lease_wallet = None

    def list_leases(self):
        ressource = lease_pb2.LeaseResource(resource="body")
        if self._besitzer:
            ressource.lease_owner.client_name = self._besitzer
        return [ressource]

    def acquire(self, resource="body", **kw):
        if self._blockiert:
            raise ResourceAlreadyClaimedError(response=None)
        self.acquired += 1
        return object()

    def take(self, resource="body", **kw):
        self.taken += 1
        return object()

    def return_lease(self, *a, **kw):
        self.returned += 1


def test_client_name_traegt_benutzer_und_rechner():
    name = client_name()
    assert name.startswith("spotlab/") and "@" in name


def test_halter_wird_gelesen():
    assert holder_of(FakeLeaseClient(besitzer="spotlab/anna@laptop7")) == "spotlab/anna@laptop7"


def test_freies_lease_hat_keinen_halter():
    assert holder_of(FakeLeaseClient()) is None


def test_belegtes_lease_wird_zu_klartext():
    wache = LeaseGuard(FakeLeaseClient(besitzer="spotlab/anna@laptop7", blockiert=True))
    with pytest.raises(LeaseBusy) as info:
        wache.start()
    assert "spotlab lease --take" in str(info.value)


def test_take_uebernimmt_bewusst():
    client = FakeLeaseClient(besitzer="spotlab/anna@laptop7", blockiert=True)
    wache = LeaseGuard(client, take=True)
    wache.start(keepalive_bauen=lambda *_a, **_k: None)
    assert client.taken == 1 and client.acquired == 0
    wache.stop()


def test_verlust_wird_gemerkt_und_geworfen():
    wache = LeaseGuard(FakeLeaseClient())
    wache.start(keepalive_bauen=lambda *_a, **_k: None)
    wache._melde_verlust()
    assert wache.lost is True
    with pytest.raises(LeaseLost):
        wache.raise_if_lost()


def test_stop_ohne_start_wirft_nicht():
    LeaseGuard(FakeLeaseClient()).stop()
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_real_lease.py -v`

- [ ] **Step 3: `backends/real/lease.py` implementieren**

```python
"""Lease-Erwerb mit Namen, Keepalive und Verlusterkennung.

Der Client meldet sich als `spotlab/<benutzer>@<rechner>` an, damit ein Halter
im Klassenraum einen Namen hat. Erworben wird immer mit acquire, nie implizit
mit take — Übernahme ist eine bewusste Handlung.
"""

import getpass
import socket

from bosdyn.client.lease import LeaseKeepAlive

from spotlab.errors import LeaseLost, translate


def client_name():
    return f"spotlab/{getpass.getuser()}@{socket.gethostname()}"


def holder_of(lease_client, resource="body"):
    for eintrag in lease_client.list_leases():
        if eintrag.resource != resource:
            continue
        besitzer = eintrag.lease_owner
        return besitzer.client_name or besitzer.user_name or None
    return None


class LeaseGuard:
    def __init__(self, lease_client, take=False, on_lost=None):
        self._client = lease_client
        self._take = take
        self._on_lost = on_lost
        self._keepalive = None
        self.lost = False
        self.previous_holder = None

    def start(self, keepalive_bauen=None):
        self.previous_holder = holder_of(self._client)
        try:
            if self._take:
                self._client.take()
            else:
                self._client.acquire()
        except Exception as fehler:
            uebersetzt = translate(fehler)
            raise uebersetzt from fehler if uebersetzt else fehler

        bauen = keepalive_bauen or self._standard_keepalive
        self._keepalive = bauen(self._client, self._melde_verlust)

    def _standard_keepalive(self, lease_client, bei_verlust):
        return LeaseKeepAlive(lease_client, must_acquire=False, return_at_exit=False,
                              on_failure_callback=lambda _msg: bei_verlust())

    def _melde_verlust(self):
        self.lost = True
        if self._on_lost is not None:
            self._on_lost()

    def raise_if_lost(self):
        if self.lost:
            raise LeaseLost(
                "Kontrolle verloren — jemand anders hat übernommen. Lauf abgebrochen.")

    def stop(self):
        if self._keepalive is not None:
            try:
                self._keepalive.shutdown()
            except Exception:
                pass
            finally:
                self._keepalive = None
        try:
            self._client.return_lease(self._client.lease_wallet.get_lease("body"))
        except Exception:
            pass                                       # Abbau darf nie werfen
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_real_lease.py -v`, erwartet 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends/real/lease.py tests/test_real_lease.py && git commit -m "feat(lease): Halternamen, bewusste Übernahme, Verlusterkennung"
```

---

## Task 15: Rückmeldungen übersetzen

**Files:**
- Create: `src/spotlab/backends/real/feedback.py`, `tests/test_real_feedback.py`

**Interfaces:**
- Produces: `to_feedback(antwort: robot_command_pb2.RobotCommandFeedbackResponse) -> Feedback`

- [ ] **Step 1: Test schreiben** — `tests/test_real_feedback.py`

```python
from bosdyn.api import basic_command_pb2 as bc
from bosdyn.api import robot_command_pb2 as rc

from spotlab.backends.real.feedback import to_feedback


def _mobility():
    antwort = rc.RobotCommandFeedbackResponse()
    return antwort, antwort.feedback.synchronized_feedback.mobility_command_feedback


def test_stehend_ist_fertig():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.stand_feedback.status = bc.StandCommand.Feedback.STATUS_IS_STANDING
    rueck = to_feedback(antwort)
    assert rueck.done is True and "steht" in rueck.status


def test_aufstehen_laeuft_noch():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.stand_feedback.status = bc.StandCommand.Feedback.STATUS_IN_PROGRESS
    assert to_feedback(antwort).done is False


def test_sitzend_ist_fertig():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.sit_feedback.status = bc.SitCommand.Feedback.STATUS_IS_SITTING
    assert to_feedback(antwort).done is True


def test_am_ziel_ist_fertig():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.se2_trajectory_feedback.status = bc.SE2TrajectoryCommand.Feedback.STATUS_AT_GOAL
    rueck = to_feedback(antwort)
    assert rueck.done is True and "angekommen" in rueck.status


def test_vorzeitig_gestoppt_gilt_als_beendet():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.se2_trajectory_feedback.status = bc.SE2TrajectoryCommand.Feedback.STATUS_STOPPED
    assert to_feedback(antwort).done is True


def test_ueberschriebenes_kommando_gilt_als_abgelehnt():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_COMMAND_OVERRIDDEN
    rueck = to_feedback(antwort)
    assert rueck.rejected is True


def test_abgelaufenes_kommando_gilt_als_abgelehnt():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_COMMAND_TIMED_OUT
    assert to_feedback(antwort).rejected is True
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_real_feedback.py -v`

- [ ] **Step 3: `backends/real/feedback.py` implementieren**

```python
"""Die tief verschachtelte SDK-Rückmeldung auf den schmalen Feedback-Typ abbilden.

Ohne diese Naht müsste jedes Verb in api/ Protobuf-Interna kennen und das
Trockenlauf-Backend sie nachbauen.
"""

from bosdyn.api import basic_command_pb2 as bc

from spotlab.backends.base import Feedback

_ABGELEHNT = {
    bc.RobotCommandFeedbackStatus.STATUS_COMMAND_OVERRIDDEN: "vom nächsten Kommando überschrieben",
    bc.RobotCommandFeedbackStatus.STATUS_COMMAND_TIMED_OUT: "abgelaufen (zu spät nachgesendet)",
    bc.RobotCommandFeedbackStatus.STATUS_ROBOT_FROZEN: "Roboter ist eingefroren (Not-Aus?)",
    bc.RobotCommandFeedbackStatus.STATUS_UNKNOWN: "unbekannter Zustand",
}


def to_feedback(antwort):
    mobility = antwort.feedback.synchronized_feedback.mobility_command_feedback

    if mobility.status in _ABGELEHNT:
        return Feedback(done=False, status=_ABGELEHNT[mobility.status], rejected=True)

    welches = mobility.WhichOneof("feedback")

    if welches == "stand_feedback":
        fertig = mobility.stand_feedback.status == bc.StandCommand.Feedback.STATUS_IS_STANDING
        return Feedback(done=fertig, status="steht" if fertig else "steht auf")

    if welches == "sit_feedback":
        fertig = mobility.sit_feedback.status == bc.SitCommand.Feedback.STATUS_IS_SITTING
        return Feedback(done=fertig, status="sitzt" if fertig else "setzt sich")

    if welches == "se2_trajectory_feedback":
        status = mobility.se2_trajectory_feedback.status
        am_ziel = status == bc.SE2TrajectoryCommand.Feedback.STATUS_AT_GOAL
        gestoppt = status == bc.SE2TrajectoryCommand.Feedback.STATUS_STOPPED
        if am_ziel:
            return Feedback(done=True, status="angekommen")
        if gestoppt:
            return Feedback(done=True, status="angekommen (vorzeitig gestoppt)")
        return Feedback(done=False, status="unterwegs")

    if welches == "stop_feedback":
        return Feedback(done=True, status="gestoppt")

    if welches == "se2_velocity_feedback":
        return Feedback(done=True, status="fährt")

    return Feedback(done=False, status="läuft")
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_real_feedback.py -v`, erwartet 7 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends/real/feedback.py tests/test_real_feedback.py && git commit -m "feat(real): SDK-Rückmeldung auf Feedback-Typ abbilden"
```

---

## Task 16: RealSpot — Aufbau- und Abbausequenz

**Files:**
- Create: `src/spotlab/backends/real/session.py`, `tests/test_real_session.py`
- Modify: `src/spotlab/backends/real/__init__.py`

**Interfaces:**
- Produces:
  - `RealSpot(robot, clients, guards, recorder)` — erfüllt `SpotBackend`; Klassenmethode `RealSpot.connect(cfg, recorder=None, take=False, sdk_bauen=None) -> RealSpot`
  - `.robot` — das rohe bosdyn-Robot-Objekt
  - `AUFBAU_SCHRITTE: tuple[str, ...]` — für Test und `doctor` dieselbe Reihenfolge

**Aufbaureihenfolge (fest):** `auth → time_sync → estop → lease → aufzeichnung`. Motoren bleiben aus.
**Abbaureihenfolge (fest, garantiert):** `bewegung_stoppen → sicher_hinsetzen_und_ausschalten → lease_zurückgeben → estop_abmelden → verbindung_schliessen`.

- [ ] **Step 1: Test schreiben** — `tests/test_real_session.py`

```python
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
        self.protokoll.append(f"client:{name}")
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
        return type("Id", (), {"serial_number": "SN-1", "nickname": "Spot",
                               "software_release": type("R", (), {"version": "4.0"})()})()


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
        _cfg(), recorder=None, take=take,
        robot_bauen=lambda cfg: FakeRobot(protokoll),
        estop_bauen=lambda client: FakeEstopGuard(protokoll),
        passwort_lesen=lambda user: "geheim")


def test_aufbau_haelt_die_reihenfolge_ein():
    protokoll = []
    _connect(protokoll)
    reihenfolge = [s for s in protokoll if s in ("auth", "time_sync", "estop", "lease_acquire")]
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
    backend.close()                                  # darf nicht werfen
    assert "lease_return" in protokoll and "estop_abmelden" in protokoll


def test_abbau_ist_idempotent():
    backend = _connect([])
    backend.close()
    backend.close()


def test_schrittlisten_sind_dokumentiert():
    assert AUFBAU_SCHRITTE[0] == "auth"
    assert ABBAU_SCHRITTE[-1] == "verbindung_schliessen"
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_real_session.py -v`

- [ ] **Step 3: `backends/real/session.py` implementieren**

```python
"""Die Sitzung am echten Spot: Aufbau, Betrieb, garantierter Abbau.

Der Abbau ist die einzige nicht verhandelbare Invariante: er läuft immer, auch
bei Ausnahme, Ctrl-C oder Lease-Verlust. Ein hart getöteter Prozess dagegen
lässt die Keepalives sterben — dann geht der Roboter von selbst in den sicheren
Zustand, und genau das ist der Not-Aus, den man nicht kaputtprogrammieren kann.
"""

from bosdyn.api import estop_pb2
from bosdyn.client import create_standard_sdk
from bosdyn.client.estop import EstopClient
from bosdyn.client.image import ImageClient, build_image_request
from bosdyn.client.lease import LeaseClient
from bosdyn.client.robot_command import RobotCommandBuilder, RobotCommandClient
from bosdyn.client.robot_state import RobotStateClient

from spotlab.backends.base import Capability, SafetyStatus
from spotlab.backends.real.estop import EstopGuard
from spotlab.backends.real.feedback import to_feedback
from spotlab.backends.real.lease import LeaseGuard, holder_of
from spotlab.config import load_password
from spotlab.errors import NotPowered, TimeSyncFailed, translate

AUFBAU_SCHRITTE = ("auth", "time_sync", "estop", "lease", "aufzeichnung")
ABBAU_SCHRITTE = ("bewegung_stoppen", "sicher_ausschalten", "lease_zurückgeben",
                  "estop_abmelden", "verbindung_schliessen")

SDK_NAME = "spotlab"


def _standard_robot(cfg):
    sdk = create_standard_sdk(SDK_NAME)
    return sdk.create_robot(cfg.ip)


class RealSpot:
    """Backend für den echten Roboter."""

    def __init__(self, robot, command_client, state_client, image_client,
                 lease_guard, estop_guard, recorder=None):
        self._robot = robot
        self._commands = command_client
        self._state = state_client
        self._images = image_client
        self._lease = lease_guard
        self._estop = estop_guard
        self._recorder = recorder
        self._geschlossen = False
        self._quellen = None

    # ------------------------------------------------------------- Aufbau

    @classmethod
    def connect(cls, cfg, recorder=None, take=False, robot_bauen=None,
                estop_bauen=None, passwort_lesen=None):
        robot_bauen = robot_bauen or _standard_robot
        passwort_lesen = passwort_lesen or load_password
        robot = robot_bauen(cfg)

        try:
            robot.authenticate(cfg.username, passwort_lesen(cfg.username))
        except Exception as fehler:
            uebersetzt = translate(fehler, ip=cfg.ip)
            raise uebersetzt from fehler if uebersetzt else fehler

        try:
            robot.time_sync.wait_for_sync()
        except Exception as fehler:
            raise TimeSyncFailed(
                "Die Uhr deines Laptops weicht zu stark von der des Roboters ab; "
                "die Zeitsynchronisierung ist fehlgeschlagen. Windows-Uhrzeit "
                "automatisch stellen lassen und erneut versuchen.") from fehler

        estop_client = robot.ensure_client(EstopClient.default_service_name)
        wache = (estop_bauen or EstopGuard)(estop_client)
        wache.start()

        lease_client = robot.ensure_client(LeaseClient.default_service_name)
        lease = LeaseGuard(lease_client, take=take)
        lease.start()
        if take and lease.previous_holder and recorder is not None:
            recorder.event("lease_übernommen", von=lease.previous_holder)

        backend = cls(
            robot=robot,
            command_client=robot.ensure_client(RobotCommandClient.default_service_name),
            state_client=robot.ensure_client(RobotStateClient.default_service_name),
            image_client=robot.ensure_client(ImageClient.default_service_name),
            lease_guard=lease, estop_guard=wache, recorder=recorder)

        if recorder is not None:
            kennung = robot.get_id()
            recorder.set_robot_info(
                roboter_seriennummer=getattr(kennung, "serial_number", None),
                roboter_nickname=getattr(kennung, "nickname", None),
                roboter_software=getattr(getattr(kennung, "software_release", None),
                                         "version", None),
                uebernommen=bool(take))
            recorder.event("verbunden", backend="real", ip=cfg.ip)
        return backend

    # ------------------------------------------------------------- Protokoll

    def capabilities(self):
        return (Capability.LOCOMOTION | Capability.POSTURE | Capability.POWER
                | Capability.DEPTH_CAMERAS | Capability.GRAY_CAMERAS
                | Capability.LEASE | Capability.ESTOP)

    def send_command(self, command, end_time_secs=None):
        self._lease.raise_if_lost()
        if not self.is_powered:
            raise NotPowered("Die Motoren sind aus — rufe zuerst `spot.power_on()` auf.")
        try:
            return self._commands.robot_command(command, end_time_secs=end_time_secs)
        except Exception as fehler:
            uebersetzt = translate(fehler)
            raise uebersetzt from fehler if uebersetzt else fehler

    def command_feedback(self, command_id):
        return to_feedback(self._commands.robot_command_feedback(command_id))

    def robot_state(self):
        return self._state.get_robot_state()

    def frame_tree_snapshot(self):
        return self._robot.get_frame_tree_snapshot()

    def image_sources(self):
        if self._quellen is None:
            self._quellen = [q.name for q in self._images.list_image_sources()]
        return list(self._quellen)

    def images(self, sources):
        return self._images.get_image([build_image_request(name) for name in sources])

    def power_on(self):
        self._lease.raise_if_lost()
        try:
            self._robot.power_on(timeout_sec=20)
        except Exception as fehler:
            uebersetzt = translate(fehler)
            raise uebersetzt from fehler if uebersetzt else fehler

    def power_off(self, safe=True):
        self._robot.power_off(cut_immediately=not safe, timeout_sec=20)

    @property
    def is_powered(self):
        return bool(self._robot.is_powered_on())

    def safety_status(self):
        halter = None
        stufe = None
        try:
            halter = holder_of(self._robot.ensure_client(LeaseClient.default_service_name))
        except Exception:
            pass
        try:
            stufe = self._estop.level()
        except Exception:
            pass
        return SafetyStatus(lease_holder=halter, estop_level=stufe)

    @property
    def robot(self):
        return self._robot

    # ------------------------------------------------------------- Abbau

    def close(self):
        """Geordnetes Ende. Jeder Schritt ist gekapselt — der Abbau läuft immer durch."""
        if self._geschlossen:
            return
        self._geschlossen = True
        self._versuche(lambda: self._commands.robot_command(
            RobotCommandBuilder.stop_command()))
        self._versuche(lambda: self._robot.power_off(cut_immediately=False, timeout_sec=20))
        self._versuche(self._lease.stop)
        self._versuche(self._estop.stop)

    @staticmethod
    def _versuche(schritt):
        try:
            schritt()
        except Exception:
            pass
```

- [ ] **Step 4: `backends/real/__init__.py`**

```python
from spotlab.backends.real.session import ABBAU_SCHRITTE, AUFBAU_SCHRITTE, RealSpot

__all__ = ["RealSpot", "AUFBAU_SCHRITTE", "ABBAU_SCHRITTE"]
```

- [ ] **Step 5: Tests laufen lassen** — `pytest tests/test_real_session.py -v`, erwartet 7 PASS

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/backends/real tests/test_real_session.py && git commit -m "feat(real): RealSpot mit fester Aufbau- und garantierter Abbaureihenfolge"
```

---

## Task 17: Projekte anlegen

**Files:**
- Create: `src/spotlab/workshop/__init__.py`, `src/spotlab/workshop/project.py`, `src/spotlab/workshop/templates/hallo_spot.py`, `tests/test_workshop_project.py`

**Interfaces:**
- Produces: `create_project(name, wurzel=Path.cwd()) -> Path`, `PROJEKT_DATEIEN: tuple[str, ...]`

- [ ] **Step 1: Test schreiben** — `tests/test_workshop_project.py`

```python
import pytest

from spotlab.workshop.project import create_project


def test_projekt_hat_alle_teile(tmp_path):
    ordner = create_project("mein-spot", tmp_path)
    assert (ordner / "hallo_spot.py").exists()
    assert (ordner / "README.md").exists()
    assert (ordner / ".vscode" / "settings.json").exists()
    assert (ordner / "runs").is_dir()


def test_vorlage_ist_lauffaehiges_python(tmp_path):
    quelle = (create_project("p", tmp_path) / "hallo_spot.py").read_text(encoding="utf-8")
    compile(quelle, "hallo_spot.py", "exec")
    assert "spotlab.connect()" in quelle
    assert "power_on()" in quelle


def test_bestehender_ordner_wird_nicht_ueberschrieben(tmp_path):
    create_project("p", tmp_path)
    with pytest.raises(FileExistsError):
        create_project("p", tmp_path)


def test_name_wird_entschaerft(tmp_path):
    ordner = create_project("Mein Spot/Projekt", tmp_path)
    assert ordner.parent == tmp_path
    assert "/" not in ordner.name
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_workshop_project.py -v`

- [ ] **Step 3: Vorlage `workshop/templates/hallo_spot.py`**

```python
"""Erstes Spot-Programm.

Starten:  spotlab run hallo_spot.py
Oder in VS Code einfach F5 drücken — aufgezeichnet wird beides.
"""

import spotlab

# connect() meldet sich an, synchronisiert die Uhr, registriert den Not-Aus und
# holt das Lease. Am Ende des with-Blocks setzt sich der Spot hin und schaltet
# die Motoren ab — auch wenn dein Programm mit einem Fehler abbricht.
with spotlab.connect() as spot:

    # Motoren einschalten ist bewusst eine eigene Zeile: ein 30-kg-Roboter steht
    # nicht auf, nur weil jemand ein Programm gestartet hat.
    spot.power_on()
    spot.stand()

    print("Akku:", spot.battery, "%")

    # Einen Meter vorwärts. move() wartet, bis der Spot wirklich angekommen ist.
    spot.move(forward=1.0)

    # Ein Bild der vorderen linken Kamera aufnehmen und speichern.
    bild = spot.camera("frontleft")
    bild.save("vorne.png")
    print("Bild gespeichert:", bild)

    # 90 Grad nach links drehen.
    spot.move(turn=90)

print("Fertig. Der Lauf liegt im Ordner runs/.")
```

- [ ] **Step 4: `workshop/project.py` implementieren**

```python
"""Ein neues Schülerprojekt anlegen — vollständig, nicht als leeres Gerüst."""

import json
import re
import sys
from importlib import resources
from pathlib import Path

PROJEKT_DATEIEN = ("hallo_spot.py", "README.md", ".vscode/settings.json")

README = """# {name}

Ein Spot-Projekt.

## Losfahren

```
spotlab doctor          # prüft Netz, Anmeldung, Not-Aus, Lease, Akku
spotlab run hallo_spot.py
```

Oder in VS Code `hallo_spot.py` öffnen und F5 drücken — der Lauf wird so oder so
in `runs/` aufgezeichnet.

## Ohne Roboter üben

```
spotlab run hallo_spot.py --dryrun
```

Baut und prüft alle Kommandos, bewegt aber nichts. Kameras gibt es dabei nicht.

## Läufe ansehen

```
spotlab runs
```
"""


def _sicherer_name(name):
    sauber = re.sub(r"[^\w.-]+", "-", name.strip()).strip("-.")
    return sauber or "spot-projekt"


def create_project(name, wurzel=None):
    wurzel = Path(wurzel) if wurzel else Path.cwd()
    ordner = wurzel / _sicherer_name(name)
    if ordner.exists():
        raise FileExistsError(
            f"Den Ordner {ordner} gibt es schon. Wähle einen anderen Namen.")

    (ordner / ".vscode").mkdir(parents=True)
    (ordner / "runs").mkdir()

    vorlage = resources.files("spotlab.workshop.templates").joinpath("hallo_spot.py")
    (ordner / "hallo_spot.py").write_text(vorlage.read_text(encoding="utf-8"),
                                          encoding="utf-8")
    (ordner / "README.md").write_text(README.format(name=ordner.name), encoding="utf-8")
    (ordner / ".vscode" / "settings.json").write_text(
        json.dumps({"python.defaultInterpreterPath": sys.executable,
                    "python.terminal.activateEnvironment": True,
                    "files.encoding": "utf8"}, indent=2), encoding="utf-8")
    (ordner / ".gitignore").write_text("runs/\n__pycache__/\n", encoding="utf-8")
    return ordner
```

- [ ] **Step 5: Tests laufen lassen** — `pytest tests/test_workshop_project.py -v`, erwartet 4 PASS

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/workshop tests/test_workshop_project.py && git commit -m "feat(workshop): Projekte anlegen mit lauffähiger Vorlage"
```

---

## Task 18: VS Code öffnen und Läufe starten

**Files:**
- Create: `src/spotlab/workshop/editor.py`, `src/spotlab/workshop/launcher.py`, `tests/test_workshop_launcher.py`

**Interfaces:**
- Produces:
  - `open_in_editor(pfad, command="code", starter=subprocess.run) -> None` — wirft `SpotlabError` mit Klartext, wenn das Programm fehlt
  - `run_script(pfad, dryrun=False, starter=subprocess.run) -> int` — startet `python <pfad>` im Projektordner, gibt den Rückgabecode zurück

- [ ] **Step 1: Test schreiben** — `tests/test_workshop_launcher.py`

```python
import pytest

from spotlab.errors import SpotlabError
from spotlab.workshop.editor import open_in_editor
from spotlab.workshop.launcher import run_script


def test_editor_wird_mit_pfad_aufgerufen(tmp_path):
    aufrufe = []
    open_in_editor(tmp_path, command="code", starter=lambda *a, **k: aufrufe.append(a))
    assert str(tmp_path) in aufrufe[0][0]


def test_fehlender_editor_gibt_klartext(tmp_path):
    def fehlt(*a, **k):
        raise FileNotFoundError

    with pytest.raises(SpotlabError) as info:
        open_in_editor(tmp_path, command="code", starter=fehlt)
    assert "PATH" in str(info.value) or "gefunden" in str(info.value)


def test_skript_wird_mit_python_gestartet(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    aufrufe = []

    class Ergebnis:
        returncode = 0

    def starter(argumente, **kw):
        aufrufe.append((argumente, kw))
        return Ergebnis()

    assert run_script(skript, starter=starter) == 0
    argumente, kw = aufrufe[0]
    assert argumente[1] == str(skript)
    assert kw["cwd"] == str(tmp_path)


def test_dryrun_setzt_umgebungsvariable(tmp_path):
    skript = tmp_path / "x.py"
    skript.write_text("print(1)", encoding="utf-8")
    aufrufe = []

    class Ergebnis:
        returncode = 0

    def starter(argumente, **kw):
        aufrufe.append(kw)
        return Ergebnis()

    run_script(skript, dryrun=True, starter=starter)
    assert aufrufe[0]["env"]["SPOTLAB_BACKEND"] == "dryrun"


def test_fehlendes_skript_gibt_klartext(tmp_path):
    with pytest.raises(SpotlabError) as info:
        run_script(tmp_path / "gibtsnicht.py")
    assert "gibtsnicht.py" in str(info.value)
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_workshop_launcher.py -v`

- [ ] **Step 3: `workshop/editor.py` implementieren**

```python
"""Projekt im Editor öffnen."""

import subprocess
from pathlib import Path

from spotlab.errors import SpotlabError


def open_in_editor(pfad, command="code", starter=subprocess.run):
    ziel = Path(pfad)
    try:
        starter([command, str(ziel)], shell=False, check=False)
    except FileNotFoundError as fehler:
        raise SpotlabError(
            f"'{command}' wurde nicht gefunden. In VS Code F1 drücken und "
            f"\"Shell Command: Install 'code' command in PATH\" ausführen — "
            f"oder den Ordner {ziel} von Hand öffnen.") from fehler
```

- [ ] **Step 4: `workshop/launcher.py` implementieren**

```python
"""Ein Schülerskript starten.

Die Aufzeichnung hängt an connect(), nicht an diesem Starter — wer in VS Code
F5 drückt, bekommt sie genauso. run_script() ergänzt nur die Backend-Wahl per
Umgebungsvariable und einen Rückgabecode für die Kommandozeile.
"""

import os
import subprocess
import sys
from pathlib import Path

from spotlab.errors import SpotlabError

ENV_BACKEND = "SPOTLAB_BACKEND"


def run_script(pfad, dryrun=False, starter=subprocess.run):
    skript = Path(pfad).resolve()
    if not skript.exists():
        raise SpotlabError(f"Die Datei {skript} gibt es nicht.")

    umgebung = dict(os.environ)
    if dryrun:
        umgebung[ENV_BACKEND] = "dryrun"

    ergebnis = starter([sys.executable, str(skript)], cwd=str(skript.parent),
                       env=umgebung, check=False)
    return int(getattr(ergebnis, "returncode", 0))
```

- [ ] **Step 5: `connect()` muss `SPOTLAB_BACKEND` beachten** — in `src/spotlab/__init__.py` die Zeile

```python
    art = backend or (cfg.default_backend if cfg else "dryrun")
```

ersetzen durch

```python
    import os
    art = backend or os.environ.get("SPOTLAB_BACKEND") or (
        cfg.default_backend if cfg else "dryrun")
```

- [ ] **Step 6: Test dafür ergänzen** — in `tests/test_workshop_launcher.py`

```python
def test_connect_beachtet_umgebungsvariable(tmp_path, monkeypatch):
    import spotlab
    monkeypatch.setenv("SPOTLAB_BACKEND", "dryrun")
    with spotlab.connect(runs_dir=tmp_path) as spot:
        assert spot.backend.__class__.__name__ == "DryRunBackend"
```

- [ ] **Step 7: Tests laufen lassen** — `pytest tests/test_workshop_launcher.py -v`, erwartet 6 PASS

- [ ] **Step 8: Commit**

```bash
git add src/spotlab tests/test_workshop_launcher.py && git commit -m "feat(workshop): VS Code öffnen und Skripte starten"
```

---

## Task 19: doctor — die Diagnose

**Files:**
- Create: `src/spotlab/workshop/doctor.py`, `tests/test_doctor.py`

**Interfaces:**
- Produces:
  - `Check(name: str, ok: bool, detail: str, rat: str = "")` — frozen dataclass
  - `diagnose(cfg=None, robot_bauen=None, passwort_lesen=None) -> list[Check]` — bricht nach dem ersten Fehlschlag ab, weil jede Stufe die nächste voraussetzt
  - `STUFEN = ("Konfiguration", "Netz", "Anmeldung", "Zeitsync", "Not-Aus", "Lease", "Akku")`

- [ ] **Step 1: Test schreiben** — `tests/test_doctor.py`

```python
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
    pruefungen = diagnose(_cfg(), robot_bauen=lambda cfg: GesunderRobot(),
                          passwort_lesen=lambda u: "x")
    assert [p.name for p in pruefungen] == list(STUFEN)
    assert all(p.ok for p in pruefungen)


def test_ohne_konfiguration_bricht_es_sofort_ab():
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

    pruefungen = diagnose(_cfg(), robot_bauen=lambda cfg: SchlechterLogin(),
                          passwort_lesen=lambda u: "x")
    assert pruefungen[-1].name == "Anmeldung" and not pruefungen[-1].ok


def test_belegtes_lease_ist_kein_fehler_sondern_ein_hinweis():
    from bosdyn.api import lease_pb2

    class Belegt(GesunderRobot):
        def list_leases(self):
            r = lease_pb2.LeaseResource(resource="body")
            r.lease_owner.client_name = "spotlab/anna@laptop7"
            return [r]

    pruefungen = diagnose(_cfg(), robot_bauen=lambda cfg: Belegt(),
                          passwort_lesen=lambda u: "x")
    lease = [p for p in pruefungen if p.name == "Lease"][0]
    assert lease.ok is False
    assert "anna" in lease.detail
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_doctor.py -v`

- [ ] **Step 3: `workshop/doctor.py` implementieren**

```python
"""`spotlab doctor` — beantwortet „warum geht es nicht" in der Reihenfolge,
in der die Dinge tatsächlich schiefgehen.

Die Kette bricht nach dem ersten Fehlschlag ab: ohne Netz keine Anmeldung, ohne
Anmeldung kein Lease. Weiterzuprüfen erzeugte nur Folgefehler, die vom
eigentlichen Problem ablenken.
"""

from dataclasses import dataclass

from spotlab.errors import ConfigMissing, translate


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    rat: str = ""


STUFEN = ("Konfiguration", "Netz", "Anmeldung", "Zeitsync", "Not-Aus", "Lease", "Akku")


def diagnose(cfg=None, robot_bauen=None, passwort_lesen=None):
    from spotlab.backends.real.estop import LEVEL_NAMEN
    from spotlab.backends.real.lease import holder_of
    from spotlab.backends.real.session import _standard_robot
    from spotlab.config import load_config, load_password

    robot_bauen = robot_bauen or _standard_robot
    passwort_lesen = passwort_lesen or load_password
    pruefungen = []

    if cfg is None:
        try:
            cfg = load_config()
        except ConfigMissing as fehler:
            return [Check("Konfiguration", False, str(fehler),
                          "Einmalig einrichten mit `spotlab login`.")]
    pruefungen.append(Check("Konfiguration", True,
                            f"{cfg.nickname} unter {cfg.ip} als '{cfg.username}'"))

    try:
        robot = robot_bauen(cfg)
    except Exception as fehler:
        return pruefungen + [_fehler("Netz", fehler, cfg.ip)]
    pruefungen.append(Check("Netz", True, f"{cfg.ip} antwortet"))

    try:
        robot.authenticate(cfg.username, passwort_lesen(cfg.username))
    except Exception as fehler:
        return pruefungen + [_fehler("Anmeldung", fehler, cfg.ip)]
    pruefungen.append(Check("Anmeldung", True, f"als '{cfg.username}' angemeldet"))

    try:
        robot.time_sync.wait_for_sync()
    except Exception as fehler:
        return pruefungen + [Check("Zeitsync", False, str(fehler),
                                   "Windows-Uhrzeit automatisch stellen lassen.")]
    pruefungen.append(Check("Zeitsync", True, "Uhren laufen synchron"))

    try:
        from bosdyn.client.estop import EstopClient
        status = robot.ensure_client(EstopClient.default_service_name).get_status()
        stufe = LEVEL_NAMEN.get(status.stop_level, "unbekannt")
        frei = stufe == "frei"
        pruefungen.append(Check("Not-Aus", frei, stufe,
                                "" if frei else "Am Tablet oder Knopf freigeben."))
        if not frei:
            return pruefungen
    except Exception as fehler:
        return pruefungen + [_fehler("Not-Aus", fehler, cfg.ip)]

    try:
        from bosdyn.client.lease import LeaseClient
        halter = holder_of(robot.ensure_client(LeaseClient.default_service_name))
        if halter and not halter.startswith("spotlab/"):
            pruefungen.append(Check("Lease", False, f"gehalten von {halter}",
                                    "Absprechen, dann `spotlab lease --take`."))
        elif halter:
            pruefungen.append(Check("Lease", False, f"gehalten von {halter}",
                                    "Läuft dort noch ein Skript? Sonst `spotlab lease --take`."))
        else:
            pruefungen.append(Check("Lease", True, "frei"))
    except Exception as fehler:
        return pruefungen + [_fehler("Lease", fehler, cfg.ip)]

    try:
        from bosdyn.client.robot_state import RobotStateClient
        zustand = robot.ensure_client(RobotStateClient.default_service_name).get_robot_state()
        prozent = (zustand.battery_states[0].charge_percentage.value
                   if zustand.battery_states else 0.0)
        genug = prozent >= 20.0
        pruefungen.append(Check("Akku", genug, f"{prozent:.0f} %",
                                "" if genug else "Auf die Ladestation stellen."))
    except Exception as fehler:
        pruefungen.append(_fehler("Akku", fehler, cfg.ip))

    return pruefungen


def _fehler(name, fehler, ip):
    uebersetzt = translate(fehler, ip=ip)
    if uebersetzt is not None:
        return Check(name, False, type(fehler).__name__, str(uebersetzt))
    return Check(name, False, f"{type(fehler).__name__}: {fehler}", "")
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_doctor.py -v`, erwartet 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/workshop/doctor.py tests/test_doctor.py && git commit -m "feat(workshop): doctor mit stufenweiser Diagnose"
```

---

## Task 20: Kommandozeile

**Files:**
- Create: `src/spotlab/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `main(argv=None) -> int`, `build_parser() -> argparse.ArgumentParser`
- Kommandos: `login`, `doctor`, `new`, `open`, `run`, `runs`, `runs show <id>`, `lease`, `lease --take`

- [ ] **Step 1: Test schreiben** — `tests/test_cli.py`

```python
import pytest

from spotlab.cli import build_parser, main


def test_alle_kommandos_sind_erreichbar():
    parser = build_parser()
    for kommando in ("login", "doctor", "new", "open", "run", "runs", "lease"):
        assert parser.parse_args([kommando] + (["x"] if kommando in ("new", "open", "run") else []))


def test_new_legt_projekt_an(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "mein-projekt"]) == 0
    assert (tmp_path / "mein-projekt" / "hallo_spot.py").exists()
    assert "mein-projekt" in capsys.readouterr().out


def test_new_meldet_bestehenden_ordner_als_fehler(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["new", "p"])
    assert main(["new", "p"]) == 1
    assert "gibt es schon" in capsys.readouterr().err


def test_runs_listet_laeufe(tmp_path, monkeypatch, capsys):
    from spotlab.record.run import RunRecorder
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()
    rec = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    rec.finish("ok")
    assert main(["runs"]) == 0
    assert rec.id in capsys.readouterr().out


def test_runs_ohne_laeufe_sagt_das_freundlich(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["runs"]) == 0
    assert "noch keine" in capsys.readouterr().out.lower()


def test_run_mit_dryrun_setzt_die_variable(tmp_path, monkeypatch):
    skript = tmp_path / "x.py"
    skript.write_text("import spotlab\nwith spotlab.connect() as s:\n    pass\n",
                      encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["run", "x.py", "--dryrun"]) == 0


def test_doctor_gibt_stufen_aus(monkeypatch, capsys):
    from spotlab.workshop.doctor import Check
    monkeypatch.setattr("spotlab.cli.diagnose",
                        lambda *a, **k: [Check("Netz", True, "antwortet"),
                                         Check("Anmeldung", False, "falsch", "spotlab login")])
    assert main(["doctor"]) == 1
    ausgabe = capsys.readouterr().out
    assert "Netz" in ausgabe and "spotlab login" in ausgabe


def test_unbekanntes_kommando_gibt_hilfe():
    with pytest.raises(SystemExit):
        main(["quatsch"])
```

- [ ] **Step 2: Fehlschlag prüfen** — `pytest tests/test_cli.py -v`

- [ ] **Step 3: `cli.py` implementieren**

```python
"""Kommandozeile — eine dünne Hülle.

Alles, was hier steht, ist Argumentauswertung und Ausgabe. Die Funktionalität
liegt in workshop/ und api/, damit die spätere GUI und der MCP-Server sich an
derselben Schicht bedienen können.
"""

import argparse
import getpass
import sys
from pathlib import Path

from spotlab import __version__
from spotlab.errors import SpotlabError
from spotlab.record.read import list_runs, read_jsonl, read_run
from spotlab.workshop.doctor import diagnose
from spotlab.workshop.editor import open_in_editor
from spotlab.workshop.launcher import run_script
from spotlab.workshop.project import create_project

GRUEN, ROT, GRAU, AUS = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="spotlab", description="Den Spot programmieren — Kantonsschule")
    parser.add_argument("--version", action="version", version=f"spotlab {__version__}")
    unter = parser.add_subparsers(dest="kommando", required=True)

    unter.add_parser("login", help="IP, Benutzer und Passwort hinterlegen")
    unter.add_parser("doctor", help="Netz, Anmeldung, Not-Aus, Lease und Akku prüfen")

    neu = unter.add_parser("new", help="neues Projekt anlegen")
    neu.add_argument("name")

    oeffnen = unter.add_parser("open", help="Projekt in VS Code öffnen")
    oeffnen.add_argument("projekt", nargs="?", default=".")

    starten = unter.add_parser("run", help="Skript starten und aufzeichnen")
    starten.add_argument("datei")
    starten.add_argument("--dryrun", action="store_true",
                         help="ohne Roboter, nur Kommandos prüfen")

    laeufe = unter.add_parser("runs", help="Läufe auflisten")
    laeufe.add_argument("show", nargs="?", help="Lauf-ID für Details")

    lease = unter.add_parser("lease", help="wer steuert den Spot")
    lease.add_argument("--take", action="store_true", help="Kontrolle bewusst übernehmen")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return _fuehre_aus(args)
    except SpotlabError as fehler:
        print(f"{ROT}{fehler}{AUS}", file=sys.stderr)
        return 1
    except FileExistsError as fehler:
        print(f"{ROT}{fehler}{AUS}", file=sys.stderr)
        return 1


def _fuehre_aus(args):
    if args.kommando == "login":
        return _login()
    if args.kommando == "doctor":
        return _doctor()
    if args.kommando == "new":
        ordner = create_project(args.name)
        print(f"Projekt angelegt: {ordner}")
        print(f"Weiter mit:  spotlab open {ordner.name}")
        return 0
    if args.kommando == "open":
        from spotlab.config import load_config
        try:
            befehl = load_config().editor_command
        except SpotlabError:
            befehl = "code"
        open_in_editor(Path(args.projekt).resolve(), command=befehl)
        return 0
    if args.kommando == "run":
        return run_script(args.datei, dryrun=args.dryrun)
    if args.kommando == "runs":
        return _runs(args.show)
    if args.kommando == "lease":
        return _lease(args.take)
    return 1


def _login():
    from spotlab.config import Config, Limits, load_config, save_config, save_password
    try:
        alt = load_config()
    except SpotlabError:
        alt = None
    ip = input(f"IP des Spot [{alt.ip if alt else '192.168.80.3'}]: ").strip() \
        or (alt.ip if alt else "192.168.80.3")
    benutzer = input(f"Benutzername [{alt.username if alt else 'user'}]: ").strip() \
        or (alt.username if alt else "user")
    spitzname = input(f"Spitzname [{alt.nickname if alt else 'Spot'}]: ").strip() \
        or (alt.nickname if alt else "Spot")
    passwort = getpass.getpass("Passwort (wird im Windows-Tresor gespeichert): ")

    save_config(Config(ip=ip, username=benutzer, nickname=spitzname,
                       limits=alt.limits if alt else Limits(),
                       editor_command=alt.editor_command if alt else "code",
                       default_backend=alt.default_backend if alt else "real"))
    if passwort:
        save_password(benutzer, passwort)
    print("Gespeichert. Prüfen mit:  spotlab doctor")
    return 0


def _doctor():
    alles_gut = True
    for pruefung in diagnose():
        zeichen = f"{GRUEN}OK  {AUS}" if pruefung.ok else f"{ROT}FEHL{AUS}"
        print(f"{zeichen} {pruefung.name:<14} {pruefung.detail}")
        if pruefung.rat:
            print(f"     {GRAU}→ {pruefung.rat}{AUS}")
        alles_gut = alles_gut and pruefung.ok
    return 0 if alles_gut else 1


def _runs(kennung):
    wurzel = Path.cwd() / "runs"
    if kennung:
        verzeichnis = wurzel / kennung
        if not verzeichnis.is_dir():
            raise SpotlabError(f"Den Lauf {kennung} gibt es in {wurzel} nicht.")
        lauf = read_run(verzeichnis)
        print(f"Lauf     {lauf.id}")
        print(f"Ergebnis {lauf.ergebnis}" + (f" — {lauf.fehler}" if lauf.fehler else ""))
        print(f"Backend  {lauf.backend}")
        print(f"Dauer    {lauf.dauer_s:.1f} s")
        print(f"Skript   {lauf.skript or '(interaktiv)'}")
        print(f"Daten    {lauf.ereignisse_n} Ereignisse, {lauf.abtastungen_n} Abtastungen")
        print()
        for satz in read_jsonl(verzeichnis / "ereignisse.jsonl"):
            print(f"  {satz.get('t', 0.0):7.2f}s  {satz.get('art'):<16} {satz.get('daten')}")
        return 0

    laeufe = list_runs(wurzel)
    if not laeufe:
        print(f"In {wurzel} gibt es noch keine Läufe. Starte einen mit:  spotlab run <datei>")
        return 0
    for lauf in laeufe:
        farbe = GRUEN if lauf.ergebnis == "ok" else ROT
        print(f"{lauf.id}  {farbe}{lauf.ergebnis:<14}{AUS} "
              f"{lauf.dauer_s:6.1f}s  {lauf.backend:<7} {Path(lauf.skript).name if lauf.skript else ''}")
    return 0


def _lease(uebernehmen):
    from bosdyn.client.lease import LeaseClient

    from spotlab.backends.real.lease import client_name, holder_of
    from spotlab.backends.real.session import _standard_robot
    from spotlab.config import load_config, load_password

    cfg = load_config()
    robot = _standard_robot(cfg)
    robot.authenticate(cfg.username, load_password(cfg.username))
    robot.time_sync.wait_for_sync()
    client = robot.ensure_client(LeaseClient.default_service_name)

    halter = holder_of(client)
    if not uebernehmen:
        print(f"Lease: {halter or 'frei'}")
        print(f"Du wärst: {client_name()}")
        return 0

    if halter:
        print(f"{ROT}Achtung:{AUS} {halter} steuert den Spot gerade.")
        print("Ein laufendes Skript dort bricht sofort ab.")
        if input("Wirklich übernehmen? [ja/nein] ").strip().lower() not in ("ja", "j"):
            print("Abgebrochen.")
            return 1
    client.take()
    print(f"Übernommen als {client_name()}.")
    return 0
```

- [ ] **Step 4: Tests laufen lassen** — `pytest tests/test_cli.py -v`, erwartet 8 PASS

- [ ] **Step 5: Gesamtsuite laufen lassen** — `pytest -q`, erwartet alle PASS

- [ ] **Step 6: Commit**

```bash
git add src/spotlab/cli.py tests/test_cli.py && git commit -m "feat(cli): login, doctor, new, open, run, runs, lease"
```

---

## Task 21: Doku und Abnahme-Checkliste

**Files:**
- Create: `README.md`, `CLAUDE.md`, `docs/ABNAHME.md`

**Interfaces:** keine — reine Dokumentation.

- [ ] **Step 1: `README.md`** — Zweck, Installation (`pip install -e .[dev]`), Schnellstart (`spotlab login` → `doctor` → `new` → `open` → `run`), Beispielprogramm, Verbverzeichnis, Hinweis auf Trockenlauf, Verweis auf `docs/ABNAHME.md` und die Spec.

- [ ] **Step 2: `CLAUDE.md`** — Regeln für die weitere Arbeit am Repo:
  - Kommandos nur über `RobotCommandBuilder`, keine Eigen-API
  - Bezeichner englisch, Meldungen deutsch, Aufzeichnungsdateien deutsch
  - Der Abbau in `RealSpot.close()` ist die nicht verhandelbare Invariante — jede Änderung daran braucht einen Test
  - `force_simple_setup()` ist verboten (verdrängt den Tablet-Not-Aus); Registrierung nur über `register_coexisting`
  - Neue Fähigkeit ⇒ neuer Eintrag in `Capability` und neuer Abnahmepunkt
  - Tests laufen ohne Roboter; `dryrun` ist das Standard-Testdouble
  - Verweis auf Spec und die drei Planteile

- [ ] **Step 3: `docs/ABNAHME.md`** — die Punkte A1–A8 aus der Spec, jeder mit Prozedur, Erwartung und leerem Ergebnisfeld. A1 wird ergänzt um den Befund aus Task 13: *im SDK-Quelltext bestätigt, dass `force_simple_setup()` verdrängt; `register_coexisting` ist die Gegenmassnahme; am Gerät zu verifizieren ist, dass der Tablet-Not-Aus danach weiterhin auslöst.*

- [ ] **Step 4: Vollständige Suite** — `pytest -q`

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/ABNAHME.md && git commit -m "docs: README, Arbeitsregeln und Abnahme-Checkliste A1-A8"
```

---

## Selbstprüfung des Plans

**Spec-Abdeckung:** 5.1 Konfiguration → Task 3 · 5.2 Protokoll → Task 6 · 5.3 Sitzungskern → Tasks 13–16 · 5.4 Trockenlauf → Task 7 · 5.5 Bibliothek → Tasks 8–12 · 5.6 Aufzeichnung → Tasks 4, 5, 12 · 5.7 Fehlerübersetzung → Task 2 · 5.8 Werkstatt/CLI → Tasks 17–20 · Abschnitt 8 Prüfung → in jeden Task eingebaut · Abschnitt 9 Abnahme → Task 21 · Abschnitt 10 A1 → Task 13.

**Abweichung von der Spec, bewusst:** die Spec beschrieb `command_feedback` als „Rückmeldung zu einem laufenden Kommando" ohne Typ. Der Plan legt ihn auf `Feedback(done, status, rejected)` fest statt auf das rohe Protobuf, damit `api/` protobuf-frei bleibt und der Trockenlauf die Struktur nicht nachbauen muss. Das rohe Protobuf bleibt über `spot.robot` erreichbar.

**Neuer Befund gegenüber der Spec:** A1 ist im SDK-Quelltext bestätigt, nicht mehr nur vermutet. Task 13 liefert die Gegenmassnahme mit sechs Tests. Die Geräteverifikation bleibt trotzdem nötig — Tests gegen eine Attrappe zeigen, dass wir die *richtige* Konfiguration schreiben, nicht dass der Roboter sie so auslegt wie erwartet.
