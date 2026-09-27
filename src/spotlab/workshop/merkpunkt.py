"""Der Merkpunkt: wo der Mensch steht — als Punkt im Raum, nicht als Winkel im Bild.

Bis zum 27.09.2026 kannte `folge()` den Menschen nur so, wie ihn das letzte Bild
zeigte: Peilung und Abstand, auf die Drehung seither nachgeführt. Fehlte ein
Bild länger als den Nachlauf (1 s), stand Spot und suchte. Zwei Folge-Aufnahmen
vom 25.09.2026 zeigen, was dabei verloren ging: von 74 Lücken über einer
Sekunde stand der Mensch 70-mal VOR Spot und wurde nur ein, zwei Bilder lang
übersehen, und in der Lücke ging er im Mittel 0.4 m weit. 48 der Lücken waren
kürzer als drei Sekunden.

Der Merkpunkt liegt in den Koordinaten der Odometrie (`state.pose`: wie weit
Spot selbst gelaufen und gedreht ist). Deshalb stimmen Peilung und Abstand zum
Menschen auch nach einer Fahrt ohne neues Bild, und Spot kann den Menschen
`HALTEN_S` lang festhalten. Aus den letzten Punkten kommt ein Tempo: läuft der
Mensch seitlich aus dem Bild, zeigt das gemerkte Ziel dorthin, wo er in einer
Sekunde sein sollte — weiter voraus wird nicht geraten, denn die Abstände
streuen, und über längere Lücken war die Vorhersage in den Aufnahmen schlechter
als „er steht noch dort“.

Mit dem Punkt wählt Spot auch, WEM er folgt: von mehreren Menschen den, der
dort steht, wo der gemerkte erwartet wird oder zuletzt war — nicht mehr einfach
den nächsten. Wer weiter daneben steht als `fang_m()`, ist ein anderer. Das gilt
erst ab `MIN_TREFFER` passenden Erkennungen hintereinander: ein Punkt aus EINER
Messung schützt vor niemandem. Nachgespielt an Fahrt 2 begannen fünf von acht
verworfenen Erkennungen mit einem einzelnen Ausreisser der Tiefe in 7-8 m, und
der echte Mensch in 4 m galt drei Sekunden lang als „ein anderer“.

Rein rechnerisch, ohne Roboter prüfbar; `folge()` gibt Zeit und Lage hinein.
"""

import math
from dataclasses import replace

# So lange gilt der Punkt ohne neue Erkennung. Blind FAHREN darf Spot nur den
# Nachlauf lang (`folgen.NACHLAUF_S`), danach dreht er höchstens noch mit.
HALTEN_S = 3.0
# So weit voraus wird die Laufrichtung verlängert, nicht weiter.
VORHERSAGE_S = 1.0
# Aus den Punkten dieser letzten Sekunden kommt das Tempo; mindestens so viel
# Zeit muss zwischen dem ersten und dem letzten liegen, sonst ist es null.
TEMPO_FENSTER_S = 2.0
MIN_SPANNE_S = 0.4
# Schneller als ein schnell gehender Mensch wird nichts angenommen: ein Sprung in
# der Tiefe (Fahrt 2: einmal 3.1 m/s) ist ein Messfehler, kein Sprint.
MAX_MENSCH_M_S = 1.5
# Der Fangkreis um die Erwartung: so weit daneben darf eine Erkennung liegen und
# ist noch ER. Er wächst mit dem Abstand (die Tiefe streut weit weg mehr) und mit
# der Zeit seit der letzten Erkennung (ein gehender Mensch ist nach einer Sekunde
# einen Meter weiter). Nachgespielt an beiden Fahrten lag die nächste Erkennung im
# Mittel 0.07-0.13 m neben der Vorhersage, in neun von zehn Fällen unter 0.45 m.
FANG_M = 1.0
FANG_JE_M = 0.15
FANG_JE_S = 1.0
# Ab so vielen passenden Erkennungen hintereinander ist der Punkt bestätigt.
MIN_TREFFER = 2


def in_raum(ort, gier, peilung_grad, abstand):
    """(x, y) im Raum aus der Lage des Roboters und Peilung/Abstand des Ziels."""
    winkel = gier + math.radians(peilung_grad)
    return ort[0] + abstand * math.cos(winkel), ort[1] + abstand * math.sin(winkel)


def vom_roboter(ort, gier, punkt):
    """(Peilung in Grad, links positiv; Abstand) eines Raumpunkts, gesehen vom Roboter."""
    dx, dy = punkt[0] - ort[0], punkt[1] - ort[1]
    winkel = math.atan2(dy, dx) - gier
    winkel = (winkel + math.pi) % (2.0 * math.pi) - math.pi
    return math.degrees(winkel), math.hypot(dx, dy)


def _hat_ort(ziel):
    return getattr(ziel, "ort", None) is not None and getattr(ziel, "gier", None) is not None


