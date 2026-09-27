"""Die wachsende Skizze der Steuerzentrale: was Spot gesehen hat, als Raster im Rahmen „vision“.

Jedes Hindernisgitter (`spot.obstacles()`, 3-cm-Zellen um Spot, mit Maske für das
Beobachtete) wird in 5-cm-Zellen eingearbeitet: je Zelle ein Zustand (unbekannt,
frei, Wand) und die Zeit der letzten Beobachtung. Die Skizze wächst mit der Fahrt
und vergisst nichts — nur blasser wird, was lange nicht gesehen wurde. **Die
neueste Beobachtung gewinnt**: ein Mensch, der weggeht, hinterlässt keine Wand.

Der Rahmen ist „vision“ wie beim Gitter; über lange Wege darf die Skizze etwas
verziehen (Odometrie). Eine echte Karte ist Teil 3 der Steuerzentrale
(`docs/superpowers/specs/2026-09-27-steuerzentrale-design.md`).

Rein rechnerisch, ohne Roboter prüfbar. Die Farben des Bilds legt die GUI fest:
hier stehen nur Farbnummern (`record/zentrale.ALTERSSTUFEN`).
"""

import io
import math

import numpy as np

from spotlab.record.zentrale import ALTERSSTUFEN

ZELLE_M = 0.05
# Liegt in einer 5-cm-Zelle ein Gitterabstand bis hierhin, ist die Zelle Wand.
WAND_BIS_M = 0.05
ANBAU_M = 2.0              # so viel wächst die Skizze auf einmal (und so liegen ihre Ränder)
MAX_M = 60.0               # grösser wird sie nie: die Seite fern vom Neuen fällt weg
UNBEKANNT, FREI, WAND = 0, 1, 2
FRISCH_S = 5.0             # so lange gilt eine Beobachtung als frisch
ALT_S = 60.0               # ab hier ist sie so blass, wie es geht
# Ein Hauch in Zellen beim Einsortieren: 20 x 0.03 m sind rechnerisch 0.5999…, und ohne
# ihn landete eine Gitterzeile genau auf einer Zellgrenze in der Zelle darunter.
_HAUCH = 1e-6


