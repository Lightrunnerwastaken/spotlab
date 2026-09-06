"""Geometrie und Kamera der 3D-Sicht -- ohne GL.

Kaesten aus Waenden, Bloecken, Tags und dem Spot am Start, das Bodenraster,
die Orbit-Kamera mit Matrizen und Mausstrahl. Alles mit `QMatrix4x4`/`QVector3D`
aus Qt, kein numpy (Regel fuer gui/), und deshalb unter `offscreen` testbar --
`sicht3d.py` ist nur noch die GL-Haut darum.
"""

import math

from PySide6.QtGui import QMatrix4x4, QVector3D

SPOT_LAENGE, SPOT_BREITE, SPOT_HOEHE, SPOT_OBEN = 1.1, 0.5, 0.2, 0.6
TAG_KANTE, TAG_DICKE = 0.15, 0.02
FOV_GRAD = 50.0

# Die sechs Flaechen eines Einheitskastens (+-1): je zwei Dreiecke, mit Normale.
_FLAECHEN = (
    ((1, 0, 0), ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1))),
    ((-1, 0, 0), ((-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1))),
    ((0, 1, 0), ((1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1))),
    ((0, -1, 0), ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1))),
    ((0, 0, 1), ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))),
    ((0, 0, -1), ((-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1))),
)


def kasten(x, y, z, hx, hy, hz, yaw_grad=0.0):
    """36 Vertices (px, py, pz, nx, ny, nz) eines um die Hochachse gedrehten Kastens."""
    c, s = math.cos(math.radians(yaw_grad)), math.sin(math.radians(yaw_grad))
    daten = []
    for normale, ecken in _FLAECHEN:
        nx, ny = normale[0] * c - normale[1] * s, normale[0] * s + normale[1] * c
        n = (nx, ny, float(normale[2]))
        punkte = []
        for ex, ey, ez in ecken:
            lx, ly, lz = ex * hx, ey * hy, ez * hz
            punkte.append((x + lx * c - ly * s, y + lx * s + ly * c, z + lz))
        for a, b_, d in ((0, 1, 2), (0, 2, 3)):
            for p in (punkte[a], punkte[b_], punkte[d]):
                daten.extend(p)
                daten.extend(n)
    return daten


def kaesten_aus_raum(raum, auswahl):
    """[(schluessel, vertices)] fuer Waende, Bloecke, Tags und den Spot am Start."""
    kaesten = []
    for i, wand in enumerate(raum.waende):
        if wand.laenge <= 0:
            continue
        mx, my = wand.mitte
        kaesten.append((("wand", i), kasten(
            mx, my, raum.wand_hoehe / 2, wand.laenge / 2, raum.wand_dicke / 2,
            raum.wand_hoehe / 2, wand.winkel)))
    for i, b in enumerate(raum.bloecke):
        kaesten.append((("block", i), kasten(
            b.x, b.y, b.hoehe / 2, b.breite / 2, b.tiefe / 2, b.hoehe / 2, b.drehung)))
    for i, t in enumerate(raum.tags):
        kaesten.append((("tag", i), kasten(
            t.x, t.y, t.hoehe, TAG_DICKE / 2, TAG_KANTE / 2, TAG_KANTE / 2, t.grad)))
    sx, sy, sgrad = raum.start
    kaesten.append((("start",), kasten(
        sx, sy, SPOT_OBEN - SPOT_HOEHE / 2, SPOT_LAENGE / 2, SPOT_BREITE / 2,
        SPOT_HOEHE / 2, sgrad)))
    return kaesten


def bodenraster(huelle_, schritt=1.0):
    """Linien (x, y, z) am Boden ueber die Huelle, ganze Meter."""
    x0, y0, x1, y1 = huelle_
    linien = []
    k = math.floor(x0 / schritt)
    while k * schritt <= x1 + 1e-9:
        linien += [k * schritt, y0, 0.0, k * schritt, y1, 0.0]
        k += 1
    k = math.floor(y0 / schritt)
    while k * schritt <= y1 + 1e-9:
        linien += [x0, k * schritt, 0.0, x1, k * schritt, 0.0]
        k += 1
    return linien


