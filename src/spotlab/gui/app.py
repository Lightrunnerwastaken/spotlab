"""Das Hauptfenster: Kopfleiste, Seitenleiste, vier Ansichten.

Hier wird verdrahtet und sonst nichts. Die einzige Stelle im Programm, die Qt
nach dem Farbschema fragt, ist system_ist_dunkel() — theme.py bleibt dadurch
Qt-frei und prüfbar.
"""

import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spotlab.config import load_config, save_config
from spotlab.errors import SpotlabError
from spotlab.gui.header import Header
from spotlab.gui.sidebar import Sidebar
from spotlab.gui.theme import palette_fuer, stylesheet
from spotlab.gui.views.checkup import CheckupView
from spotlab.gui.views.live import LiveView
from spotlab.gui.views.projects import ProjectsView
from spotlab.gui.views.runs import RunsView
from spotlab.gui.watcher import RunWatcher
from spotlab.gui.workers import DoctorWorker, OutputReader
from spotlab.record.read import read_run


def system_ist_dunkel(app=None):
    """Die einzige Stelle, die Qt nach dem Farbschema fragt."""
    app = app or QApplication.instance()
    if app is None:
        return True
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return True


class MainWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("spotlab")
        self.resize(1080, 720)

        try:
            self._config = load_config()
        except SpotlabError:
            self._config = None

        self.kopf = Header()
        self.leiste = Sidebar()
        self.statuszeile = QLabel("")
        self.statuszeile.setObjectName("Gedaempft")

        self.ansichten = {
            "projekte": ProjectsView(
                editor_command=self._config.editor_command if self._config else "code"
            ),
            "live": LiveView(),
            "laeufe": RunsView(),
            "spot": CheckupView(),
        }
        self.stapel = QStackedWidget()
        for schluessel in ("projekte", "live", "laeufe", "spot"):
            self.stapel.addWidget(self.ansichten[schluessel])

        unten = QHBoxLayout()
        unten.setContentsMargins(0, 0, 0, 0)
        unten.addWidget(self.leiste)
        unten.addWidget(self.stapel, 1)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(0, 0, 0, 0)
        aussen.addWidget(self.kopf)
        aussen.addLayout(unten, 1)
        aussen.addWidget(self.statuszeile)

        self._watcher = None
        self._leser = None
        self._doctor = None
        self._verdrahte()
        self._setze_arbeitsordner(self._config.workspace if self._config else "")
        self.kopf.zeige_config(self._config)

        if self._config is None:
            self._wechsle("spot")
            self.leiste.waehle("spot")

    # ------------------------------------------------------------- Aufbau

    def _verdrahte(self):
        self.leiste.gewaehlt.connect(self._wechsle)
        self.kopf.notaus.connect(lambda: self.ansichten["live"].notaus())
        self.ansichten["live"].meldung.connect(self._melde)
        self.ansichten["projekte"].lauf_gestartet.connect(self._lauf_gestartet)
        self.ansichten["projekte"].arbeitsordner_geaendert.connect(self._merke_arbeitsordner)
        self.ansichten["spot"].config_gespeichert.connect(self._config_gespeichert)
        self.ansichten["spot"].pruefung_angefordert.connect(self._pruefe)

    def _setze_arbeitsordner(self, pfad):
        self.ansichten["projekte"].setze_arbeitsordner(pfad or None)
        self.ansichten["laeufe"].setze_arbeitsordner(pfad or None)
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if not pfad:
            return
        self._watcher = RunWatcher(Path(pfad))
        self._watcher.lauf_begonnen.connect(self._lauf_begonnen)
        self._watcher.zustand.connect(self._zustand)
        self._watcher.ereignis.connect(self.ansichten["live"].zeige_ereignis)
        self._watcher.bild.connect(self.ansichten["live"].zeige_bild)
        self._watcher.lauf_beendet.connect(self._lauf_beendet)
        self._watcher.fehler.connect(self._melde)
        self._watcher.start()

    # ------------------------------------------------------------- Reaktionen

    def _wechsle(self, schluessel):
        self.stapel.setCurrentWidget(self.ansichten[schluessel])

    def _melde(self, text):
        self.statuszeile.setText(text)

    def _merke_arbeitsordner(self, pfad):
        self._setze_arbeitsordner(pfad)
        if self._config is None:
            return
        self._config = replace(self._config, workspace=pfad)
        save_config(self._config)

    def _config_gespeichert(self, cfg):
        self._config = cfg
        self.kopf.zeige_config(cfg)

    def _pruefe(self):
        self.ansichten["spot"].pruefen_knopf.setEnabled(False)
        self.ansichten["spot"].pruefen_knopf.setText("Prüfe…")
        self._doctor = DoctorWorker(self)
        self._doctor.fertig.connect(self._pruefung_fertig)
        self._doctor.fehler.connect(self._melde)
        self._doctor.finished.connect(self._pruefung_aufraeumen)
        self._doctor.start()

    def _pruefung_fertig(self, pruefungen):
        self.ansichten["spot"].zeige_pruefung(pruefungen)
        self.kopf.zeige_pruefung(pruefungen)

    def _pruefung_aufraeumen(self):
        self.ansichten["spot"].pruefen_knopf.setEnabled(True)
        self.ansichten["spot"].pruefen_knopf.setText("Spot prüfen")

    def _lauf_gestartet(self, prozess, skript):
        self._wechsle("live")
        self.leiste.waehle("live")
        self._leser = OutputReader(prozess, self)
        self._leser.zeile.connect(self.ansichten["live"].zeige_ausgabe)
        self._leser.start()

    def _lauf_begonnen(self, verzeichnis):
        # Skriptnamen aus lauf.json holen: „hallo_spot.py" sagt mehr als eine
        # Zeitstempel-Kennung.
        skript = read_run(verzeichnis).skript
        name = Path(skript).name if skript else Path(verzeichnis).name
        self.ansichten["live"].setze_lauf(verzeichnis, name)
        # Auch bei einem von aussen gestarteten Lauf (F5 in VS Code) hinschalten —
        # sonst sieht der Schüler nicht, dass sein Programm läuft.
        self._wechsle("live")
        self.leiste.waehle("live")

    def _zustand(self, satz):
        self.kopf.zeige_zustand(satz)
        self.ansichten["live"].zeige_zustand(satz)

    def _lauf_beendet(self, verzeichnis):
        self.ansichten["live"].lauf_beendet()
        self.ansichten["laeufe"].aktualisiere()
        self.kopf.zeige_getrennt()

    def closeEvent(self, ereignis):
        if self._watcher is not None:
            self._watcher.stop()
        super().closeEvent(ereignis)


def main(argv=None):
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("spotlab")
    app.setStyleSheet(stylesheet(palette_fuer(system_ist_dunkel(app))))
    fenster = MainWindow()
    fenster.show()
    return app.exec()
