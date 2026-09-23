"""Das Ladebild: ein Spot im Trab, solange die Oberflaeche im Hintergrund laedt.

Die Gangmechanik ist reine Geometrie und ohne Fenster pruefbar. Worauf es
ankommt: ein Fuss, der steht, bewegt sich GENAU so schnell nach hinten wie der
Boden unter ihm -- sonst rutscht Spot, und das sieht man sofort.
"""

import math
import threading
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui import ladebild  # noqa: E402
from spotlab.gui.ladebild import GANG, Ladebild, beine  # noqa: E402


def _abstand(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_die_beinlaengen_bleiben_ueber_den_ganzen_schritt():
    for i in range(200):
        for bein in beine(i * GANG.periode / 200):
            assert _abstand(bein.huefte, bein.knie) == pytest.approx(GANG.oberschenkel, abs=1e-6)
            assert _abstand(bein.knie, bein.fuss) == pytest.approx(GANG.unterschenkel, abs=1e-6)


def test_ein_stehender_fuss_ruht_auf_dem_mitlaufenden_boden():
    dt = 0.004
    for i in range(100):
        t = i * GANG.periode / 100
        for jetzt, spaeter in zip(beine(t), beine(t + dt)):
            if jetzt.steht and spaeter.steht:
                assert jetzt.fuss[1] == pytest.approx(GANG.huefthoehe)
                geschwindigkeit = (spaeter.fuss[0] - jetzt.fuss[0]) / dt
                assert geschwindigkeit == pytest.approx(-GANG.bodentempo(), rel=1e-6)


def test_die_knie_zeigen_nach_hinten_wie_bei_spot():
    """Spot schaut nach +x. Sein Knie liegt hinter der Linie Huefte-Fuss."""
    for i in range(50):
        for bein in beine(i * GANG.periode / 50):
            (hx, hy), (kx, ky), (fx, fy) = bein.huefte, bein.knie, bein.fuss
            kreuz = (fx - hx) * (ky - hy) - (fy - hy) * (kx - hx)
            assert kreuz > 0, bein.name


def test_trab_diagonale_paare_und_nie_alle_fuesse_in_der_luft():
    for i in range(100):
        stand = {b.name: b.steht for b in beine(i * GANG.periode / 100)}
        assert stand["vorne_nah"] == stand["hinten_fern"]
        assert stand["vorne_fern"] == stand["hinten_nah"]
        assert sum(stand.values()) >= 2


def test_das_ladebild_zeichnet_zu_jeder_zeit(qapp):
    from PySide6.QtGui import QImage

    bild = Ladebild("0.2.0b3")
    bild.melde("Lade Oberfläche …")
    assert bild.status() == "Lade Oberfläche …"
    for t in (0.0, 0.13, 0.4, 1.7):
        bild.setze_zeit(t)
        leinwand = QImage(bild.size(), QImage.Format_ARGB32)
        leinwand.fill(0)
        bild.render(leinwand)
        assert not leinwand.isNull()


def _warte_bis(qapp, bedingung, frist_s=30.0):
    """Wartet, bis `bedingung()` wahr ist -- kehrt sofort zurueck, sobald sie es ist.
    Die grosse Frist ist Absicht: in der vollen Suite leben Hunderte Fenster
    frueherer Tests weiter, deren Zeitgeber jede Runde der Ereignisschleife
    verlangsamen (23.09.2026: 559 Fenster nach test_gui_app, 5 s reichten nicht)."""
    ende = time.monotonic() + frist_s
    while not bedingung() and time.monotonic() < ende:
        qapp.processEvents()
        time.sleep(0.01)
    return bedingung()


def test_geladen_wird_im_hintergrund_gebaut_im_gui_thread(qapp):
    from PySide6.QtWidgets import QWidget

    from spotlab.gui.start import Start

    faeden = {}

    def lade():
        faeden["lade"] = threading.current_thread()
        time.sleep(0.05)

    def baue():
        faeden["baue"] = threading.current_thread()
        fenster = QWidget()
        faeden["fenster"] = fenster
        return fenster

    fehler = []
    start = Start(lade, baue, fehler.append, version="test")
    start.bild.setAttribute(ladebild.Qt.WA_DontShowOnScreen, True)
    start.los()
    assert _warte_bis(qapp, lambda: "fenster" in faeden)
    assert faeden["lade"] is not threading.main_thread()
    assert faeden["baue"] is threading.main_thread()
    assert fehler == []
    assert _warte_bis(qapp, lambda: not start.bild.isVisible())


def test_scheitert_das_laden_wird_gemeldet_und_nichts_gebaut(qapp):
    from spotlab.gui.start import Start

    gebaut, fehler = [], []

    def lade():
        raise ImportError("PySide6 halb installiert")

    start = Start(lade, lambda: gebaut.append(1), fehler.append, version="test")
    start.bild.setAttribute(ladebild.Qt.WA_DontShowOnScreen, True)
    start.los()
    assert _warte_bis(qapp, lambda: fehler)
    assert isinstance(fehler[0], ImportError)
    assert gebaut == []
    assert not start.bild.isVisible()


def test_vorwaermen_laedt_im_hintergrund_und_schluckt_fehler():
    from spotlab.gui.start import vorwaermen

    faden = vorwaermen(("json", "gibt_es_nicht_xyz"))
    faden.join(10)
    assert not faden.is_alive()
    assert faden.daemon


def test_die_fassung_steht_lesbar_da():
    from spotlab.gui.ladebild import fassung_lesbar

    assert fassung_lesbar("0.2.0b3") == ("0.2.0 · Beta 3", True)
    assert fassung_lesbar("1.0.0rc1") == ("1.0.0 · Vorabversion 1", True)
    assert fassung_lesbar("1.0.0") == ("1.0.0", False)
    assert fassung_lesbar("") == ("", False)


def test_scheitert_der_fensterbau_verschwindet_das_ladebild(qapp):
    """Eine Ausnahme im Qt-Slot verpufft -- ohne Fang stuende das Ladebild ewig."""
    from spotlab.gui.start import Start

    fehler = []

    def baue():
        raise ImportError("cannot import name 'stylesheet'")

    start = Start(lambda: None, baue, fehler.append, version="test")
    start.bild.setAttribute(ladebild.Qt.WA_DontShowOnScreen, True)
    start.los()
    assert _warte_bis(qapp, lambda: fehler)
    assert not start.bild.isVisible()
    assert start.fenster is None


def test_der_echte_startweg_baut_das_hauptfenster(qapp, monkeypatch, tmp_path):
    """lade_gui im Hintergrund, baue_gui im GUI-Thread -- mit dem echten
    Hauptfenster. Ohne diesen Test fiel nicht auf, dass baue_gui Namen aus
    app.py holte, die dort beim Aufraeumen der Importe verschwunden waren."""
    from spotlab.gui.start import Start, baue_gui, lade_gui

    fehler = []
    start = Start(lade_gui, baue_gui, fehler.append, version="test")
    start.bild.setAttribute(ladebild.Qt.WA_DontShowOnScreen, True)
    start.los()
    assert _warte_bis(qapp, lambda: start.fenster is not None or fehler, frist_s=90)
    assert fehler == []
    assert type(start.fenster).__name__ == "MainWindow"
    start.fenster.close()
