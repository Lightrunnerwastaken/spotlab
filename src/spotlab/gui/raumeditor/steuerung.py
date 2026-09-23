"""Die Steuerung des Raumeditors -- ohne Qt.

Maus kommt in METERN (die Sicht rechnet Pixel um), Tasten als Namen
("g", "x", "return", "escape", "delete", ...). Was hier steht, ist alles, was der
Editor kann; `sicht2d.py` und `tab.py` sind nur die Haut darum. Deshalb laeuft
jeder Bedienfall als Test ohne Fenster.
"""

import math

from spotlab.welt import bearbeitung as b

WERKZEUGE = ("auswahl", "wand", "block", "boden", "sperrzone", "tag", "start")
WERKZEUG_NAMEN = {"auswahl": "Auswählen", "wand": "Wand", "block": "Block", "boden": "Boden",
                  "sperrzone": "Sperrzone", "tag": "Tag", "start": "Start"}
TOLERANZ_M = 0.12        # Treffer um den Zeiger; die Sicht rechnet 8 px um
TRENNER = "  ·  "
RASTER_TEXT = f"Raster {round(b.RASTER_M * 100)} cm (Strg: frei)"
MODUS_NAMEN = {b.Modus.BEWEGEN: "G bewegen", b.Modus.DREHEN: "R drehen",
               b.Modus.SKALIEREN: "S skalieren"}


