"""Der Tab Raumeditor -- Qt-Haut ueber Steuerung und Sicht."""
import ast
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QDoubleSpinBox, QInputDialog  # noqa: E402

from spotlab.config import Config, Limits  # noqa: E402
from spotlab.gui.raumeditor import RaumeditorView  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import raum_laden  # noqa: E402


def test_der_editor_importiert_nichts_verbotenes():
    wurzel = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "gui" / "raumeditor"
    verboten = ("bosdyn", "spotlab.backends", "mujoco", "spotsim", "OpenGL", "numpy")
    for datei in wurzel.glob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        namen = set()
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Import):
                namen.update(t.name for t in knoten.names)
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                namen.add(knoten.module)
        # OpenGL nur in sicht3d.py -- und dort erst beim Zeigen (test_gui_raumeditor_sicht3d).
        erlaubt = ("OpenGL",) if datei.name == "sicht3d.py" else ()
        schlimm = [n for n in namen
                   if any(n.startswith(v) for v in verboten) and not n.startswith(erlaubt)]
        assert not schlimm, f"{datei.name} importiert {schlimm}"


def test_die_schnittstelle_fuer_app_py_steht(qapp):
    ansicht = RaumeditorView(DUNKEL)
    for name in ("meldung", "config_gespeichert", "start_gewuenscht", "setze_laeuft",
                 "setze_arbeitsordner", "setze_config", "waehle_raum", "raum", "raumname",
                 "startpose", "lade", "starten"):
        assert hasattr(ansicht, name), name


