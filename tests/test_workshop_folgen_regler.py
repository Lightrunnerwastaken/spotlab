"""Der Regler gegen das Pendeln: die Peilung wird um die Drehung seit der Aufnahme nachgefuehrt.

Befund vom 17.09.2026 (Laeufe 09:41 und 09:49, Koerper-Finder, Takt 0.5-0.7 s): Spot
sah den Menschen bei +30 Grad, drehte -- und weil das Bild schon 0.5 s alt war, als
der Befehl kam, und der Befehl bis zum naechsten Blick weiterlief, drehte er ueber
den Menschen hinaus, verlor ihn 4 s lang, fand ihn auf der anderen Seite und drehte
zurueck. 35 Drehsinn-Wechsel in 100 s. Die Deckelung je Takt (ANTEIL_JE_TAKT) half
nicht, weil sie auf die VERALTETE Peilung rechnete.

Die Antwort: jede Aufnahme traegt den Gierwinkel, den der Roboter hatte, als das
Bild kam (`Ziel.gier`), und `folge()` zieht vor dem Befehl ab, was er seither
gedreht hat. Auch im Nachlauf. Dazu ein Totband, damit er um null nicht zappelt,
und je Takt eine Zeile `ziel` in der Aufzeichnung -- ohne sie war heute nicht zu
sehen, WAS der Finder lieferte.
"""

import json
import math
from types import SimpleNamespace

import pytest
from test_workshop_folgen import _laeuft_takte, _Spot, _uhr

from spotlab.workshop import folgen
from spotlab.workshop.folgen import Ziel


def _fahrten(spot):
    return [k for k in spot.kommandos if isinstance(k, dict)]


def _grad(wz):
    return math.degrees(wz)


# ------------------------------------------------------ Nachfuehren der Peilung


def test_die_peilung_wird_um_die_seit_der_aufnahme_gedrehte_gier_nachgefuehrt():
    """Gesehen bei +30 Grad, als der Roboter bei 0 Grad stand; jetzt steht er bei +20:
    es bleiben 10 Grad -- und der Befehl rechnet mit 10, nicht mit 30."""
    spot = _Spot(pose=(0.0, 0.0, math.radians(20.0)))
    folgen.folge(spot, lambda _s: Ziel(30.0, 3.0, "Körper", gier=0.0), melde=lambda _t: None,
                 jetzt=_uhr(0.05), schlaf=lambda _s: None, laeuft=_laeuft_takte(1))
    [fahrt] = _fahrten(spot)
    assert _grad(fahrt["wz"]) == pytest.approx(folgen.LENKUNG * 10.0, abs=0.1)


def test_ohne_gier_am_ziel_wird_nicht_nachgefuehrt():
    """Ein Tag kommt aus dem Weltmodell des Roboters, nicht aus einem alten Bild."""
    spot = _Spot(pose=(0.0, 0.0, math.radians(20.0)))
    folgen.folge(spot, lambda _s: Ziel(30.0, 3.0, "Tag 3"), melde=lambda _t: None,
                 jetzt=_uhr(0.05), schlaf=lambda _s: None, laeuft=_laeuft_takte(1))
    [fahrt] = _fahrten(spot)
    assert _grad(fahrt["wz"]) == pytest.approx(folgen.LENKUNG * 30.0, abs=0.1)


def test_die_nachfuehrung_rechnet_um_die_360_grad_herum():
    spot = _Spot(pose=(0.0, 0.0, math.radians(-170.0)))
    folgen.folge(spot, lambda _s: Ziel(30.0, 3.0, "Körper", gier=math.radians(170.0)),
                 melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(1))
    [fahrt] = _fahrten(spot)
    # von +170 nach -170 sind +20 Grad gedreht, nicht -340
    assert _grad(fahrt["wz"]) == pytest.approx(folgen.LENKUNG * 10.0, abs=0.1)


def test_im_nachlauf_wird_das_gehaltene_ziel_mit_der_gier_nachgefuehrt():
    """Der Roboter hat sich zum Menschen gedreht, dann fehlt ein Takt: das gehaltene
    Ziel liegt jetzt voraus, nicht mehr bei +30 -- sonst drehte er blind weiter."""
    spot = _Spot()
    plan = iter([Ziel(30.0, 3.0, "Körper", gier=0.0), None])

    def finde(s):
        ziel = next(plan, None)
        if ziel is None:
            s._pose = (0.0, 0.0, math.radians(30.0))     # inzwischen hingedreht
        return ziel

    folgen.folge(spot, finde, melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(2))
    erste, zweite = _fahrten(spot)[:2]
    assert _grad(erste["wz"]) > 0.0
    assert zweite["wz"] == 0.0, "im Nachlauf zeigt das Ziel voraus: kein Drehen mehr"
    assert zweite["vx"] > 0.0, "aber der Weg zum Ziel bleibt"


