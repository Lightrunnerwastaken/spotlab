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

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.liveplot import LiveRaumPlot
from spotlab.record import fahrt, kamera
from spotlab.welt.raum import raum_laden

ZOOM_STUFE = 1.25            # je Rad-Raste
FAHRT_TAKT_MS = 200          # solange eine Taste gedrueckt ist: den Zeitstempel auffrischen
FAHRT_HINWEIS = "Fahren: W/S vor und zurück · A/D seitwärts · Q/E drehen · Leertaste hält"


class _Ansichtsbild(QLabel):
    """Das gerenderte Zimmer; das Mausrad darueber meldet Zoom-Stufen."""

    gezoomt = Signal(int)    # +1 naeher, -1 weiter

    def wheelEvent(self, ereignis):
        delta = ereignis.angleDelta().y()
        if delta:
            self.gezoomt.emit(1 if delta > 0 else -1)
        ereignis.accept()

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

        self.plot = LiveRaumPlot(palette)
        # Das gerenderte Zimmer des MuJoCo-Backends. Versteckt, bis ein Bild
        # da ist -- der 2D-Sim liefert keines, und ein leerer Rahmen saehe
        # aus wie ein Fehler.
        self.bild = _Ansichtsbild()
        self.bild.setAlignment(Qt.AlignCenter)
        self.bild.hide()
        self.bild.gezoomt.connect(self._zoome)
        # Kamerawunsch fuer die Zimmeransicht: ueber Laeufe hinweg gemerkt und je
        # Lauf als kamera.json ins Lauf-Verzeichnis geschrieben (record/kamera.py).
        self._kamera_modus, self._kamera_zoom = kamera.VORGABE_MODUS, kamera.VORGABE_ZOOM
        self._lauf_dir = None
        self.verfolgen = QPushButton("Verfolgen")
        self.verfolgen.setCheckable(True)
        self.verfolgen.setToolTip("Kamera schräg hinter Spot; das Mausrad über dem Bild zoomt")
        self.verfolgen.hide()
        self.verfolgen.toggled.connect(self._verfolgen_umgeschaltet)
        # Fahrmodus (Knopf „Fahren" im Raumeditor): die Tasten hier werden
        # fahrt.json im Lauf-Verzeichnis, fahren.py liest sie (record/fahrt.py).
        self._fahrt = False
        self._tasten = set()
        self._lauf_dir_fahrt = None
        self.fahrt_zeile = QLabel(FAHRT_HINWEIS)
        self.fahrt_zeile.setObjectName("Gedaempft")
        self.fahrt_zeile.hide()
        self._fahrt_takt = QTimer(self)
        self._fahrt_takt.setInterval(FAHRT_TAKT_MS)
        self._fahrt_takt.timeout.connect(self._fahrt_schreiben)
        self.setFocusPolicy(Qt.StrongFocus)
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

        # Hoehe und Neigung des Laufs -- leer, solange der Lauf nichts meldet.
        self.hoehe = QLabel("")
        self.hoehe.setObjectName("hoehe")
        unten = QHBoxLayout()
        unten.addWidget(self.zeile, 1)
        unten.addWidget(self.hoehe)
        unten.addWidget(self.verfolgen)
        unten.addWidget(self.video_oeffnen)
        unten.addWidget(self.video)
        unten.addWidget(self.stopp)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(self.kopf)
        anordnung.addWidget(self.fahrt_zeile)
        anordnung.addWidget(self.bild)
        anordnung.addWidget(self.plot, 1)
        anordnung.addLayout(unten)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = pfad

    def beginne(self, raum=None, start=None, titel="", lauf_dir=None, fahrt=False):
        """Ein neuer Lauf faengt an: Raum stellen, Spur leeren, Stopp scharf.

        `fahrt`: der Fahrmodus -- Tasten fahren, die Kamera folgt. `lauf_dir` kennt
        die App erst, wenn der Watcher den Lauf meldet (`setze_lauf_dir`); die
        Tests geben es gleich mit.
        """
        self.plot.setze_raum(raum)
        self.plot.setze_anstoesse([])
        self.plot.setze_start(start if start else (raum.start if raum else None))
        self.kopf.setText(titel or "Läuft…")
        self.zeile.setText("")
        self.hoehe.setText("")
        self.stopp.setEnabled(True)
        self.bild.hide()                   # das Bild des letzten Laufs gehoert nicht zum neuen
        self.verfolgen.hide()
        self._lauf_dir = None
        self._lauf = None
        self._fahrt = bool(fahrt)
        self._tasten = set()
        self._fahrt_takt.stop()
        self.fahrt_zeile.setVisible(self._fahrt)
        self._lauf_dir_fahrt = Path(lauf_dir) if lauf_dir else None
        if self._fahrt:
            self.verfolgen.setChecked(True)
            self._tastatur_greifen()
        else:
            self._tastatur_loslassen()
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

    def zeige_pose(self, x, y, grad=None, z=None, nick=None):
        """`z` ist die Koerperhoehe aus dem Zustand, `nick` in Grad (Nase hoch negativ)."""
        self.plot.haenge_pose_an(x, y, grad)
        if z is None:
            self.hoehe.setText("")
        else:
            text = f"Höhe {z:.2f} m"
            if nick is not None:
                text += f" · Neigung {nick:.0f}°"
            self.hoehe.setText(text)

    def zeige_anstoss(self, x, y):
        self.plot.setze_anstoesse([*self.plot.anstoesse(), (x, y)])

    def zeige_ansicht(self, pfad):
        """Das gerenderte Zimmer -- aus dem Lauf-Verzeichnis, wie alle Live-Daten."""
        # Gleicher Dateiname mit neuen Bytes: den dateibasierten QPixmap-Cache
        # umgehen. Das File ist vor dem Dekodieren wieder geschlossen.
        try:
            daten = Path(pfad).read_bytes()
        except OSError:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(daten)
        if pixmap.isNull():
            return                         # halb geschrieben? naechster Takt bringt es
        breite = max(320, min(self.width() - 24, 640))
        self.bild.setPixmap(pixmap.scaledToWidth(breite, Qt.SmoothTransformation))
        self.bild.show()
        if self._lauf_dir is None:
            # Das erste Bild nennt das Lauf-Verzeichnis: den gemerkten Wunsch dorthin.
            self._lauf_dir = Path(pfad).parent
            self._kamera_schreiben()
        self.verfolgen.show()

    # -------------------------------------------------------------- Kamera

    def _kamera_schreiben(self):
        if self._lauf_dir is None:
            return
        try:
            kamera.schreibe(self._lauf_dir, self._kamera_modus, self._kamera_zoom)
        except OSError:
            pass                           # ein Kamerawunsch darf nichts anhalten

    def _verfolgen_umgeschaltet(self, an):
        self._kamera_modus = "verfolgen" if an else kamera.VORGABE_MODUS
        self._kamera_schreiben()

    def _zoome(self, richtung):
        faktor = ZOOM_STUFE if richtung > 0 else 1 / ZOOM_STUFE
        unten, oben = kamera.ZOOM_BEREICH
        self._kamera_zoom = min(oben, max(unten, self._kamera_zoom * faktor))
        self._kamera_schreiben()

    # -------------------------------------------------------------- Fahren

    _TASTEN = {Qt.Key_W: "w", Qt.Key_A: "a", Qt.Key_S: "s", Qt.Key_D: "d",
               Qt.Key_Q: "q", Qt.Key_E: "e"}

    def keyPressEvent(self, ereignis):
        if not self._fahrt or ereignis.isAutoRepeat():
            return super().keyPressEvent(ereignis)
        taste = ereignis.key()
        if taste in (Qt.Key_Space, Qt.Key_Escape):
            self._tasten.clear()
        elif taste in self._TASTEN:
            self._tasten.add(self._TASTEN[taste])
        else:
            return super().keyPressEvent(ereignis)
        self._fahrt_schreiben()
        ereignis.accept()

    def keyReleaseEvent(self, ereignis):
        if not self._fahrt or ereignis.isAutoRepeat() or ereignis.key() not in self._TASTEN:
            return super().keyReleaseEvent(ereignis)
        self._tasten.discard(self._TASTEN[ereignis.key()])
        self._fahrt_schreiben()
        ereignis.accept()

    def _fahrt_schreiben(self):
        """fahrt.json mit den Tasten von jetzt; der Takt frischt den Zeitstempel auf,
        solange etwas gedrueckt ist (Totmannschalter in record/fahrt.py)."""
        if self._tasten:
            if not self._fahrt_takt.isActive():
                self._fahrt_takt.start()
        else:
            self._fahrt_takt.stop()
        if self._lauf_dir_fahrt is None:
            return
        vx, vy, wz = fahrt.befehl_aus_tasten(self._tasten)
        try:
            fahrt.schreibe(self._lauf_dir_fahrt, vx, vy, wz)
        except OSError:
            pass                           # ein Fahrwunsch darf nichts anhalten

    def zeige_ausgabe(self, zeile):
        """Nur die letzte Zeile. Die volle Ausgabe steht in der Ansicht „Code";
        hier geht es darum, dass ein Traceback nicht unsichtbar bleibt."""
        self.zeile.setText(zeile)

    def setze_lauf_dir(self, pfad):
        """Das Lauf-Verzeichnis, sobald der Watcher es kennt: Kamera- und Fahrwunsch dorthin."""
        self._lauf_dir_fahrt = Path(pfad)
        if self._lauf_dir is None:
            self._lauf_dir = Path(pfad)
            self._kamera_schreiben()
        if self._fahrt:
            self._fahrt_schreiben()

    def _tastatur_greifen(self):
        """Im Fahrmodus bekommt dieses Fenster alle Tasten der App -- egal welches
        Widget den Fokus hat; sonst kam W bei niemandem an, und die Leertaste
        drueckte den fokussierten Stopp-Knopf. Nur ein sichtbares Fenster kann greifen."""
        if self._fahrt and self.isVisible():
            self.grabKeyboard()

    def _tastatur_loslassen(self):
        if QWidget.keyboardGrabber() is self:
            self.releaseKeyboard()

    def showEvent(self, ereignis):
        super().showEvent(ereignis)
        self._tastatur_greifen()

    def hideEvent(self, ereignis):
        self._tastatur_loslassen()
        super().hideEvent(ereignis)

    def beendet(self, text="", lauf=None):
        self._fahrt_takt.stop()
        self._fahrt = False
        self._tastatur_loslassen()
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