def test_vorlage_laden_und_abfragen(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    assert ansicht.raum().name == "Möbliert" and ansicht.raumname() == "moebliert"
    assert ansicht.startpose() == raum_laden("moebliert").start
    assert ansicht.liste.count() == 4 + 3 + 2 + 1              # Waende, Bloecke, Tags, Start


def test_klick_in_der_sicht_waehlt_und_die_liste_folgt(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.resize(900, 600)
    ansicht.waehle_raum("moebliert")
    ansicht.sicht.alles_zeigen()
    px, py = ansicht.sicht.meter_zu_schirm(3.1, 1.8)              # der Tisch
    QTest.mouseClick(ansicht.sicht, Qt.LeftButton, Qt.NoModifier, QPoint(int(px), int(py)))
    tisch = next(i for i, b_ in enumerate(ansicht.raum().bloecke) if b_.name == "Tisch")
    assert ansicht.steuerung.auswahl == {("block", tisch)}
    gewaehlt = [w.data(Qt.UserRole) for w in ansicht.liste.selectedItems()]
    assert gewaehlt == [("block", tisch)]


def test_zahlenfeld_aendert_das_modell_und_setzt_den_stern(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    tisch = next(i for i, b_ in enumerate(ansicht.raum().bloecke) if b_.name == "Tisch")
    ansicht.steuerung.auswahl = frozenset({("block", tisch)})
    ansicht._zeige()
    feld = ansicht.eigenschaften.findChild(object, "feld_drehung")
    feld.setValue(30.0)
    feld.editingFinished.emit()
    assert ansicht.raum().bloecke[tisch].drehung == 30.0
    assert ansicht.steuerung.geaendert and "*" in ansicht.titel.text()


def test_speichern_unter_schreibt_die_datei_und_die_konfiguration(qapp, tmp_path, monkeypatch):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.setze_config(Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(tmp_path)))
    ansicht.waehle_raum("leer")
    gespeichert = []
    ansicht.config_gespeichert.connect(gespeichert.append)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("mein zimmer", True))
    ansicht.steuerung.setze_feld(("raum",), "beschreibung", "meins")
    ansicht.speichern()
    assert (tmp_path / "raeume" / "mein zimmer.toml").is_file()
    assert raum_laden("mein zimmer", workspace=tmp_path).beschreibung == "meins"
    assert ansicht.raumname() == "mein zimmer" and not ansicht.steuerung.geaendert
    assert gespeichert[-1].raum == "mein zimmer"


def test_ein_start_im_hindernis_wird_nicht_gestartet(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    ansicht.steuerung.setze_feld(("start",), "x", 3.1)
    ansicht.steuerung.setze_feld(("start",), "y", 1.8)               # im Tisch
    meldungen, starts = [], []
    ansicht.meldung.connect(meldungen.append)
    ansicht.start_gewuenscht.connect(lambda: starts.append(True))
    ansicht.starten.click()
    assert starts == [] and any("Tisch" in m for m in meldungen)


def test_der_startknopf_meldet_nur_den_wunsch_und_sichert_raum_und_start(qapp, tmp_path):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_config(Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(tmp_path)))
    ansicht.waehle_raum("durchgang")
    gespeichert, starts = [], []
    ansicht.config_gespeichert.connect(gespeichert.append)
    ansicht.start_gewuenscht.connect(lambda: starts.append(True))
    ansicht.starten.click()
    assert starts == [True]
    assert gespeichert[-1].raum == "durchgang" and gespeichert[-1].raum_start.startswith("1.00,2.00")


def test_der_knopf_wird_zum_stopp(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_laeuft(True)
    assert "Stopp" in ansicht.starten.text()
    starts = []
    ansicht.start_gewuenscht.connect(lambda: starts.append(True))
    ansicht.starten.click()                                          # Stopp: der Wunsch geht raus
    assert starts == [True]
    ansicht.setze_laeuft(False)
    assert "starten" in ansicht.starten.text()


def test_lade_zeigt_raum_spur_und_anstoesse(qapp, tmp_path):
    lauf = tmp_path / "lauf"
    lauf.mkdir()
    (lauf / "ereignisse.jsonl").write_text(
        json.dumps({"t": 0, "art": "verbunden", "daten": {"raum": "moebliert"}}) + "\n"
        + json.dumps({"t": 1, "art": "angestossen", "daten": {"x": 2.0, "y": 1.0}}) + "\n",
        encoding="utf-8")
    (lauf / "zustand.jsonl").write_text(
        json.dumps({"t": 0, "daten": {"pose": [1.0, 1.0, 0.0]}}) + "\n"
        + json.dumps({"t": 1, "daten": {"pose": [1.5, 1.0, 0.0]}}) + "\n"
        + '{"t": 2, "daten": {"po',                                # halbe letzte Zeile
        encoding="utf-8")
    ansicht = RaumeditorView(DUNKEL)
    ansicht.lade(lauf)
    assert ansicht.raumname() == "moebliert"
    assert ansicht.sicht._spur == [(1.0, 1.0), (1.5, 1.0)]
    assert ansicht.sicht._anstoesse == [(2.0, 1.0)]


def test_das_nachspielen_ueberschreibt_keine_offenen_aenderungen(qapp, tmp_path):
    lauf = tmp_path / "lauf"
    lauf.mkdir()
    (lauf / "ereignisse.jsonl").write_text(
        json.dumps({"t": 0, "art": "verbunden", "daten": {"raum": "moebliert"}}) + "\n",
        encoding="utf-8")
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    ansicht.steuerung.setze_feld(("raum",), "beschreibung", "in Arbeit")
    ansicht.lade(lauf)
    assert ansicht.raum().beschreibung == "in Arbeit"


def test_der_umschalter_folgt_der_3d_verfuegbarkeit(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("leer")
    ansicht.show()
    qapp.processEvents()
    if ansicht.sicht3d.verfuegbar:
        assert ansicht.umschalter.isEnabled()
        ansicht.umschalter.click()
        assert ansicht.stapel.currentWidget() is ansicht.sicht3d
        ansicht._taste("tab", False, False, False)
        assert ansicht.stapel.currentWidget() is ansicht.sicht
    else:
        assert not ansicht.umschalter.isEnabled()
        ansicht._taste("tab", False, False, False)
        assert ansicht.stapel.currentWidget() is ansicht.sicht
        # Erzwungen gezeigt: statt eines schwarzen Fensters steht die Tafel.
        ansicht.stapel.setCurrentWidget(ansicht.sicht3d)
        ansicht.sicht3d.repaint()
        qapp.processEvents()
        assert ansicht.sicht3d.verfuegbar is False and "3D" in ansicht.sicht3d.tafel


def test_bereit_fuer_lauf_verlangt_einen_raum_auf_der_platte(qapp, tmp_path, monkeypatch):
    """Der Lauf vom 06.09.2026: die rekonstruierten Katakomben waren nie
    gespeichert, `SPOTLAB_RAUM` ging leer mit, MuJoCo fuhr ohne Waende --
    waehrend die Zeichnung die Waende zeigte."""
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.neu()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))   # abgebrochen
    grund = ansicht.bereit_fuer_lauf()
    assert grund and "gespeichert" in grund and ansicht.raumname() == ""
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("katakomben", True))
    assert ansicht.bereit_fuer_lauf() is None
    assert ansicht.raumname() == "katakomben"
    assert (tmp_path / "raeume" / "katakomben.toml").is_file()


