"""Das Ladebild: Spot im Trab, solange die Oberfläche im Hintergrund lädt.

Gezeichnet im Stil des Symbols (`spotlab.png`): dunkles Marineblau, weisse
runde Linien, ein blaues Licht am Kopf. Immer dunkel, unabhängig vom Thema --
es ist das Markenbild, nicht ein Teil der Oberfläche.

Der Gang ist ein echter Trab: diagonale Beinpaare im Takt, jeder Fuss steht
etwas länger, als er schwingt, und ein stehender Fuss wandert genau so schnell
nach hinten wie der Boden unter ihm (`test_ein_stehender_fuss_ruht_auf_dem_
mitlaufenden_boden`). Die Knie zeigen nach hinten, wie bei Spot.

Nur PySide6 und nichts Schweres: dieses Modul wird geladen, BEVOR der Rest
der Oberfläche da ist.
"""

import math
import re
from dataclasses import dataclass

from PySide6.QtCore import QElapsedTimer, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

# Farben des Symbols, nicht der Palette: das Ladebild ist immer dunkel.
HINTERGRUND_OBEN = "#1b2130"
HINTERGRUND_UNTEN = "#10141c"
RAND = "#2b3242"
LINIE = "#eef1f6"
LINIE_FERN = "#687287"
LICHT = "#4f6bff"
TEXT = "#eef1f6"
GEDAEMPFT = "#8a93a6"


@dataclass(frozen=True)
class Gang:
    """Masse in Pixeln, Zeit in Sekunden. x nach vorn, y nach UNTEN (Bildschirm)."""

    oberschenkel: float = 44.0
    unterschenkel: float = 46.0
    huefthoehe: float = 76.0      # Hüfte über dem Boden
    schritt: float = 42.0         # Fussweg relativ zur Hüfte je Standphase
    hub: float = 13.0             # wie hoch der schwingende Fuss kommt
    periode: float = 0.72         # ein ganzer Doppelschritt
    stand: float = 0.56           # Anteil der Periode, in dem ein Fuss steht
    huefte_x: float = 60.0        # Hüften vorn und hinten, ab Körpermitte

    def bodentempo(self):
        """So schnell läuft der Boden nach hinten -- gleich schnell wie ein stehender Fuss."""
        return self.schritt / (self.stand * self.periode)


GANG = Gang()

# (Name, Hüfte vorn/hinten, Phasenversatz, nah). Trab: vorne-nah mit hinten-fern.
BEINE = (
    ("vorne_nah", +1, 0.0, True),
    ("hinten_fern", -1, 0.0, False),
    ("vorne_fern", +1, 0.5, False),
    ("hinten_nah", -1, 0.5, True),
)


@dataclass(frozen=True)
class Bein:
    name: str
    nah: bool
    steht: bool
    huefte: tuple
    knie: tuple
    fuss: tuple


def _fuss(phase, g):
    """Fuss relativ zur Hüfte: in der Standphase am Boden nach hinten, sonst im Bogen vor."""
    if phase < g.stand:
        s = phase / g.stand
        return g.schritt / 2 - g.schritt * s, g.huefthoehe, True
    s = (phase - g.stand) / (1.0 - g.stand)
    x = -g.schritt / 2 + g.schritt * (0.5 - 0.5 * math.cos(math.pi * s))
    return x, g.huefthoehe - g.hub * math.sin(math.pi * s), False


def _knie(huefte, fuss, g):
    """Zweigelenk-Kinematik; von den zwei Lösungen die mit dem Knie HINTEN."""
    hx, hy = huefte
    dx, dy = fuss[0] - hx, fuss[1] - hy
    d = max(1e-6, min(math.hypot(dx, dy), g.oberschenkel + g.unterschenkel - 1e-6))
    a = (g.oberschenkel ** 2 - g.unterschenkel ** 2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, g.oberschenkel ** 2 - a * a))
    mx, my = hx + a * dx / d, hy + a * dy / d
    # Senkrechte auf Huefte->Fuss; das Vorzeichen waehlt die Seite hinter der Linie.
    return mx - h * dy / d, my + h * dx / d


def wippen(t, g=GANG):
    """Der Körper hebt und senkt sich zweimal je Periode -- zweimal setzen zwei Füsse auf."""
    return 1.6 * math.sin(4 * math.pi * t / g.periode)


