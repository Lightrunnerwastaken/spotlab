"""Die Ansicht „Fahren": den echten Spot live ueber W A S D Q E fahren.

Kein eigener Weg zum Roboter: der Knopf startet `Beispiele/fahren.py` ueber die
App -- derselbe eine Startweg wie „Starten" im Editor, mit dem Backend „real"
(`app.py::_starte_fahrt`), also Lease, Not-Aus-Endpunkt, Geschwindigkeits-
deckel aus `config.toml` und die Aufzeichnung wie bei jedem Programm. Die
Tasten gehen als `fahrt.json` ins Lauf-Verzeichnis (`gui/tastenfahrt.py`,
`record/fahrt.py`); `fahren.py` liest sie mit 20 Hz. **Ein Befehl aelter als
eine halbe Sekunde heisst Stopp** -- und jedes Kommando traegt eine Endzeit
von rund einer Sekunde: stirbt die GUI oder der Lauf, steht der Roboter.

Die Tastatur gehoert dem Tab nur, solange er sichtbar ist und der Lauf lebt.
Reiterwechsel oder ein Fenster, das den Fokus verliert (Alt-Tab mit gehaltenem
W), lassen alle Tasten los und schreiben Stillstand -- Qt schickt in dem Fall
kein KeyRelease mehr, und der Takt frischte den letzten Befehl sonst blind auf.
Stopp und NOT-AUS delegieren an die Live-Ansicht bzw. den Kopf: dasselbe
Objekt mit demselben Zustand, kein zweiter Weg.

Diese Ansicht importiert weder `bosdyn` noch `spotlab.backends`.
"""

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.tastenfahrt import Tastenfahrt
from spotlab.record import fahrt

VORGABE_STUFE = "langsam"             # am echten Roboter gemächlich anfangen

HINWEIS = (
    'Startet das Programm „fahren.py" aus dem Projekt Beispiele am ECHTEN Spot — mit Lease, '
    "Not-Aus-Endpunkt und den Tempogrenzen aus der Konfiguration, aufgezeichnet wie jeder Lauf. "
    "Tasten: W/S vor und zurück · A/D seitwärts · Q/E drehen · 1/2/3 Tempo · "
    "Leertaste oder Esc hält. "
    "Losgelassen heisst Stopp (Totmannschalter, ½ s); stirbt die GUI, steht Spot nach einer "
    "Sekunde. Freifläche, Aufsicht, Tablet mit Not-Aus in Reichweite — "
    "vor dem ersten Mal Abnahmepunkt A1 (docs/ABNAHME.md)."
)
BELEGUNG = "W A S D Q E  ·  1 2 3 Tempo  ·  Leertaste hält"
BILD_BREITE_PX = 640          # die beiden Frontbilder nebeneinander


