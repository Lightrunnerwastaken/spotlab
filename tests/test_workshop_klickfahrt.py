"""Die Klickfahrt der Steuerzentrale: zu einem angeklickten Punkt gehen — rein rechnerisch."""

import math

import pytest
from test_workshop_wegsuche import _raum

from spotlab.record import fahrt
from spotlab.workshop import klickfahrt as kf


def _unterwegs(ziel=(2.0, 1.0), lage=(1.0, 1.0, 0.0), t=0.0):
    k = kf.Klickfahrt()
    s = _raum()
    k.neues_ziel(1, ziel, lage, s, t)
    return k, s


def test_ein_gutes_ziel_macht_sich_auf_den_weg():
    k, _ = _unterwegs()
    assert k.unterwegs and k.stand.zustand == "unterwegs"
    assert k.stand.weg == [(2.0, 1.0)] and k.stand.ziel == (2.0, 1.0) and k.stand.nummer == 1


def test_ein_schlechtes_ziel_wird_abgelehnt_mit_grund():
    k = kf.Klickfahrt()
    k.neues_ziel(2, (2.52, 1.0), (1.0, 1.0, 0.0), _raum(), 0.0)
    assert k.stand.zustand == "abgelehnt" and "Wand" in k.stand.grund
    assert k.schritt((1.0, 1.0, 0.0), _raum(), 0.1, 5.0) == (0.0, 0.0)


def test_eine_geschlossene_wand_heisst_kein_weg():
    k = kf.Klickfahrt()
    k.neues_ziel(3, (4.0, 1.0), (1.0, 1.0, 0.0), _raum(wand_bis_y=5.0), 0.0)
    assert k.stand.zustand == "abgelehnt" and "kein Weg" in k.stand.grund


def test_steht_das_ziel_seitlich_dreht_er_erst():
    k, s = _unterwegs(ziel=(1.0, 2.5))            # 90 Grad links
    vx, wz = k.schritt((1.0, 1.0, 0.0), s, 0.1, 5.0)
    assert vx == 0.0 and wz > 0.0
    assert wz <= fahrt.DREH_RAD_S + 1e-9


def test_geradeaus_geht_er():
    k, s = _unterwegs(ziel=(2.0, 1.0))
    vx, wz = k.schritt((1.0, 1.0, 0.0), s, 0.1, 5.0)
    assert vx == pytest.approx(fahrt.TEMPO_M_S) and wz == pytest.approx(0.0, abs=1e-9)


def test_nah_am_ziel_wird_er_langsamer():
    k, s = _unterwegs(ziel=(2.0, 1.0))
    vx, _ = k.schritt((1.8, 1.0, 0.0), s, 0.1, 5.0)
    assert vx <= 0.8 * 0.2 + 1e-9


def test_die_stufe_drosselt_das_tempo():
    k, s = _unterwegs(ziel=(2.0, 1.0))
    vx, _ = k.schritt((1.0, 1.0, 0.0), s, 0.1, 5.0, faktor=0.5)
    assert vx == pytest.approx(fahrt.TEMPO_M_S * 0.5)


def test_am_ziel_ist_er_angekommen():
    k, s = _unterwegs(ziel=(2.0, 1.0))
    assert k.schritt((1.9, 1.05, 0.0), s, 0.1, 5.0) == (0.0, 0.0)
    assert k.stand.zustand == "angekommen" and not k.unterwegs


def test_ohne_lesbares_gitter_steht_er():
    k, s = _unterwegs()
    assert k.schritt((1.0, 1.0, 0.0), s, 0.1, None) == (0.0, 0.0)
    assert k.unterwegs, "noch nicht aufgegeben"


def test_ein_ueberhang_haelt_ihn_an_und_steht_im_grund():
    k, s = _unterwegs()
    t = 0.0
    while k.unterwegs and t < 20:
        k.schritt((1.0, 1.0, 0.0), s, t, 5.0, kopf_frei=False, kopf_grund="Überhang 0.6 m voraus")
        t += 0.5
    assert k.stand.zustand == "versperrt" and "Überhang" in k.stand.grund


