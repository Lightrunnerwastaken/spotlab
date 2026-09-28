"""Die Aufstehbahn aus echten Läufen (Physik Stufe B, 28.09.2026)."""
import json

import pytest

from spotlab.kalibrierung import haltung

SITZ = [0.52, 1.40, -2.79, -0.52, 1.40, -2.79, 0.57, 1.40, -2.79, -0.57, 1.40, -2.79]
STAND = [0.02, 0.85, -1.50, -0.02, 0.85, -1.50, 0.02, 0.87, -1.61, -0.02, 0.87, -1.61]


def _lauf(ordner, name="20260101T000000Z_x", backend="real", hub=0.41, z_start=0.10):
    """Ein Lauf mit einem stand() bei t=10: ab t=10.2 linear in 1 s vom Sitz in den Stand."""
    d = ordner / name
    d.mkdir()
    (d / "lauf.json").write_text(json.dumps({"backend": backend}), encoding="utf-8")
    (d / "ereignisse.jsonl").write_text(json.dumps(
        {"t": 10.0, "art": "kommando", "daten": {"name": "stand"}}) + "\n", encoding="utf-8")
    zeilen = []
    for i in range(160):
        t = 9.0 + i * 0.1
        u = min(1.0, max(0.0, (t - 10.2) / 1.0))
        gelenke = {n: {"position": SITZ[k] + u * (STAND[k] - SITZ[k])}
                   for k, n in enumerate(haltung.GELENKE)}
        zeilen.append(json.dumps({"t": t, "daten": {"z": z_start + u * hub, "joints": gelenke}}))
    (d / "zustand.jsonl").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return d


def test_ein_aufstehen_aus_dem_sitzen_wird_vermessen(tmp_path):
    vorgaenge = haltung.aufstehvorgaenge(_lauf(tmp_path))
    assert len(vorgaenge) == 1
    v = vorgaenge[0]
    assert v["verzug_s"] == pytest.approx(0.2, abs=0.1)
    assert v["dauer_s"] == pytest.approx(1.0, abs=0.15)
    assert v["hub_m"] == pytest.approx(0.41, abs=0.01)
    assert len(v["bahn"]) == haltung.PUNKTE
    assert v["bahn"][0] == pytest.approx(SITZ, abs=0.02)
    assert v["bahn"][-1] == pytest.approx(STAND, abs=0.02)


def test_nur_echte_laeufe_und_nur_aus_dem_sitzen(tmp_path):
    assert haltung.aufstehvorgaenge(_lauf(tmp_path, "a", backend="mujoco")) == []
    assert haltung.aufstehvorgaenge(_lauf(tmp_path, "b", hub=0.05)) == [], "stand() aus dem Stehen"
    kaputt = tmp_path / "c"
    kaputt.mkdir()
    (kaputt / "lauf.json").write_text("{", encoding="utf-8")
    assert haltung.aufstehvorgaenge(kaputt) == []


def test_der_median_ueber_mehrere_laeufe(tmp_path):
    ordner = [_lauf(tmp_path, "a", hub=0.40), _lauf(tmp_path, "b", hub=0.41),
              _lauf(tmp_path, "c", hub=0.45)]
    daten = haltung.haltung(ordner)
    assert daten["anzahl"] == 3
    assert daten["hub_m"] == pytest.approx(0.41, abs=0.005)
    assert daten["gelenke"] == list(haltung.GELENKE)
    assert len(daten["bahn"]) == haltung.PUNKTE and len(daten["bahn"][0]) == 12


def test_die_mitgelieferte_datei_ist_gemessen():
    daten = json.loads(haltung.DATEI.read_text(encoding="utf-8"))
    assert daten["anzahl"] >= 100, "aus den echten Läufen, nicht aus einer Attrappe"
    assert 0.34 < daten["hub_m"] < 0.46
    assert 0.6 < daten["dauer_s"] < 1.3
