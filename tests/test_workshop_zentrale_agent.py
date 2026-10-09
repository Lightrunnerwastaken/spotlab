"""Der Agent in der Steuerzentrale (Agenten am Spot, Teil 1): Befehle, Freigabe, Totmann."""

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
from test_workshop_zentrale import (
    T0,
    _fahrten,
    _Folge,
    _KameraSpot,
    _Licht,
    _Spot,
    _Suche,
    _zentrale,
)

from spotlab.backends.base import Capability, ObstacleGrid
from spotlab.record import agent as agentdatei
from spotlab.record import fahrt
from spotlab.record import zentrale as protokoll
from spotlab.record.run import RunRecorder
from spotlab.workshop import agentfahrt, zentrale


def _befehl(lauf, nummer, art, werte=None, uhr=None, warum="zum Test"):
    agentdatei.schreibe_befehl(lauf, nummer, art, werte or {}, warum, "claude",
                               jetzt=(lambda: uhr["t"]) if uhr else (lambda: T0))


def _agent(lauf):
    return protokoll.lies_lagebild(lauf)["agent"]


def _freigabe(lauf, an=True, nummer=1, t=T0):
    agentdatei.schreibe_freigabe(lauf, an, nummer, jetzt=lambda: t)
    protokoll.schreibe_gui_puls(lauf, jetzt=lambda: t)


def _mit_uhr(spot, tmp_path, **kw):
    uhr = {"t": T0}
    z = _zentrale(spot, tmp_path, jetzt=lambda: uhr["t"], **kw)
    z.wahrnehmen()
    return z, uhr


# ------------------------------------------------------------ Ziele


def test_ein_agentenziel_faehrt_wie_ein_klick_und_steht_im_lagebild(tmp_path):
    spot = _Spot()
    z, _ = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0}, warum="zur Tür")
    z.takt()
    assert _fahrten(spot)[-1]["vx"] > 0.0
    assert z.klick.unterwegs and z.klick.stand.quelle == "agent"
    z.wahrnehmen()
    stand = _agent(tmp_path)
    assert (stand["nummer"], stand["art"], stand["zustand"], stand["warum"]) == (
        1, "ziel", "unterwegs", "zur Tür")
    assert stand["braucht_freigabe"] is False and protokoll.lies_lagebild(tmp_path)[
        "klickfahrt"]["quelle"] == "agent"


def test_relativ_rechnet_vom_blick_aus(tmp_path):
    spot = _Spot()
    spot._pose = (1.0, 1.0, math.pi / 2)            # Blick nach +y
    z, _ = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "relativ", {"vor_m": 1.0, "links_m": 0.0})
    z.takt()
    assert z.klick.stand.ziel == pytest.approx((1.0, 2.0))


def test_angekommen_steht_als_ergebnis_da(tmp_path):
    spot = _Spot()
    z, uhr = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": 2.0, "y": 1.0}, uhr=uhr)
    z.takt()
    spot._pose = (2.0, 1.0, 0.0)
    uhr["t"] += 0.1
    _befehl(tmp_path, 1, "ziel", {"x": 2.0, "y": 1.0}, uhr=uhr)   # das Lebenszeichen
    z.takt()
    assert z._agent["zustand"] == "angekommen"