def test_eine_unlesbare_gier_laesst_die_peilung_wie_sie_ist():
    class _OhneLage(_Spot):
        @property
        def state(self):
            raise RuntimeError("kein Zustand")

    spot = _OhneLage()
    folgen.folge(spot, lambda _s: Ziel(30.0, 3.0, "Körper", gier=0.0), melde=lambda _t: None,
                 jetzt=_uhr(0.05), schlaf=lambda _s: None, laeuft=_laeuft_takte(1))
    assert _grad(_fahrten(spot)[0]["wz"]) == pytest.approx(folgen.LENKUNG * 30.0, abs=0.1)


# ------------------------------------------------------------------- Totband


def test_kleine_peilungen_werden_nicht_ausgeregelt():
    spot = _Spot()
    folgen.folge(spot, lambda _s: Ziel(folgen.PEILUNG_TOTBAND_GRAD - 0.5, 3.0, "Körper"),
                 melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(1))
    [fahrt] = _fahrten(spot)
    assert fahrt["wz"] == 0.0 and fahrt["vx"] > 0.0


def test_ab_dem_totband_wird_gedreht():
    assert folgen.befehl(Ziel(folgen.PEILUNG_TOTBAND_GRAD + 1.0, 3.0))[1] != 0.0
    assert folgen.befehl(Ziel(-(folgen.PEILUNG_TOTBAND_GRAD + 1.0), 3.0))[1] < 0.0


# -------------------------------------------------------- Die Aufnahme traegt die Gier


def test_die_bildaufnahme_traegt_die_gier_des_roboters(monkeypatch):
    """Dieselbe Zustands-Abfrage wie fuer den Nick: kein zweiter RPC."""
    import numpy as np

    from spotlab.backends.real import panorama, tiefe

    abfragen = {"n": 0}

    class _Mit(_Spot):
        @property
        def state(self):
            abfragen["n"] += 1
            return SimpleNamespace(pose=(0.0, 0.0, 0.7), pitch=-0.1)

    antwort = SimpleNamespace(source=SimpleNamespace(name="x"))
    monkeypatch.setattr(panorama, "kalibrierung_aus", lambda grau: "KAL")
    monkeypatch.setattr(panorama, "bilder_aus", lambda grau: [])

    class _Pano:
        def __init__(self, kal, zuschnitt=None):
            pass

        def zusammensetzen(self, bilder):
            return np.zeros((4, 4), dtype="uint8")

    monkeypatch.setattr(panorama, "Panorama", _Pano)
    monkeypatch.setattr(tiefe, "punkte_aus_bild", lambda a: np.zeros((1, 3)))
    spot = _Mit()
    spot.backend = SimpleNamespace(images=lambda quellen, **kw: [
        SimpleNamespace(source=SimpleNamespace(name=q)) for q in quellen])
    del antwort
    aufnahme = folgen.bildaufnahme(spot, {}, ("a", "b"), ("t",))
    assert aufnahme.gier == pytest.approx(0.7)
    assert aufnahme.blick_grad == pytest.approx(math.degrees(0.1))
    assert abfragen["n"] == 1


def test_der_koerperfinder_gibt_die_gier_der_aufnahme_weiter():
    from test_workshop_folgen import _ein_koerper, _koerperaufnahme_bei

    from spotlab.workshop.folgen import Gesichtsaufnahme

    holen = _koerperaufnahme_bei(10.0)

    def mit_gier(spot, gemerkt, *a, **kw):
        aufnahme = holen(spot, gemerkt)
        return Gesichtsaufnahme(aufnahme.feld, aufnahme.pano, None, aufnahme.punkte,
                                aufnahme.blick_grad, gier=0.25)

    finder = folgen.koerper_finder(aufnahme_holen=mit_gier, koerper_holen=lambda feld: [_ein_koerper()])
    assert finder(_Spot()).gier == pytest.approx(0.25)


# --------------------------------------------------- Jeder Takt mit Ziel im Lauf


