import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.theme import DUNKEL  # noqa: E402
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


# ================================ S2.8 / S2.9 / S2.13 Laeufe-Ansicht
#
# S2.8: Laeufe angebundener Fremdprojekte liegen unter <skriptordner>/runs, also
# ausserhalb des Arbeitsordners. `projekte_in()` findet sie nicht -- genau der
# Fehler aus Stufe 3 in neuem Gewand, den CLAUDE.md benennt und den zwei
# unabhaengige Suchergruppen wiederentdeckt haben.


def _fremdes_projekt(tmp_path, arbeitsordner):
    """Ein angebundenes Projekt, dessen Laeufe AUSSERHALB des Arbeitsordners liegen."""
    from spotlab.anbindung.manifest import DATEINAME
    from spotlab.anbindung.speicher import binde_an
    from spotlab.record.run import RunRecorder

    fremd = tmp_path / "fremd"
    (fremd / "scripts").mkdir(parents=True)
    skript = fremd / "scripts" / "lauf.py"
    skript.write_text("x = 1\n", encoding="utf-8")
    (fremd / DATEINAME).write_text(
        '[projekt]\nname = "fremd"\n\n[[skript]]\n'
        'name = "Lauf"\ndatei = "scripts/lauf.py"\nroboter = false\n',
        encoding="utf-8",
    )
    binde_an(arbeitsordner, fremd)
    RunRecorder(fremd / "scripts" / "runs", skript, backend="dryrun").finish("ok")
    return fremd


def test_laeufe_angebundener_projekte_erscheinen(qapp, tmp_path):
    from spotlab.gui.views.runs import RunsView

    arbeitsordner = tmp_path / "werkstatt"
    (arbeitsordner / "eigen" / "runs").mkdir(parents=True)
    _fremdes_projekt(tmp_path, arbeitsordner)

    ansicht = RunsView(DUNKEL) if _nimmt_palette() else RunsView()
    ansicht.setze_arbeitsordner(arbeitsordner)
    assert ansicht.tabelle.rowCount() >= 1, "kein Lauf des angebundenen Projekts"


def _nimmt_palette():
    import inspect

    from spotlab.gui.views.runs import RunsView

    return "palette" in inspect.signature(RunsView.__init__).parameters


def test_die_ansicht_nimmt_eine_palette(qapp):
    """S2.13: auf Windows-Standard `hell` sind die Beschriftungen im Diagramm
    sonst praktisch unlesbar -- das trifft die Mehrheit der Schullaptops."""
    assert _nimmt_palette(), "RunsView reicht die Palette nicht durch"


def test_die_kurve_bekommt_die_palette(qapp):
    from spotlab.gui.theme import HELL
    from spotlab.gui.views.runs import RunsView

    ansicht = RunsView(HELL)
    assert ansicht.kurve.palette_ is HELL


def test_die_ereignisliste_zeigt_das_ergebnis(qapp, tmp_path):
    """S2.9: bei `ende`, `bild` und `lease_übernommen` blieb die Beschreibung
    leer -- ausgerechnet dort, wo Erfolg oder Fehlertext staende."""
    from spotlab.record.run import RunRecorder

    projekt = create_project("demo", tmp_path)
    rec = RunRecorder(projekt / "runs", None, backend="dryrun")
    rec.event("bild", pfad="bilder/000.png")
    rec.event("lease_übernommen", von="Tablet")
    rec.finish("fehler", "Kontrolle verloren")

    ansicht = RunsView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.tabelle.selectRow(0)
    texte = [
        ansicht.ereignisliste.item(i).text()
        for i in range(ansicht.ereignisliste.count())
    ]
    zusammen = " | ".join(texte)
    assert "fehler" in zusammen, zusammen
    assert "Kontrolle verloren" in zusammen, zusammen
    assert "Tablet" in zusammen, zusammen
    assert "000.png" in zusammen, zusammen
