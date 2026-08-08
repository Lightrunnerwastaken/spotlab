# spotlab Kalibrier-Infrastruktur Implementierungsplan — Teil 2 (Aufgaben 5–9)

> **Für agentische Arbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development`
> (empfohlen) oder `superpowers:executing-plans`. Schritte sind Checkboxen (`- [ ]`).

**Fortsetzung von** `docs/superpowers/plans/2026-08-08-spotlab-kalibrierung.md`.
**Die „Globalen Vorgaben" aus Teil 1 gelten unverändert.**

**Voraussetzungen aus Teil 1** (Aufgaben 1–4 abgeschlossen):

| Baustein | Was daraus benutzt wird |
|---|---|
| `api/state.py` | `as_sample(zustand, reich)`; Schlüssel `t_robot`, `z`, `roll`, `pitch` immer, `feet_detail`, `joint_acc`, `velocity_vision`, `behavior`, `battery_detail`, `motor_temps` nur reich |
| `record/sampler.py` | `setze_takt(hz, reich)`, `takt()` |
| `record/events.py` | Ereignisart `"messfenster"` |
| `api/spot.py` | `messfenster(name, hz=50.0, **felder)`; Ereignisse mit `phase`, `name`, `hz_soll` |
| `record/read.py` | `read_jsonl(pfad)` — SDK-frei, in `messung/` erlaubt |

---

## Aufgabe 5: `messung/fenster.py` — Fenster erkennen

**Dateien:**
- Anlegen: `src/spotlab/messung/__init__.py`
- Anlegen: `src/spotlab/messung/fenster.py`
- Test: `tests/test_messung_fenster.py`

**Schnittstellen:**
- Verbraucht: `read_jsonl` aus `spotlab.record.read`; `SpotlabError`.
- Liefert: `Fenster(name, felder, von_s, bis_s, hz_soll, hz_ist, abtastungen, reich,
  unvollstaendig, zeitquelle, kommandos, messwerte)`, `fenster(lauf_dir) -> list[Fenster]`,
  `als_json(liste) -> dict`, `schreibe(lauf_dir) -> Path`.
  Aufgabe 6 füllt `messwerte`, Aufgabe 7 benutzt dieselbe Abschnittsbildung.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_messung_fenster.py`:

```python
import json
from pathlib import Path

import pytest

from spotlab.messung.fenster import als_json, fenster, schreibe


def _lauf(tmp_path, ereignisse, saetze):
    ordner = tmp_path / "20260808T120000Z"
    ordner.mkdir(parents=True)
    (ordner / "ereignisse.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ereignisse),
        encoding="utf-8",
    )
    (ordner / "zustand.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in saetze),
        encoding="utf-8",
    )
    return ordner


def _start(t, name, hz=50, **felder):
    return {"t": t, "art": "messfenster",
            "daten": {"phase": "start", "name": name, "hz_soll": hz, **felder}}


def _ende(t, name, **felder):
    return {"t": t, "art": "messfenster", "daten": {"phase": "ende", "name": name, **felder}}


def _satz(t, t_robot=None, **daten):
    voll = {"pose": [0.0, 0.0, 0.0], "velocity": [0.0, 0.0, 0.0],
            "z": 0.42, "roll": 0.0, "pitch": 0.0, "feet": [True] * 4,
            "joints": {}, "battery": 87.0, "powered": True,
            "t_robot": t if t_robot is None else t_robot}
    voll.update(daten)
    return {"t": t, "daten": voll}


def test_ein_fenster_wird_erkannt(tmp_path):
    ordner = _lauf(
        tmp_path,
        [_start(1.0, "G3", stuetzstelle="0.30"), _ende(3.0, "G3")],
        [_satz(t / 10) for t in range(0, 50)],
    )
    liste = fenster(ordner)
    assert len(liste) == 1
    f = liste[0]
    assert f.name == "G3"
    assert f.felder == {"stuetzstelle": "0.30"}
    assert f.hz_soll == 50
    assert f.von_s == 1.0 and f.bis_s == 3.0
    assert f.unvollstaendig is False


def test_nur_abtastungen_im_fenster_zaehlen(tmp_path):
    ordner = _lauf(
        tmp_path,
        [_start(1.0, "G1"), _ende(2.0, "G1")],
        [_satz(t / 10) for t in range(0, 40)],      # 0.0 bis 3.9 s
    )
    f = fenster(ordner)[0]
    assert f.abtastungen == 11                       # 1.0 … 2.0 einschliesslich


def test_hz_ist_wird_aus_den_abtastungen_gerechnet(tmp_path):
    """Nicht aus den Marken — deren Abstand zaehlt die Wartezeit auf den ersten Tick mit."""
    ordner = _lauf(
        tmp_path,
        [_start(0.9, "G1", hz=10), _ende(2.2, "G1")],
        [_satz(1.0 + i / 10) for i in range(11)],    # 1.0 … 2.0, genau 10 Hz
    )
    f = fenster(ordner)[0]
    assert f.hz_ist == pytest.approx(10.0, abs=0.01)


def test_zwei_fenster_nacheinander(tmp_path):
    ordner = _lauf(
        tmp_path,
        [_start(1.0, "G2"), _ende(2.0, "G2"), _start(3.0, "G3"), _ende(4.0, "G3")],
        [_satz(t / 10) for t in range(0, 50)],
    )
    assert [f.name for f in fenster(ordner)] == ["G2", "G3"]


def test_fenster_ohne_ende_gilt_als_unvollstaendig(tmp_path):
    """Prozess gestorben — die letzte Abtastung ist das Ende, und das steht dran."""
    ordner = _lauf(tmp_path, [_start(1.0, "G6")], [_satz(t / 10) for t in range(0, 30)])
    f = fenster(ordner)[0]
    assert f.unvollstaendig is True
    assert f.bis_s == pytest.approx(2.9)


def test_zeitquelle_robot_wenn_alle_stempel_da_sind(tmp_path):
    ordner = _lauf(tmp_path, [_start(1.0, "G1"), _ende(2.0, "G1")],
                   [_satz(t / 10, t_robot=1000.0 + t / 10) for t in range(0, 30)])
    assert fenster(ordner)[0].zeitquelle == "robot"


def test_zeitquelle_empfang_wenn_ein_stempel_fehlt(tmp_path):
    saetze = [_satz(t / 10, t_robot=1000.0 + t / 10) for t in range(0, 30)]
    saetze[5]["daten"]["t_robot"] = 0.0
    ordner = _lauf(tmp_path, [_start(1.0, "G1"), _ende(2.0, "G1")], saetze)
    assert fenster(ordner)[0].zeitquelle == "empfang"


def test_reich_wird_erkannt(tmp_path):
    schlank = _lauf(tmp_path / "a", [_start(1.0, "G1"), _ende(2.0, "G1")],
                    [_satz(t / 10) for t in range(0, 30)])
    assert fenster(schlank)[0].reich is False

    reich = _lauf(tmp_path / "b", [_start(1.0, "G1"), _ende(2.0, "G1")],
                  [_satz(t / 10, feet_detail=[{"kontakt": True, "mu": 0.6}])
                   for t in range(0, 30)])
    assert fenster(reich)[0].reich is True


def test_kommandos_im_fenster_werden_mitgenommen(tmp_path):
    ordner = _lauf(
        tmp_path,
        [
            {"t": 0.5, "art": "kommando", "daten": {"name": "walk", "vx": 0.9}},   # davor
            _start(1.0, "G3"),
            {"t": 1.2, "art": "kommando", "daten": {"name": "walk", "vx": 0.30}},
            _ende(2.0, "G3"),
        ],
        [_satz(t / 10) for t in range(0, 30)],
    )
    kommandos = fenster(ordner)[0].kommandos
    assert [k["vx"] for k in kommandos] == [0.30]


def test_fenster_ohne_abtastungen_stuerzt_nicht(tmp_path):
    ordner = _lauf(tmp_path, [_start(9.0, "G1"), _ende(9.5, "G1")],
                   [_satz(t / 10) for t in range(0, 30)])
    f = fenster(ordner)[0]
    assert f.abtastungen == 0
    assert f.hz_ist == 0.0
    assert f.messwerte == {}


def test_lauf_ohne_fenster(tmp_path):
    assert fenster(_lauf(tmp_path, [], [_satz(0.1)])) == []


def test_schreibe_legt_messfenster_json_an(tmp_path):
    ordner = _lauf(tmp_path, [_start(1.0, "G1"), _ende(2.0, "G1")],
                   [_satz(t / 10) for t in range(0, 30)])
    pfad = schreibe(ordner)
    assert pfad.name == "messfenster.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    assert daten["lauf"] == ordner.name
    assert [f["name"] for f in daten["fenster"]] == ["G1"]
    json.dumps(als_json(fenster(ordner)))          # JSON-fähig


def test_messung_ist_frei_von_sdk_und_qt():
    import re

    import spotlab.messung as paket

    wurzel = Path(paket.__file__).parent
    muster = re.compile(
        r"^\s*(from|import)\s+"
        r"(bosdyn|PySide6|spotlab\.api|spotlab\.backends|spotlab\.gui)",
        re.M,
    )
    verstoesse = [
        str(p) for p in wurzel.rglob("*.py") if muster.search(p.read_text(encoding="utf-8"))
    ]
    assert verstoesse == []
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_messung_fenster.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.messung'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/messung/__init__.py`:

