"""Rekonstruieren: Karte waehlen, Einstellungen, Vorschau im Arbeiter-Thread.

Die Rechnung selbst steht in `maps/rekonstruktion.py` (bosdyn, numpy). Hier
laeuft sie in einem QThread, damit das Fenster bei 40 MB Karte nicht einfriert
-- Muster wie `gui/recorder.py`. Der Dialog bekommt `Ergebnis(raum, pauspapier,
bericht)` und sieht nie ein Protobuf.
"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from spotlab.errors import SpotlabError
from spotlab.maps.rekonstruktion import Einstellungen, rekonstruiere
from spotlab.maps.store import karten


class RekonstruktionsArbeiter(QThread):
    fortschritt = Signal(str)
    fertig = Signal(object)          # Ergebnis
    fehler = Signal(str)

    def __init__(self, ordner, einstellungen, parent=None):
        super().__init__(parent)
        self._ordner = Path(ordner)
        self._einstellungen = einstellungen

    def run(self):
        try:
            ergebnis = rekonstruiere(self._ordner, self._einstellungen,
                                     fortschritt=self.fortschritt.emit)
        except SpotlabError as fehler:
            self.fehler.emit(str(fehler))
            return
        except Exception as fehler:
            self.fehler.emit(f"{type(fehler).__name__}: {fehler}")
            return
        self.fertig.emit(ergebnis)


def _berichtstext(bericht):
    zeilen = [
        f"Wegpunkte: {bericht['wegpunkte']}  ·  Schnappschüsse: {bericht['schnappschuesse']}"
        f" (fehlend: {bericht['fehlend']})  ·  Posen: {bericht['posen']}",
        f"Punkte: {bericht['punkte']}  ·  im Band: {bericht['im_band']}  ·  Zellen: {bericht['zellen']}",
        f"Linien: {bericht['linien']}  ·  Wände: {bericht['waende']}  ·  verworfen: {bericht['verworfen']}"
        f"  ·  durchquert (frei): {bericht.get('durchquert', 0)}",
        f"Tags: {bericht['tags']}  ·  Ausrichtung: {bericht['ausricht_grad']:+.0f}°"
        f"  ·  Quelle: {bericht['quelle']}  ·  {bericht.get('dauer_s', 0):.1f} s",
        f"Böden: {bericht.get('boeden', 0)}  ·  Treppen: {bericht.get('treppen', 0)}"
        f"  ·  Rampen: {bericht.get('rampen', 0)}  ·  grösstes Gefälle: {bericht.get('gefaelle_grad', 0):.1f}°"
        f"  ·  Ebenen: " + ", ".join(f"{e:.1f}" for e in bericht.get("ebenen", [0.0]))
        + f"  ·  Stufe: {bericht.get('stufe_m', 0):.2f} m (Annahme)",
    ]
    zeilen += [f"⚠ {h}" for h in bericht.get("hinweise", [])]
    return "\n".join(zeilen)


class RekonstruktionsDialog(QDialog):
    ergebnis_da = Signal(object)

    def __init__(self, parent, arbeitsordner):
        super().__init__(parent)
        self.setWindowTitle("Raum aus einer Karte rekonstruieren")
        self.ergebnis = None
        self._arbeiter = None
        self._arbeitsordner = arbeitsordner

        self.karten = QComboBox()
        self._karten = karten(arbeitsordner) if arbeitsordner else []
        for karte in self._karten:
            self.karten.addItem(karte.name, str(karte.dir))
        self.karten.currentIndexChanged.connect(self._karte_gewaehlt)
        self.ordner_feld = QLineEdit()
        self.ordner_feld.setPlaceholderText("Kartenordner mit `graph` und `waypoint_snapshots/`")
        waehlen = QPushButton("Ordner wählen…")
        waehlen.clicked.connect(self._ordner_waehlen)
        zeile = QHBoxLayout()
        zeile.addWidget(self.ordner_feld, 1)
        zeile.addWidget(waehlen)

        self.band_von = self._zahl(0.3, 0.0, 3.0)
        self.band_bis = self._zahl(1.6, 0.1, 4.0)
        self.zelle = self._zahl(0.05, 0.02, 0.5, 0.01)
        self.luecke = self._zahl(0.4, 0.1, 3.0)
        self.min_laenge = self._zahl(0.5, 0.1, 5.0)
        self.schlauch = self._zahl(2.0, 0.5, 6.0)
        self.ausrichten = QCheckBox("Häufigste Wandrichtung auf die x-Achse drehen")
        self.ausrichten.setChecked(True)
        self.sichtpruefung = QCheckBox("Sichtprüfung: Zellen, durch die Strahlen gehen, sind frei")
        self.sichtpruefung.setChecked(True)
        self.begradigen = QCheckBox("Begradigen: Winkel bis 7° rasten, Doppelwände vereinen")
        self.begradigen.setChecked(True)
        form = QFormLayout()
        form.addRow("Karte aus dem Arbeitsordner", self.karten)
        form.addRow("oder Ordner", zeile)
        band = QHBoxLayout()
        band.addWidget(self.band_von)
        band.addWidget(QLabel("bis"))
        band.addWidget(self.band_bis)
        form.addRow("Höhenband über dem Boden (m)", band)
        form.addRow("Zelle (m)", self.zelle)
        form.addRow("Lücke = Tür ab (m)", self.luecke)
        form.addRow("Mindestlänge einer Wand (m)", self.min_laenge)
        form.addRow("Schlauchbreite ohne Wolken (m)", self.schlauch)
        form.addRow("", self.sichtpruefung)
        form.addRow("", self.ausrichten)
        form.addRow("", self.begradigen)

        self.vorschau_knopf = QPushButton("Vorschau rechnen")
        self.vorschau_knopf.clicked.connect(self.vorschau)
        self.status = QLabel("")
        self.status.setObjectName("Gedaempft")
        self.bericht = QTextEdit()
        self.bericht.setReadOnly(True)
        self.bericht.setMinimumHeight(110)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(False)
        self.knoepfe.accepted.connect(self.accept)
        self.knoepfe.rejected.connect(self.reject)

        aussen = QVBoxLayout(self)
        aussen.addLayout(form)
        aussen.addWidget(self.vorschau_knopf)
        aussen.addWidget(self.status)
        aussen.addWidget(self.bericht, 1)
        aussen.addWidget(self.knoepfe)
        if self._karten:
            self._karte_gewaehlt(0)

    @staticmethod
    def _zahl(wert, von, bis, schritt=0.1):
        feld = QDoubleSpinBox()
        feld.setDecimals(2)
        feld.setRange(von, bis)
        feld.setSingleStep(schritt)
        feld.setValue(wert)
        return feld

    def _karte_gewaehlt(self, index):
        if 0 <= index < len(self._karten):
            self.ordner_feld.setText(str(self._karten[index].dir))

    def _ordner_waehlen(self):
        start = self.ordner_feld.text() or (str(self._arbeitsordner) if self._arbeitsordner else "")
        ordner = QFileDialog.getExistingDirectory(self, "Kartenordner wählen", start)
        if ordner:
            self.ordner_feld.setText(ordner)

    def einstellungen(self):
        return Einstellungen(
            band=(self.band_von.value(), self.band_bis.value()), zelle=self.zelle.value(),
            luecke=self.luecke.value(), min_laenge=self.min_laenge.value(),
            ausrichten=self.ausrichten.isChecked(), schlauch_breite=self.schlauch.value(),
            sichtpruefung=self.sichtpruefung.isChecked(), begradigen=self.begradigen.isChecked(),
        )

    def vorschau(self):
        ordner = self.ordner_feld.text().strip()
        if not ordner:
            self.status.setText("Zuerst eine Karte oder einen Ordner wählen.")
            return
        if self._arbeiter is not None and self._arbeiter.isRunning():
            return
        self.vorschau_knopf.setEnabled(False)
        self.status.setText("Rechne…")
        self._arbeiter = RekonstruktionsArbeiter(ordner, self.einstellungen(), self)
        self._arbeiter.fortschritt.connect(self.status.setText)
        self._arbeiter.fertig.connect(self._fertig)
        self._arbeiter.fehler.connect(self._fehler)
        self._arbeiter.start()

    def _fertig(self, ergebnis):
        self.ergebnis = ergebnis
        self.bericht.setPlainText(_berichtstext(ergebnis.bericht))
        b = ergebnis.bericht
        self.status.setText(f"Vorschlag: {b['waende']} Wände, {b['tags']} Tags, "
                            f"{b.get('treppen', 0)} Treppen, {b.get('rampen', 0)} Rampen — "
                            f"im Editor nachziehen.")
        self.vorschau_knopf.setEnabled(True)
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(True)
        self.ergebnis_da.emit(ergebnis)

    def _fehler(self, text):
        self.status.setText(text)
        self.vorschau_knopf.setEnabled(True)

    def closeEvent(self, ereignis):
        # Ein laufender Arbeiter darf nicht mit dem Dialog sterben (siehe CLAUDE.md, JediWorker).
        if self._arbeiter is not None and self._arbeiter.isRunning():
            self._arbeiter.wait(30_000)
        super().closeEvent(ereignis)
