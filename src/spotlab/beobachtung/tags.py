"""Tagmitschnitt: erkannte Fiducials im eigenen Takt neben die Aufzeichnung.

Eigener Thread neben `StateSampler` und `Bildmitschnitt`, aus demselben Grund
wie dort: eine Abfrage, die im WLAN hängt, verlangsamt DIESEN Takt und nicht
die Messung, um die es eigentlich geht.

WAS GESCHRIEBEN WIRD, und warum so viel: der ganze `WorldObject` als JSON,
samt `transforms_snapshot`. Die Labelerzeugung braucht die Tag-Pose IM
RAHMENBAUM — nur damit lässt sich eine ruhende Weltlage später exakt in ein
aufgezeichnetes Bild projizieren, unabhängig davon, wie weit die Zeitstempel
auseinanderliegen. Was hier fehlt, fehlt für immer; die Aufnahme findet einmal
statt. Bei zwei Takten je Sekunde sind das über eine halbe Stunde rund zehn
Megabyte — gegen einen zweiten Messtag ist das kein Preis.

LEERE TAKTE WERDEN AUCH GESCHRIEBEN. „Vier Sekunden lang keinen Tag gesehen"
ist eine Information, die beim Auswerten zählt — dieselbe Regel wie bei der
erfolglosen Tag-Abfrage in `api/world.py`.

Geschrieben wird NICHT über den `RunRecorder`: der kennt Bilder und Zustände,
und ein Versuchsformat gehört nicht in die Aufzeichnung aller Läufe. Gebraucht
werden von ihm nur das Verzeichnis und die Zeitmarke — dieselbe Zeitbasis wie
`t` im Bildindex, sonst findet niemand das Bild zu einer Tag-Beobachtung.
"""

import json
import threading
import time
from pathlib import Path

# Zeitgrenze eines Abrufs. Ohne sie hinge der Thread an einem abgerissenen WLAN
# bis zum Ende der Messfahrt — und der Zähler zeigte weiterhin den letzten
# Stand, also „alles gut", während längst nichts mehr ankommt.
ABRUF_FRIST_S = 5.0
ORDNER = "tags"
INDEX = "tags.jsonl"


def _als_dict(objekt):
    from google.protobuf import json_format

    return json_format.MessageToDict(objekt)


class Tagmitschnitt:
    """Holt in festem Takt die erkannten Fiducials und schreibt sie mit.

    Wirft nie nach aussen. Ein gescheiterter Abruf wird gezählt und beim
    nächsten Takt erneut versucht — eine misslungene Abfrage darf die Messfahrt
    nicht kippen, aber sie darf auch nicht unsichtbar bleiben.
    """

    def __init__(self, quelle, recorder, hz=2.0):
        self._quelle = quelle
        self._recorder = recorder
        self._hz = float(hz)
        self._periode = 1.0 / self._hz if self._hz > 0 else 0.0
        self._stopp = threading.Event()
        self._thread = None
        self._sperre = threading.Lock()
        self._takte = 0
        self._tags = 0
        self._fehler = 0
        self._letzter_fehler = None
        self._bereit = False
        self._t0 = None

    # ------------------------------------------------------------ Steuerung

    def start(self):
        if self._thread is not None or self._periode <= 0:
            return
        self._t0 = time.monotonic()
        self._thread = threading.Thread(
            target=self._schleife, name="spotlab-tags", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=ABRUF_FRIST_S + 2.0):
        self._stopp.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def setze_rate(self, hz):
        """Wirkt ab dem nächsten Takt. Startet nichts — ein Mitschnitt, der mit
        0 Hz aufgesetzt wurde, hat gar keinen Thread, und ihn hier nachträglich
        anzuwerfen umginge die Entscheidung „keine Tags" an der einzigen Stelle,
        wo sie steht."""
        with self._sperre:
            self._hz = float(hz)
            self._periode = 1.0 / self._hz if self._hz > 0 else 0.0

    def zaehler(self):
        with self._sperre:
            dauer = (time.monotonic() - self._t0) if self._t0 else 0.0
            return {
                "takte": self._takte,
                "tags": self._tags,
                "fehler": self._fehler,
                "letzter_fehler": self._letzter_fehler,
                "hz_ist": round(self._takte / dauer, 2) if dauer > 0 else None,
            }

    # ----------------------------------------------------------- Innenleben

    @property
    def _pfad(self):
        return Path(self._recorder.dir) / ORDNER / INDEX

    def _einmal(self):
        try:
            objekte = list(self._quelle.objekte())
        except Exception as fehler:
            with self._sperre:
                self._fehler += 1
                self._letzter_fehler = f"{type(fehler).__name__}: {fehler}"
            return
        satz = {
            "t": round(self._recorder.zeitmarke(), 3),
            "objekte": [_als_dict(o) for o in objekte],
        }
        try:
            self._schreibe(satz)
        except OSError as fehler:
            with self._sperre:
                self._fehler += 1
                self._letzter_fehler = f"{type(fehler).__name__}: {fehler}"
            return
        with self._sperre:
            self._takte += 1
            self._tags += len(objekte)

    def _schreibe(self, satz):
        pfad = self._pfad
        if not self._bereit:
            pfad.parent.mkdir(parents=True, exist_ok=True)
            self._bereit = True
        with pfad.open("a", encoding="utf-8") as ziel:
            ziel.write(json.dumps(satz, ensure_ascii=False, default=str) + "\n")

    def _schleife(self):
        while not self._stopp.is_set():
            beginn = time.monotonic()
            with self._sperre:
                periode = self._periode
            self._einmal()
            # Nichts nachholen — dieselbe Regel wie beim Abtaster und beim
            # Bildmitschnitt. Ein Burst nach einer Störung sähe in der
            # Auswertung wie ein dichter abgetasteter Abschnitt aus.
            rest = periode - (time.monotonic() - beginn)
            if rest > 0:
                self._stopp.wait(rest)