```python
"""Auswertung einer Aufzeichnung — Qt-frei, SDK-frei.

Dieses Paket liest nur Dateien von der Platte und rechnet. Es importiert nichts
aus api/, backends/ oder gui/ und kein bosdyn; spotlab.record.read ist erlaubt,
weil es selbst SDK-frei ist.

spotlab liefert Messwerte, nicht Urteile: die Kriterien der Realismus-Gates
liegen in matura-spot, und spotlab darf davon nicht abhaengen.
"""
```

`src/spotlab/messung/fenster.py` — Erkennung (die Kennzahlen kommen in Aufgabe 6):

```python
"""Messfenster aus einer Aufzeichnung herausschneiden und auswerten."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from spotlab.record.read import read_jsonl

DATEINAME = "messfenster.json"
# Schluessel, deren Vorhandensein einen reich aufgezeichneten Satz ausmacht.
REICHE_SCHLUESSEL = ("feet_detail", "joint_acc", "velocity_vision")


@dataclass(frozen=True)
class Fenster:
    name: str
    felder: dict
    von_s: float
    bis_s: float
    hz_soll: float
    hz_ist: float
    abtastungen: int
    reich: bool
    unvollstaendig: bool
    zeitquelle: str                       # "robot" oder "empfang"
    kommandos: list = field(default_factory=list)
    messwerte: dict = field(default_factory=dict)


def _zeilen(pfad):
    return [z for z in read_jsonl(pfad) if isinstance(z, dict)]


def _marken(ereignisse):
    """(start, ende|None) in Reihenfolge. Verschachtelung ist beim Schreiben verboten."""
    paare, offen = [], None
    for eintrag in ereignisse:
        if eintrag.get("art") != "messfenster":
            continue
        daten = eintrag.get("daten") or {}
        if daten.get("phase") == "start":
            if offen is not None:
                paare.append((offen, None))
            offen = eintrag
        elif daten.get("phase") == "ende" and offen is not None:
            paare.append((offen, eintrag))
            offen = None
    if offen is not None:
        paare.append((offen, None))
    return paare


def _zeit(satz, quelle):
    if quelle == "robot":
        return float((satz.get("daten") or {}).get("t_robot") or 0.0)
    return float(satz.get("t") or 0.0)


def _quelle(saetze):
    """Roboteruhr nur, wenn JEDE Abtastung im Fenster einen Stempel hat.

    Ein einziger fehlender Stempel machte die Reihe ungleichmaessig auf eine Art,
    die man in der Auswertung nicht mehr sieht.
    """
    if not saetze:
        return "empfang"
    alle = all(float((s.get("daten") or {}).get("t_robot") or 0.0) > 0 for s in saetze)
    return "robot" if alle else "empfang"


def fenster(lauf_dir):
    ordner = Path(lauf_dir)
    ereignisse = _zeilen(ordner / "ereignisse.jsonl")
    saetze = _zeilen(ordner / "zustand.jsonl")
    letzte_zeit = float(saetze[-1].get("t") or 0.0) if saetze else 0.0

    gefunden = []
    for start, ende in _marken(ereignisse):
        s_daten = start.get("daten") or {}
        von = float(start.get("t") or 0.0)
        bis = float(ende.get("t") or 0.0) if ende is not None else letzte_zeit
        # Die Zuordnung laeuft ueber die EMPFANGSZEIT: nur sie steht in den
        # Ereignissen und in den Abtastungen auf derselben Uhr.
        drin = [s for s in saetze if von <= float(s.get("t") or 0.0) <= bis]
        quelle = _quelle(drin)
        zeiten = [_zeit(s, quelle) for s in drin]
        dauer = (zeiten[-1] - zeiten[0]) if len(zeiten) > 1 else 0.0
        felder = {
            k: v for k, v in s_daten.items() if k not in ("phase", "name", "hz_soll")
        }
        gefunden.append(
            Fenster(
                name=s_daten.get("name", ""),
                felder=felder,
                von_s=von,
                bis_s=bis,
                hz_soll=float(s_daten.get("hz_soll") or 0.0),
                hz_ist=round((len(drin) - 1) / dauer, 2) if dauer > 0 else 0.0,
                abtastungen=len(drin),
                reich=bool(drin)
                and any(k in (drin[0].get("daten") or {}) for k in REICHE_SCHLUESSEL),
                unvollstaendig=ende is None,
                zeitquelle=quelle,
                kommandos=[
                    dict(e.get("daten") or {})
                    for e in ereignisse
                    if e.get("art") == "kommando" and von <= float(e.get("t") or 0.0) <= bis
                ],
                messwerte={},          # Aufgabe 6
            )
        )
    return gefunden


def als_json(liste):
    return {
        "fenster": [
            {
                "name": f.name,
                "felder": f.felder,
                "von_s": f.von_s,
                "bis_s": f.bis_s,
                "hz_soll": f.hz_soll,
                "hz_ist": f.hz_ist,
                "abtastungen": f.abtastungen,
                "reich": f.reich,
                "unvollstaendig": f.unvollstaendig,
                "zeitquelle": f.zeitquelle,
                "kommandos": f.kommandos,
                "messwerte": f.messwerte,
            }
            for f in liste
        ]
    }


def schreibe(lauf_dir):
    ordner = Path(lauf_dir)
    daten = {"lauf": ordner.name, **als_json(fenster(ordner))}
    ziel = ordner / DATEINAME
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    return ziel
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_messung_fenster.py -q
```

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/messung/ tests/test_messung_fenster.py
git commit -m "feat(messung): Messfenster aus einer Aufzeichnung herausschneiden"
```

---

## Aufgabe 6: Die Kennzahlen je Fenster

**Dateien:**
- Ändern: `src/spotlab/messung/fenster.py`
- Test: `tests/test_messung_kennzahlen.py`

**Schnittstellen:**
- Liefert: `kennzahlen(saetze, kommandos, quelle, hz_soll) -> dict`, aufgerufen in `fenster()`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_messung_kennzahlen.py`:

