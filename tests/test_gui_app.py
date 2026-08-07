import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.app import MainWindow  # noqa: E402


def test_navigation_wechselt_die_ansicht(qapp):
    fenster = MainWindow()
    fenster.leiste.knoepfe["laeufe"].click()
    assert fenster.stapel.currentWidget() is fenster.ansichten["laeufe"]


def test_notaus_der_kopfleiste_erreicht_die_live_ansicht(qapp, monkeypatch):
    gerufen = []
    fenster = MainWindow()
    monkeypatch.setattr(fenster.ansichten["live"], "notaus", lambda: gerufen.append(True))
    fenster.kopf.notaus_knopf.click()
    assert gerufen == [True]


def test_zustandssignal_erreicht_kopf_und_live(qapp, tmp_path):
    from spotlab.record.run import RunRecorder

    fenster = MainWindow()
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    fenster._lauf_begonnen(str(rec.dir))
    fenster._zustand(
        {"daten": {"battery": 55.0, "pose": [1.0, 0.0, 0.0],
                   "velocity": [0.2, 0.0, 0.0], "feet": [True] * 4}}
    )

    assert "55" in fenster.kopf.akku.text()
    assert "1.00" in fenster.ansichten["live"].kachel_pose.text()


def test_ohne_konfiguration_startet_die_spot_ansicht(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "gibtsnicht.toml")
    fenster = MainWindow()
    assert fenster.stapel.currentWidget() is fenster.ansichten["spot"]


def test_lauf_start_wechselt_zur_live_ansicht(qapp, tmp_path):
    class FakeProzess:
        stdout = None

        def wait(self):
            return 0

    fenster = MainWindow()
    fenster._lauf_gestartet(FakeProzess(), str(tmp_path / "x.py"))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_fehlermeldungen_landen_in_der_statuszeile(qapp):
    fenster = MainWindow()
    fenster._melde("Beobachter kaputt")
    assert "Beobachter kaputt" in fenster.statuszeile.text()


def test_fremd_gestarteter_lauf_schaltet_zur_live_ansicht(qapp, tmp_path):
    """Der F5-Fall aus Abnahmepunkt A11: der Schüler soll sehen, dass es läuft."""
    from spotlab.record.run import RunRecorder

    skript = tmp_path / "hallo_spot.py"
    skript.write_text("print(1)", encoding="utf-8")

    fenster = MainWindow()
    fenster.leiste.knoepfe["laeufe"].click()
    rec = RunRecorder(tmp_path / "runs", skript, backend="dryrun")
    fenster._lauf_begonnen(str(rec.dir))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_titel_zeigt_den_skriptnamen(qapp, tmp_path):
    from spotlab.record.run import RunRecorder

    skript = tmp_path / "hallo_spot.py"
    skript.write_text("print(1)", encoding="utf-8")
    rec = RunRecorder(tmp_path / "runs", skript, backend="dryrun")

    fenster = MainWindow()
    fenster._lauf_begonnen(str(rec.dir))
    assert "hallo_spot.py" in fenster.ansichten["live"].titel.text()


def test_gui_importiert_kein_bosdyn():
    """Entwurfsregel, nicht Stil: die GUI hält nie ein Lease.

    Ein import bosdyn im GUI-Code bricht die Grundsatzentscheidung H1.
    """
    import re
    from pathlib import Path

    import spotlab.gui

    wurzel = Path(spotlab.gui.__file__).parent
    muster = re.compile(r"^\s*(from|import)\s+(bosdyn|spotlab\.backends)", re.M)
    verstoesse = [
        str(p) for p in wurzel.rglob("*.py")
        if muster.search(p.read_text(encoding="utf-8"))
    ]
    assert verstoesse == []


def test_fenster_hat_jetzt_sieben_ansichten(qapp):
    fenster = MainWindow()
    assert set(fenster.ansichten) == {
        "projekte", "code", "live", "laeufe", "karten", "anbindungen", "spot"
    }
    assert fenster.stapel.count() == 7


# --------------------------------------------------------------- Ansicht „Code"


class _FakeProzess:
    """Eine Pipe, die sofort endet — der Leser darf nicht hängen bleiben."""

    stdout = ()

    def wait(self):
        return 0


def _lauf_verzeichnis(tmp_path):
    from spotlab.record.run import RunRecorder

    skript = tmp_path / "demo.py"
    skript.write_text("print(1)", encoding="utf-8")
    recorder = RunRecorder(tmp_path / "runs", skript, backend="dryrun")
    recorder.finish("ok")
    return str(recorder.dir)


