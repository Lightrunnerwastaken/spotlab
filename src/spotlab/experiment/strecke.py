"""Wie lang ist die Strecke — gemessen, nicht eingetippt.

Zwei AprilTags markieren Anfang und Ende. Spot sieht beide, rechnet aus Peilung
und Abstand ihre Lage in der Bodenebene und misst dazwischen. Das ist der Grund,
warum der Versuch ueberhaupt ein TEMPO liefern kann und nicht nur eine Zeit.

WARUM NICHT EINTIPPEN. Ein Massband am Boden misst genauer als Spot. Aber die
eingetippte Zahl ist die bequemste Fehlerquelle des ganzen Versuchs: sie
stimmt beim ersten Aufbau und bleibt stehen, wenn jemand die Tags am naechsten
Tag zwei Meter weiter haengt. Die Zeiten sahen dann weiter richtig aus und jedes
Tempo waere um denselben Faktor falsch. Gemessen wird die Strecke, die HEUTE
zwischen den Tags liegt — und wie stark die Einzelmessungen dabei streuten,
steht daneben (`streuung_m`). Wem das zu ungenau ist, der nimmt das Massband
und traegt den Wert als `strecke_m` in die Tabelle nach; auch das ist dann eine
bewusste Handlung und keine Altlast.

Reine Standardbibliothek: hier wird auf Zahlen gerechnet, nicht auf Robotern.
"""

import math
import statistics
from dataclasses import dataclass

from spotlab.errors import SpotlabError

# So viele Abtastungen muessen BEIDE Tags zeigen, bevor eine Laenge gilt. Zwei
# waeren keine Streuung, sondern eine Differenz.
MINDESTPROBEN = 3
# Ab hier wackelt die Messung so stark, dass das Programm nachfragt statt zu
# rechnen. Kein Naturgesetz — die Erkennungsreichweite der Tags misst erst
# Abnahmepunkt A22, danach gehoert die Zahl hierher zurueck.
MAX_STREUUNG_M = 0.5


@dataclass(frozen=True)
class Punkt:
    """Lage in der Bodenebene des Koerperrahmens: x vorwaerts, y links, Meter."""

    x: float
    y: float


@dataclass(frozen=True)
class Strecke:
    """Die vermessene Strecke zwischen zwei Tags.

    `laenge_m` ist der Median der Einzelmessungen, `streuung_m` der groesste
    Abstand einer Einzelmessung davon. Beides gehoert in den Bericht: ein Median
    allein liesse eine wackelige Messung aussehen wie eine ruhige.
    """

    start: Punkt
    ziel: Punkt
    laenge_m: float
    streuung_m: float
    tag_start: int
    tag_ziel: int
    proben: int


def punkt_aus(peilung_grad, abstand_m):
    """Peilung (Grad, LINKS positiv) und Abstand (Meter) in eine Lage.

    Dieselbe Konvention wie `backends/base.py::richtung`, nur rueckwaerts — ein
    Tag, das `spot.tags()` bei +90 Grad meldet, liegt links von Spot.
    """
    bogen = math.radians(float(peilung_grad))
    return Punkt(abstand_m * math.cos(bogen), abstand_m * math.sin(bogen))


def _haeufigste_zwei(proben):
    """Die zwei Tags, die in den meisten Abtastungen vorkamen.

    Bei Gleichstand die kleinere Nummer — die Wahl muss reproduzierbar sein,
    sonst zeigt derselbe Aufbau morgen in die andere Richtung.
    """
    zaehler = {}
    for probe in proben:
        for nummer in {int(e[0]) for e in probe}:
            zaehler[nummer] = zaehler.get(nummer, 0) + 1
    geordnet = sorted(zaehler.items(), key=lambda paar: (-paar[1], paar[0]))
    return [nummer for nummer, _anzahl in geordnet[:2]]