```python
import math

import pytest

from spotlab.messung.fenster import kennzahlen


def _satz(t, x=0.0, y=0.0, yaw=0.0, z=0.42, roll=0.0, pitch=0.0,
          vx=0.0, vy=0.0, wz=0.0, feet=(True, True, True, True), **extra):
    daten = {
        "pose": [x, y, yaw], "velocity": [vx, vy, wz],
        "z": z, "roll": roll, "pitch": pitch, "feet": list(feet),
        "joints": {}, "t_robot": t,
    }
    daten.update(extra)
    return {"t": t, "daten": daten}


def _reihe(n, dt=0.02, **fest):
    return [_satz(i * dt, **fest) for i in range(n)]


def test_messguete_zuerst():
    k = kennzahlen(_reihe(51), [], "robot", 50.0)
    assert k["abtastungen"] == 51
    assert k["dauer_s"] == pytest.approx(1.0)
    assert k["hz_ist"] == pytest.approx(50.0, abs=0.1)
    assert k["zeitquelle"] == "robot"
    assert k["luecken"] == []


def test_luecke_wird_gegen_hz_soll_gemessen():
    saetze = _reihe(10)
    saetze += [_satz(1.0 + i * 0.02) for i in range(10)]     # Sprung von 0.18 auf 1.0
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert len(k["luecken"]) == 1
    assert k["luecken"][0]["laenge_s"] == pytest.approx(0.82, abs=0.01)


def test_hoehe_drift_und_absacken():
    saetze = [_satz(i * 0.02, z=0.42 - i * 0.0001) for i in range(51)]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["hoehe_mittel"] == pytest.approx(0.4175, abs=1e-3)
    assert k["hoehe_max"] == pytest.approx(0.42)
    assert k["hoehe_min"] == pytest.approx(0.415)
    assert k["hoehe_drift"] == pytest.approx(-0.005, abs=1e-4)


def test_neigung_in_grad():
    saetze = [_satz(i * 0.02, roll=math.radians(3), pitch=math.radians(-5))
              for i in range(10)]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["roll_max_grad"] == pytest.approx(3.0, abs=1e-6)
    assert k["pitch_max_grad"] == pytest.approx(5.0, abs=1e-6)


def test_strecke_und_netto_versatz():
    """Hin und zurueck: Strecke 2 m, Netto 0."""
    hin = [_satz(i * 0.1, x=i * 0.1) for i in range(11)]        # 0 -> 1.0
    zurueck = [_satz(1.1 + i * 0.1, x=1.0 - i * 0.1) for i in range(11)]
    k = kennzahlen(hin + zurueck, [], "robot", 10.0)
    assert k["strecke_m"] == pytest.approx(2.0, abs=1e-6)
    assert k["netto_versatz_m"] == pytest.approx(0.0, abs=1e-6)


def test_gierwinkel_wird_fortlaufend_aufsummiert():
    """G4 verlangt das ausdruecklich: eine Drehung ueber 180 Grad wechselt sonst das Zeichen."""
    winkel = [math.radians(g) for g in range(0, 300, 10)]
    winkel = [(w + math.pi) % (2 * math.pi) - math.pi for w in winkel]   # auf +-180 gefaltet
    saetze = [_satz(i * 0.1, yaw=w) for i, w in enumerate(winkel)]
    k = kennzahlen(saetze, [], "robot", 10.0)
    assert k["gierwinkel_grad"] == pytest.approx(290.0, abs=0.5)


def test_tempo_kennzahlen():
    saetze = [_satz(i * 0.02, vx=0.30, wz=0.05) for i in range(51)]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["tempo_x_mittel"] == pytest.approx(0.30)
    assert k["drehrate_mittel"] == pytest.approx(0.05)
    assert k["tempo_max"] == pytest.approx(0.30)


def test_tracking_aus_kommando_und_messung():
    saetze = [_satz(i * 0.02, vx=0.24) for i in range(51)]
    k = kennzahlen(saetze, [{"name": "walk", "vx": 0.30, "vy": 0.0, "wz": 0.0}],
                   "robot", 50.0)
    assert k["kommandiert"] == {"vx": 0.30, "vy": 0.0, "wz": 0.0}
    assert k["tracking_prozent"] == pytest.approx(80.0, abs=0.1)


def test_widerspruechliche_kommandos_ergeben_keine_zahl():
    """Lieber keine Zahl als eine ueber zwei Bedingungen gemittelte."""
    saetze = [_satz(i * 0.02, vx=0.24) for i in range(51)]
    k = kennzahlen(
        saetze,
        [{"name": "walk", "vx": 0.30}, {"name": "walk", "vx": 0.50}],
        "robot", 50.0,
    )
    assert k["kommandiert"] == {}
    assert k["tracking_prozent"] is None


def test_gleiches_kommando_zweimal_ist_kein_widerspruch():
    saetze = [_satz(i * 0.02, vx=0.24) for i in range(51)]
    k = kennzahlen(saetze, [{"name": "walk", "vx": 0.30}, {"name": "walk", "vx": 0.30}],
                   "robot", 50.0)
    assert k["tracking_prozent"] == pytest.approx(80.0, abs=0.1)


def test_kein_kommando_kein_tracking():
    assert kennzahlen(_reihe(10), [], "robot", 50.0)["tracking_prozent"] is None


def test_gelenkkennzahlen():
    saetze = [
        _satz(i * 0.02, joints={"fl.hx": {"position": 0.1, "velocity": 0.4, "load": 20.0},
                                "fl.hy": {"position": 0.2, "velocity": -0.9, "load": -5.0}})
        for i in range(10)
    ]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["gelenk_rate_max"] == pytest.approx(0.9)
    assert k["gelenk_last_max"] == pytest.approx(20.0)
    assert k["gelenke"]["fl.hy"]["rate_max"] == pytest.approx(0.9)
    assert k["gelenke"]["fl.hx"]["last_max"] == pytest.approx(20.0)


def test_fuss_duty_und_schrittfrequenz_aus_schlanken_daten():
    """Kontakte stehen schon in `feet` — dafuer braucht es kein reiches Fenster."""
    muster = [(True, True, True, True), (False, True, True, True)]
    saetze = [_satz(i * 0.05, feet=muster[i % 2]) for i in range(41)]     # 2 s, 10 Wechsel
    k = kennzahlen(saetze, [], "robot", 20.0)
    assert k["fuss_duty"][1] == pytest.approx(1.0)
    assert k["fuss_duty"][0] == pytest.approx(0.51, abs=0.02)
    assert k["schrittfrequenz_hz"] > 0


def test_reibwert_und_schlupf_nur_aus_reichen_daten():
    saetze = [
        _satz(i * 0.02, feet_detail=[
            {"kontakt": True, "mu": 0.60, "slip_weg": [0.002, 0.0, 0.0],
             "slip_tempo": [0.03, 0.0, 0.0]},
            {"kontakt": True, "mu": 0.64, "slip_weg": [0.001, 0.0, 0.0],
             "slip_tempo": [0.01, 0.0, 0.0]},
        ])
        for i in range(10)
    ]
    k = kennzahlen(saetze, [], "robot", 50.0)
    assert k["mu_mittel"] == pytest.approx(0.62)
    assert k["schlupf_weg_max_m"] == pytest.approx(0.002)
    assert k["schlupf_tempo_max"] == pytest.approx(0.03)


def test_schlanke_daten_ergeben_none_statt_null():
    """Der Unterschied zwischen 'gemessen und null' und 'nicht gemessen' entscheidet,
    ob eine Kalibrierung gueltig ist."""
    k = kennzahlen(_reihe(10), [], "robot", 50.0)
    assert k["mu_mittel"] is None
    assert k["schlupf_weg_max_m"] is None
    assert k["schlupf_tempo_max"] is None


def test_leere_reihe_ergibt_leere_kennzahlen():
    assert kennzahlen([], [], "empfang", 50.0) == {}
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Erwartet: `ImportError: cannot import name 'kennzahlen'`.

- [ ] **Schritt 3: Umsetzen**

An `src/spotlab/messung/fenster.py` anhängen (und in `fenster()` statt `messwerte={}`
einsetzen: `messwerte=kennzahlen(drin, kommandos, quelle, hz_soll)`):

```python
import math