def test_ein_ziel_ohne_zahlen_wird_abgelehnt(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": "da"})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and "Zahl" in z._agent["grund"]


# ------------------------------------------------------------ Freigabe


def test_am_echten_spot_ohne_freigabe_wird_abgelehnt(tmp_path):
    spot = _Spot()
    z, _ = _mit_uhr(spot, tmp_path, braucht_freigabe=True)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and "Freigabe" in z._agent["grund"]
    assert not _fahrten(spot)


def test_mit_freigabe_faehrt_er(tmp_path):
    spot = _Spot()
    z, _ = _mit_uhr(spot, tmp_path, braucht_freigabe=True)
    _freigabe(tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    assert _fahrten(spot) and z._agent["zustand"] == "unterwegs"


def test_geht_die_freigabe_aus_bricht_die_fahrt_ab(tmp_path):
    spot = _Spot()
    z, _ = _mit_uhr(spot, tmp_path, braucht_freigabe=True)
    _freigabe(tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    _freigabe(tmp_path, an=False, nummer=2)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    assert spot.kommandos[-1] == "stop"
    assert z._agent["zustand"] == "abgebrochen" and "Freigabe" in z._agent["grund"]
    assert not z.klick.unterwegs


def test_lesen_geht_ohne_freigabe(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path, braucht_freigabe=True)
    _befehl(tmp_path, 1, "tiefe")
    z.takt()
    z.wahrnehmen()
    assert "Freigabe" not in z._agent["grund"]
    assert z._agent["zustand"] == "abgelehnt" and "nicht messbar" in z._agent["grund"]


# ------------------------------------------------------------ Vorrang und Totmann


def test_ohne_lebenszeichen_des_agenten_steht_er(tmp_path):
    spot = _Spot()
    z, uhr = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0}, uhr=uhr)
    z.takt()
    uhr["t"] = T0 + agentdatei.AGENT_TOTMANN_S + 0.1
    z.takt()
    assert spot.kommandos[-1] == "stop"
    assert z._agent["zustand"] == "abgebrochen" and "Lebenszeichen" in z._agent["grund"]


def test_eine_taste_uebernimmt_vom_agenten(tmp_path):
    spot = _Spot()
    z, _ = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    fahrt.schreibe(tmp_path, 0.4, 0.0, 0.0, jetzt=lambda: T0)
    z.takt()
    assert _fahrten(spot)[-1]["vx"] == pytest.approx(0.4)
    assert z._agent["zustand"] == "abgebrochen" and "Mensch" in z._agent["grund"]


def test_ein_klick_uebernimmt_vom_agenten(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    protokoll.schreibe_klickziel(tmp_path, 1, (1.0, 2.5), "normal", jetzt=lambda: T0)
    z.takt()
    assert z._agent["zustand"] == "abgebrochen" and "Mensch" in z._agent["grund"]
    assert z.klick.stand.quelle == "tab" and z.klick.unterwegs


def test_der_klick_geht_vor_dem_agenten(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path)
    protokoll.schreibe_klickziel(tmp_path, 1, (2.5, 1.0), "normal", jetzt=lambda: T0)
    z.takt()
    _befehl(tmp_path, 1, "drehen", {"grad": 90})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and "Mensch" in z._agent["grund"]
    assert z.klick.stand.quelle == "tab" and z.klick.unterwegs


def test_stopp_haelt_den_laufenden_befehl_an(tmp_path):
    spot = _Spot()
    z, _ = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    _befehl(tmp_path, 2, "stopp")
    z.takt()
    assert spot.kommandos[-1] == "stop" and not z.klick.unterwegs
    assert z._agent["nummer"] == 2 and z._agent["zustand"] == "erledigt"


# ------------------------------------------------------------ Drehen und Stoss


def test_drehen_gegen_die_gemessene_gier(tmp_path):
    spot = _Spot()
    z, uhr = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "drehen", {"grad": 90}, uhr=uhr)
    z.takt()
    fahrt_ = _fahrten(spot)[-1]
    assert fahrt_["vx"] == 0.0 and fahrt_["wz"] > 0.0
    spot._pose = (1.0, 1.0, math.radians(88.5))
    uhr["t"] += 0.1
    _befehl(tmp_path, 1, "drehen", {"grad": 90}, uhr=uhr)
    z.takt()
    assert z._agent["zustand"] == "angekommen" and spot.kommandos[-1] == "stop"


def test_ein_stoss_wird_gekappt_und_endet_nach_der_dauer(tmp_path):
    spot = _Spot()
    z, uhr = _mit_uhr(spot, tmp_path)
    z._kopf, z._kopf_t = (True, ""), T0
    _befehl(tmp_path, 1, "stoss", {"vx": 2.0, "vy": 0.0, "wz": 0.0, "dauer_s": 9}, uhr=uhr)
    z.takt()
    assert 0.0 < _fahrten(spot)[-1]["vx"] <= fahrt.TEMPO_M_S
    uhr["t"] = T0 + agentfahrt.STOSS_MAX_S + 0.01
    _befehl(tmp_path, 1, "stoss", {"vx": 2.0, "vy": 0.0, "wz": 0.0, "dauer_s": 9}, uhr=uhr)
    z.takt()
    assert z._agent["zustand"] == "angekommen" and spot.kommandos[-1] == "stop"


def test_rueckwaerts_ueber_ungesehenen_boden_gibt_es_keinen_stoss(tmp_path):
    n = 128
    blind = ObstacleGrid(cells=np.full((n, n), 1.0), cell_size=0.03, origin=(-0.92, -0.92),
                         time=0.0, known=np.zeros((n, n), bool))
    spot = _Spot(gitter=blind)
    z, _ = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "stoss", {"vx": -0.2, "vy": 0.0, "wz": 0.0, "dauer_s": 1.0})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and "hinten" in z._agent["grund"]
    assert not _fahrten(spot)


# ------------------------------------------------------------ Tiefe, Licht, Suche


class _TiefenSpot(_Spot):
    def __init__(self, punkte, **kw):
        super().__init__(**kw)
        self.punkte = punkte
        self.backend.capabilities = lambda: (Capability.LOCOMOTION | Capability.LOCAL_GRID
                                             | Capability.DEPTH_CAMERAS)

    def point_cloud(self, name, frame="body", **_kw):
        assert frame == "body"
        return SimpleNamespace(points=self.punkte[name])


