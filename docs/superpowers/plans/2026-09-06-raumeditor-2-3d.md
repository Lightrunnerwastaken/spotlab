# Raumeditor Etappe 2 „3D-Sicht" — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der Raumeditor bekommt eine 3D-Sicht (OpenGL 3.3 Core über `QOpenGLWidget` + PyOpenGL) mit Orbit-Kamera, Farb-ID-Auswahl, denselben Tasten wie in 2D und einem Rückfall auf 2D, wenn kein Kontext zustande kommt.

**Architecture:** Die Geometrie (Kästen aus Wänden/Blöcken/Tags/Spot, Bodenraster, Punkte, Spur) und die Kamera-Mathematik liegen in `gui/raumeditor/geometrie3d.py` — ohne GL, mit `QMatrix4x4`/`QVector3D`, testbar unter `offscreen`. `sicht3d.py` ist die dünne GL-Haut: Shader, Puffer, Zeichnen, Farb-ID-Puffer, Ereignisse in Metern (Mausstrahl ∩ Boden). Der Tab schaltet über ein `QStackedWidget` zwischen 2D und 3D um; beide Sichten sprechen dieselbe `Steuerung`.

**Tech Stack:** PySide6 (`QtOpenGLWidgets`, `QtOpenGL`, `QtGui`), PyOpenGL >= 3.1 (nur in `sicht3d.py`, verzögert importiert), `array`/`struct` für Vertexdaten (kein numpy unter `gui/`).

**Spec:** `docs/superpowers/specs/2026-09-06-raumeditor-design.md` (Abschnitt 4, 7, 8)

## Global Constraints

- Kein `bosdyn`, `spotlab.backends`, `mujoco`, `spotsim`, `numpy` unter `gui/`; `OpenGL` nur in `gui/raumeditor/sicht3d.py`, importiert erst beim Erzeugen der Sicht.
- Farben nur aus `gui/theme.py` (die Shader bekommen sie als Uniforms aus der Palette).
- Kein schwarzes Fenster: scheitert der Kontext (Version < 3.3, PyOpenGL fehlt, Shader kompiliert nicht), zeigt der Tab die Tafel und der Umschalter bleibt grau.
- Gemessen auf dem Rechner des Autors (06.09.2026): OpenGL 3.3.0 Core, Intel Iris Xe, 4 Samples — unter `QT_QPA_PLATFORM=offscreen` KEIN Kontext. Tests, die rendern, laufen nur mit Kontext (`skip` mit Grund); der Rückfall wird unter `offscreen` geprüft.
- Kommandos aus `D:\Users\janis\Documents\Matura\spotlab`; Python `C:\Users\janis\miniconda3\python.exe`; Commit-Trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, Meldungen über `-F`.

---

## Dateiplan

| Datei | Aufgabe |
|---|---|
| `src/spotlab/gui/raumeditor/geometrie3d.py` | `kasten(...)`, `kaesten_aus_raum(raum, auswahl)`, `bodenraster(huelle)`, `Kamera` (Orbit, Matrizen, Strahl, Bodenschnitt), Farb-IDs |
| `src/spotlab/gui/raumeditor/sicht3d.py` | `Sicht3D(QOpenGLWidget)`: Shader, Puffer, Zeichnen, Farb-ID-Puffer, Ereignisse; `verfuegbar`, `grund` |
| `src/spotlab/gui/raumeditor/tab.py` | `QStackedWidget` 2D/3D, Umschalter, `Tab`, beide Sichten an die Steuerung |
| `pyproject.toml` | `PyOpenGL>=3.1,<4` im Extra `gui` |
| `tests/test_gui_raumeditor_geometrie3d.py`, `tests/test_gui_raumeditor_sicht3d.py`, `tests/test_gui_raumeditor.py` | Tests |
| `README.md`, `CLAUDE.md` | Doku und Regel „PyOpenGL nur in sicht3d.py" |

---

### Task 1: `geometrie3d.py` — Kästen, Raster, Kamera, Farb-IDs (ohne GL)

**Files:**
- Create: `src/spotlab/gui/raumeditor/geometrie3d.py`
- Test: `tests/test_gui_raumeditor_geometrie3d.py`

**Interfaces:**
- Produces:
  - `kasten(x, y, z, hx, hy, hz, yaw_grad) -> list[float]`: 36 Vertices × (px, py, pz, nx, ny, nz) = 216 Zahlen, gedreht um die Hochachse, Mitte (x, y, z).
  - `kaesten_aus_raum(raum, auswahl) -> list[(schluessel, floats)]`: je Wand ein Kasten (`wand_hoehe`, `wand_dicke`), je Block ein Kasten, je Tag eine Tafel 0.15 × 0.02 × 0.15 auf `hoehe` mit Blick, Spot als Kasten 1.1 × 0.5 × 0.2 mit Oberkante 0.6 m am Start (`("start",)`).
  - `bodenraster(huelle, schritt=1.0) -> list[float]`: Linienpaare (x, y, z) am Boden.
  - `spot_pfeil(start) -> list[float]`: Linie vom Start in Blickrichtung (0.6 m, 0.3 m hoch).
  - `Kamera(ziel=(0, 0, 0), abstand=8.0, azimut=45.0, elevation=35.0)` mit `orbit(d_azimut, d_elevation)`, `zoom(faktor)`, `schwenke(dx_m, dy_m)`, `rahme(huelle)`, `ansicht() -> QMatrix4x4`, `projektion(breite, hoehe) -> QMatrix4x4`, `strahl(px, py, breite, hoehe) -> (QVector3D ursprung, QVector3D richtung)`, `bodenpunkt(px, py, breite, hoehe) -> (x, y) | None`, `auge() -> QVector3D`. Elevation 5°–89°, Abstand 1–60 m, Perspektive 50° vertikal.
  - `farbe_fuer(index) -> (r, g, b)` (0..1) und `index_aus(r, g, b) -> int` (24-Bit-Index aus 8-Bit-Kanälen); Index 0 = nichts.