FAHRKOMMANDOS = ("walk", "move")


def _mittel(werte):
    return sum(werte) / len(werte) if werte else 0.0


def _gier_aufsummiert(winkel):
    """Fortlaufend, nicht Endwert minus Anfangswert.

    G4 verlangt das ausdruecklich: eine Drehung ueber 180 Grad wechselt in der
    Differenz das Vorzeichen und ergaebe eine kleinere Zahl als die Wahrheit.
    """
    gesamt = 0.0
    for vorher, jetzt in zip(winkel, winkel[1:]):
        schritt = jetzt - vorher
        while schritt > math.pi:
            schritt -= 2 * math.pi
        while schritt < -math.pi:
            schritt += 2 * math.pi
        gesamt += schritt
    return gesamt


def _kommandiert(kommandos):
    """Das eine Fahrkommando im Fenster — oder {} bei Widerspruch.

    Lieber keine Zahl als eine ueber zwei Bedingungen gemittelte.
    """
    fahrten = [k for k in kommandos if k.get("name") in FAHRKOMMANDOS]
    if not fahrten:
        return {}
    eindeutig = {
        (round(float(k.get("vx") or 0.0), 6),
         round(float(k.get("vy") or 0.0), 6),
         round(float(k.get("wz") or 0.0), 6))
        for k in fahrten
    }
    if len(eindeutig) != 1:
        return {}
    vx, vy, wz = next(iter(eindeutig))
    return {"vx": vx, "vy": vy, "wz": wz}


def _tracking(kommandiert, tempo_x, tempo_y, drehrate):
    """Prozent erreicht gegen kommandiert — auf der Achse, die kommandiert wurde."""
    for schluessel, erreicht in (("vx", tempo_x), ("vy", tempo_y), ("wz", drehrate)):
        soll = kommandiert.get(schluessel) or 0.0
        if abs(soll) > 1e-9:
            return round(100.0 * erreicht / soll, 2)
    return None


def _gelenke(saetze):
    je_gelenk = {}
    for satz in saetze:
        for name, g in (satz.get("daten") or {}).get("joints", {}).items():
            eintrag = je_gelenk.setdefault(name, {"rate_max": 0.0, "last_max": 0.0})
            eintrag["rate_max"] = max(eintrag["rate_max"], abs(float(g.get("velocity") or 0.0)))
            eintrag["last_max"] = max(eintrag["last_max"], abs(float(g.get("load") or 0.0)))
    return je_gelenk


def _fuesse(saetze, dauer):
    reihen = [list((s.get("daten") or {}).get("feet") or ()) for s in saetze]
    breite = max((len(r) for r in reihen), default=0)
    if not breite:
        return [], None
    duty, flanken = [], 0
    for i in range(breite):
        spalte = [bool(r[i]) if i < len(r) else False for r in reihen]
        duty.append(round(sum(spalte) / len(spalte), 3))
        flanken += sum(1 for a, b in zip(spalte, spalte[1:]) if not a and b)
    frequenz = round(flanken / breite / dauer, 3) if dauer > 0 else None
    return duty, frequenz


