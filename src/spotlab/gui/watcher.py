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

Gemessen am 23.09.2026, alles im GUI-Thread: jeder alte Lauf wurde alle 250 ms
auf Leben geprüft (335 Läufe: 52 ms je Takt, 21 %; 1500 Läufe: mehr als der
Takt), und ein laufender 20-Minuten-Lauf, den die GUI spät fand, ging mit
60 000 Zeilen einzeln durch den Thread (8 s). Deshalb: lange Stilles wird
vergessen, und eine grosse Vorgeschichte übersprungen.

`zeige_nur(lauf)`: das Hauptfenster zeigt EINEN Lauf -- den, auf den Stopp und
NOT-AUS zeigen. Zustand, Bilder und Stände anderer Läufe kommen dann nicht
mehr durch; vorher zeigte der Tab „Fahren“ das Bild eines zweiten Laufs.
"""

import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from spotlab.laufsuche import laeufe_in, runs_wurzeln
from spotlab.laufsuche import lauf_verzeichnisse  # noqa: F401  (Re-Export)
from spotlab.record.tail import JsonlTail
from spotlab.workshop.control import ist_aktiv

TAKT_MS = 250
LIVE_TAKT_MS = 16  # neue 30-Hz-Bilder ohne zusaetzlichen ganzen Bildtakt abholen
# So lange still, und ein Lauf-Ordner wird nie wieder lebendig: nicht mehr pruefen.
VERGESSEN_NACH_S = 60.0
# Mehr ungelesene Vorgeschichte als das, und nur der letzte Stand wird gezeigt
# (~2 min bei 10 Hz). Darunter bleibt alles -- das Uebungsfenster zeichnet daraus
# die Spur seit dem Start.
VORGESCHICHTE_BYTES = 256 * 1024
PRO_LAUF = ("zustand", "ereignis", "bild", "ansicht", "navigation")


def _vor_der_letzten_zeile(pfad):
    """Byte-Stelle, ab der nur noch die letzte vollstaendige Zeile folgt -- oder 0."""
    try:
        groesse = pfad.stat().st_size
        with pfad.open("rb") as datei:
            anfang = max(0, groesse - 64 * 1024)
            datei.seek(anfang)
            roh = datei.read(groesse - anfang)
    except OSError:
        return 0
    ende = roh.rfind(b"\n")
    if ende < 0:
        return 0
    davor = roh.rfind(b"\n", 0, ende)
    return anfang + davor + 1 if davor >= 0 else anfang


class _Lauf:
    def __init__(self, verzeichnis):
        self.dir = Path(verzeichnis)
        self.zustand = JsonlTail(self.dir / "zustand.jsonl")
        pfad = self.dir / "zustand.jsonl"
        try:
            if pfad.stat().st_size > VORGESCHICHTE_BYTES:
                self.zustand.stand = _vor_der_letzten_zeile(pfad)
        except OSError:
            pass
        self.ereignisse = JsonlTail(self.dir / "ereignisse.jsonl")
        self.gesehene_bilder = set()
        # (mtime_ns, Groesse) von ansicht.jpg beim letzten Takt -- das
        # MuJoCo-Backend ERSETZT die Datei, es legt keine neuen an.
        self.ansicht_stand = None
        self.navigation_stand = None            # dasselbe fuer navigation.json


class RunScanner:
    """Qt-freier Kern: findet Läufe und liefert die Neuigkeiten seit dem letzten Aufruf."""

    def __init__(self, workspace, jetzt=time.time):
        self._wurzel = Path(workspace)
        self._offen = {}
        self._vergessen = set()          # lange stille Ordner: nie wieder pruefen
        self._jetzt = jetzt
        self._listen = {}                # runs/-Ordner -> (mtime_ns, Laeufe darin)

    def tick(self):
        return [(art, nutzlast) for art, _lauf, nutzlast in self.tick_mit_lauf()]

    def live_tick(self):
        return [(art, nutzlast) for art, _lauf, nutzlast in self.live_tick_mit_lauf()]

    def tick_mit_lauf(self):
        """Wie `tick`, aber je Neuigkeit (art, lauf, nutzlast) -- wer sie geschickt hat."""
        ereignisse = []
        ereignisse.extend(self._neue_laeufe())
        for schluessel in list(self._offen):
            ereignisse.extend(self._neuigkeiten(schluessel))
        return ereignisse

    def live_tick_mit_lauf(self):
        """Nur bekannte Laeufe: keine Verzeichnissuche und keine Kamera-PNGs."""
        ereignisse = []
        for schluessel, lauf in self._offen.items():
            ereignisse.extend(("zustand", schluessel, satz) for satz in lauf.zustand.neue_saetze())
            ereignisse.extend(self._mit(schluessel, self._neue_ansicht(lauf)))
            ereignisse.extend(self._mit(schluessel, self._neuer_navigationsstand(lauf)))
        return ereignisse

    @staticmethod
    def _mit(schluessel, paare):
        return [(art, schluessel, nutzlast) for art, nutzlast in paare]

    # ------------------------------------------------------------------ intern

    def _neue_laeufe(self):
        gefunden = []
        for verzeichnis in self._lauf_verzeichnisse():
            # Schlüssel ist der volle Pfad: zwei Projekte können Läufe mit
            # derselben Kennung haben.
            schluessel = str(verzeichnis)
            if schluessel in self._offen or schluessel in self._vergessen:
                continue
            if not ist_aktiv(verzeichnis):
                if self._lange_still(verzeichnis):
                    self._vergessen.add(schluessel)
                continue
            self._offen[schluessel] = _Lauf(verzeichnis)
            gefunden.append(("lauf_begonnen", schluessel, schluessel))
        return gefunden

    def _lauf_verzeichnisse(self):
        """Wie `laufsuche.lauf_verzeichnisse`, aber ein runs/-Ordner wird nur neu
        aufgelistet, wenn sich sein Zeitstempel geaendert hat -- ein neuer Lauf legt
        darin ein Verzeichnis an und aendert ihn. 335 Laeufe kosteten sonst 16 ms je
        Takt, nur fuer das Auflisten."""
        gefunden = {}
        for runs in runs_wurzeln(self._wurzel):
            try:
                stand = runs.stat().st_mtime_ns
            except OSError:
                continue
            gemerkt = self._listen.get(str(runs))
            # Kuerzlich geaendert: weiter auflisten. FAT32 (USB-Stick) fuehrt den
            # Zeitstempel nur auf 2 s genau -- ein zweiter Lauf im selben Fenster
            # aenderte ihn nicht sichtbar.
            frisch = self._jetzt() - stand / 1e9 < 3.0
            if gemerkt is None or gemerkt[0] != stand or frisch:
                gemerkt = (stand, laeufe_in(runs))
                self._listen[str(runs)] = gemerkt
            for lauf in gemerkt[1]:
                gefunden[str(lauf)] = lauf
        return list(gefunden.values())

    def _lange_still(self, verzeichnis):
        """Seit VERGESSEN_NACH_S weder im Ordner noch im Zustand etwas geschrieben.
        Ein junger Ordner ohne ersten Abtastwert gehoert NICHT dazu -- er lebt gleich."""
        juengste = 0.0
        for pfad in (verzeichnis, verzeichnis / "zustand.jsonl", verzeichnis / "lauf.json"):
            try:
                juengste = max(juengste, pfad.stat().st_mtime)
            except OSError:
                continue
        return juengste > 0 and self._jetzt() - juengste > VERGESSEN_NACH_S

    def _neuigkeiten(self, name):
        lauf = self._offen[name]
        ereignisse = []
        for satz in lauf.zustand.neue_saetze():
            ereignisse.append(("zustand", name, satz))
        for satz in lauf.ereignisse.neue_saetze():
            ereignisse.append(("ereignis", name, satz))
        ereignisse.extend(self._mit(name, self._neue_bilder(lauf)))
        ereignisse.extend(self._mit(name, self._neue_ansicht(lauf)))
        # Auch hier, nicht nur im Live-Takt: ein Lauf, der schon tot ist, wenn der
        # Watcher ihn findet, meldet seinen letzten Stand sonst nie -- Beginn und
        # Ende kaemen im selben Takt, und dazwischen laege kein Live-Takt mehr.
        ereignisse.extend(self._mit(name, self._neuer_navigationsstand(lauf)))
        if not ist_aktiv(lauf.dir):
            del self._offen[name]
            ereignisse.append(("lauf_beendet", name, str(lauf.dir)))
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
        self._gezeigt = None
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

    def zeige_nur(self, lauf):
        """Nur noch Zustand, Bilder und Staende DIESES Laufs weitergeben (None: alle).
        Beginn und Ende JEDES Laufs kommen weiter durch -- das Fenster fuehrt
        die Warteschlange."""
        self._gezeigt = str(lauf) if lauf is not None else None

    def _live_takt(self):
        try:
            self._sende(self._scanner.live_tick_mit_lauf())
        except Exception as fehler:
            self.fehler.emit(f"Live-Ansicht: {type(fehler).__name__}: {fehler}")

    def _takt(self):
        try:
            ereignisse = self._scanner.tick_mit_lauf()
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
        for art, lauf, nutzlast in ereignisse:
            if art in PRO_LAUF and self._gezeigt is not None and lauf != self._gezeigt:
                continue
            signale[art].emit(nutzlast)
