"""Das eigene Fenster fuer den virtuellen Lauf -- die Turtle-Ansicht.

Warum ein eigenes Fenster und keine weitere Ansicht: der Schueler soll seinen
Code SEHEN, waehrend Spot faehrt. In einem Fenster mit umschaltbaren Ansichten
geht genau das nicht.
"""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.gui.uebungsfenster import Uebungsfenster  # noqa: E402
from spotlab.welt.raum import raum_laden  # noqa: E402


def test_das_fenster_ist_ein_eigenes_fenster(qapp):
    fenster = Uebungsfenster(DUNKEL)
    assert fenster.parent() is None
    assert "Übungsraum" in fenster.windowTitle()


def test_ein_lauf_zeichnet_die_spur_waehrend_er_laeuft(qapp):
    """Nicht erst am Ende: 71 Posen in 7 Sekunden sind genau das, was man sehen
    will."""
    fenster = Uebungsfenster(DUNKEL)
    fenster.beginne(raum_laden("durchgang"), (1.0, 2.0, 0.0))
    fenster.zeige_pose(1.5, 2.0, 0.0)
    fenster.zeige_pose(2.0, 2.0, 45.0)

    assert fenster.plot.spur() == [(1.5, 2.0), (2.0, 2.0)]


def test_ein_zweiter_lauf_faengt_leer_an(qapp):
    fenster = Uebungsfenster(DUNKEL)
    fenster.beginne(raum_laden("leer"), (1.0, 1.0, 0.0))
    fenster.zeige_pose(2.0, 1.0, 0.0)
    fenster.beginne(raum_laden("leer"), (1.0, 1.0, 0.0))

    assert fenster.plot.spur() == []


def test_der_raum_laesst_sich_ueber_den_namen_setzen(qapp):
    """Der Name kommt aus dem `verbunden`-Ereignis des Laufs -- das ist die
    einzige Quelle, die sagt, worin das Programm WIRKLICH gefahren ist."""
    fenster = Uebungsfenster(DUNKEL)
    fenster.setze_raum_name("durchgang")
    assert fenster.plot.raum() is not None
    assert fenster.plot.raum().tags


def test_ein_unbekannter_raum_bringt_das_fenster_nicht_um(qapp):
    fenster = Uebungsfenster(DUNKEL)
    fenster.setze_raum_name("gibtsnicht")          # darf nicht werfen
    assert fenster.plot.raum() is None


def test_die_letzte_ausgabezeile_steht_im_fenster(qapp):
    """Sonst ist ein Traceback unsichtbar: die Ausgabe liegt in der Ansicht
    „Code", und die sieht man waehrend des Laufs gerade nicht."""
    fenster = Uebungsfenster(DUNKEL)
    fenster.zeige_ausgabe("Tag 3: 0.9 m, +12 Grad")
    assert "Tag 3" in fenster.zeile.text()


def test_der_stopp_knopf_meldet_nur_den_wunsch(qapp):
    """Wie im Editor: gestoppt wird ueber LiveView, die als Einzige das
    Lauf-Verzeichnis kennt."""
    fenster = Uebungsfenster(DUNKEL)
    fenster.beginne(raum_laden("leer"), (1.0, 1.0, 0.0))
    gewuenscht = []
    fenster.stopp_gewuenscht.connect(lambda: gewuenscht.append(True))
    fenster.stopp.click()
    assert gewuenscht == [True]


def test_nach_dem_ende_stoppt_der_knopf_nichts_mehr(qapp):
    fenster = Uebungsfenster(DUNKEL)
    fenster.beginne(raum_laden("leer"), (1.0, 1.0, 0.0))
    assert fenster.stopp.isEnabled()
    fenster.beendet("fertig")
    assert not fenster.stopp.isEnabled()
    assert "fertig" in fenster.zeile.text()


def test_ein_anstoss_wird_vermerkt(qapp):
    fenster = Uebungsfenster(DUNKEL)
    fenster.beginne(raum_laden("moebliert"), (1.0, 1.0, 0.0))
    fenster.zeige_anstoss(2.0, 3.0)
    assert fenster.plot.anstoesse() == [(2.0, 3.0)]


def test_der_raumwechsel_verwirft_eine_schon_gefahrene_spur_nicht(qapp):
    """Das `verbunden`-Ereignis kommt NACH den ersten Posen an. Setzte es den
    Start neu, entstuende ein Strich von der Schablonenposition zur echten --
    ein Weg, den Spot nie gefahren ist."""
    fenster = Uebungsfenster(DUNKEL)
    fenster.beginne(raum_laden("durchgang"), (3.0, 4.0, 0.0))
    fenster.zeige_pose(3.1, 4.0, 0.0)
    fenster.setze_raum_name("durchgang")

    assert fenster.plot.spur() == [(3.1, 4.0)]


def test_die_3d_ansicht_erscheint_sobald_ein_bild_da_ist(qapp, tmp_path):
    """Ohne Bild bleibt die Zeichnung allein (2D-Sim); mit backend='mujoco'
    kommt das gerenderte Zimmer dazu."""
    from PySide6.QtGui import QColor, QImage

    fenster = Uebungsfenster(DUNKEL)
    fenster.beginne(raum_laden("leer"), (1.0, 1.0, 0.0))
    assert fenster.bild.isHidden()

    pfad = tmp_path / "ansicht.jpg"
    bild = QImage(64, 36, QImage.Format_RGB32)
    bild.fill(QColor(30, 60, 90))
    assert bild.save(str(pfad), "JPG")
    fenster.zeige_ansicht(pfad)

    assert not fenster.bild.isHidden()
    assert fenster.bild.pixmap() is not None and not fenster.bild.pixmap().isNull()


def test_ein_neuer_lauf_versteckt_das_alte_bild(qapp, tmp_path):
    from PySide6.QtGui import QColor, QImage

    fenster = Uebungsfenster(DUNKEL)
    pfad = tmp_path / "ansicht.jpg"
    bild = QImage(8, 8, QImage.Format_RGB32)
    bild.fill(QColor(0, 0, 0))
    bild.save(str(pfad), "JPG")
    fenster.zeige_ansicht(pfad)
    fenster.beginne(raum_laden("leer"), (1.0, 1.0, 0.0))
    assert fenster.bild.isHidden(), "das Bild des letzten Laufs gehoert nicht zum neuen"
