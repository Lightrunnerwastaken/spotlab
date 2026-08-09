"""Ein Lauf = ein Verzeichnis mit Metadaten, Ereignisstrom, Zustandsabtastung, Bildern.

jsonl statt Datenbank: mitlesbar während der Lauf läuft, ein Absturz kostet
höchstens die letzte Zeile, ohne Werkzeug lesbar.
"""

import getpass
import hashlib
import json
import os
import platform
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from spotlab.record.events import ARTEN, ERGEBNISSE

ZEITFORMAT = "%Y%m%dT%H%M%SZ"
STOPP_DATEI = "stopp"  # von der GUI angelegt; der Abtaster bricht daraufhin ab
ABBAU_DATEI = "abbau"  # vom Lauf angelegt, solange close() läuft und der Abtaster schweigt


def _sha256(pfad):
    hasher = hashlib.sha256()
    with Path(pfad).open("rb") as datei:
        for block in iter(lambda: datei.read(65536), b""):
            hasher.update(block)
    return hasher.hexdigest()


def run_id(script_path, now):
    zeit = now.astimezone(UTC).strftime(ZEITFORMAT)
    kurz = "interakt" if script_path is None else _sha256(script_path)[:8]
    return f"{zeit}_{kurz}"


def _freies_verzeichnis(runs_dir, kennung):
    """Kollisionen auflösen: zwei Läufe pro Sekunde dürfen sich nicht überschreiben.

    Ohne Skript ist die Kurzkennung immer "interakt", und auch dasselbe Skript
    zweimal in derselben Sekunde ergäbe dieselbe ID. Beide Läufe schrieben dann
    in dieselben jsonl-Dateien und überschrieben gegenseitig lauf.json.
    """
    ziel = runs_dir / kennung
    nummer = 2
    while ziel.exists():
        ziel = runs_dir / f"{kennung}-{nummer}"
        nummer += 1
    return ziel.name, ziel


class RunRecorder:
    """Schreibt einen Lauf nach runs_dir/<id>/. Threadsicher."""

    def __init__(self, runs_dir, script_path, backend, nickname="", user=None):
        self._t0 = time.monotonic()
        self._sperre = threading.RLock()
        jetzt = datetime.now(UTC)
        self._script_path = Path(script_path) if script_path else None
        self.id, self.dir = _freies_verzeichnis(
            Path(runs_dir), run_id(self._script_path, jetzt)
        )
        (self.dir / "bilder").mkdir(parents=True, exist_ok=True)
        self._bilder = []
        self._meta = {
            "id": self.id,
            "gestartet": jetzt.isoformat(),
            "dauer_s": 0.0,
            "backend": backend,
            "nickname": nickname,
            "spotlab_version": _version(),
            "benutzer": user or f"{getpass.getuser()}@{socket.gethostname()}",
            "python": platform.python_version(),
            "pid": os.getpid(),
            "skript": str(self._script_path) if self._script_path else None,
            "skript_sha256": _sha256(self._script_path) if self._script_path else None,
            "ergebnis": "läuft",
            "fehler": None,
            "uebernommen": False,
        }
        self._schreibe_meta()

    # ---------------------------------------------------------------- schreiben

    def event(self, art, **daten):
        if art not in ARTEN:
            raise ValueError(f"Unbekannte Ereignisart: {art!r}")
        self._zeile("ereignisse.jsonl", {"t": self._t(), "art": art, "daten": daten})

    def sample(self, daten):
        self._zeile("zustand.jsonl", {"t": self._t(), "daten": daten})

    def image(self, name, roh, meta):
        meta = dict(meta)
        endung = meta.pop("endung", "png")
        datei = f"{len(self._bilder):04d}_{name}.{endung}"
        ziel = self.dir / "bilder" / datei
        ziel.write_bytes(roh)
        eintrag = {"t": self._t(), "datei": datei, **meta}
        with self._sperre:
            self._bilder.append(eintrag)
            (self.dir / "bilder" / "bilder.json").write_text(
                json.dumps(self._bilder, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        self.event("bild", datei=datei, source=meta.get("source"))
        return ziel

    def set_robot_info(self, **felder):
        with self._sperre:
            self._meta.update(felder)
        self._schreibe_meta()

    def abbau_beginnt(self):
        """Markiert: ab jetzt wird abgebaut, der Abtaster schweigt schon.

        Ohne diese Markierung gilt der Lauf während des Abbaus als tot — der
        Abtaster ist das einzige Lebenszeichen und hört als Erstes auf, während
        `close()` noch bis zu 20 s läuft. Der NOT-AUS-Knopf träfe in genau
        diesem Fenster niemanden (`workshop/control.py::ist_aktiv`).

        Darf nie werfen: sie hängt im Abbaupfad.
        """
        try:
            (self.dir / ABBAU_DATEI).touch()
        except OSError:
            pass

    def finish(self, ergebnis, fehler=None):
        if ergebnis not in ERGEBNISSE:
            raise ValueError(f"Unbekanntes Ergebnis: {ergebnis!r}")
        self.event("ende", ergebnis=ergebnis, fehler=fehler)
        try:
            (self.dir / ABBAU_DATEI).unlink(missing_ok=True)
        except OSError:
            pass
        with self._sperre:
            self._meta["ergebnis"] = ergebnis
            self._meta["fehler"] = fehler
            self._meta["dauer_s"] = round(self._t(), 3)
        self._schreibe_meta()

    # ---------------------------------------------------------------- intern

    def _t(self):
        return time.monotonic() - self._t0

    def _zeile(self, datei, satz):
        text = json.dumps(satz, ensure_ascii=False, default=str) + "\n"
        with self._sperre, (self.dir / datei).open("a", encoding="utf-8") as ziel:
            ziel.write(text)
            ziel.flush()
            os.fsync(ziel.fileno())

    def _schreibe_meta(self):
        with self._sperre:
            (self.dir / "lauf.json").write_text(
                json.dumps(self._meta, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )


def _version():
    from spotlab import __version__

    return __version__
