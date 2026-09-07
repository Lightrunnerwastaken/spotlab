# Gelände, Etappe 1 „Kern" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Höhenraster `Gelaende` als Element des Raums (Fassung 4, Binärdatei daneben), das `boden_bei` als Grund kennt; Klippen, Ebenen, Kollision und Gitter folgen ihm; das Pauspapier trägt den gelaufenen Weg (PAUS2), die Rekonstruktion liefert ihn.

**Architecture:** Neues Modul `welt/gelaende.py` (Standardbibliothek) mit Element, Abtastung, Klippen, Plateaus, Datei. `welt/raum.py` bekommt `Raum.gelaende` und den `[gelaende]`-Verweis; `welt/hoehe.py` fragt das Gelände als Grundkandidaten; `welt/kollision.py` merkt sich Klippen je Raum. `welt/pauspapier.py` schreibt PAUS2 mit Weg; `maps/rekonstruktion.py::Ergebnis` trägt `weg`; der Tab hält ihn.

**Tech Stack:** Python 3.11+, Standardbibliothek in `welt/`, numpy nur in Tests/`maps/`; pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-korrigierer-gelaende-design.md` (§ 1, 2, 3)

## Global Constraints

- `welt/` bleibt reine Standardbibliothek (numpy nur in `wahrnehmung.py`).
- Kein `bosdyn`, `mujoco`, `spotsim`, `spotlab.backends` unter `gui/`.
- `boden_bei` ist die einzige Stelle, die `raum.gelaende` nach der Höhe an einem Punkt fragt (ausser `gelaende.py` selbst, `pruefe` und die Sichten für ihr Bild).
- `MAX_STUFE_M = 0.25` aus `welt/raum.py` ist die Klippenregel, auch für das Gelände.
- Tests: `PYTHONPATH=src /c/Users/janis/miniconda3/python.exe -m pytest -q -p no:cacheprovider <datei>` im Worktree `.worktrees/korrigierer`.
- Commits mit `-F <datei>`, Trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- `None` steht für „kein Boden" im Speicher, NaN nur in der Datei.

---

### Task 1: Das Element `Gelaende` mit Abtastung

**Files:**
- Create: `src/spotlab/welt/gelaende.py`
- Test: `tests/test_welt_gelaende.py`

**Interfaces:**
- Produces: `GELAENDE_ZELLE_M = 0.2`; `Gelaende(x0, y0, zelle, zeilen, spalten, hoehen)` (frozen dataclass, `hoehen` Tupel mit `float | None`, `zeilen >= 2`, `spalten >= 2`, sonst `ValueError`); `Gelaende.knoten(i, j) -> float | None` (ausserhalb `None`); `Gelaende.hoehe_bei(x, y) -> float | None`; `Gelaende.neigung_bei(x, y) -> (float, float)`; `umriss(gelaende) -> (x_min, y_min, x_max, y_max)` über gültige Knoten (alle ungültig → `None`); `verschoben(gelaende, dx, dy, dz) -> Gelaende`; `zusammenfassung(gelaende) -> str`; `gitter(x0, y0, zelle, zeilen, spalten, funktion) -> Gelaende` (Testhelfer im Modul: `funktion(x, y)` gibt Höhe oder `None`).

- [ ] **Step 1: Tests**

```python
import math
import pytest
from spotlab.welt import gelaende as g


def _ebene(x0=0.0, y0=0.0, zelle=0.5, zeilen=4, spalten=5, f=lambda x, y: 0.1 * x):
    return g.gitter(x0, y0, zelle, zeilen, spalten, f)


def test_ein_gelaende_braucht_mindestens_zwei_mal_zwei_knoten():
    with pytest.raises(ValueError):
        g.Gelaende(0.0, 0.0, 0.2, 1, 3, (0.0, 0.0, 0.0))


def test_knoten_ausserhalb_ist_none():
    ge = _ebene()
    assert ge.knoten(0, 0) == 0.0
    assert ge.knoten(-1, 0) is None and ge.knoten(0, 5) is None


def test_hoehe_bei_ist_bilinear():
    ge = g.gitter(0.0, 0.0, 1.0, 2, 2, lambda x, y: {(0, 0): 0.0, (1, 0): 1.0, (0, 1): 0.0, (1, 1): 1.0}[(int(x), int(y))])
    assert ge.hoehe_bei(0.5, 0.5) == pytest.approx(0.5)
    assert ge.hoehe_bei(0.25, 0.9) == pytest.approx(0.25)