- [ ] **Step 1: Tests**

```python
"""Geometrie und Kamera der 3D-Sicht -- ohne GL, unter offscreen testbar."""
import math

import pytest

pytest.importorskip("PySide6.QtGui")

from spotlab.gui.raumeditor import geometrie3d as g  # noqa: E402
from spotlab.welt.raum import Block, Raum, RaumTag, huelle  # noqa: E402


def test_ein_kasten_hat_36_vertices_mit_normalen_und_dreht_sich():
    daten = g.kasten(1.0, 2.0, 0.5, 1.0, 0.25, 0.5, yaw_grad=90.0)
    assert len(daten) == 36 * 6
    xs = daten[0::6]
    ys = daten[1::6]
    zs = daten[2::6]
    # 2 m lang entlang der eigenen x-Achse, die nach +y zeigt: y spannt 1..3, x nur 0.75..1.25
    assert min(ys) == pytest.approx(1.0) and max(ys) == pytest.approx(3.0)
    assert min(xs) == pytest.approx(0.75) and max(xs) == pytest.approx(1.25)
    assert min(zs) == pytest.approx(0.0) and max(zs) == pytest.approx(1.0)
    normalen = {tuple(round(v, 6) for v in daten[i + 3:i + 6]) for i in range(0, len(daten), 6)}
    assert len(normalen) == 6                       # sechs Flaechen, sechs Richtungen
    assert all(abs(math.hypot(*n) - 1.0) < 1e-6 for n in normalen)


def test_kaesten_aus_raum_nennen_ihre_schluessel():
    raum = Raum(name="T", beschreibung="", start=(1.0, 1.0, 0.0),
                waende=((0, 0, 4, 0),), bloecke=(Block("K", 2, 2, 1, 1),),
                tags=(RaumTag(1, 3, 3, 90.0),))
    kaesten = g.kaesten_aus_raum(raum, frozenset())
    schluessel = [s for s, _ in kaesten]
    assert schluessel == [("wand", 0), ("block", 0), ("tag", 0), ("start",)]
    wand = dict(kaesten)[("wand", 0)]
    assert max(wand[2::6]) == pytest.approx(raum.wand_hoehe)
    spot = dict(kaesten)[("start",)]
    assert max(spot[2::6]) == pytest.approx(0.6) and min(spot[2::6]) == pytest.approx(0.4)


def test_bodenraster_und_pfeil():
    linien = g.bodenraster((0.0, 0.0, 2.0, 1.0), schritt=1.0)
    assert len(linien) % 6 == 0
    assert len(linien) // 6 == 3 + 2                 # x = 0, 1, 2 und y = 0, 1
    pfeil = g.spot_pfeil((1.0, 1.0, 90.0))
    assert pfeil[:3] == [1.0, 1.0, 0.3] and pfeil[4] == pytest.approx(1.6)


def test_kamera_schaut_auf_das_ziel_und_rahmt_den_raum():
    kamera = g.Kamera()
    kamera.rahme((0.0, 0.0, 6.0, 4.0))
    assert kamera.ziel == (3.0, 2.0, 0.0)
    auge = kamera.auge()
    assert auge.z() > 0 and kamera.abstand > 6.0
    sicht = kamera.ansicht()
    mitte = sicht.map(g.QVector3D(3.0, 2.0, 0.0))
    assert abs(mitte.x()) < 1e-6 and abs(mitte.y()) < 1e-6 and mitte.z() < 0   # vor der Kamera, mittig
    kamera.orbit(10.0, 200.0)
    assert kamera.elevation == 89.0                   # Deckel
    kamera.zoom(0.001)
    assert kamera.abstand == 1.0


def test_der_mausstrahl_durch_die_bildmitte_trifft_das_ziel():
    kamera = g.Kamera(ziel=(3.0, 2.0, 0.0), abstand=8.0, azimut=30.0, elevation=40.0)
    punkt = kamera.bodenpunkt(400, 300, 800, 600)
    assert punkt == (pytest.approx(3.0, abs=1e-3), pytest.approx(2.0, abs=1e-3))
    kamera.schwenke(1.0, 0.0)
    assert kamera.ziel[0] != 3.0 or kamera.ziel[1] != 2.0


def test_farb_ids_sind_umkehrbar():
    for index in (1, 2, 255, 256, 65537):
        r, gg, b = g.farbe_fuer(index)
        assert g.index_aus(round(r * 255), round(gg * 255), round(b * 255)) == index
    assert g.index_aus(0, 0, 0) == 0
```