def test_bereit_fuer_lauf_nennt_das_hindernis_und_speichert_dann_nicht(qapp, tmp_path, monkeypatch):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.waehle_raum("moebliert")
    ansicht.steuerung.setze_feld(("start",), "x", 3.1)
    ansicht.steuerung.setze_feld(("start",), "y", 1.8)               # im Tisch
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("x", True))
    grund = ansicht.bereit_fuer_lauf()
    assert "Tisch" in grund and not (tmp_path / "raeume").exists()


def test_eine_unveraenderte_vorlage_ist_bereit(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    assert ansicht.bereit_fuer_lauf() is None and ansicht.raumname() == "moebliert"


# ------------------------------------------------------------- Hoehe (Stufe 13)


def _raum_mit_podest():
    from spotlab.welt.raum import Boden, Raum

    return Raum(name="H", beschreibung="", start=(1, 1, 0), waende=((0, 0, 6, 0),),
                boeden=(Boden("P", 4, 2, 2, 2, z=1.2),))


def test_die_ebenenwahl_listet_die_boeden_und_setzt_z(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.steuerung.setze_raum(_raum_mit_podest())
    ansicht._zeige()
    eintraege = [ansicht.ebenenwahl.itemText(i) for i in range(ansicht.ebenenwahl.count())]
    assert eintraege == ["alle Ebenen", "0.00 m", "1.20 m"]
    ansicht.ebenenwahl.setCurrentIndex(2)
    assert ansicht.steuerung.ebene == 1.2
    assert ansicht.eigenschaften.findChild(object, "werkzeug_boden") is None      # der Knopf sitzt links
    assert ansicht.findChild(object, "werkzeug_boden") is not None
    st = ansicht.steuerung
    st.setze_werkzeug("block")
    st.druecke(1.0, 1.0)
    st.bewege(2.0, 2.0)
    st.lasse_los(2.0, 2.0)
    assert ansicht.raum().bloecke[-1].z == 1.2
    ansicht._zeige()
    assert ansicht.ebenenwahl.currentIndex() == 2 and st.ebene == 1.2           # die Wahl ueberlebt das Neuzeichnen


def test_die_felder_eines_bodens(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.steuerung.setze_raum(_raum_mit_podest())
    ansicht.steuerung.auswahl = frozenset({("boden", 0)})
    ansicht._zeige()
    for name in ("feld_z", "feld_anstieg", "feld_stufen", "feld_drehung"):
        assert ansicht.eigenschaften.findChild(object, name) is not None, name
    feld = ansicht.eigenschaften.findChild(object, "feld_stufen")
    feld.setValue(6)
    feld.editingFinished.emit()
    assert ansicht.raum().boeden[0].stufen == 6
    assert any("(Podest)" in ansicht.liste.item(i).text() for i in range(ansicht.liste.count()))


def test_der_weg_wird_mit_dem_pauspapier_gespeichert_und_geladen(qapp, tmp_path):
    from spotlab.maps.rekonstruktion import Ergebnis
    from spotlab.welt.raum import raum_laden as _laden

    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    bericht = {"waende": 0, "tags": 0, "treppen": 0, "rampen": 0, "boeden": 0, "hinweise": []}
    ergebnis = Ergebnis(_laden("leer"), [(1.0, 1.0)], bericht, weg=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.2)])
    ansicht.uebernimm_rekonstruktion(ergebnis)
    assert ansicht._weg == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.2)]
    assert ansicht._schreibe("wegtest")
    ansicht.neu()
    assert ansicht._weg == []
    ansicht.waehle_raum("wegtest")
    assert ansicht._weg == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.2)] and ansicht._pauspapier == [(1.0, 1.0)]