def test_hoehe_bei_ausserhalb_ist_none():
    assert _ebene().hoehe_bei(-0.1, 0.0) is None
    assert _ebene().hoehe_bei(2.0, 1.6) is None      # spalten 5 -> x bis 2.0, zeilen 4 -> y bis 1.5


def test_am_rand_gilt_der_naechste_gueltige_knoten():
    def f(x, y):
        return None if (x, y) == (1.0, 1.0) else 0.3
    ge = g.gitter(0.0, 0.0, 1.0, 2, 2, f)
    assert ge.hoehe_bei(0.9, 0.9) == pytest.approx(0.3)


def test_alle_vier_none_gibt_none():
    ge = g.gitter(0.0, 0.0, 1.0, 3, 3, lambda x, y: None if x < 1.5 else 0.2)
    assert ge.hoehe_bei(0.5, 0.5) is None
    assert ge.hoehe_bei(1.7, 0.5) == pytest.approx(0.2)


def test_neigung_folgt_dem_gefaelle():
    ge = _ebene(f=lambda x, y: 0.1 * x)
    dzdx, dzdy = ge.neigung_bei(1.0, 0.75)
    assert dzdx == pytest.approx(0.1, abs=1e-6) and dzdy == pytest.approx(0.0, abs=1e-6)
    assert ge.neigung_bei(-5.0, 0.0) == (0.0, 0.0)


def test_umriss_und_verschieben():
    ge = _ebene(zelle=0.5, zeilen=4, spalten=5)
    assert g.umriss(ge) == (0.0, 0.0, 2.0, 1.5)
    neu = g.verschoben(ge, 1.0, 2.0, 0.5)
    assert g.umriss(neu) == (1.0, 2.0, 3.0, 3.5)
    assert neu.knoten(0, 2) == pytest.approx(0.1 + 0.5)


def test_zusammenfassung_nennt_zelle_knoten_und_spanne():
    text = g.zusammenfassung(_ebene(f=lambda x, y: 0.1 * x))
    assert text.startswith("Gelände · 0.5 m · 20 Knoten · 0.00 bis 0.20 m")
```

- [ ] **Step 2: Laufen lassen, alle scheitern** („No module named spotlab.welt.gelaende").

- [ ] **Step 3: Implementieren**

```python
"""Das Gelaende: ein Hoehenraster als Grund des Raums. Standardbibliothek."""

import math
from dataclasses import dataclass, replace

from spotlab.welt.raum import MAX_STUFE_M

GELAENDE_ZELLE_M = 0.2
PLATEAU_NEIGUNG_GRAD = 2.0
PLATEAU_KNOTEN = 50


@dataclass(frozen=True)
class Gelaende:
    x0: float
    y0: float
    zelle: float
    zeilen: int
    spalten: int
    hoehen: tuple

    def __post_init__(self):
        if self.zeilen < 2 or self.spalten < 2:
            raise ValueError("Ein Gelaende braucht mindestens 2 x 2 Knoten.")
        if len(self.hoehen) != self.zeilen * self.spalten:
            raise ValueError("hoehen passt nicht zu zeilen x spalten.")
        object.__setattr__(self, "hoehen", tuple(self.hoehen))

    def knoten(self, i, j):
        if 0 <= i < self.zeilen and 0 <= j < self.spalten:
            return self.hoehen[i * self.spalten + j]
        return None

    def hoehe_bei(self, x, y):
        fx = (x - self.x0) / self.zelle
        fy = (y - self.y0) / self.zelle
        if fx < 0 or fy < 0 or fx > self.spalten - 1 or fy > self.zeilen - 1:
            return None
        j = min(int(fx), self.spalten - 2)
        i = min(int(fy), self.zeilen - 2)
        tx, ty = fx - j, fy - i
        ecken = [(self.knoten(i, j), 0.0, 0.0), (self.knoten(i, j + 1), 1.0, 0.0),
                 (self.knoten(i + 1, j), 0.0, 1.0), (self.knoten(i + 1, j + 1), 1.0, 1.0)]
        gueltig = [e for e in ecken if e[0] is not None]
        if not gueltig:
            return None
        if len(gueltig) == 4:
            h00, h10, h01, h11 = (e[0] for e in ecken)
            return (h00 * (1 - tx) * (1 - ty) + h10 * tx * (1 - ty)
                    + h01 * (1 - tx) * ty + h11 * tx * ty)
        return min(gueltig, key=lambda e: (e[1] - tx) ** 2 + (e[2] - ty) ** 2)[0]

    def neigung_bei(self, x, y):
        h = self.zelle / 2
        mitte = self.hoehe_bei(x, y)
        if mitte is None:
            return 0.0, 0.0

        def ableitung(a, b, schritt):
            if a is not None and b is not None:
                return (b - a) / (2 * schritt)
            if b is not None:
                return (b - mitte) / schritt
            if a is not None:
                return (mitte - a) / schritt
            return 0.0

        return (ableitung(self.hoehe_bei(x - h, y), self.hoehe_bei(x + h, y), h),
                ableitung(self.hoehe_bei(x, y - h), self.hoehe_bei(x, y + h), h))


