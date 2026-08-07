import json

import pytest
from bosdyn.api.graph_nav import map_pb2

from spotlab.errors import SpotlabError
from spotlab.maps.store import (
    MapInfo,
    finde,
    karten,
    karten_wurzel,
    lade_graph,
    loesche,
    sicherer_name,
    speichere_metadaten,
)


def _graph(n=3):
    graph = map_pb2.Graph()
    for i in range(n):
        wp = graph.waypoints.add()
        wp.id = f"wp{i}"
    for i in range(n - 1):
        kante = graph.edges.add()
        kante.id.from_waypoint = f"wp{i}"
        kante.id.to_waypoint = f"wp{i + 1}"
    return graph


def _lege_an(workspace, name, n=3):
    ordner = karten_wurzel(workspace) / name
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(_graph(n).SerializeToString())
    speichere_metadaten(ordner, name, "SN-1", _graph(n))
    return ordner


def test_wurzel_heisst_karten(tmp_path):
    assert karten_wurzel(tmp_path).name == "karten"


def test_namen_werden_entschaerft():
    assert "/" not in sicherer_name("Turn/Halle")
    assert sicherer_name("  ") == "karte"


def test_karte_wird_gefunden_und_beschrieben(tmp_path):
    _lege_an(tmp_path, "turnhalle", n=4)
    liste = karten(tmp_path)
    assert len(liste) == 1
    eintrag = liste[0]
    assert isinstance(eintrag, MapInfo)
    assert eintrag.name == "turnhalle"
    assert eintrag.wegpunkte == 4
    assert eintrag.kanten == 3
    assert eintrag.roboter == "SN-1"


def test_leerer_arbeitsordner(tmp_path):
    assert karten(tmp_path) == []


def test_fehlender_kartenordner(tmp_path):
    assert karten(tmp_path / "gibtsnicht") == []


def test_beschaedigte_metadaten_machen_die_karte_nicht_unbrauchbar(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle", n=5)
    (ordner / "karte.json").write_text("{kaputt", encoding="utf-8")

    eintrag = karten(tmp_path)[0]
    assert eintrag.name == "turnhalle"
    assert eintrag.wegpunkte == 5  # aus dem Graphen zurückgefallen


def test_graph_wird_gelesen(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle", n=2)
    assert len(lade_graph(ordner).waypoints) == 2


def test_finde_liefert_den_ordner(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle")
    assert finde(tmp_path, "turnhalle") == ordner


def test_finde_zaehlt_vorhandene_auf(tmp_path):
    _lege_an(tmp_path, "turnhalle")
    _lege_an(tmp_path, "aula")
    with pytest.raises(SpotlabError) as info:
        finde(tmp_path, "keller")
    assert "turnhalle" in str(info.value) and "aula" in str(info.value)


def test_finde_ohne_jede_karte(tmp_path):
    with pytest.raises(SpotlabError) as info:
        finde(tmp_path, "keller")
    assert "keine" in str(info.value).lower()


def test_loeschen_entfernt_alles(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle")
    loesche(ordner)
    assert not ordner.exists()
    assert karten(tmp_path) == []


def test_metadaten_sind_lesbares_json(tmp_path):
    ordner = _lege_an(tmp_path, "turnhalle", n=3)
    daten = json.loads((ordner / "karte.json").read_text(encoding="utf-8"))
    assert daten["name"] == "turnhalle"
    assert daten["wegpunkte"] == 3
    assert daten["spotlab_version"]
