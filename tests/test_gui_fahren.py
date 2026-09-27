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
    assert ansicht.tastenfeld.gedrueckt() == {"w"}
    ansicht.stufe.setCurrentIndex(1)                             # normal
    QTest.keyPress(ansicht, Qt.Key_Q)
    assert fahrt.lies(tmp_path) == (fahrt.TEMPO_M_S, 0.0, fahrt.DREH_RAD_S)
    assert ansicht.tastenfeld.gedrueckt() == {"w", "q"}
    QTest.keyPress(ansicht, Qt.Key_Space)
    assert fahrt.lies(tmp_path) == (0.0, 0.0, 0.0)
    assert ansicht.tastenfeld.gedrueckt() == set()


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


def test_die_uebernahme_gilt_nur_fuer_den_einen_start(qapp, tmp_path):
    """Pruefung 23.09.2026: das Haekchen blieb nach dem Lauf gesetzt, und jede
    spaetere Fahrt, jeder Akkuwechsel nahm dem Tablet das Lease wortlos weg.
    Uebernehmen ist eine bewusste Handlung -- einmal, nicht als Vorgabe."""
    ansicht = FahrenView()
    ansicht.uebernehmen.setChecked(True)
    ansicht.lauf_beginnt(tmp_path)
    assert not ansicht.uebernehmen.isChecked()
    ansicht.lauf_beendet()
    ansicht.uebernehmen.setChecked(True)
    ansicht.lage_beginnt("akku")
    assert not ansicht.uebernehmen.isChecked()


def test_waehrend_akkuwechsel_und_aufrichten_geht_der_stopp(qapp):
    """Der Text verwies auf einen „Stopp im Kopf“, den es nicht gibt -- im Kopf
    ist nur der NOT-AUS. Uebrig blieb der harte Abbruch mitten im Rollen."""
    gewuenscht = []
    ansicht = FahrenView()
    ansicht.stopp_gewuenscht.connect(lambda: gewuenscht.append(1))
    ansicht.lage_beginnt("aufrichten")
    assert ansicht.stopp.isEnabled()
    assert "Stopp im Kopf" not in ansicht.lage_zustand.text()
    ansicht.stopp.click()
    assert gewuenscht == [1]
    ansicht.lage_beendet()
    assert not ansicht.stopp.isEnabled()


def test_das_tastenfeld_zeigt_tasten_stufe_und_ob_sie_scharf_sind(qapp, tmp_path):
    """UX-Pruefung 23.09.2026: die Belegung stand in 10 px, „Tasten sind scharf“
    wurde von der ersten Positionszeile ueberschrieben -- am echten Roboter sah
    man nicht mehr, dass die Tastatur faehrt."""
    ansicht = FahrenView()
    assert not ansicht.tastenfeld.aktiv()
    ansicht.lauf_beginnt(tmp_path, "fahren.py")
    assert ansicht.tastenfeld.aktiv()
    assert ansicht.tastenfeld.stufe() == "langsam"
    QTest.keyPress(ansicht, Qt.Key_3)
    assert ansicht.tastenfeld.stufe() == "schnell"
    ansicht.zeige_zustand({"daten": {"pose": [1.0, 2.0, 0.0], "battery": 70.0}})
    assert ansicht.tastenfeld.aktiv(), "eine Positionszeile darf den Zustand nicht verdecken"
    ansicht.lauf_beendet()
    assert not ansicht.tastenfeld.aktiv()


def test_der_lange_hinweis_ist_einklappbar_die_sicherheitszeile_nicht(qapp):
    ansicht = FahrenView()
    assert not ansicht.sicherheit.isHidden()
    assert "Not-Aus" in ansicht.sicherheit.text()
    assert ansicht.hinweis.isHidden()
    ansicht.mehr.click()
    assert not ansicht.hinweis.isHidden()


# ------------------------------------------------ Steuerzentrale (27.09.2026)


