"""Kopfleiste: Zustand links, NOT-AUS rechts.

Der Knopf ist in jeder Ansicht sichtbar und fragt NICHT nach. Wer ihn drückt,
hat keine Zeit für einen Dialog. Was er tut, steht dauerhaft daneben — samt
dem Hinweis, dass der physische Not-Aus das primäre Sicherheitsmittel bleibt.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

ERKLAERUNG = (
    "Beendet das laufende Programm sofort — der Spot schaltet die Motoren ab und "
    "sackt zusammen. Wirkt nur auf spotlab. Das primäre Sicherheitsmittel bleibt "
    "der physische Not-Aus am Tablet."
)
SIM_ERKLAERUNG = (
    "Beendet das laufende Programm sofort. Gerade läuft nur die Simulation — "
    "kein Roboter bewegt sich."
)
# Backends ohne Roboter (`lauf.json` → `backend`) und ihr Name im Kopf. Ein Backend,
# das hier fehlt, bekommt KEIN Schild -- im Zweifel steht die Roboteranzeige da.
SIMULATIONEN = {
    "physics": "Physik 3D",
    "mujoco": "3D-Wiedergabe",
    "sim": "2D",
    "dryrun": "Trockenlauf",
    "beobachter-trocken": "Trockenprobe",
}


class Header(QWidget):
    notaus = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._simulation = False
        self._roboter_text = "Nicht eingerichtet"

        self.ampel = QLabel("●")
        self.ampel.setObjectName("Gedaempft")
        self.status = QLabel("Nicht eingerichtet")
        self.akku = QLabel("Akku —")
        self.lease = QLabel("Lease —")

        self.notaus_knopf = QPushButton("NOT-AUS")
        self.notaus_knopf.setObjectName("Notaus")
        self.notaus_knopf.setCursor(Qt.PointingHandCursor)
        self.notaus_knopf.clicked.connect(self.notaus.emit)

        self.hinweis = QLabel(ERKLAERUNG)
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        zeile = QHBoxLayout()
        for widget in (self.ampel, self.status, self.akku, self.lease):
            zeile.addWidget(widget)
        zeile.addStretch(1)
        zeile.addWidget(self.notaus_knopf)

        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(14, 10, 14, 8)
        aussen.addLayout(zeile)
        aussen.addWidget(self.hinweis)

    # ------------------------------------------------------------- Anzeige

    def _setze_ampel(self, name):
        self.ampel.setObjectName(name)
        self.ampel.style().unpolish(self.ampel)
        self.ampel.style().polish(self.ampel)

    def zeige_config(self, cfg):
        if cfg is None:
            self._roboter_text = "Nicht eingerichtet — Ansicht „Spot“"
        else:
            self._roboter_text = f"{cfg.nickname} · {cfg.ip}"
        if not self._simulation:
            self.status.setText(self._roboter_text)

    def zeige_simulation(self, backend):
        """Ein Lauf ohne Roboter: Schild statt IP, Lease und Roboterhinweis.

        Playtest 04.10.2026: während eines Übungslaufs stand oben die IP des echten
        Spot samt „Lease —“ und dem Hinweis aufs Tablet -- als führe er.
        """
        name = SIMULATIONEN.get(backend)
        if name is None:
            return
        self._simulation = True
        self.status.setText(f"Übungsraum · {name} · kein Roboter")
        self.lease.hide()
        self.hinweis.setText(SIM_ERKLAERUNG)

    def zeige_getrennt(self):
        self._setze_ampel("Gedaempft")
        self.akku.setText("Akku —")
        self.lease.setText("Lease —")
        if self._simulation:
            self._simulation = False
            self.status.setText(self._roboter_text)
            self.lease.show()
            self.hinweis.setText(ERKLAERUNG)

    def zeige_pruefung(self, pruefungen):
        if not pruefungen:
            self.zeige_getrennt()
            return
        schlimm = [p for p in pruefungen if not p.ok]
        if not schlimm:
            self._setze_ampel("Ok")
        elif any(p.name in ("Netz", "Anmeldung", "Not-Aus") for p in schlimm):
            self._setze_ampel("Gefahr")
        else:
            self._setze_ampel("Warnung")

        for pruefung in pruefungen:
            if pruefung.name == "Akku":
                self.akku.setText(f"Akku {pruefung.detail}")
            if pruefung.name == "Lease":
                self.lease.setText(f"Lease {pruefung.detail}")

    def zeige_zustand(self, satz):
        """Live-Werte aus zustand.jsonl — ohne eigene Roboterverbindung."""
        daten = satz.get("daten", {})
        akku = daten.get("battery")
        if akku is not None:
            self.akku.setText(f"Akku {akku:.0f} %")
        self._setze_ampel("Ok")