class FahrenView(QWidget):
    fahrt_gewuenscht = Signal()        # beginnen oder beenden -- die App entscheidet (ein Lauf)
    stopp_gewuenscht = Signal()
    meldung = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._laeuft = False

        titel = QLabel("Den echten Spot über die Tastatur fahren")
        titel.setObjectName("Titel")
        hinweis = QLabel(HINWEIS)
        hinweis.setObjectName("Gedaempft")
        hinweis.setWordWrap(True)

        self.start = QPushButton("🎮 Fahrt beginnen")
        self.start.clicked.connect(self._start_geklickt)
        self.stufe = QComboBox()
        self.stufe.setToolTip("Tempostufe — auch mit den Tasten 1, 2, 3 während der Fahrt")
        for name, faktor in fahrt.STUFEN:
            self.stufe.addItem(f"{name.capitalize()} — {fahrt.TEMPO_M_S * faktor:.1f} m/s", name)
        self.stufe.setCurrentIndex(self.stufe.findData(VORGABE_STUFE))
        self.stufe.currentIndexChanged.connect(self._stufe_gewaehlt)
        self.stopp = QPushButton("■ Stopp")
        self.stopp.setEnabled(False)
        self.stopp.clicked.connect(self._stopp_geklickt)

        knoepfe = QHBoxLayout()
        knoepfe.addWidget(self.start)
        knoepfe.addWidget(self.stopp)
        knoepfe.addWidget(QLabel("Tempo"))
        knoepfe.addWidget(self.stufe)
        knoepfe.addStretch(1)

        # Der Blick nach vorn: `workshop/blick.py` schreibt `ansicht.jpg` aus den
        # beiden Frontkameras ins Lauf-Verzeichnis, der Watcher meldet jede
        # Aenderung. Die GUI holt sich nichts vom Roboter -- die Platte bleibt
        # der einzige Kanal.
        self.bild = QLabel("Kein Bild — der Blick kommt, sobald der Lauf steht.")
        self.bild.setObjectName("Gedaempft")
        self.bild.setAlignment(Qt.AlignCenter)
        self.bild.setMinimumHeight(200)

        self.belegung = QLabel(BELEGUNG)
        self.belegung.setObjectName("Kachelname")
        self.gedrueckt = QLabel("—")
        self.gedrueckt.setObjectName("Kachelwert")
        self.befehl_zeile = QLabel("Spot steht.")
        self.zustand = QLabel("Kein Lauf.")
        self.zustand.setObjectName("Gedaempft")

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(titel)
        anordnung.addWidget(hinweis)
        anordnung.addLayout(knoepfe)
        anordnung.addWidget(self.bild, 1)
        anordnung.addWidget(self.belegung)
        anordnung.addWidget(self.gedrueckt)
        anordnung.addWidget(self.befehl_zeile)
        anordnung.addWidget(self.zustand)
        anordnung.addStretch(1)

        self.tastenfahrt = Tastenfahrt(self)
        self.tastenfahrt.befehl.connect(self._zeige_befehl)
        self.tastenfahrt.stufe_geaendert.connect(self._zeige_stufe)
        self.tastenfahrt.setze_stufe(VORGABE_STUFE)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._app_zustand)

    # ------------------------------------------------------------- Zustand

    def laeuft(self):
        return self._laeuft

    def lauf_beginnt(self, lauf_dir, name="fahren.py"):
        """Der Watcher hat den Lauf gemeldet: ab jetzt fahren die Tasten."""
        self._laeuft = True
        self.tastenfahrt.beginne(lauf_dir)
        self.start.setText("■ Fahrt beenden")
        self.stopp.setEnabled(True)
        self.zustand.setText(f"{name} läuft — Tasten sind scharf.")
        self._tastatur_greifen()

    def lauf_beendet(self):
        self.tastenfahrt.beende()
        self._laeuft = False
        self._tastatur_loslassen()
        self.start.setText("🎮 Fahrt beginnen")
        self.stopp.setEnabled(False)
        self.gedrueckt.setText("—")
        self.befehl_zeile.setText("Spot steht.")
        self.zustand.setText("Kein Lauf.")
        self.bild.clear()
        self.bild.setText("Kein Bild — der Blick kommt, sobald der Lauf steht.")

    def zeige_ansicht(self, pfad):
        """Das neueste Kamerabild des Laufs (`ansicht.jpg`)."""
        pixmap = QPixmap(str(pfad))
        if pixmap.isNull():                      # halb geschriebene Datei: nicht leeren
            return
        self.bild.setPixmap(pixmap.scaledToWidth(BILD_BREITE_PX, Qt.SmoothTransformation))

    def zeige_zustand(self, satz):
        daten = satz.get("daten") or {}
        pose = daten.get("pose") or [0.0, 0.0, 0.0]
        tempo = daten.get("velocity") or [0.0, 0.0, 0.0]
        akku = daten.get("battery")
        text = (f"Position {pose[0]:.2f} / {pose[1]:.2f} m · Blick {math.degrees(pose[2]):.0f}° · "
                f"Tempo {tempo[0]:.2f} m/s")
        if akku is not None:
            text += f" · Akku {akku:.0f} %"
        self.zustand.setText(text)

    # -------------------------------------------------------------- Knoepfe

    def _start_geklickt(self):
        # Am `clicked`-Signal: Qt reicht `checked` herein, deshalb kein Parameter.
        self.fahrt_gewuenscht.emit()

    def _stopp_geklickt(self):
        self.tastenfahrt.alle_los()
        self.stopp_gewuenscht.emit()

    def _stufe_gewaehlt(self, _index):
        name = self.stufe.currentData()
        if name and name != self.tastenfahrt.stufe:
            self.tastenfahrt.setze_stufe(name)

    def _zeige_stufe(self, name):
        # Per Ziffer gewechselt: die Auswahl folgt, ohne noch einmal zu setzen.
        if self.stufe.currentData() != name:
            self.stufe.blockSignals(True)
            self.stufe.setCurrentIndex(self.stufe.findData(name))
            self.stufe.blockSignals(False)

    # -------------------------------------------------------------- Tasten

    def keyPressEvent(self, ereignis):
        if self.tastenfahrt.tastenereignis(ereignis, gedrueckt=True):
            ereignis.accept()
            return
        super().keyPressEvent(ereignis)

    def keyReleaseEvent(self, ereignis):
        if self.tastenfahrt.tastenereignis(ereignis, gedrueckt=False):
            ereignis.accept()
            return
        super().keyReleaseEvent(ereignis)

    def _zeige_befehl(self, vx, vy, wz):
        tasten = self.tastenfahrt.tasten
        self.gedrueckt.setText(" ".join(sorted(t.upper() for t in tasten)) if tasten else "—")
        teile = []
        if vx:
            teile.append(f"{'vor' if vx > 0 else 'zurück'} {abs(vx):.2f} m/s")
        if vy:
            teile.append(f"{'links' if vy > 0 else 'rechts'} {abs(vy):.2f} m/s")
        if wz:
            teile.append(f"drehen {'links' if wz > 0 else 'rechts'} {math.degrees(abs(wz)):.0f}°/s")
        self.befehl_zeile.setText(" · ".join(teile) if teile else "Spot steht.")

    def _app_zustand(self, zustand):
        # Alt-Tab mit gehaltener Taste: kein KeyRelease mehr -- also alle los.
        if zustand != Qt.ApplicationActive and self._laeuft:
            self.tastenfahrt.alle_los()

    # ------------------------------------------------------------ Tastatur

    def _tastatur_greifen(self):
        """Die Tasten gehoeren dem Tab, egal welches Widget den Fokus hat -- aber nur,
        solange er sichtbar ist und ein Lauf lebt."""
        if self._laeuft and self.isVisible():
            self.grabKeyboard()

    def _tastatur_loslassen(self):
        if QWidget.keyboardGrabber() is self:
            self.releaseKeyboard()

    def showEvent(self, ereignis):
        super().showEvent(ereignis)
        self._tastatur_greifen()

    def hideEvent(self, ereignis):
        # Reiterwechsel: Tasten los, Spot steht -- eine gehaltene Taste darf nicht
        # aus einem anderen Reiter heraus weiterfahren.
        self._tastatur_loslassen()
        if self._laeuft:
            self.tastenfahrt.alle_los()
        super().hideEvent(ereignis)
