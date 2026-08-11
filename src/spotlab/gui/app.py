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
from spotlab.gui.editor.view import EditorView
from spotlab.gui.header import Header
from spotlab.gui.sidebar import Sidebar
from spotlab.gui.theme import palette_fuer, stylesheet
from spotlab.gui.views.anbindungen import AnbindungenView
from spotlab.gui.views.checkup import CheckupView
from spotlab.gui.views.live import LiveView
from spotlab.gui.views.maps import MapsView
from spotlab.gui.views.projects import ProjectsView
from spotlab.gui.views.runs import RunsView
from spotlab.gui.watcher import RunWatcher
from spotlab.gui.workers import DoctorWorker, OutputReader
from spotlab.record.read import read_run
from spotlab.workshop.control import ist_aktiv


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

        self._palette = palette_fuer(system_ist_dunkel())
        # Woher der letzte Start kam. Steuert nur eines: ob _lauf_begonnen die
        # Ansicht wechselt.
        self._start_aus = None
        # Genau EIN Lauf ist der, auf den Stopp und NOT-AUS zeigen. Weitere
        # warten, statt ihn zu verdrängen — sonst zeigt der Knopf auf einen
        # anderen Prozess als den, der gerade den Roboter hält.
        self._aktiver_lauf = None
        self._wartende_laeufe = []

        self.kopf = Header()
        self.leiste = Sidebar()
        self.statuszeile = QLabel("")
        self.statuszeile.setObjectName("Gedaempft")

        self.ansichten = {
            "projekte": ProjectsView(
                editor_command=self._config.editor_command if self._config else "code"
            ),
            "code": EditorView(self._palette),
            "live": LiveView(),
            "laeufe": RunsView(),
            "karten": MapsView(),
            "anbindungen": AnbindungenView(self._palette),
            "spot": CheckupView(),
        }
        self.stapel = QStackedWidget()
        for schluessel in (
            "projekte", "code", "live", "laeufe", "karten", "anbindungen", "spot"
        ):
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
        self.ansichten["karten"].setze_config(self._config)

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
        self.ansichten["karten"].meldung.connect(self._melde)
        self.ansichten["karten"].aktive_karte_gewaehlt.connect(self._merke_aktive_karte)
        self.ansichten["code"].lauf_gestartet.connect(self._lauf_aus_code)
        self.ansichten["code"].meldung.connect(self._melde)
        self.ansichten["projekte"].projekt_oeffnen.connect(self._oeffne_in_code)
        self.ansichten["anbindungen"].meldung.connect(self._melde)
        self.ansichten["anbindungen"].lauf_gestartet.connect(self._lauf_aus_anbindungen)
        self._verdrahte_code_stopp()

    def _verdrahte_code_stopp(self):
        """Eigene Methode, damit Tests nach dem Austausch von stoppe() neu verdrahten.

        Der Stopp-Knopf im Editor ruft NICHT eine zweite Kopie der Logik: der
        freundliche Stopp hängt am Lauf-Verzeichnis, das nur die Live-Ansicht
        vom Watcher bekommt. Delegation heisst dasselbe Objekt mit demselben
        Zustand — und damit garantiert dasselbe Verhalten.
        """
        self.ansichten["code"].stopp_gewuenscht.connect(
            lambda: self.ansichten["live"].stoppe()
        )

    def _setze_arbeitsordner(self, pfad):
        self.ansichten["projekte"].setze_arbeitsordner(pfad or None)
        self.ansichten["code"].setze_arbeitsordner(pfad or None)
        self.ansichten["anbindungen"].setze_arbeitsordner(pfad or None)
        self.ansichten["laeufe"].setze_arbeitsordner(pfad or None)
        self.ansichten["karten"].setze_arbeitsordner(pfad or None)
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

    def _merke_aktive_karte(self, name):
        if self._config is None:
            self._melde("Der Spot ist noch nicht eingerichtet — Ansicht 'Spot'.")
            return
        self._config = replace(self._config, active_map=name)
        save_config(self._config)
        self.ansichten["karten"].setze_config(self._config)

    def _config_gespeichert(self, cfg):
        self._config = cfg
        self.kopf.zeige_config(cfg)
        self.ansichten["karten"].setze_config(cfg)

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

    def _starte_leser(self, prozess):
        """EIN Leser, zwei Senken.

        Ein zweiter OutputReader auf derselben Pipe teilte sich die Zeilen
        zufällig mit dem ersten. Neue Ansichten hängen sich hier als weitere
        Senke an, nie mit einem eigenen Leser an den Prozess.
        """
        self._leser = OutputReader(prozess, self)
        self._leser.zeile.connect(self.ansichten["live"].zeige_ausgabe)
        self._leser.zeile.connect(self.ansichten["code"].zeige_ausgabe)
        self._leser.start()

    def _lauf_gestartet(self, prozess, skript):
        self._start_aus = "projekte"
        self._wechsle("live")
        self.leiste.waehle("live")
        self._starte_leser(prozess)

    def _lauf_aus_code(self, prozess, skript):
        # Kein Ansichtswechsel: wer aus „Code" startet, will dort bleiben.
        self._start_aus = "code"
        self._starte_leser(prozess)

    def _lauf_aus_anbindungen(self, prozess, skript):
        # Aus demselben Grund: wer dort startet, will die Panels sehen, nicht
        # Telemetrie. Ein langer Experimentlauf schreibt seinen Fortschritt
        # genau in die Ansicht, aus der er gestartet wurde.
        self._start_aus = "anbindungen"
        self._starte_leser(prozess)

    def _oeffne_in_code(self, projekt):
        self.ansichten["code"].setze_projekt(projekt)
        self._wechsle("code")
        self.leiste.waehle("code")

    def _lauf_begonnen(self, verzeichnis):
        # NIE bedingungslos umhängen: die Live-Ansicht ist das Ziel von Stopp
        # und NOT-AUS. Zeigt sie auf einen anderen Lauf als den, der gerade den
        # Roboter hält, trifft der Knopf den falschen Prozess. Zwei Läufe
        # gleichzeitig sind kein konstruierter Fall — aus „Projekte" starten,
        # dann aus „Code", oder zusätzlich F5 aus VS Code (A11 sieht das vor).
        if Path(verzeichnis) == self._aktiver_lauf:
            return
        if self._aktiver_lauf is not None and ist_aktiv(self._aktiver_lauf):
            self._wartende_laeufe.append(Path(verzeichnis))
            self.ansichten["live"].meldung.emit(
                f"Es läuft bereits ein Programm ({self._aktiver_lauf.name}). "
                f"Die Anzeige und der NOT-AUS bleiben bei diesem — der zweite "
                f"Lauf wird übernommen, sobald der erste fertig ist."
            )
            return
        self._uebernimm_lauf(verzeichnis)

    def _uebernimm_lauf(self, verzeichnis):
        self._aktiver_lauf = Path(verzeichnis)
        # Skriptnamen aus lauf.json holen: „hallo_spot.py" sagt mehr als eine
        # Zeitstempel-Kennung.
        skript = read_run(verzeichnis).skript
        name = Path(skript).name if skript else Path(verzeichnis).name
        self.ansichten["live"].setze_lauf(verzeichnis, name)
        # Auch bei einem von aussen gestarteten Lauf (F5 in VS Code) hinschalten —
        # sonst sieht der Schüler nicht, dass sein Programm läuft. Wer aber
        # gerade selbst aus „Code" gestartet hat, wird nicht aus seiner Ansicht
        # geworfen.
        if self._start_aus in ("code", "anbindungen"):
            return
        self._wechsle("live")
        self.leiste.waehle("live")

    def _zustand(self, satz):
        self.kopf.zeige_zustand(satz)
        self.ansichten["live"].zeige_zustand(satz)

    def _lauf_beendet(self, verzeichnis):
        if self._aktiver_lauf is not None and Path(verzeichnis) != self._aktiver_lauf:
            # Ein Lauf, den wir gar nicht anzeigen, ist fertig geworden.
            self._wartende_laeufe = [
                p for p in self._wartende_laeufe if p != Path(verzeichnis)
            ]
            return
        self.ansichten["live"].lauf_beendet()
        self.ansichten["code"].lauf_beendet()
        self.ansichten["anbindungen"].aktualisiere()
        self.ansichten["laeufe"].aktualisiere()
        self.kopf.zeige_getrennt()
        self._start_aus = None
        self._aktiver_lauf = None
        # Jetzt darf ein wartender Lauf nachrücken — aber nur, wenn er noch lebt.
        while self._wartende_laeufe:
            naechster = self._wartende_laeufe.pop(0)
            if ist_aktiv(naechster):
                self._uebernimm_lauf(naechster)
                return

    def closeEvent(self, ereignis):
        if self._watcher is not None:
            self._watcher.stop()
        # Die Kartenaufnahme ist ein QThread mit einer OFFENEN Robotersitzung.
        # Ohne diesen Aufruf bliebe er als Kind eines zerstörten Widgets zurück —
        # dasselbe Absturzmuster wie beim JediWorker, hier aber mit einer
        # laufenden Verbindung zum Spot.
        try:
            self.ansichten["karten"]._beende_worker()
        except Exception as fehler:      # Schliessen darf nie hängen bleiben
            print(f"Kartenaufnahme liess sich nicht beenden: {fehler}", file=sys.stderr)
        super().closeEvent(ereignis)


def main(argv=None):
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("spotlab")
    app.setStyleSheet(stylesheet(palette_fuer(system_ist_dunkel(app))))
    fenster = MainWindow()
    fenster.show()
    return app.exec()
