"""Schleifen schliessen und Anker optimieren — an genau einer Stelle.

Zwei Wege führen hierher, und beide sollen dasselbe tun:

frisch    `maps/session.py` bearbeitet die Aufnahme, bevor sie sie herunterlädt.
          Leaselos wie die Aufnahme selbst.
nachher   `api/navigation.py::process_map` bearbeitet eine schon gespeicherte
          Karte. Die muss dafür zuerst auf den Roboter, und **Hochladen braucht
          ein Lease** (`UploadGraphRequest.lease` — „ownership of graph-nav
          service"; das SDK-Beispiel `graph_nav_command_line.py` hält es
          entsprechend, `recording_command_line.py` nicht). Deshalb läuft der
          zweite Weg in einem Schülerprogramm und nicht in der GUI.

Was BEIDE brauchen, ist nur dieses Protokoll — und das kennt kein Lease. Der
Aufrufer bringt den fertigen `MapProcessingServiceClient` mit; hier wird keiner
gebaut, keine Sitzung geöffnet und nichts besessen. Genau deshalb darf diese
Datei unter `maps/` liegen.
"""

import time
from dataclasses import dataclass

from bosdyn.api.graph_nav import map_processing_pb2
from google.protobuf import wrappers_pb2

# Zwei Fristen, damit weder der Dienst noch der Aufrufer ewig wartet: der Dienst
# hört von selbst auf (`timeout_seconds`, er meldet dann `timed_out` und liefert,
# was er hat), die RPC-Frist liegt darüber und ist nur das Netz darunter.
SERVER_FRIST_S = 90.0
RPC_FRIST_S = 120.0
# NOCHMAL VERSUCHEN, wenn der Dienst meldet, die Karte sei waehrend der Rechnung
# veraendert worden (MapModifiedError: "Please try again"). Befund vom 27.09.2026:
# in allen vier Laeufen von `karte_verbessern.py` scheiterte der Schleifenschluss
# genau so, direkt nach dem Hochladen -- und es wurde nie nochmal versucht. Dieselbe
# Karte bekam auf dem Roboter ohne Hochladen davor 15 neue Kanten. Gewartet wird vor
# dem zweiten und dritten Versuch so lange wie in `WARTEN_S`.
VERSUCHE = 3
WARTEN_S = (3.0, 8.0)

OHNE_DIENST = (
    "Dieser Roboter bietet die Kartennachbearbeitung nicht an "
    "(Dienst map-processing-service)."
)


@dataclass(frozen=True)
class Nachbearbeitung:
    """Was die Nachbearbeitung erreicht hat. `None` heisst: nicht gelaufen."""

    neue_kanten: int | None = None
    schritte: int | None = None
    meldungen: tuple = ()

    @property
    def gelaufen(self):
        return self.neue_kanten is not None or self.schritte is not None


def schliesse_schleifen(client, fiducial=True, odometrie=True, frist_s=RPC_FRIST_S,
                        melde=None, schlaf=time.sleep):
    """Schleifen im Graphen suchen und schliessen. Gibt (neue Kanten, abgelaufen).

    Der Aufzeichnungsdienst legt Wegpunkte in einer KETTE an: er weiss nicht,
    dass der Gang, durch den Spot zum zweiten Mal fährt, derselbe ist. Erst
    dieser Schritt verbindet die Enden — über gesehene Fiducials und über die
    Odometrie. Ohne ihn gibt es zwischen zwei Punkten immer nur den einen
    aufgezeichneten Weg.

    `modify_map_on_server=True`: geändert wird die Karte AUF DEM ROBOTER, und
    genau die lädt der Aufrufer danach herunter.
    """
    params = map_processing_pb2.ProcessTopologyRequest.Params(
        do_fiducial_loop_closure=wrappers_pb2.BoolValue(value=bool(fiducial)),
        do_odometry_loop_closure=wrappers_pb2.BoolValue(value=bool(odometrie)),
        timeout_seconds=SERVER_FRIST_S,
    )
    antwort = _wiederholt(
        lambda: _dienst(client).process_topology(
            params=params, modify_map_on_server=True, timeout=frist_s
        ),
        "Schleifensuche", melde, schlaf,
    )
    return len(antwort.new_subgraph.edges), bool(antwort.timed_out)


