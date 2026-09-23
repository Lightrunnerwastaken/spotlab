"""Befunde der Pruefung des Raumeditors vom 23.09.2026 (Probeskripte p01-p20).

Je Befund ein Test, der den Fehler zeigt. Die Steuerung wird ohne Fenster
geprueft; wo es um die Haut geht (Felder, Tasten, Dialoge), mit dem `qapp`.
"""
import threading
from dataclasses import replace

import pytest

from spotlab.gui.raumeditor.steuerung import Steuerung
from spotlab.welt import bearbeitung as b
from spotlab.welt.raum import Raum, raum_laden, raum_speichern

FUENF_WAENDE = Raum(name="Test", beschreibung="", start=(1.0, 2.0, 0.0), waende=(
    (3.0, 1.0, 3.0, 3.0),                                    # Wand 1: quer ueber den Weg
    (0, 0, 6, 0), (6, 0, 6, 4), (6, 4, 0, 4), (0, 4, 0, 0),   # Wand 2..5: aussen
))
WEG = [(1.0, 2.0, 0.0), (2.0, 2.0, 0.0), (4.0, 2.0, 0.0), (5.0, 2.0, 0.0)]


# ------------------------------------------------ 1. Auswahl nach „Korrigieren"


def test_ein_raum_von_aussen_leert_die_auswahl_und_ist_ein_schritt():
    """p02: die Auswahl zeigte danach auf alte Indizes -- IndexError bei jeder
    Mausbewegung, Entf loeschte eine ANDERE Wand."""
    st = Steuerung(FUENF_WAENDE)
    st.auswahl = frozenset({("wand", 4)})
    ohne_erste = replace(st.raum, waende=st.raum.waende[1:])
    st.ersetze_raum(ohne_erste)
    assert st.auswahl == frozenset() and st.raum is ohne_erste and st.geaendert
    st.bewege(2.0, 2.0)                                   # warf IndexError
    st.druecke(3.0, 0.0)
    st.lasse_los(3.0, 0.0)
    assert st.rueckgaengig() and st.raum == FUENF_WAENDE


def test_ein_raum_von_aussen_beendet_eine_offene_geste():
    st = Steuerung(FUENF_WAENDE)
    st.auswahl = frozenset({("wand", 2)})
    st.taste("g")
    st.bewege(1.0, 1.0)
    neu = replace(FUENF_WAENDE, beschreibung="korrigiert")
    st.ersetze_raum(neu)
    assert not st.modus.aktiv and st.raum is neu
    st.taste("escape")
    assert st.raum is neu                                 # der Abbruch holt nichts Altes zurueck


def test_korrigieren_leert_die_auswahl_im_tab(qapp):
    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    tab = RaumeditorView(DUNKEL)
    tab._setze(FUENF_WAENDE, "", False, True, (), WEG)
    tab.steuerung.auswahl = frozenset({("wand", 2)})
    tab._zeige()
    tab._korrigieren()
    dialog = tab._korrektur_dialog
    dialog.gelaende_bauen.setChecked(False)
    dialog.anwenden.click()                               # die kreuzende Wand 1 wird geloescht
    qapp.processEvents()
    assert len(tab.steuerung.raum.waende) == 4
    assert tab.steuerung.auswahl == frozenset()
    tab._taste("delete", False, False, False)             # loescht nichts Falsches
    assert len(tab.steuerung.raum.waende) == 4
    tab._bewegt(2.0, 2.0, False)


# --------------------------------------------------- 2. G, Z mit einer Sperrzone


def test_heben_laesst_sperrzonen_liegen():
    """p01: eine Zone hat keine Hoehe -- `hebe` warf AttributeError."""
    raum, zone = b.neue_sperrzone(FUENF_WAENDE, 2.0, 2.0, 1.0, 1.0)
    gehoben = b.hebe(raum, frozenset({zone, ("wand", 0)}), 0.5)
    assert gehoben.sperrzonen == raum.sperrzonen
    assert gehoben.waende[0].z == 0.5


