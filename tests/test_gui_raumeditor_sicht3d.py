"""Die 3D-Sicht: GL-Haut mit Rueckfall. Rendern nur mit Kontext."""
import ast
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtOpenGLWidgets")

from spotlab.gui.raumeditor.sicht3d import Sicht3D, gl_verfuegbar  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import Block, Raum  # noqa: E402

RAUM = Raum(name="T", beschreibung="", start=(1, 1, 0), waende=((0, 0, 4, 0),),
            bloecke=(Block("K", 2, 2, 1, 1, drehung=30.0),))


def test_opengl_wird_nur_in_sicht3d_und_erst_beim_zeigen_importiert():
    wurzel = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "gui" / "raumeditor"
    for datei in wurzel.glob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        oben = [k for k in baum.body if isinstance(k, (ast.Import, ast.ImportFrom))]
        namen = set()
        for k in oben:
            namen.update([a.name for a in k.names] if isinstance(k, ast.Import) else [k.module or ""])
        assert not any(n.startswith("OpenGL") for n in namen), \
            f"{datei.name} importiert OpenGL auf Modulebene"


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


def test_gl_verfuegbar_ohne_anwendung_ist_falsch_und_stuerzt_nicht():
    """`QOpenGLContext.create()` ohne QGuiApplication ist eine Zugriffsverletzung."""
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is not None:
        pytest.skip("hier laeuft schon eine Anwendung")
    assert gl_verfuegbar() is False


def test_mit_kontext_rendert_die_sicht_den_raum(qapp):
    if not gl_verfuegbar():
        pytest.skip("kein OpenGL-3.3-Kontext (offscreen?)")
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


def test_das_gelaende_hat_eine_bandfarbe_und_ist_nicht_anklickbar(qapp):
    from spotlab.welt import gelaende as g

    sicht = Sicht3D(DUNKEL)
    farbe = sicht._elementfarbe(("gelaende", 3))
    assert farbe.startswith("#") and farbe != DUNKEL.akzent
    assert sicht._elementfarbe(("gelaende", 0)) != farbe
    raum = Raum(name="G", beschreibung="", start=(1, 1, 0),
                gelaende=g.gitter(0.0, 0.0, 0.5, 5, 9, lambda x, y: 0.2 * x))
    sicht.zeige(raum)
    if not gl_verfuegbar():
        pytest.skip("kein OpenGL-3.3-Kontext (offscreen?)")
    sicht.resize(320, 240)
    sicht.show()
    qapp.processEvents()
    sicht.alles_zeigen()
    sicht.bild()
    assert sicht.treffer(160, 120) in (("start",), None)
