"""Das Gelaende: Hoehenraster als Grund -- Abtastung, Klippen, Plateaus, Datei."""

import pytest

from spotlab.welt import gelaende as g


def _ebene(x0=0.0, y0=0.0, zelle=0.5, zeilen=4, spalten=5, f=lambda x, y: 0.1 * x):
    return g.gitter(x0, y0, zelle, zeilen, spalten, f)


def test_ein_gelaende_braucht_mindestens_zwei_mal_zwei_knoten():
    with pytest.raises(ValueError):
        g.Gelaende(0.0, 0.0, 0.2, 1, 3, (0.0, 0.0, 0.0))


def test_knoten_ausserhalb_ist_none():
    ge = _ebene()
    assert ge.knoten(0, 0) == 0.0
    assert ge.knoten(-1, 0) is None and ge.knoten(0, 5) is None


def test_hoehe_bei_ist_bilinear():
    ge = g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: x)   # 0 links, 1 rechts
    assert ge.hoehe_bei(0.5, 0.5) == pytest.approx(0.5)
    assert ge.hoehe_bei(0.25, 0.9) == pytest.approx(0.25)


def test_hoehe_bei_ausserhalb_ist_none():
    assert _ebene().hoehe_bei(-0.1, 0.0) is None
    assert _ebene().hoehe_bei(2.0, 1.6) is None      # spalten 5 -> x bis 2.0, zeilen 4 -> y bis 1.5


def test_am_rand_gilt_der_naechste_gueltige_knoten():
    def f(x, y):
        return None if (x, y) == (1.0, 1.0) else 0.3
    ge = g.gitter(0.0, 0.0, 1.0, 2, 2, f)
    assert ge.hoehe_bei(0.9, 0.9) == pytest.approx(0.3)


def test_alle_vier_none_gibt_none():
    ge = g.gitter(0.0, 0.0, 1.0, 3, 3, lambda x, y: None if x < 1.5 else 0.2)
    assert ge.hoehe_bei(0.5, 0.5) is None
    assert ge.hoehe_bei(1.7, 0.5) == pytest.approx(0.2)


def test_neigung_folgt_dem_gefaelle():
    ge = _ebene(f=lambda x, y: 0.1 * x)
    dzdx, dzdy = ge.neigung_bei(1.0, 0.75)
    assert dzdx == pytest.approx(0.1, abs=1e-6) and dzdy == pytest.approx(0.0, abs=1e-6)
    assert ge.neigung_bei(-5.0, 0.0) == (0.0, 0.0)


def test_umriss_und_verschieben():
    ge = _ebene(zelle=0.5, zeilen=4, spalten=5)
    assert g.umriss(ge) == (0.0, 0.0, 2.0, 1.5)
    neu = g.verschoben(ge, 1.0, 2.0, 0.5)
    assert g.umriss(neu) == (1.0, 2.0, 3.0, 3.5)
    assert neu.knoten(0, 2) == pytest.approx(0.1 + 0.5)


def test_zusammenfassung_nennt_zelle_knoten_und_spanne():
    text = g.zusammenfassung(_ebene(f=lambda x, y: 0.1 * x))
    assert text.startswith("Gelände · 0.5 m · 20 Knoten · 0.00 bis 0.20 m")


# ------------------------------------------------------------- Klippen, Plateaus


def test_ein_sprung_ueber_max_stufe_ist_eine_klippe_und_eine_strecke():
    ge = g.gitter(0.0, 0.0, 0.2, 4, 6, lambda x, y: 0.0 if x < 0.5 else 0.5)
    kl = [k for k in g.klippen(ge) if abs(k[0] - 0.5) < 1e-9 and abs(k[2] - 0.5) < 1e-9]
    assert len(kl) == 1                       # eine Strecke, nicht vier Stuecke
    x1, y1, x2, y2 = kl[0]
    assert min(y1, y2) == pytest.approx(-0.1) and max(y1, y2) == pytest.approx(0.7)


def test_ein_sprung_unter_max_stufe_ist_keine_klippe():
    ge = g.gitter(0.0, 0.0, 0.2, 4, 6, lambda x, y: 0.0 if x < 0.5 else 0.2)
    assert not [k for k in g.klippen(ge) if abs(k[0] - 0.5) < 1e-9]


def test_der_rand_ueber_max_stufe_ist_eine_klippe():
    ge = g.gitter(0.0, 0.0, 0.2, 3, 3, lambda x, y: 0.6)
    assert len(g.klippen(ge)) == 4                 # vier Kanten, je eine Strecke


def test_der_rand_auf_dem_grund_ist_keine_klippe():
    assert g.klippen(g.gitter(0.0, 0.0, 0.2, 3, 3, lambda x, y: 0.1)) == []


def test_plateaus_sind_die_ebenen_flaechen():
    def f(x, y):
        if x < 2.0:
            return 0.0
        if x < 4.0:
            return (x - 2.0) * 0.5          # Rampe auf 1.0
        return 1.0
    ge = g.gitter(0.0, 0.0, 0.2, 12, 31, f)      # 12 Zeilen x 10 Spalten je Plateau = 120 Knoten
    assert g.plateaus(ge) == [0.0, 1.0]


# ------------------------------------------------------------- Datei


def test_datei_hin_und_zurueck_mit_none(tmp_path):
    ge = g.gitter(1.0, 2.0, 0.25, 3, 4, lambda x, y: None if x > 1.6 else x + y)
    pfad = g.pfad_zu(tmp_path / "raum.toml")
    assert pfad.suffix == ".gelaende"
    g.schreibe(pfad, ge)
    zurueck = g.lies(pfad)
    assert (zurueck.x0, zurueck.y0, zurueck.zelle, zurueck.zeilen, zurueck.spalten) == (1.0, 2.0, 0.25, 3, 4)
    assert zurueck.knoten(0, 3) is None
    assert zurueck.knoten(1, 1) == pytest.approx(1.25 + 2.25, abs=1e-6)


def test_fehlende_datei_ist_none(tmp_path):
    assert g.lies(tmp_path / "nix.gelaende") is None


def test_falsche_kennung_ist_ein_fehler(tmp_path):
    from spotlab.errors import SpotlabError
    pfad = tmp_path / "kaputt.gelaende"
    pfad.write_bytes(b"PAUS1" + b"\0" * 40)
    with pytest.raises(SpotlabError, match="Gelände"):
        g.lies(pfad)
