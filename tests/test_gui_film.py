"""Der Knopf „Video speichern": im Uebungsfenster nach dem Lauf, in „Laeufe" fuer alte.

Die GUI rendert nichts selbst (kein MuJoCo unter gui/): sie startet
`spotlab film <lauf>` als Unterprozess und zeigt an, was der zurueckmeldet.
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.app import MainWindow  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.gui.uebungsfenster import Uebungsfenster  # noqa: E402
from spotlab.gui.views.runs import RunsView  # noqa: E402
from spotlab.welt.raum import raum_laden  # noqa: E402


def test_der_videoknopf_erscheint_erst_wenn_der_lauf_fertig_ist(qapp, tmp_path):
    fenster = Uebungsfenster(DUNKEL)
    fenster.beginne(raum_laden("leer"), (1.0, 1.0, 0.0))
    assert fenster.video.isHidden()
    fenster.beendet(lauf=tmp_path)
    assert not fenster.video.isHidden()


def test_der_videoknopf_meldet_den_lauf(qapp, tmp_path):
    fenster = Uebungsfenster(DUNKEL)
    fenster.beendet(lauf=tmp_path)
    gewuenscht = []
    fenster.video_gewuenscht.connect(gewuenscht.append)
    fenster.video.click()
    assert gewuenscht == [str(tmp_path)]


def test_der_stand_des_videos_steht_in_der_zeile(qapp, tmp_path):
    fenster = Uebungsfenster(DUNKEL)
    fenster.beendet(lauf=tmp_path)
    fenster.zeige_video_stand("Video wird gerendert…")
    assert "gerendert" in fenster.zeile.text()
    assert fenster.video_oeffnen.isHidden()
    fenster.zeige_video_stand("Video: film.mp4", pfad=tmp_path / "film.mp4")
    assert not fenster.video_oeffnen.isHidden()


def test_die_laeufe_ansicht_hat_den_knopf_fuer_alte_laeufe(qapp, tmp_path):
    from spotlab.record.run import RunRecorder

    projekt = tmp_path / "demo"
    (projekt / "runs").mkdir(parents=True)
    (projekt / "x.py").write_text("print(1)" + chr(10), encoding="utf-8")
    rec = RunRecorder(projekt / "runs", projekt / "x.py", backend="sim")
    rec.sample({"battery": 90.0})
    rec.finish("ok")

    ansicht = RunsView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    assert not ansicht.video.isEnabled(), "ohne Auswahl gibt es nichts zu rendern"
    ansicht.tabelle.selectRow(0)
    assert ansicht.video.isEnabled()
    gewuenscht = []
    ansicht.video_gewuenscht.connect(gewuenscht.append)
    ansicht.video.click()
    assert gewuenscht == [str(rec.dir)]


def test_das_hauptfenster_startet_den_unterprozess(qapp, tmp_path, monkeypatch):
    """Delegation an `spotlab film`: die GUI importiert kein MuJoCo."""
    fenster = MainWindow()
    gestartet = []
    monkeypatch.setattr(fenster, "_starte_film", lambda lauf: gestartet.append(lauf))
    fenster.ansichten["laeufe"].video_gewuenscht.emit(str(tmp_path))
    assert gestartet == [str(tmp_path)]


def test_die_rueckmeldung_des_unterprozesses_erreicht_das_fenster(qapp, tmp_path):
    fenster = MainWindow()
    fenster._oeffne_uebungsfenster("x.py")
    fenster.uebungsfenster.beendet(lauf=tmp_path)
    (tmp_path / "film.mp4").write_bytes(b"\x00")
    fenster._film_fertig(str(tmp_path), 0, f"Bilder: 45\nVideo: {tmp_path / 'film.mp4'}\n")
    assert "film.mp4" in fenster.statuszeile.text()
    assert not fenster.uebungsfenster.video_oeffnen.isHidden()


def test_ein_gescheiterter_unterprozess_sagt_warum(qapp, tmp_path):
    fenster = MainWindow()
    fenster._film_fertig(str(tmp_path), 1, "Das Menagerie-Modell des Spot fehlt\n")
    assert "Menagerie" in fenster.statuszeile.text()
