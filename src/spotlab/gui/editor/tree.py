"""Der Dateibaum eines Projekts.

Ein Projekt auf einmal, nicht die ganze Werkstatt: der Baum bleibt kurz genug,
um ihn zu ueberblicken.
"""

from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Signal
from PySide6.QtWidgets import QFileSystemModel, QTreeView, QVBoxLayout, QWidget

ENDUNGEN = ("*.py", "*.md", "*.txt", "*.json")


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
    datei_gewaehlt = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modell = QFileSystemModel(self)
        self.modell.setNameFilters(list(ENDUNGEN))
        self.modell.setNameFilterDisables(False)

        self.filter = KeineLaeufe(self)
        self.filter.setSourceModel(self.modell)

        self.ansicht = QTreeView()
        self.ansicht.setModel(self.filter)
        self.ansicht.setHeaderHidden(True)
        for spalte in (1, 2, 3):
            self.ansicht.hideColumn(spalte)
        self.ansicht.doubleClicked.connect(self._gewaehlt)

        anordnung = QVBoxLayout(self)
        anordnung.setContentsMargins(0, 0, 0, 0)
        anordnung.addWidget(self.ansicht)

    def setze_projekt(self, pfad):
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
