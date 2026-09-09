"""Der Draht zwischen dem Karten-Tab und dem Navigationslauf: zwei Dateien.

Die GUI hält keinen Draht in den Lauf — die Platte ist der einzige Kanal, in
beide Richtungen, wie bei `fahrt.json` und `kamera.json`:

    ziel.json         GUI → Lauf   der angeklickte Wegpunkt, mit laufender Nummer
    navigation.json   Lauf → GUI   was der Lauf gerade tut, und wo Spot steht

Die Nummer im Ziel ist der Grund, warum derselbe Wegpunkt zweimal angeklickt
werden kann: der Lauf reagiert auf eine NEUE Nummer, nicht auf einen neuen
Namen. Der Stand trägt den Wegpunkt, an dem Spot verortet ist, und den Versatz
des Körpers dazu — die GUI rechnet daraus die Lage im Grundriss
(`maps/geometry.py::lage_im_grundriss`), denn nur sie kennt den Grundriss.

Beide Dateien werden atomar ersetzt (`record/atomar.py`); ein halb
geschriebener Stand wird beim Lesen zu `None`, nie zu einem Fehler.
"""

import json
import time
from pathlib import Path

from spotlab.record import atomar

ZIEL_DATEI = "ziel.json"
STAND_DATEI = "navigation.json"
STATI = ("lade_karte", "verorte", "bereit", "unterwegs", "angekommen", "gescheitert", "beendet")


def schreibe_ziel(lauf_dir, wegpunkt, nr, jetzt=time.time):
    """Das Ziel der GUI. `nr` steigt bei jedem Klick; True, wenn es geschrieben ist."""
    return atomar.schreibe_atomar(
        Path(lauf_dir) / ZIEL_DATEI,
        json.dumps({"wegpunkt": str(wegpunkt), "nr": int(nr), "t": float(jetzt())}),
    )


def lies_ziel(lauf_dir):
    """(wegpunkt, nr) -- oder None, wenn kein oder kein lesbares Ziel da ist."""
    daten = _lies(Path(lauf_dir) / ZIEL_DATEI)
    if not daten or not daten.get("wegpunkt") or not isinstance(daten.get("nr"), int):
        return None
    return str(daten["wegpunkt"]), int(daten["nr"])


def schreibe_stand(lauf_dir, status, text="", karte=None, ziel=None,
                   standort=None, versatz=None, jetzt=time.time):
    """Der Stand des Laufs. `versatz` ist (dx, dy, grad) des Körpers zum `standort`."""
    if status not in STATI:
        raise ValueError(f"Unbekannter Navigationsstand '{status}'. Erlaubt: {', '.join(STATI)}.")
    return atomar.schreibe_atomar(
        Path(lauf_dir) / STAND_DATEI,
        json.dumps({
            "status": status,
            "text": str(text or ""),
            "karte": karte,
            "ziel": ziel,
            "standort": standort,
            "versatz": [float(v) for v in versatz] if versatz is not None else None,
            "t": float(jetzt()),
        }),
    )


def lies_stand(lauf_dir):
    """Der Stand als dict -- oder None, wenn keiner oder kein lesbarer da ist."""
    daten = _lies(Path(lauf_dir) / STAND_DATEI)
    if not daten or daten.get("status") not in STATI:
        return None
    versatz = daten.get("versatz")
    if versatz is not None and (not isinstance(versatz, list) or len(versatz) != 3):
        daten["versatz"] = None
    return daten


def _lies(pfad):
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return daten if isinstance(daten, dict) else None
