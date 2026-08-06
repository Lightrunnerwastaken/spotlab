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
            continue  # stale eigener Endpunkt
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
        self._endpoint = EstopEndpoint(
            client=self._client, name=self._name, estop_timeout=self._timeout
        )
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
                pass  # Abbau darf nie werfen
            finally:
                self._endpoint = None
