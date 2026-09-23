"""Bedienung des Raumeditors (UX-Pruefung vom 23.09.2026): was der Editor sagt,
zeigt und wo seine Tasten wirken.

Der Text der Zustandszeile, die gesperrte Achse, die Hervorhebung und der
Mauszeiger kommen aus der Steuerung -- ohne Fenster pruefbar. Die Qt-Tests
pruefen nur die Haut: Knoepfe, Kuerzel, Felder, Groessen.
"""
import pytest

from spotlab.gui.raumeditor.steuerung import Steuerung
from spotlab.welt import bearbeitung as b
from spotlab.welt.raum import Block, Raum, RaumTag

RAUM = Raum(
    name="T", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 4, 0), (4, 0, 4, 3)),
    bloecke=(Block("Kiste", 2.0, 2.0, 1.0, 0.5),),
    tags=(RaumTag(1, 3.5, 1.5, 180.0),),
)


# ------------------------------------------------------------- Zustandszeile


def test_die_zustandszeile_nennt_werkzeug_zeiger_und_raster():
    st = Steuerung(RAUM)
    st.bewege(1.234, 2.5)
    text = st.beschreibung()
    assert text.startswith("Auswählen")
    assert "x 1.23 m  y 2.50 m" in text and "Raster 5 cm (Strg: frei)" in text
    st.auswahl = frozenset({("block", 0)})
    assert "1 gewählt" in st.beschreibung() and "Entf löscht" in st.beschreibung()


def test_die_zustandszeile_zeigt_die_geste_mit_achse_und_getippter_zahl():
    st = Steuerung(RAUM)
    st.auswahl = frozenset({("block", 0)})
    st.zeiger = (2.0, 2.0)
    st.taste("g")
    st.bewege(2.5, 2.2)
    text = st.beschreibung()
    assert text.startswith("G bewegen") and "Δx +0.50 m  Δy +0.20 m" in text
    assert "Enter bestätigt · Esc bricht ab" in text
    st.taste("x")
    st.taste("1")
    st.taste(".")
    st.taste("5")
    text = st.beschreibung()
    assert "nur X" in text and "getippt 1.5 m" in text
    st.taste("escape")
    st.taste("r")
    for t in "30":
        st.taste(t)
    assert "R drehen" in st.beschreibung() and "getippt 30°" in st.beschreibung()
    st.taste("escape")
    st.taste("s")
    st.taste("2")
    assert "S skalieren" in st.beschreibung() and "getippt ×2" in st.beschreibung()


def test_die_zustandszeile_zeigt_laenge_und_winkel_der_naechsten_wand():
    st = Steuerung(RAUM)
    st.setze_werkzeug("wand")
    assert "Klick setzt den ersten Punkt" in st.beschreibung()
    st.druecke(0.0, 3.0)
    st.lasse_los(0.0, 3.0)
    st.bewege(3.0, 7.0)
    text = st.beschreibung()
    assert text.startswith("Wand") and "Länge 5.00 m · Winkel 53°" in text
    assert "Esc beendet" in text


def test_die_zustandszeile_zeigt_die_groesse_beim_aufziehen():
    st = Steuerung(RAUM)
    st.setze_werkzeug("block")
    st.druecke(0.5, 0.5)
    st.bewege(1.5, 1.0)
    assert "Block" in st.beschreibung() and "1.00 × 0.50 m" in st.beschreibung()


def test_die_gesperrte_achse_ist_eine_linie_durch_die_mitte():
    st = Steuerung(RAUM)
    st.auswahl = frozenset({("block", 0)})
    st.taste("g")
    assert st.achslinie() is None
    st.taste("x")
    assert st.achslinie() == ("x", (2.0, 2.0))
    st.taste("z")
    assert st.achslinie() is None                           # Hoehe: keine Linie in 2D
    st.taste("escape")
    st.taste("r")
    st.taste("x")
    assert st.achslinie() is None                           # Drehen kennt keine Achse


# ------------------------------------------------ Hervorhebung und Zeiger


def test_ueberfahren_hebt_hervor_und_waehlt_den_zeiger():
    st = Steuerung(RAUM)
    st.bewege(2.0, 2.0)
    assert st.ueber == ("block", 0) and st.zeigerart() == "element"
    st.bewege(1.0, 2.8)
    assert st.ueber is None and st.zeigerart() is None
    st.auswahl = frozenset({("block", 0)})
    ecke = next(g for g in st.griffe() if g[1] == "ecke0")
    st.bewege(ecke[2], ecke[3])
    assert st.ueber_griff and st.zeigerart() == "bewegen"
    st.setze_werkzeug("wand")
    st.bewege(2.0, 2.0)
    assert st.ueber is None and st.zeigerart() == "zeichnen"