def test_ein_neuer_raum_leert_markierung_und_offene_raender(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("leer")
    ansicht.sicht.setze_markierung([(0, 0, 1, 1)])
    ansicht.sicht.setze_kandidaten([(0, 0, 1, 1)])
    ansicht.sicht.setze_offen([(0.5, 0.5)])
    ansicht.neu()
    assert ansicht.sicht._markierung == [] and ansicht.sicht._kandidaten == [] and ansicht.sicht._offen == []


def test_die_liste_zeigt_das_gelaende_nur_lesend_und_entf_loescht_es(qapp):
    from spotlab.welt import bearbeitung as b
    from spotlab.welt import gelaende as g
    from spotlab.welt.raum import Raum

    ansicht = RaumeditorView(DUNKEL)
    raum = Raum("G", "", (0.5, 0.5, 0.0), waende=[(0, 0, 3, 0)],
                gelaende=g.gitter(0.0, 0.0, 0.5, 5, 5, lambda x, y: 0.1 * x))
    ansicht._setze(raum, "", False, True)
    texte = [ansicht.liste.item(i).text() for i in range(ansicht.liste.count())]
    assert any(t.startswith("Gelände · 0.5 m · 25 Knoten") for t in texte)
    ansicht.steuerung.auswahl = frozenset({b.GELAENDE})
    ansicht._zeige()
    assert ansicht._form.rowCount() == 2 and ansicht.findChild(QDoubleSpinBox, "feld_x0") is None
    ansicht.steuerung.taste("delete")
    assert ansicht.steuerung.raum.gelaende is None


def test_der_tab_uebernimmt_eine_korrektur_als_einen_verlaufsschritt(qapp):
    from PySide6.QtWidgets import QPushButton

    from spotlab.gui.raumeditor.korrektur_dialog import Korrektur
    from spotlab.welt import gelaende as g
    from spotlab.welt.raum import Raum

    ansicht = RaumeditorView(DUNKEL)
    assert ansicht.findChild(QPushButton, "knopf_korrigieren") is not None
    ansicht.waehle_raum("leer")
    alt = ansicht.steuerung.raum
    neu = Raum("K", "", (1.0, 1.0, 0.0), waende=[(0, 0, 4, 0)],
               gelaende=g.gitter(0.0, 0.0, 0.5, 5, 5, lambda x, y: 0.1))
    meldungen = []
    ansicht.meldung.connect(meldungen.append)
    bericht = {"waende_verbunden": 2, "durchgaenge": 1, "geloescht": 0,
               "gelaende": {"knoten": 25, "z_min": 0.0, "z_max": 0.1, "offen": 1}}
    ansicht.uebernimm_korrektur(Korrektur(neu, [(0.5, 0.5)], bericht))
    assert ansicht.steuerung.raum is neu and ansicht.steuerung.geaendert
    assert ansicht.sicht._offen == [(0.5, 0.5)]
    assert meldungen[-1].startswith("Korrigiert: 2 Wände verbunden, 1 Durchgang, 0 Wände gelöscht")
    assert "25 Knoten" in meldungen[-1] and "1 offener Rand" in meldungen[-1]
    ansicht.steuerung.rueckgaengig()
    assert ansicht.steuerung.raum == alt


def test_korrigieren_oeffnet_den_dialog_nicht_modal(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("durchgang")
    ansicht._korrigieren()
    dialog = ansicht._korrektur_dialog
    assert dialog is not None and dialog.isVisible() and not dialog.isModal()
    dialog.close()
