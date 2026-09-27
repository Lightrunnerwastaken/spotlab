"""Folgen per Klick: Spot folgt DEM Menschen, der in der Draufsicht angeklickt wurde.

Die Steuerzentrale übergibt an den bestehenden Folgemodus (`folgen.folge`) — kein zweites
Folgen. `folge()` wählt unter mehreren Menschen über den Merkpunkt, und der kennt am
Anfang noch keinen: er nähme den nächsten. `KlickFinder` wickelt deshalb den Körperfinder
ein und schiebt sich für die ersten `START_TREFFER` Treffer vor diese Wahl (dieselbe
ContextVar `folgen._WAHL`, die `folge()` je Takt setzt): nur der Kandidat, der am nächsten
an der angeklickten Stelle steht, und nur bis `START_M` daneben, verglichen im
Körperrahmen des Roboters. Nach jedem Treffer wandert die Stelle mit dem Menschen mit
(er geht ja weiter). Danach hat der Merkpunkt ihn bestätigt und hält ihn — der Finder
reicht nur noch durch.

Ohne lesbare Lage wird am Anfang KEINER genommen: den Angeklickten ohne Lage zu
„erkennen“ hiesse raten, und geraten wäre der nächste.

`gesehen(punkte, gewaehlt)` bekommt je Takt alle Kandidaten als (x, y, Abstand, Peilung)
im Rahmen „vision“ und den gewählten als (x, y) oder None — daraus zeichnet die
Zentrale, was der Folgemodus sieht, den Gefolgten hervorgehoben.
"""

import math

from spotlab.workshop import folgen, merkpunkt

START_TREFFER = merkpunkt.MIN_TREFFER   # so viele Treffer, bis der Merkpunkt ihn bestätigt
START_M = 1.0          # so weit darf der Mensch am Anfang neben der Stelle stehen


class KlickFinder:
    def __init__(self, finder, ziel, lage_holen=None, gesehen=None):
        self._finder = finder
        self.stelle = (float(ziel[0]), float(ziel[1]))
        self._lage_holen = lage_holen or folgen._lage_im_gitter
        self._gesehen = gesehen
        self.treffer = 0
        self._text = ""
        self.hinweis = getattr(finder, "hinweis", None)

    def befund(self):
        innen = getattr(self._finder, "befund", None)
        try:
            text = innen() if callable(innen) else ""
        except Exception:
            text = ""
        return ", ".join(t for t in (text, self._text) if t)

    def letzte(self):
        innen = getattr(self._finder, "letzte", None)
        return innen() if callable(innen) else None

    def __call__(self, spot):
        try:
            lage = self._lage_holen(spot)
        except Exception:
            lage = None
        aussen = folgen._WAHL.get()
        gesehen = []
        self._text = ""

        def wahl(kandidaten):
            kandidaten = list(kandidaten)
            gesehen[:] = kandidaten
            if self.treffer < START_TREFFER:
                kandidaten = self._beim_klick(kandidaten, lage)
            if aussen is not None:
                return aussen(kandidaten)
            return min(kandidaten, key=lambda k: k.distance) if kandidaten else None

        marke = folgen._WAHL.set(wahl)
        try:
            ziel = self._finder(spot)
        finally:
            folgen._WAHL.reset(marke)
        gewaehlt = None if ziel is None or lage is None else _welt(lage, ziel)
        if ziel is not None and self.treffer < START_TREFFER:
            self.treffer += 1
            if gewaehlt is not None:
                self.stelle = gewaehlt
        if self._gesehen is not None and lage is not None:
            punkte = [(*_welt(lage, k), float(k.distance), float(k.bearing)) for k in gesehen]
            self._gesehen(punkte, gewaehlt)
        return ziel

    def _beim_klick(self, kandidaten, lage):
        """[der Kandidat an der angeklickten Stelle] — oder [], und der Befund sagt warum."""
        if not kandidaten:
            return []
        if lage is None:
            self._text = "Spots Lage ist nicht lesbar — der Angeklickte ist nicht zu erkennen"
            return []
        x, y, gier = lage
        dx, dy = self.stelle[0] - x, self.stelle[1] - y
        vorn = dx * math.cos(gier) + dy * math.sin(gier)
        links = -dx * math.sin(gier) + dy * math.cos(gier)

        def daneben(k):
            w = math.radians(k.bearing)
            return math.hypot(k.distance * math.cos(w) - vorn, k.distance * math.sin(w) - links)

        bester = min(kandidaten, key=daneben)
        weite = daneben(bester)
        if weite <= START_M:
            return [bester]
        self._text = (f"keiner beim angeklickten Menschen (der nächste {weite:.1f} m daneben)")
        return []


def _welt(lage, ziel):
    return merkpunkt.in_raum((lage[0], lage[1]), lage[2], ziel.bearing, ziel.distance)
