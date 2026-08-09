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

from spotlab.record.run import ABBAU_DATEI, STOPP_DATEI

LEBENSZEICHEN_S = 2.0

# Wie lange ein angefangener Abbau als „läuft noch" gilt. `RealSpot.close()`
# braucht im schlechtesten Fall gut 20 s allein für power_off(timeout_sec=20),
# dazu Stopp-Kommando, Lease-Rückgabe und E-Stop-Abmeldung.
# Endlich, weil ein mitten im Abbau getöteter Prozess die Markierung liegen
# lässt — danach greift wieder die Prozess-ID-Regel.
ABBAU_FRIST_S = 30.0


def ist_aktiv(run_dir, grenze_s=LEBENSZEICHEN_S, jetzt=None):
    """Lebt der Lauf noch — oder baut er gerade ab?

    Gemessen am Änderungszeitpunkt von zustand.jsonl, nicht an der Prozess-ID:
    der Abtaster schreibt mit 10 Hz, und unter Windows ist os.kill(pid, 0) kein
    Test, sondern beendet den Prozess.

    Das allein genügt nicht. Bei Strg-C hört der Abtaster als Erstes auf,
    während der geordnete Abbau noch bis zu 20 s weiterläuft. Nach der reinen
    Abtaster-Regel galt der Lauf dort schon als tot, und der NOT-AUS-Knopf traf
    niemanden — im einzigen Zeitfenster, in dem der Spot noch unter Strom steht
    und der Abbau hängen könnte. Genau das ist der Fall, den Abnahmepunkt A9
    zu prüfen behauptet.

    Deshalb ein AUSDRÜCKLICHES Merkmal statt eines geratenen Zeitfensters: der
    Lauf legt `ABBAU_DATEI` an, wenn er mit dem Abbauen beginnt, und entfernt sie
    am Ende. Ein abgestürzter Prozess kommt nie dazu, sie anzulegen — die Regel
    „eine wiederverwendete Prozess-ID darf niemanden treffen" bleibt dadurch
    unberührt.
    """
    wurzel = Path(run_dir)
    jetzt = jetzt or time.time()
    try:
        alter = jetzt - (wurzel / "zustand.jsonl").stat().st_mtime
    except OSError:
        return False
    if alter <= grenze_s:
        return True
    try:
        seit_abbau = jetzt - (wurzel / ABBAU_DATEI).stat().st_mtime
    except OSError:
        return False
    return seit_abbau <= ABBAU_FRIST_S


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
    """Töten und ehrlich melden, ob es geklappt hat.

    `taskkill` mit `check=False` schluckt jeden Fehlschlag — Rechteproblem,
    Prozess schon weg, falsche ID. Wer den Rückgabewert nicht ansieht, meldet
    dem Schüler „beendet", während der Roboter weiterläuft.
    """
    if os.name == "nt":
        ergebnis = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return ergebnis.returncode == 0
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return False
    return True


def beende_hart(run_dir, killer=None):
    """Prozess des Laufs töten. Gibt zurück, ob der Prozess wirklich weg ist.

    Getötet wird NUR ein Lauf, der nach ist_aktiv() noch lebt. Prozess-IDs
    werden vom Betriebssystem wiederverwendet; eine gespeicherte ID blind zu
    töten könnte einen fremden Prozess treffen.

    Der Rückgabewert ist eine Aussage über den PROZESS, nicht über den
    Knopfdruck. Die GUI hängt ihre Rückmeldung daran — ein falsches „beendet"
    am NOT-AUS-Knopf ist schlimmer als gar keine Rückmeldung.
    """
    if not ist_aktiv(run_dir):
        return False
    pid = pid_von(run_dir)
    if pid is None:
        return False
    return bool((killer or _standard_killer)(pid))