def test_seitenleiste_hat_die_ansicht_code(qapp):
    from spotlab.gui.sidebar import EINTRAEGE

    assert ("code", "Code") in EINTRAEGE


def test_ein_leser_speist_beide_ansichten(qapp, tmp_path):
    """Zwei OutputReader auf derselben Pipe teilten sich die Zeilen zufällig auf."""
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._starte_leser(_FakeProzess())
    fenster._leser.zeile.emit("Akku: 87 %")
    assert "Akku: 87 %" in fenster.ansichten["code"].ausgabe.toPlainText()
    assert "Akku: 87 %" in fenster.ansichten["live"].ausgabe.toPlainText()


def test_lauf_aus_dem_editor_schaltet_nicht_um(qapp, tmp_path):
    fenster = MainWindow()
    fenster._wechsle("code")
    fenster._lauf_aus_code(_FakeProzess(), "egal.py")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["code"]


def test_lauf_von_aussen_schaltet_weiterhin_um(qapp, tmp_path):
    """F5 in VS Code: der Schüler soll sehen, dass sein Programm läuft."""
    fenster = MainWindow()
    fenster._wechsle("code")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_nach_dem_lauf_schaltet_ein_neuer_fremdlauf_wieder_um(qapp, tmp_path):
    fenster = MainWindow()
    fenster._wechsle("code")
    fenster._lauf_aus_code(_FakeProzess(), "egal.py")
    fenster._lauf_beendet(_lauf_verzeichnis(tmp_path))
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_stopp_aus_dem_editor_geht_an_die_live_ansicht(qapp):
    fenster = MainWindow()
    gerufen = []
    fenster.ansichten["live"].stoppe = lambda: gerufen.append(True)
    fenster.ansichten["code"].stopp_gewuenscht.emit()
    assert gerufen == [True]


def test_seitenleiste_hat_die_ansicht_anbindungen(qapp):
    from spotlab.gui.sidebar import EINTRAEGE

    assert ("anbindungen", "Anbindungen") in EINTRAEGE
    schluessel = [s for s, _ in EINTRAEGE]
    assert schluessel.index("anbindungen") < schluessel.index("spot")


def test_lauf_aus_anbindungen_schaltet_nicht_um(qapp, tmp_path):
    """Wer in „Anbindungen" startet, will die Panels sehen, nicht Telemetrie."""
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._wechsle("anbindungen")
    fenster._lauf_aus_anbindungen(_FakeProzess(), "egal.py")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["anbindungen"]


def test_lauf_aus_anbindungen_speist_die_ausgaben(qapp, tmp_path):
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._lauf_aus_anbindungen(_FakeProzess(), "egal.py")
    fenster._leser.zeile.emit("Fortschritt 3/20")
    assert "Fortschritt 3/20" in fenster.ansichten["live"].ausgabe.toPlainText()
    assert "Fortschritt 3/20" in fenster.ansichten["code"].ausgabe.toPlainText()


def test_arbeitsordner_erreicht_die_anbindungen(qapp, tmp_path):
    from spotlab.anbindung.manifest import DATEINAME
    from spotlab.anbindung.speicher import binde_an

    projekt = tmp_path / "fremd"
    projekt.mkdir()
    (projekt / "s.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(
        '[projekt]\nname = "fremd"\n\n[[skript]]\nname = "s"\ndatei = "s.py"\n',
        encoding="utf-8",
    )
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    binde_an(arbeit, projekt)

    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(arbeit))
    assert fenster.ansichten["anbindungen"].liste.count() == 1


def test_projekt_in_spotlab_oeffnen_wechselt_zur_code_ansicht(qapp, tmp_path):
    projekt = tmp_path / "demo"
    (projekt / "runs").mkdir(parents=True)
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster.ansichten["projekte"].projektliste.setCurrentRow(0)
    fenster.ansichten["projekte"].spotlab_knopf.click()
    assert fenster.stapel.currentWidget() is fenster.ansichten["code"]
    assert fenster.ansichten["code"].projektwahl.currentText() == "demo"


def test_aktive_karte_wird_gemerkt(qapp, tmp_path, monkeypatch):
    from spotlab.config import Config, Limits, load_config, save_config

    pfad = tmp_path / "config.toml"
    save_config(Config(ip="1.2.3.4", username="u", limits=Limits()), pfad)
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    fenster = MainWindow()
    fenster._merke_aktive_karte("turnhalle")
    assert load_config(pfad).active_map == "turnhalle"