def gitter(x0, y0, zelle, zeilen, spalten, funktion):
    hoehen = tuple(funktion(x0 + j * zelle, y0 + i * zelle) for i in range(zeilen) for j in range(spalten))
    return Gelaende(x0, y0, zelle, zeilen, spalten, hoehen)


def umriss(gelaende):
    xs, ys = [], []
    for i in range(gelaende.zeilen):
        for j in range(gelaende.spalten):
            if gelaende.knoten(i, j) is not None:
                xs.append(gelaende.x0 + j * gelaende.zelle)
                ys.append(gelaende.y0 + i * gelaende.zelle)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def verschoben(gelaende, dx, dy, dz):
    return replace(gelaende, x0=gelaende.x0 + dx, y0=gelaende.y0 + dy,
                   hoehen=tuple(None if h is None else h + dz for h in gelaende.hoehen))


def zusammenfassung(gelaende):
    werte = [h for h in gelaende.hoehen if h is not None]
    if not werte:
        return "Gelände · ohne Boden"
    return (f"Gelände · {gelaende.zelle:g} m · {len(werte)} Knoten · "
            f"{min(werte):.2f} bis {max(werte):.2f} m")
```

- [ ] **Step 4: Tests grün.** Commit `feat(welt): Gelaende -- Hoehenraster mit bilinearer Abtastung`.

### Task 2: Klippen und Plateaus des Geländes

**Files:** Modify `src/spotlab/welt/gelaende.py`; Test `tests/test_welt_gelaende.py`.

**Interfaces:** Produces `klippen(gelaende) -> [(x1, y1, x2, y2)]`, `plateaus(gelaende) -> [float]`.

- [ ] **Step 1: Tests**

```python
def test_ein_sprung_ueber_max_stufe_ist_eine_klippe_und_eine_strecke():
    ge = g.gitter(0.0, 0.0, 0.2, 4, 6, lambda x, y: 0.0 if x < 0.5 else 0.5)
    kl = [k for k in g.klippen(ge) if abs(k[0] - 0.5) < 1e-9 and abs(k[2] - 0.5) < 1e-9]
    assert len(kl) == 1                       # eine Strecke, nicht vier Stuecke
    x1, y1, x2, y2 = kl[0]
    assert min(y1, y2) == pytest.approx(-0.1) and max(y1, y2) == pytest.approx(0.7)


def test_ein_sprung_unter_max_stufe_ist_keine_klippe():
    ge = g.gitter(0.0, 0.0, 0.2, 4, 6, lambda x, y: 0.0 if x < 0.5 else 0.2)
    assert not [k for k in g.klippen(ge) if abs(k[0] - 0.5) < 1e-9]


def test_der_rand_ueber_max_stufe_ist_eine_klippe():
    ge = g.gitter(0.0, 0.0, 0.2, 3, 3, lambda x, y: 0.6)
    assert len(g.klippen(ge)) == 4                 # vier Kanten, je eine Strecke


def test_der_rand_auf_dem_grund_ist_keine_klippe():
    assert g.klippen(g.gitter(0.0, 0.0, 0.2, 3, 3, lambda x, y: 0.1)) == []


def test_plateaus_sind_die_ebenen_flaechen():
    def f(x, y):
        if x < 2.0:
            return 0.0
        if x < 4.0:
            return (x - 2.0) * 0.5          # Rampe auf 1.0
        return 1.0
    ge = g.gitter(0.0, 0.0, 0.2, 12, 31, f)      # 12 Zeilen x 10 Spalten je Plateau = 120 Knoten
    assert g.plateaus(ge) == [0.0, 1.0]