def beine(t, g=GANG):
    """Die vier Beine zur Zeit t, relativ zur RUHENDEN Körpermitte (y = 0).

    Die Hüften wippen mit dem Körper, die Füsse stehen auf dem Boden
    (y = huefthoehe); das Knie gleicht aus, die Beinlängen bleiben.
    """
    ergebnis = []
    for name, seite, versatz, nah in BEINE:
        phase = ((t / g.periode) + versatz) % 1.0
        fx, fy, steht = _fuss(phase, g)
        huefte = (seite * g.huefte_x, wippen(t, g))
        fuss = (huefte[0] + fx, fy)
        ergebnis.append(Bein(name, nah, steht, huefte, _knie(huefte, fuss, g), fuss))
    return ergebnis


def fassung_lesbar(version):
    """`0.2.0b3` -> („0.2.0 · Beta 3“, True). PEP 440 ist für Menschen schwer zu lesen."""
    treffer = re.fullmatch(r"(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?", version or "")
    if treffer is None:
        return version or "", False
    basis, art, nummer = treffer.groups()
    if art is None:
        return basis, False
    name = {"a": "Alpha", "b": "Beta", "rc": "Vorabversion"}[art]
    return f"{basis} · {name} {nummer}", True


class Ladebild(QWidget):
    """Rahmenloses Fenster mit dem trabenden Spot, Name, Fassung und Status."""

    BREITE, HOEHE = 520, 330
    MASSSTAB = 1.2          # Spot ist in Gang-Pixeln gebaut und wird so vergrössert
    SPOT_Y = 112            # Körpermitte im Fenster

    def __init__(self, version="", parent=None):
        super().__init__(parent, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.BREITE, self.HOEHE)
        self._version = version
        self._status = "Starte …"
        self._t = 0.0
        self._uhr = QElapsedTimer()
        self._takt = QTimer(self)
        self._takt.setInterval(16)
        self._takt.timeout.connect(self._weiter)
        self._ausblenden = None

    # ------------------------------------------------------------ Steuerung

    def zeige(self):
        bildschirm = QApplication.primaryScreen()
        if bildschirm is not None:
            mitte = bildschirm.availableGeometry().center()
            self.move(mitte.x() - self.width() // 2, mitte.y() - self.height() // 2)
        self._uhr.start()
        self._takt.start()
        self.show()
        self.raise_()

    def melde(self, text):
        self._status = text
        self.update()

    def status(self):
        return self._status

    def setze_zeit(self, t):
        """Für Tests und Standbilder: die Animation auf eine feste Zeit stellen."""
        self._t = t
        self.update()

    def ausblenden(self, dauer_ms=220):
        """Sanft ausblenden und schliessen. Ohne Fensterdeckkraft (Offscreen) sofort."""
        self._takt.stop()
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(dauer_ms)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.finished.connect(self.close)
        self._ausblenden = animation
        animation.start()

    def closeEvent(self, ereignis):
        self._takt.stop()
        super().closeEvent(ereignis)

    def _weiter(self):
        self._t = self._uhr.elapsed() / 1000.0
        self.update()

    # ------------------------------------------------------------ Zeichnen

    def paintEvent(self, _ereignis):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        self._zeichne_karte(p)
        p.save()
        p.translate(self.width() / 2, self.SPOT_Y)
        p.scale(self.MASSSTAB, self.MASSSTAB)
        self._zeichne_spot(p, QPointF(0, 0))
        p.restore()
        self._zeichne_text(p)
        p.end()

    def _zeichne_karte(self, p):
        karte = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        verlauf = QLinearGradient(karte.topLeft(), karte.bottomLeft())
        verlauf.setColorAt(0.0, QColor(HINTERGRUND_OBEN))
        verlauf.setColorAt(1.0, QColor(HINTERGRUND_UNTEN))
        p.setPen(QPen(QColor(RAND), 1))
        p.setBrush(QBrush(verlauf))
        p.drawRoundedRect(karte, 18, 18)

    def _zeichne_spot(self, p, mitte, g=GANG):
        koerper = QPointF(mitte.x(), mitte.y() + wippen(self._t, g))
        boden_y = mitte.y() + g.huefthoehe

        self._zeichne_boden(p, mitte.x(), boden_y, g)
        schatten = QRadialGradient(QPointF(mitte.x(), boden_y + 2), 120)
        schatten.setColorAt(0.0, QColor(0, 0, 0, 110))
        schatten.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(schatten))
        p.drawEllipse(QPointF(mitte.x(), boden_y + 2), 120, 10)

        alle = beine(self._t, g)
        # Die fernen Beine zuerst, leicht versetzt und blass: so entsteht Tiefe.
        for bein in (b for b in alle if not b.nah):
            self._zeichne_bein(p, mitte, bein, QColor(LINIE_FERN), versatz=QPointF(8, -3))
        self._zeichne_koerper(p, koerper)
        for bein in (b for b in alle if b.nah):
            self._zeichne_bein(p, mitte, bein, QColor(LINIE))

    def _zeichne_boden(self, p, mitte_x, boden_y, g):
        strich, luecke, breite = 16.0, 12.0, 180.0
        takt = strich + luecke
        verschoben = (self._t * g.bodentempo()) % takt
        x = -breite - verschoben
        while x < breite:
            a, b = max(x, -breite), min(x + strich, breite)
            if b > a:
                sichtbar = 1.0 - (abs((a + b) / 2) / breite) ** 2
                farbe = QColor(LINIE_FERN)
                farbe.setAlphaF(max(0.0, 0.85 * sichtbar))
                p.setPen(QPen(farbe, 3, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(mitte_x + a, boden_y + 6), QPointF(mitte_x + b, boden_y + 6))
            x += takt

    def _zeichne_bein(self, p, mitte, bein, farbe, versatz=QPointF(0, 0)):
        def punkt(xy):
            return QPointF(mitte.x() + xy[0], mitte.y() + xy[1]) + versatz

        pfad = QPainterPath(punkt(bein.huefte))
        pfad.lineTo(punkt(bein.knie))
        pfad.lineTo(punkt(bein.fuss))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(farbe, 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(pfad)

    def _zeichne_koerper(self, p, k):
        x, y = k.x(), k.y()
        rumpf = QPainterPath()
        # Silhouette nach dem Symbol: flacher Rücken, Schulterbuckel, Kopf vorn.
        rumpf.moveTo(x - 82, y + 10)
        rumpf.lineTo(x - 82, y - 12)
        rumpf.lineTo(x - 20, y - 12)
        rumpf.lineTo(x + 6, y - 24)
        rumpf.lineTo(x + 84, y - 24)
        rumpf.lineTo(x + 84, y - 4)
        rumpf.lineTo(x + 62, y + 10)
        rumpf.closeSubpath()
        p.setBrush(QColor(HINTERGRUND_OBEN))
        p.setPen(QPen(QColor(LINIE), 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(rumpf)

        # Das blaue Licht vorn am Kopf, mit einem Hauch Leuchten.
        licht = QRectF(x + 92, y - 26, 11, 20)
        schein = QRadialGradient(licht.center(), 22)
        schein.setColorAt(0.0, QColor(79, 107, 255, 120))
        schein.setColorAt(1.0, QColor(79, 107, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(schein))
        p.drawEllipse(licht.center(), 22, 22)
        p.setBrush(QColor(LICHT))
        p.drawRoundedRect(licht, 4, 4)

    def _zeichne_text(self, p):
        breite = self.width()
        titel = QFont(self.font())
        titel.setPointSizeF(24)
        titel.setWeight(QFont.DemiBold)
        titel.setLetterSpacing(QFont.PercentageSpacing, 102)
        p.setFont(titel)
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(0, 226, breite, 36), Qt.AlignHCenter | Qt.AlignVCenter, "spotlab")

        lesbar, vorab = fassung_lesbar(self._version)
        klein = QFont(self.font())
        klein.setPointSizeF(9.5)
        p.setFont(klein)
        p.setPen(QColor(GEDAEMPFT))
        zeile = f"Fassung {lesbar}" if lesbar else ""
        p.drawText(QRectF(0, 262, breite, 18), Qt.AlignHCenter | Qt.AlignVCenter, zeile)
        p.drawText(QRectF(0, 283, breite, 18), Qt.AlignHCenter | Qt.AlignVCenter, self._status)

        if vorab:
            schild = QFont(self.font())
            schild.setPointSizeF(7.5)
            schild.setWeight(QFont.Bold)
            schild.setLetterSpacing(QFont.PercentageSpacing, 112)
            p.setFont(schild)
            rahmen = QRectF(breite - 68, 16, 50, 20)
            p.setPen(QPen(QColor(LICHT), 1.2))
            p.setBrush(QColor(79, 107, 255, 38))
            p.drawRoundedRect(rahmen, 10, 10)
            p.setPen(QColor("#aab8ff"))
            p.drawText(rahmen, Qt.AlignCenter, "BETA" if "Beta" in lesbar else "VORAB")

        # Schmaler, unbestimmter Fortschrittsbalken: ein Lichtstreifen läuft durch.
        bahn = QRectF(breite / 2 - 80, 311, 160, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(RAND))
        p.drawRoundedRect(bahn, 1.5, 1.5)
        lauf = (self._t / 1.3) % 1.0
        start = bahn.left() - 50 + (bahn.width() + 50) * lauf
        streifen = QRectF(max(bahn.left(), start), bahn.top(),
                          min(bahn.right(), start + 50) - max(bahn.left(), start), bahn.height())
        if streifen.width() > 0:
            p.setBrush(QColor(LICHT))
            p.drawRoundedRect(streifen, 1.5, 1.5)