def test_jeder_takt_mit_ziel_steht_in_der_aufzeichnung_und_das_wegbleiben_einmal(tmp_path):
    """Am 17.09.2026 liess sich aus 169 walk-Befehlen nicht sagen, WAS der Finder sah --
    ob ein Mensch bei +60 Grad oder ein Phantom. Jetzt steht es je Takt da, beim
    echten Schreiber (Erlaubnisliste!)."""
    from spotlab.record.run import RunRecorder

    spot = _Spot(pose=(0.0, 0.0, math.radians(5.0)))
    spot.recorder = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    plan = iter([Ziel(30.0, 3.0, "Körper, Hüfte auf 1.00 m", gier=0.0, bild_oben=12.0),
                 Ziel(20.0, 2.5, "Gesicht auf 1.60 m", gier=0.0), None, None, None, None])
    folgen.folge(spot, lambda _s: next(plan, None), melde=lambda _t: None, jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6), nachlauf_s=0.0)
    zeilen = [json.loads(z) for z in
              (spot.recorder.dir / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
              if z.strip()]
    ziele = [z["daten"] for z in zeilen if z["art"] == "ziel"]
    assert len(ziele) == 3, "zwei Takte mit Ziel, dann EINMAL das Wegbleiben -- nicht jeden leeren Takt"
    assert ziele[0]["finder"] == "Körper, Hüfte auf 1.00 m"
    assert ziele[0]["peilung"] == pytest.approx(30.0)
    assert ziele[0]["peilung_jetzt"] == pytest.approx(25.0), "um die 5 Grad Drehung nachgefuehrt"
    assert ziele[0]["abstand"] == pytest.approx(3.0) and ziele[0]["bild_oben"] == pytest.approx(12.0)
    assert ziele[0]["echt"] is True and ziele[0]["vx"] > 0 and ziele[0]["wz_grad"] > 0
    assert ziele[1]["finder"].startswith("Gesicht")
    assert ziele[2] == {"finder": None, "weg": True} or ziele[2]["finder"] is None


def test_die_ereignisart_ziel_ist_erlaubt():
    from spotlab.record.events import ARTEN

    assert "ziel" in ARTEN


# ----------------------------------------------------------- Die Kreissperre


def _mitdrehendes_ziel(peilung=60.0, schritt_grad=30.0):
    """Ein Ziel, das im Bild stehen bleibt, waehrend der Roboter dreht -- je Takt dreht
    er `schritt_grad` weiter, und das Ziel ist wieder bei `peilung`. So sah der Lauf
    vom 17.09.2026 09:41 aus: 14 Takte +45 Grad/s, 400 Grad, das Ziel nie voraus."""
    stand = {"gier": 0.0}

    def finde(s):
        stand["gier"] += math.radians(schritt_grad)
        s._pose = (0.0, 0.0, stand["gier"])
        return Ziel(peilung, 2.0, "Körper", gier=stand["gier"])

    return finde


def test_nach_einer_halben_drehung_ohne_ziel_voraus_hoert_er_auf_zu_drehen():
    spot = _Spot(neigt=True)          # mit Suchhaltung gibt es je Takt einen Befehl, auch im Stand
    gesagt = []
    folgen.folge(spot, _mitdrehendes_ziel(), melde=gesagt.append, jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(10))
    fahrten = _fahrten(spot)
    assert all(f["wz"] > 0.0 for f in fahrten[:5]), "bis 150 Grad dreht er dem Ziel nach"
    assert all(f["wz"] == 0.0 and f["vx"] == 0.0 for f in fahrten[6:]), "ab 180 Grad steht er"
    assert len([m for m in gesagt if "gedreht" in m]) == 1


def test_ein_ziel_das_vor_ihn_kommt_setzt_die_drehsperre_zurueck():
    spot = _Spot(neigt=True)
    mitdrehend = _mitdrehendes_ziel()
    plan = iter([mitdrehend, mitdrehend, mitdrehend, lambda s: Ziel(10.0, 2.0, "Körper"),
                 mitdrehend, mitdrehend, mitdrehend])

    def finde(s):
        return next(plan)(s)

    folgen.folge(spot, finde, melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(7))
    fahrten = _fahrten(spot)
    assert all(f["wz"] > 0.0 for f in fahrten[4:]), "nach dem Ziel voraus zaehlt die Drehung von vorn"


def test_ohne_ziel_faellt_die_drehsperre_weg():
    spot = _Spot(neigt=True)
    mitdrehend = _mitdrehendes_ziel()
    plan = [mitdrehend] * 7 + [lambda s: None] * 2 + [mitdrehend] * 3

    def finde(s):
        return plan.pop(0)(s)

    folgen.folge(spot, finde, melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(12), nachlauf_s=0.0)
    fahrten = _fahrten(spot)
    assert fahrten[6]["wz"] == 0.0, "gesperrt"
    assert fahrten[-1]["wz"] > 0.0, "nach der Luecke wieder frei"