```

- [ ] **Step 2: Scheitern sehen.**

- [ ] **Step 3: Implementieren**

```python
def _laeufe(indizes):
    """[3, 4, 5, 8] -> [(3, 5), (8, 8)]"""
    laeufe = []
    for k in sorted(indizes):
        if laeufe and laeufe[-1][1] == k - 1:
            laeufe[-1] = (laeufe[-1][0], k)
        else:
            laeufe.append((k, k))
    return laeufe


def klippen(gelaende):
    """Kanten auf Zellgrenzen, an denen der Grund um mehr als MAX_STUFE_M springt.
    Ein fehlender Knoten (auch ausserhalb des Rasters) gilt als Grund 0."""
    z, x0, y0 = gelaende.zelle, gelaende.x0, gelaende.y0

    def wert(i, j):
        h = gelaende.knoten(i, j)
        return 0.0 if h is None else h

    def springt(i, j, i2, j2):
        if gelaende.knoten(i, j) is None and gelaende.knoten(i2, j2) is None:
            return False
        return abs(wert(i, j) - wert(i2, j2)) > MAX_STUFE_M

    ergebnis = []
    for j in range(-1, gelaende.spalten):            # senkrechte Grenzen zwischen j und j+1
        zeilen = [i for i in range(gelaende.zeilen) if springt(i, j, i, j + 1)]
        x = x0 + (j + 0.5) * z
        for a, b in _laeufe(zeilen):
            ergebnis.append((x, y0 + (a - 0.5) * z, x, y0 + (b + 0.5) * z))
    for i in range(-1, gelaende.zeilen):             # waagrechte Grenzen zwischen i und i+1
        spalten = [j for j in range(gelaende.spalten) if springt(i, j, i + 1, j)]
        y = y0 + (i + 0.5) * z
        for a, b in _laeufe(spalten):
            ergebnis.append((x0 + (a - 0.5) * z, y, x0 + (b + 0.5) * z, y))
    return ergebnis


def plateaus(gelaende):
    grenze = math.tan(math.radians(PLATEAU_NEIGUNG_GRAD)) * gelaende.zelle
    zaehler = {}
    for i in range(gelaende.zeilen):
        for j in range(gelaende.spalten):
            h = gelaende.knoten(i, j)
            if h is None:
                continue
            nachbarn = [gelaende.knoten(i + di, j + dj) for di, dj in ((0, 1), (0, -1), (1, 0), (-1, 0))]
            if any(n is None or abs(n - h) > grenze for n in nachbarn):
                continue
            stufe = round(h, 1)
            zaehler[stufe] = zaehler.get(stufe, 0) + 1
    return sorted(s for s, n in zaehler.items() if n >= PLATEAU_KNOTEN)
```

- [ ] **Step 4: Grün.** Commit `feat(welt): Klippen und Plateaus des Gelaendes`.

### Task 3: Die Gelände-Datei

**Files:** Modify `src/spotlab/welt/gelaende.py`; Test `tests/test_welt_gelaende.py`.

**Interfaces:** Produces `ENDUNG = ".gelaende"`, `KENNUNG = b"GEL1"`, `pfad_zu(raumpfad) -> Path`, `schreibe(pfad, gelaende)`, `lies(pfad) -> Gelaende | None`.

- [ ] **Step 1: Tests**

```python
def test_datei_hin_und_zurueck_mit_none(tmp_path):
    ge = g.gitter(1.0, 2.0, 0.25, 3, 4, lambda x, y: None if x > 1.6 else x + y)
    pfad = g.pfad_zu(tmp_path / "raum.toml")
    assert pfad.suffix == ".gelaende"
    g.schreibe(pfad, ge)
    zurueck = g.lies(pfad)
    assert (zurueck.x0, zurueck.y0, zurueck.zelle, zurueck.zeilen, zurueck.spalten) == (1.0, 2.0, 0.25, 3, 4)
    assert zurueck.knoten(0, 3) is None
    assert zurueck.knoten(1, 1) == pytest.approx(1.25 + 2.25, abs=1e-6)


def test_fehlende_datei_ist_none(tmp_path):
    assert g.lies(tmp_path / "nix.gelaende") is None


def test_falsche_kennung_ist_ein_fehler(tmp_path):
    from spotlab.errors import SpotlabError
    pfad = tmp_path / "kaputt.gelaende"
    pfad.write_bytes(b"PAUS1" + b"\0" * 20)
    with pytest.raises(SpotlabError, match="Gelände"):
        g.lies(pfad)
```

- [ ] **Step 2: Scheitern.**

- [ ] **Step 3: Implementieren**

```python
import struct
from array import array
from pathlib import Path

