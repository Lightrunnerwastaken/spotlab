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
            # Auch ein Fehler im folgenden register/check-in braucht einen
            # eindeutig zugeordneten Rollback der gerade gesetzten Konfiguration.
            endpoint._config_id = angewandt.unique_id
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
        self.cleanup_status = "nicht_gestartet"

    def start(self):
        self._endpoint = EstopEndpoint(
            client=self._client, name=self._name, estop_timeout=self._timeout
        )
        try:
            register_coexisting(self._endpoint)
            self._keepalive = EstopKeepAlive(self._endpoint)
            self._keepalive.allow()
        except BaseException:
            try:
                self.stop()
            except BaseException as fehler:
                protokoll.notiere("E-Stop-Aufbau rollback gescheitert", fehler)
            raise

    def level(self):
        status = self._client.get_status()
        return LEVEL_NAMEN.get(status.stop_level, "unbekannt")

    def stop(self):
        """Eigenen Endpunkt nach Motor-Aus abgeben; niemals fremde Config ersetzen.

        Eine ausschliesslich eigene Config wird geleert (SDK >= 3.3). Bei
        fremden Endpunkten nur deregistrieren: set_config wuerde deren
        Registrierungen ebenfalls ungueltig machen. Der Server verweigert
        beide Operationen bei eingeschalteten Motoren. Keine Freigabe/CUTs
        senden. Keepalive bis zum Abmeldeversuch aufrechterhalten.
        """
        abbruch = None
        try:
            if self._endpoint is not None:
                self._abmelden()
        except Exception as fehler:
            self.cleanup_status = "fehlgeschlagen"
            protokoll.notiere("E-Stop-Abgabe fehlgeschlagen; diagnose/Tablet pruefen", fehler)
        except BaseException as fehler:
            self.cleanup_status = "abgebrochen"
            abbruch = fehler
        finally:
            if self._keepalive is not None:
                try:
                    self._keepalive.shutdown()
                except Exception as fehler:
                    protokoll.notiere("E-Stop-Keepalive beenden gescheitert", fehler)
                except BaseException as fehler:
                    abbruch = abbruch or fehler
                finally:
                    self._keepalive = None
            self._endpoint = None
        if abbruch is not None:
            raise abbruch

    def _abmelden(self):
        """Eigenen Endpunkt abgeben -- und JEDEN fruehen Ausstieg begruenden.

        Lauf 20260916T143307Z (16.09.2026): close() lief regulaer durch, der
        Endpunkt 'spotlab' stand danach weiter in der Konfiguration, und
        diagnose.log hatte keine Zeile dazu. Welche der beiden Bedingungen unten
        gegriffen hatte, war nicht nachlesbar. Deshalb nennt jeder Ausstieg die
        Bedingung und die IDs, die er gesehen hat; der Abgleich selbst bleibt
        streng -- nach Namen wird nie geloescht.
        """
        endpoint = self._endpoint
        config_id = endpoint._config_id
        if not config_id or not endpoint.unique_id:
            # Zum Beispiel EstopBusy: keine eigene Registrierung erworben.
            self.cleanup_status = "keine_eigene_registrierung"
            protokoll.notiere(
                "E-Stop-Abgabe uebersprungen: keine eigene Registrierung "
                f"(Konfigurations-ID {config_id!r}, eigene Endpunkt-ID {endpoint.unique_id!r})."
            )
            return
        aktiv = self._client.get_config(timeout=3)
        eintraege = [(ep.name, ep.unique_id) for ep in aktiv.endpoints]
        if aktiv.unique_id != config_id:
            # Andere Sitzung/Tablet hat uebernommen; keinesfalls nach Namen loeschen.
            self.cleanup_status = "bereits_abgegeben"
            protokoll.notiere(
                "E-Stop-Abgabe uebersprungen: Konfigurations-ID geaendert "
                f"(registriert gegen {config_id!r}, aktiv {aktiv.unique_id!r}; aktive "
                f"Endpunkte {eintraege}). Eine andere Sitzung oder das Tablet hat "
                "uebernommen; spotlab loescht nie nach Namen."
            )
            return
        eigen = [ep for ep in aktiv.endpoints if ep.unique_id == endpoint.unique_id
                 and ep.name == endpoint._name]
        if len(eigen) != 1:
            self.cleanup_status = "bereits_abgegeben"
            protokoll.notiere(
                "E-Stop-Abgabe uebersprungen: eigener Endpunkt nicht eindeutig in der "
                f"aktiven Konfiguration {aktiv.unique_id!r} ({len(eigen)} Treffer fuer Name "
                f"{endpoint._name!r} mit eigener ID {endpoint.unique_id!r}; aktive Endpunkte "
                f"{eintraege}). Spotlab loescht nie nach Namen."
            )
            return
        if len(aktiv.endpoints) == 1:
            # Kein Wiederherstellen eines alten Snapshots: nur unsere noch
            # aktive, ausschliesslich eigene Config per Config-ID vergleichen.
            result = self._client.set_config(estop_pb2.EstopConfig(), config_id, timeout=3)
            if result.endpoints:
                raise RuntimeError("E-Stop-Konfiguration wurde nicht geleert")
            self.cleanup_status = "eigene_konfiguration_entfernt"
        else:
            # SDK Endpoint.deregister() reicht timeout nicht weiter; direkt
            # ueber den Client ist auch dieser Abbau-RPC zeitlich begrenzt.
            self._client.deregister(config_id, endpoint, timeout=3)
            self.cleanup_status = "abgemeldet_fremde_konfiguration_erhalten"
            protokoll.notiere(
                "E-Stop: eigener Endpunkt abgemeldet, fremde Konfiguration erhalten. "
                "Falls Spot weiter gesperrt ist, Konfiguration am Tablet pruefen; "
                "Spotlab setzt fremde Registrierungen nicht zurueck.")
        protokoll.notiere(f"E-Stop-Abgabe: {self.cleanup_status}")
