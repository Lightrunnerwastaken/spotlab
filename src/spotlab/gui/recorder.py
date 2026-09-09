"""Die Aufzeichnung im Hintergrund.

RecordingSession.connect braucht Sekunden, und der Status wird im Sekundentakt
abgefragt. Beides im Qt-Hauptthread würde das Fenster einfrieren.

Das prüfbare Herzstück ist verarbeite() — Qt-frei, ohne Thread, ohne
Warteschlange. Der QThread darum herum ist nur Transport.
"""

import queue
from dataclasses import dataclass, field, replace

from PySide6.QtCore import QThread, Signal

from spotlab.errors import SpotlabError

TAKT_S = 1.0


@dataclass(frozen=True)
class Auftrag:
    art: str
    daten: dict = field(default_factory=dict)


def verarbeite(sitzung, auftrag, melde=None):
    """Einen Auftrag ausführen. Gibt ('status'|'gespeichert'|'fehler', Nutzlast).

    Wirft NICHT — ein Fehler in der Aufnahme darf den Arbeiter nicht beenden,
    sonst steht die Anzeige still und niemand weiss warum.

    `melde(text)` ist der Zwischenstand: die Nachbearbeitung vor dem Speichern
    dauert Sekunden, und ohne Zeichen sähe es aus, als hinge die Oberfläche.
    """
    try:
        if auftrag.art == "start":
            sitzung.start(graph_leeren=bool(auftrag.daten.get("graph_leeren")))
        elif auftrag.art == "waypoint":
            sitzung.waypoint(auftrag.daten["name"])
        elif auftrag.art == "stop":
            sitzung.stop()
        elif auftrag.art == "speichern":
            sitzung.stop()
            # Erst nachbearbeiten, dann herunterladen: `nachbearbeiten` ändert
            # die Karte AUF DEM ROBOTER, und die holen wir gleich.
            if auftrag.daten.get("nachbearbeiten", True):
                sitzung.nachbearbeiten(melde=melde)
            ziel = sitzung.download(
                auftrag.daten["wurzel"],
                auftrag.daten["name"],
                roboter=auftrag.daten.get("roboter"),
            )
            return "gespeichert", str(ziel)
        else:
            return "fehler", f"Unbekannter Auftrag: {auftrag.art}"
    except SpotlabError as fehler:
        return "fehler", str(fehler)
    except Exception as fehler:
        return "fehler", f"{type(fehler).__name__}: {fehler}"
    return "status", sitzung.status()


class RecordingWorker(QThread):
    status = Signal(object)
    fehler = Signal(str)
    gespeichert = Signal(str)
    bereit = Signal()

    def __init__(self, cfg, parent=None, verbinder=None):
        super().__init__(parent)
        self._cfg = cfg
        self._verbinder = verbinder
        self._auftraege = queue.Queue()
        self._laeuft = True

    # ------------------------------------------------------------- Aufträge

    def starte(self, graph_leeren=False):
        self._auftraege.put(Auftrag("start", {"graph_leeren": graph_leeren}))

    def setze_wegpunkt(self, name):
        self._auftraege.put(Auftrag("waypoint", {"name": name}))

    def beende(self):
        self._auftraege.put(Auftrag("stop"))

    def speichere(self, wurzel, name, roboter=None, nachbearbeiten=True):
        self._auftraege.put(
            Auftrag("speichern", {"wurzel": wurzel, "name": name, "roboter": roboter,
                                  "nachbearbeiten": nachbearbeiten})
        )

    def schliesse(self):
        self._laeuft = False
        self._auftraege.put(Auftrag("ende"))

    # ------------------------------------------------------------- Schleife

    def run(self):
        from spotlab.maps.session import RecordingSession

        try:
            sitzung = RecordingSession.connect(self._cfg, verbinder=self._verbinder)
        except SpotlabError as fehler:
            self.fehler.emit(str(fehler))
            return
        except Exception as fehler:
            self.fehler.emit(f"{type(fehler).__name__}: {fehler}")
            return

        self.bereit.emit()
        try:
            while self._laeuft:
                try:
                    auftrag = self._auftraege.get(timeout=TAKT_S)
                except queue.Empty:
                    self._melde_status(sitzung)
                    continue
                if auftrag.art == "ende":
                    break
                art, nutzlast = verarbeite(
                    sitzung, auftrag, melde=lambda text: self._melde_text(sitzung, text)
                )
                if art == "fehler":
                    self.fehler.emit(nutzlast)
                elif art == "gespeichert":
                    self.gespeichert.emit(nutzlast)
                else:
                    self.status.emit(nutzlast)
        finally:
            sitzung.close()

    def _melde_status(self, sitzung):
        try:
            self.status.emit(sitzung.status())
        except Exception as fehler:
            self.fehler.emit(f"Status nicht abrufbar: {fehler}")

    def _melde_text(self, sitzung, text):
        """Ein Zwischenstand mit den aktuellen Zahlen — die Kanten wachsen dabei."""
        from spotlab.maps.session import RecordingStatus

        try:
            stand = replace(sitzung.status(), meldung=text)
        except Exception:
            stand = RecordingStatus(False, 0, 0, text)
        self.status.emit(stand)
