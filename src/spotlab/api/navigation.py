"""Auf einer Karte fahren.

Die Verben laufen im Schülerskript, nicht in der GUI: der Roboter bewegt sich
autonom, also braucht es Lease und Not-Aus — dieselbe Regel wie für move().

Zwei Dinge nimmt die Bibliothek dem Schüler ab, die im SDK-Beispiel jedes Mal
von Hand stehen: das Nachsenden (Navigationskommandos verfallen) und der
Geschwindigkeitsdeckel aus config.toml.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from spotlab.api import motion
from spotlab.backends.base import Capability, require
from spotlab.errors import NavigationError, SpotlabError
from spotlab.maps.store import finde, karten, lade_graph

NACHSENDE_INTERVALL_S = 0.5
KOMMANDO_GUELTIGKEIT_S = 1.5


@dataclass(frozen=True)
class Map:
    name: str
    dir: Path
    graph: object

    @property
    def waypoints(self):
        """Die bei der Aufnahme gesetzten Namen."""
        return [wp.annotations.name for wp in self.graph.waypoints if wp.annotations.name]

    def id_fuer(self, name):
        for wp in self.graph.waypoints:
            if wp.annotations.name == name or wp.id == name:
                return wp.id
        vorhanden = ", ".join(self.waypoints) or "keine benannten Wegpunkte"
        raise SpotlabError(
            f"Den Wegpunkt '{name}' gibt es auf der Karte '{self.name}' nicht. "
            f"Vorhanden: {vorhanden}."
        )

    def __repr__(self):
        return f"<Map {self.name} mit {len(self.graph.waypoints)} Wegpunkten>"


def _protokolliere(recorder, name, **daten):
    if recorder is not None:
        recorder.event("kommando", name=name, **daten)


def load_map(backend, recorder, workspace, name=None, active=None):
    """Karte auf den Roboter laden. Ohne `name` die in der GUI gewählte."""
    require(backend, Capability.GRAPH_NAV, "auf einer Karte navigieren")
    if not workspace:
        raise SpotlabError(
            "Es ist kein Arbeitsordner gesetzt. Wähle einen in der Ansicht 'Projekte'."
        )
    gewaehlt = name or active
    if not gewaehlt:
        vorhanden = ", ".join(k.name for k in karten(workspace)) or "keine"
        raise SpotlabError(
            "Es ist keine Karte ausgewählt. Gib eine an — spot.load_map('name') — "
            f"oder wähle eine in der Ansicht 'Karten'. Vorhanden: {vorhanden}."
        )

    ordner = finde(workspace, gewaehlt)
    _protokolliere(recorder, "load_map", karte=str(gewaehlt))
    backend.upload_map(ordner)
    return Map(name=ordner.name, dir=ordner, graph=lade_graph(ordner))


def localize(backend, recorder):
    require(backend, Capability.GRAPH_NAV, "sich auf einer Karte verorten")
    _protokolliere(recorder, "localize")
    kennung = backend.localize()
    if recorder is not None:
        recorder.event("rückmeldung", name="localize", status=f"verortet bei {kennung}")
    return kennung


def map_pose(backend, recorder=None):
    """(x, y, grad) im Rahmen der Karte -- oder None, solange nicht verortet."""
    require(backend, Capability.GRAPH_NAV, "die eigene Lage auf der Karte lesen")
    return backend.map_pose()


def process_map(backend, recorder, karte, melde=None, fiducial=True, odometrie=True,
                speichern=True):
    """Eine schon gespeicherte Karte nachbearbeiten und zurückschreiben.

    Der Weg für eine Karte, die vor dieser Funktion aufgezeichnet wurde: sie ist
    eine KETTE, und Spot fährt darauf nur die aufgezeichnete Strecke ab. `karte`
    muss geladen sein — HOCHLADEN ist der Schritt, der ein Lease braucht, und
    genau deshalb läuft das hier in einem Programm und nicht in der GUI.

    Geschrieben wird nur, wenn wirklich etwas gerechnet wurde: eine gescheiterte
    Nachbearbeitung soll die gespeicherte Karte nicht anfassen.
    """
    require(backend, Capability.GRAPH_NAV, "eine Karte nachbearbeiten")
    _protokolliere(recorder, "process_map", karte=karte.name,
                   fiducial=bool(fiducial), odometrie=bool(odometrie))
    bericht = backend.process_map(melde=melde, fiducial=fiducial, odometrie=odometrie)
    if recorder is not None:
        recorder.event("rückmeldung", name="process_map",
                       status=" ".join(bericht.meldungen))
    if speichern and bericht.gelaufen:
        graph = backend.download_map(karte.dir)
        if melde is not None:
            melde(f"Karte gespeichert: {len(graph.waypoints)} Wegpunkte, "
                  f"{len(graph.edges)} Kanten.")
    return bericht


def navigate_to(
    backend,
    recorder,
    karte,
    ziel,
    limits,
    timeout=120.0,
    schlaf=time.sleep,
    jetzt=time.monotonic,
    abbruch=None,
):
    """Autonom zu einem Wegpunkt fahren. True: angekommen; False: abgebrochen.

    Navigationskommandos verfallen wie Geschwindigkeitskommandos, deshalb die
    Schleife: nachsenden, Rückmeldung prüfen, wiederholen. `abbruch()` wird in
    jedem Takt gefragt; sagt es wahr, hält Spot an (`stop`) und die Fahrt ist
    zu Ende -- so bricht der Karten-Tab eine Fahrt für ein neues Ziel ab.
    """
    require(backend, Capability.GRAPH_NAV, "auf einer Karte navigieren")
    waypoint_id = karte.id_fuer(ziel)
    params = backend.travel_params(limits)
    _protokolliere(
        recorder,
        "navigate_to",
        ziel=str(ziel),
        waypoint=waypoint_id,
        max_speed=limits.max_speed,
    )

    ende = jetzt() + float(timeout)
    command_id = None
    letzter_text = ""
    while True:
        command_id = backend.navigate_step(
            waypoint_id, KOMMANDO_GUELTIGKEIT_S, params, command_id=command_id
        )
        zustand = backend.navigation_status(command_id)

        if zustand.status != letzter_text:
            letzter_text = zustand.status
            if recorder is not None:
                recorder.event("rückmeldung", name="navigate_to", status=zustand.status)

        if zustand.gescheitert:
            raise NavigationError(zustand.status)
        if zustand.fertig:
            return True
        if abbruch is not None and abbruch():
            motion.stop(backend, recorder)
            if recorder is not None:
                recorder.event("rückmeldung", name="navigate_to", status="abgebrochen")
            return False
        if jetzt() >= ende:
            raise NavigationError(
                f"Der Spot hat '{ziel}' nicht innerhalb von {timeout:.0f} s erreicht "
                f"(zuletzt: {zustand.status})."
            )
        schlaf(NACHSENDE_INTERVALL_S)