- [ ] **Step 2: Rot** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumeditor_geometrie3d.py`

- [ ] **Step 3: `geometrie3d.py`**

```python
"""Geometrie und Kamera der 3D-Sicht -- ohne GL.

Kaesten aus Waenden, Bloecken, Tags und dem Spot am Start, das Bodenraster,
die Orbit-Kamera mit Matrizen und Mausstrahl. Alles mit `QMatrix4x4`/`QVector3D`
aus Qt, kein numpy (Regel fuer gui/), und deshalb unter `offscreen` testbar --
`sicht3d.py` ist nur noch die GL-Haut darum.
"""

import math

from PySide6.QtGui import QMatrix4x4, QVector3D

from spotlab.welt.raum import huelle

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
        n = (nx, ny, normale[2])
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
        sx, sy, SPOT_OBEN - SPOT_HOEHE / 2, SPOT_LAENGE / 2, SPOT_BREITE / 2, SPOT_HOEHE / 2, sgrad)))
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
    return [x, y, 0.3, x + 0.6 * math.cos(math.radians(grad)), y + 0.6 * math.sin(math.radians(grad)), 0.3]


def farbe_fuer(index):
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
        self.abstand = max(1.0, min(60.0, spanne / (2.0 * math.tan(math.radians(FOV_GRAD) / 2)) * 1.3))

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
        inv = (self.projektion(breite, hoehe) * self.ansicht()).inverted()[0]
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


__all__ = ["Kamera", "QVector3D", "bodenraster", "farbe_fuer", "huelle", "index_aus",
           "kaesten_aus_raum", "kasten", "spot_pfeil"]
```

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumeditor_geometrie3d.py tests/test_gui_raumeditor.py` (der Import-Grenz-Test erlaubt kein numpy — bleibt grün).
- [ ] **Step 5: Commit** — `feat(raumeditor): Geometrie und Kamera der 3D-Sicht -- ohne GL, unter offscreen testbar`

---

### Task 2: `sicht3d.py` — die GL-Haut mit Rückfall

**Files:**
- Create: `src/spotlab/gui/raumeditor/sicht3d.py`
- Modify: `pyproject.toml:35-38` (`"PyOpenGL>=3.1,<4"` ins Extra `gui`), `tests/test_gui_raumeditor.py::test_der_editor_importiert_nichts_verbotenes` (OpenGL nur in `sicht3d.py`, dort nur innerhalb von Funktionen)
- Test: `tests/test_gui_raumeditor_sicht3d.py`

**Interfaces:**
- Produces: `Sicht3D(palette)` (`QOpenGLWidget`) mit denselben Signalen wie `Sicht2D` (`gedrueckt`, `bewegt`, `losgelassen`, `taste_gedrueckt`), Methoden `zeige(raum, auswahl=frozenset(), griffe=(), rahmen=None, kette=None)`, `setze_spur`, `setze_anstoesse`, `setze_pauspapier`, `alles_zeigen`, `toleranz_m()` (0.12), Attribute `verfuegbar: bool | None` (None bis zum ersten `initializeGL`), `grund: str`, `kamera`, `tafel` (QLabel-Text des Rückfalls), Signal `bereit(bool)` nach `initializeGL`. `bodenpunkt(px, py)`, `treffer(px, py) -> schluessel | None` (Farb-ID), `bild() -> QImage` (`grabFramebuffer`).

- [ ] **Step 1: Tests**

```python
"""Die 3D-Sicht: GL-Haut mit Rueckfall. Rendern nur mit Kontext."""
import ast
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtOpenGLWidgets")

from PySide6.QtGui import QOpenGLContext, QSurfaceFormat  # noqa: E402

from spotlab.gui.raumeditor.sicht3d import Sicht3D, gl_verfuegbar  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import Block, Raum  # noqa: E402

RAUM = Raum(name="T", beschreibung="", start=(1, 1, 0), waende=((0, 0, 4, 0),),
            bloecke=(Block("K", 2, 2, 1, 1, drehung=30.0),))


def _kontext_da():
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    ctx = QOpenGLContext()
    ctx.setFormat(fmt)
    return ctx.create() and ctx.format().majorVersion() >= 3


def test_opengl_wird_nur_in_sicht3d_und_erst_beim_zeigen_importiert():
    wurzel = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "gui" / "raumeditor"
    for datei in wurzel.glob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        oben = [k for k in baum.body if isinstance(k, (ast.Import, ast.ImportFrom))]
        namen = set()
        for k in oben:
            namen.update([a.name for a in k.names] if isinstance(k, ast.Import) else [k.module or ""])
        assert not any(n.startswith("OpenGL") for n in namen), f"{datei.name} importiert OpenGL auf Modulebene"


def test_ohne_kontext_gibt_es_eine_tafel_und_keinen_absturz(qapp):
    sicht = Sicht3D(DUNKEL)
    sicht.zeige(RAUM)
    sicht.resize(320, 240)
    sicht.show()
    qapp.processEvents()
    if sicht.verfuegbar:
        pytest.skip("hier gibt es einen GL-Kontext -- der Rueckfall ist nicht zu pruefen")
    assert sicht.verfuegbar is False
    assert "3D" in sicht.tafel and "QT_OPENGL" in sicht.tafel
    assert sicht.grund


@pytest.mark.skipif(not gl_verfuegbar(), reason="kein OpenGL-3.3-Kontext (offscreen?)")
def test_mit_kontext_rendert_die_sicht_den_raum(qapp):
    sicht = Sicht3D(DUNKEL)
    sicht.zeige(RAUM, auswahl=frozenset({("block", 0)}))
    sicht.resize(320, 240)
    sicht.show()
    qapp.processEvents()
    sicht.alles_zeigen()
    bild = sicht.bild()
    mitte = bild.pixel(160, 120)
    assert bild.width() == 320 and mitte != bild.pixel(1, 1)
    assert sicht.treffer(160, 120) in (("block", 0), ("wand", 0), ("start",), None)
    x, y = sicht.bodenpunkt(160, 120)
    assert abs(x - 2.0) < 1.0 and abs(y - 1.0) < 1.5
```