def test_g_z_nach_a_mit_einer_zone_in_der_auswahl():
    raum, zone = b.neue_sperrzone(FUENF_WAENDE, 2.0, 2.0, 1.0, 1.0)
    st = Steuerung(raum)
    st.taste("a")
    assert zone in st.auswahl
    st.zeiger = (1.0, 1.0)
    assert st.taste("g") and st.taste("z")
    st.bewege(1.0, 1.5)
    assert st.taste("return")
    assert st.raum.waende[0].z == pytest.approx(0.5) and st.raum.sperrzonen == raum.sperrzonen


# ----------------------------------------------- 7b. Entf waehrend des Ziehens


def test_entf_waehrend_des_ziehens_holt_nichts_aus_dem_schnappschuss():
    """p19: Entf loeschte den Block aus der Vorschau, die naechste Mausbewegung
    rechnete aus dem Schnappschuss und holte ihn zurueck."""
    st = Steuerung(raum_laden("moebliert"))
    tisch = st.raum.bloecke[0]
    st.druecke(tisch.x, tisch.y)
    st.bewege(tisch.x + 0.5, tisch.y)
    assert not st.taste("delete")                         # beim Ziehen gesperrt
    st.bewege(tisch.x + 1.0, tisch.y)
    st.lasse_los(tisch.x + 1.0, tisch.y)
    assert [k.name for k in st.raum.bloecke][0] == "Tisch"
    assert st.raum.bloecke[0].x == pytest.approx(tisch.x + 1.0)
    assert st.rueckgaengig() and st.raum.bloecke[0].x == pytest.approx(tisch.x)


def test_escape_waehrend_des_ziehens_bricht_das_ziehen_ab():
    st = Steuerung(raum_laden("moebliert"))
    tisch = st.raum.bloecke[0]
    st.druecke(tisch.x, tisch.y)
    st.bewege(tisch.x + 0.5, tisch.y)
    assert st.taste("escape")
    assert st.raum.bloecke[0].x == pytest.approx(tisch.x)
    st.bewege(tisch.x + 1.0, tisch.y)
    st.lasse_los(tisch.x + 1.0, tisch.y)
    assert st.raum.bloecke[0].x == pytest.approx(tisch.x) and not st.geaendert


# ------------------------------------------ 7a. 3D: Loslassen ueber dem Horizont


