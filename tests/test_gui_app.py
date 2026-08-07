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


def test_fenster_hat_jetzt_fuenf_ansichten(qapp):
    fenster = MainWindow()
    assert set(fenster.ansichten) == {"projekte", "live", "laeufe", "karten", "spot"}
    assert fenster.stapel.count() == 5


def test_aktive_karte_wird_gemerkt(qapp, tmp_path, monkeypatch):
    from spotlab.config import Config, Limits, load_config, save_config

    pfad = tmp_path / "config.toml"
    save_config(Config(ip="1.2.3.4", username="u", limits=Limits()), pfad)
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    fenster = MainWindow()
    fenster._merke_aktive_karte("turnhalle")
    assert load_config(pfad).active_map == "turnhalle"
