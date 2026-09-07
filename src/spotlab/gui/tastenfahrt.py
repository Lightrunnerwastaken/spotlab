"""Tasten -> `fahrt.json`: die eine Formulierung fuer Uebungsfenster und Ansicht „Fahren".

Haelt die gedrueckten Buchstaben, schreibt bei jeder Aenderung und alle
FAHRT_TAKT_MS, solange etwas gedrueckt ist (der Totmannschalter in
`record/fahrt.py` braucht frische Zeitstempel), und meldet den Befehl zur
Anzeige. Qt nur fuer Zeitgeber, Signal und die Tastennummern; die Belegung
selbst steht in `record/fahrt.py`, ohne Qt prueffbar.

`alle_los()` ist der Sicherheitsgriff: Reiterwechsel, verlorener Fenster-
fokus, Leertaste, Escape -- alles heisst „Spot steht", sofort geschrieben.
"""

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from spotlab.record import fahrt

FAHRT_TAKT_MS = 200          # solange eine Taste gedrueckt ist: den Zeitstempel auffrischen
TASTE_VON_QT = {Qt.Key_W: "w", Qt.Key_A: "a", Qt.Key_S: "s", Qt.Key_D: "d",
                Qt.Key_Q: "q", Qt.Key_E: "e"}
HALT_TASTEN = (Qt.Key_Space, Qt.Key_Escape)
STUFE_VON_QT = {Qt.Key_1: "langsam", Qt.Key_2: "normal", Qt.Key_3: "schnell"}
VORGABE_STUFE = "normal"


class Tastenfahrt(QObject):
    befehl = Signal(float, float, float)      # (vx, vy, wz) nach jedem Schreiben
    stufe_geaendert = Signal(str)             # Tempostufe, auch per Ziffer gewechselt

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aktiv = False
        self._tasten = set()
        self._lauf_dir = None
        self._stufe = VORGABE_STUFE
        self.takt = QTimer(self)
        self.takt.setInterval(FAHRT_TAKT_MS)
        self.takt.timeout.connect(self.schreibe)

    # ------------------------------------------------------------- Zustand

    @property
    def aktiv(self):
        return self._aktiv

    @property
    def tasten(self):
        return set(self._tasten)

    @property
    def lauf_dir(self):
        return self._lauf_dir

    @property
    def stufe(self):
        return self._stufe

    @property
    def faktor(self):
        return fahrt.faktor_der_stufe(self._stufe)

    def setze_stufe(self, name):
        """Tempostufe wechseln -- sofort geschrieben, damit eine gehaltene Taste
        nicht erst beim naechsten Takt langsamer wird."""
        fahrt.faktor_der_stufe(name)          # unbekannt -> ValueError, nichts geaendert
        self._stufe = name
        self.stufe_geaendert.emit(name)
        if self._aktiv:
            self.schreibe()

    def beginne(self, lauf_dir=None):
        """Ein Lauf faengt an. `lauf_dir` kennt die App oft erst spaeter (Watcher)."""
        self._aktiv = True
        self._tasten = set()
        self.takt.stop()
        self._lauf_dir = Path(lauf_dir) if lauf_dir else None

    def setze_lauf_dir(self, pfad):
        self._lauf_dir = Path(pfad)
        if self._aktiv:
            self.schreibe()

    def beende(self):
        """Tasten los, Stillstand geschrieben, danach schreibt nichts mehr."""
        if self._aktiv:
            self.alle_los()
        self._aktiv = False
        self.takt.stop()

    # -------------------------------------------------------------- Tasten

    def tastenereignis(self, ereignis, gedrueckt):
        """Ein QKeyEvent verarbeiten. True, wenn er zur Fahrt gehoerte (dann `accept`)."""
        if not self._aktiv or ereignis.isAutoRepeat():
            return False
        taste = ereignis.key()
        if gedrueckt and taste in HALT_TASTEN:
            self.alle_los()
            return True
        if taste in STUFE_VON_QT:
            if gedrueckt:
                self.setze_stufe(STUFE_VON_QT[taste])
                return True
            return False
        if taste not in TASTE_VON_QT:
            return False
        if gedrueckt:
            self.druecke(TASTE_VON_QT[taste])
        else:
            self.lasse_los(TASTE_VON_QT[taste])
        return True

    def druecke(self, name):
        self._tasten.add(name)
        self.schreibe()

    def lasse_los(self, name):
        self._tasten.discard(name)
        self.schreibe()

    def alle_los(self):
        self._tasten.clear()
        self.schreibe()

    # ----------------------------------------------------------- Schreiben

    def schreibe(self):
        if self._tasten:
            if not self.takt.isActive():
                self.takt.start()
        else:
            self.takt.stop()
        vx, vy, wz = fahrt.befehl_aus_tasten(self._tasten, faktor=self.faktor)
        if self._lauf_dir is not None:
            try:
                fahrt.schreibe(self._lauf_dir, vx, vy, wz)
            except OSError:
                pass                           # ein Fahrwunsch darf nichts anhalten
        self.befehl.emit(vx, vy, wz)