class Steuerung:
    def __init__(self, raum=None):
        self.modus = b.Modus()
        self.setze_raum(raum)

    def setze_raum(self, raum, geaendert=False):
        self.revision = getattr(self, "revision", 0) + 1
        self.raum = raum
        self.auswahl = frozenset()
        # Die gewaehlte Ebene der 2D-Sicht (None = alle). Neue Elemente landen
        # auf ihr; was auf einer anderen liegt, zeichnet die Sicht blass.
        self.ebene = None
        self.verlauf = b.Verlauf()
        if raum is not None:
            self.verlauf.merke(raum)
        self.modus = b.Modus()
        self.werkzeug = "auswahl"
        self.geaendert = geaendert
        self.kette = None          # Anfang der naechsten Wand (Wandwerkzeug)
        self.rahmen = None         # (x1, y1, x2, y2) waehrend Rahmenauswahl oder Blockziehen
        self.zeiger = (0.0, 0.0)
        self.frei = False          # Strg bei der letzten Bewegung: ohne Raster
        self.ueber = None          # das Element unter dem Zeiger (Hervorhebung beim Ueberfahren)
        self.ueber_griff = False   # liegt der Zeiger auf einem Griff?
        self._zug = None

    # ------------------------------------------------------------ innen

    def uebernimm(self, raum):
        """Eine bestaetigte Aenderung: in den Verlauf, als geaendert merken."""
        self.raum = raum
        self.revision += 1
        self.verlauf.merke(raum)
        self.geaendert = True

    def ersetze_raum(self, raum):
        """Ein ganzer neuer Raum von aussen (der Korrigierer) -- als EIN Schritt.

        Die Auswahl wird geleert wie bei `loesche`: ihre Indizes gelten fuer den
        alten Raum. Nach einer Korrektur, die eine Wand loeschte, warf sonst jede
        Mausbewegung IndexError, und Entf traf eine ANDERE Wand (23.09.2026).
        Eine offene Geste endet vorher -- ihr Abbruch holte sonst den alten Raum
        zurueck.
        """
        self._beende_geste()
        self.auswahl = frozenset()
        self.uebernimm(raum)

    def breche_ab(self):
        """Eine offene Geste (G/R/S oder Ziehen mit der Maus) verwerfen.

        Vor dem Speichern: auf die Platte kommt nur, was bestaetigt ist. Sonst
        stand die Vorschau in der Datei, der Editor zeigte nach Esc etwas anderes,
        und `geaendert` war falsch. Die Wandkette bleibt -- sie steht noch nicht
        im Raum. True, wenn es etwas abzubrechen gab.
        """
        if self.modus.aktiv:
            self.raum = self.modus.abbruch()
            return True
        if self._zug is not None:
            if "raum" in self._zug:
                self.raum = self._zug["raum"]
            self._zug = None
            self.rahmen = None
            return True
        return False

    @property
    def zieht(self):
        """Wahr, solange die Maustaste gedrueckt ist und etwas gezogen wird."""
        return self._zug is not None

    @property
    def vorschau_basis(self):
        """Der bestaetigte Raum unter einer laufenden Vorschau (G/R/S oder Ziehen) --
        sonst None. Die Sicht darf teure Ableitungen davon mitschieben."""
        if self.modus.aktiv:
            return self.modus.basis
        if self._zug is not None:
            return self._zug.get("raum")
        return None

    @staticmethod
    def _rast(wert, frei):
        return wert if frei else b.raste(wert)

    @staticmethod
    def _winkel(cx, cy, x, y, frei):
        grad = math.degrees(math.atan2(y - cy, x - cx)) % 360.0
        return grad if frei else b.raste(grad, b.RASTER_GRAD) % 360.0

    # --------------------------------------------------------- Werkzeug

    def setze_ebene(self, wert):
        """Die Ebene der 2D-Sicht: eine Bodenhoehe aus `hoehe.ebenen` oder None (alle)."""
        neue_ebene = None if wert is None else float(wert)
        if neue_ebene == self.ebene:
            return
        self.ebene = neue_ebene
        self._beende_geste()
        self.auswahl &= self.auswaehlbare()

    def auswaehlbare(self):
        """Derselbe Ebenenbegriff wie beim Zeichnen, auch fuer Fang und Rahmen."""
        from spotlab.welt.hoehe import auf_ebene, boden_bei

        if self.raum is None:
            return frozenset()
        if self.ebene is None:
            return self.alle()
        def passt(s):
            if s == b.START:
                z, _ = boden_bei(self.raum, *self.raum.start[:2])
                return abs(z - self.ebene) <= 0.3
            if s[0] in ("sperrzone", "gelaende"):
                return True
            return auf_ebene(b.element(self.raum, s), self.raum, self.ebene)
        return frozenset(s for s in self.alle() if passt(s))

    def _beende_geste(self):
        if self.modus.aktiv:
            self.raum = self.modus.abbruch()
        elif self._zug is not None and "raum" in self._zug:
            self.raum = self._zug["raum"]
        self._zug = None
        self.kette = None
        self.rahmen = None

    @property
    def _z_neu(self):
        """Die Hoehe, auf der neue Elemente entstehen."""
        return self.ebene or 0.0

    def setze_werkzeug(self, name):
        if name not in WERKZEUGE:
            raise ValueError(f"Unbekanntes Werkzeug: {name!r}")
        if self.modus.aktiv:
            self.raum = self.modus.abbruch()
        self.werkzeug = name
        self.kette = None
        self._zug = None
        self.ueber, self.ueber_griff = None, False

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
                self.uebernimm(self.modus.bestaetige())
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
        elif self.werkzeug in ("block", "boden", "sperrzone"):
            von = (self._rast(x, ctrl), self._rast(y, ctrl))
            self._zug = {"art": self.werkzeug, "von": von}
            self.rahmen = (von[0], von[1], von[0], von[1])
        elif self.werkzeug == "tag":
            raum, s = b.neuer_tag(self.raum, self._rast(x, ctrl), self._rast(y, ctrl),
                                  z=self._z_neu)
            self.uebernimm(raum)
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
        erlaubt = self.auswaehlbare()
        s = treffer if treffer is not None else b.treffer(self.raum, x, y, toleranz, erlaubt)
        if s not in erlaubt:
            s = None
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
        px, py = b.fange_ende(self.raum, self._rast(x, ctrl), self._rast(y, ctrl),
                            erlaubt=self.auswaehlbare())
        if self.kette is None:
            self.kette = (px, py)
            return
        if math.hypot(px - self.kette[0], py - self.kette[1]) < b.MINDESTKANTE_M:
            return
        raum, s = b.neue_wand(self.raum, self.kette[0], self.kette[1], px, py, z=self._z_neu)
        self.uebernimm(raum)
        self.auswahl = frozenset({s})
        self.kette = (px, py)

    def bewege(self, x, y, ctrl=False, toleranz=TOLERANZ_M):
        self.zeiger = (x, y)
        self.frei = ctrl
        self.ueber, self.ueber_griff = None, False
        if self.modus.aktiv:
            self.modus.zeiger(x, y, frei=ctrl)
            self.raum = self.modus.vorschau()
            return
        z = self._zug
        if z is None:
            self._ueberfahre(x, y, toleranz)
            return
        art = z["art"]
        if art == "rahmen":
            self.rahmen = (z["von"][0], z["von"][1], x, y)
        elif art in ("block", "boden", "sperrzone"):
            self.rahmen = (z["von"][0], z["von"][1], self._rast(x, ctrl), self._rast(y, ctrl))
        elif art == "verschieben":
            dx, dy = x - z["von"][0], y - z["von"][1]
            self.raum = b.verschiebe(z["raum"], z["auswahl"],
                                     self._rast(dx, ctrl), self._rast(dy, ctrl))
        elif art in ("ende_a", "ende_b"):
            s = z["schluessel"]
            px, py = b.fange_ende(z["raum"], self._rast(x, ctrl), self._rast(y, ctrl), ausser=s,
                                erlaubt=self.auswaehlbare())
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

    def _ueberfahre(self, x, y, toleranz):
        """Was unter dem Zeiger liegt, wenn nichts gezogen wird: ein Griff (Zeiger
        „verschieben") oder ein Element (hervorgehoben). Nur im Auswahlwerkzeug --
        beim Zeichnen gibt es nichts anzufassen."""
        if self.raum is None or self.werkzeug != "auswahl":
            return
        for _s, _art, gx, gy in b.griffe(self.raum, self.auswahl):
            if math.hypot(gx - x, gy - y) <= toleranz:
                self.ueber_griff = True
                return
        self.ueber = b.treffer(self.raum, x, y, toleranz, self.auswaehlbare())

    def lasse_los(self, x, y, shift=False, ctrl=False):
        z, self._zug = self._zug, None
        if z is None or self.raum is None:
            return
        art = z["art"]
        if art == "rahmen":
            x1, y1, x2, y2 = self.rahmen
            self.rahmen = None
            if abs(x2 - x1) > 0.02 or abs(y2 - y1) > 0.02:
                neue = b.im_rahmen(self.raum, x1, y1, x2, y2, self.auswaehlbare())
                self.auswahl = (self.auswahl | neue) if shift else neue
            return
        if art in ("block", "boden", "sperrzone"):
            x1, y1, x2, y2 = self.rahmen
            self.rahmen = None
            breite, tiefe = abs(x2 - x1), abs(y2 - y1)
            if breite < b.MINDESTKANTE_M or tiefe < b.MINDESTKANTE_M:
                return
            if art == "sperrzone":
                # Ohne z: eine Zone ist eine Flaeche, keine Kiste.
                raum, s = b.neue_sperrzone(self.raum, (x1 + x2) / 2, (y1 + y2) / 2, breite, tiefe)
            else:
                bauen = b.neuer_block if art == "block" else b.neuer_boden
                raum, s = bauen(self.raum, (x1 + x2) / 2, (y1 + y2) / 2, breite, tiefe,
                                z=self._z_neu)
            self.uebernimm(raum)
            self.auswahl = frozenset({s})
            return
        if self.raum is not z["raum"]:
            self.uebernimm(self.raum)       # etwas hat sich bewegt

    # ------------------------------------------------------------ Tasten

    def taste(self, name, shift=False, ctrl=False, alt=False):
        """True, wenn die Taste verarbeitet wurde."""
        if self.raum is None:
            return False
        name = name.lower()
        if ctrl and name == "z":
            return self.rueckgaengig()
        if ctrl and name == "y":
            return self.wiederholen()
        if self.modus.aktiv:
            if name in ("return", "enter"):
                self.uebernimm(self.modus.bestaetige())
                return True
            if name == "escape":
                self.raum = self.modus.abbruch()
                return True
            if not self.modus.taste(name):
                return False
            # Achse und getippte Zahl wirken SOFORT, nicht erst bei der naechsten
            # Mausbewegung -- sonst sagte die Zustandszeile „getippt 1 m", und der
            # Block stand, wo die Maus war (23.09.2026).
            self.raum = self.modus.vorschau()
            return True
        if self._zug is not None:
            # Waehrend die Maus zieht, gehoert der Raum der Geste: Entf loeschte
            # sonst aus der Vorschau, und die naechste Bewegung rechnete aus dem
            # Schnappschuss -- der Block war wieder da (23.09.2026). Esc bricht
            # das Ziehen ab, alles andere wartet aufs Loslassen.
            return name == "escape" and self.breche_ab()
        if name == "escape":
            self.kette = None
            self.auswahl = frozenset()
            return True
        if name == "a":
            self.auswahl = frozenset() if alt else self.auswaehlbare()
            return True
        if not self.auswahl:
            return False
        if name in ("g", "r", "s"):
            art = {"g": b.Modus.BEWEGEN, "r": b.Modus.DREHEN, "s": b.Modus.SKALIEREN}[name]
            self.modus.beginne(art, self.raum, self.auswahl, self.zeiger)
            return True
        if name == "d" and shift:
            raum, neue = b.dupliziere(self.raum, self.auswahl)
            self.uebernimm(raum)
            self.auswahl = neue
            self.modus.beginne(b.Modus.BEWEGEN, self.raum, self.auswahl, self.zeiger)
            return True
        if name == "delete":
            raum, self.auswahl = b.loesche(self.raum, self.auswahl)
            self.uebernimm(raum)
            return True
        return False

    def rueckgaengig(self):
        self._beende_geste()
        raum = self.verlauf.zurueck()
        if raum is None:
            return False
        self.raum, self.auswahl, self.geaendert = raum, frozenset(), True
        self.revision += 1
        return True

    def wiederholen(self):
        self._beende_geste()
        raum = self.verlauf.vor()
        if raum is None:
            return False
        self.raum, self.auswahl, self.geaendert = raum, frozenset(), True
        self.revision += 1
        return True

    # ---------------------------------------------------------- Auskunft

    def alle(self):
        r = self.raum
        return frozenset(
            [("wand", i) for i in range(len(r.waende))]
            + [("block", i) for i in range(len(r.bloecke))]
            + [("sperrzone", i) for i in range(len(r.sperrzonen))]
            + [("boden", i) for i in range(len(r.boeden))]
            + [("tag", i) for i in range(len(r.tags))]
            + ([b.GELAENDE] if r.gelaende is not None else [])
            + [b.START]
        )

    def setze_feld(self, schluessel, feld, wert):
        raum = b.setze_feld(self.raum, schluessel, feld, wert)
        if raum != self.raum:
            self.uebernimm(raum)

    def griffe(self):
        if self.raum is None or self.modus.aktiv:
            return []
        return b.griffe(self.raum, self.auswahl)

    def hinweise(self):
        return b.pruefe(self.raum) if self.raum is not None else []

    def befunde(self):
        return b.befunde(self.raum) if self.raum is not None else []

    # ------------------------------------------------------ Zustandszeile

    def beschreibung(self):
        """Die Zustandszeile unter der Sicht: Werkzeug oder Geste, was jetzt geht,
        Zeiger in Metern, Raster. Ohne Qt -- die Sicht zeigt nur den Text.

        Bis zum 23.09.2026 stand nirgends, dass G laeuft, welche Achse gesperrt
        ist oder was getippt wurde; wer Blender nicht kannte, sah nur einen Block,
        der der Maus folgte, und wusste nicht, wie er ihn loswird.
        """
        links, rechts = self.beschreibung_teile()
        return f"{links}{TRENNER}{rechts}" if rechts else links

    def beschreibung_teile(self):
        """(links, rechts): was gerade geht -- und Zeiger mit Raster, das die Sicht
        rechtsbuendig zeigt (eine lange Zeile wurde bei 1080 px mitten abgeschnitten)."""
        if self.raum is None:
            return "Kein Raum geöffnet.", ""
        teile = []
        m = self.modus
        if m.aktiv:
            # Wie man herauskommt, steht vorn: bei 1080 px wird hinten abgeschnitten.
            teile.append(MODUS_NAMEN[m.art])
            teile.append("Enter bestätigt · Esc bricht ab")
            if m.achse and not (m.art == b.Modus.DREHEN):
                teile.append(f"nur {m.achse.upper()}")
            if m.zahl:
                einheit = {b.Modus.BEWEGEN: " m", b.Modus.DREHEN: "°"}.get(m.art, "")
                vor = "×" if m.art == b.Modus.SKALIEREN else ""
                teile.append(f"getippt {vor}{m.zahl}{einheit}")
            else:
                teile.append(m.anzeige())
        elif self._zug is not None:
            teile += self._zug_text()
        else:
            teile.append(WERKZEUG_NAMEN[self.werkzeug])
            teile.append(self._werkzeug_text())
        x, y = self.zeiger
        return TRENNER.join(teile), f"x {x:.2f} m  y {y:.2f} m{TRENNER}{RASTER_TEXT}"

    def _zug_text(self):
        art = self._zug["art"]
        if art in ("block", "boden", "sperrzone") and self.rahmen is not None:
            x1, y1, x2, y2 = self.rahmen
            return [WERKZEUG_NAMEN[art], f"{abs(x2 - x1):.2f} × {abs(y2 - y1):.2f} m",
                    "loslassen setzt ab · Esc bricht ab"]
        if art == "rahmen":
            return ["Rahmen", "loslassen wählt, was darin liegt · Umschalt ergänzt"]
        if art == "start_richtung":
            return ["Start", "ziehen gibt die Blickrichtung · loslassen setzt ab"]
        return ["Ziehen", "loslassen setzt ab · Esc bricht ab"]

    def _werkzeug_text(self):
        w = self.werkzeug
        if w == "auswahl":
            if self.auswahl:
                return (f"{len(self.auswahl)} gewählt — G bewegen · R drehen · S skalieren · "
                        f"Entf löscht")
            return "Klick wählt · Rahmen ziehen wählt mehrere · A wählt alles"
        if w == "wand":
            if self.kette is None:
                return "Klick setzt den ersten Punkt"
            x, y = self.zeiger
            if not self.frei:
                x, y = b.raste(x), b.raste(y)
            x, y = b.fange_ende(self.raum, x, y, erlaubt=self.auswaehlbare())
            dx, dy = x - self.kette[0], y - self.kette[1]
            winkel = math.degrees(math.atan2(dy, dx))
            return (f"Länge {math.hypot(dx, dy):.2f} m · Winkel {winkel:.0f}°"
                    f"{TRENNER}Klick setzt den nächsten Punkt · Esc beendet")
        if w in ("block", "boden", "sperrzone"):
            return "Rechteck aufziehen"
        if w == "tag":
            return "Klick setzt einen Tag"
        return "Klick setzt den Start · Ziehen gibt die Blickrichtung"

    def achslinie(self):
        """(achse, (x, y)) waehrend G oder S mit gesperrter x- oder y-Achse -- die
        2D-Sicht zeichnet sie durch die Mitte der Auswahl. Sonst None."""
        m = self.modus
        if m.aktiv and m.art != b.Modus.DREHEN and m.achse in ("x", "y"):
            return (m.achse, m.mitte)
        return None

    def zeigerart(self):
        """Wie der Mauszeiger aussehen soll: "bewegen" (Griff oder laufende Geste),
        "element" (etwas zum Anklicken), "zeichnen" (Zeichenwerkzeug) oder None."""
        if self.modus.aktiv:
            return "bewegen"
        if self._zug is not None:
            return "zeichnen" if self._zug["art"] in ("block", "boden", "sperrzone") else "bewegen"
        if self.werkzeug != "auswahl":
            return "zeichnen"
        if self.ueber_griff:
            return "bewegen"
        return "element" if self.ueber is not None else None

    def auswahl_huelle(self):
        """(x0, y0, x1, y1) um die Auswahl -- F rahmt sie ein. Leer: None."""
        if self.raum is None or not self.auswahl:
            return None
        punkte = []
        for s in self.auswahl:
            e = b.element(self.raum, s)
            if s[0] == "wand":
                punkte += [(e.x1, e.y1), (e.x2, e.y2)]
            elif s[0] in ("block", "boden", "sperrzone"):
                punkte += list(e.ecken())
            elif s[0] == "gelaende" and e is not None:
                u = b.umriss(e)
                if u is not None:
                    punkte += [(u[0], u[1]), (u[2], u[3])]
            else:
                x, y = b.lage(self.raum, s)
                punkte += [(x - 0.5, y - 0.5), (x + 0.5, y + 0.5)]
        if not punkte:
            return None
        xs, ys = [p[0] for p in punkte], [p[1] for p in punkte]
        rand = 0.3
        return (min(xs) - rand, min(ys) - rand, max(xs) + rand, max(ys) + rand)
