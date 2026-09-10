"""Gehzeit — der Nachtrag im Fenster: ansehen, eintragen, löschen.

Der Versuch misst Zeiten; die Gruppengrösse trägt ein Mensch nach, nachdem er
den Abschnitt angesehen hat. Auf der Kommandozeile geht das über
`python -m spotlab.experiment.nachtrag <Lauf>`. Diese Ansicht ist dasselbe im
Fenster — dieselben Funktionen, nur mit den Bildern nebendran statt als
Dateipfade.

Sie liest und schreibt ausschliesslich Dateien im Lauf-Verzeichnis: die Tabelle
(`gehzeit/gehzeit.csv`), den Bildindex und die Bilder. Kein Roboter, kein Lease,
keine Protobufs — dieselbe Regel wie bei allen Ansichten (H1). Wo die Dateien
liegen, sagt `experiment/ablage.py`; was in ihnen steht, `experiment/tabelle.py`
und `experiment/nachtrag.py`. Hier steht nur die Haut.

DER STARTKNOPF STARTET PAKETCODE. `spotlab/workshop/gehzeit.py` hat dafür ein
Hauptprogramm, genau wie die Sonde. Die Kopie im Arbeitsordner
(`Beispiele/gehzeit.py`) kann ein Schüler bearbeiten — und dann startete ein
Knopf, der „Spot schaut nur zu" verspricht, etwas, das fährt. Zum Lesen und
Ändern ist die Kopie da, zum Klicken das Paket.

Der Lauf landet trotzdem unter `<Arbeitsordner>/Beispiele/runs/`: dort sucht
`laufsuche` (Läufe liegen in einem PROJEKT, nicht lose im Arbeitsordner), und
dort landet auch der Lauf, wenn jemand `Beispiele/gehzeit.py` aus dem Editor
startet. Zwei Wege, ein Ablageort.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spotlab.experiment import ablage, nachtrag, tabelle
from spotlab.laufsuche import lauf_verzeichnisse
from spotlab.workshop.beispiele import ORDNER as BEISPIELORDNER

# Der Pfad wird berechnet, nicht importiert — dieselbe Zurückhaltung wie bei der
# Sonde: die Ansicht bleibt frei von allem ausser Qt, Standardbibliothek und den
# reinen Dateimodulen des Versuchs.
GEHZEIT_SKRIPT = Path(__file__).resolve().parents[2] / "workshop" / "gehzeit.py"

SPALTEN = ("Nr", "Uhrzeit", "Gesehen", "Laufzeit", "Tempo", "Status", "Gruppe", "Klasse")
BILD_BREITE_PX = 420
MAX_GRUPPE = 40


def laeufe_mit_versuch(arbeitsordner):
    """Die Läufe, in denen eine Gehzeit-Tabelle liegt — jüngster zuerst.

    Über `laufsuche`, nicht über eine eigene Suche: wo Läufe liegen, entscheidet
    genau eine Stelle. Ein Arbeitsordner hat schnell Dutzende Läufe, und die
    allermeisten sind keine Messung.
    """
    if not arbeitsordner:
        return []
    gefunden = [p for p in lauf_verzeichnisse(arbeitsordner) if ablage.hat_versuch(p)]
    return sorted(gefunden, key=lambda p: p.name, reverse=True)


def _text(wert, einheit="", stellen=2):
    """Ein Messwert als Text — und `None` als Gedankenstrich, nie als 0."""
    if wert is None:
        return "—"
    return f"{wert:.{stellen}f}{einheit}"


def zeilen_aus(lauf):
    """Je Durchgang eine Zeile: die Texte für die Tabelle, dazu Bildzahl und Zeitfenster.

    Die Testtür dieser Ansicht — was hier steht, steht nachher im Fenster.
    """
    pfad = ablage.csv_pfad(lauf)
    if not pfad.is_file():
        return []
    # Der Bildindex wird EINMAL gelesen, nicht je Zeile: bei einer halben Stunde
    # Aufnahme und dreissig Durchgaengen waere das sonst hunderttausend
    # JSON-Zeilen, jedes Mal, wenn jemand etwas eintraegt.
    zeiten = nachtrag.bildzeiten(lauf)
    zeilen = []
    for zeile in tabelle.lies(pfad):
        grund = " ".join(zeile["gruende"])
        zeilen.append({
            "nummer": zeile["nummer"],
            "t_start": zeile["t_start"],
            "t_ende": zeile["t_ende"],
            "bilder": nachtrag.zaehle_bilder(zeiten, zeile["t_start"], zeile["t_ende"]),
            "texte": (
                str(zeile["nummer"]),
                zeile["uhrzeit"],
                str(zeile["personen"]),
                _text(zeile["laufzeit_s"], " s"),
                _text(zeile["tempo_m_s"], " m/s"),
                "gemessen" if zeile["gueltig"] else f"verworfen ({grund or '—'})",
                "" if zeile["gruppengroesse"] is None else str(zeile["gruppengroesse"]),
                zeile["klasse"],
            ),
        })
    return zeilen


class GehzeitView(QWidget):
    meldung = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._arbeitsordner = None
        self._lauf = None
        self._zeilen = []
        self._bilder = []
        self._bildnummer = 0
        # Austauschbar für den Test: ein Knopf, der wirklich einen Prozess
        # startet, gehört nicht in eine Testsuite — und ein modaler Dialog hielte
        # sie an.
        self._start = None
        self._frage = None

        self.starten = QPushButton("▶ Versuch starten")
        self.starten.setToolTip(
            "Startet die Messung. Spot bewegt sich dabei nicht und hält kein "
            "Lease — das Tablet darf jemand in der Hand behalten."
        )
        self.starten.clicked.connect(self._starte_versuch)

        self.auswahl = QComboBox()
        self.auswahl.currentIndexChanged.connect(self._auswahl_geaendert)
        self.aktualisieren = QPushButton("Aktualisieren")
        self.aktualisieren.clicked.connect(self._suche_laeufe)
        self.hinweis = QLabel("kein Arbeitsordner gesetzt")
        self.hinweis.setObjectName("Gedaempft")

        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(list(SPALTEN))
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabelle.itemSelectionChanged.connect(self._zeile_gewaehlt)

        self.bild = QLabel("—")
        self.bild.setAlignment(Qt.AlignCenter)
        self.bild.setMinimumWidth(BILD_BREITE_PX)
        self.zurueck = QPushButton("◀")
        self.vor = QPushButton("▶")
        self.zurueck.clicked.connect(self.rueckwaerts)
        self.vor.clicked.connect(self.weiter)
        self.bildzeile = QLabel("")
        self.bildzeile.setObjectName("Gedaempft")

        self.klasse = QLineEdit()
        self.klasse.setPlaceholderText("Klasse, z. B. 4bG")
        self.gruppe = QSpinBox()
        self.gruppe.setRange(1, MAX_GRUPPE)
        self.eintragen = QPushButton("Eintragen")
        self.eintragen.clicked.connect(self._trage_ein)

        self.loeschen = QPushButton("Bilder dieses Durchgangs löschen")
        self.loeschen.clicked.connect(self._loesche_gewaehlte)
        self.loeschen_alle = QPushButton("Alle Bilder dieses Laufs löschen")
        self.loeschen_alle.clicked.connect(self._loesche_alle)
        for knopf in (self.loeschen, self.loeschen_alle):
            knopf.setToolTip(
                "Aufnahmen von Mitschülern, gemacht für genau eine Frage. Ist "
                "sie beantwortet, dürfen sie weg."
            )

        kopf = QHBoxLayout()
        kopf.addWidget(self.starten)
        kopf.addWidget(QLabel("Lauf"))
        kopf.addWidget(self.auswahl, 1)
        kopf.addWidget(self.aktualisieren)

        bildsteuerung = QHBoxLayout()
        bildsteuerung.addWidget(self.zurueck)
        bildsteuerung.addWidget(self.bildzeile, 1)
        bildsteuerung.addWidget(self.vor)

        eintrag = QHBoxLayout()
        eintrag.addWidget(QLabel("Klasse"))
        eintrag.addWidget(self.klasse, 1)
        eintrag.addWidget(QLabel("Gruppengrösse"))
        eintrag.addWidget(self.gruppe)
        eintrag.addWidget(self.eintragen)

        rechts = QVBoxLayout()
        rechts.addWidget(self.bild, 1)
        rechts.addLayout(bildsteuerung)
        rechts.addLayout(eintrag)
        rechts.addWidget(self.loeschen)
        rechts.addWidget(self.loeschen_alle)

        mitte = QHBoxLayout()
        mitte.addWidget(self.tabelle, 3)
        mitte.addLayout(rechts, 2)

        aussen = QVBoxLayout(self)
        aussen.addLayout(kopf)
        aussen.addWidget(self.hinweis)
        aussen.addLayout(mitte, 1)

    # ------------------------------------------------------------ Arbeitsordner

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = Path(pfad) if pfad else None
        self._suche_laeufe()

    def _suche_laeufe(self):
        laeufe = laeufe_mit_versuch(self._arbeitsordner)
        self.auswahl.blockSignals(True)
        self.auswahl.clear()
        for lauf in laeufe:
            self.auswahl.addItem(lauf.name, str(lauf))
        self.auswahl.blockSignals(False)
        if laeufe:
            self.auswahl.setCurrentIndex(0)
            self.lade(laeufe[0])
            return
        self._lauf = None
        self._zeige_zeilen([])
        self.hinweis.setText(
            "kein Arbeitsordner gesetzt" if self._arbeitsordner is None
            else "Noch keine Gehzeit-Messung in diesem Arbeitsordner."
        )

    def _auswahl_geaendert(self, _index):
        pfad = self.auswahl.currentData()
        if pfad:
            self.lade(Path(pfad))

    # ------------------------------------------------------------------ Lesen

    def lade(self, lauf):
        """Die Durchgänge eines Laufs anzeigen."""
        self._lauf = Path(lauf)
        self._zeige_zeilen(zeilen_aus(self._lauf))
        self.hinweis.setText(self._streckentext())

    def _streckentext(self):
        """Was Spot als Strecke gemessen hat — samt Streuung.

        Die Zahl steht hier und nicht nur in der Datei: an ihr hängt jedes Tempo
        in der Tabelle, und wie stark die Einzelmessungen streuten, gehört
        daneben statt in eine Fussnote.
        """
        import json

        pfad = ablage.strecke_pfad(self._lauf)
        if not pfad.is_file():
            return "Für diesen Lauf ist keine Strecke aufgeschrieben."
        try:
            gemessen = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as fehler:
            return f"Strecke nicht lesbar: {fehler}"
        return (
            f"Strecke {gemessen.get('laenge_m', 0):.2f} m zwischen Tag "
            f"{gemessen.get('tag_start')} und Tag {gemessen.get('tag_ziel')} "
            f"(Streuung {gemessen.get('streuung_m', 0):.2f} m, "
            f"{gemessen.get('proben', 0)} Abtastungen)"
        )

    def _zeige_zeilen(self, zeilen):
        self._zeilen = zeilen
        self.tabelle.setRowCount(len(zeilen))
        for nummer, zeile in enumerate(zeilen):
            for spalte, text in enumerate(zeile["texte"]):
                self.tabelle.setItem(nummer, spalte, QTableWidgetItem(text))
        self._setze_bilder([])

    # ------------------------------------------------------------------ Bilder

    def waehle_zeile(self, nummer):
        self.tabelle.selectRow(nummer)

    def _gewaehlt(self):
        zeilen = {i.row() for i in self.tabelle.selectedIndexes()}
        if not zeilen or self._lauf is None:
            return None
        return self._zeilen[min(zeilen)]

    def _zeile_gewaehlt(self):
        zeile = self._gewaehlt()
        if zeile is None:
            self._setze_bilder([])
            return
        self._setze_bilder(
            nachtrag.bilder_zu(self._lauf, zeile["t_start"], zeile["t_ende"])
        )

    def bilder(self):
        return list(self._bilder)

    def bildnummer(self):
        return self._bildnummer

    def weiter(self):
        self._blaettere(+1)

    def rueckwaerts(self):
        self._blaettere(-1)

    def _blaettere(self, schritt):
        if not self._bilder:
            return
        self._bildnummer = (self._bildnummer + schritt) % len(self._bilder)
        self._zeige_bild()

    def _setze_bilder(self, pfade):
        self._bilder = list(pfade)
        self._bildnummer = 0
        self._zeige_bild()

    def _zeige_bild(self):
        if not self._bilder:
            self.bild.setPixmap(QPixmap())
            self.bild.setText("keine Bilder zu diesem Durchgang")
            self.bildzeile.setText("")
            return
        pfad = self._bilder[self._bildnummer]
        # `read_bytes` + `loadFromData`, nie `QPixmap(pfad)`: Qts Dateicache
        # zeigte sonst ein altes Bild, wenn ein Name wiederkehrt.
        bild = QPixmap()
        try:
            bild.loadFromData(pfad.read_bytes())
        except OSError as fehler:
            self.bild.setPixmap(QPixmap())
            self.bild.setText(f"Bild nicht lesbar: {fehler}")
            return
        self.bild.setPixmap(bild.scaledToWidth(BILD_BREITE_PX, Qt.SmoothTransformation))
        self.bildzeile.setText(
            f"Bild {self._bildnummer + 1} von {len(self._bilder)}   {pfad.name}"
        )

    # --------------------------------------------------------------- Eintragen

    def _trage_ein(self):
        zeile = self._gewaehlt()
        if zeile is None:
            self.meldung.emit("Wähle links den Durchgang, den du eintragen willst.")
            return
        klasse = self.klasse.text().strip()
        try:
            nachtrag.trage_ein(
                self._lauf, zeile["nummer"],
                klasse=klasse or None, gruppengroesse=self.gruppe.value(),
            )
        except Exception as fehler:
            self.meldung.emit(f"Eintrag nicht gespeichert: {fehler}")
            return
        gemerkt = zeile["nummer"]
        self.lade(self._lauf)
        self._waehle_nummer(gemerkt)
        self.meldung.emit(
            f"Durchgang {gemerkt}: Gruppe {self.gruppe.value()}"
            + (f", Klasse {klasse}" if klasse else "")
        )

    def _waehle_nummer(self, nummer):
        for zeile, eintrag in enumerate(self._zeilen):
            if eintrag["nummer"] == nummer:
                self.tabelle.selectRow(zeile)
                return

    # ----------------------------------------------------------------- Löschen

    def loesche_gewaehlte(self):
        """Die Bilder des gewählten Durchgangs löschen. Gibt die Zahl zurück."""
        zeile = self._gewaehlt()
        if zeile is None:
            return 0
        weg = nachtrag.loesche_bilder(self._lauf, zeile["t_start"], zeile["t_ende"])
        gemerkt = zeile["nummer"]
        self.lade(self._lauf)
        self._waehle_nummer(gemerkt)
        return weg

    def loesche_alle(self):
        """Alle Bilder dieses Laufs löschen. Gibt die Zahl zurück."""
        if self._lauf is None:
            return 0
        weg = nachtrag.loesche_alle_bilder(self._lauf)
        self.lade(self._lauf)
        return weg

    def _bestaetigt(self, text):
        """Löschen ist endgültig — vorher wird gefragt, wie auf der Kommandozeile."""
        if self._frage is not None:
            return bool(self._frage(text))
        antwort = QMessageBox.question(
            self, "Bilder löschen", text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        return antwort == QMessageBox.Yes

    def _loesche_gewaehlte(self):
        zeile = self._gewaehlt()
        if zeile is None:
            self.meldung.emit("Wähle links den Durchgang, dessen Bilder weg sollen.")
            return
        anzahl = len(self._bilder)
        if not self._bestaetigt(
            f"{anzahl} Bilder von Durchgang {zeile['nummer']} endgültig löschen?"
        ):
            self.meldung.emit("Nichts gelöscht.")
            return
        self.meldung.emit(f"{self.loesche_gewaehlte()} Bilder gelöscht.")

    def _loesche_alle(self):
        if self._lauf is None:
            self.meldung.emit("Kein Lauf gewählt.")
            return
        if not self._bestaetigt(
            "Alle Bilder dieses Laufs endgültig löschen? Die gemessenen Zeiten "
            "bleiben — nur die Aufnahmen gehen weg."
        ):
            self.meldung.emit("Nichts gelöscht.")
            return
        self.meldung.emit(f"{self.loesche_alle()} Bilder gelöscht.")

    # ----------------------------------------------------------------- Starten

    def _starte_versuch(self):
        if self._arbeitsordner is None:
            self.meldung.emit(
                "Es ist kein Arbeitsordner gesetzt. Wähle einen in der Ansicht "
                "'Projekte' — dorthin schreibt der Versuch seinen Lauf."
            )
            return
        starte = self._start
        if starte is None:
            from spotlab.workshop.launcher import start_script

            starte = start_script
        runs = self._arbeitsordner / BEISPIELORDNER / "runs"
        try:
            prozess = starte(GEHZEIT_SKRIPT, argumente=["--runs", str(runs)])
        except Exception as fehler:
            self.meldung.emit(f"Der Versuch liess sich nicht starten: {fehler}")
            return
        self.meldung.emit(
            "Gehzeit läuft — Spot misst die Strecke und schaut dann zu. "
            "Kein Lease, er bewegt sich nicht."
        )
        return prozess