from spotlab.errors import SpotlabError

KENNUNG = b"GEL1"
ENDUNG = ".gelaende"
_KOPF = "<4sdddII"


def pfad_zu(raumpfad):
    return Path(raumpfad).with_suffix(ENDUNG)


def schreibe(pfad, gelaende):
    werte = array("f", (math.nan if h is None else float(h) for h in gelaende.hoehen))
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "wb") as datei:
        datei.write(struct.pack(_KOPF, KENNUNG, gelaende.x0, gelaende.y0, gelaende.zelle,
                                gelaende.zeilen, gelaende.spalten))
        datei.write(werte.tobytes())


def lies(pfad):
    pfad = Path(pfad)
    if not pfad.is_file():
        return None
    roh = pfad.read_bytes()
    kopf = struct.calcsize(_KOPF)
    if len(roh) < kopf or roh[:4] != KENNUNG:
        raise SpotlabError(f"{pfad.name} ist keine Gelände-Datei (Kennung fehlt). "
                           f"Die Datei löschen und den Raum neu korrigieren.")
    _k, x0, y0, zelle, zeilen, spalten = struct.unpack(_KOPF, roh[:kopf])
    werte = array("f")
    werte.frombytes(roh[kopf:kopf + zeilen * spalten * 4])
    if len(werte) != zeilen * spalten:
        raise SpotlabError(f"{pfad.name} ist unvollständig. Den Raum neu korrigieren.")
    return Gelaende(x0, y0, zelle, zeilen, spalten,
                    tuple(None if math.isnan(w) else float(w) for w in werte))
```

- [ ] **Step 4: Grün.** Commit `feat(welt): Gelaende-Datei GEL1`.

### Task 4: Raumformat v4

**Files:** Modify `src/spotlab/welt/raum.py` (`Raum`, `huelle`, `raum_laden_pfad`, `raum_speichern`); Test `tests/test_welt_raum.py`.

**Interfaces:** Produces `Raum.gelaende: Gelaende | None = None`; `raum_speichern` schreibt `fassung = 4`, `[gelaende] datei = "<stem>.gelaende"` und die Binärdatei über `gelaende.schreibe(gelaende.pfad_zu(pfad), raum.gelaende)`; ohne Gelände löscht es eine vorhandene `.gelaende` desselben Stamms; `raum_laden_pfad` liest `[gelaende].datei` relativ zur Raumdatei, fehlend → `SpotlabError("… Gelände-Datei … fehlt …")`; `huelle` nimmt `gelaende.umriss` mit. Der Import in `raum.py` geschieht innerhalb der Funktionen (`from spotlab.welt import gelaende as _gelaende`), weil `gelaende.py` `MAX_STUFE_M` aus `raum.py` importiert.

- [ ] **Step 1: Tests**

```python
def test_raum_mit_gelaende_speichert_fassung_4_und_datei(tmp_path):
    from spotlab.welt import gelaende as g
    ge = g.gitter(0.0, 0.0, 0.5, 3, 3, lambda x, y: 0.3)
    raum = Raum("G", "", (1.0, 1.0, 0.0), waende=[(0, 0, 3, 0)], gelaende=ge)
    pfad = tmp_path / "g.toml"
    raum_speichern(raum, pfad)
    text = pfad.read_text(encoding="utf-8")
    assert "fassung      = 4" in text and '[gelaende]\ndatei = "g.gelaende"' in text
    assert (tmp_path / "g.gelaende").is_file()
    zurueck = raum_laden_pfad(pfad)
    assert zurueck.gelaende.knoten(1, 1) == pytest.approx(0.3)


def test_ohne_gelaende_keine_spur_und_alte_datei_weg(tmp_path):
    (tmp_path / "g.gelaende").write_bytes(b"x")
    raum_speichern(Raum("G", "", (1.0, 1.0, 0.0), waende=[(0, 0, 3, 0)]), tmp_path / "g.toml")
    assert "gelaende" not in (tmp_path / "g.toml").read_text(encoding="utf-8")
    assert not (tmp_path / "g.gelaende").exists()


def test_fehlende_gelaende_datei_ist_ein_klarer_fehler(tmp_path):
    (tmp_path / "g.toml").write_text(
        '[raum]\nname = "G"\nstart = [1.0, 1.0, 0.0]\nwaende = []\n\n[gelaende]\ndatei = "g.gelaende"\n',
        encoding="utf-8")
    with pytest.raises(SpotlabError, match="Gelände-Datei"):
        raum_laden_pfad(tmp_path / "g.toml")


