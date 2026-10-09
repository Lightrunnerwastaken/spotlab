"""Merkorte: benannte Punkte im Rahmen „vision“ — die Orte des Agenten im Übungsraum.

Agenten am Spot, Teil 2 (`docs/superpowers/specs/2026-10-09-agent-karten-design.md`). GraphNav
gibt es nur am echten Spot; im Übungsraum merkt sich der Agent Orte mit Namen und fährt mit der
Wegsuche hin. Sie heissen bewusst anders als Wegpunkte: sie tun nicht so, als wären sie Karten.

Die Zentrale hält sie. Mit `pfad` (im Übungsraum: neben dem Raum im Arbeitsordner, `pfad_fuer`)
werden sie beim Bau gelesen und nach jeder Änderung atomar geschrieben — eine eigene Datei, damit
der Raumeditor sie beim Speichern des Raums nicht verliert. Ohne `pfad` (am echten Spot: der
Rahmen „vision“ setzt sich bei jedem Start neu) leben sie nur im Speicher.
"""

import json
import math
from pathlib import Path

from spotlab.record import atomar

MAX_ZEICHEN = 40
ENDUNG = ".merkorte.json"


def pfad_fuer(arbeitsordner, raum):
    """`<Arbeitsordner>/raeume/<raum>.merkorte.json` — neben einem eigenen Raum, und für eine
    Vorlage aus dem Paket an derselben Stelle (dort darf nichts geschrieben werden)."""
    from spotlab.welt.raum import raum_pfad

    return raum_pfad(arbeitsordner, raum).with_name(f"{raum}{ENDUNG}")


def _name(name):
    name = str(name or "").strip()
    if not 1 <= len(name) <= MAX_ZEICHEN:
        raise ValueError(f"Ein Merkort braucht einen Namen mit 1 bis {MAX_ZEICHEN} Zeichen, nicht "
                         f"{name!r}")
    return name


class Merkorte:
    def __init__(self, pfad=None):
        self.pfad = Path(pfad) if pfad else None
        self._orte = {}
        if self.pfad is not None:
            self._orte = _lies(self.pfad)

    def setze(self, name, x, y):
        """Den Ort setzen (ein vorhandener Name wird verschoben). Gibt den bereinigten Namen."""
        name = _name(name)
        x, y = float(x), float(y)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(f"Ein Merkort braucht endliche Zahlen, nicht ({x}, {y})")
        self._orte[name] = (x, y)
        self._schreibe()
        return name

    def loesche(self, name):
        weg = self._orte.pop(str(name or "").strip(), None) is not None
        if weg:
            self._schreibe()
        return weg

    def hole(self, name):
        return self._orte.get(str(name or "").strip())

    def namen(self):
        return list(self._orte)

    def als_daten(self):
        return [{"name": n, "x": x, "y": y} for n, (x, y) in self._orte.items()]

    def _schreibe(self):
        if self.pfad is None:
            return
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        atomar.schreibe_atomar(self.pfad, json.dumps(self.als_daten(), ensure_ascii=False))


def _lies(pfad):
    """Die Orte aus der Datei — fehlend oder kaputt heisst: keine."""
    try:
        roh = json.loads(Path(pfad).read_text(encoding="utf-8"))
        return {_name(o["name"]): (float(o["x"]), float(o["y"])) for o in roh}
    except (OSError, ValueError, TypeError, KeyError):
        return {}
