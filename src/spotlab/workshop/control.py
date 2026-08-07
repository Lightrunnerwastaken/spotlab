"""Läufe finden und anhalten — ohne Qt, ohne Roboterverbindung.

Zwei Wege, wie im Entwurf festgelegt:

freundlich  Markierung ins Lauf-Verzeichnis; der Abtaster löst daraufhin
            KeyboardInterrupt aus, der Abbau läuft, der Spot setzt sich hin.
hart        Prozess töten; die Keepalives sterben, der Roboter schneidet die
            Motorleistung ab. Ein stehender Spot sackt dabei zusammen — das
            ist die Bedeutung eines Not-Aus, kein Fehler.
"""

import json
import os
import signal
import subprocess
import time
from pathlib import Path

from spotlab.record.run import STOPP_DATEI

LEBENSZEICHEN_S = 2.0


def ist_aktiv(run_dir, grenze_s=LEBENSZEICHEN_S, jetzt=None):
    """Lebt der Lauf noch?

    Gemessen am Änderungszeitpunkt von zustand.jsonl, nicht an der Prozess-ID:
    der Abtaster schreibt mit 10 Hz, und unter Windows ist os.kill(pid, 0) kein
    Test, sondern beendet den Prozess.
    """
    zustand = Path(run_dir) / "zustand.jsonl"
    try:
        letzte_aenderung = zustand.stat().st_mtime
    except OSError:
        return False
    return (jetzt or time.time()) - letzte_aenderung <= grenze_s


def aktive_laeufe(runs_dir, grenze_s=LEBENSZEICHEN_S):
    wurzel = Path(runs_dir)
    if not wurzel.is_dir():
        return []
    return sorted(
        (p for p in wurzel.iterdir() if p.is_dir() and ist_aktiv(p, grenze_s)),
        key=lambda p: p.name,
    )


def pid_von(run_dir):
    lauf = Path(run_dir) / "lauf.json"
    try:
        daten = json.loads(lauf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pid = daten.get("pid")
    return int(pid) if isinstance(pid, int) else None


def stoppe_freundlich(run_dir):
    """Markierung anlegen. Der Abtaster des Laufs sieht sie beim nächsten Takt."""
    (Path(run_dir) / STOPP_DATEI).touch()


def _standard_killer(pid):
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        os.kill(pid, signal.SIGKILL)


def beende_hart(run_dir, killer=None):
    """Prozess des Laufs töten. Gibt False zurück, wenn nichts zu töten war.

    Getötet wird NUR ein Lauf, der nach ist_aktiv() noch lebt. Prozess-IDs
    werden vom Betriebssystem wiederverwendet; eine gespeicherte ID blind zu
    töten könnte einen fremden Prozess treffen. Die Lebendigkeitsprüfung bindet
    das Zeitfenster auf zwei Sekunden.
    """
    if not ist_aktiv(run_dir):
        return False
    pid = pid_von(run_dir)
    if pid is None:
        return False
    (killer or _standard_killer)(pid)
    return True