class Skizze:
    """Zustand und Alter je Zelle; Zeile = y, Spalte = x, Zelle [0, 0] unten links bei `ursprung`."""

    def __init__(self, zelle_m=ZELLE_M):
        self.zelle_m = float(zelle_m)
        self.ursprung = None
        self.zustand = np.zeros((0, 0), np.uint8)
        self.zeit = np.zeros((0, 0), np.float64)

    @property
    def leer(self):
        return self.ursprung is None

    def zelle(self, x, y):
        """(Zeile, Spalte) der Zelle unter (x, y) — oder None ausserhalb."""
        if self.leer:
            return None
        spalte = int(math.floor((x - self.ursprung[0]) / self.zelle_m + _HAUCH))
        zeile = int(math.floor((y - self.ursprung[1]) / self.zelle_m + _HAUCH))
        hoehe, breite = self.zustand.shape
        if 0 <= zeile < hoehe and 0 <= spalte < breite:
            return zeile, spalte
        return None

    def welt(self, zeile, spalte):
        """Die Mitte einer Zelle in Weltkoordinaten."""
        return (self.ursprung[0] + (spalte + 0.5) * self.zelle_m,
                self.ursprung[1] + (zeile + 0.5) * self.zelle_m)

    # ------------------------------------------------------------ Einarbeiten

    def aufnehmen(self, gitter, t):
        """Ein Hindernisgitter (`ObstacleGrid`) einarbeiten. Unbeobachtetes ändert nichts."""
        werte = np.asarray(gitter.cells, dtype=float)
        bekannt = (np.ones(werte.shape, bool) if gitter.known is None
                   else np.asarray(gitter.known, bool)) & np.isfinite(werte)
        zeilen, spalten = np.nonzero(bekannt)
        if not len(zeilen):
            return
        xs = gitter.origin[0] + spalten * gitter.cell_size
        ys = gitter.origin[1] + zeilen * gitter.cell_size
        self._decke(float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))
        z = np.floor((ys - self.ursprung[1]) / self.zelle_m + _HAUCH).astype(int)
        s = np.floor((xs - self.ursprung[0]) / self.zelle_m + _HAUCH).astype(int)
        hoehe, breite = self.zustand.shape
        drin = (z >= 0) & (z < hoehe) & (s >= 0) & (s < breite)
        kleinster = np.full((hoehe, breite), np.inf)
        np.minimum.at(kleinster, (z[drin], s[drin]), werte[zeilen[drin], spalten[drin]])
        getroffen = np.isfinite(kleinster)
        self.zustand[getroffen] = np.where(kleinster[getroffen] <= WAND_BIS_M, WAND, FREI)
        self.zeit[getroffen] = t

    def _decke(self, x0, y0, x1, y1):
        """Die Skizze so gross machen, dass (x0, y0)–(x1, y1) hineinpasst — höchstens MAX_M."""
        a = ANBAU_M
        nx0, ny0 = math.floor(x0 / a) * a, math.floor(y0 / a) * a
        nx1, ny1 = (math.floor(x1 / a) + 1) * a, (math.floor(y1 / a) + 1) * a
        if not self.leer:
            hoehe, breite = self.zustand.shape
            ax0, ay0 = self.ursprung
            ax1, ay1 = ax0 + breite * self.zelle_m, ay0 + hoehe * self.zelle_m
            if nx0 >= ax0 - 1e-9 and ny0 >= ay0 - 1e-9 and nx1 <= ax1 + 1e-9 and ny1 <= ay1 + 1e-9:
                return
            nx0, ny0, nx1, ny1 = min(nx0, ax0), min(ny0, ay0), max(nx1, ax1), max(ny1, ay1)
        nx0, nx1 = _gedeckelt(nx0, nx1, (x0 + x1) / 2.0)
        ny0, ny1 = _gedeckelt(ny0, ny1, (y0 + y1) / 2.0)
        breite = int(round((nx1 - nx0) / self.zelle_m))
        hoehe = int(round((ny1 - ny0) / self.zelle_m))
        zustand = np.zeros((hoehe, breite), np.uint8)
        zeit = np.zeros((hoehe, breite), np.float64)
        if not self.leer:
            dz = int(round((self.ursprung[1] - ny0) / self.zelle_m))
            ds = int(round((self.ursprung[0] - nx0) / self.zelle_m))
            _kopiere(self.zustand, zustand, dz, ds)
            _kopiere(self.zeit, zeit, dz, ds)
        self.ursprung = (nx0, ny0)
        self.zustand, self.zeit = zustand, zeit

    # ------------------------------------------------------------ Bild

    def bild_index(self, t):
        """Farbnummern je Zelle, Zeile 0 = OBEN (grösstes y): 0 unbekannt, dann frei, dann Wand."""
        if self.leer:
            raise ValueError("Die Skizze ist leer — noch kein Hindernisgitter gesehen.")
        alter = np.maximum(0.0, t - self.zeit)
        stufe = np.clip((alter - FRISCH_S) / (ALT_S - FRISCH_S) * (ALTERSSTUFEN - 1),
                        0, ALTERSSTUFEN - 1).astype(np.uint8)
        index = np.zeros(self.zustand.shape, np.uint8)
        frei = self.zustand == FREI
        wand = self.zustand == WAND
        index[frei] = 1 + stufe[frei]
        index[wand] = 1 + ALTERSSTUFEN + stufe[wand]
        return np.flipud(index)

    def png(self, t):
        """Das Bild als PNG mit Palette — die GUI ersetzt die Palette durch ihre Farben."""
        from PIL import Image

        bild = Image.fromarray(self.bild_index(t), mode="P")
        grau = []
        for i in range(256):
            grau += [i, i, i]
        bild.putpalette(grau)
        puffer = io.BytesIO()
        bild.save(puffer, format="PNG")
        return puffer.getvalue()


def _gedeckelt(lo, hi, mitte_neu):
    """Höchstens MAX_M breit: die Seite fern vom neuen Stück fällt weg."""
    if hi - lo <= MAX_M + 1e-9:
        return lo, hi
    if mitte_neu > (lo + hi) / 2.0:
        return hi - MAX_M, hi
    return lo, lo + MAX_M


def _kopiere(alt, neu, dz, ds):
    """`alt` an der Verschiebung (dz, ds) in `neu` schreiben, was hineinpasst."""
    ha, ba = alt.shape
    hn, bn = neu.shape
    z0, s0 = max(0, dz), max(0, ds)
    z1, s1 = min(hn, dz + ha), min(bn, ds + ba)
    if z1 <= z0 or s1 <= s0:
        return
    neu[z0:z1, s0:s1] = alt[z0 - dz:z1 - dz, s0 - ds:s1 - ds]
