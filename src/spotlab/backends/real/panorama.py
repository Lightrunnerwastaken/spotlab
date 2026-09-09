"""Der Blick nach vorn: die beiden Frontbilder zu EINEM Bild — wie auf dem Tablet.

Spots Frontkameras sitzen schräg im Kopf und schauen über Kreuz (die rechte
nach links-vorn, die linke nach rechts-vorn, beide rund 20° nach unten). Ihre
Bilder nur aufrecht zu drehen und nebeneinanderzulegen ergibt zwei schiefe
Vierecke mit schwarzen Ecken; das Tablet von Boston Dynamics zeigt stattdessen
ein Rechteck, in dem der Boden durchläuft. Es tut das, was auch das
SDK-Beispiel `stitch_front_images` tut: beide Bilder auf eine Ebene vor dem
Roboter projizieren und diese Ebene mit einer VIRTUELLEN Kamera ansehen.

Hier ist die virtuelle Kamera eine Zylinderkamera: Spalte = Azimut, Zeile =
Tangens der Höhe. Sie steht in der Mitte zwischen den beiden Kameras, blickt
waagerecht (im Körperrahmen) in ihre mittlere Richtung, und senkrechte Kanten
bleiben senkrecht. Für jedes Zielpixel wird der Strahl in den Körper gedreht,
mit der Bildebene jeder Kamera (`EBENE_M` vor ihr) geschnitten und durch deren
Lochkamera-Intrinsik zurück ins Quellbild gerechnet. Das passiert EINMAL je
Kalibrierung; je Bild bleiben Nachschlagen und Mischen — rund 10 ms.

Wo beide Kameras dasselbe Zielpixel sehen, wird nach Randabstand gemischt
(näher am eigenen Bildrand = weniger Gewicht), und ein Helligkeitsausgleich
gleicht die getrennte Belichtung der beiden Kameras aus — sonst steht in der
Mitte eine Kante. Der Ausschnitt ist das grösste Rechteck, das vollständig
gedeckt ist, auf 16:9 beschnitten: kein schwarzer Rand, nie.

Intrinsik und Extrinsik kommen aus der `ImageResponse` selbst (`source.pinhole`,
`shot.transforms_snapshot`), nichts wird angenommen — dieselbe Regel wie in
`tiefe.py`. Geprüft an einer echten Aufzeichnung vom 12.08.2026
(`tests/daten/blick_real_20260812/`): in der Überlappung stimmen die beiden
Bilder überein, mit vertauschter Kalibrierung dreimal schlechter.

Dieses Modul ist unterhalb von `backends/`, weil `kalibrierung_aus` Protobufs
liest; `Panorama` selbst ist reines numpy.
"""

import math
from dataclasses import dataclass

import numpy as np

from spotlab.errors import SpotlabError

# Abstand der Bildebene vor jeder Kamera. Dort passen die Bilder exakt
# zusammen; näher und ferner entsteht ein leichter Versatz (die Kameras sitzen
# 7 cm auseinander). Gemessen an der Aufzeichnung vom 12.08.2026: bei 1.5 m ist
# die Abweichung in der Überlappung am kleinsten, ab 2 m ändert sich kaum noch etwas.
EBENE_M = 1.5
# Pixel je Radian der virtuellen Kamera. Die Quellbilder haben rund 330; 400
# liefert 820 Pixel Breite, ohne Details zu erfinden.
BRENNWEITE_PX = 400.0
SEITEN = (16, 9)                # Seitenverhältnis des Ausschnitts, wie das Tablet
HORIZONT = 0.35                 # Horizont bei 35 % der Höhe: vorn liegt der Boden
# Gemessene Standhöhe der Körpermitte über dem Boden (Tiefenaufnahme 12.08.2026:
# der Boden liegt bei −0.51 m). Daraus die Höhe der virtuellen Kamera.
STANDHOEHE_M = 0.51

