import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.views.projects import ProjectsView, projekte_in  # noqa: E402
from spotlab.workshop.project import create_project  # noqa: E402


def test_projekte_werden_erkannt(tmp_path):
    create_project("a", tmp_path)
    create_project("b", tmp_path)
    (tmp_path / "kein-projekt").mkdir()
    assert [p.name for p in projekte_in(tmp_path)] == ["a", "b"]


def test_leerer_ordner(tmp_path):
    assert projekte_in(tmp_path) == []


def test_fehlender_ordner(tmp_path):
    assert projekte_in(tmp_path / "gibtsnicht") == []


def test_ansicht_listet_projekte_und_skripte(qapp, tmp_path):
    create_project("demo", tmp_path)
    ansicht = ProjectsView()
    ansicht.setze_arbeitsordner(tmp_path)

    assert ansicht.projektliste.count() == 1
    ansicht.projektliste.setCurrentRow(0)
    namen = [ansicht.skriptliste.item(i).text() for i in range(ansicht.skriptliste.count())]
    assert "hallo_spot.py" in namen


def test_starten_reicht_trockenlauf_durch(qapp, tmp_path, monkeypatch):
    create_project("demo", tmp_path)
    gerufen = {}

    def fake_start(pfad, dryrun=False, **kw):
        gerufen["pfad"], gerufen["dryrun"] = pfad, dryrun
        return object()

    monkeypatch.setattr("spotlab.gui.views.projects.start_script", fake_start)

    ansicht = ProjectsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.projektliste.setCurrentRow(0)
    ansicht.skriptliste.setCurrentRow(0)
    ansicht.trockenlauf.setChecked(True)
    ansicht.starten_knopf.click()

    assert gerufen["dryrun"] is True
    assert str(gerufen["pfad"]).endswith("hallo_spot.py")


def test_starten_ohne_auswahl_tut_nichts(qapp, tmp_path, monkeypatch):
    gerufen = []
    monkeypatch.setattr(
        "spotlab.gui.views.projects.start_script", lambda *a, **k: gerufen.append(a)
    )
    ansicht = ProjectsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.starten_knopf.click()
    assert gerufen == []


def test_sidebar_meldet_die_wahl(qapp):
    from spotlab.gui.sidebar import Sidebar

    gewaehlt = []
    leiste = Sidebar()
    leiste.gewaehlt.connect(gewaehlt.append)
    leiste.knoepfe["laeufe"].click()
    assert gewaehlt == ["laeufe"]


def test_starten_ohne_auswahl_meldet_klartext(qapp, tmp_path):
    """Bisher kehrte _starte wortlos zurueck -- der Knopf sah kaputt aus.

    Ueber ein Signal, nicht ueber QMessageBox: ein modaler Dialog blockiert den
    Test fuer immer, weil ihn offscreen niemand wegklickt. Genau darauf bin ich
    beim ersten Versuch hereingefallen.
    """
    from spotlab.gui.views.projects import ProjectsView

    ansicht = ProjectsView()
    ansicht.setze_arbeitsordner(tmp_path)
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)

    ansicht.starte_aktuelles()
    assert gemeldet and "Skript" in gemeldet[0]
