"""Der Dateibaum eines Projekts.

Ein Projekt auf einmal, nicht die ganze Werkstatt: der Baum bleibt kurz genug,
um ihn zu ueberblicken.
"""

from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QFileSystemModel,
    QInputDialog,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

ENDUNGEN = ("*.py", "*.md", "*.txt", "*.json")
SICHTBAR = tuple(e.lstrip("*") for e in ENDUNGEN)      # (".py", ".md", …)

try:
    from send2trash import send2trash as _send2trash
except Exception:       # pragma: no cover - haengt an der Installation
    in_den_papierkorb = None
else:
    def in_den_papierkorb(pfad):
        _send2trash(str(pfad))


class KeineLaeufe(QSortFilterProxyModel):
    """Blendet runs/ auf oberster Ebene aus.

    Namensfilter greifen in Qt nur auf Dateien, nicht auf Verzeichnisse. Und
    ein QFileSystemModel ueber runs/ horcht auf zustand.jsonl, in die der
    Sampler mit 10 Hz schreibt — Aenderungssignale im Zehntelsekundentakt fuer
    Dateien, die im Editor ohnehin niemand oeffnet.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wurzel = None

    def setze_wurzel(self, pfad):
        self._wurzel = Path(pfad) if pfad else None
        # invalidate() statt invalidateRowsFilter(): PySide6 markiert die
        # geschuetzten Varianten als veraltet, und der Projektwechsel ist selten
        # genug, dass die breitere Neubewertung nichts kostet.
        self.invalidate()

    def filterAcceptsRow(self, zeile, eltern):
        quelle = self.sourceModel()
        if quelle is None or self._wurzel is None:
            return True
        index = quelle.index(zeile, 0, eltern)
        if not index.isValid() or not quelle.isDir(index):
            return True
        pfad = Path(quelle.filePath(index))
        return not (pfad.name == "runs" and pfad.parent == self._wurzel)


class Dateibaum(QWidget):
    """Zeigt ein Projekt -- und laesst darin Dateien anlegen.

    GELOESCHT WIRD IN DEN PAPIERKORB, nicht endgueltig. Die Dateien eines
    Schuelers liegen nicht in git; ein Fehlklick waere sonst unwiederbringlich.
    Fehlt `send2trash`, entfaellt der Menueeintrag -- die Oberflaeche kann dann
    weniger, scheitert aber nicht (dieselbe Regel wie bei jedi).
    """

    datei_gewaehlt = Signal(object)
    datei_entfernt = Signal(object)
    meldung = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modell = QFileSystemModel(self)
        self.modell.setNameFilters(list(ENDUNGEN))
        self.modell.setNameFilterDisables(False)

        self.filter = KeineLaeufe(self)
        self.filter.setSourceModel(self.modell)

        self._wurzel = None
        self.ansicht = QTreeView()
        self.ansicht.setModel(self.filter)
        self.ansicht.setHeaderHidden(True)
        for spalte in (1, 2, 3):
            self.ansicht.hideColumn(spalte)
        self.ansicht.doubleClicked.connect(self._gewaehlt)
        self.ansicht.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ansicht.customContextMenuRequested.connect(self._menue_zeigen)

        anordnung = QVBoxLayout(self)
        anordnung.setContentsMargins(0, 0, 0, 0)
        anordnung.addWidget(self.ansicht)

    def setze_projekt(self, pfad):
        self._wurzel = Path(pfad) if pfad else None
        if not pfad:
            self.filter.setze_wurzel(None)
            self.ansicht.setRootIndex(self.filter.index(-1, -1))
            return
        wurzel = Path(pfad)
        self.filter.setze_wurzel(wurzel)
        quelle = self.modell.setRootPath(str(wurzel))
        self.ansicht.setRootIndex(self.filter.mapFromSource(quelle))

    def _gewaehlt(self, index):
        quelle = self.filter.mapToSource(index)
        if self.modell.isDir(quelle):
            return
        self.datei_gewaehlt.emit(Path(self.modell.filePath(quelle)))

    # ------------------------------------------------------ Dateien verwalten

    def zielordner(self, pfad):
        """Wohin Neues kommt: der angeklickte Ordner, sonst dessen Elternteil.

        Ohne Auswahl die Projektwurzel -- ein Rechtsklick ins Leere soll etwas
        tun, nicht nichts.
        """
        if pfad is None:
            return self._wurzel
        pfad = Path(pfad)
        return pfad if pfad.is_dir() else pfad.parent

    def _pruefe_namen(self, name):
        """None, wenn der Name taugt -- sonst der Grund im Klartext."""
        if not name or not name.strip():
            return "Der Name ist leer."
        if name != Path(name).name:
            # "../x.py" oder "a/b.py" wuerde aus dem Projekt herausfuehren.
            return f"'{name}' enthält Pfadtrenner. Gib nur einen Namen an."
        return None

    def neue_datei(self, ordner, name):
        """Legt eine leere Datei an und oeffnet sie. Pfad oder None."""
        grund = self._pruefe_namen(name)
        if grund is None and not name.endswith(SICHTBAR):
            # Der Baum blendet alles andere aus (setNameFilterDisables(False)).
            # Ohne diese Pruefung verschwaende die neue Datei sofort wieder,
            # und jemand suchte eine Datei, die es gibt.
            grund = (f"'{name}' wäre im Baum nicht sichtbar. Erlaubt sind "
                     f"{', '.join(SICHTBAR)}.")
        if grund is not None:
            self.meldung.emit(grund)
            return None
        ziel = Path(ordner) / name
        if ziel.exists():
            self.meldung.emit(f"'{name}' gibt es schon.")
            return None
        try:
            ziel.write_text("", encoding="utf-8", newline="\n")
        except OSError as fehler:
            self.meldung.emit(f"'{name}' liess sich nicht anlegen: {fehler}")
            return None
        self.datei_gewaehlt.emit(ziel)
        return ziel

    def neuer_ordner(self, ordner, name):
        grund = self._pruefe_namen(name)
        if grund is not None:
            self.meldung.emit(grund)
            return None
        ziel = Path(ordner) / name
        if ziel.exists():
            self.meldung.emit(f"'{name}' gibt es schon.")
            return None
        try:
            ziel.mkdir(parents=True)
        except OSError as fehler:
            self.meldung.emit(f"'{name}' liess sich nicht anlegen: {fehler}")
            return None
        return ziel

    def umbenennen(self, pfad, name):
        grund = self._pruefe_namen(name)
        if grund is not None:
            self.meldung.emit(grund)
            return None
        pfad = Path(pfad)
        ziel = pfad.parent / name
        if ziel.exists():
            self.meldung.emit(f"'{name}' gibt es schon.")
            return None
        try:
            pfad.rename(ziel)
        except OSError as fehler:
            self.meldung.emit(f"Umbenennen ging nicht: {fehler}")
            return None
        return ziel

    def loeschen(self, pfad):
        """In den Papierkorb, nie endgueltig."""
        if in_den_papierkorb is None:
            self.meldung.emit(
                "Löschen ist hier nicht eingerichtet (send2trash fehlt)."
            )
            return None
        pfad = Path(pfad)
        try:
            in_den_papierkorb(pfad)
        except Exception as fehler:
            self.meldung.emit(f"Löschen ging nicht: {fehler}")
            return None
        # Damit ein offener Reiter zugeht: sonst zeigte er auf eine
        # verschwundene Datei, und das naechste Speichern legte sie wieder an.
        self.datei_entfernt.emit(pfad)
        return pfad

    # --------------------------------------------------------------- Menue

    def baue_menue(self, pfad):
        """Das Kontextmenue fuer `pfad`. Oeffentlich, damit es pruefbar ist."""
        menue = QMenu(self)
        ordner = self.zielordner(pfad)
        menue.addAction("Neue Datei\u2026", lambda: self._frage_und_lege_an(ordner))
        menue.addAction(
            "Neuer Ordner\u2026", lambda: self._frage_und_lege_ordner_an(ordner)
        )
        if pfad is not None:
            menue.addSeparator()
            menue.addAction(
                "Umbenennen\u2026", lambda: self._frage_und_benenne_um(pfad)
            )
            if in_den_papierkorb is not None:
                menue.addAction(
                    "L\u00f6schen (Papierkorb)", lambda: self.loeschen(pfad)
                )
        return menue

    def _pfad_bei(self, punkt):
        index = self.ansicht.indexAt(punkt)
        if not index.isValid():
            return None
        return Path(self.modell.filePath(self.filter.mapToSource(index)))

    def _menue_zeigen(self, punkt):
        if self._wurzel is None:
            return
        self.baue_menue(self._pfad_bei(punkt)).exec(
            self.ansicht.viewport().mapToGlobal(punkt)
        )

    def _frage_und_lege_an(self, ordner):
        name, ok = QInputDialog.getText(self, "Neue Datei", "Name:", text="neu.py")
        if ok:
            self.neue_datei(ordner, name)

    def _frage_und_lege_ordner_an(self, ordner):
        name, ok = QInputDialog.getText(self, "Neuer Ordner", "Name:")
        if ok:
            self.neuer_ordner(ordner, name)

    def _frage_und_benenne_um(self, pfad):
        name, ok = QInputDialog.getText(
            self, "Umbenennen", "Neuer Name:", text=Path(pfad).name
        )
        if ok:
            self.umbenennen(pfad, name)
