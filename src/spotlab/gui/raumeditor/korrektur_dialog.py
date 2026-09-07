"""Korrigieren: Wandluecken als Liste mit Vorschlag und Grund, dann das Gelaende.

Nicht modal, damit die 2D-Sicht daneben bedienbar bleibt: die gewaehlte Zeile
leuchtet dort auf (`markiere`), alle Kandidaten stehen duenn dahinter
(`kandidaten`). „Anwenden" macht erst die Waende (`welt/korrektur.py`, sofort),
dann das Gelaende in einem Arbeiter-Thread (`maps/gelaende_bau.py`, numpy),
und uebergibt dem Tab EIN Ergebnis (`Korrektur`) -- ein Verlaufsschritt.
Scheitert das Gelaende, sind die Waende trotzdem angewendet.
"""

from dataclasses import dataclass

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from spotlab.errors import SpotlabError
from spotlab.maps.gelaende_bau import Einstellungen, baue_gelaende
from spotlab.welt.korrektur import finde_luecken, uebernimm_gelaende, wende_an

ARTEN = {"luecke": "Lücke", "ecke": "Ecke", "anschluss": "Anschluss", "kreuzt": "Kreuzt"}
WAHL = (("Wand", "wand"), ("Durchgang", "durchgang"), ("lassen", "lassen"))
WAHL_KREUZT = (("Löschen", "loeschen"), ("lassen", "lassen"))


@dataclass(frozen=True)
class Korrektur:
    raum: object
    offene_raender: list
    bericht: dict        # waende_verbunden, durchgaenge, geloescht, gelaende (Bericht | None)


class GelaendeArbeiter(QThread):
    fortschritt = Signal(str)
    fertig = Signal(object)          # maps.gelaende_bau.Ergebnis
    fehler = Signal(str)

    def __init__(self, raum, weg, pauspapier, einstellungen, parent=None):
        super().__init__(parent)
        self._raum, self._weg, self._pauspapier = raum, list(weg), list(pauspapier)
        self._einstellungen = einstellungen

    def run(self):
        try:
            ergebnis = baue_gelaende(self._raum, self._weg, self._pauspapier,
                                     self._einstellungen, fortschritt=self.fortschritt.emit)
        except SpotlabError as fehler:
            self.fehler.emit(str(fehler))
            return
        except Exception as fehler:
            self.fehler.emit(f"{type(fehler).__name__}: {fehler}")
            return
        self.fertig.emit(ergebnis)


def _anzahl(n, einzahl, mehrzahl):
    return f"{n} {einzahl if n == 1 else mehrzahl}"


