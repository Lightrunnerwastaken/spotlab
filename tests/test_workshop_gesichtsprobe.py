"""Die Messprobe: was der Gesichtserkenner WIRKLICH sieht, und was damit passiert.

Der Anlass ist ein Lauf am 11.09.2026. Der Folgemodus meldete in 73 von 73
Takten kein Gesicht — und die Aufzeichnung konnte nicht sagen, ob YuNet gar
keinen Kasten setzte oder ob die Gegenprobe einen verwarf. Ein Nullergebnis ohne
Begruendung ist keine Messung.

Die Probe steht still (`nur_lesen=True`, kein Lease), schreibt je Kasten Urteil
und Grund, und behaelt die Panoramen. Damit bekommt das Projekt nebenbei das
Testbild, das ihm seit dem ersten Tag fehlt: eines MIT einem Gesicht darin.
"""

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from spotlab.backends.real import gesicht
from spotlab.workshop import gesichtsprobe

QUELLE = (Path(__file__).resolve().parents[1] / "src" / "spotlab" / "workshop"
          / "gesichtsprobe.py")


class _Pano:
    """Ein Panorama fester Groesse, das die Bildzeile in einen Winkel dreht."""

    breite, hoehe = 400, 200

    def winkel(self, spalte, zeile):
        return 0.0, (200.0 - zeile) / 5.0

    def kamerahoehe(self, blick_grad=0.0):
        return 0.46


class FakeSpot:
    """Liefert je Takt dieselbe Aufnahme; die Kaesten kommen aus dem Drehbuch."""

    recorder = None

    def __init__(self, kaesten_je_takt, punkte=None):
        self._drehbuch = list(kaesten_je_takt)
        self._punkte = np.zeros((0, 3)) if punkte is None else punkte
        self.takte = 0

    def aufnahme(self):
        from spotlab.workshop.folgen import Gesichtsaufnahme

        self.takte += 1
        feld = np.zeros((_Pano.hoehe, _Pano.breite), dtype=np.uint8)
        return Gesichtsaufnahme(feld, _Pano(), None, self._punkte, 0.0)

    def naechste_kaesten(self):
        return self._drehbuch.pop(0) if self._drehbuch else []


def _probe(tmp_path, spot, **kw):
    """Ruft die Probe mit vorgegebener Aufnahme und vorgegebenen Kaesten.

    Feine Uhr: `probe` fragt sie mehrmals je Takt (Schleifenkopf, Taktbeginn,
    Wartezeit). Mit groben Schritten waere nach einem Takt Schluss.
    """
    argumente = dict(
        ziel=tmp_path, dauer_s=3.0, takt_s=1.0,
        jetzt=_uhr(0.1), schlaf=lambda _s: None, melde=lambda _t: None,
        aufnahme_holen=lambda _spot, _gemerkt: spot.aufnahme(),
        kaesten_holen=lambda _feld, _erkenner: spot.naechste_kaesten(),
    )
    argumente.update(kw)
    return gesichtsprobe.probe(spot, **argumente)


def _uhr(schritt=1.0):
    stand = {"t": 0.0}

    def jetzt():
        stand["t"] += schritt
        return stand["t"]

    return jetzt


def _zeilen(tmp_path):
    # `ziel=` ist schon der Versuchsordner; die Probe haengt nur den Dateinamen an.
    pfad = tmp_path / Path(gesichtsprobe.INDEX).name
    if not pfad.is_file():
        return []
    return [json.loads(z) for z in pfad.read_text(encoding="utf-8").splitlines() if z.strip()]


# ------------------------------------------------------------ Das Urteil


def test_ein_verworfener_kasten_steht_mit_grund_im_protokoll(tmp_path):
    """Der ganze Zweck. Ohne diese Zeile sieht ein verworfener Kasten aus wie
    'YuNet hat nichts gesehen'."""
    spot = FakeSpot([[(320.0, 180.0, 40.0, 40.0, 0.66)]])
    ergebnis = _probe(tmp_path, spot)

    befunde = [b for z in _zeilen(tmp_path) for b in z["befunde"]]
    assert len(befunde) == 1
    b = befunde[0]
    assert b["genommen"] is False
    assert b["grund"] == gesicht.OHNE_TIEFE
    assert b["score"] == pytest.approx(0.66)
    assert ergebnis["kaesten"] == 1 and ergebnis["genommen"] == 0


