"""Was ein fremdes Projekt zu sagen hat.

„Code" zeigt, was das Programm sagt; „Live-Lauf", was der Roboter tut;
„Anbindungen", was ein fremdes Projekt zu sagen hat.

Panels sind Daten, kein Code: der GUI-Prozess ist der Prozess mit dem NOT-AUS,
und fremder Qt-Code im selben Event-Loop braeche genau den Failsafe, um den
Stufe 1 herumgebaut ist.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spotlab.anbindung import panel as panelmodul
from spotlab.anbindung import speicher
from spotlab.errors import SpotlabError
from spotlab.workshop.launcher import start_script

KNOEPFE_JE_ZEILE = 3


class Kurve(QWidget):
    """Eine Zahlenreihe als Linie. Wie gui/mapplot.py: QPainter statt Bibliothek."""

    def __init__(self, x, y, palette, parent=None):
        super().__init__(parent)
        self._x = [float(w) for w in x]
        self._y = [float(w) for w in y]
        self._palette = palette
        self.setMinimumHeight(120)

    def paintEvent(self, ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        if len(self._x) < 2:
            return
        rand = 8
        breite = max(1, self.width() - 2 * rand)
        hoehe = max(1, self.height() - 2 * rand)
        x_min, x_max = min(self._x), max(self._x)
        y_min, y_max = min(self._y), max(self._y)
        x_spanne = (x_max - x_min) or 1.0
        y_spanne = (y_max - y_min) or 1.0
        punkte = [
            (
                rand + (wert_x - x_min) / x_spanne * breite,
                rand + hoehe - (wert_y - y_min) / y_spanne * hoehe,
            )
            for wert_x, wert_y in zip(self._x, self._y)
        ]
        maler.setPen(QPen(QColor(self._palette.akzent), 2))
        for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
            maler.drawLine(int(x1), int(y1), int(x2), int(y2))


def _karte(titel):
    rahmen = QFrame()
    rahmen.setObjectName("Flaeche")
    anordnung = QVBoxLayout(rahmen)
    kopf = QLabel(titel)
    kopf.setObjectName("Titel")
    anordnung.addWidget(kopf)
    return rahmen, anordnung


def _warnung(anordnung, text):
    hinweis = QLabel(text)
    hinweis.setObjectName("Warnung")
    hinweis.setWordWrap(True)
    anordnung.addWidget(hinweis)
    return text


def panel_widget(panel, anbindung, palette):
    """Ein Panel als Widget. Gibt (Widget, Hinweistext) zurück — Text nur für Tests."""
    rahmen, anordnung = _karte(panel.titel or panel.name)

    if panel.fehler:
        return rahmen, _warnung(
            anordnung, f"Dieses Panel ist unbrauchbar: {panel.fehler}"
        )

    if panel.art == "kennzahlen":
        gitter = QGridLayout()
        for spalte, eintrag in enumerate(panel.inhalt):
            wert = QLabel(str(eintrag.get("wert", "")))
            wert.setObjectName("Kachelwert")
            name = QLabel(str(eintrag.get("name", "")))
            name.setObjectName("Kachelname")
            gitter.addWidget(wert, 0, spalte)
            gitter.addWidget(name, 1, spalte)
            zusatztext = str(eintrag.get("hinweis", ""))
            if zusatztext:
                zusatz = QLabel(zusatztext)
                zusatz.setObjectName("Gedaempft")
                gitter.addWidget(zusatz, 2, spalte)
        anordnung.addLayout(gitter)
        return rahmen, ""

    if panel.art == "tabelle":
        spalten = panel.inhalt["spalten"]
        zeilen = panel.inhalt["zeilen"]
        tabelle = QTableWidget(len(zeilen), len(spalten))
        tabelle.setHorizontalHeaderLabels([str(s) for s in spalten])
        tabelle.verticalHeader().setVisible(False)
        for z, zeile in enumerate(zeilen):
            for s, wert in enumerate(zeile):
                tabelle.setItem(z, s, QTableWidgetItem(str(wert)))
        anordnung.addWidget(tabelle)
        return rahmen, ""

    if panel.art == "reihe":
        beschriftung = QLabel(
            f"{panel.inhalt.get('y_name', 'Wert')} über {panel.inhalt.get('x_name', 'x')}"
        )
        beschriftung.setObjectName("Gedaempft")
        anordnung.addWidget(beschriftung)
        anordnung.addWidget(Kurve(panel.inhalt["x"], panel.inhalt["y"], palette))
        return rahmen, ""

    if panel.art == "bild":
        pfad = Path(panel.inhalt["pfad"])
        if not panelmodul.bild_erlaubt(pfad, anbindung):
            return rahmen, _warnung(
                anordnung,
                "Dieses Bild liegt ausserhalb des Projekts und wird nicht geladen. "
                "Lege es unter das Projektverzeichnis.",
            )
        pixmap = QPixmap(str(pfad))
        if pixmap.isNull():
            return rahmen, _warnung(
                anordnung, f"{pfad.name} liess sich nicht als Bild lesen."
            )
        bild = QLabel()
        bild.setPixmap(pixmap.scaledToWidth(520, Qt.SmoothTransformation))
        anordnung.addWidget(bild)
        return rahmen, ""

    absaetze = QLabel("\n\n".join(str(a) for a in panel.inhalt["absaetze"]))
    absaetze.setWordWrap(True)
    anordnung.addWidget(absaetze)
    return rahmen, ""


class AnbindungenView(QWidget):
    meldung = Signal(str)
    lauf_gestartet = Signal(object, str)
    # Ein Skript mit `roboter = true` bewegt den echten Spot. Dann ist die
    # Live-Ansicht mit ihrem NOT-AUS wichtiger als die Panels — Sicherheit
    # schlaegt Bequemlichkeit.
    roboterlauf = Signal()
    # Delegiert an LiveView.stoppe(), wie der Editor. Projektregel: dieselbe
    # Funktion aufzurufen genuegt nicht, es muss dasselbe Objekt mit demselben
    # Zustand sein — der freundliche Stopp haengt am Lauf-Verzeichnis.
    stopp_gewuenscht = Signal()

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._ordner = None
        self._anbindungen = []
        self.skriptknoepfe = []
        self._texte = []

        self.liste = QListWidget()
        self.liste.currentRowChanged.connect(lambda _: self._zeige())
        self.anbinden_knopf = QPushButton("Projekt anbinden…")
        self.anbinden_knopf.clicked.connect(self._anbinden)

        self.stopp_knopf = QPushButton("■ Stopp")
        self.stopp_knopf.clicked.connect(self.stopp_gewuenscht.emit)
        self.stopp_knopf.hide()

        links = QWidget()
        links_anordnung = QVBoxLayout(links)
        links_anordnung.setContentsMargins(0, 0, 0, 0)
        links_anordnung.addWidget(QLabel("Angebundene Projekte"))
        links_anordnung.addWidget(self.liste, 1)
        links_anordnung.addWidget(self.anbinden_knopf)
        links_anordnung.addWidget(self.stopp_knopf)
        links.setFixedWidth(230)

        self.hinweis = QLabel("")
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        # Gitter statt Reihe: matura-spot bringt acht Skripte mit, und eine
        # QHBoxLayout bricht nicht um — die Knoepfe wuerden zu Streifen
        # zusammengequetscht, bis keine Beschriftung mehr lesbar ist.
        knopfhuelle = QWidget()
        self.knopfzeile = QGridLayout(knopfhuelle)
        self.knopfzeile.setContentsMargins(0, 0, 0, 0)

        self._panelhuelle = QWidget()
        self.panelbereich = QVBoxLayout(self._panelhuelle)
        self.panelbereich.setAlignment(Qt.AlignTop)
        rollbereich = QScrollArea()
        rollbereich.setWidgetResizable(True)
        rollbereich.setWidget(self._panelhuelle)

        rechts = QVBoxLayout()
        rechts.addWidget(knopfhuelle)
        rechts.addWidget(self.hinweis)
        rechts.addWidget(rollbereich, 1)

        aussen = QHBoxLayout(self)
        aussen.addWidget(links)
        aussen.addLayout(rechts, 1)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.aktualisiere()

    def aktualisiere(self):
        merker = self.liste.currentRow()
        self.liste.blockSignals(True)
        self.liste.clear()
        self._anbindungen = (
            speicher.anbindungen(self._ordner) if self._ordner is not None else []
        )
        for anbindung in self._anbindungen:
            self.liste.addItem(anbindung.name)
        self.liste.blockSignals(False)
        if self._anbindungen:
            self.liste.setCurrentRow(min(max(merker, 0), len(self._anbindungen) - 1))
        self._zeige()

    def gewaehlt(self):
        zeile = self.liste.currentRow()
        if 0 <= zeile < len(self._anbindungen):
            return self._anbindungen[zeile]
        return None

    def paneltexte(self):
        """Nur für Tests: die Hinweistexte der gezeichneten Panels."""
        return list(self._texte)

    # ------------------------------------------------------------- Anzeige

    @staticmethod
    def _leere(anordnung):
        while anordnung.count():
            eintrag = anordnung.takeAt(0)
            widget = eintrag.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _zeige(self):
        self._leere(self.panelbereich)
        self._leere(self.knopfzeile)
        self.skriptknoepfe = []
        self._texte = []
        anbindung = self.gewaehlt()
        if anbindung is None:
            self.hinweis.setText("")
            return

        if anbindung.vorhanden:
            self.hinweis.setText(str(anbindung.quelle))
        else:
            self.hinweis.setText(
                f"Der Projektordner {anbindung.quelle} ist nicht mehr da. "
                "Die Panels bleiben sichtbar, die Skripte lassen sich nicht starten."
            )

        for nummer, skript in enumerate(anbindung.manifest.skripte):
            beschriftung = f"▶ {skript.name}"
            if skript.roboter:
                beschriftung += "  (mit Roboter)"
            knopf = QPushButton(beschriftung)
            knopf.setToolTip(skript.beschreibung or str(skript.datei))
            knopf.setEnabled(anbindung.vorhanden)
            knopf.clicked.connect(lambda _=False, s=skript: self._starte(s))
            self.knopfzeile.addWidget(knopf, nummer // KNOEPFE_JE_ZEILE,
                                      nummer % KNOEPFE_JE_ZEILE)
            self.skriptknoepfe.append(knopf)

        for panel in panelmodul.panels(anbindung):
            widget, text = panel_widget(panel, anbindung, self._palette)
            self.panelbereich.addWidget(widget)
            self._texte.append(text)

    # ------------------------------------------------------------- Aktionen

    def _anbinden(self):
        if self._ordner is None:
            self.meldung.emit("Wähle zuerst einen Arbeitsordner in „Projekte“.")
            return
        gewaehlt = QFileDialog.getExistingDirectory(self, "Projekt mit spotlab.toml wählen")
        if not gewaehlt:
            return
        try:
            speicher.binde_an(self._ordner, Path(gewaehlt))
        except SpotlabError as fehler:
            QMessageBox.warning(self, "spotlab", str(fehler))
            return
        self.aktualisiere()

    def _starte(self, skript):
        """Hier sitzt ein Mensch vor dem NOT-AUS — keine Trockenlauf-Schranke.

        Die Schranke gilt fuer den Agenten, nicht fuer den Menschen.
        """
        try:
            prozess = start_script(skript.datei, argumente=skript.argumente)
        except SpotlabError as fehler:
            self.meldung.emit(str(fehler))
            return
        self.lauf_gestartet.emit(prozess, str(skript.datei))
        self.lauf_laeuft(True)
        self._melde_roboterlauf(skript)

    def _melde_roboterlauf(self, skript):
        """Bei `roboter = true` gehoert der NOT-AUS in Sichtweite.

        Wer hier startet, will sonst die Panels sehen — aber ein Skript, das den
        echten Spot bewegt, ist der am wenigsten geprueften Startweg im ganzen
        Fenster. Da schlaegt Sicherheit die Bequemlichkeit.
        """
        if getattr(skript, "roboter", False):
            self.roboterlauf.emit()

    def lauf_laeuft(self, laeuft):
        """Stopp-Knopf zeigen oder verstecken."""
        self.stopp_knopf.setVisible(bool(laeuft))