def test_f_rahmt_die_auswahl():
    st = Steuerung(RAUM)
    assert st.auswahl_huelle() is None
    st.auswahl = frozenset({("block", 0), ("wand", 0)})
    x0, y0, x1, y1 = st.auswahl_huelle()
    assert x0 < 0.0 and y0 < 0.0 and x1 > 4.0 and 2.25 < y1 < 3.0


# -------------------------------------------------------------------- Hinweise


def test_gleiche_befunde_haben_eine_gruppe_und_ihr_element():
    raum = Raum(name="H", beschreibung="", start=(2.0, 2.0, 0.0),
                waende=((0, 0, 0, 0), (1, 1, 1, 1), (0, 0, 4, 0)))
    befunde = b.befunde(raum)
    assert [f.schluessel for f in befunde] == [("wand", 0), ("wand", 1)]
    assert {f.gruppe for f in befunde} == {"Wände ohne Länge"}
    assert [f.text for f in befunde] == b.pruefe(raum) == ["Wand 1 hat keine Länge.",
                                                          "Wand 2 hat keine Länge."]
    im_tisch = b.befunde(Raum(name="S", beschreibung="", start=(2.0, 2.0, 0.0),
                              bloecke=(Block("Tisch", 2.0, 2.0, 1.0, 1.0),)))
    assert im_tisch[0].schluessel == b.START and im_tisch[0].gruppe is None
    assert im_tisch[0].text.startswith("Der Start steht")


# ---------------------------------------------------------------- Aufbau (Qt)


@pytest.fixture
def tab(qapp):
    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    ansicht = RaumeditorView(DUNKEL)
    yield ansicht
    ansicht.close()


def _leer():
    from spotlab.welt.raum import raum_laden

    return raum_laden("leer")


def test_die_rechte_spalte_ist_fest_und_die_sicht_springt_nicht(tab, qapp):
    from spotlab.welt.raum import Boden

    tab.resize(1080, 640)
    tab.show()
    raum = Raum(name="R", beschreibung="", start=(1.0, 1.0, 0.0), waende=((0, 0, 6, 0),),
                boeden=(Boden("Eine Treppe mit einem sehr langen Namen, der nicht passt",
                              3, 2, 2, 1, anstieg=0.6, stufen=4),))
    tab._setze(raum, "", False, False)
    qapp.processEvents()
    breite = tab.sicht.width()
    for auswahl in ({("boden", 0)}, {("wand", 0)}, {b.START}, set()):
        tab.steuerung.auswahl = frozenset(auswahl)
        tab._zeige()
        qapp.processEvents()
        assert tab.sicht.width() == breite, auswahl
    assert tab.rechts.width() == 300


def test_hinweise_sind_eine_liste_gleiche_zusammengefasst_ein_klick_waehlt(tab):
    raum = Raum(name="H", beschreibung="", start=(2.0, 2.0, 0.0),
                waende=((0, 0, 0, 0), (1, 1, 1, 1), (0, 0, 4, 0)),
                bloecke=(Block("Tisch", 2.0, 2.0, 1.0, 1.0),))
    tab._setze(raum, "", False, False)
    texte = [tab.hinweisliste.item(i).text() for i in range(tab.hinweisliste.count())]
    assert texte[0].startswith("Der Start steht in „Tisch“")
    assert "Wände ohne Länge (2)" in texte and len(texte) == 2
    assert tab.hinweis_titel.text() == "Hinweise (3)"
    assert tab.hinweisliste.maximumHeight() <= 110
    zeile = tab.hinweisliste.item(texte.index("Wände ohne Länge (2)"))
    assert "Wand 1 hat keine Länge." in zeile.toolTip()
    tab._hinweis_gewaehlt(zeile)
    assert tab.steuerung.auswahl == {("wand", 0), ("wand", 1)}
    tab._setze(_leer(), "", False, False)
    assert tab.hinweis_titel.text() == "Keine Hinweise" and tab.hinweisliste.isHidden()


