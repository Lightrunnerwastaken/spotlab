"""Das Pauspapier: die Punktdatei neben einem rekonstruierten Raum."""
from pathlib import Path

import pytest

from spotlab.errors import SpotlabError
from spotlab.welt import pauspapier


def test_rundreise(tmp_path):
    pfad = tmp_path / "gang.pauspapier"
    pauspapier.schreibe(pfad, [(0.0, 0.0), (1.5, -2.25), (3.0, 4.0)])
    assert pauspapier.lies(pfad) == [(0.0, 0.0), (1.5, -2.25), (3.0, 4.0)]
    assert pfad.read_bytes()[:5] == b"PAUS2"


def test_zu_viele_punkte_werden_gleichmaessig_geduennt(tmp_path):
    pfad = tmp_path / "viel.pauspapier"
    pauspapier.schreibe(pfad, [(float(i), 0.0) for i in range(250_000)])
    punkte = pauspapier.lies(pfad)
    assert len(punkte) <= pauspapier.MAX_PUNKTE
    assert punkte[0] == (0.0, 0.0) and punkte[-1][0] > 249_000   # ueber die ganze Laenge


def test_fehlende_datei_ist_leer_und_falsche_kennung_ein_fehler(tmp_path):
    assert pauspapier.lies(tmp_path / "gibts_nicht.pauspapier") == []
    kaputt = tmp_path / "kaputt.pauspapier"
    kaputt.write_bytes(b"NOPE1\x00\x00\x00\x00")
    with pytest.raises(SpotlabError, match="Pauspapier"):
        pauspapier.lies(kaputt)


def test_der_pfad_liegt_neben_der_raumdatei():
    assert pauspapier.pfad_zu(Path("raeume") / "gang.toml") == Path("raeume") / "gang.pauspapier"


# ------------------------------------------------------------- PAUS2: der Weg


def test_paus2_traegt_den_weg(tmp_path):
    pfad = tmp_path / "r.pauspapier"
    pauspapier.schreibe(pfad, [(1.0, 2.0)], weg=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.5)])
    assert pauspapier.lies(pfad) == [(1.0, 2.0)]
    assert pauspapier.lies_weg(pfad) == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.5)]
    assert pauspapier.lies_weg(tmp_path / "nix.pauspapier") == []


def test_paus1_bleibt_lesbar_mit_leerem_weg(tmp_path):
    import struct

    pfad = tmp_path / "alt.pauspapier"
    pfad.write_bytes(b"PAUS1" + struct.pack("<I", 1) + struct.pack("<ff", 3.0, 4.0))
    assert pauspapier.lies(pfad) == [(3.0, 4.0)] and pauspapier.lies_weg(pfad) == []