def test_3d_loslassen_ueber_dem_horizont_beendet_das_ziehen(qapp):
    """p10: kein `losgelassen` -- der Block klebte an der Maus und stand nicht im Verlauf."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QVector3D
    from PySide6.QtWidgets import QApplication

    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    tab = RaumeditorView(DUNKEL)
    tab.waehle_raum("moebliert")
    s3 = tab.sicht3d
    s3.resize(800, 600)
    s3.verfuegbar = True
    s3.treffer = lambda px, py: None
    s3.alles_zeigen()
    s3.kamera.elevation = 10.0
    st = tab.steuerung
    block = st.raum.bloecke[0]

    def pixel(x, y):
        p = s3._mvp().map(QVector3D(x, y, 0.0))
        return QPointF((p.x() + 1) / 2 * s3.width(), (1 - p.y()) / 2 * s3.height())

    def maus(art, punkt, knoepfe):
        knopf = Qt.LeftButton if art != QMouseEvent.MouseMove else Qt.NoButton
        QApplication.sendEvent(s3, QMouseEvent(art, punkt, punkt, knopf, knoepfe, Qt.NoModifier))

    assert s3.bodenpunkt(400, 5) is None                  # oben ist Himmel
    maus(QMouseEvent.MouseButtonPress, pixel(block.x, block.y), Qt.LeftButton)
    maus(QMouseEvent.MouseMove, pixel(block.x + 1.0, block.y), Qt.LeftButton)
    maus(QMouseEvent.MouseButtonRelease, QPointF(400, 5), Qt.NoButton)
    assert st._zug is None and st.geaendert and st.verlauf.kann_zurueck
    x_danach = st.raum.bloecke[0].x
    maus(QMouseEvent.MouseMove, pixel(block.x - 1.0, block.y + 1.0), Qt.NoButton)
    assert st.raum.bloecke[0].x == x_danach               # klebt nicht an der Maus


# -------------------------------------------------------- 4. Speichern im Modus


def _arbeitsordner(tmp_path, raum=None, name="probe"):
    raum_speichern(raum if raum is not None else raum_laden("leer"),
                   tmp_path / "raeume" / f"{name}.toml")
    return tmp_path


def test_strg_s_waehrend_g_speichert_nicht_die_vorschau(qapp, tmp_path):
    """p07: gespeichert wurde die Vorschau, danach zeigte der Editor etwas
    anderes als die Datei, und `geaendert` war falsch."""
    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    ws = _arbeitsordner(tmp_path)
    tab = RaumeditorView(DUNKEL)
    tab.setze_arbeitsordner(ws)
    tab.waehle_raum("probe")
    st = tab.steuerung
    st.auswahl = frozenset({("wand", 0)})
    st.zeiger = (1.0, 0.0)
    tab._taste("g", False, False, False)
    tab._bewegt(1.0, 2.0, False)                          # Vorschau: 2 m nach oben
    tab._taste("s", False, True, False)                   # Strg+S
    tab._taste("escape", False, False, False)
    assert not st.modus.aktiv
    assert raum_laden("probe", workspace=ws) == st.raum   # Editor und Datei gleich
    assert not st.geaendert


def test_der_speicherknopf_beendet_einen_offenen_zug(qapp, tmp_path):
    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    ws = _arbeitsordner(tmp_path, raum_laden("moebliert"))
    tab = RaumeditorView(DUNKEL)
    tab.setze_arbeitsordner(ws)
    tab.waehle_raum("probe")
    st = tab.steuerung
    tisch = st.raum.bloecke[0]
    tab._gedrueckt(tisch.x, tisch.y, "links", False, False)
    tab._bewegt(tisch.x + 1.0, tisch.y, False)            # Maus noch gedrueckt
    assert tab.speichern()
    assert st._zug is None and st.raum.bloecke[0].x == pytest.approx(tisch.x)   # abgebrochen
    assert raum_laden("probe", workspace=ws) == st.raum and not st.geaendert


# ---------------------------------------------------- 5. Text mit Zeilenumbruch


def test_steuerzeichen_im_text_ueberstehen_speichern_und_laden(tmp_path):
    """p11: ein eingefuegter Zeilenumbruch machte die Raumdatei unladbar."""
    raum, _ = b.neue_sperrzone(raum_laden("leer"), 2.0, 2.0, 1.0, 1.0,
                               grund="Glasfront\nnicht sichtbar\tfür die \"Kamera\" \\ \x01\x7f")
    raum = replace(raum, name="Zeile 1\r\nZeile 2", beschreibung="ä\bö\fü")
    pfad = tmp_path / "raeume" / "probe.toml"
    raum_speichern(raum, pfad)
    from spotlab.welt.raum import raum_laden_pfad

    zurueck = raum_laden_pfad(pfad)
    assert zurueck.sperrzonen[0].grund == raum.sperrzonen[0].grund
    assert zurueck.name == raum.name and zurueck.beschreibung == raum.beschreibung


# ----------------------------------------------------- 6. Pauspapier unlesbar


def test_ein_unlesbares_pauspapier_bleibt_beim_speichern_liegen(qapp, tmp_path):
    """p14: war das Pauspapier beim Oeffnen nicht lesbar, loeschte das naechste
    Speichern es -- die Messdaten einer ganzen Kartenfahrt."""
    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL
    from spotlab.welt import pauspapier

    ws = _arbeitsordner(tmp_path, name="gang")
    pp = pauspapier.pfad_zu(ws / "raeume" / "gang.toml")
    pauspapier.schreibe(pp, [(i * 0.01, 1.0) for i in range(500)], weg=[(0, 0, 0), (1, 1, 0)])
    roh = pp.read_bytes()[:-3]                            # abgeschnitten
    pp.write_bytes(roh)
    tab = RaumeditorView(DUNKEL)
    tab.setze_arbeitsordner(ws)
    meldungen = []
    tab.meldung.connect(meldungen.append)
    tab.waehle_raum("gang")
    assert any("Pauspapier" in m and "nicht" in m for m in meldungen)
    tab.steuerung.setze_feld(("start",), "x", 1.5)
    assert tab.speichern()
    assert pp.read_bytes() == roh                         # unangetastet


# --------------------------------------- 8. Klippen des Gelaendes ohne Boeden


def _gelaende_raum():
    from spotlab.welt.gelaende import gitter

    gel = gitter(0.0, 0.0, 0.2, 21, 31, lambda x, y: 0.0 if x < 3.0 else 1.0)
    return Raum(name="G", beschreibung="", start=(3.0, 2.0, 0.0), gelaende=gel,
                waende=((0, 0, 6, 0), (6, 0, 6, 4), (6, 4, 0, 4), (0, 4, 0, 0)))


# ------------------------------------------------------ 9. Arbeit im GUI-Thread


# ------------------------------------------------- 10. Korrigieren abbrechen


def _langsamer_bau(monkeypatch):
    """Ein Gelaendebau, der wartet, bis der Test ihn freigibt -- statt einer festen Frist."""
    from spotlab.gui.raumeditor import korrektur_dialog as kd

    frei = threading.Event()
    echt = kd.baue_gelaende

    def langsam(*a, **kw):
        frei.wait(30)
        return echt(*a, **kw)

    monkeypatch.setattr(kd, "baue_gelaende", langsam)
    return frei


def _tab_mit_weg(qapp):
    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    tab = RaumeditorView(DUNKEL)
    weg = [(1.0, 1.0, 0.0), (2.0, 1.5, 0.0), (3.0, 2.0, 0.0), (4.0, 2.0, 0.0)]
    tab._setze(raum_laden("leer"), "", False, False, (), weg)
    return tab


# ---------------------------------------------------- 11. Rueckgaengig nach Lauf


def test_ein_lauf_im_offenen_raum_laesst_den_verlauf_stehen(qapp, tmp_path):
    """p08: `lade()` lud den offenen Raum neu -- nach jedem Lauf war Strg+Z weg."""
    import json

    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    ws = _arbeitsordner(tmp_path)
    tab = RaumeditorView(DUNKEL)
    tab.setze_arbeitsordner(ws)
    tab.waehle_raum("probe")
    st = tab.steuerung
    st.setze_feld(("wand", 0), "y1", 0.5)
    assert tab.speichern() and st.verlauf.kann_zurueck
    lauf = tmp_path / "lauf"
    lauf.mkdir()
    (lauf / "ereignisse.jsonl").write_text(
        json.dumps({"art": "verbunden", "daten": {"raum": "probe"}}) + "\n", encoding="utf-8")
    (lauf / "zustand.jsonl").write_text(
        json.dumps({"daten": {"pose": [1.0, 1.0, 0.0]}}) + "\n", encoding="utf-8")
    tab.lade(lauf)
    assert st.verlauf.kann_zurueck and tab.sicht._spur == [(1.0, 1.0)]
    assert st.rueckgaengig() and st.raum.waende[0].y1 == 0.0


# ---------------------------------------------------------- 12. Tab schaltet 3D


# -------------------------------------------------- 18. Die erste 2D-Ansicht


# --------------------------------------------------------- 3. Zahlenfelder


PROBE_TOML = """[raum]
name = "Probe"
beschreibung = ""
start = [1.0, 1.0, -90.0]
waende = [
    [0.0, 0.0, 6.1234, 0.0],
]

