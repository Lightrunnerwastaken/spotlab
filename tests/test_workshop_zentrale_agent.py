"""Der Agent in der Steuerzentrale (Agenten am Spot, Teil 1): Befehle, Freigabe, Totmann."""

import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
from test_workshop_folgen import _baum
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

from spotlab.backends.base import Capability, NavStatus, ObstacleGrid
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


# ------------------------------------------------------------ Warten auf die Freigabe


class _MotorSpot(_Spot):
    def power_on(self):
        self.kommandos.append("power_on")

    def stand(self):
        self.kommandos.append("stand")


def test_ohne_freigabe_bleiben_die_motoren_aus_und_nichts_faehrt(tmp_path):
    spot = _MotorSpot()
    gesagt = []
    z, _ = _mit_uhr(spot, tmp_path, braucht_freigabe=True, warte_auf_freigabe=True,
                    melde=gesagt.append)
    fahrt.schreibe(tmp_path, 0.4, 0.0, 0.0, jetzt=lambda: T0)
    protokoll.schreibe_klickziel(tmp_path, 1, (2.5, 1.0), "normal", jetzt=lambda: T0)
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    z.wahrnehmen()
    assert spot.kommandos == [] and z.wartet
    assert z._agent["zustand"] == "abgelehnt" and "Freigabe" in z._agent["grund"]
    assert "wartet auf Freigabe" in protokoll.lies_lagebild(tmp_path)["motoren"]
    assert any("Motoren" in text for text in gesagt), gesagt
    assert not z.klick.unterwegs, "ein Klick aus der Wartezeit fährt nicht später los"


def test_mit_der_freigabe_steht_spot_auf_und_faehrt_dann(tmp_path):
    spot = _MotorSpot()
    z, _ = _mit_uhr(spot, tmp_path, braucht_freigabe=True, warte_auf_freigabe=True)
    protokoll.schreibe_klickziel(tmp_path, 1, (2.5, 1.0), "normal", jetzt=lambda: T0)
    z.takt()
    _freigabe(tmp_path)
    z.takt()
    assert spot.kommandos == ["power_on", "stand"] and not z.wartet
    assert not z.klick.unterwegs, "der alte Klick ist verbraucht"
    _befehl(tmp_path, 1, "ziel", {"x": 2.5, "y": 1.0})
    z.takt()
    assert _fahrten(spot) and z._agent["zustand"] == "unterwegs"
    z.wahrnehmen()
    assert protokoll.lies_lagebild(tmp_path)["motoren"] is None


def test_schlaegt_das_aufstehen_fehl_wartet_sie_auf_eine_neue_freigabe(tmp_path):
    class _Kaputt(_MotorSpot):
        def power_on(self):
            self.kommandos.append("power_on")
            raise RuntimeError("Not-Aus am Tablet")

    spot = _Kaputt()
    gesagt = []
    z, _ = _mit_uhr(spot, tmp_path, braucht_freigabe=True, warte_auf_freigabe=True,
                    melde=gesagt.append)
    _freigabe(tmp_path)
    z.takt()
    z.takt()
    assert spot.kommandos == ["power_on"] and z.wartet, "kein zweiter Versuch ohne neue Freigabe"
    assert any("Not-Aus am Tablet" in text for text in gesagt)
    _freigabe(tmp_path, an=False, nummer=2)
    z.takt()
    _freigabe(tmp_path, an=True, nummer=3)
    z.takt()
    assert spot.kommandos == ["power_on", "power_on"]


def test_am_ende_haelt_eine_wartende_zentrale_nichts_an(tmp_path):
    spot = _MotorSpot()
    z, _ = _mit_uhr(spot, tmp_path, braucht_freigabe=True, warte_auf_freigabe=True)
    runden = {"n": 0}

    def laeuft():
        runden["n"] += 1
        return runden["n"] <= 2

    z.lauf(laeuft, schlaf=lambda _s: None, mit_blick=False)
    assert "stop" not in spot.kommandos, "mit Motoren aus gibt es nichts anzuhalten"


