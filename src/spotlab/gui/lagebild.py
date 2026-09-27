"""Die Draufsicht der Steuerzentrale: die Skizze aus `lagebild.png`, darüber Spot, Tags,
Menschen, Weg und Ziel.

Das Widget rechnet nichts ausser Umrechnen und Zeichnen — die Skizze baut das Programm
(`workshop/zentrale.py`), hier kommt sie als Datei an. Das PNG trägt Farbnummern
(`record/zentrale.ALTERSSTUFEN`), die Farben legt dieses Widget aus dem Thema darüber:
so stimmt die Skizze in hell und dunkel, und im Code steht kein Farbwert.

Oben ist +y, rechts +x (Rahmen „vision“ wie die Skizze). Die Ansicht folgt Spot, bis
man sie verschiebt; „Mitte“ (`mitte()`) holt sie zurück. Mausrad zoomt um den Zeiger.
Ein Klick ohne Ziehen meldet die Weltkoordinate über `klick`.

Menschen (Teil 2) sind Kreise, so breit wie ein Mensch, aber nie kleiner als lesbar; sie
werden mit dem Alter blasser (das Programm schickt sie höchstens 3 s alt), der Gefolgte trägt einen
Ring in Spots Farbe. `mensch_bei` sagt, ob ein Klick einen trifft — getroffen wird, was
man SIEHT: klein gezoomt ist der Kreis grösser als ein halber Meter.

Eine geladene Karte (Teil 3) kommt als zweites Indexbild (`lagebild_karte.png`) mit eigener
Ausdehnung im selben Zellgitter: nicht geprüft blass, erkannt in Spots Farbe, neu in der
Gefahrfarbe, fehlt GESTRICHELT — eine Maske nur der Fehlt-Zellen, darüber ein Musterpinsel,
so bleibt es reines Qt (kein numpy im Fenster). Dazu Wegpunkte und Kanten der Karte.

Kein `bosdyn`, kein `spotlab.backends`: die GUI liest nur Dateien.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from spotlab.gui.theme import mische, palette_fuer
from spotlab.record.zentrale import (
    ALTERSSTUFEN,
    KARTE_ERKANNT,
    KARTE_FEHLT,
    KARTE_NEU,
    KARTE_UNGEPRUEFT,
)

ZIEHEN_AB_PX = 4
MASSSTAB_VORGABE = 60.0          # Pixel je Meter
MASSSTAB_GRENZEN = (8.0, 400.0)
ZOOM_JE_RAST = 1.15
BLASS_ALPHA = 110                # die älteste Altersstufe
MENSCH_M = 0.22                  # Halbmesser eines Menschen von oben
MENSCH_MIN_PX = 6.0
MENSCH_ALTER_S = 3.0             # so alt wird ein Mensch im Lagebild höchstens
MENSCH_BLASS_ALPHA = 70
RING_ABSTAND_PX = 5.0
KARTE_BLASS_ALPHA = 120          # Kartenwand ausserhalb des Blickfelds
WEGPUNKT_PX = 4.0


class Lagebild(QWidget):
    klick = Signal(float, float)

    def __init__(self, palette=None, parent=None):
        super().__init__(parent)
        self._palette = palette or palette_fuer(False)
        self._daten = None
        self._roh = None                  # das geladene Indexbild (Farbnummern)
        self._bild = None                 # dasselbe mit den Themenfarben
        self._karte_roh = None            # das Kartenbild (Farbnummern des Abgleichs)
        self._karte_bild = None           # dasselbe mit den Themenfarben
        self._mitte = (0.0, 0.0)
        self.px_je_m = MASSSTAB_VORGABE
        self.folgt = True
        self._druck = None
        self._gezogen = False
        self._mitte_beim_druck = None
        self.setMinimumSize(280, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------ Daten

    def setze_palette(self, palette):
        self._palette = palette
        self._faerbe()
        self._faerbe_karte()
        self.update()

    def zeige(self, daten, bilddaten, kartenbild=None):
        """Ein neues Lagebild. Ein unlesbares Bild lässt das letzte stehen (halb geschrieben)."""
        self._daten = daten
        if bilddaten:
            bild = _indexbild(bilddaten)
            if bild is not None:
                self._roh = bild
                self._faerbe()
        if kartenbild:
            bild = _indexbild(kartenbild)
            if bild is not None:
                self._karte_roh = bild
                self._faerbe_karte()
        spot = (daten or {}).get("spot")
        if self.folgt and spot:
            self._mitte = (float(spot["x"]), float(spot["y"]))
        self.update()

    def leeren(self):
        self._daten = None
        self._roh = self._bild = None
        self._karte_roh = self._karte_bild = None
        self.folgt = True
        self.update()

    def hat_bild(self):
        return self._bild is not None

    def hat_kartenbild(self):
        return self._karte_bild is not None and bool(self._karten_raster())

    def _karten_raster(self):
        karte = (self._daten or {}).get("karte") or {}
        return karte.get("raster")

    def mensch_radius_px(self):
        return max(MENSCH_MIN_PX, MENSCH_M * self.px_je_m)

    def mensch_bei(self, x, y, umkreis_m):
        """Der Mensch (dict aus dem Lagebild), den ein Klick bei (x, y) meint — oder None.

        Im Umkreis `umkreis_m`, mindestens aber so weit, wie sein Kreis gezeichnet ist."""
        menschen = (self._daten or {}).get("menschen") or []
        if not menschen:
            return None
        umkreis = max(umkreis_m, (self.mensch_radius_px() + RING_ABSTAND_PX) / self.px_je_m)

        def weite(m):
            return math.hypot(float(m["x"]) - x, float(m["y"]) - y)

        bester = min(menschen, key=weite)
        return bester if weite(bester) <= umkreis else None

    def mitte(self):
        """Die Ansicht folgt wieder Spot."""
        self.folgt = True
        spot = (self._daten or {}).get("spot")
        if spot:
            self._mitte = (float(spot["x"]), float(spot["y"]))
        self.update()

    def _faerbe(self):
        if self._roh is None:
            return
        p = self._palette
        frei = QColor(mische(p.flaeche, p.text, 0.16))
        wand = QColor(p.text)
        tabelle = [0] * 256                  # 0 und alles ohne Bedeutung: durchsichtig
        for stufe in range(ALTERSSTUFEN):
            alpha = round(255 - (255 - BLASS_ALPHA) * stufe / max(1, ALTERSSTUFEN - 1))
            for code, farbe in ((1 + stufe, frei), (1 + ALTERSSTUFEN + stufe, wand)):
                tabelle[code] = QColor(farbe.red(), farbe.green(), farbe.blue(), alpha).rgba()
        bild = self._roh.copy()
        bild.setColorTable(tabelle)
        self._bild = bild.convertToFormat(QImage.Format_ARGB32_Premultiplied)

    def _faerbe_karte(self):
        if self._karte_roh is None:
            return
        p = self._palette
        blass = QColor(p.gedaempft)
        blass.setAlpha(KARTE_BLASS_ALPHA)
        tabelle = [0] * 256
        tabelle[KARTE_UNGEPRUEFT] = blass.rgba()
        tabelle[KARTE_ERKANNT] = QColor(p.ok).rgba()
        tabelle[KARTE_NEU] = QColor(p.gefahr).rgba()
        bild = self._karte_roh.copy()
        bild.setColorTable(tabelle)
        farbig = bild.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        # Fehlt: die Maske der Fehlt-Zellen, darin nur jede zweite Zelle (Schachbrett).
        maske = self._karte_roh.copy()
        nur_fehlt = [0] * 256
        nur_fehlt[KARTE_FEHLT] = QColor(p.text).rgba()
        maske.setColorTable(nur_fehlt)
        maske = maske.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        maler = QPainter(maske)
        maler.setCompositionMode(QPainter.CompositionMode_SourceIn)
        maler.fillRect(maske.rect(), QBrush(QColor(p.warnung), Qt.Dense4Pattern))
        maler.end()
        maler = QPainter(farbig)
        maler.drawImage(0, 0, maske)
        maler.end()
        self._karte_bild = farbig

    # ------------------------------------------------------------ Umrechnen

    def welt_zu_schirm(self, x, y):
        return QPointF(self.width() / 2.0 + (x - self._mitte[0]) * self.px_je_m,
                       self.height() / 2.0 - (y - self._mitte[1]) * self.px_je_m)

    def schirm_zu_welt(self, px, py):
        return (self._mitte[0] + (px - self.width() / 2.0) / self.px_je_m,
                self._mitte[1] - (py - self.height() / 2.0) / self.px_je_m)

    # ------------------------------------------------------------ Zeichnen

    def paintEvent(self, _ereignis):
        p = self._palette
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        # Die FLÄCHE, nicht der Seitenhintergrund: sonst sieht man nicht, wo das Feld
        # aufhört -- Unbekanntes hatte die Farbe der Seite (Bild vom 27.09.2026).
        maler.fillRect(self.rect(), QColor(p.flaeche))
        daten = self._daten or {}
        if self._bild is not None and daten.get("ursprung") and daten.get("breite"):
            zelle = float(daten["zelle_m"])
            ux, uy = daten["ursprung"]
            links_oben = self.welt_zu_schirm(ux, uy + daten["hoehe"] * zelle)
            groesse = zelle * self.px_je_m
            ziel = QRectF(links_oben.x(), links_oben.y(), daten["breite"] * groesse,
                          daten["hoehe"] * groesse)
            maler.drawImage(ziel, self._bild)
        elif not daten:
            maler.setPen(QColor(p.gedaempft))
            maler.drawText(self.rect(), Qt.AlignCenter, "Noch kein Lagebild — Fahrt beginnen.")
        self._zeichne_karte(maler, daten)
        self._zeichne_klickfahrt(maler, daten.get("klickfahrt") or {})
        self._zeichne_tags(maler, daten.get("tags") or [])
        self._zeichne_menschen(maler, daten.get("menschen") or [])
        self._zeichne_spot(maler, daten.get("spot"))
        maler.setPen(QPen(QColor(p.rand), 1))
        maler.setBrush(Qt.NoBrush)
        maler.drawRect(self.rect().adjusted(0, 0, -1, -1))
        maler.end()

    def _zeichne_karte(self, maler, daten):
        karte = daten.get("karte") or {}
        raster = karte.get("raster")
        if raster and self._karte_bild is not None:
            zelle = float(daten.get("zelle_m") or 0.05)
            ux, uy = raster["ursprung"]
            links_oben = self.welt_zu_schirm(ux, uy + raster["hoehe"] * zelle)
            groesse = zelle * self.px_je_m
            maler.drawImage(QRectF(links_oben.x(), links_oben.y(), raster["breite"] * groesse,
                                   raster["hoehe"] * groesse), self._karte_bild)
        p = self._palette
        wegpunkte = karte.get("wegpunkte") or []
        maler.setPen(QPen(QColor(p.gedaempft), 1))
        for i, j in karte.get("kanten") or []:
            if 0 <= i < len(wegpunkte) and 0 <= j < len(wegpunkte):
                a, b = wegpunkte[i], wegpunkte[j]
                maler.drawLine(self.welt_zu_schirm(a["x"], a["y"]),
                               self.welt_zu_schirm(b["x"], b["y"]))
        for w in wegpunkte:
            q = self.welt_zu_schirm(w["x"], w["y"])
            maler.setPen(QPen(QColor(p.akzent), 1))
            maler.setBrush(QColor(p.akzent_flaeche))
            maler.drawEllipse(q, WEGPUNKT_PX, WEGPUNKT_PX)
            if w.get("name"):
                maler.setPen(QColor(p.text))
                maler.drawText(QRectF(q.x() + 6, q.y() - 9, 120, 18),
                               Qt.AlignLeft | Qt.AlignVCenter, str(w["name"]))
        maler.setBrush(Qt.NoBrush)

    def _zeichne_klickfahrt(self, maler, k):
        p = self._palette
        weg = k.get("weg") or []
        spot = (self._daten or {}).get("spot")
        if weg and k.get("zustand") == "unterwegs":
            punkte = ([self.welt_zu_schirm(spot["x"], spot["y"])] if spot else []) + [
                self.welt_zu_schirm(x, y) for x, y in weg]
            maler.setPen(QPen(QColor(p.warnung), 2, Qt.DashLine))
            maler.drawPolyline(QPolygonF(punkte))
        ziel = k.get("ziel")
        if ziel:
            farbe = QColor(p.gefahr if k.get("zustand") in ("abgelehnt", "versperrt") else p.akzent)
            q = self.welt_zu_schirm(*ziel)
            maler.setPen(QPen(farbe, 2))
            r = 7
            maler.drawLine(QPointF(q.x() - r, q.y() - r), QPointF(q.x() + r, q.y() + r))
            maler.drawLine(QPointF(q.x() - r, q.y() + r), QPointF(q.x() + r, q.y() - r))

    def _zeichne_tags(self, maler, tags):
        p = self._palette
        for tag in tags:
            q = self.welt_zu_schirm(tag["x"], tag["y"])
            maler.setPen(QPen(QColor(p.akzent), 2))
            maler.setBrush(QColor(p.akzent_flaeche))
            maler.drawRect(QRectF(q.x() - 7, q.y() - 7, 14, 14))
            maler.setPen(QColor(p.text))
            maler.drawText(QRectF(q.x() + 9, q.y() - 9, 40, 18), Qt.AlignLeft | Qt.AlignVCenter,
                           str(tag["id"]))
        maler.setBrush(Qt.NoBrush)

    def _zeichne_menschen(self, maler, menschen):
        p = self._palette
        r = self.mensch_radius_px()
        fuellung, rand = QColor(p.warnung), QColor(p.text)
        for m in menschen:
            q = self.welt_zu_schirm(float(m["x"]), float(m["y"]))
            anteil = min(1.0, max(0.0, float(m.get("alter_s") or 0.0)) / MENSCH_ALTER_S)
            alpha = round(255 - (255 - MENSCH_BLASS_ALPHA) * anteil)
            fuellung.setAlpha(alpha)
            rand.setAlpha(alpha)
            maler.setPen(QPen(rand, 1))
            maler.setBrush(fuellung)
            maler.drawEllipse(q, r, r)
            if m.get("gefolgt"):
                maler.setPen(QPen(QColor(p.ok), 3))
                maler.setBrush(Qt.NoBrush)
                maler.drawEllipse(q, r + RING_ABSTAND_PX, r + RING_ABSTAND_PX)
        maler.setBrush(Qt.NoBrush)

    def _zeichne_spot(self, maler, spot):
        if not spot:
            return
        p = self._palette
        q = self.welt_zu_schirm(spot["x"], spot["y"])
        w = math.radians(float(spot.get("gier_grad") or 0.0))
        # Ein Pfeil in Blickrichtung, gut 1 m lang wie Spot, aber nie kleiner als lesbar.
        laenge = max(14.0, 0.55 * self.px_je_m)
        breite = laenge * 0.5

        def punkt(vor, links):
            return QPointF(q.x() + math.cos(w) * vor - math.sin(w) * links,
                           q.y() - (math.sin(w) * vor + math.cos(w) * links))

        maler.setPen(QPen(QColor(p.text), 1))
        maler.setBrush(QColor(p.ok))
        maler.drawPolygon(QPolygonF([punkt(laenge, 0), punkt(-laenge * 0.6, breite),
                                     punkt(-laenge * 0.3, 0), punkt(-laenge * 0.6, -breite)]))
        maler.setBrush(Qt.NoBrush)

    # ------------------------------------------------------------ Maus

    def mousePressEvent(self, ereignis):
        if ereignis.button() == Qt.LeftButton:
            self._druck = ereignis.position()
            self._gezogen = False
            self._mitte_beim_druck = self._mitte
        super().mousePressEvent(ereignis)

    def mouseMoveEvent(self, ereignis):
        if self._druck is not None:
            d = ereignis.position() - self._druck
            if not self._gezogen and abs(d.x()) + abs(d.y()) > ZIEHEN_AB_PX:
                self._gezogen = True
                self.folgt = False
            if self._gezogen:
                mx, my = self._mitte_beim_druck
                self._mitte = (mx - d.x() / self.px_je_m, my + d.y() / self.px_je_m)
                self.update()
        super().mouseMoveEvent(ereignis)

    def mouseReleaseEvent(self, ereignis):
        if ereignis.button() == Qt.LeftButton and self._druck is not None:
            if not self._gezogen:
                x, y = self.schirm_zu_welt(ereignis.position().x(), ereignis.position().y())
                self.klick.emit(x, y)
            self._druck = None
        super().mouseReleaseEvent(ereignis)

    def wheelEvent(self, ereignis):
        rasten = ereignis.angleDelta().y() / 120.0
        if not rasten:
            return
        zeiger = ereignis.position()
        vorher = self.schirm_zu_welt(zeiger.x(), zeiger.y())
        self.px_je_m = min(MASSSTAB_GRENZEN[1],
                           max(MASSSTAB_GRENZEN[0], self.px_je_m * ZOOM_JE_RAST ** rasten))
        nachher = self.schirm_zu_welt(zeiger.x(), zeiger.y())
        self._mitte = (self._mitte[0] + vorher[0] - nachher[0],
                       self._mitte[1] + vorher[1] - nachher[1])
        self.update()
        ereignis.accept()


def _indexbild(daten):
    """Ein PNG mit Palette als Indexbild — oder None, wenn es (noch) nicht lesbar ist."""
    bild = QImage()
    if not bild.loadFromData(bytes(daten)):
        return None
    if bild.format() != QImage.Format_Indexed8:
        bild = bild.convertToFormat(QImage.Format_Indexed8)
    return bild