def test_die_huelle_nimmt_das_gelaende_mit():
    from spotlab.welt import gelaende as g
    ge = g.gitter(5.0, 5.0, 1.0, 2, 2, lambda x, y: 0.0)
    raum = Raum("G", "", (1.0, 1.0, 0.0), gelaende=ge)
    assert huelle(raum)[2] >= 6.0 + RAND_M - 1e-9 and huelle(raum)[3] >= 6.0 + RAND_M - 1e-9
```

- [ ] **Step 2: Scheitern.**

- [ ] **Step 3: Implementieren.** In `Raum`: Feld `gelaende: object = None` (nach `boeden`). In `huelle`: `if raum.gelaende is not None: u = _gelaende.umriss(raum.gelaende); if u: punkte += [(u[0], u[1]), (u[2], u[3])]`. In `raum_laden_pfad`:

```python
    gelaende = None
    verweis = roh.get("gelaende")
    if isinstance(verweis, dict) and verweis.get("datei"):
        from spotlab.welt import gelaende as _gelaende
        gelaende = _gelaende.lies(pfad.parent / str(verweis["datei"]))
        if gelaende is None:
            raise SpotlabError(
                f"Die Gelände-Datei {verweis['datei']} zu {pfad.name} fehlt — den Raum neu "
                f"korrigieren oder den Abschnitt [gelaende] entfernen.")
```

In `raum_speichern`: `mit_gelaende = raum.gelaende is not None`; `fassung = 4 if mit_gelaende else 3` (wenn `mit_hoehe or mit_gelaende`); nach den Tags:

```python
    if mit_gelaende:
        zeilen += ["", "[gelaende]", f"datei = {_text(pfad.with_suffix(_gelaende.ENDUNG).name)}"]
    ...
    pfad.write_text(...)
    if mit_gelaende:
        _gelaende.schreibe(_gelaende.pfad_zu(pfad), raum.gelaende)
    else:
        alt = _gelaende.pfad_zu(pfad)
        if alt.exists():
            alt.unlink()
```

Modul-Docstring um Fassung 4 ergänzen.

- [ ] **Step 4: Grün, ganze `test_welt_raum.py` grün.** Commit `feat(welt): Raumformat v4 -- Gelaende mit Datei daneben`.

### Task 5: Höhe mit Gelände

**Files:** Modify `src/spotlab/welt/hoehe.py` (`boden_bei`, `neigung_bei`, `ebenen`, `boden_z`, `klippen`); Test `tests/test_welt_hoehe.py`.

- [ ] **Step 1: Tests**

```python
def _mit_gelaende(f, boeden=()):
    from spotlab.welt import gelaende as g
    return Raum("G", "", (0.5, 0.5, 0.0), boeden=boeden,
                gelaende=g.gitter(0.0, 0.0, 0.2, 11, 31, f))     # 6 x 2 m


def test_der_grund_ist_das_gelaende():
    raum = _mit_gelaende(lambda x, y: 0.1 * x)
    z, boden = boden_bei(raum, 3.0, 1.0)
    assert z == pytest.approx(0.3) and boden is None


def test_ausserhalb_des_gelaendes_ist_der_grund_null():
    assert boden_bei(_mit_gelaende(lambda x, y: 0.5), 9.0, 9.0) == (0.0, None)


def test_eine_treppe_auf_dem_gelaende_gewinnt():
    treppe = Boden("T", 3.0, 1.0, 2.0, 1.0, z=0.3, anstieg=1.0, stufen=6)
    raum = _mit_gelaende(lambda x, y: 0.3, boeden=(treppe,))
    assert boden_bei(raum, 3.0, 1.0)[1] is treppe


def test_nick_auf_dem_gefaelle():
    raum = _mit_gelaende(lambda x, y: 0.1 * x)
    assert nick_grad(raum, 3.0, 1.0, 0.0) == pytest.approx(-math.degrees(math.atan(0.1)), abs=0.3)


def test_ebenen_mit_plateaus():
    raum = _mit_gelaende(lambda x, y: 0.0 if x < 2.0 else (1.0 if x > 4.0 else (x - 2.0) * 0.5))
    assert ebenen(raum) == [0.0, 1.0]


def test_klippen_des_gelaendes_gehoeren_zum_raum():
    raum = _mit_gelaende(lambda x, y: 0.0 if x < 3.0 else 0.6)
    assert any(abs(k[0] - 2.9) < 1e-6 or abs(k[0] - 3.1) < 1e-6 for k in klippen(raum))
