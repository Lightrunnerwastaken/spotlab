"""Zwischenbilder duerfen Messpunkte und Roboterzustand nicht veraendern."""

import math

import pytest

from spotlab.animation import Zeitpuffer
from spotlab.backends.mujoco import _mische_qpos


def test_zwischenbilder_ohne_extrapolation_und_mit_kopie():
    p = Zeitpuffer()
    a = [0.0, 1.0]
    p.anhaengen(1, a)
    a[0] = 999
    p.anhaengen(2, (2, 3))
    assert p.bei(0) == (0, 1)
    assert p.bei(1.5) == (1, 2)
    assert p.bei(9) == (2, 3)
    assert not p.fertig(1.5)
    assert p.fertig(2)


def test_gleiche_und_rueckwaertige_zeitstempel():
    p = Zeitpuffer()
    p.anhaengen(1, (1,))
    p.anhaengen(1, (2,))
    p.anhaengen(0, (999,))
    assert p.bei(1) == (2,)
    p.leeren()
    assert p.bei(1) is None


def test_gelenkwechsel_wird_ueber_zwischenwinkel_dargestellt():
    p = Zeitpuffer(_mische_qpos)
    a = (0, 0, .5, 1, 0, 0, 0, .7)
    b = (1, 0, .5, 1, 0, 0, 0, .9)
    p.anhaengen(1, a)
    p.anhaengen(1.1, b)
    mitte = p.bei(1.05)
    assert mitte[0] == pytest.approx(.5)
    assert mitte[-1] == pytest.approx(.8)
    assert a[-1] == .7 and b[-1] == .9


def test_quaternion_vorzeichen_und_norm():
    a = (0, 0, .5, 1, 0, 0, 0)
    assert _mische_qpos(a, (0, 0, .5, -1, 0, 0, 0), .5) == a
    b = (0, 0, .5, math.cos(.4), 0, math.sin(.4), 0)
    mitte = _mische_qpos(a, b, .5)
    assert sum(x*x for x in mitte[3:7]) == pytest.approx(1)


def test_liveplot_animiert_marker_aber_keine_messspur(qapp):
    from spotlab.gui.liveplot import LiveRaumPlot
    from spotlab.gui.theme import DUNKEL

    zeit = [1.0]
    plot = LiveRaumPlot(DUNKEL, jetzt=lambda: zeit[0])
    plot.haenge_pose_an(0, 0, 179)
    zeit[0] = 1.1
    plot.haenge_pose_an(1, 0, -179)
    zeit[0] = 1.17  # Anzeigezeit 1.05
    x, y, grad = plot.anzeigepose()
    assert x == pytest.approx(.5)
    assert y == 0
    assert grad == pytest.approx(180)
    assert plot.spur() == [(0, 0), (1, 0)]
    zeit[0] = 2
    plot._bild()
    assert not plot._animation.isActive()
    plot.setze_start((5, 5, 90))
    assert plot.anzeigepose() == (5, 5, 90)
    plot.close()


def test_live_scanner_sucht_keine_verzeichnisse_und_verliert_keine_saetze(tmp_path, monkeypatch):
    from spotlab.gui.watcher import RunScanner
    from spotlab.record.run import RunRecorder
    from spotlab.workshop.project import create_project

    rec = RunRecorder(create_project('demo', tmp_path) / 'runs', None, backend='mujoco')
    rec.sample({'battery': 89})  # Lebenszeichen, damit der Lauf entdeckt wird
    scanner = RunScanner(tmp_path)
    scanner.tick()

    def verboten():
        raise AssertionError('Verzeichnissuche im Bildtakt')

    monkeypatch.setattr(scanner, '_neue_laeufe', verboten)
    rec.sample({'battery': 88})
    bild = rec.dir / 'ansicht.jpg'
    bild.write_bytes(b'bild')
    neu = scanner.live_tick()
    assert [art for art, _ in neu] == ['zustand', 'ansicht']
    assert scanner.live_tick() == []
    rec.finish('ok')


def test_wiederverwendeter_bildname_liefert_neue_pixel(qapp, tmp_path):
    from PySide6.QtGui import QImage

    from spotlab.gui.theme import DUNKEL
    from spotlab.gui.uebungsfenster import Uebungsfenster

    fenster = Uebungsfenster(DUNKEL)
    pfad = tmp_path / 'ansicht.bmp'
    bild = QImage(32, 32, QImage.Format_RGB32)
    bild.fill(0xffff0000)
    bild.save(str(pfad))
    fenster.zeige_ansicht(pfad)
    vorher = fenster.bild.pixmap().toImage().pixel(0, 0)
    bild.fill(0xff0000ff)
    bild.save(str(pfad))
    fenster.zeige_ansicht(pfad)
    assert fenster.bild.pixmap().toImage().pixel(0, 0) != vorher
    fenster.close()


def test_beenden_schreibt_letzte_pose_ohne_anzeigeverzug(tmp_path, monkeypatch):
    import numpy as np

    from spotlab.backends import mujoco as backend_modul

    gesehen = []
    geschlossen = []

    class Puppe:
        def qpos(self):
            return (0, 0, .5, 1, 0, 0, 0)

    class Renderer:
        def __init__(self, *_args):
            pass

        def bild(self, qpos):
            gesehen.append(qpos)
            return np.zeros((2, 2, 3), dtype=np.uint8)

        def close(self):
            geschlossen.append(True)

    monkeypatch.setattr(backend_modul, '_LiveAnsicht', Renderer)
    ziel = tmp_path / 'ansicht.jpg'
    schreiber = backend_modul._Ansichtsschreiber(None, Puppe(), ziel)
    schreiber.publiziere((1, 0, .5, 1, 0, 0, 0))
    schreiber._halt.set()
    schreiber.run()
    assert gesehen[-1][0] == 1
    assert geschlossen == [True]
    assert ziel.is_file()
    assert not list(tmp_path.glob('*.tmp'))
