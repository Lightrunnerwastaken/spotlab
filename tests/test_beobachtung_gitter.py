"""Der Gitter-Mitschnitt: Ablage, Index, Vorschau, Fehlerzaehlung.

Laeuft ohne Roboter — der Client ist eine Attrappe, die echte Protobufs baut.
"""

import json

import numpy as np
import pytest
from bosdyn.api import local_grid_pb2

from spotlab.beobachtung.gitter import Gittermitschnitt, lies_mitschnitt

ZELLEN = 4


def _antwort(typ="obstacle_distance", mit_unbekannt=False):
    antwort = local_grid_pb2.LocalGridResponse()
    g = antwort.local_grid
    g.local_grid_type_name = typ
    g.extent.cell_size = 0.03
    g.extent.num_cells_x = ZELLEN
    g.extent.num_cells_y = ZELLEN
    g.cell_format = local_grid_pb2.LocalGrid.CELL_FORMAT_FLOAT32
    g.encoding = local_grid_pb2.LocalGrid.ENCODING_RAW
    g.cell_value_scale = 1.0
    g.cell_value_offset = 0.0
    g.data = np.full(ZELLEN * ZELLEN, 1.5, dtype=np.float32).tobytes()
    if mit_unbekannt:
        # Ein Bit je Zelle; alles bekannt ausser der ersten.
        bits = np.zeros(ZELLEN * ZELLEN, dtype=np.uint8)
        bits[0] = 1
        g.unknown_cells = np.packbits(bits, bitorder="little").tobytes()
    return antwort


class AttrappenClient:
    def __init__(self, fehler_ab=None, antworten=None):
        self.abrufe = 0
        self._fehler_ab = fehler_ab
        self._antworten = antworten

    def get_local_grids(self, typen):
        self.abrufe += 1
        if self._fehler_ab is not None and self.abrufe >= self._fehler_ab:
            raise RuntimeError("Netz weg")
        return self._antworten if self._antworten is not None else [_antwort()]


def _einmal_laufen(tmp_path, client):
    mitschnitt = Gittermitschnitt(client, tmp_path, hz=50.0)
    mitschnitt.start()
    mitschnitt.stop()
    return mitschnitt


def _saetze(tmp_path):
    index = tmp_path / "gitter" / "gitter.jsonl"
    return [json.loads(z) for z in index.read_text(encoding="utf-8").splitlines() if z]


def test_legt_gitter_und_index_ab(tmp_path):
    _einmal_laufen(tmp_path, AttrappenClient())
    saetze = _saetze(tmp_path)
    assert saetze
    assert (tmp_path / "gitter" / saetze[0]["datei"]).exists()


def test_speichert_die_serialisierte_antwort_nicht_ein_eigenformat(tmp_path):
    """Die Garantie, dass GUI, Replay und Sim identisch dekodieren."""
    _einmal_laufen(tmp_path, AttrappenClient())
    erster = _saetze(tmp_path)[0]
    roh = (tmp_path / "gitter" / erster["datei"]).read_bytes()
    wieder = local_grid_pb2.LocalGridResponse()
    wieder.ParseFromString(roh)              # muss ohne Fehler gelingen
    assert wieder.local_grid.extent.cell_size == pytest.approx(0.03)


def test_legt_eine_vorschau_fuer_die_gui_daneben(tmp_path):
    """Die GUI kann kein Protobuf dekodieren — sie bekommt ein Bild."""
    _einmal_laufen(tmp_path, AttrappenClient())
    erster = _saetze(tmp_path)[0]
    vorschau = tmp_path / "gitter" / (erster["datei"][:-3] + ".png")
    assert vorschau.is_file()
    assert vorschau.stat().st_size > 0


def test_unbekannte_zelle_wird_in_der_vorschau_schwarz(tmp_path):
    """Eine erfundene Freiheit im Bild waere derselbe Fehler wie in der API."""
    from PIL import Image

    _einmal_laufen(tmp_path, AttrappenClient(antworten=[_antwort(mit_unbekannt=True)]))
    erster = _saetze(tmp_path)[0]
    bild = np.asarray(Image.open(tmp_path / "gitter" / (erster["datei"][:-3] + ".png")))
    assert bild.flat[0] == 0          # unbekannt -> schwarz
    assert bild.flat[1] > 0           # bekannt und frei -> hell


def test_fehler_werden_gezaehlt_nicht_geworfen(tmp_path):
    mitschnitt = _einmal_laufen(tmp_path, AttrappenClient(fehler_ab=1))
    assert mitschnitt.zaehler()["fehler"] > 0


def test_wiedereinlesen_liefert_satz_und_antwort(tmp_path):
    _einmal_laufen(tmp_path, AttrappenClient())
    gelesen = list(lies_mitschnitt(tmp_path))
    assert gelesen
    satz, resp = gelesen[0]
    assert satz["typ"] == "obstacle_distance"
    assert resp.local_grid.extent.num_cells_x == ZELLEN
