import os
import sys
from pathlib import Path

# Muss vor dem ersten PySide6-Import stehen: Qt-Tests laufen ohne Bildschirm.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Kein Test erreicht den echten Passwort-Tresor -- auch kein Kindprozess, der die
# Umgebung erbt. Hier und nicht in der Fixture: keyring wählt seinen Speicher beim
# ersten Gebrauch und behält ihn für den ganzen Prozess.
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"

import pytest  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tests_fenster import halte_beobachter_an  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """Eine QApplication pro Testlauf — mehrere gleichzeitig sind nicht erlaubt."""
    pyside = pytest.importorskip("PySide6.QtWidgets")
    app = pyside.QApplication.instance() or pyside.QApplication([])
    yield app


@pytest.fixture(scope="session", autouse=True)
def _echte_erkennermodelle():
    """Die Erkennermodelle bleiben mit Absicht die echten -- sie werden nur gelesen.

    `MODELL_ORDNER` entsteht beim Import aus `Path.home()`. Käme der erste Import
    erst in einem Test, unter dem umgebogenen Benutzerordner von `_leeres_zuhause`,
    zeigte er für den Rest des Laufs in einen leeren tmp-Ordner, und die
    Modelltests würden still übersprungen. Deshalb einmal vorab, solange
    `Path.home()` noch der echte ist.
    """
    try:
        import spotlab.backends.real.gesicht  # noqa: F401
    except ImportError:
        pass  # ohne Spot-SDK gibt es auch keine Modelltests
    yield


@pytest.fixture(autouse=True)
def _leeres_zuhause(_echte_erkennermodelle, tmp_path_factory, monkeypatch):
    """Jeder Test bekommt einen leeren Benutzerordner und eine leere Konfiguration.

    Bis zum 05.10.2026 las jedes `MainWindow()` die echte `~/.spotlab/config.toml`
    und beobachtete den echten Arbeitsordner; ein altes Testfenster übernahm so
    einen Lauf am echten Spot. In der echten Datei steht ausserdem
    `backend = "real"`. `CONFIG_PATH` für diesen Prozess, `USERPROFILE`/`HOME`
    für jeden Kindprozess, den ein Test startet. Ein eigener Ordner statt
    `tmp_path`: Tests, die ihren `tmp_path` auflisten, sähen sonst `.spotlab`.
    """
    zuhause = tmp_path_factory.mktemp("zuhause")
    monkeypatch.setenv("USERPROFILE", str(zuhause))
    monkeypatch.setenv("HOME", str(zuhause))
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", zuhause / ".spotlab" / "config.toml")
    yield
    halte_beobachter_an()
