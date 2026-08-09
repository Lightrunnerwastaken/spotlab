"""Der laufende Lauf: Ereignisse, Telemetrie, Bild, Ausgabe, Stopp.

Der freundliche Stopp schreibt nur eine Markierung — der Abtaster des Laufs
holt sie ab. Reagiert der Lauf nach ESKALATION_MS nicht, bietet die Ansicht
das harte Beenden an, statt kommentarlos zu erschlagen oder ewig zu warten.
"""

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.workshop.control import beende_hart, ist_aktiv, stoppe_freundlich

ESKALATION_MS = 3000


def _kachel(name):
    rahmen = QFrame()
    rahmen.setObjectName("Flaeche")
    wert = QLabel("—")
    wert.setObjectName("Kachelwert")
    beschriftung = QLabel(name)
    beschriftung.setObjectName("Kachelname")
    anordnung = QVBoxLayout(rahmen)
    anordnung.setContentsMargins(10, 7, 10, 7)
    anordnung.addWidget(beschriftung)
    anordnung.addWidget(wert)
    return rahmen, wert


class LiveView(QWidget):
    meldung = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lauf = None

        self.leer = QLabel(
            "Gerade läuft kein Programm.\n\n"
            "Starte eines unter „Projekte“ — oder drücke in VS Code F5. "
            "Beides wird hier angezeigt."
        )
        self.leer.setObjectName("Gedaempft")

        self.titel = QLabel("—")
        self.titel.setObjectName("Titel")
        self.stopp_knopf = QPushButton("Stopp")
        self.stopp_knopf.clicked.connect(self.stoppe)
        self.hart_knopf = QPushButton("Reagiert nicht — hart beenden")
        self.hart_knopf.clicked.connect(self.notaus)
        self.hart_knopf.hide()

        self.ereignisliste = QListWidget()
        self.ausgabe = QPlainTextEdit()
        self.ausgabe.setReadOnly(True)
        self.bild = QLabel("Kein Bild")
        self.bild.setObjectName("Flaeche")
        self.bild.setFixedWidth(240)
        self.bild.setMinimumHeight(160)

        pose, self.kachel_pose = _kachel("Pose x / y")
        tempo, self.kachel_tempo = _kachel("Tempo")
        fuesse, self.kachel_fuesse = _kachel("Füsse")
        akku, self.kachel_akku = _kachel("Akku")

        kopf = QHBoxLayout()
        kopf.addWidget(self.titel, 1)
        kopf.addWidget(self.hart_knopf)
        kopf.addWidget(self.stopp_knopf)

        mitte = QHBoxLayout()
        mitte.addWidget(self.ereignisliste, 1)
        mitte.addWidget(self.bild)

        kacheln = QHBoxLayout()
        for widget in (pose, tempo, fuesse, akku):
            kacheln.addWidget(widget)

        self.inhalt = QWidget()
        innen = QVBoxLayout(self.inhalt)
        innen.setContentsMargins(0, 0, 0, 0)
        innen.addLayout(kopf)
        innen.addLayout(mitte, 3)
        innen.addLayout(kacheln)
        innen.addWidget(QLabel("Ausgabe"))
        innen.addWidget(self.ausgabe, 2)
        self.inhalt.hide()

        aussen = QVBoxLayout(self)
        aussen.addWidget(self.leer)
        aussen.addWidget(self.inhalt)

        self._eskalation = QTimer(self)
        self._eskalation.setSingleShot(True)
        self._eskalation.setInterval(ESKALATION_MS)
        self._eskalation.timeout.connect(self._pruefe_eskalation)

    # ------------------------------------------------------------- Zustand

    def setze_lauf(self, verzeichnis, skript):
        self._lauf = Path(verzeichnis)
        self.titel.setText(f"{skript} — läuft")
        self.ereignisliste.clear()
        self.ausgabe.clear()
        self.bild.setText("Kein Bild")
        self.hart_knopf.hide()
        self.leer.hide()
        self.inhalt.show()

    def lauf_beendet(self):
        self._eskalation.stop()
        self.hart_knopf.hide()
        if self._lauf is not None:
            self.titel.setText(
                self.titel.text().replace("wird gestoppt", "beendet").replace("läuft", "beendet")
            )
        self._lauf = None

    # ------------------------------------------------------------- Anzeige

    def zeige_zustand(self, satz):
        daten = satz.get("daten", {})
        pose = daten.get("pose") or [0.0, 0.0, 0.0]
        tempo = daten.get("velocity") or [0.0, 0.0, 0.0]
        fuesse = daten.get("feet") or []
        akku = daten.get("battery")
        self.kachel_pose.setText(f"{pose[0]:.2f} / {pose[1]:.2f}")
        self.kachel_tempo.setText(f"{tempo[0]:.2f} m/s")
        self.kachel_fuesse.setText(" ".join("●" if f else "○" for f in fuesse) or "—")
        if akku is not None:
            self.kachel_akku.setText(f"{akku:.0f} %")

    def zeige_ereignis(self, satz):
        daten = satz.get("daten", {})
        beschreibung = daten.get("name") or daten.get("status") or ""
        self.ereignisliste.addItem(
            f"{satz.get('t', 0.0):7.2f} s  {satz.get('art', ''):<14} {beschreibung}"
        )
        self.ereignisliste.scrollToBottom()

    def zeige_bild(self, pfad):
        pixmap = QPixmap(str(pfad))
        if not pixmap.isNull():
            self.bild.setPixmap(pixmap.scaledToWidth(240))

    def zeige_ausgabe(self, zeile):
        self.ausgabe.appendPlainText(zeile)

    # ------------------------------------------------------------- Stoppen

    def stoppe(self):
        if self._lauf is None:
            self.meldung.emit("Es läuft gerade kein Programm.")
            return
        stoppe_freundlich(self._lauf)
        self.titel.setText(self.titel.text().replace("läuft", "wird gestoppt"))
        self._eskalation.start()

    def _pruefe_eskalation(self):
        if self._lauf is not None and ist_aktiv(self._lauf):
            self.hart_knopf.show()

    def notaus(self):
        """Harter Stopp. Meldet die Wahrheit, auch wenn sie unangenehm ist.

        `beende_hart` gibt aus zwei sehr verschiedenen Gründen False zurück: es
        war nichts mehr zu töten (harmlos), oder das Töten ist GESCHEITERT
        (Rechte, hängender Prozess). Die beiden zu verwechseln hiess, im
        gefährlicheren Fall Entwarnung zu geben, während der Roboter weiterfährt.
        """
        if self._lauf is None:
            self.meldung.emit("Es läuft gerade kein Programm.")
            return
        lief = ist_aktiv(self._lauf)
        if beende_hart(self._lauf):
            self.hart_knopf.hide()
            return
        if lief:
            # Kein Verstecken des Knopfes: er bleibt sichtbar zum Nachdrücken.
            self.meldung.emit(
                "Das Programm liess sich NICHT beenden. Drücke sofort den "
                "physischen Not-Aus am Tablet."
            )
            return
        self.meldung.emit("Der Lauf läuft nicht mehr.")
        self.hart_knopf.hide()