```

- [ ] **Step 2: Scheitern.**

- [ ] **Step 3: Implementieren.** `boden_bei`: Grundkandidat wie in Spec § 2; `neigung_bei`: `if boden is None: return raum.gelaende.neigung_bei(x, y) if raum.gelaende is not None else (0.0, 0.0)`; `ebenen`: `hoehen.update(gelaende_plateaus(raum.gelaende))`; `boden_z`: min mit gültigen Knoten; `klippen`: `ergebnis += gelaende_klippen(raum.gelaende)` am Ende (`from spotlab.welt.gelaende import klippen as gelaende_klippen, plateaus as gelaende_plateaus`). Docstring des Moduls: „Der Grund ist das Gelände, wo es eines gibt, sonst 0."

- [ ] **Step 4: Grün.** Commit `feat(welt): der Grund ist das Gelaende -- boden_bei, Neigung, Ebenen, Klippen`.

### Task 6: Kollision, Gitter, Memo

**Files:** Modify `src/spotlab/welt/kollision.py` (`klippen_von`), `src/spotlab/welt/bearbeitung.py` (`pruefe`); Test `tests/test_welt_kollision.py`, `tests/test_welt_wahrnehmung.py`, `tests/test_welt_bearbeitung.py`.

- [ ] **Step 1: Tests**

```python
# test_welt_kollision.py
def test_eine_gelaendekante_haelt_den_roboter():
    from spotlab.welt import gelaende as g
    raum = Raum("G", "", (0.5, 1.0, 0.0),
                gelaende=g.gitter(0.0, 0.0, 0.2, 11, 31, lambda x, y: 0.0 if x < 3.0 else 0.6))
    kl = klippen_von(raum)
    z, _ = boden_bei(raum, 2.0, 1.0)
    pose, getroffen = bewege_mit_hoehe(raum, (2.0, 1.0), (4.0, 1.0), z, kl)
    assert getroffen == "Kante" and pose[0] < 3.0


def test_klippen_von_merkt_sich_das_ergebnis():
    raum = Raum("G", "", (0.5, 1.0, 0.0), boeden=(Boden("P", 2.0, 1.0, 1.0, 1.0, z=0.5),))
    assert klippen_von(raum) is klippen_von(replace(raum, waende=((0, 0, 1, 0),)))
    assert klippen_von(raum) is not klippen_von(replace(raum, boeden=()))

# test_welt_wahrnehmung.py
def test_das_gitter_meldet_die_gelaendekante():
    from spotlab.welt import gelaende as g
    raum = Raum("G", "", (0.5, 1.0, 0.0),
                gelaende=g.gitter(0.0, 0.0, 0.2, 11, 31, lambda x, y: 0.0 if x < 3.0 else 0.6))
    werte, bekannt, ursprung = abstandsgitter(raum, (2.0, 1.0, 0.0), z=0.0, klippen_=klippen_von(raum))
    assert _gitterwert(werte, ursprung, 2.95, 1.0) < 0.15

# test_welt_bearbeitung.py
def test_pruefe_meldet_eine_schwebende_wand():
    from spotlab.welt import gelaende as g
    raum = Raum("G", "", (0.5, 0.5, 0.0), waende=[Wand(0, 1, 2, 1, z=1.0)],
                gelaende=g.gitter(0.0, 0.0, 0.5, 5, 5, lambda x, y: 0.2))
    assert any("Wand 1 schwebt 0.8 m" in h for h in pruefe(raum))
```

`_gitterwert` existiert in `test_welt_wahrnehmung.py`; `bewege_mit_hoehe` gibt `(pose, getroffen)` — Signatur vor dem Schreiben im Modul nachlesen und den Test anpassen.

- [ ] **Step 2: Scheitern.**

- [ ] **Step 3: Implementieren.** `klippen_von` mit Memo wie im Spec § 2 (ein Eintrag, Identität von `raum.boeden` und `raum.gelaende`, plus `alles`). `pruefe` wie Spec § 2.

- [ ] **Step 4: Grün.** Commit `feat(welt): Gelaendekanten in Kollision und Gitter, Memo fuer Klippen, pruefe`.

### Task 7: Pauspapier PAUS2 mit Weg

**Files:** Modify `src/spotlab/welt/pauspapier.py`; Test `tests/test_welt_pauspapier.py`.

**Interfaces:** Produces `schreibe(pfad, punkte, weg=())`, `lies(pfad)` (unverändert), `lies_weg(pfad) -> [(x, y, z)]`; Kennungen `b"PAUS2"` (neu) und `b"PAUS1"` (lesbar).

- [ ] **Step 1: Tests**

```python
def test_paus2_traegt_den_weg(tmp_path):
    pfad = tmp_path / "r.pauspapier"
    schreibe(pfad, [(1.0, 2.0)], weg=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.5)])
    assert lies(pfad) == [(1.0, 2.0)]
    assert lies_weg(pfad) == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.5)]


