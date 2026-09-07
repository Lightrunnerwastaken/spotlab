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
    # Mit globalPos: die kuerzere Ueberladung ist in PySide6 veraltet und
    # schreibt bei jedem Lauf eine DeprecationWarning in die Ausgabe.
    ereignis = QMouseEvent(
        QMouseEvent.MouseButtonPress, QPointF(px, py), QPointF(px, py),
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


def test_die_spur_zeigt_nur_gemessene_posen(qapp):
    """Der eingetragene Start ist eine ANNAHME der GUI, keine Messung. Weicht
    er vom echten Start ab, zeichnete er einen Weg, den Spot nie gefahren ist --
    am 04.09.2026 eine Diagonale von (1, 1) nach (0, 0) quer durchs Zimmer.
    Der Kreis steht trotzdem am gewaehlten Start, bis die erste Pose kommt."""
    plot = RaumPlot(DUNKEL)
    plot.setze_start((1.0, 2.0, 0.0))
    assert plot.spur() == []
    assert plot.start() == (1.0, 2.0, 0.0)

    plot.haenge_pose_an(1.5, 2.0, 30.0)
    assert plot.spur() == [(1.5, 2.0)]


def test_die_blickrichtung_folgt_der_pose(qapp):
    """Vorher stand sie fest auf dem Startwinkel -- ein `move(turn=90)` war in
    der Zeichnung nicht zu sehen."""
    plot = RaumPlot(DUNKEL)
    plot.setze_start((1.0, 2.0, 0.0))
    plot.haenge_pose_an(1.0, 2.0, 90.0)
    assert plot.blick() == 90.0


def test_ein_neuer_start_setzt_spur_und_blick_zurueck(qapp):
    plot = RaumPlot(DUNKEL)
    plot.setze_start((1.0, 2.0, 0.0))
    plot.haenge_pose_an(3.0, 2.0, 90.0)
    plot.setze_start((1.0, 2.0, 0.0))
    assert plot.spur() == []
    assert plot.blick() == 0.0


def test_ohne_groesse_zeichnet_die_huelle(qapp):
    from spotlab.gui.raumplot import RaumPlot
    from spotlab.welt.raum import Raum

    plot = RaumPlot(DUNKEL)
    plot.resize(400, 300)
    plot.setze_raum(Raum(name="T", beschreibung="", start=(0, 0, 0), waende=((0, 0, 4, 0),)))
    x, y = plot.schirm_zu_meter(*plot.meter_zu_schirm(2.0, 0.0))
    assert (x, y) == (pytest.approx(2.0), pytest.approx(0.0, abs=1e-6))


def test_die_huelle_wird_je_raum_gerechnet_nicht_je_punkt(qapp, monkeypatch):
    """`meter_zu_schirm` wird je gezeichnetem Punkt gerufen -- und rechnete ueber
    `_massstab` jedes Mal `huelle(raum)` neu, ueber alle Waende, Boeden und den
    Gelaende-Umriss: auf den korrigierten Katakomben 950 Aufrufe und 172 ms je Bild,
    bei 10 Zustaenden je Sekunde stand die GUI (07.09.2026). Was je Punkt gefragt
    wird, muss O(1) sein -- die Huelle gehoert zum Raum, nicht zum Punkt."""
    from spotlab.gui import raumplot as modul
    from spotlab.welt.raum import Raum

    zaehler = {"n": 0}
    echt = modul.huelle

    def gezaehlt(raum):
        zaehler["n"] += 1
        return echt(raum)

    monkeypatch.setattr(modul, "huelle", gezaehlt)
    plot = RaumPlot(DUNKEL)
    plot.resize(400, 300)
    plot.setze_raum(Raum(name="T", beschreibung="", start=(0, 0, 0),
                         waende=tuple((i, 0, i + 1, 1) for i in range(40))))
    for _ in range(3):
        plot.grab()
    assert zaehler["n"] <= 1, zaehler["n"]
    x, y = plot.schirm_zu_meter(*plot.meter_zu_schirm(2.0, 0.5))
    assert (x, y) == (pytest.approx(2.0), pytest.approx(0.5))