- [ ] **Step 2: Rot**

- [ ] **Step 3: `sicht3d.py`**

```python
"""Die 3D-Sicht des Raumeditors: OpenGL 3.3 Core ueber QOpenGLWidget + PyOpenGL.

Die Geometrie und die Kamera kommen aus `geometrie3d.py`; hier gibt es nur
Shader, Puffer, Zeichnen und den Farb-ID-Puffer fuer die Auswahl. PyOpenGL wird
ERST hier und erst beim Erzeugen der Sicht importiert -- fehlt es, oder kommt
kein 3.3-Kontext zustande, zeigt die Sicht eine Tafel mit dem Grund. Kein
schwarzes Fenster.

Ereignisse gehen wie in 2D in METERN an die Steuerung: der Mausstrahl wird
mit der Bodenebene geschnitten.
"""

import ctypes
from array import array

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor, QOpenGLContext, QPainter, QSurfaceFormat, QVector3D,
)
from PySide6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from spotlab.gui.raumeditor import geometrie3d as geo
from spotlab.gui.raumeditor.sicht2d import TASTEN
from spotlab.welt.raum import huelle

TOLERANZ_M = 0.12
MINDESTVERSION = (3, 3)
TAFEL = ("3D-Sicht nicht verfügbar: {grund}\n\n"
         "Der Editor bleibt in 2D. Auf Rechnern ohne OpenGL 3.3 hilft oft "
         "QT_OPENGL=software setzen, dann spotlab neu starten.")

VERTEX = """
#version 330 core
layout(location = 0) in vec3 pos;
layout(location = 1) in vec3 normal;
uniform mat4 mvp;
out vec3 n;
void main() { gl_Position = mvp * vec4(pos, 1.0); n = normal; }
"""
FRAGMENT = """
#version 330 core
in vec3 n;
uniform vec3 farbe;
uniform vec3 licht;
uniform float flach;      // 1.0: keine Beleuchtung (Farb-IDs, Linien)
out vec4 aus;
void main() {
    float l = mix(0.55 + 0.45 * max(dot(normalize(n), normalize(licht)), 0.0), 1.0, flach);
    aus = vec4(farbe * l, 1.0);
}
"""


def gl_verfuegbar():
    """Kommt auf diesem Rechner ein 3.3-Core-Kontext zustande?"""
    try:
        import OpenGL  # noqa: F401
    except ImportError:
        return False
    fmt = QSurfaceFormat()
    fmt.setVersion(*MINDESTVERSION)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    ctx = QOpenGLContext()
    ctx.setFormat(fmt)
    return bool(ctx.create()) and (ctx.format().majorVersion(), ctx.format().minorVersion()) >= MINDESTVERSION


def _farbe(hexwert):
    c = QColor(hexwert)
    return (c.redF(), c.greenF(), c.blueF())


class Sicht3D(QOpenGLWidget):
    gedrueckt = Signal(float, float, str, bool, bool)
    bewegt = Signal(float, float, bool)
    losgelassen = Signal(float, float, bool, bool)
    taste_gedrueckt = Signal(str, bool, bool, bool)
    bereit = Signal(bool)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setVersion(*MINDESTVERSION)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setSamples(4)
        fmt.setDepthBufferSize(24)
        self.setFormat(fmt)
        self._p = palette
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self.kamera = geo.Kamera()
        self.verfuegbar = None
        self.grund = ""
        self.tafel = ""
        self._raum = None
        self._auswahl = frozenset()
        self._spur = []
        self._anstoesse = []
        self._pauspapier = []
        self._kaesten = []          # [(schluessel, vertices)]
        self._gl = None             # das OpenGL.GL-Modul, sobald es da ist
        self._programm = None
        self._vao = None
        self._vbo = None
        self._puffer_dirty = True
        self._geometrie = []        # [(schluessel, anfang, anzahl)] im VBO
        self._linien = []           # [(farbe, anfang, anzahl, GL_LINES/GL_POINTS)]
        self._letzte_maus = None
        self._taste = None

    # ------------------------------------------------------------ Fuellen

    def zeige(self, raum, auswahl=frozenset(), griffe=(), rahmen=None, kette=None):
        self._raum, self._auswahl = raum, frozenset(auswahl)
        self._puffer_dirty = True
        self.update()

    def setze_spur(self, punkte):
        self._spur = list(punkte)
        self._puffer_dirty = True
        self.update()

    def setze_anstoesse(self, punkte):
        self._anstoesse = list(punkte)
        self._puffer_dirty = True
        self.update()

    def setze_pauspapier(self, punkte):
        self._pauspapier = list(punkte)
        self._puffer_dirty = True
        self.update()

    def alles_zeigen(self):
        if self._raum is not None:
            self.kamera.rahme(huelle(self._raum))
            self.update()

    def toleranz_m(self):
        return TOLERANZ_M

    # ---------------------------------------------------------------- GL

    def initializeGL(self):
        try:
            from OpenGL import GL
        except ImportError as fehler:
            self._scheitere(f"PyOpenGL fehlt ({fehler}). pip install \"spotlab[gui]\"")
            return
        ctx = self.context()
        if ctx is None or not ctx.isValid():
            self._scheitere("kein OpenGL-Kontext")
            return
        fassung = (ctx.format().majorVersion(), ctx.format().minorVersion())
        if fassung < MINDESTVERSION:
            self._scheitere(f"OpenGL {fassung[0]}.{fassung[1]} — gebraucht wird 3.3")
            return
        self._gl = GL
        programm = QOpenGLShaderProgram(self)
        if (not programm.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX)
                or not programm.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT)
                or not programm.link()):
            self._scheitere(f"Shader: {programm.log().strip()}")
            return
        self._programm = programm
        self._vao = GL.glGenVertexArrays(1)
        self._vbo = GL.glGenBuffers(1)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_MULTISAMPLE)
        self.verfuegbar = True
        self.bereit.emit(True)

    def _scheitere(self, grund):
        self.verfuegbar = False
        self.grund = grund
        self.tafel = TAFEL.format(grund=grund)
        self.bereit.emit(False)

    def _baue_puffer(self):
        """Alle Vertices in EINEN Puffer: Kaesten (mit Normale), dann Linien und Punkte."""
        GL = self._gl
        daten = array("f")
        self._geometrie = []
        self._linien = []
        if self._raum is not None:
            self._kaesten = geo.kaesten_aus_raum(self._raum, self._auswahl)
            for schluessel, vertices in self._kaesten:
                self._geometrie.append((schluessel, len(daten) // 6, len(vertices) // 6))
                daten.extend(vertices)
            raster = geo.bodenraster(huelle(self._raum))
            self._linien.append((self._p.rand, len(daten) // 6, len(raster) // 3, GL.GL_LINES))
            daten.extend(self._mit_normale(raster))
            pfeil = geo.spot_pfeil(self._raum.start)
            self._linien.append((self._p.funktion, len(daten) // 6, 2, GL.GL_LINES))
            daten.extend(self._mit_normale(pfeil))
        if len(self._spur) > 1:
            punkte = []
            for (x1, y1), (x2, y2) in zip(self._spur, self._spur[1:]):
                punkte += [x1, y1, 0.01, x2, y2, 0.01]
            self._linien.append((self._p.akzent, len(daten) // 6, len(punkte) // 3, GL.GL_LINES))
            daten.extend(self._mit_normale(punkte))
        if self._anstoesse:
            punkte = []
            for x, y in self._anstoesse:
                punkte += [x - 0.1, y - 0.1, 0.02, x + 0.1, y + 0.1, 0.02,
                           x - 0.1, y + 0.1, 0.02, x + 0.1, y - 0.1, 0.02]
            self._linien.append((self._p.gefahr, len(daten) // 6, len(punkte) // 3, GL.GL_LINES))
            daten.extend(self._mit_normale(punkte))
        if self._pauspapier:
            punkte = []
            for x, y in self._pauspapier:
                punkte += [x, y, 0.02]
            self._linien.append((self._p.gedaempft, len(daten) // 6, len(punkte) // 3, GL.GL_POINTS))
            daten.extend(self._mit_normale(punkte))
        GL.glBindVertexArray(self._vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self._vbo)
        roh = daten.tobytes()
        GL.glBufferData(GL.GL_ARRAY_BUFFER, len(roh), roh, GL.GL_DYNAMIC_DRAW)
        schritt = 6 * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, schritt, ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 3, GL.GL_FLOAT, GL.GL_FALSE, schritt, ctypes.c_void_p(12))
        GL.glBindVertexArray(0)
        self._puffer_dirty = False

    @staticmethod
    def _mit_normale(xyz):
        aus = []
        for i in range(0, len(xyz), 3):
            aus += [xyz[i], xyz[i + 1], xyz[i + 2], 0.0, 0.0, 1.0]
        return aus

    def _mvp(self):
        return self.kamera.projektion(self.width(), self.height()) * self.kamera.ansicht()

    def _zeichne_szene(self, ids=False):
        GL = self._gl
        if self._puffer_dirty:
            self._baue_puffer()
        p = self._programm
        p.bind()
        p.setUniformValue("mvp", self._mvp())
        p.setUniformValue("licht", QVector3D(0.4, -0.6, 1.0))
        GL.glBindVertexArray(self._vao)
        for i, (schluessel, anfang, anzahl) in enumerate(self._geometrie):
            if ids:
                farbe = geo.farbe_fuer(i + 1)
                p.setUniformValue("flach", 1.0)
            else:
                gewaehlt = schluessel in self._auswahl
                art = schluessel[0]
                farbe = _farbe(self._p.akzent if gewaehlt else
                               self._p.zahl if art == "tag" else
                               self._p.funktion if art == "start" else
                               self._p.text if art == "wand" else self._p.flaeche)
                p.setUniformValue("flach", 0.0)
            p.setUniformValue("farbe", QVector3D(*farbe))
            GL.glDrawArrays(GL.GL_TRIANGLES, anfang, anzahl)
        if not ids:
            p.setUniformValue("flach", 1.0)
            GL.glPointSize(2.0)
            for farbe, anfang, anzahl, art in self._linien:
                p.setUniformValue("farbe", QVector3D(*_farbe(farbe)))
                GL.glDrawArrays(art, anfang, anzahl)
        GL.glBindVertexArray(0)
        p.release()

    def paintGL(self):
        if not self.verfuegbar:
            return
        GL = self._gl
        r, g, b = _farbe(self._p.hintergrund)
        GL.glClearColor(r, g, b, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        self._zeichne_szene()
        # Beschriftungen ueber dem GL-Bild -- Text in GL waere die Arbeit nicht wert.
        if self._raum is not None:
            maler = QPainter(self)
            maler.setPen(QColor(self._p.text))
            mvp = self._mvp()
            for i, block in enumerate(self._raum.bloecke):
                self._beschrifte(maler, mvp, block.x, block.y, block.hoehe + 0.1, block.name)
            for t in self._raum.tags:
                self._beschrifte(maler, mvp, t.x, t.y, t.hoehe + 0.15, str(t.id))
            maler.end()

    def _beschrifte(self, maler, mvp, x, y, z, text):
        p = mvp.map(QVector3D(x, y, z))
        if not (-1.0 <= p.z() <= 1.0):
            return
        maler.drawText(QPointF((p.x() + 1.0) / 2 * self.width(), (1.0 - p.y()) / 2 * self.height()), text)

    def resizeGL(self, breite, hoehe):
        if self.verfuegbar:
            self._gl.glViewport(0, 0, breite, hoehe)

    def paintEvent(self, ereignis):
        if self.verfuegbar is False:
            maler = QPainter(self)
            maler.fillRect(self.rect(), QColor(self._p.hintergrund))
            maler.setPen(QColor(self._p.gedaempft))
            maler.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignCenter | Qt.TextWordWrap, self.tafel)
            return
        super().paintEvent(ereignis)

    # ---------------------------------------------------------- Auswahl

    def treffer(self, px, py):
        """Das Element unter dem Pixel -- ueber einen Farb-ID-Durchgang."""
        if not self.verfuegbar:
            return None
        GL = self._gl
        self.makeCurrent()
        try:
            fbo = QOpenGLFramebufferObject(self.width(), self.height(),
                                           QOpenGLFramebufferObject.CombinedDepthStencil)
            fbo.bind()
            GL.glViewport(0, 0, self.width(), self.height())
            GL.glClearColor(0.0, 0.0, 0.0, 1.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glDisable(GL.GL_MULTISAMPLE)
            self._zeichne_szene(ids=True)
            GL.glEnable(GL.GL_MULTISAMPLE)
            pixel = GL.glReadPixels(int(px), self.height() - int(py) - 1, 1, 1, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
            fbo.release()
        finally:
            self.doneCurrent()
        index = geo.index_aus(pixel[0], pixel[1], pixel[2])
        if 0 < index <= len(self._geometrie):
            return self._geometrie[index - 1][0]
        return None

    def bodenpunkt(self, px, py):
        return self.kamera.bodenpunkt(px, py, self.width(), self.height())

    def bild(self):
        return self.grabFramebuffer()

    # ------------------------------------------------------- Ereignisse

    @staticmethod
    def _tasten(ereignis):
        m = ereignis.modifiers()
        return bool(m & Qt.ShiftModifier), bool(m & Qt.ControlModifier), bool(m & Qt.AltModifier)

    def mousePressEvent(self, ereignis):
        self.setFocus()
        p = ereignis.position()
        self._letzte_maus = (p.x(), p.y())
        self._taste = ereignis.button()
        if ereignis.button() != Qt.LeftButton or not self.verfuegbar:
            return
        shift, ctrl, _alt = self._tasten(ereignis)
        boden = self.bodenpunkt(p.x(), p.y())
        if boden is None:
            return
        self._klick_schluessel = self.treffer(p.x(), p.y())
        self.gedrueckt.emit(boden[0], boden[1], "links", shift, ctrl)

    def mouseMoveEvent(self, ereignis):
        p = ereignis.position()
        if self._letzte_maus is None:
            self._letzte_maus = (p.x(), p.y())
        dx, dy = p.x() - self._letzte_maus[0], p.y() - self._letzte_maus[1]
        self._letzte_maus = (p.x(), p.y())
        knoepfe = ereignis.buttons()
        if knoepfe & Qt.RightButton or knoepfe & Qt.MiddleButton:
            if ereignis.modifiers() & Qt.ShiftModifier or knoepfe & Qt.MiddleButton:
                self.kamera.schwenke(-dx * self.kamera.abstand / 500.0, dy * self.kamera.abstand / 500.0)
            else:
                self.kamera.orbit(-dx * 0.5, dy * 0.5)
            self.update()
            return
        if not self.verfuegbar:
            return
        _shift, ctrl, _alt = self._tasten(ereignis)
        boden = self.bodenpunkt(p.x(), p.y())
        if boden is not None:
            self.bewegt.emit(boden[0], boden[1], ctrl)

    def mouseReleaseEvent(self, ereignis):
        if ereignis.button() != Qt.LeftButton or not self.verfuegbar:
            return
        shift, ctrl, _alt = self._tasten(ereignis)
        p = ereignis.position()
        boden = self.bodenpunkt(p.x(), p.y())
        if boden is not None:
            self.losgelassen.emit(boden[0], boden[1], shift, ctrl)

    def wheelEvent(self, ereignis):
        self.kamera.zoom(1.15 ** (-ereignis.angleDelta().y() / 120.0))
        self.update()

    def keyPressEvent(self, ereignis):
        taste = ereignis.key()
        if taste == Qt.Key_Home:
            self.alles_zeigen()
            return
        shift, ctrl, alt = self._tasten(ereignis)
        if taste in TASTEN:
            name = TASTEN[taste]
        elif Qt.Key_0 <= taste <= Qt.Key_9:
            name = chr(taste)
        elif Qt.Key_A <= taste <= Qt.Key_Z:
            name = chr(taste).lower()
        else:
            super().keyPressEvent(ereignis)
            return
        self.taste_gedrueckt.emit(name, shift, ctrl, alt)
```

