"""Karten auf der Platte — im Format des SDK.

graph, waypoint_snapshots/ und edge_snapshots/ schreibt
GraphNavClient.write_graph_and_snapshots; daran ändern wir nichts. Nur
karte.json kommt dazu, mit dem, was das SDK nicht speichert.

Der Grund für dieses Format ist Austauschbarkeit: eine mit spotlab
aufgezeichnete Karte lässt sich unverändert an graph_nav_command_line.py und
view_map.py verfüttern — und umgekehrt.
"""

import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from google.protobuf.message import DecodeError
from bosdyn.api.graph_nav import map_pb2

from spotlab.errors import SpotlabError
from spotlab.pfade import sicherer_name  # noqa: F401  (Re-Export, historischer Pfad)

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


def loesche(kartenordner):
    shutil.rmtree(Path(kartenordner), ignore_errors=True)
