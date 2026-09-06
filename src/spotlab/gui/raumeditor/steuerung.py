"""Die Steuerung des Raumeditors -- ohne Qt.

Maus kommt in METERN (die Sicht rechnet Pixel um), Tasten als Namen
("g", "x", "return", "escape", "delete", ...). Was hier steht, ist alles, was der
Editor kann; `sicht2d.py` und `tab.py` sind nur die Haut darum. Deshalb laeuft
jeder Bedienfall als Test ohne Fenster.
"""

import math

from spotlab.welt import bearbeitung as b

WERKZEUGE = ("auswahl", "wand", "block", "tag", "start")
TOLERANZ_M = 0.12        # Treffer um den Zeiger; die Sicht rechnet 8 px um


class Steuerung:
    def __init__(self, raum=None):
        self.modus = b.Modus()
        self.setze_raum(raum)

    def setze_raum(self, raum, geaendert=False):
        self.raum = raum
        self.auswahl = frozenset()
        self.verlauf = b.Verlauf()
        if raum is not None:
            self.verlauf.merke(raum)
        self.modus = b.Modus()
        self.werkzeug = "auswahl"
        self.geaendert = geaendert
        self.kette = None          # Anfang der naechsten Wand (Wandwerkzeug)
        self.rahmen = None         # (x1, y1, x2, y2) waehrend Rahmenauswahl oder Blockziehen
        self.zeiger = (0.0, 0.0)
        self._zug = None

    # ------------------------------------------------------------ innen

    def _uebernimm(self, raum):
        """Eine bestaetigte Aenderung: in den Verlauf, als geaendert merken."""
        self.raum = raum
        self.verlauf.merke(raum)
        self.geaendert = True

    @staticmethod
    def _rast(wert, frei):
        return wert if frei else b.raste(wert)

    @staticmethod
    def _winkel(cx, cy, x, y, frei):
        grad = math.degrees(math.atan2(y - cy, x - cx)) % 360.0
        return grad if frei else b.raste(grad, b.RASTER_GRAD) % 360.0

    # --------------------------------------------------------- Werkzeug

    def setze_werkzeug(self, name):
        if name not in WERKZEUGE:
            raise ValueError(f"Unbekanntes Werkzeug: {name!r}")
        if self.modus.aktiv:
            self.raum = self.modus.abbruch()
        self.werkzeug = name
        self.kette = None
        self._zug = None

    # -------------------------------------------------------------- Maus

    def druecke(self, x, y, taste="links", shift=False, ctrl=False, toleranz=TOLERANZ_M,
                treffer=None):
        """`treffer`: ein Schluessel, den die Sicht schon kennt (3D: Farb-ID-Puffer) --
        er geht dem Treffertest am Bodenpunkt vor, die Griffe bleiben zuerst."""
        self.zeiger = (x, y)
        if self.raum is None:
            return
        if self.modus.aktiv:
            if taste == "links":
                self._uebernimm(self.modus.bestaetige())
            else:
                self.raum = self.modus.abbruch()
            return
        if taste == "rechts":
            self.kette = None
            return
        if taste != "links":
            return
        if self.werkzeug == "auswahl":
            self._druecke_auswahl(x, y, shift, toleranz, treffer)
        elif self.werkzeug == "wand":
            self._druecke_wand(x, y, ctrl)
        elif self.werkzeug == "block":
            von = (self._rast(x, ctrl), self._rast(y, ctrl))
            self._zug = {"art": "block", "von": von}
            self.rahmen = (von[0], von[1], von[0], von[1])
        elif self.werkzeug == "tag":
            raum, s = b.neuer_tag(self.raum, self._rast(x, ctrl), self._rast(y, ctrl))
            self._uebernimm(raum)
            self.auswahl = frozenset({s})
        elif self.werkzeug == "start":
            sx, sy = self._rast(x, ctrl), self._rast(y, ctrl)
            self._zug = {"art": "start_richtung", "raum": self.raum, "von": (sx, sy)}
            self.raum = b.setze_start(self.raum, sx, sy, self.raum.start[2])
            self.auswahl = frozenset({b.START})

    def _druecke_auswahl(self, x, y, shift, toleranz, treffer=None):
        for s, art, gx, gy in b.griffe(self.raum, self.auswahl):
            if math.hypot(gx - x, gy - y) <= toleranz:
                self._zug = {"art": art, "schluessel": s, "raum": self.raum, "von": (x, y)}
                return
        s = treffer if treffer is not None else b.treffer(self.raum, x, y, toleranz)
        if s is None:
            if not shift:
                self.auswahl = frozenset()
            self._zug = {"art": "rahmen", "von": (x, y)}
            self.rahmen = (x, y, x, y)
            return
        if shift:
            self.auswahl = self.auswahl ^ frozenset({s})
        elif s not in self.auswahl:
            self.auswahl = frozenset({s})
        self._zug = {"art": "verschieben", "von": (x, y), "raum": self.raum,
                     "auswahl": self.auswahl}

    def _druecke_wand(self, x, y, ctrl):
        px, py = b.fange_ende(self.raum, self._rast(x, ctrl), self._rast(y, ctrl))
        if self.kette is None:
            self.kette = (px, py)
            return
        if math.hypot(px - self.kette[0], py - self.kette[1]) < b.MINDESTKANTE_M:
            return
        raum, s = b.neue_wand(self.raum, self.kette[0], self.kette[1], px, py)
        self._uebernimm(raum)
        self.auswahl = frozenset({s})
        self.kette = (px, py)

    def bewege(self, x, y, ctrl=False):
        self.zeiger = (x, y)
        if self.modus.aktiv:
            self.modus.zeiger(x, y, frei=ctrl)
            self.raum = self.modus.vorschau()
            return
        z = self._zug
        if z is None:
            return
        art = z["art"]
        if art == "rahmen":
            self.rahmen = (z["von"][0], z["von"][1], x, y)
        elif art == "block":
            self.rahmen = (z["von"][0], z["von"][1], self._rast(x, ctrl), self._rast(y, ctrl))
        elif art == "verschieben":
            dx, dy = x - z["von"][0], y - z["von"][1]
            self.raum = b.verschiebe(z["raum"], z["auswahl"],
                                     self._rast(dx, ctrl), self._rast(dy, ctrl))
        elif art in ("ende_a", "ende_b"):
            s = z["schluessel"]
            px, py = b.fange_ende(z["raum"], self._rast(x, ctrl), self._rast(y, ctrl), ausser=s)
            fx, fy = ("x1", "y1") if art == "ende_a" else ("x2", "y2")
            self.raum = b.setze_feld(b.setze_feld(z["raum"], s, fx, px), s, fy, py)
        elif art.startswith("ecke"):
            self.raum = b.ziehe_ecke(z["raum"], z["schluessel"], int(art[4:]),
                                     self._rast(x, ctrl), self._rast(y, ctrl))
        elif art == "drehring":
            block = b.element(z["raum"], z["schluessel"])
            grad = self._winkel(block.x, block.y, x, y, ctrl)
            self.raum = b.setze_feld(z["raum"], z["schluessel"], "drehung", grad)
        elif art == "richtung":
            cx, cy = b.lage(z["raum"], z["schluessel"])
            self.raum = b.setze_feld(z["raum"], z["schluessel"], "grad",
                                     self._winkel(cx, cy, x, y, ctrl))
        elif art == "start_richtung":
            sx, sy = z["von"]
            if math.hypot(x - sx, y - sy) >= 0.05:
                self.raum = b.setze_start(z["raum"], sx, sy, self._winkel(sx, sy, x, y, ctrl))

    def lasse_los(self, x, y, shift=False, ctrl=False):
        z, self._zug = self._zug, None
        if z is None or self.raum is None:
            return
        art = z["art"]
        if art == "rahmen":
            x1, y1, x2, y2 = self.rahmen
            self.rahmen = None
            if abs(x2 - x1) > 0.02 or abs(y2 - y1) > 0.02:
                neue = b.im_rahmen(self.raum, x1, y1, x2, y2)
                self.auswahl = (self.auswahl | neue) if shift else neue
            return
        if art == "block":
            x1, y1, x2, y2 = self.rahmen
            self.rahmen = None
            breite, tiefe = abs(x2 - x1), abs(y2 - y1)
            if breite < b.MINDESTKANTE_M or tiefe < b.MINDESTKANTE_M:
                return
            raum, s = b.neuer_block(self.raum, (x1 + x2) / 2, (y1 + y2) / 2, breite, tiefe)
            self._uebernimm(raum)
            self.auswahl = frozenset({s})
            return
        if self.raum is not z["raum"]:
            self._uebernimm(self.raum)       # etwas hat sich bewegt

    # ------------------------------------------------------------ Tasten

    def taste(self, name, shift=False, ctrl=False, alt=False):
        """True, wenn die Taste verarbeitet wurde."""
        if self.raum is None:
            return False
        name = name.lower()
        if self.modus.aktiv:
            if name in ("return", "enter"):
                self._uebernimm(self.modus.bestaetige())
                return True
            if name == "escape":
                self.raum = self.modus.abbruch()
                return True
            return self.modus.taste(name)
        if ctrl and name == "z":
            return self.rueckgaengig()
        if ctrl and name == "y":
            return self.wiederholen()
        if name == "escape":
            self.kette = None
            self.auswahl = frozenset()
            return True
        if name == "a":
            self.auswahl = frozenset() if alt else self.alle()
            return True
        if not self.auswahl:
            return False
        if name in ("g", "r", "s"):
            art = {"g": b.Modus.BEWEGEN, "r": b.Modus.DREHEN, "s": b.Modus.SKALIEREN}[name]
            self.modus.beginne(art, self.raum, self.auswahl, self.zeiger)
            return True
        if name == "d" and shift:
            raum, neue = b.dupliziere(self.raum, self.auswahl)
            self._uebernimm(raum)
            self.auswahl = neue
            self.modus.beginne(b.Modus.BEWEGEN, self.raum, self.auswahl, self.zeiger)
            return True
        if name == "delete":
            raum, self.auswahl = b.loesche(self.raum, self.auswahl)
            self._uebernimm(raum)
            return True
        return False

    def rueckgaengig(self):
        raum = self.verlauf.zurueck()
        if raum is None:
            return False
        self.raum, self.auswahl, self.geaendert = raum, frozenset(), True
        return True

    def wiederholen(self):
        raum = self.verlauf.vor()
        if raum is None:
            return False
        self.raum, self.auswahl, self.geaendert = raum, frozenset(), True
        return True

    # ---------------------------------------------------------- Auskunft

    def alle(self):
        r = self.raum
        return frozenset(
            [("wand", i) for i in range(len(r.waende))]
            + [("block", i) for i in range(len(r.bloecke))]
            + [("tag", i) for i in range(len(r.tags))]
            + [b.START]
        )

    def setze_feld(self, schluessel, feld, wert):
        self._uebernimm(b.setze_feld(self.raum, schluessel, feld, wert))

    def griffe(self):
        if self.raum is None or self.modus.aktiv:
            return []
        return b.griffe(self.raum, self.auswahl)

    def hinweise(self):
        return b.pruefe(self.raum) if self.raum is not None else []
