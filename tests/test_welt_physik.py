"""Welche Räume kann der Physikmodus? EINE Regel für den Tab und das Backend (28.09.2026)."""

from spotlab.welt import physik
from spotlab.welt.raum import Block, Boden, Raum, RaumTag, Sperrzone, raum_laden


def _raum(**felder):
    return Raum(name="t", beschreibung="", start=(0.0, 0.0, 0.0), **felder)


def test_ein_ebener_raum_mit_waenden_bloecken_tags_und_zonen_geht():
    raum = _raum(waende=[(0, 0, 4, 0)], bloecke=(Block("kiste", 2.0, 1.0, 0.5, 0.5),),
                 tags=(RaumTag(1, 3.0, 0.0, 90.0),),
                 sperrzonen=(Sperrzone("glas", 3.0, 3.0, 1.0, 1.0),))
    assert physik.tauglich(raum, (0.0, 0.0, 0.0)) == (True, "eben", "")


def test_kein_raum_ist_ein_ebener_raum():
    assert physik.tauglich(None, None)[:2] == (True, "eben")


def test_rampen_treppen_und_gelaende_gehen_nicht_und_sagen_warum():
    rampe = _raum(boeden=(Boden("rampe", 2.0, 0.0, 2.0, 1.0, z=0.0, anstieg=0.3),))
    ok, art, grund = physik.tauglich(rampe, (0.0, 0.0, 0.0))
    assert not ok and art is None and "Rampen" in grund and "Übungsraum 3D" in grund
    assert not physik.tauglich(raum_laden("treppe"), None)[0]


def test_die_zwei_validierten_szenen_bleiben_erlaubt():
    assert physik.tauglich(raum_laden("physik_einzelstufe"), (0.0, 0.0, 0.0))[:2] == \
        (True, "einzelstufe")
    assert physik.tauglich(raum_laden("physik_treppe_3stufen"), (0.0, 0.0, 0.0))[:2] == \
        (True, "treppe3")


def test_die_versuchstreppe_nur_vom_validierten_start():
    ok, _, grund = physik.tauglich(raum_laden("physik_treppe_3stufen"), (1.0, 0.0, 0.0))
    assert not ok and "Start" in grund


def test_die_regel_braucht_kein_numpy_und_kein_mujoco():
    """`welt/` bleibt Standardbibliothek -- die GUI fragt dieselbe Regel."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    import spotlab
    from tests_zeitgrenzen import TEST_TIMEOUT_S

    quelle = str(Path(spotlab.__file__).resolve().parents[1])     # das geprüfte Paket
    code = ("import sys; import spotlab.welt.physik; "
            "print(any(m in sys.modules for m in ('numpy', 'mujoco', 'spotsim')))")
    aus = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         timeout=TEST_TIMEOUT_S, env=dict(os.environ, PYTHONPATH=quelle))
    assert aus.stdout.strip() == "False", aus.stderr
