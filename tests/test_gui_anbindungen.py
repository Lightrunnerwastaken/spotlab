import json
import shutil

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.anbindung.manifest import DATEINAME  # noqa: E402
from spotlab.anbindung.panel import schreibe  # noqa: E402
from spotlab.anbindung.speicher import binde_an, panelordner  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.gui.views.anbindungen import AnbindungenView  # noqa: E402
from tests_zeitgrenzen import TEST_TIMEOUT_S  # noqa: E402

MANIFEST = """
[projekt]
name = "matura-spot"

[[skript]]
name = "Baseline"
datei = "scripts/lauf.py"
roboter = false
"""

def _schreibe_png(pfad):
    """Ein echtes PNG statt eines handgeschriebenen — Pillow ist Kernabhängigkeit."""
    from PIL import Image

    Image.new("RGB", (4, 4), (10, 20, 30)).save(pfad)
    return pfad


def _welt(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = tmp_path / "matura-spot"
    (projekt / "scripts").mkdir(parents=True)
    (projekt / "scripts" / "lauf.py").write_text("print(1)\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(MANIFEST, encoding="utf-8")
    return arbeit, projekt, binde_an(arbeit, projekt)


def test_liste_zeigt_angebundene_projekte(qapp, tmp_path):
    arbeit, _, _ = _welt(tmp_path)
    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert ansicht.liste.count() == 1
    assert ansicht.liste.item(0).text() == "matura-spot"


def test_alle_fuenf_arten_zeichnen(qapp, tmp_path):
    arbeit, _, gebunden = _welt(tmp_path)
    bild = _schreibe_png(gebunden.ordner / "b.png")
    schreibe(gebunden, "a", "kennzahlen", "K", [{"name": "x", "wert": "1", "hinweis": "h"}])
    schreibe(gebunden, "b", "tabelle", "T", {"spalten": ["a"], "zeilen": [["1"]]})
    schreibe(gebunden, "c", "reihe", "R", {"x": [0, 1], "y": [1, 2]})
    schreibe(gebunden, "d", "bild", "B", {"pfad": str(bild)})
    schreibe(gebunden, "e", "text", "X", {"absaetze": ["hallo"]})

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert ansicht.panelbereich.count() == 5
    assert ansicht.paneltexte() == ["", "", "", "", ""]     # kein Hinweis nötig


def test_ein_kaputtes_panel_laesst_die_anderen_stehen(qapp, tmp_path):
    """Die Ansicht darf an einer halb geschriebenen Datei nicht leer werden."""
    arbeit, _, gebunden = _welt(tmp_path)
    schreibe(gebunden, "gut", "kennzahlen", "Gut", [{"name": "x", "wert": "1"}])
    (gebunden.ordner / "panels" / "kaputt.json").write_text("{", encoding="utf-8")

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert ansicht.panelbereich.count() == 2          # gut + Fehlerkarte
    assert any("unbrauchbar" in t for t in ansicht.paneltexte())


def test_bild_von_ausserhalb_wird_nicht_geladen(qapp, tmp_path):
    # Die Datei wird von HAND geschrieben, nicht ueber schreibe(): seit S4.6
    # weist der Schreiber solche Pfade ab. Genau deshalb ist dieser Test noch
    # noetig — er deckt den Fall, dass die Datei NICHT von spotlab stammt oder
    # aelter ist als die Pruefung. Ginge er nur noch ueber schreibe(), pruefte
    # er zweimal dieselbe Schranke und die Anzeige gar nicht mehr.
    arbeit, _, gebunden = _welt(tmp_path)
    fremd = _schreibe_png(tmp_path / "fremd.png")
    ordner = panelordner(gebunden)
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "b.json").write_text(
        json.dumps(
            {"titel": "B", "art": "bild", "stand": "2026-08-11T00:00:00+00:00",
             "inhalt": {"pfad": str(fremd)}}
        ),
        encoding="utf-8",
    )

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert any("ausserhalb" in t for t in ansicht.paneltexte())


def test_kaputtes_bild_meldet_es(qapp, tmp_path):
    arbeit, _, gebunden = _welt(tmp_path)
    kaputt = gebunden.ordner / "kein.png"
    kaputt.write_bytes(b"nicht wirklich ein Bild")
    schreibe(gebunden, "b", "bild", "B", {"pfad": str(kaputt)})

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert any("Bild" in t for t in ansicht.paneltexte())


def test_skriptknopf_startet_wirklich(qapp, tmp_path):
    arbeit, _, _ = _welt(tmp_path)
    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    gestartet = []
    ansicht.lauf_gestartet.connect(lambda p, s: gestartet.append((p, s)))
    assert len(ansicht.skriptknoepfe) == 1
    ansicht.skriptknoepfe[0].click()
    assert gestartet
    prozess, _skript = gestartet[0]
    prozess.wait(timeout=TEST_TIMEOUT_S)


def test_viele_skripte_brechen_auf_mehrere_zeilen_um(qapp, tmp_path):
    """matura-spot bringt acht Skripte mit — in einer Reihe wäre keines mehr lesbar."""
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = tmp_path / "viele"
    (projekt / "scripts").mkdir(parents=True)
    eintraege = ['[projekt]\nname = "viele"\n']
    for i in range(8):
        (projekt / "scripts" / f"s{i}.py").write_text("x = 1\n", encoding="utf-8")
        eintraege.append(f'\n[[skript]]\nname = "Skript {i}"\ndatei = "scripts/s{i}.py"\n')
    (projekt / DATEINAME).write_text("".join(eintraege), encoding="utf-8")
    binde_an(arbeit, projekt)

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert len(ansicht.skriptknoepfe) == 8
    assert ansicht.knopfzeile.rowCount() >= 3
    assert ansicht.knopfzeile.columnCount() <= 3


def test_fehlende_quelle_schaltet_die_knoepfe_ab(qapp, tmp_path):
    arbeit, projekt, gebunden = _welt(tmp_path)
    schreibe(gebunden, "a", "kennzahlen", "K", [{"name": "x", "wert": "1"}])
    shutil.rmtree(projekt)

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert all(not k.isEnabled() for k in ansicht.skriptknoepfe)
    assert ansicht.panelbereich.count() == 1          # Panels bleiben sichtbar
    assert str(projekt) in ansicht.hinweis.text()


def test_ohne_anbindungen_bleibt_die_ansicht_leer(qapp, tmp_path):
    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.liste.count() == 0
    assert ansicht.panelbereich.count() == 0


def test_aktualisieren_zeigt_neue_panels(qapp, tmp_path):
    arbeit, _, gebunden = _welt(tmp_path)
    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert ansicht.panelbereich.count() == 0
    schreibe(gebunden, "neu", "text", "Neu", {"absaetze": ["frisch"]})
    ansicht.aktualisiere()
    assert ansicht.panelbereich.count() == 1


# ================= S1.9 der dritte Startweg zum echten Roboter
#
# Aus "Anbindungen" laesst sich FREMDER Code starten, und zwar ohne
# Trockenlauf-Schranke (hier sitzt ein Mensch vor dem NOT-AUS). Ein Skript mit
# `roboter = true` bewegt damit den echten Spot -- aber die Ansicht hatte
# keinen eigenen Stopp-Knopf und wechselte auch nicht zur Live-Ansicht. Der am
# wenigsten geprueften Startweg war zugleich der ohne Notbremse in Sichtweite.


def test_ein_roboter_skript_meldet_sich_als_solches(qapp, tmp_path):
    from spotlab.anbindung.manifest import Skript

    ansicht = AnbindungenView(DUNKEL)
    gemeldet = []
    ansicht.roboterlauf.connect(lambda: gemeldet.append(True))
    skript = Skript(name="fahrt", datei=tmp_path / "f.py", argumente=[],
                    roboter=True, beschreibung="")
    ansicht._melde_roboterlauf(skript)
    assert gemeldet == [True]


def test_ein_gewoehnliches_skript_meldet_nichts(qapp, tmp_path):
    from spotlab.anbindung.manifest import Skript

    ansicht = AnbindungenView(DUNKEL)
    gemeldet = []
    ansicht.roboterlauf.connect(lambda: gemeldet.append(True))
    skript = Skript(name="auswertung", datei=tmp_path / "a.py", argumente=[],
                    roboter=False, beschreibung="")
    ansicht._melde_roboterlauf(skript)
    assert gemeldet == []


def test_die_ansicht_hat_einen_stopp_knopf(qapp, tmp_path):
    """Er delegiert an LiveView.stoppe() -- Projektregel: dieselbe Funktion
    aufzurufen genuegt nicht, es muss dasselbe Objekt mit demselben Zustand sein."""
    ansicht = AnbindungenView(DUNKEL)
    gewuenscht = []
    ansicht.stopp_gewuenscht.connect(lambda: gewuenscht.append(True))
    ansicht.stopp_knopf.click()
    assert gewuenscht == [True]


def test_der_stopp_knopf_ist_erst_bei_einem_lauf_da(qapp, tmp_path):
    ansicht = AnbindungenView(DUNKEL)
    assert ansicht.stopp_knopf.isHidden()
    ansicht.lauf_laeuft(True)
    assert not ansicht.stopp_knopf.isHidden()
    ansicht.lauf_laeuft(False)
    assert ansicht.stopp_knopf.isHidden()