class KorrekturDialog(QDialog):
    markiere = Signal(object)        # [(x1, y1, x2, y2)] der gewaehlten Zeile
    kandidaten = Signal(object)      # alle Strecken, beim Zeigen
    angewendet = Signal(object)      # Korrektur

    def __init__(self, eltern, raum, weg, pauspapier):
        super().__init__(eltern)
        self.setWindowTitle("Korrigieren: Lücken schliessen, Gelände bauen")
        self.setModal(False)
        self._raum, self._weg, self._pauspapier = raum, list(weg), list(pauspapier)
        self._luecken = finde_luecken(raum, self._weg, self._pauspapier)
        self._arbeiter = None
        self._korrigierter_raum = None
        self._teilbericht = {}
        mit_weg = len(self._weg) >= 2

        self.tabelle = QTableWidget(len(self._luecken), 5)
        self.tabelle.setHorizontalHeaderLabels(["Nr", "Art", "Länge", "Vorschlag", "Grund"])
        self.tabelle.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabelle.setSelectionMode(QTableWidget.SingleSelection)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        for zeile, luecke in enumerate(self._luecken):
            for spalte, text in ((0, str(zeile + 1)), (1, ARTEN.get(luecke.art, luecke.art)),
                                 (2, f"{luecke.laenge:.2f} m"), (4, luecke.grund)):
                eintrag = QTableWidgetItem(text)
                eintrag.setFlags(eintrag.flags() & ~Qt.ItemIsEditable)
                self.tabelle.setItem(zeile, spalte, eintrag)
            wahl = QComboBox()
            for text, wert in (WAHL_KREUZT if luecke.art == "kreuzt" else WAHL):
                wahl.addItem(text, wert)
            vorgabe = luecke.vorschlag if luecke.vorschlag != "unklar" else "lassen"
            wahl.setCurrentIndex(max(0, wahl.findData(vorgabe)))
            self.tabelle.setCellWidget(zeile, 3, wahl)
        self.tabelle.itemSelectionChanged.connect(self._zeile_gewaehlt)

        self.gelaende_bauen = QCheckBox("Gelände bauen")
        self.abstand = QDoubleSpinBox()
        self.abstand.setRange(0.5, 6.0)
        self.abstand.setSingleStep(0.5)
        self.abstand.setDecimals(1)
        self.abstand.setValue(2.0)
        self.abstand.setSuffix(" m")
        rampen = sum(1 for b in raum.boeden if b.stufen == 0 and b.anstieg != 0.0)
        podeste = sum(1 for b in raum.boeden if b.stufen == 0 and b.anstieg == 0.0)
        self.boeden_aufloesen = QCheckBox(
            f"{_anzahl(rampen, 'Rampe', 'Rampen')} und {_anzahl(podeste, 'Podest', 'Podeste')} "
            f"ins Gelände übernehmen")
        if mit_weg:
            self.gelaende_bauen.setChecked(True)
            self.boeden_aufloesen.setChecked(rampen + podeste > 0)
        else:
            self.gelaende_bauen.setText("Gelände bauen — Kein Weg gespeichert, nur die Wände")
            self.gelaende_bauen.setChecked(False)
            self.gelaende_bauen.setEnabled(False)
            self.boeden_aufloesen.setEnabled(False)
            self.abstand.setEnabled(False)
        form = QFormLayout()
        form.addRow("", self.gelaende_bauen)
        form.addRow("Boden bis … neben dem Weg, wo keine Wand ist", self.abstand)
        form.addRow("", self.boeden_aufloesen)

        self.fortschritt = QLabel("")
        self.fortschritt.setObjectName("Gedaempft")
        self.anwenden = QPushButton("Anwenden")
        self.anwenden.clicked.connect(self._anwenden)
        self.schliessen = QPushButton("Schliessen")
        self.schliessen.clicked.connect(self.close)
        if not self._luecken and not mit_weg:
            self.fortschritt.setText("Nichts zu korrigieren: keine Lücken, kein Weg.")
            self.anwenden.setEnabled(False)
        knoepfe = QHBoxLayout()
        knoepfe.addWidget(self.fortschritt, 1)
        knoepfe.addWidget(self.anwenden)
        knoepfe.addWidget(self.schliessen)

        aussen = QVBoxLayout(self)
        aussen.addWidget(QLabel(f"{len(self._luecken)} Kandidaten — die gewählte Zeile leuchtet "
                                f"in der 2D-Sicht auf; „lassen“ ändert nichts."))
        aussen.addWidget(self.tabelle, 1)
        aussen.addLayout(form)
        aussen.addLayout(knoepfe)
        self.resize(720, 460)

    # ---------------------------------------------------------- Tabelle

    def entscheide(self):
        """{Zeile: "wand" | "durchgang" | "loeschen" | "lassen"} aus der Tabelle."""
        return {zeile: self.tabelle.cellWidget(zeile, 3).currentData()
                for zeile in range(self.tabelle.rowCount())}

    def alle_strecken(self):
        return [strecke for luecke in self._luecken for strecke in luecke.strecken]

    def _zeile_gewaehlt(self):
        zeilen = {eintrag.row() for eintrag in self.tabelle.selectedItems()}
        if not zeilen:
            self.markiere.emit([])
            return
        self.markiere.emit(list(self._luecken[min(zeilen)].strecken))

    def showEvent(self, ereignis):
        super().showEvent(ereignis)
        self.kandidaten.emit(self.alle_strecken())

    # ---------------------------------------------------------- Anwenden

    def _anwenden(self):
        entscheide = self.entscheide()
        raum = wende_an(self._raum, self._luecken, entscheide)
        self._teilbericht = {
            "waende_verbunden": sum(1 for i, luecke in enumerate(self._luecken)
                                    if entscheide.get(i) == "wand" and luecke.art != "kreuzt"),
            "durchgaenge": sum(1 for wert in entscheide.values() if wert == "durchgang"),
            "geloescht": sum(1 for wert in entscheide.values() if wert == "loeschen"),
        }
        self._korrigierter_raum = raum
        if not self.gelaende_bauen.isChecked():
            self._fertig(raum, [], None)
            return
        self.anwenden.setEnabled(False)
        self.fortschritt.setText("Gelände: Sperren")
        self._arbeiter = GelaendeArbeiter(raum, self._weg, self._pauspapier,
                                          Einstellungen(abstand=self.abstand.value()), self)
        self._arbeiter.fortschritt.connect(lambda text: self.fortschritt.setText(f"Gelände: {text}"))
        self._arbeiter.fertig.connect(self._gelaende_fertig)
        self._arbeiter.fehler.connect(self._gelaende_fehler)
        self._arbeiter.start()

    def _gelaende_fertig(self, ergebnis):
        raum = uebernimm_gelaende(self._korrigierter_raum, ergebnis.gelaende,
                                  self.boeden_aufloesen.isChecked())
        self._fertig(raum, ergebnis.offene_raender, ergebnis.bericht)

    def _gelaende_fehler(self, text):
        # Die Waende sind angewendet; das Gelaende nicht -- der Dialog bleibt offen und sagt es.
        self.fortschritt.setText(f"Gelände scheiterte: {text}")
        self.anwenden.setEnabled(True)
        self._fertig(self._korrigierter_raum, [], None, schliessen=False)

    def _fertig(self, raum, offene_raender, gelaende_bericht, schliessen=True):
        bericht = dict(self._teilbericht)
        bericht["gelaende"] = gelaende_bericht
        self.angewendet.emit(Korrektur(raum, list(offene_raender), bericht))
        if schliessen:
            self.accept()

    def closeEvent(self, ereignis):
        if self._arbeiter is not None and self._arbeiter.isRunning():
            self._arbeiter.wait()
        super().closeEvent(ereignis)