def test_versperrt_plant_er_neu_und_gibt_dann_auf(monkeypatch):
    k, s = _unterwegs(ziel=(2.0, 1.0))
    geplant = []
    echt = kf.wegsuche.weg

    def zaehlen(*a, **kw):
        geplant.append(a[3] if len(a) > 3 else kw)
        return echt(*a, **kw)

    monkeypatch.setattr(kf.wegsuche, "weg", zaehlen)
    t = 0.0
    while k.unterwegs and t < 30:
        assert k.schritt((1.0, 1.0, 0.0), s, t, 0.4) == (0.0, 0.0)
        t += 0.25
    assert k.stand.zustand == "versperrt" and "frei voraus" in k.stand.grund
    assert kf.VERSPERRT_NACH_S <= t <= kf.VERSPERRT_NACH_S + 0.5
    assert len(geplant) >= int(kf.VERSPERRT_NACH_S / kf.NEU_PLANEN_S) - 1, "zwischendurch neu geplant"


def test_haelt_die_schranke_dreht_er_trotzdem_zum_weg():
    """Kette im Übungsraum, 27.09.2026: Spot stand 19 Grad schräg vor einer Tür, der schräge
    Strahl lief auf die Türkante (0.48 m frei), und weil nichts ging, drehte er auch nicht --
    nach 6 s „versperrt“. Drehen auf der Stelle braucht keinen Freiraum."""
    k, s = _unterwegs(ziel=(2.0, 1.0))
    vx, wz = k.schritt((1.0, 1.0, math.radians(-20.0)), s, 0.1, 0.48)
    assert vx == 0.0 and wz > 0.0


def test_nah_am_ziel_reicht_weniger_freiraum():
    """Das Ziel liegt 0.3 m vor einer Wand: auf den letzten Zentimetern ist voraus nie 0.8 m frei."""
    k, s = _unterwegs(ziel=(2.0, 1.0))
    vx, _ = k.schritt((1.7, 1.0, 0.0), s, 0.1, 0.5)
    assert vx > 0.0


def test_abbrechen_nur_unterwegs():
    k, _ = _unterwegs()
    k.abbrechen("eine Taste hat übernommen")
    assert k.stand.zustand == "abgebrochen" and "Taste" in k.stand.grund
    k.abbrechen("nochmal")
    assert "Taste" in k.stand.grund, "ein zweites Abbrechen ändert nichts"


def test_der_stand_als_daten():
    k, _ = _unterwegs()
    daten = k.stand.als_daten()
    assert daten == {"nummer": 1, "zustand": "unterwegs", "grund": "",
                     "ziel": [2.0, 1.0], "weg": [[2.0, 1.0]], "quelle": "tab"}
    assert kf.Stand().als_daten()["ziel"] is None


def test_das_ziel_merkt_sich_wer_es_gesetzt_hat():
    k = kf.Klickfahrt()
    k.neues_ziel(3, (2.0, 1.0), (1.0, 1.0, 0.0), _raum(), 0.0, quelle="agent")
    assert k.stand.quelle == "agent" and k.stand.als_daten()["quelle"] == "agent"
    k.neues_ziel(4, (2.52, 1.0), (1.0, 1.0, 0.0), _raum(), 0.0, quelle="agent")
    assert k.stand.zustand == "abgelehnt" and k.stand.quelle == "agent"


def test_die_abweichung_rechnet_um_die_180_grad():
    k, s = _unterwegs(ziel=(0.2, 1.0), lage=(1.0, 1.0, math.radians(170.0)))
    vx, wz = k.schritt((1.0, 1.0, math.radians(170.0)), s, 0.1, 5.0)
    assert vx > 0.0 and wz > 0.0, "10 Grad links liegt das Ziel, nicht 350 Grad rechts"
