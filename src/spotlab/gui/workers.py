"""Hintergrund-Arbeiter.

Im Qt-Hauptthread passiert nur Anzeige. diagnose() braucht mehrere Sekunden
übers Netz, und die Pipe eines Kindprozesses muss laufend geleert werden —
sonst füllt sich der Puffer und der Kindprozess bleibt stehen.

Beide Arbeiter fangen Ausnahmen ab und melden sie als Signal: eine GUI, die
still nichts mehr tut, ist schlimmer als eine, die abstürzt.
"""

from PySide6.QtCore import QThread, Signal

from spotlab.workshop.doctor import diagnose


class DoctorWorker(QThread):
    fertig = Signal(list)
    fehler = Signal(str)

    def run(self):
        try:
            self.fertig.emit(list(diagnose()))
        except Exception as fehler:
            self.fehler.emit(f"Prüfung fehlgeschlagen: {type(fehler).__name__}: {fehler}")


class OutputReader(QThread):
    zeile = Signal(str)
    ende = Signal(int)

    def __init__(self, prozess, parent=None):
        super().__init__(parent)
        self._prozess = prozess

    def run(self):
        strom = getattr(self._prozess, "stdout", None)
        if strom is not None:
            try:
                for zeile in strom:
                    self.zeile.emit(zeile.rstrip("\n"))
            except Exception as fehler:
                self.zeile.emit(f"[Ausgabe abgebrochen: {fehler}]")
        try:
            code = int(self._prozess.wait())
        except Exception:
            code = -1
        self.ende.emit(code)
