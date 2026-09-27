"""Die Menschensuche der Steuerzentrale: wer steht wo — als Punkte in der Draufsicht.

Dieselbe Kette wie beim Folgen (`folgen.koerper_finder`): Bild → `Koerpererkenner`
(YOLOX sucht, MediaPipe gibt das Skelett, die Spur hält es) → `koerper.beurteile` (die
Tiefenkamera misst den Abstand, die Höhenprobe verwirft Kisten und Stuhllehnen). Jeder
genommene Körper wird mit Spots Lage im Rahmen „vision“ — dem der Skizze — in die
Draufsicht gerechnet (`merkpunkt.in_raum`).

Die Stufe entscheidet, wie viel Rechenzeit die Suche bekommt (`record/zentrale.SUCHSTUFEN`):

    aus       nichts
    sparsam   vorne, eine Runde alle SPARSAM_PAUSE_S
    normal    vorne, so oft es geht
    rundum    vorne plus links, rechts, hinten — je Seite eine `panorama.Einzelsicht`

Je Quelle ein eigener Erkenner: die Spur gehört zu EINER Bildfolge, und abwechselnd
vorne und hinten zu suchen, risse sie jedes Mal ab. Das YOLOX-Modell teilen sie sich.
Eine Quelle, die scheitert, hält die anderen nicht auf; ihr Grund steht in der Runde.

Ohne Roboter prüfbar: `erkenner_bauen`, `vorne_holen`, `seite_holen` und `lage_holen` sind
die Testtüren.
"""

from dataclasses import dataclass

from spotlab.workshop import merkpunkt

SPARSAM_PAUSE_S = 2.0
# Die Seiten und das Heck: (Name im Lagebild, Bildquelle, Tiefenquelle).
SEITEN = (
    ("links", "left_fisheye_image", "left_depth"),
    ("rechts", "right_fisheye_image", "right_depth"),
    ("hinten", "back_fisheye_image", "back_depth"),
)


@dataclass(frozen=True)
class Mensch:
    x: float                     # Meter im Rahmen „vision“ (der der Skizze)
    y: float
    abstand: float               # Meter vom Körper, gemessen
    peilung: float               # Grad im Körperrahmen, links positiv
    quelle: str                  # "vorne", "links", "rechts", "hinten"
    t: float                     # wann gesehen (Uhr der Zentrale)


def pause_s(stufe):
    """Wie lange nach einer Runde gewartet wird."""
    pausen = {"sparsam": SPARSAM_PAUSE_S, "normal": 0.0, "rundum": 0.0}
    if stufe not in pausen:
        raise ValueError(f"Suchstufe {stufe!r} -- erwartet sparsam, normal oder rundum.")
    return pausen[stufe]


