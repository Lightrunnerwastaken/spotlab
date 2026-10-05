"""Kein Test sieht die echte Konfiguration, den echten Arbeitsordner oder den Passwort-Tresor.

Bis zum 05.10.2026 las jedes `MainWindow()` im Test die `~/.spotlab/config.toml`
des Entwicklers und beobachtete dessen Arbeitsordner. Lief daneben die
Steuerzentrale am echten Spot, übernahm ein altes Testfenster diesen Lauf (23 000
Ereignisse, einzeln in die Live-Liste) und der Test hing bis zur 300-s-Grenze.
Über den Tab „Fahren" hätte es auch Dateien in das Lauf-Verzeichnis des echten
Roboters schreiben können. Und in der echten Datei steht `backend = "real"`: ein
Kindprozess, der `spotlab.connect()` ohne Backend ruft, hätte den Roboter gewählt.

Die Trennung macht `tests/conftest.py::_leeres_zuhause` für jeden Test; diese
Datei hält fest, dass sie greift.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from spotlab import config
from spotlab.errors import ConfigMissing
from tests_fenster import halte_beobachter_an
from tests_zeitgrenzen import TEST_TIMEOUT_S


def _unter(pfad, ordner):
    return Path(pfad).resolve().is_relative_to(Path(ordner).resolve())


def test_die_konfiguration_liegt_im_testlauf_unter_tmp(tmp_path_factory):
    assert _unter(config.CONFIG_PATH, tmp_path_factory.getbasetemp())


def test_load_config_liest_im_testlauf_nie_die_echte_datei():
    with pytest.raises(ConfigMissing):
        config.load_config()


def test_jeder_test_beginnt_ohne_konfiguration(tmp_path_factory):
    """Ein Test, der speichert, hinterlässt dem nächsten nichts."""
    # Zuerst prüfen, dann schreiben: ohne Trennung wäre das die echte Datei.
    assert _unter(config.CONFIG_PATH, tmp_path_factory.getbasetemp())
    config.save_config(config.Config(ip="10.0.0.3", username="admin"))
    assert config.load_config().ip == "10.0.0.3"


def test_jeder_test_beginnt_ohne_konfiguration_auch_der_naechste():
    assert not config.CONFIG_PATH.exists()


def test_der_benutzerordner_liegt_im_testlauf_unter_tmp(tmp_path_factory):
    assert _unter(Path.home(), tmp_path_factory.getbasetemp())


def test_auch_kindprozesse_sehen_den_leeren_benutzerordner(tmp_path_factory):
    """Ein Skript, das die Tests als eigenen Prozess starten, liest seine
    Konfiguration selbst -- `monkeypatch.setattr` erreicht es nicht."""
    aus = subprocess.run(
        [sys.executable, "-c", "from pathlib import Path; print(Path.home())"],
        capture_output=True, text=True, check=True, timeout=TEST_TIMEOUT_S,
    )
    assert _unter(aus.stdout.strip(), tmp_path_factory.getbasetemp())


def test_der_passwort_tresor_ist_im_testlauf_leer():
    """Auch im Kindprozess: die Variable erbt er."""
    keyring = pytest.importorskip("keyring")
    assert type(keyring.get_keyring()).__module__ == "keyring.backends.null"
    aus = subprocess.run(
        [sys.executable, "-c",
         "import keyring; print(type(keyring.get_keyring()).__module__)"],
        capture_output=True, text=True, check=True, timeout=TEST_TIMEOUT_S,
    )
    assert aus.stdout.strip() == "keyring.backends.null"


def test_die_erkennermodelle_bleiben_die_echten(tmp_path_factory):
    """Mit Absicht: die Modelle werden nur gelesen. Zeigte `MODELL_ORDNER` in den
    leeren Benutzerordner, würden die Modelltests still übersprungen."""
    pytest.importorskip("bosdyn.client")
    from spotlab.backends.real import gesicht, gesten, koerper

    for modul in (gesicht, gesten, koerper):
        assert not _unter(modul.MODELL_ORDNER, tmp_path_factory.getbasetemp()), modul


def test_ein_neues_hauptfenster_beobachtet_keinen_arbeitsordner(qapp):
    """Genau der Weg vom 05.10.2026: Konfiguration -> Arbeitsordner -> RunWatcher."""
    from spotlab.gui.app import MainWindow

    fenster = MainWindow()
    assert fenster._watcher is None


def test_nach_dem_test_beobachtet_kein_altes_fenster_mehr(qapp, tmp_path):
    """Fenster aus früheren Tests leben weiter (Referenzzyklen); ihre Beobachter
    liefen in jedem späteren `processEvents()` mit."""
    from spotlab.gui.app import MainWindow

    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    assert fenster._watcher._timer.isActive()

    halte_beobachter_an()

    assert not fenster._watcher._timer.isActive()
    assert not fenster._watcher._live_timer.isActive()
