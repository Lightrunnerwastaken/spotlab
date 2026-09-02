import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.raumplot import RaumPlot  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import raum_laden  # noqa: E402


def _plot():
    plot = RaumPlot(DUNKEL)
    plot.resize(400, 300)
    plot.setze_raum(raum_laden("moebliert"))
    return plot


def test_umrechnung_ist_umkehrbar(qapp):
    plot = _plot()
    for x, y in [(0.0, 0.0), (3.0, 2.0), (6.0, 4.0)]:
        px, py = plot.meter_zu_schirm(x, y)
        zurueck = plot.schirm_zu_meter(px, py)
        assert zurueck[0] == pytest.approx(x, abs=0.02)
        assert zurueck[1] == pytest.approx(y, abs=0.02)


def test_y_zeigt_nach_oben(qapp):
    """Auf dem Schirm waechst y nach unten, im Raum nach oben."""
    plot = _plot()
    _px_unten, py_unten = plot.meter_zu_schirm(1.0, 0.0)
    _px_oben, py_oben = plot.meter_zu_schirm(1.0, 4.0)
    assert py_oben < py_unten


def test_seitenverhaeltnis_bleibt_erhalten(qapp):
    """Ein 6x4-Zimmer darf in einem breiten Fenster nicht verzerrt werden."""
    plot = _plot()
    plot.resize(800, 300)
    px0, py0 = plot.meter_zu_schirm(0.0, 0.0)
    px1, _ = plot.meter_zu_schirm(1.0, 0.0)
    _, py1 = plot.meter_zu_schirm(0.0, 1.0)
    assert abs((px1 - px0) - (py0 - py1)) < 0.5


def test_klick_liefert_meter(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    plot = _plot()
    gemeldet = []
    plot.start_gewaehlt.connect(lambda x, y: gemeldet.append((x, y)))
    px, py = plot.meter_zu_schirm(3.0, 2.0)
    ereignis = QMouseEvent(
        QMouseEvent.MouseButtonPress, QPointF(px, py),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    plot.mousePressEvent(ereignis)
    assert gemeldet
    assert gemeldet[0][0] == pytest.approx(3.0, abs=0.05)
    assert gemeldet[0][1] == pytest.approx(2.0, abs=0.05)


def test_zeichnen_ohne_raum_stuerzt_nicht(qapp):
    from PySide6.QtGui import QPixmap

    plot = RaumPlot(DUNKEL)
    plot.resize(200, 150)
    plot.render(QPixmap(200, 150))


def test_zeichnen_mit_allem_stuerzt_nicht(qapp):
    from PySide6.QtGui import QPixmap

    plot = _plot()
    plot.setze_spur([(1.0, 1.0), (2.0, 1.0), (2.0, 2.0)])
    plot.setze_anstoesse([(2.5, 1.4)])
    plot.setze_start((1.0, 1.0, 0.0))
    plot.render(QPixmap(400, 300))


def test_kein_farbliteral():
    """CLAUDE.md: Farben nur aus theme.py."""
    import re
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[1]
              / "src" / "spotlab" / "gui" / "raumplot.py").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{6}", quelle)