def _terrain(saetze):
    """Reibwerte und Schlupf — nur aus reich aufgezeichneten Fenstern.

    schlupf_weg wird als GROESSTER beobachteter Betrag gemeldet, nicht aufsummiert:
    ob das SDK-Feld kumulativ oder momentan ist, ist nicht belegt, und eine Summe
    ueber eine kumulative Groesse waere schlicht falsch.
    """
    mu, weg, tempo = [], 0.0, 0.0
    gesehen = False
    for satz in saetze:
        for fuss in (satz.get("daten") or {}).get("feet_detail") or ():
            gesehen = True
            if fuss.get("kontakt") and "mu" in fuss:
                mu.append(float(fuss["mu"]))
            if "slip_weg" in fuss:
                weg = max(weg, math.dist((0.0, 0.0, 0.0), fuss["slip_weg"]))
            if "slip_tempo" in fuss:
                tempo = max(tempo, math.dist((0.0, 0.0, 0.0), fuss["slip_tempo"]))
    if not gesehen:
        return None, None, None
    return (round(_mittel(mu), 4) if mu else None, round(weg, 5), round(tempo, 5))


def kennzahlen(saetze, kommandos, quelle, hz_soll):
    """Die Gate-Messgroessen aus den Abtastungen eines Fensters."""
    if not saetze:
        return {}

    zeiten = [_zeit(s, quelle) for s in saetze]
    daten = [s.get("daten") or {} for s in saetze]
    dauer = zeiten[-1] - zeiten[0]
    grenze = 2.0 / hz_soll if hz_soll > 0 else 0.2
    luecken = [
        {"von_s": round(zeiten[i - 1], 3), "laenge_s": round(zeiten[i] - zeiten[i - 1], 3)}
        for i in range(1, len(zeiten))
        if zeiten[i] - zeiten[i - 1] > grenze
    ]

    hoehen = [float(d.get("z") or 0.0) for d in daten]
    posen = [d.get("pose") or [0.0, 0.0, 0.0] for d in daten]
    tempi = [d.get("velocity") or [0.0, 0.0, 0.0] for d in daten]

    strecke = sum(
        math.dist(a[:2], b[:2]) for a, b in zip(posen, posen[1:])
    )
    tempo_x = _mittel([t[0] for t in tempi])
    tempo_y = _mittel([t[1] for t in tempi])
    drehrate = _mittel([t[2] for t in tempi])
    kommandiert = _kommandiert(kommandos)
    duty, frequenz = _fuesse(saetze, dauer)
    mu_mittel, schlupf_weg, schlupf_tempo = _terrain(saetze)
    je_gelenk = _gelenke(saetze)

    return {
        "abtastungen": len(saetze),
        "dauer_s": round(dauer, 3),
        "hz_ist": round((len(saetze) - 1) / dauer, 2) if dauer > 0 else 0.0,
        "zeitquelle": quelle,
        "luecken": luecken,
        "hoehe_mittel": round(_mittel(hoehen), 4),
        "hoehe_min": round(min(hoehen), 4),
        "hoehe_max": round(max(hoehen), 4),
        "hoehe_drift": round(hoehen[-1] - hoehen[0], 4),
        "roll_max_grad": round(max(abs(math.degrees(d.get("roll") or 0.0)) for d in daten), 3),
        "pitch_max_grad": round(max(abs(math.degrees(d.get("pitch") or 0.0)) for d in daten), 3),
        "tempo_x_mittel": round(tempo_x, 4),
        "tempo_y_mittel": round(tempo_y, 4),
        "drehrate_mittel": round(drehrate, 4),
        "tempo_max": round(max(math.dist((0.0, 0.0), t[:2]) for t in tempi), 4),
        "strecke_m": round(strecke, 4),
        "netto_versatz_m": round(math.dist(posen[0][:2], posen[-1][:2]), 4),
        "gierwinkel_grad": round(
            math.degrees(_gier_aufsummiert([p[2] for p in posen])), 2
        ),
        "kommandiert": kommandiert,
        "tracking_prozent": _tracking(kommandiert, tempo_x, tempo_y, drehrate),
        "gelenk_rate_max": round(max((g["rate_max"] for g in je_gelenk.values()), default=0.0), 4),
        "gelenk_last_max": round(max((g["last_max"] for g in je_gelenk.values()), default=0.0), 4),
        "gelenke": je_gelenk,
        "fuss_duty": duty,
        "schrittfrequenz_hz": frequenz,
        "mu_mittel": mu_mittel,
        "schlupf_weg_max_m": schlupf_weg,
        "schlupf_tempo_max": schlupf_tempo,
    }
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_messung_kennzahlen.py tests/test_messung_fenster.py -q
```

**Erwarteter Stolperstein:** `test_fenster_ohne_abtastungen_stuerzt_nicht` aus Aufgabe 5
prüft `messwerte == {}`. Das bleibt richtig, weil `kennzahlen([])` `{}` liefert.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/messung/fenster.py tests/test_messung_kennzahlen.py
git commit -m "feat(messung): Gate-Messgroessen je Fenster, fehlende Werte als None"
```

---

## Aufgabe 7: Der Lückenmelder wird abschnittsweise

**Dateien:**
- Ändern: `src/spotlab/mcp/werkzeuge.py`
- Test: `tests/test_mcp_lesen.py` (ergänzen)

**Schnittstellen:**
- Verbraucht: `_marken` aus `spotlab.messung.fenster` — als öffentliche Funktion
  `abschnitte(lauf_dir, standard_hz=10.0) -> list[dict]` bereitstellen.
- Liefert: `zustand_zusammenfassen` mit Feld `abschnitte`, Lücken je Abschnitt gemessen.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `tests/test_mcp_lesen.py` anhängen:

```python
def _ereignisse(recorder, eintraege):
    text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eintraege)
    (recorder.dir / "ereignisse.jsonl").write_text(text, encoding="utf-8")


def test_ratenwechsel_ist_keine_luecke(welt):
    """Ein Alarm, der bei jeder Messfahrt kommt, wird ignoriert."""
    recorder = _lauf(welt)
    saetze = [_satz(i * 0.1) for i in range(11)]                  # 0.0-1.0 bei 10 Hz
    saetze += [_satz(1.0 + i * 0.02) for i in range(1, 51)]       # 1.0-2.0 bei 50 Hz
    saetze += [_satz(2.0 + i * 0.1) for i in range(1, 11)]        # 2.0-3.0 bei 10 Hz
    _schreibe_zustand(recorder, saetze)
    _ereignisse(recorder, [
        {"t": 1.0, "art": "messfenster",
         "daten": {"phase": "start", "name": "G3", "hz_soll": 50}},
        {"t": 2.0, "art": "messfenster", "daten": {"phase": "ende", "name": "G3"}},
    ])
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert antwort["luecken"] == []
    assert [a["hz_soll"] for a in antwort["abschnitte"]] == [10.0, 50.0, 10.0]


def test_echte_luecke_im_fenster_wird_gefunden(welt):
    recorder = _lauf(welt)
    saetze = [_satz(1.0 + i * 0.02) for i in range(11)]           # bis 1.2
    saetze += [_satz(1.5 + i * 0.02) for i in range(11)]          # Sprung 0.3 s
    _schreibe_zustand(recorder, saetze)
    _ereignisse(recorder, [
        {"t": 1.0, "art": "messfenster",
         "daten": {"phase": "start", "name": "G3", "hz_soll": 50}},
        {"t": 2.0, "art": "messfenster", "daten": {"phase": "ende", "name": "G3"}},
    ])
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert len(antwort["luecken"]) == 1
    assert antwort["luecken"][0]["laenge_s"] == pytest.approx(0.3, abs=0.01)


def test_ohne_fenster_bleibt_es_bei_zehn_hertz(welt):
    recorder = _lauf(welt)
    _schreibe_zustand(recorder, [_satz(0.0), _satz(0.1), _satz(1.4), _satz(1.5)])
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert len(antwort["luecken"]) == 1
    assert [a["hz_soll"] for a in antwort["abschnitte"]] == [10.0]
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Erwartet: `KeyError: 'abschnitte'`, und `test_ratenwechsel_ist_keine_luecke` meldet Lücken.

- [ ] **Schritt 3: Umsetzen**

In `src/spotlab/messung/fenster.py` die Abschnittsbildung öffentlich machen:

```python
STANDARD_HZ = 10.0        # ausserhalb jedes Messfensters


