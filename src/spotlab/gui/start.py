"""Der Start der Oberfläche: zuerst das Ladebild, der Rest im Hintergrund.

Kalt, gleich nach dem Hochfahren, brauchte spotlab am 23.09.2026 17 s bis zum
Fenster -- 17 s, in denen nichts zu sehen war und man ein zweites Mal klickte.
Jetzt steht nach einem Bruchteil davon das Ladebild, und der schwere Import
(`spotlab.gui.app` mit allen Ansichten) läuft in einem eigenen Faden, damit
die Animation weiterläuft. Gebaut wird das Fenster danach im GUI-Thread: Qt
erlaubt Widgets nur dort.

Ist das Fenster da, lädt `vorwaermen` im Hintergrund, was die GUI erst beim
ersten Gebrauch braucht (Spot-SDK, Passwort-Tresor, jedi). Sonst hinge der
erste Klick auf „Karten“ oder der erste Vorschlag im Editor eine Sekunde.

Dieses Modul lädt selbst nur PySide6 und das Ladebild.
"""

import importlib
import sys
import threading

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from spotlab import __version__
from spotlab.gui.ladebild import Ladebild
from spotlab.gui.symbol import symbol

# Was die GUI erst beim ersten Gebrauch braucht, in der Reihenfolge des Nutzens.
VORWAERMEN = ("bosdyn.client", "jedi", "keyring")
VORWAERMEN_NACH_MS = 1500


class _Lader(QThread):
    def __init__(self, lade, parent=None):
        super().__init__(parent)
        self._lade = lade
        self.ausnahme = None

    def run(self):
        try:
            self._lade()
        except BaseException as fehler:     # noqa: BLE001 -- jede Ursache wird gemeldet
            self.ausnahme = fehler


class Start(QObject):
    """Ladebild zeigen, `lade()` im Hintergrund, dann `baue()` im GUI-Thread.

    `melde_fehler(ausnahme)` bekommt, woran das Laden scheiterte; gebaut wird
    dann nichts. `fenster` hält, was `baue()` zurückgab; `fertig` meldet es.
    """

    fertig = Signal()

    def __init__(self, lade, baue, melde_fehler, version=__version__, parent=None):
        super().__init__(parent)
        self._baue = baue
        self._melde_fehler = melde_fehler
        self.fenster = None
        self.bild = Ladebild(version)
        self._lader = _Lader(lade, self)
        self._lader.finished.connect(self._geladen)

    def los(self):
        self.bild.melde("Lade Oberfläche …")
        self.bild.zeige()
        self._lader.start()

    def _geladen(self):
        ausnahme = self._lader.ausnahme
        if ausnahme is not None:
            self.bild.close()
            self._melde_fehler(ausnahme)
            return
        self.bild.melde("Baue Fenster …")
        self.bild.repaint()
        try:
            self.fenster = self._baue()
        except Exception as fehler:     # noqa: BLE001 -- sonst stuende das Ladebild ewig
            self.bild.close()
            self._melde_fehler(fehler)
            return
        self.bild.ausblenden()
        self.fertig.emit()


def lade_gui():
    import spotlab.gui.app  # noqa: F401 -- der schwere Teil, im Hintergrund


def baue_gui():
    from spotlab.gui.app import MainWindow, system_ist_dunkel
    from spotlab.gui.theme import palette_fuer, stylesheet

    app = QApplication.instance()
    app.setStyleSheet(stylesheet(palette_fuer(system_ist_dunkel(app))))
    fenster = MainWindow()
    fenster.show()
    fenster.raise_()
    fenster.activateWindow()
    return fenster


def vorwaermen(module=VORWAERMEN):
    """Lädt `module` in einem Hintergrundfaden; Fehler zählen nicht."""
    def arbeit():
        for name in module:
            try:
                importlib.import_module(name)
            except Exception:       # noqa: BLE001 -- nur eine Vorwärmung
                pass

    faden = threading.Thread(target=arbeit, name="spotlab-vorwaermen", daemon=True)
    faden.start()
    return faden


def _zeige_fehler(ausnahme):
    QMessageBox.critical(
        None,
        "spotlab startet nicht",
        "Die Oberfläche liess sich nicht laden:\n\n"
        f"{type(ausnahme).__name__}: {ausnahme}\n\n"
        "Meist hilft es, einrichten.cmd noch einmal auszuführen.",
    )
    QApplication.exit(1)


def main(argv=None):
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("spotlab")
    # Auch an der Anwendung: sonst tragen Dialoge und das Übungsfenster unter
    # Windows das Standardbild von Qt.
    app.setWindowIcon(symbol())
    start = Start(lade_gui, baue_gui, _zeige_fehler)
    start.fertig.connect(lambda: QTimer.singleShot(VORWAERMEN_NACH_MS, vorwaermen))
    start.los()
    return app.exec()
