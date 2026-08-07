import os
import sys
from pathlib import Path

# Muss vor dem ersten PySide6-Import stehen: Qt-Tests laufen ohne Bildschirm.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def qapp():
    """Eine QApplication pro Testlauf — mehrere gleichzeitig sind nicht erlaubt."""
    pyside = pytest.importorskip("PySide6.QtWidgets")
    app = pyside.QApplication.instance() or pyside.QApplication([])
    yield app
