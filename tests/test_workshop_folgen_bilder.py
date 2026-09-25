"""Bilder EINMAL je Takt, Farbe und Tiefe GLEICHZEITIG (25.09.2026).

Lauf 20260925T125326Z (Folge-Aufnahme): in 303 von 441 Takten holte die Staffel
die Bilder zweimal — der Körper fand nichts, und das Gesicht rief seine eigene
`bildaufnahme`, rund 200 ms für dieselben vier Bilder. Und je Abruf kamen Farbe
(32 ms) und Tiefe (89 ms) nacheinander, obwohl die zwei Anfragen voneinander
nichts wissen.
"""

import threading
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from test_workshop_folgen import _Spot

from spotlab.workshop import folgeaufnahme as fa
from spotlab.workshop import folgen


class _Backend:
    """Zählt die Bildanfragen; `warte` lässt jede Anfrage auf eine Schranke warten."""

    def __init__(self, warte=None, tiefe_wirft=False):
        self.aufrufe = []
        self._sperre = threading.Lock()
        self._warte = warte
        self._tiefe_wirft = tiefe_wirft

    def images(self, quellen, **kw):
        with self._sperre:
            self.aufrufe.append((tuple(quellen), bool(kw.get("farbe"))))
        if self._warte is not None:
            self._warte.wait()
        if self._tiefe_wirft and not kw.get("farbe"):
            raise RuntimeError("Tiefe weg")
        return [SimpleNamespace(source=SimpleNamespace(name=q)) for q in quellen]


@pytest.fixture
def ohne_rechnung(monkeypatch):
    """Panorama, Punkte und Erkenner als Attrappen — geprüft wird nur der Abruf."""
    from spotlab.backends.real import gesicht, panorama, tiefe

    class _Pano:
        breite, hoehe = 8, 4

        def __init__(self, kal, zuschnitt=None):
            pass

        def zusammensetzen(self, bilder):
            return np.zeros((4, 8, 3), dtype="uint8")

        def kamerahoehe(self, blick_grad=0.0):
            return 0.46

    monkeypatch.setattr(panorama, "kalibrierung_aus", lambda grau: "KAL")
    monkeypatch.setattr(panorama, "bilder_aus", lambda grau: [])
    monkeypatch.setattr(panorama, "Panorama", _Pano)
    monkeypatch.setattr(tiefe, "punkte_aus_bild", lambda a: np.zeros((1, 3)))
    monkeypatch.setattr(gesicht, "erkenner", lambda *a, **kw: object())
    monkeypatch.setattr(gesicht, "kaesten", lambda feld, erkenner_: [])


def _spot(backend):
    spot = _Spot()
    spot.backend = backend
    return spot


def test_die_staffel_holt_die_bilder_einmal_je_takt(ohne_rechnung):
    backend = _Backend()
    spot = _spot(backend)
    staffel = folgen.zuerst(folgen.koerper_finder(koerper_holen=lambda feld: []),
                            folgen.gesicht_finder())
    assert staffel(spot) is None
    assert len(backend.aufrufe) == 2, "eine Farb-, eine Tiefenanfrage — nicht vier"
    staffel(spot)
    assert len(backend.aufrufe) == 4, "der nächste Takt holt NEUE Bilder"


def test_ohne_staffel_holt_ein_finder_jedes_mal_selbst(ohne_rechnung):
    backend = _Backend()
    finder = folgen.koerper_finder(koerper_holen=lambda feld: [])
    finder(_spot(backend))
    finder(_spot(backend))
    assert len(backend.aufrufe) == 4


def test_farbe_und_tiefe_kommen_gleichzeitig(ohne_rechnung):
    """Beide Anfragen warten, bis die andere auch unterwegs ist. Nacheinander
    gestellt, bräche die Schranke nach zwei Sekunden."""
    backend = _Backend(warte=threading.Barrier(2, timeout=2.0))
    aufnahme = folgen.bildaufnahme(_spot(backend), {})
    assert aufnahme is not None
    assert sorted(farbe for _, farbe in backend.aufrufe) == [False, True]
    [tiefe] = [q for q, farbe in backend.aufrufe if not farbe]
    assert set(tiefe) == set(folgen.TIEFE_QUELLEN), "die Tiefe NIE in Farbe"


def test_ein_fehler_beim_tiefenbild_kommt_an(ohne_rechnung):
    with pytest.raises(RuntimeError, match="Tiefe weg"):
        folgen.bildaufnahme(_spot(_Backend(tiefe_wirft=True)), {})


def test_die_aufnahme_zeigt_einen_abruf_je_takt(ohne_rechnung, tmp_path):
    backend = _Backend()
    aufnahme = fa.Folgeaufnahme(tmp_path)
    staffel = folgen.zuerst(folgen.koerper_finder(koerper_holen=lambda feld: []),
                            folgen.gesicht_finder())
    with aufnahme.aktiviert():
        aufnahme.takt_beginnt()
        staffel(_spot(backend))
        aufnahme.takt_endet("sucht")
    aufnahme.schliessen()
    import json

    [zeile] = [json.loads(z) for z in (tmp_path / fa.ORDNER / fa.INDEX).read_text(
        encoding="utf-8").splitlines()]
    namen = [name for name, _ in zeile["zeiten"]]
    assert namen.count("bilder") == 1 and namen.count("panorama") == 1
    [sicht] = zeile["sichten"]
    assert sicht["finder"] == "koerper+gesicht", "ein Bild, beide Finder"


def test_dieselbe_aufnahme_wird_nur_einmal_gespeichert(tmp_path):
    """Die Gesichtsaufnahme ist die Körperaufnahme plus YuNet (`replace`) — dasselbe Bild."""
    from spotlab.workshop.folgen import Gesichtsaufnahme

    aufnahme = fa.Folgeaufnahme(tmp_path)
    bild = Gesichtsaufnahme(np.zeros((4, 8, 3), dtype="uint8"), None, None, np.zeros((2, 3)), 10.0)
    aufnahme.takt_beginnt()
    assert aufnahme.sicht(bild, "koerper") == 0
    assert aufnahme.sicht(replace(bild, erkenner=object()), "gesicht") == 0
    aufnahme.takt_endet("sucht")
    bericht = aufnahme.schliessen()
    assert bericht["sichten"] == 1
    assert len(list((tmp_path / fa.ORDNER / fa.SICHTEN).glob("*.jpg"))) == 1
