"""Eine jsonl-Datei mitlesen, während sie geschrieben wird.

Der Abtaster schreibt mit 10 Hz; die GUI liest mit 4 Hz nach. Beim Lesen kann
die letzte Zeile halb geschrieben sein. Sie darf dann NICHT als kaputt
verworfen werden — sonst verliert die Anzeige still Messwerte, und zwar
bevorzugt die letzten vor einem Abbruch, also die interessantesten.

Deshalb wandert der Lesestand nur bis zum letzten vollständigen
Zeilenumbruch; der Rest wird beim nächsten Aufruf gelesen.
"""

import json
from pathlib import Path


class JsonlTail:
    def __init__(self, path):
        self._pfad = Path(path)
        self.stand = 0

    def neue_saetze(self):
        """Alle vollständigen Zeilen seit dem letzten Aufruf."""
        try:
            groesse = self._pfad.stat().st_size
        except OSError:
            return []  # Datei (noch) nicht da

        if groesse < self.stand:  # neu begonnen oder geleert
            self.stand = 0
        if groesse == self.stand:
            return []

        try:
            with self._pfad.open("rb") as datei:
                datei.seek(self.stand)
                roh = datei.read(groesse - self.stand)
        except OSError:
            return []

        letzter_umbruch = roh.rfind(b"\n")
        if letzter_umbruch < 0:
            return []  # noch keine vollständige Zeile
        vollstaendig = roh[: letzter_umbruch + 1]
        self.stand += len(vollstaendig)

        saetze = []
        for zeile in vollstaendig.decode("utf-8", errors="replace").splitlines():
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                saetze.append(json.loads(zeile))
            except json.JSONDecodeError:
                continue
        return saetze
