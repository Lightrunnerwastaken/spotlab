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
    # Der Rueckfallname ist Sache des Aufrufers, seit die Funktion in pfade.py
    # liegt und auch die Anbindung sie benutzt.
    assert sicherer_name("  ", ersatz="karte") == "karte"


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


# ============================== S1.11 eine kaputte Karte blockiert den Start
#
# `karten()` beschreibt jeden Ordner in einer Listcomprehension, und
# `_beschreibe` fing um `lade_graph` nur OSError. Eine beschaedigte `graph`-Datei
# wirft aber DecodeError -- der flog aus `karten()` heraus, und weil die
# Kartenansicht beim Programmstart fuellt, startete die GANZE GUI nicht mehr.
# Damit war auch der NOT-AUS-Knopf unerreichbar.


def _karte(wurzel, name, inhalt=b"", meta=True):
    import json

    from spotlab.maps.store import KARTEN_ORDNER, METADATEN

    ordner = wurzel / KARTEN_ORDNER / name
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "graph").write_bytes(inhalt)
    if meta:
        (ordner / METADATEN).write_text(
            json.dumps({"name": name, "wegpunkte": 3, "kanten": 2}), encoding="utf-8"
        )
    return ordner


def test_kaputte_graph_datei_wirft_nicht(tmp_path):
    from spotlab.maps.store import karten

    _karte(tmp_path, "kaputt", inhalt=b"\xff\xfe kein protobuf", meta=False)
    liste = karten(tmp_path)          # darf nicht werfen
    assert [k.name for k in liste] == ["kaputt"]
    assert liste[0].wegpunkte == 0, "erfundene Zahlen waeren schlimmer als 0"


def test_eine_kaputte_karte_reisst_die_anderen_nicht_mit(tmp_path):
    """Der eigentliche Schaden: die ganze Liste war weg, nicht nur die eine."""
    from spotlab.maps.store import karten

    _karte(tmp_path, "kaputt", inhalt=b"\xff\xfe kein protobuf", meta=False)
    _karte(tmp_path, "heil")
    namen = {k.name for k in karten(tmp_path)}
    assert namen == {"kaputt", "heil"}


def test_ein_unlesbarer_ordner_reisst_die_liste_nicht_mit(tmp_path, monkeypatch):
    from spotlab.maps import store

    _karte(tmp_path, "heil")
    _karte(tmp_path, "sperrig")

    echt = store._beschreibe

    def stolpert(ordner):
        if ordner.name == "sperrig":
            raise OSError("Zugriff verweigert")
        return echt(ordner)

    monkeypatch.setattr(store, "_beschreibe", stolpert)
    assert [k.name for k in store.karten(tmp_path)] == ["heil"]


# ---------------------------------------------------------- Benennen


def _karte_mit_graph(tmp_path, graph):
    ordner = karten_wurzel(tmp_path) / "flur"
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(graph.SerializeToString())
    speichere_metadaten(ordner, "flur", "SN-1", graph)
    return ordner


def test_ein_wegpunkt_bekommt_nachtraeglich_einen_namen(tmp_path):
    """Im SDK-Format, an derselben Stelle wie bei der Aufnahme: der Graph selbst."""
    from spotlab.maps.store import benenne_wegpunkt, wegpunkt_name

    ordner = _karte_mit_graph(tmp_path, _graph())
    assert benenne_wegpunkt(ordner, "wp1", "Küche links") == "Küche-links"
    graph = lade_graph(ordner)
    assert wegpunkt_name(graph, "wp1") == "Küche-links" and wegpunkt_name(graph, "wp0") == ""
    assert len(graph.waypoints) == 3 and len(graph.edges) == 2, "sonst nichts angefasst"
    assert not list(ordner.glob("*.tmp")), "atomar ersetzt"
    assert karten(tmp_path)[0].wegpunkte == 3


def test_leer_entfernt_den_namen_und_fremde_kennungen_werden_abgewiesen(tmp_path):
    from spotlab.maps.store import benenne_wegpunkt, wegpunkt_name

    ordner = _karte_mit_graph(tmp_path, _graph())
    benenne_wegpunkt(ordner, "wp1", "kueche")
    assert benenne_wegpunkt(ordner, "wp1", "   ") == ""
    assert wegpunkt_name(lade_graph(ordner), "wp1") == ""
    with pytest.raises(SpotlabError, match="gibt es auf dieser Karte nicht"):
        benenne_wegpunkt(ordner, "wp9", "x")


def test_ein_doppelter_name_wird_abgewiesen(tmp_path):
    """`id_fuer` naehme sonst stillschweigend den ersten -- und Spot fuehre woandershin."""
    from spotlab.maps.store import benenne_wegpunkt, wegpunkt_name

    ordner = _karte_mit_graph(tmp_path, _graph())
    benenne_wegpunkt(ordner, "wp0", "kueche")
    with pytest.raises(SpotlabError, match="schon ein anderer Wegpunkt"):
        benenne_wegpunkt(ordner, "wp1", "kueche")
    assert wegpunkt_name(lade_graph(ordner), "wp1") == ""
    assert benenne_wegpunkt(ordner, "wp0", "kueche") == "kueche", "derselbe Name am selben Punkt geht"