[[block]]
name = "Kiste"
mitte = [3.0, 2.0]
groesse = [1.0, 0.5, 0.75]
drehung = -30.0
"""


def _tab_mit_probe(qapp, tmp_path):
    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    (tmp_path / "raeume").mkdir()
    (tmp_path / "raeume" / "probe.toml").write_text(PROBE_TOML, encoding="utf-8")
    tab = RaumeditorView(DUNKEL)
    tab.setze_arbeitsordner(tmp_path)
    tab.resize(1000, 700)
    tab.show()
    tab.activateWindow()
    qapp.processEvents()
    tab.waehle_raum("probe")
    return tab


def _feld(tab, qapp, schluessel, feld):
    from PySide6.QtWidgets import QAbstractSpinBox

    tab.steuerung.auswahl = frozenset({schluessel})
    tab._zeige()
    qapp.processEvents()
    return tab.eigenschaften.findChild(QAbstractSpinBox, f"feld_{feld}")


@pytest.mark.parametrize("schluessel, feld, anzeige", [
    (("start",), "grad", -90.0), (("wand", 0), "x2", 6.1234), (("block", 0), "drehung", -30.0)])
def test_durch_ein_feld_klicken_aendert_den_raum_nicht(qapp, tmp_path, schluessel, feld, anzeige):
    """p03: Hineinklicken und Verlassen schrieb den Wert zurueck -- -90 Grad
    wurden 0, 6.1234 wurde 6.12, und jedes Mal ein Verlaufsschritt."""
    from PySide6.QtCore import Qt

    tab = _tab_mit_probe(qapp, tmp_path)
    vorher = tab.steuerung.raum
    w = _feld(tab, qapp, schluessel, feld)
    assert w.value() == pytest.approx(anzeige)
    w.setFocus(Qt.MouseFocusReason)
    qapp.processEvents()
    tab.sicht.setFocus(Qt.MouseFocusReason)
    qapp.processEvents()
    w.editingFinished.emit()                              # auch ein ausdrueckliches Ende aendert nichts
    assert tab.steuerung.raum is vorher and not tab.steuerung.geaendert
    assert not tab.steuerung.verlauf.kann_zurueck
    tab.close()


def test_ein_geaenderter_winkel_wird_geschrieben_und_normalisiert(qapp, tmp_path):
    tab = _tab_mit_probe(qapp, tmp_path)
    w = _feld(tab, qapp, ("start",), "grad")
    w.setValue(-45.0)
    w.editingFinished.emit()
    assert tab.steuerung.raum.start[2] % 360.0 == pytest.approx(315.0)
    assert tab.steuerung.geaendert and tab.steuerung.verlauf.kann_zurueck
    w = _feld(tab, qapp, ("wand", 0), "x2")
    w.setValue(6.2345)
    w.editingFinished.emit()
    assert tab.steuerung.raum.waende[0].x2 == pytest.approx(6.2345)
    tab.close()


def test_nach_einem_feld_bleiben_die_felder_stehen(qapp, tmp_path):
    """Tab von Feld zu Feld: die Felder werden aktualisiert, nicht neu gebaut --
    sonst ist der Fokus nach jedem Wert weg."""
    tab = _tab_mit_probe(qapp, tmp_path)
    x = _feld(tab, qapp, ("block", 0), "x")
    y = tab.eigenschaften.findChild(type(x), "feld_y")
    x.setValue(3.5)
    x.editingFinished.emit()
    assert tab.steuerung.raum.bloecke[0].x == pytest.approx(3.5)
    assert tab.eigenschaften.findChild(type(x), "feld_y") is y
    tab.close()


# ------------------------------------------------------------- weitere kleine


def test_ein_eigener_raum_darf_nicht_wie_eine_vorlage_heissen(qapp, tmp_path, monkeypatch):
    """p16: ein eigener Raum „leer" verdeckte die Vorlage -- „Vorlage laden… leer"
    oeffnete ihn, und `SPOTLAB_RAUM=leer` waere mehrdeutig."""
    from PySide6.QtWidgets import QInputDialog

    from spotlab.gui.raumeditor import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    tab = RaumeditorView(DUNKEL)
    tab.setze_arbeitsordner(tmp_path)
    tab.neu()
    meldungen = []
    tab.meldung.connect(meldungen.append)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("leer", True))
    assert not tab.speichern_unter()
    assert not (tmp_path / "raeume" / "leer.toml").exists()
    assert any("Vorlage" in m for m in meldungen)
