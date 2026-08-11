"""Vergangene Läufe ansehen — mit der einen Auswertung, die zählt.

Kommandiertes gegen gemessenes Tempo ist genau die Grösse, auf die die spätere
Real→Sim-Kalibrierung hinausläuft. Sie macht aus zustand.jsonl etwas
Ansehbares statt nur Archiviertes.

Gezeichnet wird mit QPainter: eine Kurve rechtfertigt keine weitere
Abhängigkeit auf zwanzig Schullaptops.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.theme import DUNKEL
from spotlab.laufsuche import lauf_verzeichnisse
from spotlab.record.read import read_jsonl, read_run

SPALTEN = ("Lauf", "Ergebnis", "Dauer", "Backend", "Skript")


# Was ein Ereignis interessant macht, je nach Art. Vorher stand hier nur
# `name` oder `status` — bei `ende`, `bild` und `lease_übernommen` blieb die
# Zeile deshalb leer, ausgerechnet dort, wo Erfolg oder Fehlertext steht.
BESCHREIBER = {
    "ende": ("ergebnis", "fehler"),
    "bild": ("pfad",),
    "lease_übernommen": ("von",),
    "rückmeldung": ("name", "status"),
    "messfenster": ("name", "phase"),
    "fehler": ("text",),
}
STANDARD_FELDER = ("name", "status", "backend", "ip")


def beschreibe(satz):
    """Der Klartext hinter einem Ereignis — was auch immer es trägt."""
    daten = satz.get("daten") or {}
    felder = BESCHREIBER.get(satz.get("art"), STANDARD_FELDER)
    teile = [str(daten[f]) for f in felder if daten.get(f) not in (None, "")]
    if teile:
        return " · ".join(teile)
    # Unbekannte Art: lieber alles zeigen als eine leere Zeile.
    return " · ".join(f"{k}={v}" for k, v in daten.items() if v not in (None, ""))


def tempo_reihen(run_dir):
    """(gemessen, kommandiert) als Listen von (Sekunde, m/s)."""
    verzeichnis = Path(run_dir)
    gemessen = []
    for satz in read_jsonl(verzeichnis / "zustand.jsonl"):
        tempo = (satz.get("daten") or {}).get("velocity")
        if tempo:
            gemessen.append((float(satz.get("t", 0.0)), float(tempo[0])))

    kommandiert = []
    for satz in read_jsonl(verzeichnis / "ereignisse.jsonl"):
        daten = satz.get("daten") or {}
        if satz.get("art") == "kommando" and daten.get("name") == "walk":
            t0 = float(satz.get("t", 0.0))
            vx = float(daten.get("vx", 0.0))
            dauer = float(daten.get("duration", 0.0))
            kommandiert.append((t0, vx))
            kommandiert.append((t0 + dauer, vx))
    return gemessen, kommandiert


class SpeedPlot(QWidget):
    """Zwei Linien: gemessen und kommandiert."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.gemessen = []
        self.kommandiert = []
        self.palette_ = DUNKEL

    def setze_daten(self, gemessen, kommandiert, palette=None):
        self.gemessen = list(gemessen)
        self.kommandiert = list(kommandiert)
        if palette is not None:
            self.palette_ = palette
        self.update()

    def paintEvent(self, ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        rand = 26
        breite = max(self.width() - 2 * rand, 1)
        hoehe = max(self.height() - 2 * rand, 1)

        maler.setPen(QPen(QColor(self.palette_.rand), 1))
        maler.drawRect(rand, rand, breite, hoehe)

        alle = self.gemessen + self.kommandiert
        if not alle:
            maler.setPen(QColor(self.palette_.gedaempft))
            maler.drawText(self.rect(), Qt.AlignCenter, "Keine Fahrdaten in diesem Lauf")
            return

        t_max = max(t for t, _ in alle) or 1.0
        v_max = max(0.1, max(abs(v) for _, v in alle)) * 1.15

        def punkt(t, v):
            return (rand + breite * (t / t_max), rand + hoehe * (1.0 - v / v_max))

        for reihe, farbe, dicke in (
            (self.kommandiert, self.palette_.gedaempft, 1),
            (self.gemessen, self.palette_.akzent, 2),
        ):
            if len(reihe) < 2:
                continue
            maler.setPen(QPen(QColor(farbe), dicke))
            vorher = punkt(*reihe[0])
            for t, v in reihe[1:]:
                jetzt = punkt(t, v)
                maler.drawLine(*(int(x) for x in vorher), *(int(x) for x in jetzt))
                vorher = jetzt

        maler.setPen(QColor(self.palette_.gedaempft))
        maler.drawText(rand, rand - 8, f"m/s (max {v_max:.2f})")
        maler.drawText(rand, self.height() - 6, f"0 – {t_max:.1f} s")


class RunsView(QWidget):
    def __init__(self, palette=DUNKEL, parent=None):
        super().__init__(parent)
        # Palette durchreichen wie bei EditorView und AnbindungenView: das
        # Diagramm malt sonst dunkle Beschriftungen auf hellen Grund, und auf
        # der Windows-Vorgabe „hell" ist das praktisch unlesbar — die Mehrheit
        # der Schullaptops.
        self._palette = palette
        self._ordner = None
        self._laeufe = []

        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabelle.itemSelectionChanged.connect(self._zeige_detail)

        self.ereignisliste = QListWidget()
        self.kurve = SpeedPlot()
        self.kurve.palette_ = self._palette

        detail = QHBoxLayout()
        detail.addWidget(self.ereignisliste, 1)
        detail.addWidget(self.kurve, 1)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(QLabel("Läufe"))
        anordnung.addWidget(self.tabelle, 2)
        anordnung.addWidget(QLabel("Kommandiertes (grau) gegen gemessenes (farbig) Tempo"))
        anordnung.addLayout(detail, 3)

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.aktualisiere()

    def aktualisiere(self):
        # ueber laufsuche, nicht ueber projekte_in: Laeufe angebundener
        # Fremdprojekte liegen unter <skriptordner>/runs, also AUSSERHALB des
        # Arbeitsordners. Wo Laeufe liegen, entscheidet genau eine Stelle --
        # zwei Suchen mit verschiedenen Ergebnissen waren der Fehler aus
        # Stufe 3, und er ist hier unbemerkt wiedergekommen.
        self._laeufe = []
        if self._ordner is not None:
            self._laeufe = [read_run(p) for p in lauf_verzeichnisse(self._ordner)]
        self._laeufe.sort(key=lambda lauf: lauf.id, reverse=True)

        self.tabelle.setRowCount(len(self._laeufe))
        for zeile, lauf in enumerate(self._laeufe):
            skript = Path(lauf.skript).name if lauf.skript else ""
            werte = (lauf.id, lauf.ergebnis, f"{lauf.dauer_s:.1f} s", lauf.backend, skript)
            for spalte, wert in enumerate(werte):
                self.tabelle.setItem(zeile, spalte, QTableWidgetItem(str(wert)))

    def _zeige_detail(self):
        zeilen = {i.row() for i in self.tabelle.selectedIndexes()}
        if not zeilen:
            return
        lauf = self._laeufe[min(zeilen)]
        self.ereignisliste.clear()
        for satz in read_jsonl(lauf.dir / "ereignisse.jsonl"):
            self.ereignisliste.addItem(
                f"{satz.get('t', 0.0):7.2f} s  {satz.get('art', ''):<14} "
                f"{beschreibe(satz)}"
            )
        self.kurve.setze_daten(*tempo_reihen(lauf.dir))