class Merkpunkt:
    """Der gemerkte Mensch: Punkte im Raum, daraus Ort, Tempo und Erwartung."""

    def __init__(self, halten_s=HALTEN_S):
        self.halten_s = float(halten_s)
        self._punkte = []            # [(t, x, y)], nur die letzten TEMPO_FENSTER_S
        self._treffer = 0            # passende Erkennungen hintereinander
        self.befund = ""

    # ------------------------------------------------------------ Zustand

    def vergessen(self):
        self._punkte = []
        self._treffer = 0

    def bestaetigt(self, t):
        """Aktiv UND aus mindestens MIN_TREFFER passenden Erkennungen."""
        return self.aktiv(t) and self._treffer >= MIN_TREFFER

    def alter(self, t):
        """Sekunden seit der letzten Erkennung — None ohne Punkt."""
        return None if not self._punkte else t - self._punkte[-1][0]

    def aktiv(self, t):
        alter = self.alter(t)
        return alter is not None and alter <= self.halten_s

    def aufnehmen(self, t, ziel):
        """Eine ECHTE Erkennung merken. Ohne Ort (Tag, alter Finder) gibt es nichts zu merken."""
        if not _hat_ort(ziel):
            self.vergessen()
            return
        x, y = in_raum(ziel.ort, ziel.gier, ziel.bearing, ziel.distance)
        if not self.aktiv(t) or self._daneben(t, (x, y)) > self.fang_m(t, ziel.distance):
            # Abgelaufen, oder ein unbestätigter Punkt passt nicht: neu anfangen, statt
            # aus dem Sprung ein Tempo zu machen.
            self.vergessen()
        self._punkte.append((t, x, y))
        self._treffer += 1
        self._punkte = [p for p in self._punkte if t - p[0] <= TEMPO_FENSTER_S]

    # ------------------------------------------------------------ Rechnen

    def tempo(self):
        """(vx, vy) in m/s aus den letzten Punkten — Ausgleichsgerade, gedeckelt."""
        if len(self._punkte) < 2 or self._punkte[-1][0] - self._punkte[0][0] < MIN_SPANNE_S:
            return 0.0, 0.0
        n = len(self._punkte)
        tm = sum(p[0] for p in self._punkte) / n
        xm = sum(p[1] for p in self._punkte) / n
        ym = sum(p[2] for p in self._punkte) / n
        stt = sum((p[0] - tm) ** 2 for p in self._punkte)
        vx = sum((p[0] - tm) * (p[1] - xm) for p in self._punkte) / stt
        vy = sum((p[0] - tm) * (p[2] - ym) for p in self._punkte) / stt
        betrag = math.hypot(vx, vy)
        if betrag > MAX_MENSCH_M_S:
            vx, vy = vx * MAX_MENSCH_M_S / betrag, vy * MAX_MENSCH_M_S / betrag
        return vx, vy

    def erwartet(self, t):
        """Wo der Mensch zur Zeit `t` sein sollte — höchstens VORHERSAGE_S weiter gerechnet."""
        if not self._punkte:
            return None
        t0, x, y = self._punkte[-1]
        vx, vy = self.tempo()
        voraus = min(max(0.0, t - t0), VORHERSAGE_S)
        return x + vx * voraus, y + vy * voraus

    def fang_m(self, t, abstand):
        """So weit neben der Erwartung darf eine Erkennung liegen und ist noch er."""
        alter = self.alter(t) or 0.0
        return FANG_M + FANG_JE_M * float(abstand) + FANG_JE_S * max(0.0, alter)

    def _daneben(self, t, punkt):
        """Abstand zur Erwartung ODER zum zuletzt gesehenen Ort -- der kleinere zählt.

        Die Vorhersage ist ein Hinweis, keine Bedingung: aus zwei Punkten geschätzt kann
        sie hinausschiessen (Fahrt 2, 52.3 s: 1.9 m daneben, der Mensch stand 1.2 m neben
        seinem letzten Ort).
        """
        return min(math.dist(punkt, self.erwartet(t)), math.dist(punkt, self._punkte[-1][1:]))

    def weg_tempo(self, ort):
        """Wie schnell der Mensch sich vom Roboter bei `ort` entfernt (m/s, auf ihn zu negativ)."""
        if not self._punkte:
            return 0.0
        _, x, y = self._punkte[-1]
        dx, dy = x - ort[0], y - ort[1]
        weite = math.hypot(dx, dy)
        if weite < 1e-9:
            return 0.0
        vx, vy = self.tempo()
        return (vx * dx + vy * dy) / weite

    # ------------------------------------------------------------ Für folge()

    def waehle(self, t, kandidaten):
        """Welcher der erkannten Menschen ist ER? Ohne aktiven Punkt: der nächste.

        Mit bestätigtem Punkt: der, der am nächsten an der Erwartung (oder am zuletzt
        gesehenen Ort) steht — und nur, wenn er im Fangkreis liegt. Sonst None, und
        `befund` sagt, wie weit der nächste daneben war.
        """
        self.befund = ""
        kandidaten = list(kandidaten)
        if not kandidaten:
            return None
        mit_ort = [k for k in kandidaten if _hat_ort(k)]
        if not self.bestaetigt(t) or not mit_ort:
            return min(kandidaten, key=lambda k: k.distance)

        def daneben(k):
            return self._daneben(t, in_raum(k.ort, k.gier, k.bearing, k.distance))

        bester = min(mit_ort, key=daneben)
        weite = daneben(bester)
        if weite <= self.fang_m(t, bester.distance):
            return bester
        self.befund = (f"{len(mit_ort)} gesehen, keiner beim Merkpunkt "
                       f"(der nächste {weite:.1f} m daneben)")
        return None

    def ziel(self, t, ort, gier, vorlage):
        """Das gemerkte Ziel, gesehen vom Roboter JETZT (Lage `ort`, `gier`) — oder None.

        Name und Oberkante kommen von `vorlage` (dem zuletzt gesehenen Ziel); die Gier
        fällt weg, denn Peilung und Abstand sind schon auf jetzt gerechnet.
        """
        if not self.aktiv(t):
            return None
        peilung, abstand = vom_roboter(ort, gier, self.erwartet(t))
        return replace(vorlage, bearing=peilung, distance=abstand, gier=None, ort=None)

    def bericht(self, t):
        """Der Punkt für die Aufnahme — oder None ohne Punkt."""
        if not self._punkte:
            return None
        x, y = self.erwartet(t)
        vx, vy = self.tempo()
        return {"x": round(x, 3), "y": round(y, 3), "vx": round(vx, 3), "vy": round(vy, 3),
                "alter_s": round(self.alter(t), 3)}