def abschnitte(lauf_dir, standard_hz=STANDARD_HZ):
    """Der Lauf in Abschnitte mit ihrer erwarteten Rate — für den Lückenmelder.

    Ohne das waere jeder Ratenwechsel eine Falschmeldung, und ein Alarm, der bei
    jeder Messfahrt kommt, wird ignoriert.
    """
    ereignisse = _zeilen(Path(lauf_dir) / "ereignisse.jsonl")
    saetze = _zeilen(Path(lauf_dir) / "zustand.jsonl")
    ende = float(saetze[-1].get("t") or 0.0) if saetze else 0.0

    stuecke, zeiger = [], 0.0
    for start, schluss in _marken(ereignisse):
        von = float(start.get("t") or 0.0)
        bis = float(schluss.get("t") or 0.0) if schluss is not None else ende
        if von > zeiger:
            stuecke.append({"von_s": zeiger, "bis_s": von, "hz_soll": standard_hz})
        stuecke.append(
            {
                "von_s": von,
                "bis_s": bis,
                "hz_soll": float((start.get("daten") or {}).get("hz_soll") or standard_hz),
                "fenster": (start.get("daten") or {}).get("name", ""),
            }
        )
        zeiger = bis
    if ende > zeiger or not stuecke:
        stuecke.append({"von_s": zeiger, "bis_s": ende, "hz_soll": standard_hz})
    return stuecke


def hz_soll_bei(stuecke, zeitpunkt, standard_hz=STANDARD_HZ):
    for stueck in stuecke:
        if stueck["von_s"] <= zeitpunkt <= stueck["bis_s"]:
            return stueck["hz_soll"]
    return standard_hz
```

In `src/spotlab/mcp/werkzeuge.py` den Import ergänzen und `zustand_zusammenfassen` anpassen:

```python
from spotlab.messung.fenster import abschnitte as _abschnitte
from spotlab.messung.fenster import hz_soll_bei
```

Die Lückenberechnung ersetzen — die feste Grenze fällt weg:

```python
    stuecke = _abschnitte(verzeichnis)
    luecken = []
    for i in range(1, len(zeiten)):
        abstand = zeiten[i] - zeiten[i - 1]
        # Die ZUORDNUNG laeuft ueber die Empfangszeit, weil die Fenstermarken
        # nur die kennen. Die Zeiten hier sind dieselbe Uhr (Feld `t`).
        grenze = 2.0 / hz_soll_bei(stuecke, zeiten[i - 1])
        if abstand > grenze:
            luecken.append(
                {"von_s": round(zeiten[i - 1], 3), "laenge_s": round(abstand, 3)}
            )
```

und in die Antwort aufnehmen:

```python
        "abschnitte": stuecke,
        "luecken": luecken,
```

`SOLLTAKT_S` und `LUECKE_AB_S` bleiben als Standardwerte stehen; `takt_soll_hz` in der
Antwort wird zu `takt_soll_hz: STANDARD_HZ` — oder besser entfernt, weil `abschnitte` die
Frage genauer beantwortet. **Entfernen**, und den Test in `test_mcp_lesen.py`, der
`takt_soll_hz == 10.0` prüft, auf `abschnitte` umstellen.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_mcp_lesen.py -q
python -m pytest -q
```

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/messung/fenster.py src/spotlab/mcp/werkzeuge.py tests/test_mcp_lesen.py
git commit -m "fix(mcp): Luecken abschnittsweise gegen die erwartete Rate messen"
```

---

## Aufgabe 8: `spotlab doctor` — die Zeile „Zustandsstrom"

**Dateien:**
- Ändern: `src/spotlab/workshop/doctor.py`
- Test: `tests/test_doctor.py` (ergänzen)

**Schnittstellen:**
- Liefert: `STUFEN` mit `"Zustandsstrom"` nach `"Zeitsync"`; ein `Check` mit `ok=True`
  in **beiden** Fällen — die Zeile beantwortet eine Frage, sie prüft keinen Defekt.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_zustandsstrom_ist_eine_stufe():
    from spotlab.workshop.doctor import STUFEN

    assert "Zustandsstrom" in STUFEN
    assert STUFEN.index("Zustandsstrom") == STUFEN.index("Zeitsync") + 1


def test_zustandsstrom_vorhanden(monkeypatch):
    from spotlab.workshop.doctor import _zustandsstrom

    pruefung = _zustandsstrom(_RobotMit(["robot-state", "robot-state-streaming"]))
    assert pruefung.ok is True
    assert "verfügbar" in pruefung.detail


def test_zustandsstrom_fehlt_ist_kein_fehler():
    """Die Zeile beantwortet eine Frage — ein rotes Kreuz waere eine Falschaussage."""
    from spotlab.workshop.doctor import _zustandsstrom

    pruefung = _zustandsstrom(_RobotMit(["robot-state"]))
    assert pruefung.ok is True
    assert "Lizenz" in pruefung.rat


def test_zustandsstrom_bei_fehlender_liste():
    from spotlab.workshop.doctor import _zustandsstrom

    class Kaputt:
        def list_services(self):
            raise RuntimeError("keine Verbindung")

    pruefung = _zustandsstrom(Kaputt())
    assert pruefung.ok is True
    assert "nicht ermittelbar" in pruefung.detail
```

Die Attrappe am Kopf der Datei:

