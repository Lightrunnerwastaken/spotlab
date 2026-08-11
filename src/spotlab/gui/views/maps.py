"""Ansicht „Karten": aufzeichnen, ansehen, auswählen.

Aufzeichnen braucht kein Lease — deshalb darf die GUI es. Hochladen und
Fahren gehören ins Skript, deshalb setzt der Auswählen-Knopf nur die aktive
Karte in der Konfiguration.
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.mapplot import MapPlot
from spotlab.gui.theme import DUNKEL
from spotlab.maps.geometry import grundriss
from spotlab.maps.store import karten, karten_wurzel, lade_graph, loesche

HINWEIS = (
    "Zum Aufzeichnen muss der Spot ein Fiducial sehen. Fahre ihn während der "
    "Aufnahme mit dem TABLET durch den Raum — spotlab zeichnet nur mit und "
    "übernimmt die Steuerung nicht."
)


class MapsView(QWidget):
    aktive_karte_gewaehlt = Signal(str)
    meldung = Signal(str)

    def __init__(self, palette=DUNKEL, parent=None):
        super().__init__(parent)
        # Palette durchreichen wie bei den anderen Ansichten: der Grundriss
        # malte seine Beschriftungen sonst immer in Dunkelmodus-Farben, auch
        # auf hellem Grund.
        self._palette = palette
        self._ordner = None
        self._config = None
        self._worker = None
        self._karten = []

        self.hinweis = QLabel(HINWEIS)
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        self.graph_leeren = QCheckBox("Karte auf dem Roboter zuerst leeren")
        self.start_knopf = QPushButton("Aufnahme starten")
        self.start_knopf.clicked.connect(self._starte_aufnahme)
        self.wegpunkt_knopf = QPushButton("Wegpunkt setzen")
        self.wegpunkt_knopf.clicked.connect(self._setze_wegpunkt)
        self.speichern_knopf = QPushButton("Beenden und speichern")
        self.speichern_knopf.clicked.connect(self._beende_und_speichere)
        self.aufnahme_status = QLabel("Keine Aufnahme")
        self.aufnahme_status.setObjectName("Gedaempft")
        for knopf in (self.wegpunkt_knopf, self.speichern_knopf):
            knopf.setEnabled(False)

        self.liste = QListWidget()
        self.liste.currentRowChanged.connect(self._zeige_karte)
        self.aktiv_knopf = QPushButton("Als aktive Karte setzen")
        self.aktiv_knopf.clicked.connect(self._setze_aktiv)
        self.loeschen_knopf = QPushButton("Löschen")
        self.loeschen_knopf.clicked.connect(self._loesche)

        self.plot = MapPlot()
        self.plot.palette_ = self._palette
        self.plot_hinweis = QLabel("")
        self.plot_hinweis.setObjectName("Gedaempft")
        self.plot_hinweis.setWordWrap(True)

        aufnahme = QHBoxLayout()
        aufnahme.addWidget(self.start_knopf)
        aufnahme.addWidget(self.wegpunkt_knopf)
        aufnahme.addWidget(self.speichern_knopf)
        aufnahme.addStretch(1)
        aufnahme.addWidget(self.aufnahme_status)

        kartenknoepfe = QHBoxLayout()
        kartenknoepfe.addWidget(self.aktiv_knopf)
        kartenknoepfe.addWidget(self.loeschen_knopf)
        kartenknoepfe.addStretch(1)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(QLabel("Aufnahme"))
        anordnung.addWidget(self.hinweis)
        anordnung.addWidget(self.graph_leeren)
        anordnung.addLayout(aufnahme)
        anordnung.addWidget(QLabel("Karten"))
        anordnung.addWidget(self.liste, 1)
        anordnung.addLayout(kartenknoepfe)
        anordnung.addWidget(self.plot, 3)
        anordnung.addWidget(self.plot_hinweis)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.aktualisiere()

    def setze_config(self, cfg):
        self._config = cfg

    def aktualisiere(self):
        self.liste.clear()
        self._karten = karten(self._ordner) if self._ordner else []
        for eintrag in self._karten:
            self.liste.addItem(
                f"{eintrag.name}  ·  {eintrag.wegpunkte} Wegpunkte, "
                f"{eintrag.kanten} Kanten"
            )

    def _gewaehlte(self):
        zeile = self.liste.currentRow()
        if zeile < 0 or zeile >= len(self._karten):
            return None
        return self._karten[zeile]

    def _zeige_karte(self, _zeile):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        try:
            riss = grundriss(lade_graph(eintrag.dir))
        except OSError as fehler:
            self.meldung.emit(f"Die Karte lässt sich nicht lesen: {fehler}")
            return
        self.plot.setze_grundriss(riss)
        self.plot_hinweis.setText(riss.hinweis)

    # ------------------------------------------------------------- Karten

    def _setze_aktiv(self):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        self.aktive_karte_gewaehlt.emit(eintrag.name)
        self.meldung.emit(
            f"'{eintrag.name}' ist jetzt die aktive Karte — im Skript reicht "
            f"spot.load_map()."
        )

    def _loesche(self):
        eintrag = self._gewaehlte()
        if eintrag is None:
            return
        antwort = QMessageBox.question(
            self, "spotlab", f"Die Karte '{eintrag.name}' wirklich löschen?"
        )
        if antwort != QMessageBox.Yes:
            return
        loesche(eintrag.dir)
        self.aktualisiere()

    # ------------------------------------------------------------- Aufnahme

    def _starte_aufnahme(self):
        if self._config is None:
            self.meldung.emit("Der Spot ist noch nicht eingerichtet — Ansicht 'Spot'.")
            return
        if self._ordner is None:
            self.meldung.emit("Wähle zuerst einen Arbeitsordner — Ansicht 'Projekte'.")
            return
        if self._worker is not None:
            self.meldung.emit("Es läuft bereits eine Aufnahme.")
            return

        from spotlab.gui.recorder import RecordingWorker

        self._worker = RecordingWorker(self._config, self)
        self._worker.status.connect(self._zeige_status)
        self._worker.fehler.connect(self._aufnahme_fehler)
        self._worker.gespeichert.connect(self._aufnahme_gespeichert)
        self._worker.bereit.connect(
            lambda: self._worker.starte(self.graph_leeren.isChecked())
        )
        self._worker.start()
        self.start_knopf.setEnabled(False)
        self.wegpunkt_knopf.setEnabled(True)
        self.speichern_knopf.setEnabled(True)
        self.aufnahme_status.setText("Verbinde…")

    def _setze_wegpunkt(self):
        if self._worker is None:
            return
        name, ok = QInputDialog.getText(self, "Wegpunkt", "Name:")
        if ok and name.strip():
            self._worker.setze_wegpunkt(name.strip())

    def _beende_und_speichere(self):
        if self._worker is None or self._ordner is None:
            return
        name, ok = QInputDialog.getText(self, "Karte speichern", "Name der Karte:")
        if not ok or not name.strip():
            return
        self._worker.speichere(
            karten_wurzel(self._ordner),
            name.strip(),
            roboter=self._config.nickname if self._config else None,
        )

    def _zeige_status(self, status):
        self.aufnahme_status.setText(
            f"{status.meldung} · {status.wegpunkte} Wegpunkte, {status.kanten} Kanten"
        )

    def _aufnahme_fehler(self, text):
        self.meldung.emit(text)

    def _aufnahme_gespeichert(self, pfad):
        self.meldung.emit(f"Karte gespeichert: {pfad}")
        self._beende_worker()
        self.aktualisiere()

    def _beende_worker(self):
        if self._worker is not None:
            self._worker.schliesse()
            self._worker.wait(3000)
            self._worker = None
        self.start_knopf.setEnabled(True)
        self.wegpunkt_knopf.setEnabled(False)
        self.speichern_knopf.setEnabled(False)
        self.aufnahme_status.setText("Keine Aufnahme")