**Wichtig — Auswahl in 3D:** Die Steuerung sucht Treffer über `bearbeitung.treffer` in Metern am Bodenpunkt; das reicht für Wände, Tags und den Start. Für Blöcke, die weiter oben angeklickt werden (Deckel), liefert der Bodenpunkt einen Punkt HINTER dem Block. Deshalb übergibt die 3D-Sicht bei `gedrueckt` zusätzlich den Farb-ID-Treffer: der Tab ruft `steuerung.druecke(..., treffer=schluessel)`; `Steuerung.druecke` bekommt den optionalen Parameter `treffer=None` und nimmt ihn statt `b.treffer(...)`, wenn er gesetzt ist (Task 3).

- [ ] **Step 4: pyproject** — `gui = [... "PyOpenGL>=3.1,<4"]` mit Kommentar: „PyOpenGL: die 3D-Sicht des Raumeditors; nur in `gui/raumeditor/sicht3d.py`, verzögert importiert — ohne das Paket läuft der Editor in 2D."

- [ ] **Step 5: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumeditor_sicht3d.py tests/test_gui_raumeditor.py` (offscreen: Rückfall-Test grün, Render-Test übersprungen). Zusätzlich manuell mit Kontext: `python scripts/... ` — ein Probeskript ohne `QT_QPA_PLATFORM=offscreen`, das `Sicht3D` zeigt, `bild().save("sicht3d.png")` schreibt; das Bild ansehen (Read).
- [ ] **Step 6: Commit** — `feat(raumeditor): 3D-Sicht -- OpenGL 3.3 mit Orbit-Kamera, Farb-ID-Auswahl und Rueckfall`

---

### Task 3: Tab mit beiden Sichten, Treffer aus 3D, Doku

**Files:**
- Modify: `src/spotlab/gui/raumeditor/tab.py` (Stapel, Umschalter, `Tab`, `_gedrueckt` mit Treffer), `src/spotlab/gui/raumeditor/steuerung.py::druecke` (`treffer=None`), `README.md`, `CLAUDE.md`
- Test: `tests/test_gui_raumeditor.py`, `tests/test_gui_raumeditor_steuerung.py`

- [ ] **Step 1: Tests**

An `tests/test_gui_raumeditor_steuerung.py`:

```python
def test_ein_uebergebener_treffer_geht_vor_dem_bodenpunkt():
    """Aus 3D: der Farb-ID-Treffer nennt den Block, obwohl der Bodenpunkt dahinter liegt."""
    st = Steuerung(RAUM)
    st.druecke(3.9, 2.9, treffer=("block", 0))
    st.lasse_los(3.9, 2.9)
    assert st.auswahl == {("block", 0)}
