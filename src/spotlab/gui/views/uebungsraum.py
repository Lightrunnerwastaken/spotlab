"""Der Uebungsraum: Raum waehlen, Start setzen, Programm laufen sehen.

Eigene Ansicht neben „Umwelt": jene zeigt, WAS Spot sieht, diese, WO er ist.

Sie importiert weder bosdyn noch spotlab.backends -- sie liest ausschliesslich
das Lauf-Verzeichnis (`ereignisse.jsonl` fuer Raum und Anstoesse, `zustand.jsonl`
fuer die Spur) und `welt.raum` fuer die Geometrie. Letzteres ist reine
Standardbibliothek.

DER STARTKNOPF STARTET NICHT SELBST. Er meldet den Wunsch; das Hauptfenster
stellt das Backend auf „sim" und laesst den EDITOR starten -- so wie der
Stopp-Knopf im Editor an „Live-Lauf" delegiert. Grund ist die Invariante aus
CLAUDE.md: genau EIN Lauf ist der, auf den Stopp und NOT-AUS zeigen.

Gezeichnet wird waehrend des Laufs im eigenen Fenster (`gui/uebungsfenster.py`);
diese Ansicht ist der Platz zum EINRICHTEN und zeigt danach die gefahrene Spur.
"""

import json
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.raumplot import RaumPlot
from spotlab.welt.kollision import hindernis_bei
from spotlab.welt.raum import raum_laden, vorlagen

# Der Knopf startet, was im EDITOR offen ist -- nicht eine Auswahl irgendwo
# sonst. Die Beschriftung sagt das, damit niemand eine Auswahl sucht.
START_TEXT = "▶ Offene Datei starten"
STOPP_TEXT = "■ Stopp"


def _zeilen(pfad):
    """jsonl lesen, halbe letzte Zeile ueberspringen (wie record/read.py)."""
    if not pfad.is_file():
        return []
    saetze = []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue
    return saetze


class UebungsraumView(QWidget):
    meldung = Signal(str)
    config_gespeichert = Signal(object)
    start_gewuenscht = Signal()

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self._config = None
        self._arbeitsordner = None
        self._raum = None
        # Der Name des GELADENEN Raums. Nicht `raeume.currentText()`: `lade()`
        # ruft `waehle_raum` auch dann, wenn die Liste noch woanders steht --
        # gespeichert wuerde sonst ein Raum, der gar nicht gezeichnet ist.
        self._raumname = ""

        self.plot = RaumPlot(palette)
        self.plot.start_gewaehlt.connect(self._start_gewaehlt)

        self.raeume = QComboBox()
        self.raeume.addItems(vorlagen())
        self.raeume.currentTextChanged.connect(self.waehle_raum)
        # `activated` statt `currentTextChanged` fuers Speichern: jenes feuert
        # auch, wenn `lade()` die Liste auf den Raum eines alten Laufs stellt --
        # das Nachspielen ueberschriebe sonst die Wahl des Schuelers.
        self.raeume.activated.connect(self._raum_gemerkt)

        self.startzeile = QLabel("—")
        self.startzeile.setObjectName("Gedaempft")
        self.starten = QPushButton(START_TEXT)
        self.starten.clicked.connect(self.start_gewuenscht.emit)

        rechts = QVBoxLayout()
        rechts.addWidget(QLabel("Raum"))
        rechts.addWidget(self.raeume)
        rechts.addWidget(QLabel("Startposition"))
        rechts.addWidget(QLabel("In die Zeichnung klicken."))
        rechts.addWidget(self.startzeile)
        rechts.addStretch(1)
        rechts.addWidget(self.starten)

        anordnung = QHBoxLayout(self)
        anordnung.addWidget(self.plot, 3)
        anordnung.addLayout(rechts, 1)

        self.waehle_raum(self.raeume.currentText())

    # ----------------------------------------------------------- Zustand

    def setze_laeuft(self, laeuft):
        """Waehrend eines Laufs haelt derselbe Knopf an.

        Ohne das haette der Uebungsraum einen Startknopf, der mitten im Lauf
        nichts tut -- und der Schueler suchte den Stopp anderswo.
        """
        self.starten.setText(STOPP_TEXT if laeuft else START_TEXT)

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = Path(pfad) if pfad else None

    def setze_config(self, cfg):
        self._config = cfg
        if cfg and cfg.raum:
            self.raeume.setCurrentText(cfg.raum)

    # -------------------------------------------------------------- Raum

    def waehle_raum(self, name):
        if not name:
            return
        try:
            self._raum = raum_laden(name, workspace=self._arbeitsordner)
        except Exception as fehler:
            self.meldung.emit(str(fehler))
            return
        self._raumname = name
        self.plot.setze_raum(self._raum)
        self.plot.setze_start(self._raum.start)
        self._zeige_start(self._raum.start)

    def raum(self):
        """Der GELADENE Raum. Das Uebungsfenster belegt seine Zeichnung damit
        vor, damit sie nicht leer beginnt."""
        return self._raum

    def raumname(self):
        """Der Name des GELADENEN Raums -- der geht mit an den Lauf."""
        return self._raumname

    def startpose(self):
        """Die GEWAEHLTE Startpose -- was der Schueler geklickt hat, nicht was
        in der Vorlage steht."""
        return self.plot.start()

    def _raum_gemerkt(self, _index):
        """Die Raumwahl sofort sichern.

        Vorher entstand `[uebungsraum]` erst beim Klick in die Zeichnung. Wer
        nur den Raum umstellte und startete, fuhr in GAR KEINEM Raum: `cfg.raum`
        blieb leer, und connect() baute den Sim ohne Welt.
        """
        if self._config is None or not self._raumname:
            return
        self._config = replace(self._config, raum=self._raumname)
        self.config_gespeichert.emit(self._config)

    def _zeige_start(self, pose):
        self.startzeile.setText(f"({pose[0]:.2f}, {pose[1]:.2f}) bei {pose[2]:.0f}°")

    def _start_gewaehlt(self, x, y):
        if self._raum is None:
            return
        getroffen = hindernis_bei(self._raum, x, y)
        if getroffen is not None:
            was = "eine Wand" if getroffen == "Wand" else getroffen
            self.meldung.emit(
                f"Dort steht {was} im Weg — such eine freie Stelle."
            )
            return
        grad = self._raum.start[2]
        self.plot.setze_start((x, y, grad))
        self._zeige_start((x, y, grad))
        if self._config is not None:
            self._config = replace(
                self._config, raum=self._raumname,
                raum_start=f"{x:.2f},{y:.2f},{grad:.1f}",
            )
            self.config_gespeichert.emit(self._config)

    # -------------------------------------------------------------- Lauf

    def lade(self, lauf_verzeichnis):
        ordner = Path(lauf_verzeichnis)
        name = None
        anstoesse = []
        for satz in _zeilen(ordner / "ereignisse.jsonl"):
            daten = satz.get("daten") or {}
            if satz.get("art") == "verbunden":
                name = daten.get("raum")
            elif satz.get("art") == "angestossen":
                anstoesse.append((daten.get("x", 0.0), daten.get("y", 0.0)))

        if name:
            self.raeume.setCurrentText(name)
            self.waehle_raum(name)
        else:
            self._raum = None
            self.plot.setze_raum(None)

        spur = []
        for satz in _zeilen(ordner / "zustand.jsonl"):
            pose = (satz.get("daten") or {}).get("pose")
            if pose and len(pose) >= 2:
                spur.append((pose[0], pose[1]))
        self.plot.setze_spur(spur)
        self.plot.setze_anstoesse(anstoesse)