def _lagebild_schreiben(lauf_dir, **mehr):
    import numpy as np

    from spotlab.backends.base import ObstacleGrid
    from spotlab.record import zentrale as protokoll
    from spotlab.workshop import skizze as sk

    s = sk.Skizze()
    s.aufnehmen(ObstacleGrid(np.full((40, 40), 1.0), 0.03, (0.0, 0.0), 0.0,
                             known=np.ones((40, 40), bool)), t=1.0)
    daten = {"t": 1.0, "rahmen": "vision", "zelle_m": s.zelle_m, "ursprung": list(s.ursprung),
             "breite": s.zustand.shape[1], "hoehe": s.zustand.shape[0],
             "spot": {"x": 0.5, "y": 0.5, "gier_grad": 0.0}, "tags": [],
             "klickfahrt": {"nummer": 0, "zustand": "keine", "grund": "", "ziel": None, "weg": []},
             "faehigkeiten": {"licht": False, "ton": False, "kamera": False},
             "menschen": [], "karte": None}
    daten.update(mehr)
    protokoll.schreibe_lagebild(lauf_dir, daten, s.png(t=1.0))


def test_die_vorgabe_ist_der_uebungsraum(qapp):
    ansicht = FahrenView()
    assert ansicht.ort() == "uebungsraum"
    assert [ansicht.ort_wahl.itemData(i) for i in range(ansicht.ort_wahl.count())] == \
        ["uebungsraum", "real"]


