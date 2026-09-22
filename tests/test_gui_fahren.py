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


def _bild(pfad, farbe):
    from PySide6.QtGui import QColor, QImage

    bild = QImage(64, 36, QImage.Format_RGB888)
    bild.fill(QColor(farbe))
    bild.save(str(pfad))


def test_der_tab_zeigt_den_blick_nach_vorn(qapp, tmp_path):
    """Wer faehrt, will sehen, wohin: `ansicht.jpg` aus dem Lauf-Verzeichnis --
    am echten Roboter die Frontkameras, im Uebungsraum das gerenderte Zimmer."""
    ansicht = FahrenView()
    assert not ansicht.bild.hat_bild() and not ansicht.hinweis_bild.isHidden()
    pfad = tmp_path / "ansicht.jpg"
    _bild(pfad, "red")

    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    ansicht.zeige_ansicht(pfad)
    assert ansicht.bild.hat_bild() and ansicht.hinweis_bild.isHidden()

    ansicht.zeige_ansicht(tmp_path / "gibtsnicht.jpg")     # halb geschrieben oder weg
    assert ansicht.bild.hat_bild(), "das letzte Bild bleibt stehen"

    ansicht.lauf_beendet()
    assert not ansicht.bild.hat_bild() and not ansicht.hinweis_bild.isHidden()


def test_neue_bytes_unter_gleichem_namen_kommen_an(qapp, tmp_path):
    """`ansicht.jpg` wird ERSETZT, nicht neu angelegt. Qts Dateicache in
    `QPixmap(pfad)` zeigte fuer denselben Namen das alte Bild."""
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    pfad = tmp_path / "ansicht.jpg"
    _bild(pfad, "red")
    ansicht.zeige_ansicht(pfad)
    _bild(pfad, "blue")
    ansicht.zeige_ansicht(pfad)
    farbe = ansicht.bild.pixmap().toImage().pixelColor(5, 5)
    assert farbe.blue() > 200 > farbe.red()


