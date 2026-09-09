"""Den runs/-Ordner mitlesen und als Qt-Signale weitergeben.

Abgefragt statt QFileSystemWatcher: Anfügungen an eine offene Datei lösen
unter Windows keine verlässliche Verzeichnisbenachrichtigung aus, und 10 Hz
Anfügungen würden einen Ereignis-Beobachter überschwemmen. Die Lauf-Suche und
Ereignisse bleiben bei 250 ms. Ein eigener 16-ms-Takt liest neue Zustaende und
Ansichtsbilder ausschliesslich aus den bereits bekannten laufenden Ordnern.

Die Logik steckt vollständig in RunScanner (Qt-frei, geprüft); RunWatcher ist
nur die Hülle, die den Takt gibt und Signale aussendet.

Wo die Läufe liegen, entscheidet spotlab.laufsuche — dieselbe Funktion benutzt
der MCP-Server, damit beide dasselbe finden.
"""

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from spotlab.laufsuche import lauf_verzeichnisse  # noqa: F401  (Re-Export)
from spotlab.record.tail import JsonlTail
from spotlab.workshop.control import ist_aktiv

TAKT_MS = 250
LIVE_TAKT_MS = 16  # neue 30-Hz-Bilder ohne zusaetzlichen ganzen Bildtakt abholen


class _Lauf:
    def __init__(self, verzeichnis):
        self.dir = Path(verzeichnis)
        self.zustand = JsonlTail(self.dir / "zustand.jsonl")
        self.ereignisse = JsonlTail(self.dir / "ereignisse.jsonl")
        self.gesehene_bilder = set()
        # (mtime_ns, Groesse) von ansicht.jpg beim letzten Takt -- das
        # MuJoCo-Backend ERSETZT die Datei, es legt keine neuen an.
        self.ansicht_stand = None
        self.navigation_stand = None            # dasselbe fuer navigation.json


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

    def live_tick(self):
        """Nur bekannte Laeufe: keine Verzeichnissuche und keine Kamera-PNGs."""
        ereignisse = []
        for lauf in self._offen.values():
            ereignisse.extend(("zustand", satz) for satz in lauf.zustand.neue_saetze())
            ereignisse.extend(self._neue_ansicht(lauf))
            ereignisse.extend(self._neuer_navigationsstand(lauf))
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
        # Auch hier, nicht nur im Live-Takt: ein Lauf, der schon tot ist, wenn der
        # Watcher ihn findet, meldet seinen letzten Stand sonst nie -- Beginn und
        # Ende kaemen im selben Takt, und dazwischen laege kein Live-Takt mehr.
        ereignisse.extend(self._neuer_navigationsstand(lauf))
        if not ist_aktiv(lauf.dir):
            del self._offen[name]
            ereignisse.append(("lauf_beendet", str(lauf.dir)))
        return ereignisse

    @staticmethod
    def _neue_ansicht(lauf):
        """`ansicht.jpg`, wenn sie sich seit dem letzten Takt geaendert hat.

        Eine Datei, die ersetzt wird, kein Strom: gemeldet wird nur eine
        Aenderung, sonst dekodierte die GUI immer wieder dasselbe Bild.
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
    def _neuer_navigationsstand(lauf):
        """`navigation.json` des Navigationslaufs, wenn sie sich geaendert hat.

        Ein halb geschriebener Stand liest sich als None; dann bleibt die
        Marke stehen, und der naechste Takt liest ihn fertig.
        """
        from spotlab.record import navigation

        pfad = lauf.dir / navigation.STAND_DATEI
        try:
            st = pfad.stat()
        except OSError:
            return []
        stand = (st.st_mtime_ns, st.st_size)
        if stand == lauf.navigation_stand:
            return []
        daten = navigation.lies_stand(lauf.dir)
        if daten is None:
            return []
        lauf.navigation_stand = stand
        return [("navigation", daten)]

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
    navigation = Signal(dict)
    lauf_beendet = Signal(str)
    fehler = Signal(str)

    def __init__(self, runs_dir, parent=None):
        super().__init__(parent)
        self._scanner = RunScanner(runs_dir)
        self._timer = QTimer(self)
        self._timer.setInterval(TAKT_MS)
        self._timer.timeout.connect(self._takt)
        self._live_timer = QTimer(self)
        self._live_timer.setTimerType(Qt.PreciseTimer)
        self._live_timer.setInterval(LIVE_TAKT_MS)
        self._live_timer.timeout.connect(self._live_takt)

    def start(self):
        self._timer.start()
        self._live_timer.start()

    def stop(self):
        self._timer.stop()
        self._live_timer.stop()

    def _live_takt(self):
        try:
            self._sende(self._scanner.live_tick())
        except Exception as fehler:
            self.fehler.emit(f"Live-Ansicht: {type(fehler).__name__}: {fehler}")

    def _takt(self):
        try:
            ereignisse = self._scanner.tick()
        except Exception as fehler:  # eine GUI, die still nichts mehr tut, ist schlimmer
            self.fehler.emit(f"Beobachter: {type(fehler).__name__}: {fehler}")
            return
        self._sende(ereignisse)

    def _sende(self, ereignisse):
        signale = {
            "lauf_begonnen": self.lauf_begonnen,
            "zustand": self.zustand,
            "ereignis": self.ereignis,
            "bild": self.bild,
            "ansicht": self.ansicht,
            "navigation": self.navigation,
            "lauf_beendet": self.lauf_beendet,
        }
        for art, nutzlast in ereignisse:
            signale[art].emit(nutzlast)