# Zwei Zuschnitte, zwei Zwecke: fahren und erkennen.
RECHTECK = "rechteck"           # grösstes voll gedecktes Rechteck, 16:9 — die Fahransicht
ALLES = "alles"                 # alles Gesehene samt schwarzen Ecken — für Erkenner
AUSGLEICH_GRENZE = (0.6, 1.7)   # Helligkeitsausgleich, geklemmt: kein Bild wird schwarz


@dataclass
class Kamera:
    """Was die Projektion über eine Quelle wissen muss — reine Zahlen."""

    name: str
    breite: int
    hoehe: int
    fx: float
    fy: float
    cx: float
    cy: float
    lage: np.ndarray          # 4x4, body_tform_sensor


def kalibrierung_aus(antworten):
    """`Kamera` je `ImageResponse` — Intrinsik und Extrinsik aus der Nachricht selbst."""
    from bosdyn.client import frame_helpers as fh

    kameras = []
    for antwort in antworten:
        quelle, aufnahme = antwort.source, antwort.shot
        innen = quelle.pinhole.intrinsics
        if not innen.focal_length.x or not innen.focal_length.y:
            raise SpotlabError(
                f"'{quelle.name or 'unbenannt'}' liefert keine Lochkamera-Intrinsik; "
                f"ohne sie lässt sich kein Panorama rechnen.")
        rahmen = aufnahme.frame_name_image_sensor
        lage = fh.get_a_tform_b(aufnahme.transforms_snapshot, fh.BODY_FRAME_NAME, rahmen)
        if lage is None:
            raise SpotlabError(
                f"Im Rahmenbaum von '{quelle.name}' fehlt die Kante body→{rahmen}; "
                f"ohne Extrinsik ist das Panorama geraten.")
        breite, hoehe = aufnahme.image.cols, aufnahme.image.rows
        if not breite or not hoehe:
            raise SpotlabError(f"'{quelle.name}' meldet keine Bildgrösse.")
        kameras.append(Kamera(
            quelle.name, breite, hoehe,
            innen.focal_length.x, innen.focal_length.y,
            innen.principal_point.x, innen.principal_point.y,
            np.asarray(lage.to_matrix(), dtype=np.float64),
        ))
    return kameras


def aufnahmezeit(antwort):
    """Der Aufnahmezeitpunkt der Kamera in Nanosekunden — zwei gleiche heissen dasselbe Bild."""
    return antwort.shot.acquisition_time.ToNanoseconds()


def bilder_aus(antworten):
    """Die dekodierten Bilder (HxW oder HxWx3, uint8) in Reihenfolge der Antworten."""
    from spotlab.api.perception import Image

    return [np.ascontiguousarray(Image(antwort).array) for antwort in antworten]


