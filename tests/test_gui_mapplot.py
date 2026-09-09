import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QColor, QPixmap  # noqa: E402

from spotlab.gui.mapplot import MapPlot  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.maps.geometry import Grundriss, Punkt  # noqa: E402


def _grundriss():
    return Grundriss(
        punkte=[Punkt("a", "start", 0.0, 0.0), Punkt("b", "kueche", 4.0, 3.0)],
        kanten=[("a", "b")],
        quelle="anker",
        hinweis="",
    )


def _gezeichnet(widget, breite=320, hoehe=240):
    widget.resize(breite, hoehe)
    bild = QPixmap(breite, hoehe)
    widget.render(bild)
    return bild.toImage()


def _zaehle(bild, hexfarbe, toleranz=40):
    ziel = QColor(hexfarbe)
    treffer = 0
    for y in range(bild.height()):
        for x in range(bild.width()):
            farbe = bild.pixelColor(x, y)
            if (
                abs(farbe.red() - ziel.red()) < toleranz
                and abs(farbe.green() - ziel.green()) < toleranz
                and abs(farbe.blue() - ziel.blue()) < toleranz
            ):
                treffer += 1
    return treffer


def test_leerer_grundriss_zeichnet_ohne_absturz(qapp):
    plot = MapPlot()
    plot.setze_grundriss(Grundriss([], [], "leer", "Diese Karte ist leer."))
    _gezeichnet(plot)  # darf nicht werfen


def test_punkte_werden_gezeichnet(qapp):
    plot = MapPlot()
    plot.setze_grundriss(_grundriss(), DUNKEL)
    bild = _gezeichnet(plot)
    # zwei benannte Wegpunkte ⇒ Kreise in der ok-Farbe
    assert _zaehle(bild, DUNKEL.ok) > 20


def test_hinweis_wird_uebernommen(qapp):
    plot = MapPlot()
    riss = Grundriss([Punkt("a", "", 0.0, 0.0)], [], "kette", "Rundungsfehler möglich.")
    plot.setze_grundriss(riss, DUNKEL)
    assert plot.grundriss.hinweis == "Rundungsfehler möglich."


def test_ein_einzelner_punkt_stuerzt_nicht_ab(qapp):
    """Ohne Ausdehnung wäre der Massstab eine Division durch null."""
    plot = MapPlot()
    plot.setze_grundriss(Grundriss([Punkt("a", "", 2.0, 2.0)], [], "kette", ""), DUNKEL)
    _gezeichnet(plot)


def test_widget_ohne_flaeche_stuerzt_nicht_ab(qapp):
    plot = MapPlot()
    plot.setze_grundriss(_grundriss(), DUNKEL)
    _gezeichnet(plot, breite=1, hoehe=1)


def test_ein_klick_nahe_einem_wegpunkt_meldet_ihn(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    plot = MapPlot()
    plot.setze_grundriss(_grundriss(), DUNKEL)
    plot.resize(320, 240)
    geklickt = []
    plot.wegpunkt_geklickt.connect(geklickt.append)
    x, y = plot.lagen_auf_schirm()["b"]
    QTest.mouseClick(plot, Qt.LeftButton, pos=QPoint(x + 3, y - 2))
    assert geklickt == ["b"]
    QTest.mouseClick(plot, Qt.LeftButton, pos=QPoint(x + 40, y + 40))
    assert geklickt == ["b"], "daneben ist daneben"
    assert plot.wegpunkt_bei(x + 40, y + 40) is None


def test_ziel_standort_und_roboter_werden_gezeichnet_und_mit_der_karte_geleert(qapp):
    plot = MapPlot()
    plot.setze_grundriss(_grundriss(), DUNKEL)
    plot.setze_ziel("b")
    plot.setze_standort("a")
    plot.setze_roboter((2.0, 1.5, 45.0))
    bild = _gezeichnet(plot)
    assert _zaehle(bild, DUNKEL.warnung) > 10, "der Zielring"
    assert (plot.ziel, plot.standort, plot.roboter) == ("b", "a", (2.0, 1.5, 45.0))
    plot.setze_grundriss(_grundriss(), DUNKEL)
    assert plot.ziel is None and plot.standort is None and plot.roboter is None


def test_ein_doppelklick_meldet_den_wegpunkt_zum_benennen(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    plot = MapPlot()
    plot.setze_grundriss(_grundriss(), DUNKEL)
    plot.resize(320, 240)
    doppelt = []
    plot.wegpunkt_doppelt.connect(doppelt.append)
    x, y = plot.lagen_auf_schirm()["a"]
    QTest.mouseDClick(plot, Qt.LeftButton, pos=QPoint(x, y))
    assert doppelt == ["a"]
