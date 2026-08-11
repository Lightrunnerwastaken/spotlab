import pytest

pytest.importorskip("PySide6.QtWidgets")

from bosdyn.api.graph_nav import map_pb2  # noqa: E402

from spotlab.gui.views.maps import MapsView  # noqa: E402
from spotlab.maps.store import karten_wurzel, speichere_metadaten  # noqa: E402


def _graph():
    graph = map_pb2.Graph()
    for kennung, name in (("wp0", "start"), ("wp1", "kueche")):
        wp = graph.waypoints.add()
        wp.id = kennung
        wp.annotations.name = name
    kante = graph.edges.add()
    kante.id.from_waypoint = "wp0"
    kante.id.to_waypoint = "wp1"
    for kennung, x in (("wp0", 0.0), ("wp1", 2.0)):
        anker = graph.anchoring.anchors.add()
        anker.id = kennung
        anker.seed_tform_waypoint.rotation.w = 1.0
        anker.seed_tform_waypoint.position.x = x
    return graph


def _karte(tmp_path, name="turnhalle"):
    ordner = karten_wurzel(tmp_path) / name
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(_graph().SerializeToString())
    speichere_metadaten(ordner, name, "SN-1", _graph())
    return ordner


def test_liste_zeigt_die_karten(qapp, tmp_path):
    _karte(tmp_path)
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.liste.count() == 1
    assert "turnhalle" in ansicht.liste.item(0).text()


def test_ohne_karten_bleibt_die_liste_leer(qapp, tmp_path):
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.liste.count() == 0


def test_auswahl_zeichnet_die_draufsicht(qapp, tmp_path):
    _karte(tmp_path)
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.liste.setCurrentRow(0)
    assert len(ansicht.plot.grundriss.punkte) == 2
    assert ansicht.plot.grundriss.quelle == "anker"


def test_als_aktiv_setzen_meldet_den_namen(qapp, tmp_path):
    _karte(tmp_path)
    gewaehlt = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.aktive_karte_gewaehlt.connect(gewaehlt.append)
    ansicht.liste.setCurrentRow(0)
    ansicht.aktiv_knopf.click()
    assert gewaehlt == ["turnhalle"]


def test_als_aktiv_ohne_auswahl_tut_nichts(qapp, tmp_path):
    gewaehlt = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.aktive_karte_gewaehlt.connect(gewaehlt.append)
    ansicht.aktiv_knopf.click()
    assert gewaehlt == []


def test_aufnahme_ohne_konfiguration_meldet_klartext(qapp, tmp_path):
    meldungen = []
    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.meldung.connect(meldungen.append)
    ansicht.start_knopf.click()
    assert meldungen and "eingerichtet" in meldungen[0].lower()


def test_hinweis_auf_tablet_und_fiducial_steht_da(qapp):
    ansicht = MapsView()
    text = ansicht.hinweis.text().lower()
    assert "fiducial" in text
    assert "tablet" in text


def test_status_fuellt_die_anzeige(qapp, tmp_path):
    from spotlab.maps.session import RecordingStatus

    ansicht = MapsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht._zeige_status(RecordingStatus(True, 12, 11, "Aufnahme läuft"))
    assert "12" in ansicht.aufnahme_status.text()


def test_die_kartenansicht_reicht_die_palette_durch(qapp):
    """S2.13: auf der Windows-Vorgabe `hell` sind die Wegpunktnamen sonst
    praktisch unlesbar -- Kontrast rund 1.3:1 auf der Mehrheit der Schullaptops."""
    from spotlab.gui.theme import HELL
    from spotlab.gui.views.maps import MapsView

    ansicht = MapsView(HELL)
    assert ansicht.plot.palette_ is HELL


def test_das_fenster_gibt_beiden_diagrammen_seine_palette(qapp):
    from spotlab.gui.app import MainWindow

    fenster = MainWindow()
    assert fenster.ansichten["karten"].plot.palette_ is fenster._palette
    assert fenster.ansichten["laeufe"].kurve.palette_ is fenster._palette