def spot_pfeil(start):
    x, y, grad = start
    return [x, y, 0.3,
            x + 0.6 * math.cos(math.radians(grad)), y + 0.6 * math.sin(math.radians(grad)), 0.3]


def farbe_fuer(index):
    """Eine eindeutige Farbe (0..1) je Element -- fuer den Farb-ID-Puffer."""
    return (((index >> 16) & 255) / 255.0, ((index >> 8) & 255) / 255.0, (index & 255) / 255.0)


def index_aus(r, g, b):
    return (int(r) << 16) | (int(g) << 8) | int(b)


class Kamera:
    """Orbit um ein Ziel am Boden. Azimut/Elevation in Grad, Abstand in Metern."""

    def __init__(self, ziel=(0.0, 0.0, 0.0), abstand=8.0, azimut=45.0, elevation=35.0):
        self.ziel = tuple(float(v) for v in ziel)
        self.abstand = float(abstand)
        self.azimut = float(azimut)
        self.elevation = float(elevation)

    def orbit(self, d_azimut, d_elevation):
        self.azimut = (self.azimut + d_azimut) % 360.0
        self.elevation = max(5.0, min(89.0, self.elevation + d_elevation))

    def zoom(self, faktor):
        self.abstand = max(1.0, min(60.0, self.abstand * faktor))

    def schwenke(self, dx_m, dy_m):
        """In der Bodenebene, relativ zur Blickrichtung (rechts, vorwaerts)."""
        a = math.radians(self.azimut)
        rechts = (-math.sin(a), math.cos(a))
        vor = (-math.cos(a), -math.sin(a))
        self.ziel = (self.ziel[0] + rechts[0] * dx_m + vor[0] * dy_m,
                     self.ziel[1] + rechts[1] * dx_m + vor[1] * dy_m, 0.0)

    def rahme(self, huelle_):
        x0, y0, x1, y1 = huelle_
        self.ziel = ((x0 + x1) / 2, (y0 + y1) / 2, 0.0)
        spanne = max(x1 - x0, y1 - y0, 1.0)
        self.abstand = max(1.0, min(
            60.0, spanne / (2.0 * math.tan(math.radians(FOV_GRAD) / 2)) * 1.3))

    def auge(self):
        a, e = math.radians(self.azimut), math.radians(self.elevation)
        return QVector3D(self.ziel[0] + self.abstand * math.cos(e) * math.cos(a),
                         self.ziel[1] + self.abstand * math.cos(e) * math.sin(a),
                         self.ziel[2] + self.abstand * math.sin(e))

    def ansicht(self):
        m = QMatrix4x4()
        m.lookAt(self.auge(), QVector3D(*self.ziel), QVector3D(0.0, 0.0, 1.0))
        return m

    def projektion(self, breite, hoehe):
        m = QMatrix4x4()
        m.perspective(FOV_GRAD, max(breite, 1) / max(hoehe, 1), 0.05, 200.0)
        return m

    def strahl(self, px, py, breite, hoehe):
        """(Ursprung, Richtung) des Mausstrahls in Weltkoordinaten."""
        inv, _ok = (self.projektion(breite, hoehe) * self.ansicht()).inverted()
        nx = 2.0 * px / max(breite, 1) - 1.0
        ny = 1.0 - 2.0 * py / max(hoehe, 1)
        nah = inv.map(QVector3D(nx, ny, -1.0))
        fern = inv.map(QVector3D(nx, ny, 1.0))
        richtung = fern - nah
        richtung.normalize()
        return nah, richtung

    def bodenpunkt(self, px, py, breite, hoehe):
        """Schnitt des Mausstrahls mit z = 0, oder None (Blick nach oben)."""
        ursprung, richtung = self.strahl(px, py, breite, hoehe)
        if abs(richtung.z()) < 1e-9:
            return None
        t = -ursprung.z() / richtung.z()
        if t < 0:
            return None
        return (ursprung.x() + t * richtung.x(), ursprung.y() + t * richtung.y())


__all__ = ["Kamera", "QVector3D", "bodenraster", "farbe_fuer", "index_aus",
           "kaesten_aus_raum", "kasten", "spot_pfeil"]
