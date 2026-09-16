"""Datenverlust, alte Korrekturen und Ebenenauswahl aus dem GUI-Audit."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from spotlab.gui.raumeditor.steuerung import Steuerung
from spotlab.welt.raum import Raum, Wand


def etagen():
    return Raum("Etagen", "", (10, 10, 0),
                waende=(Wand(0, 0, 2, 0), Wand(0, 0, 2, 0, z=3)))


def test_auswahl_und_rahmen_bleiben_auf_der_aktiven_ebene():
    st = Steuerung(etagen())
    st.setze_ebene(3)
    st.druecke(1, 0)
    st.lasse_los(1, 0)
    assert st.auswahl == {("wand", 1)}
    st.druecke(-1, -1)
    st.bewege(3, 1)
    st.lasse_los(3, 1)
    assert st.auswahl == {("wand", 1)}
    st.taste("a")
    assert st.auswahl == {("wand", 1)}
    st.setze_ebene(0)
    assert not st.auswahl


def test_fang_ignoriert_endpunkte_anderer_etagen():
    st = Steuerung(Raum("EG", "", (10, 10, 0), waende=(Wand(0, 0, 2, 0),)))
    st.setze_ebene(3)
    st.setze_werkzeug("wand")
    st.druecke(0.1, 0)
    assert st.kette == (0.1, 0)
    st.druecke(1, 1)
    assert st.raum.waende[-1].z == 3


def test_undo_redo_beenden_den_wandzug():
    st = Steuerung(etagen())
    st.setze_werkzeug("wand")
    st.druecke(3, 3)
    st.druecke(4, 3)
    st.taste("z", ctrl=True)
    assert len(st.raum.waende) == 2 and st.kette is None
    st.druecke(5, 3)
    assert len(st.raum.waende) == 2
    st.taste("y", ctrl=True)
    assert len(st.raum.waende) == 3 and st.kette is None


@pytest.fixture
def editor(qapp):
    from spotlab.gui.raumeditor.tab import RaumeditorView
    from spotlab.gui.theme import DUNKEL

    view = RaumeditorView(DUNKEL)
    yield view
    if view._korrektur_dialog is not None:
        view._korrektur_dialog.close()


@pytest.mark.parametrize("aktion", ["neu", "vorlage", "rekonstruktion"])
def test_abbrechen_behaelt_entwurf_und_verlauf(editor, monkeypatch, aktion):
    from PySide6.QtWidgets import QMessageBox

    editor.steuerung.setze_feld(("raum",), "beschreibung", "Nicht verlieren")
    raum, verlauf = editor.raum(), editor.steuerung.verlauf
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.Cancel)
    if aktion == "neu":
        editor.neu()
    elif aktion == "vorlage":
        editor.waehle_raum("moebliert")
    else:
        editor.uebernimm_rekonstruktion(SimpleNamespace(raum=etagen(), pauspapier=[]))
    assert editor.raum() is raum
    assert editor.steuerung.verlauf is verlauf


def test_speichern_vor_neu_und_abgebrochener_speicherdialog(editor, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from spotlab.welt.raum import raum_laden

    editor.setze_arbeitsordner(tmp_path)
    editor.steuerung.setze_feld(("raum",), "beschreibung", "Behalten")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.Save)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    editor.neu()
    assert editor.raum().beschreibung == "Behalten"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("entwurf", True))
    editor.neu()
    assert raum_laden("entwurf", workspace=tmp_path).beschreibung == "Behalten"
    assert editor.raum().name == "Neuer Raum"


def test_verwerfen_wechselt_den_raum(editor, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    editor.steuerung.setze_feld(("raum",), "beschreibung", "Verwerfen")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.Discard)
    editor.neu()
    assert editor.raum().beschreibung == ""


@pytest.mark.parametrize("wechsel", [False, True])
def test_alte_korrektur_ueberschreibt_nichts(editor, monkeypatch, wechsel):
    from PySide6.QtWidgets import QMessageBox

    editor._korrigieren()
    dialog = editor._korrektur_dialog
    alt = editor.raum()
    if wechsel:
        editor.waehle_raum("moebliert")
    else:
        editor.steuerung.setze_feld(("raum",), "beschreibung", "Neuere Arbeit")
    aktuell = editor.raum()
    meldungen = []
    editor.meldung.connect(meldungen.append)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: QMessageBox.Cancel)
    dialog.angewendet.emit(SimpleNamespace(raum=replace(alt, beschreibung="Alt")))
    assert editor.raum() is aktuell
    assert any("nicht übernommen" in m for m in meldungen)


def test_korrektur_nach_undo_ist_ebenfalls_veraltet(editor):
    editor._korrigieren()
    dialog = editor._korrektur_dialog
    alt = editor.raum()
    editor.steuerung.setze_feld(("raum",), "beschreibung", "Zwischenstand")
    editor.steuerung.rueckgaengig()
    assert editor.raum() is alt
    dialog.angewendet.emit(SimpleNamespace(raum=replace(alt, beschreibung="Alt")))
    assert editor.raum() is alt


def test_aktuelle_korrektur_kommt_als_undo_schritt_an(editor):
    editor._korrigieren()
    alt = editor.raum()
    neu = replace(alt, beschreibung="Korrigiert")
    editor._korrektur_dialog.angewendet.emit(SimpleNamespace(
        raum=neu, offene_raender=[],
        bericht={"waende_verbunden": 0, "durchgaenge": 0, "geloescht": 0}))
    assert editor.raum() is neu
    editor.steuerung.rueckgaengig()
    assert editor.raum() is alt


def test_speichern_unter_fragt_vor_ersetzen_und_entfernt_alte_messdaten(
        editor, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from spotlab.welt import pauspapier
    from spotlab.welt.raum import raum_laden, raum_pfad, raum_speichern

    editor.setze_arbeitsordner(tmp_path)
    pfad = raum_pfad(tmp_path, "vorhanden")
    raum_speichern(etagen(), pfad)
    nebenan = pauspapier.pfad_zu(pfad)
    pauspapier.schreibe(nebenan, [(1, 2)], weg=[(1, 2, 0), (2, 2, 0)])
    vorher = pfad.read_bytes()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("vorhanden", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.No)
    assert not editor.speichern_unter()
    assert pfad.read_bytes() == vorher and nebenan.exists()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.Yes)
    assert editor.speichern_unter()
    assert not nebenan.exists()
    assert raum_laden("vorhanden", workspace=tmp_path) == editor.raum()
    editor.waehle_raum("vorhanden")
    assert editor._pauspapier == [] and editor._weg == []


def test_fokus_ohne_aenderung_erzeugt_keinen_verlaufsschritt(editor):
    revision = editor.steuerung.revision
    editor.steuerung.setze_feld(("raum",), "name", editor.raum().name)
    assert editor.steuerung.revision == revision
    assert not editor.steuerung.geaendert


def test_rekonstruktion_entwertet_ergebnis_bei_neuen_eingaben(qapp):
    from PySide6.QtWidgets import QDialogButtonBox

    from spotlab.gui.raumeditor.rekonstruktion_dialog import RekonstruktionsDialog

    dialog = RekonstruktionsDialog(None, None)
    ok = dialog.knoepfe.button(QDialogButtonBox.Ok)
    dialog.ergebnis = object()
    ok.setEnabled(True)
    dialog.zelle.setValue(0.1)
    assert dialog.ergebnis is None and not ok.isEnabled()
    dialog.accept()
    assert dialog.result() == 0
    # Eine Antwort zu den alten Eingaben darf die Freigabe nicht wieder setzen.
    dialog._auftrag_revision = dialog._eingabe_revision - 1
    dialog._fertig(object())
    assert dialog.ergebnis is None and not ok.isEnabled()
    dialog.ergebnis = object()
    ok.setEnabled(True)
    dialog._fehler("Testfehler")
    assert dialog.ergebnis is None and not ok.isEnabled()


def test_blockziehen_uebersteht_gui_aktualisierung_auf_allen_ebenen(editor):
    editor._werkzeug("block")
    editor._gedrueckt(2, 2, "links", False, False)
    editor._bewegt(3, 2.4, False)
    editor._losgelassen(3, 2.4, False, False)
    block = editor.raum().bloecke[-1]
    assert block.breite == pytest.approx(1)
    assert block.tiefe == pytest.approx(0.4)


def test_wandkette_uebersteht_gui_aktualisierung_auf_allen_ebenen(editor):
    anzahl = len(editor.raum().waende)
    editor._werkzeug("wand")
    editor._gedrueckt(2, 2, "links", False, False)
    editor._losgelassen(2, 2, False, False)
    editor._gedrueckt(3, 2, "links", False, False)
    editor._losgelassen(3, 2, False, False)
    assert len(editor.raum().waende) == anzahl + 1
