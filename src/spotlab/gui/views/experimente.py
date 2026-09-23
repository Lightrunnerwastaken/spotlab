"""Der Reiter „Experimente": ein Ort für alle Versuche — Gehzeit ist der erste.

Bis zum 16.09.2026 hatte die Gehzeit (A35) ihren eigenen Reiter. Jeder weitere
Versuch der Maturaarbeit hätte einen weiteren Reiter gebraucht, und die Leiste
ist voll. Jetzt gibt es EINEN Reiter mit einer Auswahl oben und einem Stapel
darunter; die Gehzeit-Ansicht selbst ist unverändert (`views/gehzeit.py`).

EIN NEUES EXPERIMENT IST EINE ZEILE in `EXPERIMENTE` plus seine eigene Ansicht
— sonst nichts: kein Eintrag in der Leiste, keine Verdrahtung in `app.py`. Die
Ansicht bekommt vom Fenster durchgereicht, was jedes Experiment brauchen kann:
den Arbeitsordner (`setze_arbeitsordner`) und den Weg für Meldungen
(`meldung`). Ein Experiment, das eines davon nicht kennt, wird nicht gezwungen.

Anlegen aus der Oberfläche heraus gibt es bewusst NICHT — das bleibt Zukunft.
Ein Test hält fest, dass dieser Rahmen keinen solchen Knopf hat.

Diese Ansicht importiert weder `bosdyn` noch `spotlab.backends`.
"""

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.views.gehzeit import GehzeitView

HINWEIS = (
    "Jeder Versuch der Maturaarbeit hat hier seine Ansicht. Oben wählen, unten arbeiten. "
    "Weitere Experimente kommen als Eintrag in der Liste dazu; anlegen lässt sich hier nichts."
)


@dataclass(frozen=True)
class Experiment:
    """Der Vertrag für jedes Experiment: drei Felder, mehr braucht die Auswahl nicht."""

    schluessel: str              # eindeutig, klein, ohne Leerzeichen -- der Name im Code
    name: str                    # was der Mensch in der Auswahl liest
    ansicht: type                # die Ansichtsklasse; wird ohne Argumente gebaut


EXPERIMENTE = (
    Experiment("gehzeit", "Gehzeit — Spot nimmt für jeden gleichzeitig die Zeit (A35)", GehzeitView),
)


class ExperimenteView(QWidget):
    meldung = Signal(str)
    lauf_gestartet = Signal(object, str)      # von jedem Experiment, das Prozesse startet

    def __init__(self, parent=None, experimente=EXPERIMENTE):
        super().__init__(parent)
        titel = QLabel("Experimente")
        titel.setObjectName("Titel")
        hinweis = QLabel(HINWEIS)
        hinweis.setObjectName("Gedaempft")
        hinweis.setWordWrap(True)

        self.auswahl = QComboBox()
        self.auswahl.setToolTip("Welches Experiment unten gezeigt wird")
        self.stapel = QStackedWidget()
        self._ansichten = {}
        for experiment in experimente:
            ansicht = experiment.ansicht()
            self._ansichten[experiment.schluessel] = ansicht
            self.stapel.addWidget(ansicht)
            self.auswahl.addItem(experiment.name, experiment.schluessel)
            signal = getattr(ansicht, "meldung", None)
            if signal is not None:
                signal.connect(self.meldung)
            gestartet = getattr(ansicht, "lauf_gestartet", None)
            if gestartet is not None:
                gestartet.connect(self.lauf_gestartet)
        self.auswahl.currentIndexChanged.connect(self._gewaehlt)

        kopf = QHBoxLayout()
        kopf.addWidget(QLabel("Experiment"))
        kopf.addWidget(self.auswahl, 1)

        anordnung = QVBoxLayout(self)
        anordnung.addWidget(titel)
        anordnung.addWidget(hinweis)
        anordnung.addLayout(kopf)
        anordnung.addWidget(self.stapel, 1)

    # -------------------------------------------------------------- Zugang

    def experiment(self, schluessel):
        """Die Ansicht eines Experiments — KeyError für einen unbekannten Schlüssel."""
        return self._ansichten[schluessel]

    def aktuelles(self):
        return self.stapel.currentWidget()

    def _gewaehlt(self, index):
        self.stapel.setCurrentWidget(self._ansichten[self.auswahl.itemData(index)])

    # ------------------------------------------------------ vom Fenster

    def setze_arbeitsordner(self, pfad):
        """An jedes Experiment, das einen Arbeitsordner kennt."""
        for ansicht in self._ansichten.values():
            setzen = getattr(ansicht, "setze_arbeitsordner", None)
            if setzen is not None:
                setzen(pfad)
