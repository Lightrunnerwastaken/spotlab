"""Die Tabelle auf der Platte — und der Nachtrag des Menschen.

Sie hat die Spalten der Tabelle, die der Autor bisher von Hand gefuehrt hat
(Gruppengroesse, Klasse, Laufzeit, Uhrzeit), und daneben das, was Spot dazu
beisteuert: die gemessene Strecke, das Tempo und den Grund, falls ein Durchgang
verworfen wurde.
"""

import pytest

from spotlab.errors import SpotlabError
from spotlab.experiment import tabelle
from spotlab.experiment.durchgang import durchgaenge_aus
from spotlab.experiment.zeitnahme import Querung


def _gut(kennung, t_start, dauer):
    return Querung(kennung=kennung, richtung=1, t_start=t_start,
                   t_ende=t_start + dauer, dauer_s=dauer, tempo_m_s=10.0 / dauer)


def _zeilen():
    durchgaenge = durchgaenge_aus([
        _gut("A", 1000.0, 8.0), _gut("B", 1001.0, 8.5),
        _gut("C", 2000.0, 12.0),
    ])
    return [tabelle.zeile_aus(d, strecke_m=10.0) for d in durchgaenge]


def test_die_spalten_sind_die_der_handtabelle_plus_spots_beitrag():
    for spalte in ("uhrzeit", "klasse", "gruppengroesse", "laufzeit_s"):
        assert spalte in tabelle.FELDER
    for spalte in ("strecke_m", "tempo_m_s", "verworfen", "gruende"):
        assert spalte in tabelle.FELDER


def test_eine_zeile_traegt_was_spot_gemessen_hat_und_laesst_offen_was_er_nicht_weiss():
    zeile = _zeilen()[0]
    assert zeile["nummer"] == 1
    assert zeile["laufzeit_s"] == pytest.approx(8.25)
    assert zeile["strecke_m"] == pytest.approx(10.0)
    assert zeile["tempo_m_s"] == pytest.approx(10.0 / 8.25)
    assert zeile["personen"] == 2
    # Was Spot NICHT weiss, bleibt leer statt geraten.
    assert zeile["klasse"] == "" and zeile["gruppengroesse"] is None


def test_schreiben_und_lesen_ergeben_dieselben_zahlen(tmp_path):
    pfad = tmp_path / "gehzeit.csv"
    tabelle.schreibe(pfad, _zeilen())
    zurueck = tabelle.lies(pfad)
    assert [z["nummer"] for z in zurueck] == [1, 2]
    assert zurueck[0]["laufzeit_s"] == pytest.approx(8.25, abs=0.005)
    assert zurueck[0]["personen"] == 2
    assert zurueck[1]["laufzeit_s"] == pytest.approx(12.0, abs=0.005)


def test_die_datei_oeffnet_sich_in_einem_deutschen_tabellenprogramm(tmp_path):
    """Semikolon und Dezimalkomma. Ein Doppelklick soll die Tabelle zeigen und
    nicht eine Spalte voller Text — die Datei geht an einen Menschen, nicht an
    eine Bibliothek. `lies()` rechnet es beim Einlesen zurueck."""
    pfad = tmp_path / "gehzeit.csv"
    tabelle.schreibe(pfad, _zeilen())
    text = pfad.read_text(encoding="utf-8-sig")
    kopf, erste = text.splitlines()[0], text.splitlines()[1]
    assert kopf.startswith("nummer;")
    assert "8,25" in erste, erste


def test_der_mensch_traegt_klasse_und_gruppengroesse_nach(tmp_path):
    pfad = tmp_path / "gehzeit.csv"
    tabelle.schreibe(pfad, _zeilen())
    tabelle.ergaenze(pfad, 2, klasse="4bG", gruppengroesse=3)
    zurueck = tabelle.lies(pfad)
    assert zurueck[1]["klasse"] == "4bG"
    assert zurueck[1]["gruppengroesse"] == 3
    # Die andere Zeile bleibt unangetastet.
    assert zurueck[0]["klasse"] == "" and zurueck[0]["gruppengroesse"] is None


def test_der_nachtrag_laesst_spots_messwerte_stehen(tmp_path):
    """Der Mensch korrigiert die Gruppengroesse, nicht die Zeit."""
    pfad = tmp_path / "gehzeit.csv"
    tabelle.schreibe(pfad, _zeilen())
    vorher = tabelle.lies(pfad)[0]["laufzeit_s"]
    tabelle.ergaenze(pfad, 1, gruppengroesse=2)
    assert tabelle.lies(pfad)[0]["laufzeit_s"] == pytest.approx(vorher)


def test_ein_nachtrag_auf_eine_unbekannte_nummer_ist_ein_fehler(tmp_path):
    pfad = tmp_path / "gehzeit.csv"
    tabelle.schreibe(pfad, _zeilen())
    with pytest.raises(SpotlabError, match="99"):
        tabelle.ergaenze(pfad, 99, gruppengroesse=1)


def test_ein_verworfener_durchgang_steht_mit_grund_in_der_tabelle(tmp_path):
    """Verworfen heisst protokolliert. Eine Tabelle, in der die Abbrueche
    fehlen, sieht vollstaendiger aus, als die Messung war."""
    abgebrochen = Querung(kennung="A", richtung=1, t_start=0.0, t_ende=5.0,
                          verworfen=True, grund="gestoppt")
    d = durchgaenge_aus([abgebrochen])[0]
    zeile = tabelle.zeile_aus(d, strecke_m=10.0)
    assert zeile["gueltig"] is False
    assert zeile["gruende"] == ("gestoppt",)
    assert zeile["laufzeit_s"] is None and zeile["tempo_m_s"] is None

    pfad = tmp_path / "gehzeit.csv"
    tabelle.schreibe(pfad, [zeile])
    zurueck = tabelle.lies(pfad)[0]
    assert zurueck["gueltig"] is False
    assert zurueck["gruende"] == ("gestoppt",)
    assert zurueck["laufzeit_s"] is None


def test_die_uhrzeit_steht_als_uhrzeit_da():
    """Die Spalte aus der Handtabelle. Sekunden seit 1970 liest niemand."""
    d = durchgaenge_aus([_gut("A", 1000.0, 8.0)])[0]
    zeile = tabelle.zeile_aus(d, strecke_m=10.0, uhrzeit="09:41:03")
    assert zeile["uhrzeit"] == "09:41:03"
    abgeleitet = tabelle.zeile_aus(d, strecke_m=10.0)
    assert abgeleitet["uhrzeit"].count(":") == 2
