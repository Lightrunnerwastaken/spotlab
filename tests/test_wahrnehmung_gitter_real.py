"""Das echte Hindernisgitter vom 12.08.2026 durch den Entpacker.

Die Fixture ist eine serialisierte `LocalGridResponse`, bitgleich wie vom
LocalGridService des Schul-Spot geliefert (Herkunft: tests/daten/...). Was
hier geprueft wird, ist keine Attrappe: `unknown_cells` kommt dort mit EINEM
Byte je Zelle -- bitweise entpackt ergab das bis zum 06.09.2026 eine falsche
Maske, und `is_free()` hielt Unbekanntes fuer frei.
"""

from pathlib import Path

import pytest

pytest.importorskip("bosdyn.api")

FIXTURE = (Path(__file__).parent / "daten" / "gitter_real_20260812"
           / "000001_obstacle_distance.pb")


def _echt():
    from bosdyn.api import local_grid_pb2

    resp = local_grid_pb2.LocalGridResponse()
    resp.ParseFromString(FIXTURE.read_bytes())
    return resp


def test_das_echte_gitter_wird_entpackt():
    from spotlab.backends.real.wahrnehmung import gitter_aus

    gitter = gitter_aus(_echt())
    assert gitter.cells.shape == (128, 128)
    assert gitter.cell_size == pytest.approx(0.03)
    assert gitter.known is not None and gitter.known.shape == (128, 128)


def test_die_unbekannt_maske_ist_ein_byte_je_zelle():
    """Ein BYTE je Zelle, Werte nur 0/1 -- das gemessene Format.

    Bitweise gelesen wurden nur die ersten 2048 Bytes zu 16384 Bits verstreut.
    Die echte Maske zeigt 19 % Unbekanntes: Baender hinter Waenden UND die
    Zellen unter dem Koerper, den die Kameras nicht sehen. Ein Test, der
    "unter dem Roboter bekannt" verlangte, prueft die eigene Vorstellung."""
    import numpy as np

    from spotlab.backends.real.wahrnehmung import gitter_aus

    g = _echt().local_grid
    roh = np.frombuffer(g.unknown_cells, dtype=np.uint8)
    assert set(np.unique(roh).tolist()) <= {0, 1}, "kein Byte je Zelle"
    known = gitter_aus(_echt()).known
    assert np.array_equal(~known, roh.reshape(128, 128).astype(bool))
    anteil_unbekannt = 1.0 - float(known.mean())
    assert 0.05 < anteil_unbekannt < 0.95, anteil_unbekannt


def test_is_free_haelt_unbekanntes_nicht_fuer_frei():
    """Die Konsequenz der Maske: eine unbekannte Zelle am Rand ist NICHT frei."""
    import numpy as np

    from spotlab.backends.real.wahrnehmung import gitter_aus

    gitter = gitter_aus(_echt())
    unbekannt = np.argwhere(~gitter.known)
    assert len(unbekannt), "die Fixture hat unbekannte Zellen"
    i, j = unbekannt[0]
    x = gitter.origin[0] + (i + 0.5) * gitter.cell_size
    y = gitter.origin[1] + (j + 0.5) * gitter.cell_size
    assert gitter.distance_at(x, y) is None
    assert not gitter.is_free(x, y)