def test_das_echte_programm_wartet_mit_motoren_aus_auf_die_freigabe(tmp_path):
    """Der Startweg des Agenten am echten Spot, mit dem Trockenlauf statt des Roboters:
    verbinden, Lagebild, Motoren aus -- erst die Freigabe schaltet ein und stellt Spot hin."""
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    import spotlab
    from spotlab.record.run import STOPP_DATEI
    from tests_zeitgrenzen import TEST_TIMEOUT_S, warte_bis

    quelle = str(Path(spotlab.__file__).resolve().parents[1])
    env = dict(os.environ, SPOTLAB_BACKEND="dryrun", SPOTLAB_NUR_TROCKEN="1", PYTHONUTF8="1",
               PYTHONPATH=os.pathsep.join([quelle] + [os.environ.get("PYTHONPATH", "")]))
    prozess = subprocess.Popen(
        [sys.executable, "-m", "spotlab.workshop.zentrale", "--runs", str(tmp_path),
         "--auf-freigabe-warten"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace")
    try:
        lauf = warte_bis(lambda: next((p for p in tmp_path.iterdir() if p.is_dir()), None)
                         if prozess.poll() is None else "tot", "das Lauf-Verzeichnis")
        assert lauf != "tot", prozess.communicate()[0][-3000:]
        bild = warte_bis(lambda: protokoll.lies_lagebild(lauf) or prozess.poll() is not None,
                         "das erste Lagebild")
        assert prozess.poll() is None, prozess.communicate()[0][-3000:]
        assert "wartet auf Freigabe" in bild["motoren"]
        _freigabe(lauf, t=time.time())
        warte_bis(lambda: (protokoll.lies_lagebild(lauf) or {}).get("motoren", "") is None
                  or prozess.poll() is not None, "Spot steht auf")
        (lauf / STOPP_DATEI).touch()
        ausgabe, _ = prozess.communicate(timeout=TEST_TIMEOUT_S)
    finally:
        if prozess.poll() is None:
            prozess.kill()
            prozess.communicate()
    # Die Stopp-Datei endet wie der Stopp-Knopf (Abbruch im Hauptfaden, Abbau durch connect).
    assert "Traceback" not in ausgabe, ausgabe[-3000:]
    ereignisse = [json.loads(z) for z in (lauf / "ereignisse.jsonl").read_text(
        encoding="utf-8").splitlines()]
    arten = [e["daten"].get("name") if e["art"] == "kommando" else e["art"] for e in ereignisse]
    freigabe = arten.index("freigabe")
    assert "power_on" not in arten[:freigabe], arten
    assert arten.index("power_on") > freigabe and "stand" in arten[freigabe:], arten


def test_das_lagebild_traegt_den_kopfraum_fuer_den_agenten(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path)
    z._kopf, z._kopf_t = (False, "Überhang 0.6 m voraus"), T0 - 0.5   # noch nicht neu fällig
    z.wahrnehmen()
    kopf = protokoll.lies_lagebild(tmp_path)["kopfraum"]
    assert kopf["frei"] is False and "Überhang" in kopf["grund"] and kopf["alter_s"] == 0.5


# ------------------------------------------------------------ Karten und Merkorte (Teil 2)


class _Kartenarbeit:
    """Eine Kartenarbeit-Attrappe mit Auftraggebern: ein Auftrag läuft, bis `fertig()` kommt."""

    def __init__(self, kann=True, ablehnen=None):
        self.kann, self.ablehnen = kann, ablehnen
        self.auftraege = []
        self.arbeitet = False
        self.zustand, self.name, self.grund, self.gespeichert_als = "keine", None, "", None

    def auftrag(self, nummer, was, name=None, quelle="tab"):
        self.auftraege.append((nummer, was, name, quelle))
        if self.ablehnen:
            self.grund = self.ablehnen
            return self.ablehnen
        self.arbeitet = True
        return None

    def fertig(self, **felder):
        for schluessel, wert in felder.items():
            setattr(self, schluessel, wert)
        self.arbeitet = False

    def beobachte(self, t):
        pass

    def abgleiche(self, skizze, spot_xy, t):
        return None

    def daten(self, t, abgleich):
        return {"kann": self.kann, "zustand": self.zustand, "name": self.name}

    def beenden(self):
        pass


def test_ein_kartenauftrag_des_agenten_endet_wenn_die_kartenarbeit_fertig_ist(tmp_path):
    karten = _Kartenarbeit()
    z, _ = _mit_uhr(_Spot(), tmp_path, kartenarbeit=karten)
    _befehl(tmp_path, 1, "karte_laden", {"name": "flur2"})
    z.takt()
    assert karten.auftraege == [(1, "laden", "flur2", "agent")]
    assert z._agent["zustand"] == "unterwegs"
    z.takt()
    assert z._agent["zustand"] == "unterwegs", "solange die Kartenarbeit arbeitet"
    karten.fertig(zustand="verortet", name="flur2", grund="")
    z.takt()
    assert z._agent["zustand"] == "erledigt"
    assert z._agent["karte"] == {"zustand": "verortet", "name": "flur2", "grund": "",
                                 "gespeichert_als": None}


def test_ein_gescheitertes_laden_kommt_als_abgebrochen_mit_grund(tmp_path):
    karten = _Kartenarbeit()
    z, _ = _mit_uhr(_Spot(), tmp_path, kartenarbeit=karten)
    _befehl(tmp_path, 1, "karte_laden", {"name": "gibtsnicht"})
    z.takt()
    karten.fertig(zustand="keine", grund="Laden gescheitert: gibt es nicht")
    z.takt()
    assert z._agent["zustand"] == "abgebrochen" and "gescheitert" in z._agent["grund"]


def test_eine_abgelehnte_kartenarbeit_sagt_warum(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path, kartenarbeit=_Kartenarbeit(ablehnen="Es läuft keine Aufnahme."))
    _befehl(tmp_path, 1, "aufnahme_stopp")
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and "keine Aufnahme" in z._agent["grund"]


@pytest.mark.parametrize("karten", [None, _Kartenarbeit(kann=False)])
def test_im_uebungsraum_gibt_es_keine_karten(tmp_path, karten):
    z, _ = _mit_uhr(_Spot(), tmp_path, kartenarbeit=karten)
    _befehl(tmp_path, 1, "karte_laden", {"name": "flur2"})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and "merkort_setzen" in z._agent["grund"]


def test_eine_taste_bricht_keine_kartenarbeit_ab(tmp_path):
    karten = _Kartenarbeit()
    z, _ = _mit_uhr(_Spot(), tmp_path, kartenarbeit=karten)
    _befehl(tmp_path, 1, "aufnahme_start", {"name": "gang"})
    z.takt()
    fahrt.schreibe(tmp_path, 0.4, 0.0, 0.0, jetzt=lambda: T0)
    z.takt()
    assert z._agent["zustand"] == "unterwegs", "eine Aufnahme ist keine Fahrt"
    fahrt.schreibe(tmp_path, 0.0, 0.0, 0.0, jetzt=lambda: T0)        # Taste los
    karten.fertig(zustand="nimmt_auf")
    z.takt()
    assert z._agent["zustand"] == "erledigt"


def test_ein_merkort_an_spots_ort_und_mit_zahlen(tmp_path):
    z, _ = _mit_uhr(_Spot(), tmp_path)
    _befehl(tmp_path, 1, "merkort_setzen", {"name": "start"})
    z.takt()
    _befehl(tmp_path, 2, "merkort_setzen", {"name": "Tür", "x": 3.0, "y": 1.5})
    z.takt()
    assert z._agent["zustand"] == "erledigt"
    z.wahrnehmen()
    assert protokoll.lies_lagebild(tmp_path)["merkorte"] == [
        {"name": "start", "x": 1.0, "y": 1.0}, {"name": "Tür", "x": 3.0, "y": 1.5}]
    _befehl(tmp_path, 3, "merkort_loeschen", {"name": "start"})
    z.takt()
    _befehl(tmp_path, 4, "zum_merkort", {"name": "start"})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and "Tür" in z._agent["grund"]


def test_zum_merkort_faehrt_weiter_als_ein_klick(tmp_path):
    from test_workshop_zentrale import _gitter_um

    spot = _Spot(gitter=_gitter_um(1.0, 1.0, halb=8.0, zelle=0.1))
    z, _ = _mit_uhr(spot, tmp_path)
    _befehl(tmp_path, 1, "merkort_setzen", {"name": "fern", "x": 8.0, "y": 1.0})   # 7 m
    z.takt()
    _befehl(tmp_path, 2, "zum_merkort", {"name": "fern"})
    z.takt()
    assert z._agent["zustand"] == "unterwegs" and z.klick.unterwegs
    assert _fahrten(spot)[-1]["vx"] > 0.0


def test_die_merkorte_bleiben_im_uebungsraum_in_einer_datei(tmp_path):
    from spotlab.workshop import merkorte as mo

    uebung = RunRecorder(tmp_path / "runs", None, backend="sim")
    ort = zentrale.merkorte_fuer(uebung.dir, tmp_path / "ws", "durchgang")
    assert ort.pfad == mo.pfad_fuer(tmp_path / "ws", "durchgang")
    echt = RunRecorder(tmp_path / "runs2", None, backend="real")
    assert zentrale.merkorte_fuer(echt.dir, tmp_path / "ws", "durchgang").pfad is None
    assert zentrale.merkorte_fuer(uebung.dir, None, "durchgang").pfad is None


# ------------------------------------------------------------ Fahrt zu einem Wegpunkt (Teil 2)


def _stopp_gesendet(backend):
    return any(k.synchronized_command.mobility_command.HasField("stop_request")
               or k.full_body_command.HasField("stop_request") for k in backend.gesendet)


class _NaviBackend:
    """Trockenlauf plus GraphNav: `je_status(n)` läuft vor jeder Statusabfrage (n = Befehle)."""

    def __new__(cls, spot, folge=(), je_status=None):
        from spotlab.backends.dryrun import DryRunBackend

        class Backend(DryRunBackend):
            def capabilities(self):
                return Capability.LOCOMOTION | Capability.LOCAL_GRID | Capability.GRAPH_NAV

            def frame_tree_snapshot(self):
                return _baum(*spot._pose)

            def travel_params(self, limits):
                return "params"

            def navigate_step(self, waypoint_id, dauer_s, params, command_id=None):
                self.navi.append(waypoint_id)
                return 7

            def navigation_status(self, command_id):
                if je_status is not None:
                    je_status(len(self.navi))
                if self.folge:
                    return self.folge.pop(0)
                return NavStatus(fertig=True, status="Angekommen.", gescheitert=False)

        backend = Backend()
        backend.power_on()
        backend.navi, backend.folge = [], list(folge)
        return backend


class _NaviSpot(_Spot):
    def __init__(self, folge=(), je_status=None):
        from spotlab.config import Limits

        super().__init__()
        self.backend = _NaviBackend(self, folge, je_status)
        self.recorder, self.limits = None, Limits()


class _NaviKarten(_Kartenarbeit):
    def __init__(self, fehler=None):
        super().__init__()
        self.fehler = fehler
        self.zustand, self.name = "verortet", "flur2"

    def navigationskarte(self):
        from pathlib import Path

        from test_api_navigation import _graph

        from spotlab.api.navigation import Map
        from spotlab.errors import SpotlabError

        if self.fehler:
            raise SpotlabError(self.fehler)
        return Map(name="flur2", dir=Path("flur2"), graph=_graph())


def _unterwegs(n=30):
    return [NavStatus(fertig=False, status="Unterwegs.", gescheitert=False)] * n


def test_zum_wegpunkt_faehrt_mit_der_karte_und_kommt_an(tmp_path):
    spot = _NaviSpot(folge=_unterwegs(2))
    z, _ = _mit_uhr(spot, tmp_path, kartenarbeit=_NaviKarten())
    _befehl(tmp_path, 1, "zum_wegpunkt", {"name": "kueche"})
    z.takt()
    assert spot.backend.navi[:3] == ["wp1", "wp1", "wp1"]
    assert z._agent["zustand"] == "angekommen"
    assert (z.klick.stand.zustand, z.klick.stand.quelle) == ("angekommen", "agent")


@pytest.mark.parametrize("stoerung, erwartet", [
    ("taste", "Taste"), ("klick", "Mensch"), ("befehl", "neuer Befehl"),
    ("still", "Lebenszeichen"), ("freigabe", "Freigabe"), ("verloren", "verloren")])
def test_die_wegpunktfahrt_bricht_ab(tmp_path, stoerung, erwartet):
    karten = _NaviKarten()
    uhr = {"t": T0}

    def je_status(n):
        if n != 2:
            return
        if stoerung == "taste":
            fahrt.schreibe(tmp_path, 0.4, 0.0, 0.0, jetzt=lambda: uhr["t"])
        elif stoerung == "klick":
            protokoll.schreibe_klickziel(tmp_path, 9, (1.5, 1.0), "langsam", jetzt=lambda: uhr["t"])
        elif stoerung == "befehl":
            _befehl(tmp_path, 2, "stopp", uhr=uhr)
        elif stoerung == "still":
            uhr["t"] = T0 + agentdatei.AGENT_TOTMANN_S + 0.1
        elif stoerung == "freigabe":
            _freigabe(tmp_path, an=False, nummer=2)
        else:
            karten.zustand = "verloren"

    spot = _NaviSpot(folge=_unterwegs(), je_status=je_status)
    z = _zentrale(spot, tmp_path, kartenarbeit=karten, jetzt=lambda: uhr["t"],
                  braucht_freigabe=stoerung == "freigabe")
    z.wahrnehmen()
    if stoerung == "freigabe":
        _freigabe(tmp_path)
    _befehl(tmp_path, 1, "zum_wegpunkt", {"name": "kueche"}, uhr=uhr)
    z.takt()
    assert z._agent["zustand"] == "abgebrochen" and erwartet in z._agent["grund"], z._agent
    assert _stopp_gesendet(spot.backend), "Spot hält an"


@pytest.mark.parametrize("fehler, name, erwartet", [
    ("Keine Karte geladen — erst `karte_laden`", "kueche", "karte_laden"),
    (None, "garage", "Vorhanden")])
def test_ohne_karte_oder_mit_unbekanntem_wegpunkt_wird_abgelehnt(tmp_path, fehler, name, erwartet):
    spot = _NaviSpot()
    z, _ = _mit_uhr(spot, tmp_path, kartenarbeit=_NaviKarten(fehler))
    _befehl(tmp_path, 1, "zum_wegpunkt", {"name": name})
    z.takt()
    assert z._agent["zustand"] == "abgelehnt" and erwartet in z._agent["grund"]
    assert spot.backend.navi == []


def test_ein_klick_auf_einen_wegpunkt_im_tab_faehrt_hin(tmp_path):
    spot = _NaviSpot(folge=_unterwegs(1))
    z, _ = _mit_uhr(spot, tmp_path, kartenarbeit=_NaviKarten())
    protokoll.schreibe_klickziel(tmp_path, 1, (3.0, 1.0), "langsam", jetzt=lambda: T0,
                                 art="wegpunkt", name="kueche")
    z.takt()
    assert spot.backend.navi and spot.backend.navi[0] == "wp1"
    assert (z.klick.stand.zustand, z.klick.stand.quelle) == ("angekommen", "tab")
