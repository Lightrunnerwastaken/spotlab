"""Tasten -> fahrt.json: eine Formulierung fuer das Uebungsfenster und die Ansicht „Fahren"."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402

from spotlab.gui.tastenfahrt import Tastenfahrt  # noqa: E402
from spotlab.record import fahrt  # noqa: E402


def _taste(key, gedrueckt=True, wiederholung=False):
    art = QKeyEvent.KeyPress if gedrueckt else QKeyEvent.KeyRelease
    return QKeyEvent(art, key, Qt.NoModifier, "", wiederholung)


def test_ohne_lauf_schreiben_die_tasten_nichts(qapp, tmp_path):
    t = Tastenfahrt()
    assert not t.aktiv
    assert not t.tastenereignis(_taste(Qt.Key_W), gedrueckt=True)
    assert not (tmp_path / fahrt.DATEI).exists()


def test_die_tasten_werden_zum_befehl_und_der_takt_laeuft_solange_etwas_gedrueckt_ist(qapp, tmp_path):
    t = Tastenfahrt()
    befehle = []
    t.befehl.connect(lambda vx, vy, wz: befehle.append((vx, vy, wz)))
    t.beginne(tmp_path)
    assert t.aktiv and not t.takt.isActive()
    assert t.tastenereignis(_taste(Qt.Key_W), gedrueckt=True)
    assert fahrt.lies(tmp_path) == (fahrt.TEMPO_M_S, 0.0, 0.0)
    assert t.takt.isActive() and t.tasten == {"w"}
    assert t.tastenereignis(_taste(Qt.Key_Q), gedrueckt=True)
    assert fahrt.lies(tmp_path) == (fahrt.TEMPO_M_S, 0.0, fahrt.DREH_RAD_S)
    assert not t.tastenereignis(_taste(Qt.Key_W, wiederholung=True), gedrueckt=True), "Autorepeat ist keine Aenderung"
    assert t.tastenereignis(_taste(Qt.Key_W), gedrueckt=False)
    assert fahrt.lies(tmp_path) == (0.0, 0.0, fahrt.DREH_RAD_S)
    assert not t.tastenereignis(_taste(Qt.Key_X), gedrueckt=True), "fremde Tasten gehen weiter"
    assert t.tastenereignis(_taste(Qt.Key_Space), gedrueckt=True)
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0) and not t.takt.isActive() and t.tasten == set()
    assert befehle[-1] == (0.0, 0.0, 0.0) and befehle[0] == (fahrt.TEMPO_M_S, 0.0, 0.0)


def test_der_faktor_drosselt_alle_drei_achsen(qapp, tmp_path):
    t = Tastenfahrt()
    t.beginne(tmp_path)
    t.faktor = 0.5
    t.druecke("w")
    t.druecke("a")
    t.druecke("e")
    vx, vy, wz = fahrt.lies(tmp_path)
    assert (vx, vy, wz) == (pytest.approx(fahrt.TEMPO_M_S / 2), pytest.approx(fahrt.QUER_M_S / 2),
                            pytest.approx(-fahrt.DREH_RAD_S / 2))


def test_alle_los_und_beende_lassen_spot_stehen(qapp, tmp_path):
    t = Tastenfahrt()
    t.beginne(tmp_path)
    t.druecke("w")
    t.alle_los()
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0) and not t.takt.isActive() and t.aktiv
    t.druecke("s")
    t.beende()
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0) and not t.aktiv and not t.takt.isActive()
    assert not t.tastenereignis(_taste(Qt.Key_W), gedrueckt=True)


def test_das_lauf_verzeichnis_darf_spaeter_kommen(qapp, tmp_path):
    """Die App kennt es erst, wenn der Watcher den Lauf meldet."""
    t = Tastenfahrt()
    t.beginne()
    t.druecke("w")
    assert t.tasten == {"w"} and not (tmp_path / fahrt.DATEI).exists()
    t.setze_lauf_dir(tmp_path)
    assert fahrt.lies(tmp_path) == (fahrt.TEMPO_M_S, 0.0, 0.0)
