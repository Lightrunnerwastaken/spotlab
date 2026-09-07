"""Die Ansicht „Fahren": den echten Spot ueber W A S D Q E fahren."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from spotlab.gui.views.fahren import FahrenView  # noqa: E402
from spotlab.record import fahrt  # noqa: E402


def test_vor_dem_start_schreiben_die_tasten_nichts(qapp, tmp_path):
    ansicht = FahrenView()
    assert not ansicht.laeuft() and not ansicht.stopp.isEnabled()
    QTest.keyPress(ansicht, Qt.Key_W)
    assert not (tmp_path / fahrt.DATEI).exists()


def test_der_knopf_wuenscht_die_fahrt_und_der_stopp_delegiert(qapp, tmp_path):
    ansicht = FahrenView()
    gewuenscht, stopps = [], []
    ansicht.fahrt_gewuenscht.connect(lambda: gewuenscht.append(1))
    ansicht.stopp_gewuenscht.connect(lambda: stopps.append(1))
    ansicht.start.click()
    assert gewuenscht == [1]
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    assert "beenden" in ansicht.start.text() and ansicht.stopp.isEnabled()
    ansicht.stopp.click()
    assert stopps == [1]
    ansicht.start.click()                       # heisst jetzt beenden -- die App entscheidet
    assert gewuenscht == [1, 1]


def test_im_lauf_schreiben_die_tasten_den_befehl_langsam_voreingestellt(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    assert ansicht.laeuft() and ansicht.stufe.currentData() == "langsam"
    QTest.keyPress(ansicht, Qt.Key_W)
    assert fahrt.lies(tmp_path) == (pytest.approx(fahrt.TEMPO_M_S / 2), 0.0, 0.0)
    assert "W" in ansicht.gedrueckt.text()
    ansicht.stufe.setCurrentIndex(1)                             # normal
    QTest.keyPress(ansicht, Qt.Key_Q)
    assert fahrt.lies(tmp_path) == (fahrt.TEMPO_M_S, 0.0, fahrt.DREH_RAD_S)
    QTest.keyPress(ansicht, Qt.Key_Space)
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0)
    assert "—" in ansicht.gedrueckt.text()


def test_die_stufen_stehen_zur_wahl_und_die_ziffern_schalten_sie(qapp, tmp_path):
    ansicht = FahrenView()
    assert [ansicht.stufe.itemData(i) for i in range(ansicht.stufe.count())] == ["langsam", "normal", "schnell"]
    assert "0.2" in ansicht.stufe.itemText(0) and "0.8" in ansicht.stufe.itemText(2)
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    QTest.keyPress(ansicht, Qt.Key_3)
    assert ansicht.stufe.currentData() == "schnell", "die Auswahl folgt der Taste"
    QTest.keyPress(ansicht, Qt.Key_W)
    assert fahrt.lies(tmp_path) == (pytest.approx(2 * fahrt.TEMPO_M_S), 0.0, 0.0)
    ansicht.stufe.setCurrentIndex(0)
    assert fahrt.lies(tmp_path) == (pytest.approx(fahrt.TEMPO_M_S / 2), 0.0, 0.0), "die Auswahl schreibt sofort"
    assert ansicht.tastenfahrt.stufe == "langsam"


def test_die_ansicht_haelt_die_tastatur_nur_solange_sie_sichtbar_ist(qapp, tmp_path):
    """Reiterwechsel heisst: Tasten los, Spot steht -- eine gehaltene Taste darf den
    Roboter nicht aus einem anderen Reiter heraus weiterfahren lassen."""
    ansicht = FahrenView()
    ansicht.show()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    assert QWidget.keyboardGrabber() is ansicht
    QTest.keyPress(ansicht, Qt.Key_W)
    assert fahrt.lies(tmp_path)[0] > 0
    ansicht.hide()
    assert QWidget.keyboardGrabber() is None
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0) and not ansicht.tastenfahrt.takt.isActive()
    ansicht.show()
    assert QWidget.keyboardGrabber() is ansicht
    ansicht.lauf_beendet()
    assert QWidget.keyboardGrabber() is None and not ansicht.laeuft()
    assert "beginnen" in ansicht.start.text() and not ansicht.stopp.isEnabled()
    ansicht.close()


def test_verliert_die_app_den_fokus_steht_spot(qapp, tmp_path):
    """Alt-Tab mit gehaltenem W: Qt schickt kein KeyRelease mehr, der Takt frischte
    den Befehl sonst weiter auf -- und der echte Roboter liefe blind weiter."""
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    QTest.keyPress(ansicht, Qt.Key_W)
    assert fahrt.lies(tmp_path)[0] > 0
    qapp.applicationStateChanged.emit(Qt.ApplicationInactive)
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0) and not ansicht.tastenfahrt.takt.isActive()


def test_die_zustandszeile_zeigt_pose_tempo_und_akku(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    ansicht.zeige_zustand({"daten": {"pose": [1.25, -2.5, 0.0], "velocity": [0.31, 0.0, 0.0],
                                     "battery": 77.0}})
    text = ansicht.zustand.text()
    assert "1.25" in text and "0.31" in text and "77" in text
