"""Projekte anlegen, in VS Code öffnen, Skripte starten.

Der Trockenlauf ist ein sichtbares Häkchen statt einer Kommandozeilenoption,
die niemand findet — Üben ohne Roboter soll man sehen können.
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.errors import SpotlabError
from spotlab.workshop.editor import open_in_editor
from spotlab.workshop.launcher import start_script
from spotlab.workshop.project import create_project


def projekte_in(ordner):
    """Unterordner, die ein runs/-Verzeichnis haben — daran erkennt man ein Projekt."""
    wurzel = Path(ordner)
    try:
        kandidaten = [p for p in wurzel.iterdir() if p.is_dir()]
    except OSError:
        return []
    return sorted((p for p in kandidaten if (p / "runs").is_dir()), key=lambda p: p.name)


class ProjectsView(QWidget):
    lauf_gestartet = Signal(object, str)
    arbeitsordner_geaendert = Signal(str)
    projekt_oeffnen = Signal(object)

    def __init__(self, editor_command="code", parent=None):
        super().__init__(parent)
        self._ordner = None
        self._editor = editor_command

        self.pfadanzeige = QLabel("Kein Arbeitsordner gewählt")
        self.pfadanzeige.setObjectName("Gedaempft")
        self.waehlen_knopf = QPushButton("Arbeitsordner wählen…")
        self.waehlen_knopf.clicked.connect(self._waehle_ordner)

        self.projektliste = QListWidget()
        self.projektliste.currentRowChanged.connect(lambda _: self._fuelle_skripte())
        self.neu_knopf = QPushButton("Neues Projekt")
        self.neu_knopf.clicked.connect(self._neues_projekt)
        self.spotlab_knopf = QPushButton("In spotlab öffnen")
        self.spotlab_knopf.clicked.connect(self._oeffne_in_spotlab)
        self.oeffnen_knopf = QPushButton("In VS Code öffnen")
        self.oeffnen_knopf.clicked.connect(self._oeffne_projekt)

        self.skriptliste = QListWidget()
        self.trockenlauf = QCheckBox("Trockenlauf (ohne Roboter)")
        self.starten_knopf = QPushButton("Starten")
        self.starten_knopf.clicked.connect(self._starte)

        kopf = QHBoxLayout()
        kopf.addWidget(self.pfadanzeige, 1)
        kopf.addWidget(self.waehlen_knopf)

        projektknoepfe = QHBoxLayout()
        projektknoepfe.addWidget(self.neu_knopf)
        projektknoepfe.addWidget(self.spotlab_knopf)
        projektknoepfe.addWidget(self.oeffnen_knopf)
        projektknoepfe.addStretch(1)

        startzeile = QHBoxLayout()
        startzeile.addWidget(self.trockenlauf)
        startzeile.addStretch(1)
        startzeile.addWidget(self.starten_knopf)

        anordnung = QVBoxLayout(self)
        anordnung.addLayout(kopf)
        anordnung.addWidget(QLabel("Projekte"))
        anordnung.addWidget(self.projektliste, 2)
        anordnung.addLayout(projektknoepfe)
        anordnung.addWidget(QLabel("Programme"))
        anordnung.addWidget(self.skriptliste, 2)
        anordnung.addLayout(startzeile)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.pfadanzeige.setText(
            str(self._ordner) if self._ordner else "Kein Arbeitsordner gewählt"
        )
        self.aktualisiere()

    def aktualisiere(self):
        self.projektliste.clear()
        if self._ordner is None:
            self.skriptliste.clear()
            return
        for projekt in projekte_in(self._ordner):
            self.projektliste.addItem(projekt.name)
        self._fuelle_skripte()

    def _gewaehltes_projekt(self):
        eintrag = self.projektliste.currentItem()
        if eintrag is None or self._ordner is None:
            return None
        return self._ordner / eintrag.text()

    def _fuelle_skripte(self):
        self.skriptliste.clear()
        projekt = self._gewaehltes_projekt()
        if projekt is None:
            return
        for datei in sorted(projekt.glob("*.py")):
            self.skriptliste.addItem(datei.name)

    # ------------------------------------------------------------- Aktionen

    def _waehle_ordner(self):
        gewaehlt = QFileDialog.getExistingDirectory(self, "Arbeitsordner wählen")
        if gewaehlt:
            self.setze_arbeitsordner(gewaehlt)
            self.arbeitsordner_geaendert.emit(gewaehlt)

    def _neues_projekt(self):
        if self._ordner is None:
            QMessageBox.information(self, "spotlab", "Wähle zuerst einen Arbeitsordner.")
            return
        name, ok = QInputDialog.getText(self, "Neues Projekt", "Name:")
        if not ok or not name.strip():
            return
        try:
            create_project(name, self._ordner)
        except (SpotlabError, FileExistsError) as fehler:
            QMessageBox.warning(self, "spotlab", str(fehler))
            return
        self.aktualisiere()

    def _oeffne_in_spotlab(self):
        projekt = self._gewaehltes_projekt()
        if projekt is not None:
            self.projekt_oeffnen.emit(projekt)

    def _oeffne_projekt(self):
        projekt = self._gewaehltes_projekt()
        if projekt is None:
            return
        try:
            open_in_editor(projekt, command=self._editor)
        except SpotlabError as fehler:
            QMessageBox.warning(self, "spotlab", str(fehler))

    def starte_aktuelles(self):
        """Startet, was in dieser Ansicht gewaehlt ist.

        Oeffentlich, damit der Uebungsraum daran delegieren kann, statt einen
        zweiten Startweg zu bauen: genau EIN Lauf ist der, auf den Stopp und
        NOT-AUS zeigen.
        """
        self._starte()

    def _starte(self):
        projekt = self._gewaehltes_projekt()
        eintrag = self.skriptliste.currentItem()
        if projekt is None or eintrag is None:
            return
        skript = projekt / eintrag.text()
        try:
            prozess = start_script(skript, dryrun=self.trockenlauf.isChecked())
        except SpotlabError as fehler:
            QMessageBox.warning(self, "spotlab", str(fehler))
            return
        self.lauf_gestartet.emit(prozess, str(skript))
