"""Karten auf der Platte — im Format des SDK.

graph, waypoint_snapshots/ und edge_snapshots/ schreibt
GraphNavClient.write_graph_and_snapshots; daran ändern wir nichts. Nur
karte.json kommt dazu, mit dem, was das SDK nicht speichert.

Der Grund für dieses Format ist Austauschbarkeit: eine mit spotlab
aufgezeichnete Karte lässt sich unverändert an graph_nav_command_line.py und
view_map.py verfüttern — und umgekehrt.
"""

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bosdyn.api.graph_nav import map_pb2
from google.protobuf.message import DecodeError

from spotlab.errors import SpotlabError
from spotlab.pfade import sicherer_name
from spotlab.record import atomar

KARTEN_ORDNER = "karten"
METADATEN = "karte.json"


@dataclass(frozen=True)
class MapInfo:
    name: str
    dir: Path
    aufgezeichnet: str | None
    roboter: str | None
    wegpunkte: int
    kanten: int


def karten_wurzel(workspace):
    return Path(workspace) / KARTEN_ORDNER


def speichere_metadaten(kartenordner, name, roboter, graph):
    from spotlab import __version__

    (Path(kartenordner) / METADATEN).write_text(
        json.dumps(
            {
                "name": name,
                "aufgezeichnet": datetime.now(UTC).isoformat(),
                "roboter": roboter,
                "wegpunkte": len(graph.waypoints),
                "kanten": len(graph.edges),
                "spotlab_version": __version__,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def lade_graph(kartenordner):
    graph = map_pb2.Graph()
    graph.ParseFromString((Path(kartenordner) / "graph").read_bytes())
    return graph


def _beschreibe(ordner):
    try:
        meta = json.loads((ordner / METADATEN).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        meta = {}

    wegpunkte = meta.get("wegpunkte")
    kanten = meta.get("kanten")
    if wegpunkte is None or kanten is None:
        # Beschädigte Metadaten dürfen eine Karte nicht unbrauchbar machen —
        # der Graph selbst ist die Wahrheit.
        try:
            graph = lade_graph(ordner)
            wegpunkte, kanten = len(graph.waypoints), len(graph.edges)
        except (OSError, DecodeError):
            # DecodeError fehlte: eine beschädigte `graph`-Datei flog bis nach
            # oben durch und verhinderte den GUI-Start — samt NOT-AUS-Knopf.
            wegpunkte, kanten = 0, 0

    return MapInfo(
        name=meta.get("name", ordner.name),
        dir=ordner,
        aufgezeichnet=meta.get("aufgezeichnet"),
        roboter=meta.get("roboter"),
        wegpunkte=int(wegpunkte),
        kanten=int(kanten),
    )


def karten(workspace):
    wurzel = karten_wurzel(workspace)
    if not wurzel.is_dir():
        return []
    ordner = [p for p in wurzel.iterdir() if p.is_dir() and (p / "graph").exists()]
    ordner.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    # Ordner für Ordner, nicht in einer Listcomprehension: EINE unlesbare Karte
    # nahm sonst die ganze Liste mit — und mit ihr den Programmstart.
    liste = []
    for p in ordner:
        try:
            liste.append(_beschreibe(p))
        except Exception:
            continue
    return liste


def finde(workspace, name):
    ziel = karten_wurzel(workspace) / sicherer_name(name, ersatz="karte")
    if ziel.is_dir() and (ziel / "graph").exists():
        return ziel
    vorhanden = [k.name for k in karten(workspace)]
    if not vorhanden:
        raise SpotlabError(f"Es gibt noch keine Karten in {karten_wurzel(workspace)}.")
    raise SpotlabError(
        f"Die Karte '{name}' gibt es nicht. Vorhanden: {', '.join(vorhanden)}."
    )


def aktualisiere_zahlen(kartenordner, graph, jetzt=None):
    """Wegpunkte und Kanten in `karte.json` nachziehen, ohne den Rest zu verlieren.

    Nach dem Schleifenschluss stimmen die Zahlen nicht mehr — und `aufgezeichnet`
    darf trotzdem nicht auf heute springen: die Karte wurde damals gefahren,
    heute nur nachbearbeitet. Genau dafür kommt `nachbearbeitet` dazu.
    """
    pfad = Path(kartenordner) / METADATEN
    try:
        meta = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        meta = {}
    meta["wegpunkte"] = len(graph.waypoints)
    meta["kanten"] = len(graph.edges)
    meta["nachbearbeitet"] = (jetzt or datetime.now(UTC)).isoformat()
    pfad.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def ersetze_inhalt(ziel, quelle):
    """`quelle` an die Stelle von `ziel` setzen — und `ziel` erst danach wegwerfen.

    Eine heruntergeladene Karte überschreibt die einzige Kopie der Aufnahme. Ein
    Abbruch mitten im Schreiben liesse den Schüler ohne beides zurück, deshalb
    wird nebenan geschrieben und erst am Schluss getauscht.
    """
    ziel, quelle = Path(ziel), Path(quelle)
    alt = ziel.with_name(ziel.name + ".alt")
    shutil.rmtree(alt, ignore_errors=True)
    if ziel.exists():
        ziel.rename(alt)
    try:
        quelle.rename(ziel)
    except OSError:
        if not ziel.exists() and alt.exists():
            alt.rename(ziel)            # zurueck auf den alten Stand
        raise
    shutil.rmtree(alt, ignore_errors=True)
    return ziel


def loesche(kartenordner):
    shutil.rmtree(Path(kartenordner), ignore_errors=True)


def wegpunkt_name(graph, kennung):
    """Der Name eines Wegpunkts -- oder '' -- oder SpotlabError, wenn es ihn nicht gibt."""
    for wp in graph.waypoints:
        if wp.id == kennung:
            return wp.annotations.name or ""
    raise SpotlabError(f"Den Wegpunkt '{kennung}' gibt es auf dieser Karte nicht.")


def benenne_wegpunkt(kartenordner, kennung, name):
    """Einen Wegpunkt der gespeicherten Karte nachträglich (um)benennen. Gibt den Namen zurück.

    Der Name ist eine Anmerkung im Graphen (`annotations.name`) -- dieselbe Stelle,
    die „Wegpunkt setzen" bei der Aufnahme beschreibt, und genau die liest
    `spot.navigate_to("kueche")` über `Map.id_fuer`. Das Format bleibt das des
    SDK; der Roboter bekommt den Namen beim nächsten `load_map` mit. Bereinigt wie
    bei der Aufnahme (`sicherer_name`: Leerzeichen und Satzzeichen werden `-`).
    Leer heisst: Name entfernen. Ein Name, den schon ein anderer Wegpunkt trägt,
    wird abgewiesen -- `id_fuer` nähme sonst stillschweigend den ersten.
    `graph` wird atomar ersetzt; die Metadaten zählen nur und bleiben.
    """
    ordner = Path(kartenordner)
    graph = lade_graph(ordner)
    wegpunkt_name(graph, kennung)                      # gibt es ihn?
    neu = sicherer_name(name or "", ersatz="")
    if neu:
        for wp in graph.waypoints:
            if wp.id != kennung and wp.annotations.name == neu:
                raise SpotlabError(
                    f"Den Namen '{neu}' trägt schon ein anderer Wegpunkt. Namen müssen "
                    f"eindeutig sein, sonst weiss navigate_to('{neu}') nicht, wohin.")
    for wp in graph.waypoints:
        if wp.id == kennung:
            wp.annotations.name = neu
    if not atomar.schreibe_atomar(ordner / "graph", graph.SerializeToString()):
        raise SpotlabError(
            "Die Karte liess sich nicht schreiben. Ist die Datei `graph` gerade in einem "
            "anderen Programm offen? Schliessen und noch einmal versuchen.")
    return neu
