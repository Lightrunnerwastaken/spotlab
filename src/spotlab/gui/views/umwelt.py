"""Was Spot sieht: Objekte links, Hindernisgitter rechts.

Diese Ansicht importiert weder `bosdyn` noch `spotlab.backends` — sie liest
ausschliesslich das Lauf-Verzeichnis: `ereignisse.jsonl` fuer die Objekte,
`gitter/*.png` fuer die Karte. Das Gitter wird beim SCHREIBEN dekodiert
(`beobachtung/gitter.py`), nicht hier; ein Protobuf-Dekoder im GUI-Prozess
brauchte das SDK, und das ist unterhalb von `gui/` verboten.

Der Knopf „Umgebung abfragen" startet `spotlab.workshop.sonde` als gewoehnliches
Skript ueber den EINEN Startweg (`gui/launcher`, mit der Ein-Lauf-Sperre) —
kein Lease, kein Kommando, der Roboter kann sich dadurch nicht bewegen. Das
Backend steht ausdruecklich auf „real“: die Vorgabe ist seit 0.2 der
Uebungsraum, und die Ansicht zeigt, was der ECHTE Spot sieht.

Gezeigt wird nach jedem Lauf, der etwas gesehen hat (`lade_wenn_passend`, vom
Hauptfenster gerufen) -- die Sonde ebenso wie ein Schuelerprogramm mit
`spot.tags()`. Bis zum 23.09.2026 rief niemand `lade()`, der Reiter blieb leer.
"""

import json
import time
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Der Pfad wird berechnet, nicht importiert: ein Import von sonde.py hier waere
# harmlos, aber der Weg ueber den Dateipfad haelt die Ansicht frei von jeder
# Abhaengigkeit ausser Qt und der Standardbibliothek.
SONDE_SKRIPT = Path(__file__).resolve().parents[2] / "workshop" / "sonde.py"
GITTER_BREITE_PX = 320


def _ereignisse(lauf_verzeichnis):
    pfad = Path(lauf_verzeichnis) / "ereignisse.jsonl"
    if not pfad.is_file():
        return []
    saetze = []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            # Ein Lauf, dessen Prozess getoetet wurde, hat eine halbe letzte
            # Zeile. Dieselbe Regel wie in record/read.py: nicht daran scheitern.
            continue
    return saetze


def _juengste_abfrage(saetze):
    """Der letzte tags-/world_objects-Aufruf, oder None."""
    for satz in reversed(saetze):
        daten = satz.get("daten") or {}
        if daten.get("name") in ("tags", "world_objects"):
            return satz
    return None


def zeilen_aus(saetze, jetzt=None):
    """Die Objektliste als fertige Textzeilen — die Testtuer dieser Ansicht."""
    satz = _juengste_abfrage(saetze)
    if satz is None:
        return []
    daten = satz["daten"]
    alter = None
    if jetzt is not None and satz.get("t") is not None:
        alter = max(0.0, jetzt - float(satz["t"]))
    kennungen = daten.get("ids") or daten.get("arten") or []
    distanzen = daten.get("distanzen") or []
    zeilen = []
    for kennung, distanz in zip(kennungen, distanzen):
        zeile = f"{kennung}   {distanz:.2f} m"
        if alter is not None:
            # Eine Objektliste ohne Alter suggeriert Gegenwart.
            zeile += f"   vor {alter:.0f} s"
        zeilen.append(zeile)
    return zeilen


def gitterbild_pfad(lauf_verzeichnis):
    """Die juengste Vorschau, oder None."""
    ordner = Path(lauf_verzeichnis) / "gitter"
    if not ordner.is_dir():
        return None
    bilder = sorted(ordner.glob("*.png"))
    return bilder[-1] if bilder else None


class UmweltView(QWidget):
    meldung = Signal(str)
    # (Prozess, Name): das Hauptfenster haengt seinen Ausgabeleser an. Ohne ihn
    # warf Qt den Prozess weg, die Pipe war zu, und die Sonde starb beim ersten print.
    lauf_gestartet = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._verzeichnis = None
        self._pixmap = None
        self._arbeitsordner = None
        self._start = None                 # austauschbar im Test

        self.abfragen = QPushButton("Umgebung abfragen")
        self.abfragen.setToolTip(
            "Fragt einmal ab, was Spot sieht. Kein Lease, kein Kommando — "
            "der Roboter bewegt sich dabei nicht."
        )
        self.abfragen.clicked.connect(self._starte_sonde)

        self.liste = QListWidget()
        self.bild = QLabel("—")

        links = QVBoxLayout()
        links.addWidget(QLabel("Gesehen"))
        links.addWidget(self.liste)

        rechts = QVBoxLayout()
        rechts.addWidget(QLabel("Hindernisgitter"))
        rechts.addWidget(self.bild)
        rechts.addStretch(1)

        mitte = QHBoxLayout()
        mitte.addLayout(links, 3)
        mitte.addLayout(rechts, 2)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(self.abfragen)
        anordnung.addLayout(mitte)

    # ---------------------------------------------------------------- Lesen

    def lade(self, lauf_verzeichnis):
        """Objekte und Gitter aus einem Lauf-Verzeichnis anzeigen."""
        self._verzeichnis = Path(lauf_verzeichnis)
        self.liste.clear()
        for zeile in self.objekttexte():
            self.liste.addItem(zeile)

        pfad = gitterbild_pfad(self._verzeichnis)
        self._pixmap = QPixmap(str(pfad)) if pfad is not None else None
        if self._pixmap is not None and not self._pixmap.isNull():
            self.bild.setPixmap(self._pixmap.scaledToWidth(GITTER_BREITE_PX))
        else:
            self._pixmap = None
            self.bild.setPixmap(QPixmap())
            self.bild.setText("noch kein Gitter aufgezeichnet")

    def lade_wenn_passend(self, lauf_verzeichnis):
        """Zeigen, wenn der Lauf etwas gesehen hat (Objekte oder ein Gitter). True dann."""
        verzeichnis = Path(lauf_verzeichnis)
        if not zeilen_aus(_ereignisse(verzeichnis)) and gitterbild_pfad(verzeichnis) is None:
            return False
        self.lade(verzeichnis)
        return True

    def objekttexte(self):
        if self._verzeichnis is None:
            return []
        return zeilen_aus(_ereignisse(self._verzeichnis), jetzt=time.time())

    def gitterbild(self):
        """Das angezeigte Gitterbild, oder None."""
        return self._pixmap

    # --------------------------------------------------------------- Sonde

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = Path(pfad) if pfad else None

    def _starte_sonde(self):
        if self._arbeitsordner is None:
            self.meldung.emit(
                "Es ist kein Arbeitsordner gesetzt. Wähle einen in der Ansicht "
                "'Projekte' — dorthin schreibt die Sonde ihren Lauf."
            )
            return
        starte = self._start
        if starte is None:
            from spotlab.gui.launcher import start_script

            starte = start_script
        # Unter Beispiele/runs wie der Gehzeit-Versuch: dort sucht die Laufsuche --
        # <Arbeitsordner>/runs durchsuchte niemand.
        from spotlab.workshop.beispiele import ORDNER

        runs = self._arbeitsordner / ORDNER / "runs"
        try:
            prozess = starte(SONDE_SKRIPT, argumente=["--runs", str(runs)], backend="real")
        except Exception as fehler:
            self.meldung.emit(f"Die Sonde liess sich nicht starten: {fehler}")
            return
        self.meldung.emit("Sonde läuft — kein Lease, der Roboter bewegt sich nicht.")
        self.lauf_gestartet.emit(prozess, "sonde")
        return prozess
