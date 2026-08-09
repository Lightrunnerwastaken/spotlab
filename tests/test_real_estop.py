import pytest
from bosdyn.api import estop_pb2
from bosdyn.client.estop import EstopEndpoint

from spotlab.backends.real.estop import ENDPOINT_NAME, LEVEL_NAMEN, register_coexisting


class FakeEstopClient:
    """Bildet get_config/set_config/register des echten EstopClient nach."""

    def __init__(self, bestehende_namen=("Tablet",), frische=None):
        # frische: {Endpunktname: Sekunden seit letzter gueltiger Antwort}.
        # Fehlt ein Name, hat sich der Endpunkt nie gemeldet -- eine Leiche.
        self.frische = dict(frische or {})
        self.config = estop_pb2.EstopConfig(unique_id="config-0")
        for name in bestehende_namen:
            ep = self.config.endpoints.add()
            ep.name = name
            ep.role = "PDB_rooted"
            ep.unique_id = f"ep-{name}"
        self.gesetzte_configs = []

    def get_config(self):
        return self.config

    def get_status(self):
        """Wie der echte EstopClient: Endpunkte MIT Frischeangabe.

        `time_since_valid_response` ist der Unterschied zwischen einer Leiche aus
        einem abgestuerzten Lauf und einer lebenden fremden Sitzung.
        """
        status = estop_pb2.EstopSystemStatus()
        for ep in self.config.endpoints:
            eintrag = status.endpoints.add()
            eintrag.endpoint.CopyFrom(ep)
            seit = self.frische.get(ep.name)
            if seit is not None:
                eintrag.time_since_valid_response.FromNanoseconds(int(seit * 1e9))
        return status

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

    def check_in(self, *args, **kwargs):
        return None


def _endpoint(client):
    return EstopEndpoint(
        client=client, name=ENDPOINT_NAME, estop_timeout=5.0, first_checkin=False
    )


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


# ---------------------------------------------- Frischepruefung (A1, S1.5)
#
# ENDPOINT_NAME ist eine feste Konstante. Bisher entfernte register_coexisting
# JEDEN Endpunkt dieses Namens -- auch den einer LEBENDEN zweiten
# spotlab-Instanz. Ein versehentlicher Doppelstart oder ein zweiter Schueler
# reichte, um dem anderen den Not-Aus aus der Konfiguration zu werfen.
#
# Der naheliegende Fix (jede Instanz bekommt einen eigenen Namen) ist selbst
# gefaehrlich: er zerstoert die Selbstheilung, mit der ein abgestuerzter Lauf
# beim naechsten Start ersetzt wird. Ein abgestuerzter Schuelerlaptop hielte
# den Roboter dann dauerhaft im CUT. Deshalb: gleicher Name, aber Frischepruefung.


def test_lebender_fremder_spotlab_endpunkt_wird_nicht_verdraengt():
    from spotlab.errors import EstopBusy

    client = FakeEstopClient(
        bestehende_namen=("Tablet", ENDPOINT_NAME),
        frische={"Tablet": 0.2, ENDPOINT_NAME: 0.3},      # meldet sich gerade
    )
    with pytest.raises(EstopBusy):
        register_coexisting(_endpoint(client))
    # Und vor allem: die Konfiguration ist unveraendert geblieben.
    assert client.gesetzte_configs == []
    assert [ep.name for ep in client.config.endpoints] == ["Tablet", ENDPOINT_NAME]


def test_die_meldung_nennt_den_ausweg():
    from spotlab.errors import EstopBusy

    client = FakeEstopClient(
        bestehende_namen=(ENDPOINT_NAME,), frische={ENDPOINT_NAME: 0.1}
    )
    with pytest.raises(EstopBusy) as fehler:
        register_coexisting(_endpoint(client))
    text = str(fehler.value)
    assert "spotlab" in text
    assert "beend" in text.lower()          # sag, was zu tun ist


def test_toter_eigener_endpunkt_wird_weiterhin_ersetzt():
    """Die Selbstheilung nach einem Absturz MUSS erhalten bleiben."""
    client = FakeEstopClient(
        bestehende_namen=("Tablet", ENDPOINT_NAME),
        frische={"Tablet": 0.2},            # spotlab meldet sich gar nicht mehr
    )
    register_coexisting(_endpoint(client))
    namen = [ep.name for ep in client.config.endpoints]
    assert namen.count(ENDPOINT_NAME) == 1
    assert "Tablet" in namen


def test_ueberfaelliger_eigener_endpunkt_gilt_als_tot():
    """Laenger als das eigene Zeitfenster stumm: der Roboter wertet ihn selbst
    schon als ausgeloest, wir duerfen ihn ersetzen."""
    from spotlab.backends.real.estop import ESTOP_TIMEOUT_S

    client = FakeEstopClient(
        bestehende_namen=(ENDPOINT_NAME,),
        frische={ENDPOINT_NAME: ESTOP_TIMEOUT_S + 1.0},
    )
    register_coexisting(_endpoint(client))
    assert [ep.name for ep in client.config.endpoints] == [ENDPOINT_NAME]


def test_ohne_namenskollision_wird_der_status_nicht_gebraucht():
    """Der haeufige Fall darf nicht an einem zusaetzlichen RPC scheitern."""

    class OhneStatus(FakeEstopClient):
        def get_status(self):
            raise AssertionError("get_status() ohne Namenskollision aufgerufen")

    client = OhneStatus(bestehende_namen=("Tablet",))
    register_coexisting(_endpoint(client))
    assert ENDPOINT_NAME in [ep.name for ep in client.config.endpoints]