def test_die_tiefe_misst_je_sektor_im_wahrnehmungsfaden(tmp_path):
    vorne = np.column_stack([np.linspace(1.2, 2.0, 40), np.zeros(40), np.zeros(40)])
    spot = _TiefenSpot({"frontleft": vorne, "frontright": vorne + [0.0, 0.0, 0.1]})
    z, _ = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "tiefe")
    z.takt()
    assert z._agent["zustand"] == "unterwegs", "gemessen wird im Wahrnehmungsfaden"
    z.wahrnehmen()
    stand = _agent(tmp_path)
    assert stand["zustand"] == "gemessen"
    assert stand["tiefe"]["sektoren"]["mitte"]["abstand_m"] == pytest.approx(1.2, abs=0.05)
    assert stand["tiefe"]["sektoren"]["links"]["abstand_m"] is None
    assert "kopfraum" in stand["tiefe"]


def test_licht_ton_und_suche_ueber_den_agenten(tmp_path):
    spot = _KameraSpot(licht=True)
    z, _ = _mit_uhr(spot, tmp_path, licht=_Licht(spot.kommandos), hintergrund=lambda f: f(),
                    suche=_Suche())
    _befehl(tmp_path, 1, "licht", {"farbe": "gruen"})
    z.takt()
    _befehl(tmp_path, 2, "piep")
    z.takt()
    _befehl(tmp_path, 3, "suche", {"stufe": "normal"})
    z.takt()
    assert spot.kommandos == [("licht", "green"), "beep"]
    assert z._suchstufe == "normal" and z._agent["zustand"] == "erledigt"


def test_licht_ohne_av_dienst_wird_abgelehnt(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path)
    _befehl(tmp_path, 1, "licht", {"farbe": "rot"})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and "Licht" in z._agent["grund"]


# ------------------------------------------------------------ Folgen


def test_folgen_uebergibt_an_den_folgemodus_bis_ein_neuer_befehl_kommt(tmp_path):
    def je_takt(n, kw):
        uhr["t"] += 0.1
        _befehl(tmp_path, 1 if n < 3 else 2, "folgen" if n < 3 else "stopp",
                {"x": 3.0, "y": 1.0}, uhr=uhr)

    uhr = {"t": T0}
    folge = _Folge(je_takt)
    z = _zentrale(_KameraSpot(), tmp_path, suche=_Suche(), folgen_mit=folge,
                  koerper_finder=lambda: (lambda spot: None), jetzt=lambda: uhr["t"])
    _befehl(tmp_path, 1, "folgen", {"x": 3.0, "y": 1.0}, uhr=uhr)
    z.takt()
    assert folge.kw is not None and folge.n == 3
    assert z.klick.stand.quelle == "agent" and "neuer Befehl" in z.klick.stand.grund
    assert z._agent["nummer"] == 1 and z._agent["zustand"] == "abgebrochen"
    z.takt()
    assert z._agent["nummer"] == 2 and z._agent["zustand"] == "erledigt"


def test_ohne_kameras_wird_folgen_abgelehnt(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path)
    _befehl(tmp_path, 1, "folgen", {"x": 3.0, "y": 1.0})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and z._agent["grund"] == zentrale.KEINE_KAMERAS


# ------------------------------------------------------------ Aufzeichnung


def test_befehl_ergebnis_und_freigabe_stehen_in_der_echten_aufzeichnung(tmp_path):
    spot = _Spot()
    spot.recorder = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    lauf = spot.recorder.dir
    z, uhr = _mit_uhr(spot, lauf, braucht_freigabe=True)
    _freigabe(lauf)
    _befehl(lauf, 1, "drehen", {"grad": 45}, uhr=uhr, warum="zum Fenster schauen")
    z.takt()
    uhr["t"] += agentdatei.AGENT_TOTMANN_S + 0.1
    z.takt()
    ereignisse = [json.loads(zeile) for zeile in (lauf / "ereignisse.jsonl").read_text(
        encoding="utf-8").splitlines()]
    nach_art = {e["art"]: e["daten"] for e in ereignisse}
    assert nach_art["freigabe"]["an"] is True
    assert nach_art["agent_befehl"]["warum"] == "zum Fenster schauen"
    assert nach_art["agent_befehl"]["werte"] == {"grad": 45}
    assert nach_art["agent_ergebnis"]["zustand"] == "abgebrochen"
    assert nach_art["agent_ergebnis"]["dauer_s"] == pytest.approx(
        agentdatei.AGENT_TOTMANN_S + 0.1, abs=0.01)


@pytest.mark.parametrize("backend, noetig", [("dryrun", False), ("sim", False), ("mujoco", False),
                                             ("physics", False), ("real", True), (None, True)])
def test_freigabe_braucht_jedes_backend_ausser_dem_uebungsraum(tmp_path, backend, noetig):
    if backend is not None:
        RunRecorder(tmp_path, None, backend=backend)
    lauf = next((p for p in tmp_path.iterdir() if p.is_dir()), tmp_path)
    assert zentrale.freigabe_noetig(lauf) is noetig
