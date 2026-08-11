"""Not-Aus — mit Koexistenz statt Verdrängung.

`EstopEndpoint.force_simple_setup()` des SDK ersetzt laut eigenem Docstring die
bestehende Konfiguration durch eine mit nur EINEM Endpunkt. In einem Schulraum
hiesse das: solange ein Schülerskript läuft, ist der physische Not-Aus in der
Hand der Aufsichtsperson wirkungslos. Deshalb registrieren wir ZUSÄTZLICH.
"""

from bosdyn.api import estop_pb2
from bosdyn.client.estop import EstopEndpoint, EstopKeepAlive

from spotlab import protokoll
from spotlab.errors import EstopBusy

ENDPOINT_NAME = "spotlab"
ESTOP_TIMEOUT_S = 5.0

LEVEL_NAMEN = {
    estop_pb2.ESTOP_LEVEL_UNKNOWN: "unbekannt",
    estop_pb2.ESTOP_LEVEL_CUT: "ausgelöst (Motoren aus)",
    estop_pb2.ESTOP_LEVEL_SETTLE_THEN_CUT: "wird ausgelöst (setzt sich ab)",
    estop_pb2.ESTOP_LEVEL_NONE: "frei",
}


def sekunden_seit_antwort(client, name):
    """Sekunden seit der letzten gültigen Antwort dieses Endpunkts, sonst None.

    None heisst „hat sich nie gemeldet" — der Roboter führt ihn zwar in der
    Konfiguration, aber es antwortet niemand. Das ist die Signatur einer Leiche
    aus einem abgestürzten Lauf.
    """
    for eintrag in client.get_status().endpoints:
        if eintrag.endpoint.name != name:
            continue
        if not eintrag.HasField("time_since_valid_response"):
            return None
        dauer = eintrag.time_since_valid_response
        return dauer.seconds + dauer.nanos / 1e9
    return None


def register_coexisting(endpoint):
    """Hängt `endpoint` an die aktive E-Stop-Konfiguration an, ohne andere zu entfernen.

    Ein vorhandener Endpunkt gleichen Namens wird nur dann ersetzt, wenn er
    NICHT MEHR ANTWORTET — also der Rest eines abgestürzten Laufs ist.

    Warum diese Unterscheidung nötig ist: `ENDPOINT_NAME` ist eine feste
    Konstante. Ohne Frischeprüfung wirft ein zweiter Verbindungsversuch — ein
    versehentlicher Doppelstart, ein zweiter Schüler — der ERSTEN, laufenden
    Sitzung ihren Not-Aus aus der Konfiguration. Das trifft Abnahmepunkt A1
    unmittelbar.

    Warum trotzdem ein gemeinsamer Name: ein instanzeigener Name („spotlab-4711")
    schlösse diese Lücke ebenfalls, zerstörte aber die Selbstheilung. Ein
    abgestürzter Schülerlaptop hinterliesse dann einen Endpunkt, den niemand
    mehr ersetzen kann, und der Roboter ginge beim nächsten Timeout dauerhaft
    in den CUT. Der gemeinsame Name plus Frischeprüfung behält beides.

    Der Status wird nur bei einer Namenskollision abgefragt — der häufige Fall
    soll nicht an einem zusätzlichen RPC hängen.
    """
    client = endpoint.client
    aktiv = client.get_config()

    if any(e.name == endpoint._name for e in aktiv.endpoints):
        seit = sekunden_seit_antwort(client, endpoint._name)
        if seit is not None and seit <= ESTOP_TIMEOUT_S:
            raise EstopBusy(
                f"Ein anderer spotlab-Lauf hält gerade den Not-Aus dieses Roboters "
                f"(letzte Rückmeldung vor {seit:.1f} s). Zwei spotlab-Sitzungen am "
                f"selben Spot sind nicht vorgesehen: beende den anderen Lauf, dann "
                f"versuche es erneut."
            )

    neu = estop_pb2.EstopConfig()
    for bestehend in aktiv.endpoints:
        if bestehend.name == endpoint._name:
            continue  # nachweislich stiller eigener Endpunkt
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
            except Exception as fehler:
                # Abbau darf nie werfen — aber er darf auch nicht spurlos
                # scheitern: ein zurueckgelassener Endpunkt laesst den naechsten
                # Schueler einen scheinbar defekten Spot vorfinden.
                protokoll.notiere("E-Stop-Endpunkt abmelden gescheitert", fehler)
            finally:
                self._endpoint = None