def miss_strecke(proben, tag_start=None, tag_ziel=None, mindestproben=MINDESTPROBEN):
    """Die Strecke aus mehreren Abtastungen zweier Tags.

    `proben` ist eine Liste von Abtastungen; jede Abtastung ist eine Liste von
    `(Tag-Nummer, Peilung in Grad, Abstand in Metern)`. Ohne `tag_start`/
    `tag_ziel` werden die zwei Tags genommen, die am haeufigsten zu sehen waren.

    Gerechnet wird ueber den MEDIAN, nicht den Mittelwert: ein einzelner
    Fehltreffer der Tag-Erkennung ist der Normalfall, nicht die Ausnahme, und ein
    Mittelwert zoege die ganze Strecke mit. Die Streuung meldet ihn trotzdem.
    """
    if tag_start is None or tag_ziel is None:
        gewaehlt = _haeufigste_zwei(proben)
        if len(gewaehlt) < 2:
            raise SpotlabError(
                "Für die Strecke braucht es zwei AprilTags — Spot sieht gerade "
                "weniger. Beide Tags so aufhängen, dass er von seinem Standort "
                "aus beide zugleich sieht."
            )
        tag_start = gewaehlt[0] if tag_start is None else tag_start
        tag_ziel = next(t for t in gewaehlt if t != tag_start) if tag_ziel is None else tag_ziel

    tag_start, tag_ziel = int(tag_start), int(tag_ziel)
    ecken = {tag_start: [], tag_ziel: []}
    laengen = []
    for probe in proben:
        gesehen = {int(e[0]): punkt_aus(e[1], e[2]) for e in probe}
        a, b = gesehen.get(tag_start), gesehen.get(tag_ziel)
        if a is None or b is None:
            continue
        ecken[tag_start].append(a)
        ecken[tag_ziel].append(b)
        laengen.append(math.dist((a.x, a.y), (b.x, b.y)))

    if len(laengen) < mindestproben:
        fehlend = [t for t in (tag_start, tag_ziel) if not ecken[t]]
        wo = f" Nicht gesehen: {', '.join(str(t) for t in fehlend)}." if fehlend else ""
        raise SpotlabError(
            f"Zu wenige Abtastungen mit beiden Tags ({len(laengen)} von "
            f"{mindestproben}).{wo} Spot so hinstellen, dass er beide Tags "
            "gleichzeitig sieht, und erneut messen."
        )

    laenge = statistics.median(laengen)
    return Strecke(
        start=Punkt(statistics.median([p.x for p in ecken[tag_start]]),
                    statistics.median([p.y for p in ecken[tag_start]])),
        ziel=Punkt(statistics.median([p.x for p in ecken[tag_ziel]]),
                   statistics.median([p.y for p in ecken[tag_ziel]])),
        laenge_m=laenge,
        streuung_m=max(abs(x - laenge) for x in laengen),
        tag_start=tag_start,
        tag_ziel=tag_ziel,
        proben=len(laengen),
    )


def _achse(strecke):
    dx = strecke.ziel.x - strecke.start.x
    dy = strecke.ziel.y - strecke.start.y
    laenge = math.hypot(dx, dy)
    if laenge == 0.0:
        raise SpotlabError("Die beiden Tags liegen aufeinander — das ist keine Strecke.")
    return dx / laenge, dy / laenge, laenge


def fortschritt(strecke, punkt):
    """Meter entlang der Strecke, ab dem Start-Tag.

    Bewusst NICHT auf 0..Laenge geklemmt: negative Werte heissen 'noch vor der
    Startlinie', Werte ueber der Laenge 'schon hinter dem Ziel'. Genau diese
    beiden Zustaende braucht die Zeitnahme, um den Uebertritt zu interpolieren —
    geklemmt begaenne die Zeit erst beim ersten Bild NACH der Linie, und bei
    5 Hz waeren das bis zu 0.2 s Fehler auf jede Messung.
    """
    ex, ey, _laenge = _achse(strecke)
    return (punkt.x - strecke.start.x) * ex + (punkt.y - strecke.start.y) * ey


def querabstand(strecke, punkt):
    """Abstand seitlich der Strecke, in Metern — immer positiv.

    Der Korridorfilter der Zeitnahme haengt daran: wer zwei Meter neben der
    Linie steht, laeuft sie nicht, auch wenn seine Projektion mitten darauf
    faellt.
    """
    ex, ey, _laenge = _achse(strecke)
    return abs((punkt.x - strecke.start.x) * ey - (punkt.y - strecke.start.y) * ex)