def test_die_felder_haben_beschriftung_und_einheit(tab):
    from PySide6.QtWidgets import QAbstractSpinBox

    tab._zeige()                                           # nichts gewaehlt: der Raum
    dicke = tab.eigenschaften.findChild(QAbstractSpinBox, "feld_wand_dicke")
    assert tab._form.labelForField(dicke).text() == "Wanddicke" and dicke.suffix() == " m"
    tab.steuerung.setze_raum(RAUM)
    tab.steuerung.auswahl = frozenset({("block", 0)})
    tab._zeige()
    drehung = tab.eigenschaften.findChild(QAbstractSpinBox, "feld_drehung")
    hoehe = tab.eigenschaften.findChild(QAbstractSpinBox, "feld_hoehe")
    assert tab._form.labelForField(drehung).text() == "Drehung" and drehung.suffix() == " °"
    assert tab._form.labelForField(hoehe).text() == "Höhe"
    tab.steuerung.auswahl = frozenset({("tag", 0)})
    tab._zeige()
    hoehe = tab.eigenschaften.findChild(QAbstractSpinBox, "feld_hoehe")
    assert tab._form.labelForField(hoehe).text() == "Hängehöhe"


def test_der_startknopf_nennt_die_datei_und_ist_ohne_datei_gesperrt(tab):
    assert tab.starten.objectName() == "Primaer" and tab.starten.isEnabled()
    assert "starten" in tab.starten.text()                # app.py hat noch nichts gemeldet
    tab.setze_datei("hallo_spot.py")
    assert tab.starten.text() == "▶ hallo_spot.py im Übungsraum starten"
    assert tab.starten.isEnabled()
    tab.setze_datei(None)
    assert not tab.starten.isEnabled() and "Code" in tab.starten.toolTip()
    tab.setze_laeuft(True)
    assert tab.starten.isEnabled() and "Stopp" in tab.starten.text()
    tab.setze_laeuft(False)
    assert not tab.starten.isEnabled()
    assert tab.fahren.text() == "🎮 Selbst fahren" and "echten Spot" in tab.fahren.toolTip()


def test_die_werkzeuge_sind_eine_gruppe_und_folgen_der_steuerung(tab):
    knoepfe = tab.werkzeuge.buttons()
    assert len(knoepfe) == 7 and tab.werkzeuge.exclusive()
    assert all(k.isCheckable() for k in knoepfe)
    tab._werkzeug_knoepfe["wand"].click()
    assert tab.steuerung.werkzeug == "wand" and tab._werkzeug_knoepfe["wand"].isChecked()
    tab.neu()                                              # neuer Raum: wieder Auswählen
    assert tab._werkzeug_knoepfe["auswahl"].isChecked()


def test_das_dateimenue_hat_die_dateiaktionen(tab):
    texte = [a.text().split("\t")[0] for a in tab.dateimenue.actions() if not a.isSeparator()]
    for text in ("Neu", "Vorlage laden…", "Öffnen…", "Speichern", "Speichern unter…"):
        assert text in texte
    assert tab.datei_knopf.menu() is tab.dateimenue


def test_der_titel_nennt_vorlage_eigenen_raum_und_aenderungen(tab, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    tab.setze_arbeitsordner(tmp_path)
    tab.waehle_raum("moebliert")
    assert tab.titel.text() == "Möbliert · Vorlage"
    tab.steuerung.setze_feld(("raum",), "beschreibung", "anders")
    tab._zeige()
    assert tab.titel.text() == "Möbliert · Vorlage ●"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("zimmer 3", True))
    assert tab.speichern()
    assert tab.titel.text() == "zimmer 3"
    tab.neu()
    assert tab.titel.text() == "Neuer Raum · nicht gespeichert ●"


def test_der_editor_passt_in_ein_kleines_fenster(tab):
    """1080 x 720 abzueglich Kopf (70), Seitenleiste (150) und Statuszeile (30)."""
    groesse = tab.minimumSizeHint()
    assert groesse.width() <= 930 and groesse.height() <= 600


# ------------------------------------------------------------ Tasten finden


def test_jedes_werkzeug_sagt_im_tooltip_wie_es_geht(tab):
    for name, knopf in tab._werkzeug_knoepfe.items():
        tipp = knopf.toolTip()
        assert tipp.startswith(knopf.text()) and "—" in tipp, name
    assert "Esc" in tab._werkzeug_knoepfe["wand"].toolTip()
    for name in ("wand", "block", "boden", "sperrzone", "tag", "start"):
        assert "Strg: ohne Raster" in tab._werkzeug_knoepfe[name].toolTip(), name
    assert "G" in tab._werkzeug_knoepfe["auswahl"].toolTip()