```python
class _RobotMit:
    def __init__(self, namen):
        self._namen = namen

    def list_services(self):
        return [type("Dienst", (), {"name": n})() for n in self._namen]
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Erwartet: `assert "Zustandsstrom" in STUFEN` schlägt fehl.

- [ ] **Schritt 3: Umsetzen**

```python
STUFEN = (
    "Konfiguration", "Netz", "Anmeldung", "Zeitsync", "Zustandsstrom",
    "Not-Aus", "Lease", "Akku",
)

STROM_DIENST = "robot-state-streaming"


def _zustandsstrom(robot):
    """Gibt es den 333-Hz-Zustandsstrom auf diesem Roboter?

    Die Zeile BENUTZT ihn nicht. Sie beantwortet nur, ob die lizenzpflichtige
    Joint-Control-API auf diesem Geraet freigeschaltet ist — dort, wo man
    ohnehin hinschaut, bevor man misst. Beide Antworten sind ok=True: ein
    fehlender Strom ist kein Defekt.
    """
    try:
        namen = {getattr(d, "name", "") for d in robot.list_services()}
    except Exception as fehler:
        return Check(
            "Zustandsstrom", True, f"nicht ermittelbar ({type(fehler).__name__})",
            "Ohne die Angabe bleibt es bei RobotState mit rund 10-50 Hz.",
        )
    if STROM_DIENST in namen:
        return Check(
            "Zustandsstrom", True, "verfügbar (333 Hz mit rohem IMU)",
            "spotlab nutzt ihn noch nicht — die Messfenster laufen über RobotState.",
        )
    return Check(
        "Zustandsstrom", True, "nicht vorhanden",
        "Der 333-Hz-Strom braucht die Joint-Control-Lizenz. Ohne ihn liefert "
        "RobotState alles ausser rohem IMU — für die Gates reicht das.",
    )
```

In `diagnose()` nach der Zeitsync-Zeile einfügen:

```python
    pruefungen.append(Check("Zeitsync", True, "Uhren laufen synchron"))
    pruefungen.append(_zustandsstrom(robot))
```

**Vor dem Schreiben prüfen:** wie die Dienstliste auf einem `bosdyn`-`Robot` wirklich heisst
(`robot.list_services()` gibt `ServiceEntry`-Objekte mit `.name`). Weicht es ab, `_zustandsstrom`
daran anpassen — die Attrappe im Test bildet nur `.name` ab und bleibt gültig.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_doctor.py -q
python -m pytest -q
```

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/workshop/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): meldet, ob der 333-Hz-Zustandsstrom freigeschaltet ist"
```

---

## Aufgabe 9: Ende-zu-Ende, Dokumentation und Abnahme

**Dateien:**
- Test: `tests/test_messfahrt_ende_zu_ende.py`
- Ändern: `CLAUDE.md`
- Ändern: `docs/ABNAHME.md`
- Ändern: `docs/ANBINDUNG.md` (Abschnitt zur Messfahrt)

- [ ] **Schritt 1: Den Ende-zu-Ende-Test schreiben**

`tests/test_messfahrt_ende_zu_ende.py` — **ein echter Prozess**, die Regel, an der „In VS
Code öffnen" durch die Suite gerutscht ist:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

from spotlab.messung.fenster import fenster, schreibe

QUELLE = str(Path(__file__).resolve().parents[1] / "src")

SKRIPT = '''
import spotlab

with spotlab.connect(backend="dryrun") as spot:
    spot.power_on()
    spot.stand()
    with spot.messfenster("G1", hz=50):
        spot.walk(vx=0.0, duration=0.4)
    with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
        spot.walk(vx=0.30, duration=0.4)
'''


def test_messfahrt_im_trockenlauf_ergibt_zwei_auswertbare_fenster(tmp_path):
    skript = tmp_path / "messfahrt.py"
    skript.write_text(SKRIPT, encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(skript)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": QUELLE, "PYTHONUTF8": "1"},
    )
    assert ergebnis.returncode == 0, ergebnis.stderr

    laeufe = list((tmp_path / "runs").iterdir())
    assert len(laeufe) == 1
    lauf = laeufe[0]

    gefunden = fenster(lauf)
    assert [f.name for f in gefunden] == ["G1", "G3"]
    for f in gefunden:
        assert f.abtastungen > 0, f.name
        assert f.reich is True, f.name
        assert f.zeitquelle == "robot", f.name
        assert f.messwerte["hoehe_mittel"] > 0.3
        assert f.messwerte["mu_mittel"] is not None

    g3 = gefunden[1]
    assert g3.felder == {"stuetzstelle": "0.30"}
    assert g3.messwerte["kommandiert"]["vx"] == 0.30

    pfad = schreibe(lauf)
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    assert [f["name"] for f in daten["fenster"]] == ["G1", "G3"]


def test_ausserhalb_der_fenster_bleibt_es_schlank(tmp_path):
    skript = tmp_path / "messfahrt.py"
    skript.write_text(SKRIPT, encoding="utf-8")
    subprocess.run(
        [sys.executable, str(skript)],
        capture_output=True, text=True,
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": QUELLE, "PYTHONUTF8": "1"},
    )
    lauf = next(iter((tmp_path / "runs").iterdir()))
    saetze = [
        json.loads(z)
        for z in (lauf / "zustand.jsonl").read_text(encoding="utf-8").splitlines()
        if z.strip()
    ]
    schlanke = [s for s in saetze if "feet_detail" not in s["daten"]]
    assert schlanke, "kein einziger schlanker Satz — die Rate wird nicht zurückgestellt"
    # Und die immer-dabei-Felder fehlen nirgends.
    assert all("z" in s["daten"] and "t_robot" in s["daten"] for s in saetze)
```

- [ ] **Schritt 2: Test laufen lassen**

```bash
python -m pytest tests/test_messfahrt_ende_zu_ende.py -q
```

Er darf jetzt schon grün sein — Aufgaben 1–7 haben alles gebaut. Ist er rot, ist eine
Verdrahtung offen; **den Fehler beheben, nicht den Test aufweichen.**

- [ ] **Schritt 3: `CLAUDE.md` ergänzen**

Unter „Nicht verhandelbar":

```markdown
- **Bestehende Schlüssel in `zustand.jsonl` ändern sich nicht.** `pose` bleibt
  `(x, y, yaw)`, `feet` bleibt vier Wahrheitswerte. Die Live-Ansicht liest genau das, und
  alte Aufzeichnungen müssen lesbar bleiben. Neue Felder kommen dazu, nie an ihre Stelle.
- **`t_robot` wird nicht in die Klientenzeit umgerechnet.** Für die Kalibrierung zählen
  Abstände innerhalb eines Laufs; eine Umrechnung schöbe die Unsicherheit der
  Zeitsynchronisierung in jede Ableitung. Der Umschlag-Zeitstempel `t` bleibt die
  Empfangszeit — beide Uhren nebeneinander machen die Latenz sichtbar statt versteckt.
- **Der Abtaster holt nichts nach.** Dauert die RPC länger als die Periode, läuft die
  Schleife langsamer. Nachholen erzeugte Bursts, die in der Auswertung wie echte Dynamik
  aussehen.
- **`messung/` importiert nichts aus `api/`, `backends/`, `gui/` und kein `bosdyn`.**
  `spotlab.record.read` und `spotlab.errors` sind erlaubt.
```