def test_ein_klick_in_die_draufsicht_schreibt_das_klickziel(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    ansicht.lagebild.klick.emit(2.5, 1.0)
    kz = protokoll.lies_klickziel(tmp_path)
    assert (kz.nummer, kz.ziel, kz.stufe) == (1, (2.5, 1.0), "langsam")
    ansicht.lagebild.klick.emit(3.0, 1.0)
    assert protokoll.lies_klickziel(tmp_path).nummer == 2, "jeder Klick ein neues Ziel"


def test_ohne_lauf_schreibt_ein_klick_nichts(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lagebild.klick.emit(2.5, 1.0)
    assert not list(tmp_path.iterdir())


def test_der_herzschlag_lebt_nur_bei_sichtbarem_tab(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht = FahrenView()
    ansicht.show()
    ansicht.lauf_beginnt(tmp_path)
    ansicht.lagebild.klick.emit(2.5, 1.0)
    ansicht._herzschlag(jetzt=lambda: 123.0)
    assert protokoll.lies_klickziel(tmp_path).lebt == 123.0
    ansicht.hide()
    ansicht._herzschlag(jetzt=lambda: 999.0)
    assert protokoll.lies_klickziel(tmp_path).lebt == 123.0, "Reiter weg: kein Lebenszeichen"
    assert ansicht.herzschlag_takt.interval() == 200


def test_eine_taste_bricht_die_klickfahrt_ab(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht = FahrenView()
    ansicht.show()
    ansicht.lauf_beginnt(tmp_path)
    ansicht.lagebild.klick.emit(2.5, 1.0)
    QTest.keyPress(ansicht, Qt.Key_W)
    kz = protokoll.lies_klickziel(tmp_path)
    assert kz.nummer == 2 and kz.ziel is None
    ansicht.hide()


def test_licht_und_ton_erst_wenn_der_lauf_sie_kann(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    assert not ansicht.licht.isEnabled() and not ansicht.ton.isEnabled()
    _lagebild_schreiben(tmp_path, faehigkeiten={"licht": True, "ton": True, "kamera": True})
    ansicht._lade_lagebild()
    assert ansicht.licht.isEnabled() and ansicht.ton.isEnabled()
    ansicht.licht.setCurrentIndex(ansicht.licht.findData("gruen"))
    assert protokoll.lies_aktion(tmp_path) == {"nummer": 1, "art": "licht", "farbe": "gruen"}
    ansicht.ton.click()
    assert protokoll.lies_aktion(tmp_path) == {"nummer": 2, "art": "ton", "farbe": None}


def test_im_uebungsraum_sagen_licht_und_ton_warum_sie_grau_sind(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    _lagebild_schreiben(tmp_path)
    ansicht._lade_lagebild()
    assert not ansicht.ton.isEnabled() and "echten Spot" in ansicht.ton.toolTip()


def test_das_lagebild_kommt_an_und_die_zeile_sagt_den_stand(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    _lagebild_schreiben(tmp_path, klickfahrt={"nummer": 1, "zustand": "abgelehnt",
                                              "grund": "unbekannt — dort hat Spot noch keinen "
                                                       "Boden gesehen", "ziel": [9.0, 9.0], "weg": []})
    ansicht._lade_lagebild()
    assert ansicht.lagebild.hat_bild()
    assert "abgelehnt" in ansicht.klick_zeile.text() and "unbekannt" in ansicht.klick_zeile.text()


def test_nach_dem_lauf_ist_die_zentrale_leer(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    assert ansicht.herzschlag_takt.isActive() and not ansicht.ort_wahl.isEnabled()
    _lagebild_schreiben(tmp_path, faehigkeiten={"licht": True, "ton": True, "kamera": False})
    ansicht._lade_lagebild()
    ansicht.lauf_beendet()
    assert not ansicht.lagebild.hat_bild() and not ansicht.herzschlag_takt.isActive()
    assert not ansicht.licht.isEnabled() and ansicht.ort_wahl.isEnabled()


def test_ohne_kamera_verspricht_der_tab_kein_bild(qapp, tmp_path):
    """Im 2D-Übungsraum gibt es keine Kamera -- „der Blick kommt, sobald der Lauf steht“
    wäre ein Versprechen, das nie eingelöst wird."""
    from spotlab.gui.views.fahren import KEIN_BILD

    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    _lagebild_schreiben(tmp_path)
    ansicht._lade_lagebild()
    assert "keine Kamera" in ansicht.hinweis_bild.text()
    _lagebild_schreiben(tmp_path, t=2.0, faehigkeiten={"licht": False, "ton": False, "kamera": True})
    ansicht._lagebild_stempel = None
    ansicht._lade_lagebild()
    assert ansicht.hinweis_bild.text() == KEIN_BILD
    ansicht.lauf_beendet()
    assert ansicht.hinweis_bild.text() == KEIN_BILD


# ------------------------------------------------ Menschen und Folgen (Teil 2)


def _suche(stufe="aus", kann=True, runde_s=None, grund=None):
    return {"stufe": stufe, "runde_s": runde_s, "kann": kann, "grund": grund}


def test_der_regler_ist_grau_bis_der_lauf_menschen_suchen_kann(qapp, tmp_path):
    ansicht = FahrenView()
    assert not ansicht.suche_regler.isEnabled()
    ansicht.lauf_beginnt(tmp_path)
    _lagebild_schreiben(tmp_path, suche=_suche(kann=False, grund="Keine Bild- und "
                                                                "Tiefenkameras (Übungsraum)"))
    ansicht._lade_lagebild()
    assert not ansicht.suche_regler.isEnabled() and "Übungsraum" in ansicht.suche_text.toolTip()
    _lagebild_schreiben(tmp_path, t=2.0, suche=_suche(kann=True))
    ansicht._lagebild_stempel = None
    ansicht._lade_lagebild()
    assert ansicht.suche_regler.isEnabled()
    ansicht.lauf_beendet()
    assert not ansicht.suche_regler.isEnabled()


def test_der_regler_hat_vier_stufen_und_schickt_die_gewaehlte(qapp, tmp_path):
    from spotlab.gui.views.fahren import VORGABE_SUCHE
    from spotlab.record import zentrale as protokoll

    ansicht = FahrenView()
    assert ansicht.suche_regler.maximum() - ansicht.suche_regler.minimum() == 3
    assert ansicht.suchstufe() == VORGABE_SUCHE
    ansicht.lauf_beginnt(tmp_path)
    _lagebild_schreiben(tmp_path, suche=_suche(stufe="aus"))
    ansicht._lade_lagebild()
    aktion = protokoll.lies_aktion(tmp_path)
    assert (aktion["art"], aktion["stufe"]) == ("suche", VORGABE_SUCHE), "nachgeschickt"
    ansicht.suche_regler.setValue(3)
    aktion = protokoll.lies_aktion(tmp_path)
    assert aktion["stufe"] == "rundum" and aktion["nummer"] == 2


def test_eine_verlorene_stufe_wird_nachgeschickt_aber_nicht_jeden_takt(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    ansicht._zeige_suche(_suche(stufe="aus"), jetzt=lambda: 10.0)
    ansicht._zeige_suche(_suche(stufe="aus"), jetzt=lambda: 10.5)
    assert protokoll.lies_aktion(tmp_path)["nummer"] == 1
    ansicht._zeige_suche(_suche(stufe="aus"), jetzt=lambda: 12.0)
    assert protokoll.lies_aktion(tmp_path)["nummer"] == 2


def test_unter_dem_regler_steht_die_rundenzeit_und_was_fehlt(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    ansicht.suche_regler.setValue(3)
    ansicht._zeige_suche(_suche(stufe="rundum", runde_s=1.24, grund="hinten: Kamera weg"))
    assert "1.2 s" in ansicht.suche_text.text() and "hinten" in ansicht.suche_text.toolTip()


def test_ein_klick_neben_einen_menschen_folgt_ihm(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht = FahrenView()
    ansicht.show()
    ansicht.lauf_beginnt(tmp_path)
    mensch = {"x": 2.0, "y": 1.0, "alter_s": 0.2, "quelle": "vorne", "gefolgt": False}
    _lagebild_schreiben(tmp_path, menschen=[mensch], suche=_suche(stufe="sparsam"))
    ansicht._lade_lagebild()
    ansicht.lagebild.klick.emit(2.3, 1.2)
    kz = protokoll.lies_klickziel(tmp_path)
    assert (kz.art, kz.ziel) == ("mensch", (2.0, 1.0)), "der Mensch, nicht der Klickpunkt"
    ansicht._herzschlag(jetzt=lambda: 50.0)
    assert protokoll.lies_klickziel(tmp_path).art == "mensch", "das Lebenszeichen behält die Art"
    ansicht.lagebild.klick.emit(0.5, 0.5)
    assert protokoll.lies_klickziel(tmp_path).art == "ort"
    ansicht.hide()


def test_die_zeile_sagt_wem_spot_folgt_und_warum_er_aufhoerte(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    _lagebild_schreiben(tmp_path, klickfahrt={"nummer": 1, "zustand": "folgt",
                                              "grund": "folgt dem angeklickten Menschen",
                                              "ziel": [2.0, 1.0], "weg": []})
    ansicht._lade_lagebild()
    assert "folgt dem angeklickten" in ansicht.klick_zeile.text()
    assert "Taste" in ansicht.klick_zeile.text()
    _lagebild_schreiben(tmp_path, t=2.0, klickfahrt={"nummer": 1, "zustand": "abgebrochen",
                                                     "grund": "Folgen beendet: Stopp",
                                                     "ziel": None, "weg": []})
    ansicht._lagebild_stempel = None
    ansicht._lade_lagebild()
    assert ansicht.klick_zeile.text() == "Folgen beendet: Stopp."


# ------------------------------------------------ Karten (Teil 3)


def _karte(**felder):
    karte = {"kann": True, "name": None, "zustand": "keine", "grund": "", "auftrag": None,
             "quelle": None, "aufnahme": None, "wegpunkte": [], "kanten": [], "raster": None,
             "wiedererkennung": None}
    karte.update(felder)
    return karte


def _mit_karten(tmp_path):
    (tmp_path / "karten" / "flur2").mkdir(parents=True)
    (tmp_path / "karten" / "flur2" / "graph").write_bytes(b"")
    lauf = tmp_path / "lauf"
    lauf.mkdir()
    ansicht = FahrenView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.lauf_beginnt(lauf)
    return ansicht, lauf


def test_ohne_graphnav_ist_die_kartenzeile_grau_und_sagt_warum(qapp, tmp_path):
    ansicht, lauf = _mit_karten(tmp_path)
    ansicht._zeige_karte(_karte(kann=False, grund="Karten gibt es nur am echten Spot (GraphNav)."))
    assert not ansicht.laden.isEnabled() and not ansicht.aufnahme.isEnabled()
    assert not ansicht.wegpunkt.isEnabled() and "GraphNav" in ansicht.karten_zeile.text()
    ansicht._zeige_karte(None)
    assert not ansicht.aufnahme.isEnabled()


def test_laden_schickt_die_gewaehlte_karte(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht, lauf = _mit_karten(tmp_path)
    ansicht._zeige_karte(_karte())
    assert ansicht.karten_wahl.findText("flur2") >= 0
    ansicht.karten_wahl.setCurrentIndex(ansicht.karten_wahl.findText("flur2"))
    ansicht.laden.click()
    assert protokoll.lies_kartenauftrag(lauf) == {"nummer": 1, "was": "laden", "name": "flur2"}


def test_verortet_schlaegt_die_aufnahme_das_weiterfuehren_vor(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht, lauf = _mit_karten(tmp_path)
    ansicht._zeige_karte(_karte(name="flur2", zustand="verortet"))
    assert ansicht.karten_name.text() == "flur2-2"
    ansicht.aufnahme.click()
    assert protokoll.lies_kartenauftrag(lauf) == {"nummer": 1, "was": "aufnahme_start",
                                                  "name": "flur2-2"}
    ansicht._zeige_karte(_karte(zustand="nimmt_auf", auftrag=1,
                                aufnahme={"wegpunkte": 3, "kanten": 2, "name": "flur2-2",
                                          "weiter": True}))
    assert "beenden" in ansicht.aufnahme.text() and not ansicht.laden.isEnabled()
    assert ansicht.wegpunkt.isEnabled() and "3 Wegpunkte" in ansicht.karten_zeile.text()
    ansicht.aufnahme.click()
    assert protokoll.lies_kartenauftrag(lauf)["was"] == "aufnahme_stopp"


def test_ohne_karte_heisst_der_vorschlag_nach_datum(qapp, tmp_path):
    ansicht, _ = _mit_karten(tmp_path)
    ansicht._zeige_karte(_karte())
    assert ansicht.karten_name.text().startswith("karte-")


def test_ein_eigener_name_bleibt_stehen(qapp, tmp_path):
    from PySide6.QtTest import QTest

    ansicht, _ = _mit_karten(tmp_path)
    ansicht._zeige_karte(_karte())
    ansicht.karten_name.clear()
    QTest.keyClicks(ansicht.karten_name, "gang")
    ansicht._zeige_karte(_karte(name="flur2", zustand="verortet"))
    assert ansicht.karten_name.text() == "gang"


def test_ein_verlorener_kartenauftrag_wird_nachgeschickt(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht, lauf = _mit_karten(tmp_path)
    ansicht._zeige_karte(_karte(), jetzt=lambda: 100.0)
    ansicht._karten_auftrag("laden", "flur2", jetzt=lambda: 100.0)
    (lauf / protokoll.KARTENAUFTRAG).unlink()
    ansicht._zeige_karte(_karte(), jetzt=lambda: 100.5)
    assert not (lauf / protokoll.KARTENAUFTRAG).exists(), "noch keine 1.5 s"
    ansicht._zeige_karte(_karte(), jetzt=lambda: 102.0)
    assert protokoll.lies_kartenauftrag(lauf)["nummer"] == 1
    ansicht._zeige_karte(_karte(auftrag=1), jetzt=lambda: 104.0)
    (lauf / protokoll.KARTENAUFTRAG).unlink()
    ansicht._zeige_karte(_karte(auftrag=1), jetzt=lambda: 106.0)
    assert not (lauf / protokoll.KARTENAUFTRAG).exists(), "bestätigt: nichts mehr nachschicken"


def test_ein_wegpunkt_fragt_nach_dem_namen_und_wartet_auf_bestaetigung(qapp, tmp_path):
    from spotlab.record import zentrale as protokoll

    ansicht, lauf = _mit_karten(tmp_path)
    aufnahme = {"wegpunkte": 0, "kanten": 0, "name": "gang", "weiter": False}
    ansicht._zeige_karte(_karte(zustand="nimmt_auf", aufnahme=aufnahme))
    ansicht._frage_name = lambda vorschlag: ("Tür", True)
    ansicht.wegpunkt.click()
    assert protokoll.lies_kartenauftrag(lauf) == {"nummer": 1, "was": "wegpunkt", "name": "Tür"}
    ansicht._zeige_karte(_karte(zustand="nimmt_auf", aufnahme=aufnahme))
    assert not ansicht.wegpunkt.isEnabled(), "der vorige ist noch nicht bestätigt"
    ansicht._zeige_karte(_karte(zustand="nimmt_auf", aufnahme=aufnahme, auftrag=1))
    assert ansicht.wegpunkt.isEnabled()


def test_die_zeile_sagt_urteil_und_anteil(qapp, tmp_path):
    ansicht, _ = _mit_karten(tmp_path)
    wieder = {"verloren": False, "angenommen": 18, "abgelehnt": 2, "anteil": 0.82,
              "wandzellen": 120, "erkannt": 98, "neu": 22, "fehlt": 5}
    ansicht._zeige_karte(_karte(name="flur2", zustand="verortet", wiedererkennung=wieder))
    text = ansicht.karten_zeile.text()
    assert "flur2" in text and "18 von 20" in text and "82 %" in text


def test_verloren_steht_in_der_zeile(qapp, tmp_path):
    ansicht, _ = _mit_karten(tmp_path)
    ansicht._zeige_karte(_karte(name="flur2", zustand="verloren"))
    assert "verloren" in ansicht.karten_zeile.text()


def test_das_kartenbild_kommt_mit_dem_lagebild(qapp, tmp_path):
    import numpy as np

    from spotlab.record import zentrale as protokoll
    from spotlab.workshop import kartenabgleich as ka

    ansicht, lauf = _mit_karten(tmp_path)
    a = ka.Abgleich(np.array([[protokoll.KARTE_ERKANNT]], np.uint8), (0.5, 0.5), 1, 1, 0, 0, 0,
                    None)
    (lauf / protokoll.LAGEBILD_KARTE).write_bytes(ka.png(a))
    _lagebild_schreiben(lauf, karte=_karte(name="flur2", zustand="verortet",
                                           raster={"ursprung": [0.5, 0.5], "breite": 1,
                                                   "hoehe": 1}))
    ansicht._lade_lagebild()
    assert ansicht.lagebild.hat_kartenbild() and "flur2" in ansicht.karten_zeile.text()


def test_nach_dem_lauf_ist_die_kartenzeile_grau(qapp, tmp_path):
    ansicht, _ = _mit_karten(tmp_path)
    ansicht._zeige_karte(_karte(zustand="verortet", name="flur2"))
    ansicht.lauf_beendet()
    assert not ansicht.laden.isEnabled() and not ansicht.aufnahme.isEnabled()


# ------------------------------------------------ Flüssiger (27.09.2026)


def test_der_zustand_fuehrt_den_pfeil_in_der_draufsicht(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    _lagebild_schreiben(tmp_path, vision_von_odom=[0.0, 0.0, 0.0])
    ansicht._lade_lagebild()
    ansicht.zeige_zustand({"daten": {"pose": [0.7, 0.5, 0.0]}})
    assert ansicht.lagebild.ziel_lage()[:2] == pytest.approx((0.7, 0.5))


def test_das_lagebild_wird_alle_100_ms_nachgesehen(qapp, tmp_path):
    ansicht = FahrenView()
    ansicht.lauf_beginnt(tmp_path)
    assert ansicht.lagebild_takt.interval() == 100 and ansicht.lagebild_takt.isActive()
    assert ansicht.herzschlag_takt.interval() == 200, "das Lebenszeichen bleibt bei 200 ms"
    ansicht.lauf_beendet()
    assert not ansicht.lagebild_takt.isActive()