def test_die_tafel_nennt_alle_tasten():
    from spotlab.gui.raumeditor.tastentafel import TAFEL

    alles = " ".join(f"{taste} {was}" for _titel, zeilen in TAFEL for taste, was in zeilen)
    for taste in ("G", "R", "S", "X / Y / Z", "Zahl", "Enter", "Umschalt+D", "A", "Alt+A",
                  "Entf", "Esc", "Strg+Z", "Strg+Y", "Strg+S", "Home", "Tab", "Mausrad",
                  "Mittlere Maustaste", "Leertaste", "Rechts", "Pfeiltasten", "F1", "Strg"):
        assert taste in alles, taste


def _gezeigt(tab, qapp):
    tab.resize(1200, 760)
    tab.show()
    tab.activateWindow()
    qapp.processEvents()
    tab.waehle_raum("moebliert")
    return tab


def test_strg_z_wirkt_auch_mit_fokus_in_der_liste(tab, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    _gezeigt(tab, qapp)
    tab.steuerung.setze_feld(("raum",), "beschreibung", "geändert")
    tab.liste.setFocus()
    qapp.processEvents()
    QTest.keyClick(tab.liste, Qt.Key_Z, Qt.ControlModifier)
    assert tab.raum().beschreibung != "geändert"
    QTest.keyClick(tab.liste, Qt.Key_Y, Qt.ControlModifier)
    assert tab.raum().beschreibung == "geändert"


def test_entf_loescht_aus_der_liste_aber_nicht_aus_einem_eingabefeld(tab, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit

    _gezeigt(tab, qapp)
    bloecke = len(tab.raum().bloecke)
    tab.steuerung.auswahl = frozenset({("block", 0)})
    tab._zeige()
    name = tab.eigenschaften.findChild(QLineEdit, "feld_name")
    name.setFocus()
    name.setCursorPosition(0)
    qapp.processEvents()
    QTest.keyClick(name, Qt.Key_Delete)
    assert len(tab.raum().bloecke) == bloecke and name.text() == "isch"
    tab.liste.setFocus()
    qapp.processEvents()
    QTest.keyClick(tab.liste, Qt.Key_Delete)
    assert len(tab.raum().bloecke) == bloecke - 1


def test_strg_s_im_feld_speichert_den_getippten_wert_mit(tab, qapp, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QAbstractSpinBox, QInputDialog

    from spotlab.welt.raum import raum_laden

    tab.setze_arbeitsordner(tmp_path)
    _gezeigt(tab, qapp)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("mein raum", True))
    tab.steuerung.auswahl = frozenset({("block", 0)})
    tab._zeige()
    x = tab.eigenschaften.findChild(QAbstractSpinBox, "feld_x")
    x.setFocus()
    qapp.processEvents()
    x.selectAll()
    QTest.keyClicks(x, "3.7")
    assert x.text().startswith("3.7") and tab.raum().bloecke[0].x != pytest.approx(3.7)
    QTest.keyClick(x, Qt.Key_S, Qt.ControlModifier)          # ohne Enter
    assert raum_laden("mein raum", workspace=tmp_path).bloecke[0].x == pytest.approx(3.7)


def test_home_zeigt_alles_auch_wenn_ein_knopf_den_fokus_hat(tab, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    _gezeigt(tab, qapp)
    skala = tab.sicht.skala
    tab.sicht.zoome(3.0, 100, 100)
    tab.speichern_knopf.setFocus()
    qapp.processEvents()
    QTest.keyClick(tab.speichern_knopf, Qt.Key_Home)
    assert tab.sicht.skala == pytest.approx(skala)


def test_f1_und_der_knopf_zeigen_die_tastentafel(tab, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    _gezeigt(tab, qapp)
    assert tab.tasten_knopf.text() == "Tasten ?" and "F1" in tab.tasten_knopf.toolTip()
    tab.sicht.setFocus()
    qapp.processEvents()
    QTest.keyClick(tab.sicht, Qt.Key_F1)
    assert tab._tastentafel is not None and tab._tastentafel.isVisible()
    tab._tastentafel.close()
    tab.tasten_knopf.click()
    assert tab._tastentafel.isVisible()
    tab._tastentafel.close()