def test_die_bildrate_steht_unter_dem_bild(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    pfad = tmp_path / "ansicht.jpg"
    _bild(pfad, "red")
    uhr = iter([0.0, 0.25, 0.5, 0.75, 1.0])
    for _ in range(5):
        ansicht.zeige_ansicht(pfad, jetzt=lambda: next(uhr))
    assert ansicht.bildrate.text() == "Blick: 4 Bilder/s"
    ansicht.lauf_beendet()
    assert ansicht.bildrate.text() == ""


def test_die_app_reicht_die_ansicht_in_den_tab(qapp, tmp_path):
    from spotlab.gui.app import MainWindow

    pfad = tmp_path / "ansicht.jpg"
    _bild(pfad, "red")
    fenster = MainWindow()
    tab = fenster.ansichten["fahren"]
    fenster._ansicht(pfad)
    assert not tab.bild.hat_bild(), "ohne Lauf kein Bild"
    tab.lauf_beginnt(tmp_path, "fahren.py")
    fenster._ansicht(pfad)
    assert tab.bild.hat_bild()


# ------------------------------------------------- Der Schalter „Gesichtserkennung"


def test_ohne_lauf_ist_der_schalter_grau(qapp):
    """Er schreibt in ein Lauf-Verzeichnis. Ohne Lauf gibt es keines."""
    ansicht = FahrenView()
    assert not ansicht.gesicht.isEnabled()
    assert not ansicht.gesicht.isChecked()


def test_umlegen_schreibt_den_schalter_ins_lauf_verzeichnis(qapp, tmp_path):
    """Der ganze Kanal: die GUI schreibt, `blick.py` im Laufprozess liest."""
    from spotlab.record import ansicht as schalter

    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    assert ansicht.gesicht.isEnabled()
    assert schalter.lies(tmp_path) is False, "ohne Zutun aus"

    ansicht.gesicht.setChecked(True)
    assert schalter.lies(tmp_path) is True
    ansicht.gesicht.setChecked(False)
    assert schalter.lies(tmp_path) is False


def test_ein_neuer_lauf_bekommt_den_schalterstand_mit(qapp, tmp_path):
    """Sonst steht das Haekchen, und der naechste Lauf erkennt trotzdem nichts --
    ein Schalter, der luegt, ist schlimmer als keiner."""
    from spotlab.record import ansicht as schalter

    erster, zweiter = tmp_path / "a", tmp_path / "b"
    erster.mkdir()
    zweiter.mkdir()

    ansicht = FahrenView()
    ansicht.lauf_beginnt(erster, "fahren.py")
    ansicht.gesicht.setChecked(True)
    ansicht.lauf_beendet()

    ansicht.lauf_beginnt(zweiter, "fahren.py")
    assert ansicht.gesicht.isChecked(), "die Wahl des Menschen bleibt stehen"
    assert schalter.lies(zweiter) is True, "und sie gilt auch fuer den neuen Lauf"


def test_nach_dem_lauf_ist_der_schalter_wieder_grau(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    ansicht.gesicht.setChecked(True)
    ansicht.lauf_beendet()
    assert not ansicht.gesicht.isEnabled()


def test_der_handschalter_schreibt_neben_dem_gesicht_in_dieselbe_datei(qapp, tmp_path):
    from spotlab.record import ansicht as schalter

    ansicht = FahrenView()
    assert not ansicht.hand.isEnabled() and not ansicht.hand.isChecked()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    assert ansicht.hand.isEnabled()
    assert schalter.schalter(tmp_path) == {"gesicht": False, "hand": False}

    ansicht.hand.setChecked(True)
    assert schalter.schalter(tmp_path) == {"gesicht": False, "hand": True}
    assert ansicht.hand_hinweis.isVisible() or not ansicht.isVisible()
    ansicht.gesicht.setChecked(True)
    assert schalter.schalter(tmp_path) == {"gesicht": True, "hand": True}
    ansicht.hand.setChecked(False)
    assert schalter.schalter(tmp_path) == {"gesicht": True, "hand": False}

    ansicht.lauf_beendet()
    assert not ansicht.hand.isEnabled() and ansicht.hand_hinweis.isHidden()


def test_ein_neuer_lauf_bekommt_auch_den_handschalter_mit(qapp, tmp_path):
    from spotlab.record import ansicht as schalter

    erster, zweiter = tmp_path / "a", tmp_path / "b"
    erster.mkdir()
    zweiter.mkdir()
    ansicht = FahrenView()
    ansicht.lauf_beginnt(erster, "fahren.py")
    ansicht.hand.setChecked(True)
    ansicht.lauf_beendet()
    ansicht.lauf_beginnt(zweiter, "fahren.py")
    assert schalter.schalter(zweiter)["hand"] is True


def test_der_handschalter_sagt_woher_der_kasten_kommt_und_was_er_kostet(qapp):
    """Der Kasten kommt aus dem Rumpf-Ausschnitt des gefundenen Koerpers (wie im
    Folgemodus), und ohne Mensch im Bild sucht der Erkenner jedes Bild neu."""
    ansicht = FahrenView()
    text = (ansicht.hand.toolTip() + " " + ansicht.hand_hinweis.text()).lower()
    assert "körper" in text and "bildrate" in text
    assert "halt" in text and "weiter" in text


# ------------------------------------- Zurueck nach dem NOT-AUS (Kontrolle uebernehmen)


def test_der_fahrtknopf_meldet_ob_uebernommen_werden_soll(qapp):
    """Nach dem NOT-AUS haelt der getoetete Lauf das Lease -- ohne Uebernahme kommt
    man nie wieder hinein (18.09.2026, zweimal hintereinander)."""
    ansicht = FahrenView()
    gewuenscht = []
    ansicht.fahrt_gewuenscht.connect(gewuenscht.append)
    ansicht.start.click()
    ansicht.uebernehmen.setChecked(True)
    ansicht.start.click()
    assert gewuenscht == [False, True]


def test_das_haekchen_gilt_fuer_fahrt_und_lage(qapp):
    """EIN Haekchen fuer diesen Reiter: es geht immer um dieselbe Frage, wer steuert."""
    ansicht = FahrenView()
    gewuenscht = []
    ansicht.lage_gewuenscht.connect(lambda a, s, u: gewuenscht.append(u))
    ansicht.uebernehmen.setChecked(True)
    ansicht.akku.click()
    assert gewuenscht == [True]


def test_nach_dem_notaus_steht_der_weg_zurueck_im_reiter(qapp, tmp_path):
    ansicht = FahrenView()
    assert ansicht.notaus_hinweis.isHidden()
    ansicht.nach_notaus()
    assert not ansicht.notaus_hinweis.isHidden()
    text = ansicht.notaus_hinweis.text().lower()
    assert "übernehmen" in text and "lease" in text
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    assert ansicht.notaus_hinweis.isHidden(), "der naechste Lauf laeuft -- der Hinweis ist erledigt"


def test_die_uebernahme_bleibt_eine_bewusste_handlung(qapp):
    """Nie vorausgewaehlt, auch nicht nach dem NOT-AUS: der Mensch setzt das Haekchen."""
    ansicht = FahrenView()
    assert not ansicht.uebernehmen.isChecked()
    ansicht.nach_notaus()
    assert not ansicht.uebernehmen.isChecked()


# ------------------------------------------------------------- Die Zeile „Lage"


def test_die_lage_zeile_hat_richtung_akku_aufrichten_und_lease():
    ansicht = FahrenView()
    assert [ansicht.seite.itemData(i) for i in range(ansicht.seite.count())] == ["links", "rechts"]
    assert ansicht.akku.isEnabled() and ansicht.aufrichten.isEnabled(), "ohne Lauf frei -- die App prueft den Rest"
    assert not ansicht.uebernehmen.isChecked(), "Uebernahme ist eine bewusste Handlung, nie Vorgabe"


def test_die_knoepfe_melden_aktion_seite_und_uebernahme(qapp):
    ansicht = FahrenView()
    gewuenscht = []
    ansicht.lage_gewuenscht.connect(lambda a, s, u: gewuenscht.append((a, s, u)))
    ansicht.seite.setCurrentIndex(ansicht.seite.findData("rechts"))
    ansicht.uebernehmen.setChecked(True)
    ansicht.akku.click()
    ansicht.uebernehmen.setChecked(False)
    ansicht.aufrichten.click()
    assert gewuenscht == [("akku", "rechts", True), ("aufrichten", "rechts", False)]


def test_waehrend_der_fahrt_sind_die_lageknoepfe_grau(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    assert not ansicht.akku.isEnabled() and not ansicht.aufrichten.isEnabled()
    ansicht.lauf_beendet()
    assert ansicht.akku.isEnabled() and ansicht.aufrichten.isEnabled()


def test_ein_lagelauf_sperrt_die_fahrt_und_zeigt_die_letzte_zeile(qapp):
    """Der Fortschritt (Rollwinkel) steht dort, wo der Knopf ist -- nicht nur in „Live"."""
    ansicht = FahrenView()
    ansicht.lage_beginnt("akku")
    assert not ansicht.start.isEnabled() and not ansicht.akku.isEnabled() and not ansicht.aufrichten.isEnabled()
    assert "Akku" in ansicht.lage_zustand.text()
    ansicht.zeige_lage_zeile("  Rollwinkel -45°\n")
    assert ansicht.lage_zustand.text() == "Rollwinkel -45°"
    ansicht.zeige_lage_zeile("   \n")
    assert ansicht.lage_zustand.text() == "Rollwinkel -45°", "eine Leerzeile loescht nichts"
    ansicht.zeige_lage_zeile("Fertig: Spot liegt auf der linken Seite.")
    ansicht.lage_beendet()
    assert ansicht.start.isEnabled() and ansicht.akku.isEnabled() and ansicht.aufrichten.isEnabled()
    assert ansicht.lage_zustand.text().startswith("Fertig"), "die letzte Zeile bleibt stehen"


def test_zeilen_ohne_lagelauf_werden_nicht_angezeigt(qapp):
    ansicht = FahrenView()
    ansicht.zeige_lage_zeile("Rollwinkel -45°")
    assert ansicht.lage_zustand.text() == ""


def test_der_lagehinweis_nennt_die_bedingungen(qapp):
    """Motoren vorher aus (sonst kein Not-Aus-Eintrag), ebener Boden mit Platz, Lease frei.
    Und dass die Akku-Haltung das Weiteste ist, was die API rollt."""
    ansicht = FahrenView()
    text = (ansicht.akku.toolTip() + " " + ansicht.aufrichten.toolTip() + " "
            + ansicht.lage_hinweis.text()).lower()
    for wort in ("motoren", "lease", "eben", "platz", "hand"):
        assert wort in text, wort


def test_der_schalter_sagt_dass_die_tiefenpruefung_fehlt(qapp):
    """Was man sieht, sind die Kaesten des Erkenners -- Fehltreffer eingeschlossen.
    Das muss dort stehen, wo der Schalter ist, nicht nur in der Dokumentation."""
    ansicht = FahrenView()
    text = (ansicht.gesicht.toolTip() + " " + ansicht.gesicht_hinweis.text()).lower()
    assert "tiefe" in text or "gegenprobe" in text
    assert "fehltreffer" in text


# ------------------------------------- Nachtraege aus der Beta-Durchsicht (22.09.2026)


def test_die_seitenwahl_gehoert_zum_akkuwechsel_und_sagt_das(qapp):
    """`lage.aufrichten` liest die Seite NIE. Ein Auswahlfeld, das neben zwei Knoepfen
    steht und nur fuer einen gilt, ist ein Haekchen ohne Wirkung."""
    ansicht = FahrenView()
    beschriftung = (ansicht.seite.toolTip() + " " + ansicht.seite_beschriftung.text()).lower()
    assert "akku" in beschriftung


def test_der_notaus_hinweis_kommt_nur_wenn_wirklich_etwas_getoetet_wurde(qapp, tmp_path):
    """Ohne laufendes Programm sagt die Statuszeile 'Es laeuft gerade kein Programm' --
    dann darf im Reiter nicht stehen, ein Lauf sei getoetet worden und das Lease haenge
    an einem Toten. Im gefaehrlichen Fall (Toeten gescheitert, Roboter faehrt weiter)
    ist derselbe Satz sogar falsch und schickt zur Lease-Uebernahme."""
    ansicht = FahrenView()
    ansicht.nach_notaus(getoetet=False)
    assert ansicht.notaus_hinweis.isHidden()
    ansicht.nach_notaus(getoetet=True)
    assert not ansicht.notaus_hinweis.isHidden()
