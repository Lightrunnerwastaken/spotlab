"""Der Dialog Korrigieren: Tabelle der Luecken, Vorschlaege, Anwenden mit und ohne Gelaende."""

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from spotlab.gui.raumeditor.korrektur_dialog import KorrekturDialog  # noqa: E402
from spotlab.welt.korrektur import finde_luecken  # noqa: E402
from spotlab.welt.raum import Boden, Raum, Wand  # noqa: E402


def _punkte_auf(x1, y1, x2, y2, n=40):
    return [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]


def _l_gang():
    """L-Gang wie im Gelaendebau-Test, unten mit einer 0.6-m-Bruchstelle (Punkte drin),
    rechts mit einer 1-m-Luecke, durch die der Roboter hinausging; eine Rampe im Gang."""
    waende = [Wand(0, 0, 3.5, 0), Wand(4.1, 0, 8, 0), Wand(0, 0, 0, 2), Wand(0, 2, 6, 2),
              Wand(6, 2, 6, 8), Wand(8, 0, 8, 4), Wand(8, 5, 8, 8), Wand(6, 8, 8, 8)]
    weg = [(1.0, 1.0, 0.0), (7.0, 1.0, 0.42), (7.0, 7.0, 0.42), (7.0, 4.5, 0.42), (9.0, 4.5, 0.42)]
    punkte = _punkte_auf(3.5, 0.0, 4.1, 0.0)
    raum = Raum("L", "", (1.0, 1.0, 0.0), waende=waende,
                boeden=(Boden("Rampe 1", 4.0, 1.0, 6.0, 1.8, anstieg=0.42),))
    return raum, weg, punkte


def _warte_auf(signal, dialog, sekunden=30):
    schleife = QEventLoop()
    ergebnis = []
    signal.connect(lambda k: (ergebnis.append(k), schleife.quit()))
    QTimer.singleShot(int(sekunden * 1000), schleife.quit)
    dialog.anwenden.click()
    schleife.exec()
    return ergebnis


def test_die_tabelle_zeigt_kandidaten_mit_vorschlag_und_grund(qapp):
    raum, weg, punkte = _l_gang()
    dialog = KorrekturDialog(None, raum, weg, punkte)
    luecken = finde_luecken(raum, weg, punkte)
    assert dialog.tabelle.rowCount() == len(luecken) > 0
    zeilen = {(dialog.tabelle.item(r, 1).text(), dialog.tabelle.cellWidget(r, 3).currentText())
              for r in range(dialog.tabelle.rowCount())}
    assert ("Lücke", "Wand") in zeilen and ("Lücke", "Durchgang") in zeilen
    gruende = [dialog.tabelle.item(r, 4).text() for r in range(dialog.tabelle.rowCount())]
    assert any("lief hindurch" in g for g in gruende) and any("Punkte" in g for g in gruende)
    assert dialog.boeden_aufloesen.text().startswith("1 Rampe und 0 Podeste")
    assert dialog.gelaende_bauen.isChecked() and dialog.abstand.value() == 2.0


def test_zeilenwahl_markiert_und_zeigen_sendet_die_kandidaten(qapp):
    raum, weg, punkte = _l_gang()
    dialog = KorrekturDialog(None, raum, weg, punkte)
    markiert, alle = [], []
    dialog.markiere.connect(markiert.append)
    dialog.kandidaten.connect(alle.append)
    dialog.show()
    dialog.tabelle.selectRow(0)
    assert alle and len(alle[-1]) >= dialog.tabelle.rowCount()
    assert markiert and markiert[-1] == list(finde_luecken(raum, weg, punkte)[0].strecken)
    dialog.close()


def test_ohne_weg_nur_die_waende(qapp):
    raum, _weg, punkte = _l_gang()
    dialog = KorrekturDialog(None, raum, [], punkte)
    assert not dialog.gelaende_bauen.isChecked() and not dialog.gelaende_bauen.isEnabled()
    assert "Kein Weg" in dialog.gelaende_bauen.text()
    assert not dialog.boeden_aufloesen.isEnabled()


def test_anwenden_ohne_gelaende_schliesst_die_waende_sofort(qapp):
    raum, weg, punkte = _l_gang()
    dialog = KorrekturDialog(None, raum, weg, punkte)
    dialog.gelaende_bauen.setChecked(False)
    (korrektur,) = _warte_auf(dialog.angewendet, dialog, sekunden=5)
    assert korrektur.bericht["gelaende"] is None
    assert korrektur.bericht["waende_verbunden"] >= 1 and korrektur.bericht["durchgaenge"] >= 1
    assert korrektur.raum.gelaende is None
    # Die Bruchstelle unten ist zu: ein Wandende liegt jetzt auf dem anderen.
    enden = {(round(w.x1, 2), round(w.y1, 2)) for w in korrektur.raum.waende}
    enden |= {(round(w.x2, 2), round(w.y2, 2)) for w in korrektur.raum.waende}
    assert (4.1, 0.0) in enden and (3.5, 0.0) not in enden


def test_anwenden_mit_gelaende_baut_es_im_arbeiter(qapp):
    raum, weg, punkte = _l_gang()
    dialog = KorrekturDialog(None, raum, weg, punkte)
    (korrektur,) = _warte_auf(dialog.angewendet, dialog)
    assert korrektur.raum.gelaende is not None
    assert korrektur.bericht["gelaende"]["knoten"] > 0
    assert korrektur.raum.boeden == ()                     # die Rampe ging im Gelaende auf
    assert korrektur.raum.gelaende.hoehe_bei(1.0, 1.0) is not None
    assert isinstance(korrektur.offene_raender, list)