def test_paus1_bleibt_lesbar_mit_leerem_weg(tmp_path):
    pfad = tmp_path / "alt.pauspapier"
    pfad.write_bytes(b"PAUS1" + struct.pack("<I", 1) + struct.pack("<ff", 3.0, 4.0))
    assert lies(pfad) == [(3.0, 4.0)] and lies_weg(pfad) == []
```

- [ ] **Step 2: Scheitern.**  - [ ] **Step 3: Implementieren** (Kennung `PAUS2`, `_ALT = b"PAUS1"`; `_lies_roh(pfad) -> (kennung, punkte, weg)`; `lies` und `lies_weg` darauf). - [ ] **Step 4: Grün.** Commit `feat(welt): Pauspapier PAUS2 mit dem gelaufenen Weg`.

### Task 8: Der Weg aus der Rekonstruktion in den Tab

**Files:** Modify `src/spotlab/maps/rekonstruktion.py` (`Ergebnis`, `rekonstruiere`), `src/spotlab/gui/raumeditor/tab.py` (`_setze`, `waehle_raum`, `uebernimm_rekonstruktion`, `_schreibe`); Test `tests/test_maps_rekonstruktion.py`, `tests/test_gui_raumeditor.py`.

**Interfaces:** Produces `Ergebnis.weg: list` mit `(x, y, z_boden)` im Raumrahmen; Hinweis „Weiter mit „Korrigieren…“: Lücken schliessen, Gelände bauen." im Bericht; Tab-Attribut `_weg`.

- [ ] **Step 1: Tests**

```python
# test_maps_rekonstruktion.py (synthetische Karte mit Hoehe)
def test_das_ergebnis_traegt_den_weg_mit_bodenhoehe(tmp_path):
    synthetische_karte_mit_hoehe(tmp_path / "k")
    ergebnis = rk.rekonstruiere(tmp_path / "k")
    assert len(ergebnis.weg) == 17
    unten = [z for x, y, z in ergebnis.weg[:5]]
    oben = [z for x, y, z in ergebnis.weg[9:12]]
    assert max(abs(z) for z in unten) < 0.1 and all(abs(z - 1.0) < 0.15 for z in oben)
    assert any("Korrigieren" in h for h in ergebnis.bericht["hinweise"])

# test_gui_raumeditor.py
def test_der_weg_wird_mit_dem_pauspapier_gespeichert_und_geladen(editor, tmp_path):
    ergebnis = rk.Ergebnis(NEUER_RAUM, [(1.0, 1.0)], {"waende": 0, "tags": 0, "hinweise": []},
                           weg=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.2)])
    editor.uebernimm_rekonstruktion(ergebnis)
    editor._schreibe("wegtest")
    editor.waehle_raum("wegtest")
    assert editor._weg == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.2)]
```

(Fixture `editor` und der Weg zu `_schreibe` wie in den bestehenden Tests dieser Datei; Bericht-Schlüssel, die `uebernimm_rekonstruktion` liest, mitgeben.)

- [ ] **Step 2: Scheitern.** - [ ] **Step 3: Implementieren** wie Spec § 3 (`weg_xyz` nach `ausrichten`, `Ergebnis(raum, pauspapier, bericht, weg_xyz)`; Tab: `_setze(..., punkte=(), weg=())`, `self._weg`, Laden per `lies_weg`, Schreiben mit `weg=self._weg`, Sichten bekommen weiter nur die Punkte). - [ ] **Step 4: Grün.** Commit `feat(maps,gui): der gelaufene Weg kommt mit dem Pauspapier in den Editor`.

### Task 9: Abschluss Etappe 1

- [ ] Ganze Suite und `ruff check src tests` grün; `CLAUDE.md` Umsetzungsstand: „Stufe 14 (07.09.2026): Korrigierer und Gelände — Etappe 1 „Kern"" mit zwei Sätzen. Commit `docs: Stufe 14 Etappe 1 -- Gelaende im Kern`.