def test_ein_genommener_kasten_traegt_abstand_und_hoehe(tmp_path):
    from test_backend_gesicht import _wolke

    spot = FakeSpot([[(700.0, 80.0, 40.0, 40.0, 0.9)]], punkte=_wolke(3.0, 0.0, 20.0))
    ergebnis = _probe(tmp_path, spot)

    [b] = [b for z in _zeilen(tmp_path) for b in z["befunde"]]
    assert b["genommen"] is True and b["grund"] is None
    assert b["distance"] == pytest.approx(3.0, abs=0.05)
    assert b["height"] == pytest.approx(1.55, abs=0.05)
    assert ergebnis["genommen"] == 1


def test_ein_takt_ohne_kasten_steht_auch_da(tmp_path):
    """'YuNet hat nichts gesehen' ist selbst eine Information — sie trennt
    Erkennungs- von Gegenprobenproblemen."""
    spot = FakeSpot([[], []])
    ergebnis = _probe(tmp_path, spot, dauer_s=2.5)
    zeilen = _zeilen(tmp_path)
    assert len(zeilen) >= 2
    assert all(z["befunde"] == [] for z in zeilen[:2])
    assert ergebnis["takte"] >= 2 and ergebnis["kaesten"] == 0


def test_die_gruende_werden_gezaehlt(tmp_path):
    from test_backend_gesicht import _wolke

    spot = FakeSpot(
        [[(320.0, 180.0, 40.0, 40.0, 0.7)], [(320.0, 180.0, 40.0, 40.0, 0.7)]],
        punkte=_wolke(1.0, 0.0, 0.0),
    )
    ergebnis = _probe(tmp_path, spot, dauer_s=2.5)
    assert ergebnis["gruende"][gesicht.ZU_TIEF] == 2


# ------------------------------------------------------------- Die Bilder


def test_die_panoramen_werden_behalten(tmp_path):
    """Damit aus der Messung ein Testbild wird: eines MIT einem Gesicht."""
    spot = FakeSpot([[(700.0, 80.0, 40.0, 40.0, 0.9)], []])
    _probe(tmp_path, spot, dauer_s=2.5)
    bilder = sorted((tmp_path / Path(gesichtsprobe.BILDORDNER).name).glob("*.png"))
    assert len(bilder) >= 2
    assert bilder[0].stat().st_size > 0


def test_ohne_bilder_laeuft_die_messung_trotzdem(tmp_path):
    """Eine halbe Stunde Panoramen ist ein Gigabyte — das muss abschaltbar sein,
    ohne dass die Zahlen verloren gehen."""
    spot = FakeSpot([[(320.0, 180.0, 40.0, 40.0, 0.7)]])
    ergebnis = _probe(tmp_path, spot, bilder=False)
    assert not (tmp_path / Path(gesichtsprobe.BILDORDNER).name).exists()
    assert ergebnis["kaesten"] == 1


# ------------------------------------------------------------- Die Schranken


def test_eine_aussetzende_aufnahme_beendet_die_probe_nicht(tmp_path):
    """Vier Bilder je Takt ueber WLAN — ein Aussetzer ist der Normalfall."""
    aufrufe = {"n": 0}

    def kaputt(_spot, _gemerkt):
        aufrufe["n"] += 1
        raise RuntimeError("Funk weg")

    gesagt = []
    # Feinere Uhr: `probe` fragt sie mehrmals je Takt (Schleifenkopf, Taktbeginn,
    # Wartezeit). Mit einem Schritt von einer Sekunde waere nach einem Takt Schluss.
    ergebnis = gesichtsprobe.probe(
        FakeSpot([]), ziel=tmp_path, dauer_s=3.5, takt_s=0.1, jetzt=_uhr(0.25),
        schlaf=lambda _s: None, melde=gesagt.append, aufnahme_holen=kaputt,
    )
    assert aufrufe["n"] >= 2, "sie versucht es weiter"
    assert ergebnis["fehler"] >= 2
    assert len([s for s in gesagt if "fällt aus" in s]) == 1, "meldet EINMAL"


def test_das_programm_bewegt_nichts():
    """Dieselbe Naht wie bei der Sonde: die Probe steht still."""
    baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
    gerufen = {
        k.func.attr for k in ast.walk(baum)
        if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
    }
    verboten = gerufen & {"walk", "move", "stand", "sit", "power_on", "power_off",
                          "navigate_to", "send_command", "pose"}
    assert not verboten, f"Die Probe darf nichts bewegen, ruft aber: {sorted(verboten)}"


def test_die_probe_verbindet_ohne_lease():
    """Sie schaut nur zu — also nimmt sie dem Tablet nichts weg."""
    baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
    aufrufe = [k for k in ast.walk(baum)
               if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
               and k.func.attr == "connect"]
    assert aufrufe, "Vorbedingung: sie verbindet ueberhaupt"
    for aufruf in aufrufe:
        assert [w for w in aufruf.keywords
                if w.arg == "nur_lesen" and getattr(w.value, "value", None) is True]
