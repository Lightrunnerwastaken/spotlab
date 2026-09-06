"""Den runs/-Ordner mitlesen und als Qt-Signale weitergeben.

Abgefragt statt QFileSystemWatcher: Anfügungen an eine offene Datei lösen
unter Windows keine verlässliche Verzeichnisbenachrichtigung aus, und 10 Hz
Anfügungen würden einen Ereignis-Beobachter überschwemmen. Ein 250-ms-Takt,
der nur die neuen Bytes liest, kostet praktisch nichts.

Die Logik steckt vollständig in RunScanner (Qt-frei, geprüft); RunWatcher ist
nur die Hülle, die den Takt gibt und Signale aussendet.

Wo die Läufe liegen, entscheidet spotlab.laufsuche — dieselbe Funktion benutzt
der MCP-Server, damit beide dasselbe finden.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from spotlab.laufsuche import lauf_verzeichnisse  # noqa: F401  (Re-Export)
from spotlab.record.tail import JsonlTail
from spotlab.workshop.control import ist_aktiv

TAKT_MS = 250


class _Lauf:
    def __init__(self, verzeichnis):
        self.dir = Path(verzeichnis)
        self.zustand = JsonlTail(self.dir / "zustand.jsonl")
        self.ereignisse = JsonlTail(self.dir / "ereignisse.jsonl")
        self.gesehene_bilder = set()
        # (mtime_ns, Groesse) von ansicht.jpg beim letzten Takt -- das
        # MuJoCo-Backend ERSETZT die Datei, es legt keine neuen an.
        self.ansicht_stand = None


class RunScanner:
    """Qt-freier Kern: findet Läufe und liefert die Neuigkeiten seit dem letzten Aufruf."""

    def __init__(self, workspace):
        self._wurzel = Path(workspace)
        self._offen = {}

    def tick(self):
        ereignisse = []
        ereignisse.extend(self._neue_laeufe())
        for schluessel in list(self._offen):
            ereignisse.extend(self._neuigkeiten(schluessel))
        return ereignisse

    # ------------------------------------------------------------------ intern

    def _neue_laeufe(self):
        gefunden = []
        for verzeichnis in lauf_verzeichnisse(self._wurzel):
            # Schlüssel ist der volle Pfad: zwei Projekte können Läufe mit
            # derselben Kennung haben.
            schluessel = str(verzeichnis)
            if schluessel in self._offen or not ist_aktiv(verzeichnis):
                continue
            self._offen[schluessel] = _Lauf(verzeichnis)
            gefunden.append(("lauf_begonnen", schluessel))
        return gefunden

    def _neuigkeiten(self, name):
        lauf = self._offen[name]
        ereignisse = []
        for satz in lauf.zustand.neue_saetze():
            ereignisse.append(("zustand", satz))
        for satz in lauf.ereignisse.neue_saetze():
            ereignisse.append(("ereignis", satz))
        ereignisse.extend(self._neue_bilder(lauf))
        ereignisse.extend(self._neue_ansicht(lauf))
        if not ist_aktiv(lauf.dir):
            del self._offen[name]
            ereignisse.append(("lauf_beendet", str(lauf.dir)))
        return ereignisse

    @staticmethod
    def _neue_ansicht(lauf):
        """`ansicht.jpg`, wenn sie sich seit dem letzten Takt geaendert hat.

        Eine Datei, die ersetzt wird, kein Strom: gemeldet wird nur eine
        Aenderung, sonst zeichnete die GUI viermal je Sekunde dasselbe Bild.
        """
        pfad = lauf.dir / "ansicht.jpg"
        try:
            st = pfad.stat()
        except OSError:
            return []
        stand = (st.st_mtime_ns, st.st_size)
        if stand == lauf.ansicht_stand:
            return []
        lauf.ansicht_stand = stand
        return [("ansicht", str(pfad))]

    @staticmethod
    def _neue_bilder(lauf):
        gefunden = []
        try:
            dateien = sorted((lauf.dir / "bilder").glob("*.png"))
        except OSError:
            return gefunden
        for datei in dateien:
            if datei.name not in lauf.gesehene_bilder:
                lauf.gesehene_bilder.add(datei.name)
                gefunden.append(("bild", str(datei)))
        return gefunden


class RunWatcher(QObject):
    lauf_begonnen = Signal(str)
    zustand = Signal(dict)
    ereignis = Signal(dict)
    bild = Signal(str)
    ansicht = Signal(str)
    lauf_beendet = Signal(str)
    fehler = Signal(str)

    def __init__(self, runs_dir, parent=None):
        super().__init__(parent)
        self._scanner = RunScanner(runs_dir)
        self._timer = QTimer(self)
        self._timer.setInterval(TAKT_MS)
        self._timer.timeout.connect(self._takt)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _takt(self):
        try:
            ereignisse = self._scanner.tick()
        except Exception as fehler:  # eine GUI, die still nichts mehr tut, ist schlimmer
            self.fehler.emit(f"Beobachter: {type(fehler).__name__}: {fehler}")
            return
        signale = {
            "lauf_begonnen": self.lauf_begonnen,
            "zustand": self.zustand,
            "ereignis": self.ereignis,
            "bild": self.bild,
            "ansicht": self.ansicht,
            "lauf_beendet": self.lauf_beendet,
        }
        for art, nutzlast in ereignisse:
            signale[art].emit(nutzlast)
