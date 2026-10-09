"""Lage und Skizze für den Agenten — aus einem fest gebauten Lagebild, ohne Zentrale."""

import io
import json
import math

import numpy as np
import pytest

from spotlab.backends.base import ObstacleGrid
from spotlab.mcp import agentlage
from spotlab.record import zentrale as protokoll
from spotlab.workshop import skizze as skizzenmodul

T = 5000.0


def _gitter():
    """4 × 4 m um (0, 0): eine Wand ab x = 1.5, oberhalb y = 1.0 ungesehen."""
    zelle, n = 0.03, 134
    xs = -2.0 + np.arange(n) * zelle
    ys = -2.0 + np.arange(n) * zelle
    zellen = np.where(xs[None, :] >= 1.5, 0.0, 1.0) * np.ones((n, 1))
    bekannt = (ys[:, None] <= 1.0) & np.ones((1, n), bool)
    return ObstacleGrid(cells=zellen, cell_size=zelle, origin=(-2.0, -2.0), time=0.0,
                        known=bekannt)


def _lagebild(lauf, t=T, gier_grad=0.0, **mehr):
    s = skizzenmodul.Skizze()
    s.aufnehmen(_gitter(), t)
    daten = {"t": t, "rahmen": "vision", "zelle_m": s.zelle_m, "ursprung": list(s.ursprung),
             "breite": s.zustand.shape[1], "hoehe": s.zustand.shape[0],
             "spot": {"x": 0.0, "y": 0.0, "gier_grad": gier_grad},
             "tags": [{"id": 7, "x": 0.0, "y": 1.0}],
             "vision_von_odom": None,
             "klickfahrt": {"nummer": 0, "zustand": "keine", "grund": "", "ziel": None, "weg": [],
                            "quelle": "tab"},
             "faehigkeiten": {"licht": False, "ton": False, "kamera": False},
             "menschen": [{"x": 2.0, "y": -2.0, "alter_s": 0.5, "quelle": "vorne",
                           "gefolgt": False}],
             "suche": {"stufe": "aus"}, "karte": None,
             "agent": {"nummer": 2, "art": "ziel", "zustand": "unterwegs", "grund": "",
                       "warum": "zur Tür", "agent": "claude", "seit": t, "tiefe": None,
                       "freigabe": False, "braucht_freigabe": False},
             "motoren": None,
             "kopfraum": {"frei": True, "grund": ""}}
    daten.update(mehr)
    protokoll.schreibe_lagebild(lauf, daten, s.png(t))


def _zustand(lauf, **daten):
    zeile = {"t": T, "daten": {"pose": [0.0, 0.0, 0.0], "velocity": [0.3, 0.4, 0.0],
                               "battery": 81.0, "powered": True, **daten}}
    with (lauf / "zustand.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(zeile) + "\n")


def _richtung(lage, grad):
    return next(r for r in lage["richtungen"] if r["richtung_grad"] == grad)


def test_die_richtungen_sagen_frei_wand_und_unbekannt(tmp_path):
    _lagebild(tmp_path)
    lage = agentlage.lage_aus(tmp_path, jetzt=lambda: T + 0.5)
    vorne = _richtung(lage, 0)
    assert vorne["ende"] == "wand" and vorne["bei_m"] == pytest.approx(1.5, abs=0.1)
    links = _richtung(lage, 90)
    assert links["ende"] == "unbekannt" and links["bei_m"] == pytest.approx(1.0, abs=0.1)
    assert "Wand" in vorne["text"] and "unbekannt" in links["text"]
    assert sorted(r["richtung_grad"] for r in lage["richtungen"]) == [
        -135, -90, -45, 0, 45, 90, 135, 180]


def test_die_richtungen_drehen_mit_dem_blick(tmp_path):
    _lagebild(tmp_path, gier_grad=90.0)                 # Spot schaut nach +y
    lage = agentlage.lage_aus(tmp_path, jetzt=lambda: T)
    assert _richtung(lage, 0)["ende"] == "unbekannt"     # vorne ist jetzt +y
    assert _richtung(lage, -90)["ende"] == "wand"        # rechts ist +x


def test_menschen_und_tags_mit_peilung_und_abstand_zu_spot(tmp_path):
    _lagebild(tmp_path, gier_grad=0.0)
    lage = agentlage.lage_aus(tmp_path, jetzt=lambda: T)
    [tag] = lage["tags"]
    assert tag["peilung_grad"] == pytest.approx(90.0) and tag["abstand_m"] == pytest.approx(1.0)
    [mensch] = lage["menschen"]
    assert mensch["peilung_grad"] == pytest.approx(-45.0)
    assert mensch["abstand_m"] == pytest.approx(math.hypot(2.0, 2.0), abs=0.01)
    assert (mensch["x"], mensch["y"]) == (2.0, -2.0)


def test_pose_tempo_akku_motoren_und_agent(tmp_path):
    _lagebild(tmp_path)
    _zustand(tmp_path)
    lage = agentlage.lage_aus(tmp_path, jetzt=lambda: T)
    assert lage["spot"] == {"x": 0.0, "y": 0.0, "blick_grad": 0.0}
    assert lage["tempo_m_s"] == pytest.approx(0.5)
    assert lage["akku_prozent"] == pytest.approx(81.0) and lage["motoren"] == "an"
    assert lage["agent"]["warum"] == "zur Tür" and lage["kopfraum"]["frei"] is True
    assert "vision" in lage["rahmen"]


def test_wartet_die_zentrale_steht_das_bei_den_motoren(tmp_path):
    _lagebild(tmp_path, motoren="aus — wartet auf Freigabe")
    _zustand(tmp_path, powered=False)
    assert "wartet auf Freigabe" in agentlage.lage_aus(tmp_path, jetzt=lambda: T)["motoren"]


def test_ein_altes_lagebild_heisst_die_zentrale_antwortet_nicht(tmp_path):
    _lagebild(tmp_path)
    lage = agentlage.lage_aus(tmp_path, jetzt=lambda: T + agentlage.LAGEBILD_ALT_S + 0.1)
    assert "antwortet nicht" in lage["fehler"]
    assert "antwortet nicht" in agentlage.lage_aus(tmp_path / "leer", jetzt=lambda: T)["fehler"]


def test_die_skizze_ist_ein_ausschnitt_mit_plus_y_oben(tmp_path):
    from PIL import Image

    _lagebild(tmp_path)
    png, legende = agentlage.skizze_bild(tmp_path, radius_m=2.0)
    bild = Image.open(io.BytesIO(png)).convert("RGB")
    seite = int(round(2 * 2.0 * agentlage.PIXEL_JE_M))
    assert bild.size == (seite, seite)
    mitte = seite // 2
    oben = bild.getpixel((mitte - 30, mitte - int(1.5 * agentlage.PIXEL_JE_M)))   # y = +1.5
    unten = bild.getpixel((mitte - 30, mitte + int(1.5 * agentlage.PIXEL_JE_M)))  # y = -1.5
    assert oben == agentlage.UNBEKANNT_FARBE, "oberhalb y = 1 hat Spot nichts gesehen"
    assert unten == agentlage.FREI_FARBEN[0]
    rechts = bild.getpixel((mitte + int(1.75 * agentlage.PIXEL_JE_M), mitte + 30))  # x = +1.75
    assert rechts == agentlage.WAND_FARBEN[0]
    assert "+y" in legende and "1 m" in legende