class Panorama:
    """Die virtuelle Kamera samt vorgerechneten Karten. `zusammensetzen` je Bild."""

    def __init__(self, kameras, ebene_m=EBENE_M, brennweite_px=BRENNWEITE_PX,
                 seiten=SEITEN, ausgleich=True, zuschnitt=RECHTECK):
        if len(kameras) < 2:
            raise SpotlabError("Ein Panorama braucht zwei Kameras.")
        self.kameras = list(kameras)
        self.ebene_m = ebene_m
        self.ausgleich = ausgleich
        self.brennweite = float(brennweite_px)
        position, drehung = self._virtuelle_kamera(self.kameras)
        karten = self._karten(self.kameras, position, drehung, brennweite_px, ebene_m)
        self._voll_hoehe, self._voll_breite = karten[0][2].shape
        if zuschnitt == ALLES:
            oben, unten, links, rechts = self._alles_gesehene(karten)
        else:
            oben, unten, links, rechts = self._ausschnitt(karten, seiten)
        self._oben, self._links = oben, links
        self.breite, self.hoehe = rechts - links, unten - oben
        self._vorbereiten(karten, oben, unten, links, rechts)

    def winkel(self, spalte, zeile):
        """(Peilung, Höhenwinkel) in Grad für ein Pixel des fertigen Bildes.

        Peilung wie überall links positiv, Höhenwinkel nach oben positiv. Das
        ist der ganze Zweck der Zylinderprojektion: eine Bildspalte IST ein
        Azimut, eine Zeile ein Höhenwinkel — kein Rückrechnen durch ein Modell.
        """
        azimut = (self._links + spalte - self._voll_breite / 2.0) / self.brennweite
        tangens = (self._oben + zeile - HORIZONT * self._voll_hoehe) / self.brennweite
        return -math.degrees(azimut), -math.degrees(math.atan(tangens))

    def kamerahoehe(self, standhoehe_m=STANDHOEHE_M):
        """Wie hoch die virtuelle Kamera über dem Boden sitzt, in Metern."""
        z = float(sum(k.lage[2, 3] for k in self.kameras) / len(self.kameras))
        return standhoehe_m + z

    # ------------------------------------------------------------ Aufbau

    @staticmethod
    def _virtuelle_kamera(kameras):
        """Mitte zwischen den Kameras, Blick waagerecht in die mittlere Richtung, oben = Körper-z."""
        position = np.mean([k.lage[:3, 3] for k in kameras], axis=0)
        vorn = np.mean([k.lage[:3, 2] for k in kameras], axis=0)
        vorn[2] = 0.0
        if np.linalg.norm(vorn) < 1e-6:
            raise SpotlabError("Die Kameras schauen senkrecht; daraus wird kein Blick nach vorn.")
        vorn /= np.linalg.norm(vorn)
        oben = np.array([0.0, 0.0, 1.0])
        rechts = np.cross(vorn, oben)
        rechts /= np.linalg.norm(rechts)
        # Spalten: x (rechts), y (unten), z (vorn) der virtuellen Kamera im Körper.
        return position, np.stack([rechts, -oben, vorn], axis=1)

    @staticmethod
    def _karten(kameras, position, drehung, brennweite, ebene):
        """Je Kamera (u, v, gewicht) für jedes Pixel einer grosszügigen Zylinderfläche."""
        breite, hoehe = int(3.5 * brennweite), int(2.25 * brennweite)
        azimut = (np.arange(breite) - breite / 2.0) / brennweite
        tangens = (np.arange(hoehe) - HORIZONT * hoehe) / brennweite
        theta, y = np.meshgrid(azimut, tangens)
        richtung = np.stack([np.sin(theta), y, np.cos(theta)], axis=-1) @ drehung.T
        karten = []
        for k in kameras:
            R, t = k.lage[:3, :3], k.lage[:3, 3]
            ursprung = R.T @ (position - t)          # virtuelle Kamera im Sensorrahmen
            d = richtung @ R                          # Strahlen im Sensorrahmen
            with np.errstate(divide="ignore", invalid="ignore"):
                s = (ebene - ursprung[2]) / d[..., 2]
                x = ursprung[0] + s * d[..., 0]
                yy = ursprung[1] + s * d[..., 1]
                u = k.fx * x / ebene + k.cx
                v = k.fy * yy / ebene + k.cy
            drin = ((d[..., 2] > 1e-6) & (s > 0)
                    & (u >= 0) & (u <= k.breite - 1) & (v >= 0) & (v <= k.hoehe - 1))
            rand = np.minimum(np.minimum(u, k.breite - 1 - u), np.minimum(v, k.hoehe - 1 - v))
            gewicht = np.where(drin, np.clip(rand, 0, None) + 1.0, 0.0)
            karten.append((np.where(drin, u, 0.0), np.where(drin, v, 0.0), gewicht))
        return karten

    @staticmethod
    def _deckung(karten):
        deckung = np.zeros(karten[0][2].shape, dtype=bool)
        for _, _, gewicht in karten:
            deckung |= gewicht > 0
        return deckung

    @classmethod
    def _alles_gesehene(cls, karten):
        """Alles, was mindestens eine Kamera sieht — mit schwarzen Ecken.

        Für einen Erkenner ist eine schwarze Ecke kein Problem, ein fehlendes
        Blickfeld schon: das volle Feld reicht 26° nach oben, das gedeckte
        Rechteck nur 7°. Gemessen an der Aufzeichnung vom 12.08.2026 — und
        genau diese 19° entscheiden, ob ein stehender Mensch ein Gesicht hat
        oder nur Beine.
        """
        deckung = cls._deckung(karten)
        zeilen = np.flatnonzero(deckung.any(axis=1))
        spalten = np.flatnonzero(deckung.any(axis=0))
        if not zeilen.size or not spalten.size:
            raise SpotlabError("Die Kameras sehen nichts.")
        return int(zeilen[0]), int(zeilen[-1]) + 1, int(spalten[0]), int(spalten[-1]) + 1

    @classmethod
    def _ausschnitt(cls, karten, seiten):
        """Das grösste voll gedeckte Rechteck, dann auf `seiten` beschnitten."""
        deckung = cls._deckung(karten)
        hoehe, breite = deckung.shape
        oben, unten, links, rechts = 0, hoehe, 0, breite
        while not deckung[oben:unten, links:rechts].all():
            fenster = deckung[oben:unten, links:rechts]
            luecken = {"oben": (~fenster[0]).sum(), "unten": (~fenster[-1]).sum(),
                       "links": (~fenster[:, 0]).sum(), "rechts": (~fenster[:, -1]).sum()}
            seite = max(luecken, key=luecken.get)
            if seite == "oben":
                oben += 1
            elif seite == "unten":
                unten -= 1
            elif seite == "links":
                links += 1
            else:
                rechts -= 1
            if unten - oben < 16 or rechts - links < 16:
                raise SpotlabError("Die Kameras decken kein gemeinsames Rechteck.")
        b, h = rechts - links, unten - oben
        soll_h = int(b * seiten[1] / seiten[0])
        if h > soll_h:
            # Zu hoch: ein Viertel des Überschusses oben weg, drei Viertel unten —
            # der Boden dicht vor den Füssen ist weniger wert als das, was vorausliegt.
            ueber = h - soll_h
            oben += ueber // 4
            unten = oben + soll_h
        else:
            soll_b = int(h * seiten[0] / seiten[1])
            ueber = b - soll_b
            links += ueber // 2
            rechts = links + soll_b
        return oben, unten, links, rechts

    def _vorbereiten(self, karten, oben, unten, links, rechts):
        """Flache Indizes: nur Kamera 1, nur Kamera 2, beide (mit Gewicht)."""
        flach = []
        for k, (u, v, gewicht) in zip(self.kameras, karten):
            u, v, gewicht = u[oben:unten, links:rechts], v[oben:unten, links:rechts], gewicht[oben:unten, links:rechts]
            spalte = np.clip(np.rint(u).astype(np.int64), 0, k.breite - 1)
            zeile = np.clip(np.rint(v).astype(np.int64), 0, k.hoehe - 1)
            flach.append(((zeile * k.breite + spalte).ravel(), gewicht.ravel()))
        (i1, g1), (i2, g2) = flach[0], flach[1]
        nur1 = np.flatnonzero((g1 > 0) & (g2 == 0))
        nur2 = np.flatnonzero((g2 > 0) & (g1 == 0))
        beide = np.flatnonzero((g1 > 0) & (g2 > 0))
        self._nur1 = (nur1, i1[nur1])
        self._nur2 = (nur2, i2[nur2])
        self._beide = (beide, i1[beide], i2[beide])
        self._gewicht1 = (g1[beide] / (g1[beide] + g2[beide])).astype(np.float32)[:, None]
        self.ueberlappung_px = int(beide.size)

    # ------------------------------------------------------------- Je Bild

    def _flach(self, bild, kamera):
        if bild.shape[0] != kamera.hoehe or bild.shape[1] != kamera.breite:
            raise SpotlabError(
                f"'{kamera.name}' kommt als {bild.shape[1]}×{bild.shape[0]}, die Karte gilt "
                f"für {kamera.breite}×{kamera.hoehe}.")
        return bild.reshape(bild.shape[0] * bild.shape[1], -1)

    def _beide_flach(self, bilder):
        a = self._flach(bilder[0], self.kameras[0])
        b = self._flach(bilder[1], self.kameras[1])
        if a.shape[1] != b.shape[1]:
            kanaele = max(a.shape[1], b.shape[1])
            a = np.repeat(a, kanaele, axis=1) if a.shape[1] == 1 else a
            b = np.repeat(b, kanaele, axis=1) if b.shape[1] == 1 else b
        return a, b

    @staticmethod
    def _abgleich(beide_a, beide_b):
        """Zwei Nachschlagetabellen, die die Helligkeit der Überlappung angleichen.

        Die Kameras belichten getrennt; in der Überlappung sehen beide dasselbe.
        Ein gemeinsamer Faktor (halb hier, halb dort) zieht sie zusammen.
        """
        # `faktor` ist die Wurzel des Verhältnisses: a durch ihn und b mal ihn
        # treffen sich im geometrischen Mittel.
        faktor = math.sqrt((float(beide_a.mean()) + 1.0) / (float(beide_b.mean()) + 1.0))
        faktor = min(max(faktor, AUSGLEICH_GRENZE[0]), AUSGLEICH_GRENZE[1])
        stufen = np.arange(256, dtype=np.float32)
        tabelle_a = np.clip(stufen / faktor + 0.5, 0, 255).astype(np.uint8)
        tabelle_b = np.clip(stufen * faktor + 0.5, 0, 255).astype(np.uint8)
        return tabelle_a, tabelle_b

    def proben(self, bilder, ausgleich=None):
        """Die beiden Bilder in der Überlappung, als (n, Kanäle) — zum Vergleichen.

        Mit `ausgleich` (Vorgabe: wie das Panorama) nach dem Helligkeitsabgleich.
        """
        a, b = self._beide_flach(bilder)
        _, q1, q2 = self._beide
        beide_a, beide_b = a[q1], b[q2]
        if (self.ausgleich if ausgleich is None else ausgleich) and beide_a.size:
            tabelle_a, tabelle_b = self._abgleich(beide_a, beide_b)
            return tabelle_a[beide_a], tabelle_b[beide_b]
        return beide_a, beide_b

    def zusammensetzen(self, bilder):
        """Ein Bild (hoehe × breite[, Kanäle], uint8) aus den Bildern der beiden Kameras."""
        a, b = self._beide_flach(bilder)
        kanaele = a.shape[1]
        ziel1, q1 = self._nur1
        ziel2, q2 = self._nur2
        zielb, b1, b2 = self._beide
        nur_a, nur_b = a[q1], b[q2]
        beide_a, beide_b = a[b1], b[b2]
        if self.ausgleich and beide_a.size:
            tabelle_a, tabelle_b = self._abgleich(beide_a, beide_b)
            nur_a, beide_a = tabelle_a[nur_a], tabelle_a[beide_a]
            nur_b, beide_b = tabelle_b[nur_b], tabelle_b[beide_b]
        aus = np.empty((self.hoehe * self.breite, kanaele), dtype=np.uint8)
        aus[ziel1] = nur_a
        aus[ziel2] = nur_b
        misch = beide_a.astype(np.float32) * self._gewicht1 + beide_b.astype(np.float32) * (1.0 - self._gewicht1)
        aus[zielb] = (misch + 0.5).astype(np.uint8)
        aus = aus.reshape(self.hoehe, self.breite, kanaele)
        return aus[..., 0] if kanaele == 1 else aus
