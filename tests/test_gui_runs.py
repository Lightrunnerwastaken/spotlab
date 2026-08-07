import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.views.runs import RunsView, tempo_reihen  # noqa: E402
from spotlab.record.run import RunRecorder  # noqa: E402
from spotlab.workshop.project import create_project  # noqa: E402


def _lauf_mit_fahrt(runs_dir):
    rec = RunRecorder(runs_dir, None, backend="dryrun")
    rec.event("kommando", name="walk", vx=0.3, vy=0.0, wz=0.0, duration=2.0)
    for tempo in (0.0, 0.15, 0.29):
        rec.sample({"battery": 90.0, "velocity": [tempo, 0.0, 0.0]})
    rec.finish("ok")
    return rec.dir


def test_gemessene_reihe_kommt_aus_dem_zustand(tmp_path):
    gemessen, _ = tempo_reihen(_lauf_mit_fahrt(tmp_path))
    assert [round(v, 2) for _, v in gemessen] == [0.0, 0.15, 0.29]


def test_kommandierte_reihe_kommt_aus_den_ereignissen(tmp_path):
    _, kommandiert = tempo_reihen(_lauf_mit_fahrt(tmp_path))
    assert kommandiert
    assert all(abs(v - 0.3) < 1e-9 for _, v in kommandiert)


def test_lauf_ohne_fahrt_hat_leere_kommandoreihe(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    rec.sample({"battery": 90.0, "velocity": [0.0, 0.0, 0.0]})
    rec.finish("ok")
    _, kommandiert = tempo_reihen(rec.dir)
    assert kommandiert == []


def test_fehlender_lauf_ergibt_leere_reihen(tmp_path):
    assert tempo_reihen(tmp_path / "gibtsnicht") == ([], [])


def test_ansicht_listet_laeufe(qapp, tmp_path):
    projekt = create_project("demo", tmp_path)
    _lauf_mit_fahrt(projekt / "runs")

    ansicht = RunsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.tabelle.rowCount() == 1
    assert ansicht.tabelle.item(0, 1).text() == "ok"


def test_ansicht_ohne_laeufe(qapp, tmp_path):
    ansicht = RunsView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.tabelle.rowCount() == 0


def test_auswahl_fuellt_die_kurve(qapp, tmp_path):
    projekt = create_project("demo", tmp_path)
    _lauf_mit_fahrt(projekt / "runs")

    ansicht = RunsView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.tabelle.selectRow(0)
    assert ansicht.kurve.gemessen


def test_kurve_zeichnet_ohne_daten(qapp):
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QWidget

    from spotlab.gui.views.runs import SpeedPlot

    kurve = SpeedPlot()
    kurve.resize(200, 100)
    kurve.render(QPixmap(200, 100))  # darf nicht werfen
    assert isinstance(kurve, QWidget)