class Menschensuche:
    def __init__(self, spot, erkenner_bauen=None, vorne_holen=None, seite_holen=None,
                 lage_holen=None):
        self.spot = spot
        self._erkenner_bauen = erkenner_bauen or self._erkenner_vorgabe
        self._vorne_holen = vorne_holen or _vorne_vorgabe
        self._seite_holen = seite_holen or _seiten_vorgabe
        self._lage_holen = lage_holen or _lage_vorgabe
        self._erkenner = {}
        self._gemerkt = {}
        self._yolox = None

    def _erkenner_vorgabe(self, quelle):
        from spotlab.backends.real import koerper

        if self._yolox is None:
            try:
                self._yolox = koerper.YoloxPersonen(koerper.personenmodell(None))
            except Exception:
                self._yolox = False            # ohne YOLOX sucht der Erkenner wie früher
        return koerper.Koerpererkenner(personen=self._yolox or None)

    def _erkenner_fuer(self, quelle):
        if quelle not in self._erkenner:
            self._erkenner[quelle] = self._erkenner_bauen(quelle)
        return self._erkenner[quelle]

    def runde(self, stufe, t):
        """(Menschen, Gründe je gescheiterter Quelle) für eine Runde dieser Stufe."""
        if stufe == "aus":
            return [], {}
        menschen, gruende = [], {}
        try:
            aufnahme = self._vorne_holen(self.spot, self._gemerkt)
        except Exception as fehler:
            aufnahme, gruende["vorne"] = None, f"{type(fehler).__name__}: {fehler}"
        if aufnahme is None:
            gruende.setdefault("vorne", "keine Bilder (Kamera oder Tiefe fehlt)")
        try:
            lage = self._lage_holen(self.spot)
        except Exception:
            lage = None
        quellen = []
        if aufnahme is not None:
            quellen.append(("vorne", aufnahme.feld, aufnahme.pano, aufnahme.punkte,
                            aufnahme.blick_grad))
        if stufe == "rundum":
            try:
                seiten = self._seite_holen(self.spot, self._gemerkt)
            except Exception as fehler:
                seiten = {name: fehler for name, _, _ in SEITEN}
            for name, geholt in seiten.items():
                if isinstance(geholt, Exception):
                    gruende[name] = f"{type(geholt).__name__}: {geholt}"
                else:
                    feld, sicht, punkte = geholt
                    # Seitlich zählt die Neigung anders; die Zentrale neigt nicht (0).
                    quellen.append((name, feld, sicht, punkte, 0.0))
        for name, feld, sicht, punkte, blick_grad in quellen:
            if lage is None:
                gruende[name] = "Spots Lage ist nicht lesbar — kein Ort für den Menschen"
                continue
            try:
                menschen += self._urteil(name, feld, sicht, punkte, blick_grad, lage, t)
            except Exception as fehler:
                gruende[name] = f"{type(fehler).__name__}: {fehler}"
        return menschen, gruende

    def _urteil(self, quelle, feld, sicht, punkte, blick_grad, lage, t):
        from spotlab.backends.real import koerper as koerpermodul

        koerper = self._erkenner_fuer(quelle).finde(feld)
        befunde = koerpermodul.beurteile(koerper, sicht, punkte, sicht.kamerahoehe(blick_grad),
                                         blick_grad=blick_grad)
        menschen = []
        for b in befunde:
            if not b.genommen:
                continue
            x, y = merkpunkt.in_raum((lage[0], lage[1]), lage[2], b.bearing, b.distance)
            menschen.append(Mensch(x, y, float(b.distance), float(b.bearing), quelle, t))
        return menschen


def _vorne_vorgabe(spot, gemerkt):
    from spotlab.workshop import folgen

    return folgen.bildaufnahme(spot, gemerkt.setdefault("vorne", {}))


def _lage_vorgabe(spot):
    from spotlab.workshop import folgen

    return folgen._lage_im_gitter(spot)


def _seiten_vorgabe(spot, gemerkt):
    """{Name: (Zylinderbild, Einzelsicht, Tiefenpunkte) oder Fehler} für links, rechts, hinten.

    EIN Abruf für die drei Bilder (in Farbe, Grau als Rückfall) und einer für die drei
    Tiefenbilder — getrennt, denn ein Farbwunsch für ein Tiefenbild wird abgewiesen
    (`folgen.bildaufnahme`). Die Einzelsichten werden einmal gebaut und gemerkt.
    """
    from spotlab.backends.real import panorama, tiefe
    from spotlab.workshop import folgen

    bilder, tiefen = folgen._bilder_holen(spot, [b for _, b, _ in SEITEN], [d for _, _, d in SEITEN])
    nach_name = {a.source.name: a for a in list(bilder) + list(tiefen)}
    ergebnis = {}
    for name, bildquelle, tiefenquelle in SEITEN:
        try:
            bild, tief = nach_name.get(bildquelle), nach_name.get(tiefenquelle)
            if bild is None or tief is None:
                raise RuntimeError(f"{bildquelle} oder {tiefenquelle} fehlt in der Antwort")
            schluessel = "sicht_" + name
            if schluessel not in gemerkt:
                gemerkt[schluessel] = panorama.Einzelsicht(panorama.kalibrierung_aus([bild])[0])
            sicht = gemerkt[schluessel]
            feld = sicht.zusammensetzen(panorama.bilder_aus([bild]))
            ergebnis[name] = (feld, sicht, tiefe.punkte_aus_bild(tief))
        except Exception as fehler:
            ergebnis[name] = fehler
    return ergebnis