```

An `tests/test_gui_raumeditor.py`:

```python
def test_der_umschalter_folgt_der_3d_verfuegbarkeit(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("leer")
    ansicht.show()
    qapp.processEvents()
    if ansicht.sicht3d.verfuegbar:
        assert ansicht.umschalter.isEnabled()
        ansicht.umschalter.click()
        assert ansicht.stapel.currentWidget() is ansicht.sicht3d
        ansicht._taste("tab", False, False, False)
        assert ansicht.stapel.currentWidget() is ansicht.sicht
    else:
        assert not ansicht.umschalter.isEnabled()
        ansicht._taste("tab", False, False, False)
        assert ansicht.stapel.currentWidget() is ansicht.sicht
        assert "3D" in ansicht.sicht3d.tafel
```

- [ ] **Step 2: Rot**

- [ ] **Step 3: Steuerung und Tab**

`steuerung.py::druecke`: Signatur `druecke(self, x, y, taste="links", shift=False, ctrl=False, toleranz=TOLERANZ_M, treffer=None)`; in `_druecke_auswahl(x, y, shift, toleranz, treffer=None)`: `s = treffer if treffer is not None else b.treffer(self.raum, x, y, toleranz)` — die Griffe werden weiterhin zuerst geprüft.

`tab.py`: `from PySide6.QtWidgets import QStackedWidget`; `from spotlab.gui.raumeditor.sicht3d import Sicht3D`; im Konstruktor:

```python
        self.sicht3d = Sicht3D(palette)
        self.sicht3d.gedrueckt.connect(self._gedrueckt_3d)
        self.sicht3d.bewegt.connect(self._bewegt)
        self.sicht3d.losgelassen.connect(self._losgelassen)
        self.sicht3d.taste_gedrueckt.connect(self._taste)
        self.sicht3d.bereit.connect(self._3d_bereit)
        self.stapel = QStackedWidget()
        self.stapel.addWidget(self.sicht)
        self.stapel.addWidget(self.sicht3d)
        mitte.addWidget(self.stapel, 1)          # statt self.sicht
        self.umschalter.setToolTip("3D-Sicht (Tab)")
        self.umschalter.toggled.connect(self._umschalten)
```

`_3d_bereit(ok)`: `self.umschalter.setEnabled(ok)`; ohne GL bleibt der Umschalter grau und `sicht3d.tafel` erklärt es (Tooltip = Tafel). `_umschalten(an)`: `self.stapel.setCurrentWidget(self.sicht3d if an else self.sicht)`; beim Wechsel nach 3D `self.sicht3d.alles_zeigen()` einmalig, `self._zeige()`. `_taste`: `"tab"` → `if self.umschalter.isEnabled(): self.umschalter.toggle()`. `_gedrueckt_3d(x, y, taste, shift, ctrl)`: `self.steuerung.druecke(x, y, taste, shift, ctrl, toleranz=self.sicht3d.toleranz_m(), treffer=self.sicht3d._klick_schluessel); self._zeige()`. `_zeige`: auch `self.sicht3d.zeige(st.raum, st.auswahl)`; `_setze`: `self.sicht3d.setze_spur([])`, `setze_anstoesse([])`, `alles_zeigen()`; `lade`: Spur/Anstösse auch an `sicht3d`. Der Startknopf und alles andere bleiben.

Damit die 3D-Sicht ihren Kontext bekommt, muss sie einmal sichtbar gewesen sein — `QStackedWidget` zeigt nur die aktuelle Seite. Deshalb: `self.sicht3d` beim Erzeugen kurz als aktuelle Seite setzen? Nein — `QOpenGLWidget.initializeGL` läuft erst beim ersten Zeigen. Lösung: `_3d_bereit` wird beim ersten Umschalten ausgelöst; bis dahin ist der Umschalter **aktiviert, wenn `gl_verfuegbar()`** (Kontextprobe ohne Widget), und ein Fehlschlag in `initializeGL` schaltet ihn danach wieder aus und zurück auf 2D:

```python
        self.umschalter.setEnabled(gl_verfuegbar())
    def _3d_bereit(self, ok):
        self.umschalter.setEnabled(ok)
        if not ok:
            self.umschalter.setChecked(False)
            self.umschalter.setToolTip(self.sicht3d.tafel)
            self.meldung.emit(self.sicht3d.grund)
```

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumeditor.py tests/test_gui_raumeditor_steuerung.py tests/test_gui_app.py`; dann das Probeskript mit Kontext (Bild ansehen).

- [ ] **Step 5: Doku** — README: im Raumeditor-Abschnitt „**2D | 3D.** Der Knopf (oder `Tab`) schaltet auf eine 3D-Sicht: linke Maustaste wählt, rechte dreht die Kamera, mittlere (oder Shift+rechts) schwenkt, das Rad zoomt, `Home` rahmt den Raum; die Tasten sind dieselben. Ohne OpenGL 3.3 bleibt der Knopf grau und erklärt, warum (`QT_OPENGL=software` hilft oft)." CLAUDE.md, Nicht verhandelbar: „**PyOpenGL nur in `gui/raumeditor/sicht3d.py`, erst beim Erzeugen der Sicht importiert.** Ohne das Paket läuft der Editor in 2D; ein Import auf Modulebene liesse die ganze GUI ohne PyOpenGL sterben (`tests/test_gui_raumeditor_sicht3d.py`)." Umsetzungsstand: Etappe 2 fertig.

- [ ] **Step 6: Suite, Commit** — `python -m ruff check src tests && python -m pytest -q -p no:cacheprovider --timeout=300`; Commit `feat(raumeditor): 2D | 3D im Tab, Treffer aus dem Farb-ID-Puffer, Doku`.