def optimiere_anker(client, frist_s=RPC_FRIST_S, melde=None, schlaf=time.sleep):
    """Die Anker global optimieren. Gibt die Zahl der Rechenschritte zurück.

    Anker sind die Lage jedes Wegpunkts in EINEM gemeinsamen Rahmen. Ohne die
    Optimierung stehen sie so da, wie die Odometrie sie beim Fahren gesehen hat
    — eine Runde durch das Schulhaus schliesst sich dann sichtbar nicht. Daran
    hängt mehr als die Zeichnung: `maps/geometry.py` bevorzugt die Anker, und
    die Rekonstruktion eines Raums rechnet im selben Rahmen.
    """
    antwort = _wiederholt(
        lambda: _dienst(client).process_anchoring(
            params=map_processing_pb2.ProcessAnchoringRequest.Params(),
            modify_anchoring_on_server=True,
            stream_intermediate_results=False,
            timeout=frist_s,
        ),
        "Ankerrechnung", melde, schlaf,
    )
    return int(antwort.iteration)


def _wiederholt(aufruf, was, melde, schlaf):
    """`aufruf()` — bei MapModifiedError bis zu VERSUCHE-mal, mit Pause dazwischen.

    Jeder andere Fehler geht sofort durch: nur diesen einen erklärt der Dienst
    selbst für vorübergehend.
    """
    from bosdyn.client.map_processing import MapModifiedError

    for versuch in range(1, VERSUCHE + 1):
        try:
            return aufruf()
        except MapModifiedError:
            if versuch == VERSUCHE:
                raise
            pause = WARTEN_S[min(versuch - 1, len(WARTEN_S) - 1)]
            if melde is not None:
                melde(f"Die Karte wurde auf dem Roboter während der {was} noch verändert — "
                      f"in {pause:.0f} s noch einmal ({versuch + 1}. von {VERSUCHE} Versuchen).")
            schlaf(pause)
    raise AssertionError("unerreichbar")


def _warum(fehler, was):
    """Der Grund in Worten — und bei einer veränderten Karte, was zu tun ist."""
    from bosdyn.client.map_processing import MapModifiedError

    if isinstance(fehler, MapModifiedError):
        return (f"die Karte wurde auf dem Roboter während der {was} verändert, "
                f"{VERSUCHE}-mal hintereinander. „Karte verbessern“ im Tab Karten "
                f"noch einmal starten.")
    return str(fehler)


def nachbearbeiten(client, melde=None, fiducial=True, odometrie=True, schlaf=time.sleep):
    """Beides nacheinander — der Schritt, der aus einer Kette eine Karte macht.

    Wirft NIE. Jeder Schritt einzeln gekapselt, wie der Abbau in
    `RealSpot.close()`: eine gescheiterte Nachbearbeitung darf die Aufnahme
    nicht kosten. Wer eine Stunde durch das Schulhaus gefahren ist, bekommt
    seine Karte — notfalls unbearbeitet, aber mit dem Grund in der Meldung.
    """
    def sagen(text):
        meldungen.append(text)
        if melde is not None:
            melde(text)

    meldungen = []
    neue_kanten = schritte = None

    sagen("Schleifen werden gesucht…")
    try:
        neue_kanten, abgelaufen = schliesse_schleifen(client, fiducial, odometrie,
                                                      melde=sagen, schlaf=schlaf)
        sagen(
            f"{neue_kanten} neue Verbindung{'en' if neue_kanten != 1 else ''}."
            if neue_kanten
            else "Keine neue Verbindung gefunden."
        )
        if abgelaufen:
            sagen("Die Suche brach nach der Frist ab — die Karte ist trotzdem brauchbar.")
    except Exception as fehler:
        sagen(f"Schleifen nicht geschlossen: {_warum(fehler, 'Schleifensuche')}")

    sagen("Anker werden optimiert…")
    try:
        schritte = optimiere_anker(client, melde=sagen, schlaf=schlaf)
        sagen(f"Anker optimiert ({schritte} Rechenschritte).")
    except Exception as fehler:
        sagen(f"Anker nicht optimiert: {_warum(fehler, 'Ankerrechnung')}")

    return Nachbearbeitung(neue_kanten, schritte, tuple(meldungen))


def _dienst(client):
    if client is None:
        from spotlab.errors import MapError

        raise MapError(OHNE_DIENST)
    return client