Unter „Regeln":

```markdown
- **Fehlende Messwerte sind `None`, nie 0.** Der Unterschied zwischen „gemessen und null"
  und „nicht gemessen" entscheidet, ob eine Kalibrierung gültig ist. Das gilt besonders für
  `ground_mu_est`: ein erfundener Reibwert 0.0 mittelt sich durch jede Auswertung.
- spotlab liefert **Messwerte, keine Urteile**. Die Kriterien der Realismus-Gates liegen in
  `matura-spot`; `schranke`, `annahme` und `real_prozedur` gehören dorthin, wo das
  RESEARCH-DECISION-Protokoll gilt.
- Der Lückenmelder misst **abschnittsweise** gegen die erwartete Rate. Ein Alarm, der bei
  jeder Messfahrt kommt, wird ignoriert.
```

„Umsetzungsstand" ersetzen:

```markdown
Fundament (1+2), GUI (3), GraphNav (4), Editor (5), Anbindung samt MCP-Server (6) und die
Kalibrier-Infrastruktur (7) sind vollständig. Offen und bewusst nicht gebaut: der
Sim-Adapter, NN-Anbindung, Mehrbenutzer-Dienst, Arm und Docking. In Stufe 7 bewusst nicht
gebaut: ein Simulator in spotlab, automatische Parameteranpassung, die Nutzung der
lizenzpflichtigen 333-Hz-APIs.

Specs unter `docs/superpowers/specs/`; Anleitungen: `docs/ANBINDUNG.md`.
```

- [ ] **Schritt 4: `docs/ABNAHME.md` — A18 einfügen**

Vor „## Nach der Abnahme":

```markdown
## A18 — Abtastrate und Lücken über WLAN

**Prozedur** Eine Messfahrt mit `hz=50` über 30 s auf ebenem Boden, danach
`messfenster.json` und `zustand_zusammenfassen` ansehen.

**Erwartung** `hz_ist` und die Lückenliste werden **notiert, nicht bestanden oder
durchgefallen**. Diese Zahl entscheidet, ob 50 Hz realistisch sind oder ob die Fenster auf
20 Hz gehen müssen — und sie ist die einzige, die kein Test ohne Roboter liefern kann.

**Zusätzlich notieren:**
- ob `spotlab doctor` den Zustandsstrom meldet,
- ob `ground_mu_est` von null verschiedene Werte liefert. Bleibt der Reibwert konstant 0,
  fällt diese Quelle für die Kalibrierung aus — besser vor der Messkampagne gewusst als
  danach.

**Ergebnis** _(offen)_

---
```

- [ ] **Schritt 5: `docs/ANBINDUNG.md` um einen Abschnitt „Messfahrt" ergänzen**

Nach Abschnitt 6, mit lauffähigem Beispiel:

```markdown
## 7 · Messfahrt für die Sim-Kalibrierung

```python
import spotlab

with spotlab.connect() as spot:
    spot.power_on()
    spot.stand()
    with spot.messfenster("G3", stuetzstelle="0.30", hz=50):
        spot.walk(vx=0.30, duration=8.0)
```

Innerhalb des Blocks tastet spotlab mit 50 Hz und vollem Umfang ab — Gelenke mit
Drehmoment, Fusskontakte mit Reibwert und Schlupf, Körperhöhe, Neigung, Roboterzeit.
Ausserhalb bleibt es bei 10 Hz und schlank.

Danach:

```python
from spotlab.messung.fenster import schreibe
schreibe("<pfad>/runs/<lauf-id>")     # legt messfenster.json an
```

`messfenster.json` enthält je Fenster die Messwerte, **nicht** das Urteil: die
Gate-Kriterien liegen in deinem Repo.
```

- [ ] **Schritt 6: Ganze Suite und ein Blick auf einen echten Desktop**

```bash
python -m pytest -q
```

```bash
spotlab gui
```

Ein Trockenlauf mit Messfenstern in „Live-Lauf" ansehen: die Ansicht darf durch die reichen
Sätze nicht langsamer oder fehlerhaft werden.

- [ ] **Schritt 7: Committen**

```bash
git add CLAUDE.md docs/ABNAHME.md docs/ANBINDUNG.md tests/test_messfahrt_ende_zu_ende.py
git commit -m "docs: Kalibrierregeln, Abnahmepunkt A18, Anleitung zur Messfahrt"
```

---

## Selbstprüfung des Plans

**Abdeckung der Spec:**

| Spec | Aufgabe |
|---|---|
| §4.1 reichere Abtastung, `rpy_aus`, `as_sample(reich)` | 1 |
| §4.2 `setze_takt`, kein Nachholen | 3 |
| §4.3 `messfenster`, neue Ereignisart, `connect()`-Verdrahtung | 4 |
| §4.4 `messung/fenster.py`, Kennzahlen, `gierwinkel_grad`, `tracking_prozent` | 5, 6 |
| §4.5 Lückenmelder abschnittsweise | 7 |
| §4.6 Doktor-Zeile | 8 |
| §4.7 Trockenlauf füllt die Felder | 2 |
| §3 Format, Rückwärtskompatibilität | 1 (Test), 9 (CLAUDE.md) |
| §6 Fehlerbehandlung | als Tests in 1, 4, 5, 6 |
| §7 Prüfung, echter Prozess | 9 |
| §8 A18 | 9 |

**Namen, die über Aufgaben hinweg gleich bleiben müssen:** `rpy_aus`, `as_sample(zustand,
reich)`, `JointState.acceleration`, `State.z/roll/pitch/t_robot/velocity_vision/feet_detail/
behavior/battery_detail/motor_temps`, `StateSampler.setze_takt/takt`, `Spot.messfenster`,
`Spot.sampler`, Ereignisart `"messfenster"` mit `phase`/`name`/`hz_soll`, `Fenster`,
`fenster`, `kennzahlen`, `abschnitte`, `hz_soll_bei`, `als_json`, `schreibe`,
`DATEINAME = "messfenster.json"`, `_zustandsstrom`, `STROM_DIENST`.

**Vor dem Schreiben in der Quelle nachzusehen** (dort gilt die Quelle, nicht der Plan):
die Signatur von `robot.list_services()` und der Feldname `.name` (Aufgabe 8); ob ein
bestehender Trockenlauf-Test die Körperpose als Ursprung annimmt (Aufgabe 2).
