"""Das eigene Fenster fuer den virtuellen Lauf -- die Turtle-Ansicht.

Warum ein EIGENES Fenster und keine weitere Ansicht: der Schueler soll seinen
Code sehen, waehrend Spot faehrt. Ein Stapel umschaltbarer Ansichten kann genau
das nicht -- dort ist entweder der Code sichtbar oder der Raum.

Es gilt dieselbe Regel wie ueberall unter gui/: kein bosdyn, kein
`spotlab.backends`. Gezeichnet wird, was im Lauf-Verzeichnis steht; die
Geometrie kommt aus `welt.raum` (reine Standardbibliothek).

Der Stopp-Knopf STOPPT NICHT SELBST. Er meldet den Wunsch, und das Hauptfenster
reicht ihn an LiveView.stoppe() weiter -- wie der Stopp im Editor. Der
freundliche Stopp haengt am Lauf-Verzeichnis, das nur die Live-Ansicht vom
Watcher bekommt, und genau EIN Lauf ist der, auf den Stopp und NOT-AUS zeigen.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.raumplot import RaumPlot
from spotlab.welt.raum import raum_laden

TITEL = "Übungsraum — spotlab"


class Uebungsfenster(QWidget):
    stopp_gewuenscht = Signal()
    video_gewuenscht = Signal(str)          # Lauf-Verzeichnis

    def __init__(self, palette, parent=None):
        # Ohne Elternteil: ein eigenes Fenster im Fensterwechsler, das der
        # Schueler neben den Editor legen kann.
        super().__init__(parent)
        self._p = palette
        self._arbeitsordner = None
        self.setWindowTitle(TITEL)
        # Breiter als hoch: die Vorlagen sind Zimmer (9 x 5 m). Quadratisch
        # blieb ueber und unter der Zeichnung die halbe Flaeche leer.
        self.resize(760, 520)

        self.plot = RaumPlot(palette)
        # Das gerenderte Zimmer des MuJoCo-Backends. Versteckt, bis ein Bild
        # da ist -- der 2D-Sim liefert keines, und ein leerer Rahmen saehe
        # aus wie ein Fehler.
        self.bild = QLabel()
        self.bild.setAlignment(Qt.AlignCenter)
        self.bild.hide()
        self.kopf = QLabel("Kein Lauf.")
        self.zeile = QLabel("")
        self.zeile.setObjectName("Gedaempft")
        self.zeile.setWordWrap(True)
        self.stopp = QPushButton("■ Stopp")
        self.stopp.setEnabled(False)
        self.stopp.clicked.connect(self.stopp_gewuenscht.emit)
        # Erst nach dem Lauf: das Video entsteht aus der Aufzeichnung, nicht
        # aus dem, was gerade auf dem Bildschirm ist.
        self._lauf = None
        self._videopfad = None
        self.video = QPushButton("🎬 Video speichern")
        self.video.hide()
        self.video.clicked.connect(self._video_anfordern)
        self.video_oeffnen = QPushButton("Video öffnen")
        self.video_oeffnen.hide()
        self.video_oeffnen.clicked.connect(self._video_oeffnen)

        unten = QHBoxLayout()
        unten.addWidget(self.zeile, 1)
        unten.addWidget(self.video_oeffnen)
        unten.addWidget(self.video)
        unten.addWidget(self.stopp)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(self.kopf)
        anordnung.addWidget(self.bild)
        anordnung.addWidget(self.plot, 1)
        anordnung.addLayout(unten)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = pfad

    def beginne(self, raum=None, start=None, titel=""):
        """Ein neuer Lauf faengt an: Raum stellen, Spur leeren, Stopp scharf."""
        self.plot.setze_raum(raum)
        self.plot.setze_anstoesse([])
        self.plot.setze_start(start if start else (raum.start if raum else None))
        self.kopf.setText(titel or "Läuft…")
        self.zeile.setText("")
        self.stopp.setEnabled(True)
        self.bild.hide()                   # das Bild des letzten Laufs gehoert nicht zum neuen
        self._lauf = None
        self._videopfad = None
        self.video.hide()
        self.video_oeffnen.hide()

    def setze_raum_name(self, name):
        """Den Raum aus dem `verbunden`-Ereignis nachziehen.

        Das Ereignis ist die einzige Quelle, die sagt, worin das Programm
        WIRKLICH gefahren ist -- ein Skript darf `connect(raum=...)` selbst
        nennen, und dann steht in der GUI etwas anderes.
        Ein unbekannter Name darf das Fenster nicht umbringen: dann bleibt die
        Zeichnung leer, statt dass der Lauf unsichtbar abbricht.
        KEIN Name heisst: der Lauf faehrt in keinem Raum. Dann muss die
        Vorbelegung aus der Ansicht weg -- am 06.09.2026 zeigte sie die
        rekonstruierten Katakomben, waehrend MuJoCo auf leerem Boden fuhr.
        """
        if not name:
            self.plot.setze_raum(None)
            self.zeile.setText(
                "Dieser Lauf fährt in keinem Raum (das Ereignis „verbunden“ nennt keinen). "
                "Im Raumeditor einen Raum speichern, dann neu starten."
            )
            return
        try:
            raum = raum_laden(name, workspace=self._arbeitsordner)
        except Exception as fehler:
            self.zeile.setText(f"Raum „{name}“ liess sich nicht laden: {fehler}")
            return
        self.plot.setze_raum(raum)
        # Den Start NUR setzen, solange noch nichts gefahren ist: das
        # `verbunden`-Ereignis trifft erst nach den ersten Posen ein, und
        # `setze_start` leert die Spur. Sonst entstuende ein Strich von der
        # Schablonenposition zur echten -- ein Weg, den Spot nie gefahren ist.
        if not self.plot.spur():
            self.plot.setze_start(raum.start)

    # ---------------------------------------------------------------- Lauf

    def zeige_pose(self, x, y, grad=None):
        self.plot.haenge_pose_an(x, y, grad)

    def zeige_anstoss(self, x, y):
        self.plot.setze_anstoesse([*self.plot.anstoesse(), (x, y)])

    def zeige_ansicht(self, pfad):
        """Das gerenderte Zimmer -- aus dem Lauf-Verzeichnis, wie alle Live-Daten."""
        pixmap = QPixmap(str(pfad))
        if pixmap.isNull():
            return                         # halb geschrieben? naechster Takt bringt es
        breite = max(320, min(self.width() - 24, 640))
        self.bild.setPixmap(pixmap.scaledToWidth(breite, Qt.SmoothTransformation))
        self.bild.show()

    def zeige_ausgabe(self, zeile):
        """Nur die letzte Zeile. Die volle Ausgabe steht in der Ansicht „Code";
        hier geht es darum, dass ein Traceback nicht unsichtbar bleibt."""
        self.zeile.setText(zeile)

    def beendet(self, text="", lauf=None):
        self.stopp.setEnabled(False)
        self.kopf.setText("Fertig.")
        if text:
            self.zeile.setText(text)
        if lauf is not None:
            self._lauf = str(lauf)
            self.video.show()

    # --------------------------------------------------------------- Video

    def _video_anfordern(self):
        if self._lauf:
            self.video_gewuenscht.emit(self._lauf)

    def zeige_video_stand(self, text, pfad=None):
        """Fortschritt oder Ergebnis des Renderns -- vom Hauptfenster gemeldet."""
        self.zeile.setText(text)
        self._videopfad = Path(pfad) if pfad else None
        self.video_oeffnen.setVisible(self._videopfad is not None)

    def _video_oeffnen(self):
        if self._videopfad is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._videopfad)))
