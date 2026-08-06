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
