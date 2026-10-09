"""Die Klickfahrt der Steuerzentrale: zu einem angeklickten Punkt gehen — rein rechnerisch.

Ein Klick in die Draufsicht wird geprüft (höchstens `MAX_WEITE_M`, gesehener freier
Boden, `RAND_M` Abstand zur Wand), dann plant `workshop/wegsuche.py` einen Weg über
bekannten Boden. Je Takt sagt `schritt`, wie Spot geht: liegt der nächste Wegpunkt mehr
als `DREH_AB_GRAD` daneben, dreht er auf der Stelle, sonst geht er und lenkt; nah am
Ziel wird er langsamer, auf `ANKUNFT_M` ist er angekommen.

Die Schranken sind die des Folgens und fail-closed: frei voraus aus dem letzten
Hindernisgitter (None heisst unlesbar, also stehen) und der Kopfraum. Hält eine
Schranke, plant er höchstens alle `NEU_PLANEN_S` neu; hält sie `VERSPERRT_NACH_S`
lang, gibt er auf („versperrt“). Tempo und Drehen sind die der Tasten
(`record/fahrt.TEMPO_M_S`, `DREH_RAD_S`) mal dem Stufenfaktor.

Ohne Roboter prüfbar; `workshop/zentrale.py` gibt Lage, Skizze und Schranken hinein.
"""

import math
from dataclasses import dataclass, field

from spotlab.record import fahrt as fahrtdatei
from spotlab.workshop import wegsuche

MAX_WEITE_M = 5.0
RAND_M = 0.3
ANKUNFT_M = 0.25
ZWISCHEN_M = 0.3           # so nah an einem Zwischenpunkt: weiter zum nächsten
DREH_AB_GRAD = 30.0        # weiter daneben: erst auf der Stelle drehen
LENKUNG = 1.5              # rad/s je rad Abweichung
FREIRAUM_M = 0.8           # wie beim Folgen (`folgen.FREIRAUM_M`)
LANGSAM_JE_M = 0.8         # nah am Ziel: m/s je Meter Restweg
MIN_TEMPO_M_S = 0.1
NEU_PLANEN_S = 2.0
VERSPERRT_NACH_S = 6.0


@dataclass
class Stand:
    """Was die Klickfahrt gerade tut — so steht es im Lagebild."""

    nummer: int = 0
    zustand: str = "keine"
    grund: str = ""
    ziel: tuple | None = None
    weg: list = field(default_factory=list)
    quelle: str = "tab"        # wer das Ziel gesetzt hat: "tab" (Klick) oder "agent"

    def als_daten(self):
        return {
            "nummer": int(self.nummer),
            "zustand": self.zustand,
            "grund": self.grund,
            "ziel": None if self.ziel is None else [float(self.ziel[0]), float(self.ziel[1])],
            "weg": [[float(x), float(y)] for x, y in self.weg],
            "quelle": self.quelle,
        }


def _wickle(rad):
    return (rad + math.pi) % (2.0 * math.pi) - math.pi


def _restweg(x, y, weg):
    rest, a = 0.0, (x, y)
    for punkt in weg:
        rest += math.dist(a, punkt)
        a = punkt
    return rest


class Klickfahrt:
    def __init__(self):
        self.stand = Stand()
        self._geplant = None
        self._gesperrt_seit = None

    @property
    def unterwegs(self):
        return self.stand.zustand == "unterwegs"

    def neues_ziel(self, nummer, ziel, lage, skizze, t, quelle="tab"):
        """Ein neues Ziel prüfen und den Weg planen. `lage` = (x, y, gier) im Rahmen der Skizze."""
        self.stand = Stand(nummer=int(nummer), ziel=(float(ziel[0]), float(ziel[1])),
                           quelle=quelle)
        grund = wegsuche.pruefe_ziel(skizze, lage[:2], ziel, RAND_M, MAX_WEITE_M)
        if grund:
            self.stand.zustand, self.stand.grund = "abgelehnt", grund
            return
        weg = wegsuche.weg(skizze, lage[:2], ziel, RAND_M)
        if weg is None:
            self.stand.zustand = "abgelehnt"
            self.stand.grund = "kein Weg über bekannten Boden dorthin"
            return
        self.stand.zustand, self.stand.weg = "unterwegs", weg
        self._geplant, self._gesperrt_seit = t, None

    def abbrechen(self, grund):
        if self.unterwegs:
            self.stand.zustand, self.stand.grund = "abgebrochen", grund

    def schritt(self, lage, skizze, t, frei_m, faktor=1.0, kopf_frei=True, kopf_grund=""):
        """(vx, wz) für diesen Takt. `frei_m`: freie Strecke voraus, None = nicht lesbar."""
        if not self.unterwegs:
            return 0.0, 0.0
        x, y, gier = lage
        while self.stand.weg:
            px, py = self.stand.weg[0]
            letzter = len(self.stand.weg) == 1
            if math.hypot(px - x, py - y) <= (ANKUNFT_M if letzter else ZWISCHEN_M):
                self.stand.weg.pop(0)
            else:
                break
        if not self.stand.weg:
            self.stand.zustand, self.stand.grund = "angekommen", ""
            return 0.0, 0.0
        px, py = self.stand.weg[0]
        abweichung = _wickle(math.atan2(py - y, px - x) - gier)
        dreh_max = fahrtdatei.DREH_RAD_S * faktor
        wz = max(-dreh_max, min(dreh_max, LENKUNG * abweichung))
        if abs(math.degrees(abweichung)) > DREH_AB_GRAD:
            self._gesperrt_seit = None
            return 0.0, wz                     # auf der Stelle drehen braucht keinen Freiraum
        rest = _restweg(x, y, self.stand.weg)
        noetig = min(FREIRAUM_M, rest + 0.15)
        if not kopf_frei:
            grund = kopf_grund or "Überhang voraus"
        elif frei_m is None:
            grund = "Hindernisgitter nicht lesbar"
        elif frei_m < noetig:
            grund = f"nur {frei_m:.1f} m frei voraus"
        else:
            grund = ""
        if grund:
            # Stehen, aber weiter zum Weg hin DREHEN: schräg vor einer Tür läuft der
            # Strahl auf die Kante, geradeaus ist frei (Kette im Übungsraum, 27.09.2026).
            self._gesperrt(lage, skizze, t, grund)
            return 0.0, (wz if self.unterwegs else 0.0)
        self._gesperrt_seit = None
        tempo_max = fahrtdatei.TEMPO_M_S * faktor
        vx = min(tempo_max, max(MIN_TEMPO_M_S, LANGSAM_JE_M * rest))
        return vx, wz

    def _gesperrt(self, lage, skizze, t, grund):
        """Eine Schranke hält: neu planen (höchstens alle NEU_PLANEN_S), irgendwann aufgeben."""
        if self._gesperrt_seit is None:
            self._gesperrt_seit = t
        if t - self._gesperrt_seit >= VERSPERRT_NACH_S:
            self.stand.zustand, self.stand.grund = "versperrt", f"Weg versperrt ({grund})"
            return
        if self._geplant is None or t - self._geplant >= NEU_PLANEN_S:
            self._geplant = t
            weg = wegsuche.weg(skizze, lage[:2], self.stand.ziel, RAND_M)
            if weg is None:
                self.stand.zustand = "versperrt"
                self.stand.grund = f"kein Weg mehr ({grund})"
                return
            self.stand.weg = weg
