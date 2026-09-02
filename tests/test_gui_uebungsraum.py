import ast
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.config import Config, Limits  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.gui.views.uebungsraum import UebungsraumView  # noqa: E402

QUELLE = (Path(__file__).resolve().parents[1] / "src" / "spotlab" / "gui"
          / "views" / "uebungsraum.py")


def test_ansicht_importiert_weder_bosdyn_noch_backends():
    """CLAUDE.md: kein bosdyn UND kein spotlab.backends unterhalb von gui/.
    Ueber ast, nicht als Textsuche -- der Docstring erwaehnt beides."""
    namen = set()
    for knoten in ast.walk(ast.parse(QUELLE.read_text(encoding="utf-8"))):
        if isinstance(knoten, ast.Import):
            namen.update(t.name for t in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            namen.add(knoten.module)
    verboten = [n for n in namen
                if n.split(".")[0] == "bosdyn" or n.startswith("spotlab.backends")]
    assert not verboten


def test_zeigt_die_drei_vorlagen(qapp):
    ansicht = UebungsraumView(DUNKEL)
    texte = [ansicht.raeume.itemText(i) for i in range(ansicht.raeume.count())]
    assert sorted(texte) == ["durchgang", "leer", "moebliert"]


def test_raumwahl_zeichnet_den_raum(qapp):
    ansicht = UebungsraumView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    assert ansicht.plot._raum is not None
    assert ansicht.plot._raum.name == "Möbliert"


def test_klick_setzt_die_startpose_und_merkt_sie(qapp):
    ansicht = UebungsraumView(DUNKEL)
    ansicht.setze_config(Config(ip="1.2.3.4", username="u", limits=Limits()))
    ansicht.waehle_raum("leer")
    gemerkt = []
    ansicht.config_gespeichert.connect(gemerkt.append)
    ansicht._start_gewaehlt(2.0, 3.0)
    assert gemerkt, "die Wahl muss in die Konfiguration"
    assert gemerkt[-1].raum == "leer"
    assert gemerkt[-1].raum_start.startswith("2.00,3.00")


def test_startpose_in_einer_wand_wird_abgewiesen(qapp):
    ansicht = UebungsraumView(DUNKEL)
    ansicht.setze_config(Config(ip="1.2.3.4", username="u", limits=Limits()))
    ansicht.waehle_raum("leer")
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht._start_gewaehlt(0.05, 0.05)
    assert gemeldet and "Wand" in gemeldet[0]


def _lauf(tmp_path):
    ereignisse = [
        {"t": 0.0, "art": "verbunden", "daten": {"backend": "sim", "raum": "leer"}},
        {"t": 2.0, "art": "angestossen",
         "daten": {"x": 4.6, "y": 2.0, "hindernis": "Wand"}},
    ]
    (tmp_path / "ereignisse.jsonl").write_text(
        "\n".join(json.dumps(z) for z in ereignisse) + "\n", encoding="utf-8")
    zustand = [
        {"t": 0.1, "daten": {"pose": [1.0, 1.0, 0.0]}},
        {"t": 0.2, "daten": {"pose": [1.5, 1.0, 0.0]}},
        {"t": 0.3, "daten": {"pose": [2.0, 1.0, 0.0]}},
    ]
    (tmp_path / "zustand.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zustand) + "\n", encoding="utf-8")
    return tmp_path


def test_lauf_liefert_raum_spur_und_anstoesse(qapp, tmp_path):
    ansicht = UebungsraumView(DUNKEL)
    ansicht.lade(_lauf(tmp_path))
    assert ansicht.plot._raum.name == "Leer"
    assert len(ansicht.plot._spur) == 3
    assert ansicht.plot._anstoesse == [(4.6, 2.0)]


def test_halbe_letzte_zeile_bricht_nicht(qapp, tmp_path):
    ordner = _lauf(tmp_path)
    with (ordner / "zustand.jsonl").open("a", encoding="utf-8") as datei:
        datei.write('{"t": 0.4, "daten": {"pos')
    ansicht = UebungsraumView(DUNKEL)
    ansicht.lade(ordner)
    assert len(ansicht.plot._spur) == 3


def test_lauf_ohne_raum_zeigt_keinen(qapp, tmp_path):
    """Ein echter Lauf hat kein raum-Feld -- die Ansicht darf nicht stuerzen."""
    (tmp_path / "ereignisse.jsonl").write_text(
        json.dumps({"t": 0.0, "art": "verbunden", "daten": {"backend": "real"}}) + "\n",
        encoding="utf-8")
    ansicht = UebungsraumView(DUNKEL)
    ansicht.lade(tmp_path)
    assert ansicht.plot._raum is None


def test_startknopf_meldet_nur_den_wunsch(qapp):
    """Er startet NICHT selbst -- genau ein Lauf ist der, auf den NOT-AUS zeigt."""
    ansicht = UebungsraumView(DUNKEL)
    gewuenscht = []
    ansicht.start_gewuenscht.connect(lambda: gewuenscht.append(True))
    ansicht.starten.click()
    assert gewuenscht == [True]


def test_startknopf_heisst_nach_der_offenen_datei(qapp):
    """'Programm starten' verspricht eine Auswahl, die es nicht gibt."""
    ansicht = UebungsraumView(DUNKEL)
    assert "ffene Datei" in ansicht.starten.text()


def test_knopf_wird_zum_stopp_waehrend_ein_lauf_laeuft(qapp):
    """Sonst haette man im Uebungsraum einen Startknopf, der nichts tut."""
    ansicht = UebungsraumView(DUNKEL)
    ansicht.setze_laeuft(True)
    assert "Stopp" in ansicht.starten.text()
    ansicht.setze_laeuft(False)
    assert "Stopp" not in ansicht.starten.text()
