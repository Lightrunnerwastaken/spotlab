# Raumeditor Etappe 1 „Bauen" — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Räume aus Wänden, drehbaren Blöcken und Tags in der GUI bauen, speichern und darin fahren (2D-Sim und 3D-Puppe); der Tab „Übungsraum" wird durch „Raumeditor" ersetzt.

**Architecture:** Ein unveränderliches Modell (`welt/raum.py` v2), reine Bearbeitungsfunktionen und ein Qt-freier Zustandsautomat (`welt/bearbeitung.py`, `gui/raumeditor/steuerung.py`), darüber eine dünne Qt-Schicht (2D-Sicht mit QPainter, Tab mit Werkzeugen, Liste, Eigenschaften). Kollision, Gitter, 3D-Welt und Zeichnung lernen die Drehung nach einem Prinzip: Punkt in den Blockrahmen drehen, dann achsparallel rechnen.

**Tech Stack:** Python 3.11+, Standardbibliothek in `welt/`, numpy nur in `welt/wahrnehmung.py`, PySide6 unter `gui/`, MuJoCo nur über `spotsim.puppe` (matura-spot).

**Spec:** `docs/superpowers/specs/2026-09-06-raumeditor-design.md` (Abschnitte 1, 2, 3, 5, 7, 8, 9.1)

## Global Constraints

- `welt/` importiert nur Standardbibliothek (`raum.py`, `kollision.py`, `bearbeitung.py`); numpy nur in `welt/wahrnehmung.py` (`tests/test_welt_raum.py::test_nur_wahrnehmung_darf_numpy`).
- Kein `bosdyn`, `mujoco`, `spotsim`, `spotlab.backends` unter `src/spotlab/gui/`.
- Farben nur aus `gui/theme.py`.
- Einheiten: Meter, Grad, links positiv.
- Genau eine Datei unter `src/spotlab/` importiert `spotsim`: `backends/mujoco.py`.
- Der Startknopf startet nie selbst; er meldet `start_gewuenscht`, `app.py` startet über den Editor.
- Python-Bezeichner englisch nur bei SDK-Nähe; hier wie im übrigen `welt/`/`gui/` deutsch. Meldungen deutsch, sagen was zu tun ist.
- Editor schreibt Dateien mit `encoding="utf-8", newline="\n"`.
- Jeder Test mit Prozess bekommt `TEST_TIMEOUT_S`; Qt-Tests laufen offscreen über die `qapp`-Fixture.
- Commit-Trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Commit-Meldungen über `-F <datei>` (Backticks in `-m` werden von der Shell ausgeführt).
- Alle Kommandos aus `D:\Users\janis\Documents\Matura\spotlab`, Python `C:\Users\janis\miniconda3\python.exe`, Tests `python -m pytest -q -p no:cacheprovider <datei>`.

---

## Dateiplan

| Datei | Aufgabe |
|---|---|
| `src/spotlab/welt/raum.py` | Modell v2: `Wand`, `Block`, `RaumTag`, `Raum`, `huelle`, Laden (v1+v2), `raum_speichern`, `eigene_raeume`, `raum_pfad` |
| `src/spotlab/welt/kollision.py` | Drehung und Wanddicke in `hindernis_bei`, `sicht_frei` |
| `src/spotlab/welt/wahrnehmung.py` | Drehung und Wanddicke im Abstandsgitter |
| `src/spotlab/welt/bearbeitung.py` | Operationen, Rasten, Fang, Treffer, Griffe, Prüfung, `Verlauf`, `Modus` |
| `src/spotlab/backends/mujoco.py` | `welt_aus_raum` mit Drehung; `PUPPE_FASSUNG = 3` |
| `matura-spot/src/spotsim/puppe.py` | `Quader.yaw`, `FASSUNG = 3` |
| `src/spotlab/gui/raumzeichnung.py` | gemeinsames Zeichnen von Raum, Spur, Anstössen, Spot |
| `src/spotlab/gui/raumplot.py` | benutzt `raumzeichnung`, `huelle` |
| `src/spotlab/gui/raumeditor/steuerung.py` | Qt-freie Steuerung: Werkzeuge, Griffe, Züge, Tasten, Verlauf |
| `src/spotlab/gui/raumeditor/sicht2d.py` | QPainter-Sicht: Zoom/Schwenken, Zeichnen, Ereignisse in Metern |
| `src/spotlab/gui/raumeditor/tab.py` | `RaumeditorView`: Werkzeugleiste, Sicht, Liste, Eigenschaften, Hinweise, Dateien, Startknopf |
| `src/spotlab/gui/raumeditor/__init__.py` | exportiert `RaumeditorView` |
| `src/spotlab/gui/app.py` | `"raumeditor"` statt `"uebungsraum"` |
| `src/spotlab/gui/views/uebungsraum.py` | entfällt |
| `README.md`, `CLAUDE.md`, `docs/ABNAHME.md` | Doku, Regeln, A23 |

---

### Task 1: Raumformat v2 — Modell, Laden (alt und neu), Speichern

**Files:**
- Modify: `src/spotlab/welt/raum.py` (ganz)
- Modify: `tests/test_welt_raum.py`, `tests/test_welt_kollision.py:1-24`, `tests/test_welt_wahrnehmung.py:1-25`, `tests/test_backend_sim.py:549-560`
- Test: `tests/test_welt_raum.py`

**Interfaces:**
- Produces: `Wand(x1, y1, x2, y2)` (iterierbar als 4 Zahlen; `laenge`, `mitte`, `winkel` in Grad), `Block(name, x, y, breite, tiefe, hoehe=0.75, drehung=0.0)` mit `ecken()` (4 Weltpunkte gegen den Uhrzeigersinn ab links-unten im Blockrahmen) und `lokal(px, py)`, `RaumTag(id, x, y, grad, hoehe=0.30)`, `Raum(name, beschreibung, start, waende=(), bloecke=(), tags=(), groesse=None, wand_dicke=0.06, wand_hoehe=1.0)` (Tupel in `waende` werden zu `Wand`), `huelle(raum) -> (x_min, y_min, x_max, y_max)`, `raum_laden(name, workspace=None)`, `raum_speichern(raum, pfad)`, `eigene_raeume(workspace) -> list[str]`, `raum_pfad(workspace, name) -> Path`, Konstanten `WAND_DICKE_M, WAND_HOEHE_M, BLOCK_HOEHE_M, TAG_HOEHE_M, RAND_M, EIGENE_ORDNER`.

- [ ] **Step 1: Tests schreiben**

In `tests/test_welt_raum.py` ergänzen (bestehende Tests bleiben; `Hindernis` gibt es nicht mehr):

```python
from spotlab.welt.raum import (
    Block, Raum, RaumTag, Wand, eigene_raeume, huelle, raum_laden, raum_pfad,
    raum_speichern, vorlagen,
)


def test_alte_hindernisse_werden_zu_bloecken():
    raum = raum_laden("moebliert")
    tisch = next(b for b in raum.bloecke if b.name == "Tisch")
    # rechteck = [2.5, 1.4, 1.2, 0.8]: Mitte = Ecke + halbe Kante, tischhoch, ungedreht
    assert (tisch.x, tisch.y) == (pytest.approx(3.1), pytest.approx(1.8))
    assert (tisch.breite, tisch.tiefe, tisch.hoehe, tisch.drehung) == (1.2, 0.8, 0.75, 0.0)
    assert not hasattr(raum, "hindernisse")


def test_waende_sind_waende_auch_aus_tupeln():
    raum = Raum(name="T", beschreibung="", start=(0, 0, 0), waende=((0, 0, 2, 0),))
    wand = raum.waende[0]
    assert isinstance(wand, Wand)
    assert list(wand) == [0.0, 0.0, 2.0, 0.0]          # entpackbar wie bisher
    assert wand.laenge == pytest.approx(2.0)
    assert wand.mitte == (1.0, 0.0)
    assert wand.winkel == pytest.approx(0.0)


def test_block_ecken_drehen_mit():
    block = Block("K", 1.0, 1.0, 2.0, 1.0, drehung=90.0)
    ecken = block.ecken()
    # 2 m breit entlang der eigenen x-Achse, die jetzt nach +y zeigt
    assert ecken[0] == (pytest.approx(1.5), pytest.approx(0.0))
    assert ecken[2] == (pytest.approx(0.5), pytest.approx(2.0))
    assert block.lokal(1.0, 2.0) == (pytest.approx(1.0), pytest.approx(0.0))


def test_groesse_ist_optional_und_die_huelle_folgt_der_geometrie():
    raum = Raum(name="T", beschreibung="", start=(0.5, 0.5, 0.0),
                waende=((0, 0, 4, 0),), bloecke=(Block("K", 2, 3, 1, 1),))
    assert raum.groesse is None
    assert huelle(raum) == (-0.5, -0.5, 4.5, 4.0)          # Huelle + RAND_M
    mit = raum_laden("leer")
    assert huelle(mit) == (0.0, 0.0, mit.groesse[0], mit.groesse[1])


def test_neue_schreibweise_laedt_bloecke_und_taghoehe(tmp_path):
    (tmp_path / "raeume").mkdir()
    (tmp_path / "raeume" / "neu.toml").write_text(
        '[raum]\nname = "Neu"\nstart = [1.0, 1.0, 0.0]\nwand_dicke = 0.1\n'
        'waende = [[0.0, 0.0, 3.0, 0.0]]\n'
        '[[block]]\nname = "Regal"\nmitte = [2.0, 1.0]\ngroesse = [1.0, 0.4, 1.8]\ndrehung = 30\n'
        '[[tag]]\nid = 7\npose = [2.5, 0.2, 90.0]\nhoehe = 0.5\n',
        encoding="utf-8",
    )
    raum = raum_laden("neu", workspace=tmp_path)
    assert raum.wand_dicke == 0.1 and raum.wand_hoehe == 1.0
    assert raum.bloecke == (Block("Regal", 2.0, 1.0, 1.0, 0.4, 1.8, 30.0),)
    assert raum.tags == (RaumTag(7, 2.5, 0.2, 90.0, 0.5),)
    assert raum.groesse is None


def test_block_ohne_mitte_nennt_das_feld(tmp_path):
    (tmp_path / "raeume").mkdir()
    (tmp_path / "raeume" / "kaputt.toml").write_text(
        '[raum]\nname = "K"\nstart = [1.0, 1.0, 0.0]\n[[block]]\nname = "R"\ngroesse = [1, 1, 1]\n',
        encoding="utf-8",
    )
    with pytest.raises(SpotlabError, match="mitte"):
        raum_laden("kaputt", workspace=tmp_path)


@pytest.mark.parametrize("name", vorlagen())
def test_speichern_und_laden_ist_eine_rundreise(name, tmp_path):
    raum = raum_laden(name)
    pfad = raum_pfad(tmp_path, name)
    raum_speichern(raum, pfad)
    assert pfad == tmp_path / "raeume" / f"{name}.toml"
    wieder = raum_laden(name, workspace=tmp_path)
    assert wieder == raum
    text = pfad.read_text(encoding="utf-8")
    assert "[[block]]" in text or not raum.bloecke
    assert "hindernisse" not in text                      # immer die neue Form


def test_eigene_raeume_listet_den_arbeitsordner(tmp_path):
    assert eigene_raeume(tmp_path) == []
    raum_speichern(raum_laden("leer"), raum_pfad(tmp_path, "mein zimmer"))
    assert eigene_raeume(tmp_path) == ["mein zimmer"]
    assert eigene_raeume(None) == []


def test_speichern_schreibt_lf_und_utf8(tmp_path):
    raum = Raum(name="Ä", beschreibung='sagt "hallo"', start=(0, 0, 0))
    pfad = raum_pfad(tmp_path, "ae")
    raum_speichern(raum, pfad)
    roh = pfad.read_bytes()
    assert b"\r\n" not in roh
    assert raum_laden("ae", workspace=tmp_path).beschreibung == 'sagt "hallo"'
```

In `tests/test_welt_kollision.py` den Kopf ersetzen:

```python
from spotlab.welt.raum import Block, Raum, raum_laden

# Ein 10 x 10 m grosser Kasten mit einer Kiste in der Mitte (5..6, 5..6).
RAUM = Raum(
    name="T", beschreibung="", groesse=(10.0, 10.0), start=(1.0, 1.0, 0.0),
    waende=(
        (0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0),
        (10.0, 10.0, 0.0, 10.0), (0.0, 10.0, 0.0, 0.0),
    ),
    bloecke=(Block("Kiste", 5.5, 5.5, 1.0, 1.0),),
    tags=(),
)
```

In `tests/test_welt_wahrnehmung.py` und `tests/test_backend_sim.py::_uebungsraum` ebenso: `Hindernis("Kiste", (7.0, 4.5, 0.5, 1.0))` wird `Block("Kiste", 7.25, 5.0, 0.5, 1.0)` — Mitte = Ecke + halbe Kante; jedes `Hindernis(name, (x, y, b, h))` wird `Block(name, x + b/2, y + h/2, b, h)`.

- [ ] **Step 2: Tests laufen lassen — rot**

Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_raum.py`
Expected: ImportError (`Block`, `Wand`, `huelle`, … fehlen).

- [ ] **Step 3: `welt/raum.py` neu schreiben**

```python
"""Ein Zimmer als Geometrie: Waende, Bloecke, Tags.

Reine Standardbibliothek. Das ist kein Zufall, sondern der Grund, warum die GUI
dieses Modul importieren darf: es zieht weder Qt noch bosdyn noch numpy herein,
und die Regel "kein spotlab.backends unterhalb von gui/" bleibt unberuehrt.

Einheiten wie in der Schueler-API: Meter und GRAD, links positiv. Wer
`spot.move(turn=90)` kennt, liest eine Raumdatei ohne Umrechnung.

Fassung 2 (06.09.2026): Waende sind Linien mit Dicke und Hoehe je Raum, Bloecke
sind drehbare Kaesten mit Hoehe, Tags haben eine Haengehoehe. Die alte
Schreibweise `hindernisse = [{rechteck=...}]` wird weiter gelesen; gespeichert
wird immer die neue.
"""

import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

from spotlab.errors import SpotlabError

VORLAGEN = Path(__file__).parent / "vorlagen"
EIGENE_ORDNER = "raeume"

# Vorgaben der Geometrie in 3D. Die Vorlagen kennen keine Hoehen -- das sind
# ANNAHMEN: eine Uebungswand von 1 m reicht der Puppe, Bloecke tischhoch, Tags
# auf Kniehoehe (so steht es auch in backends/base.py::richtung).
WAND_DICKE_M = 0.06
WAND_HOEHE_M = 1.0
BLOCK_HOEHE_M = 0.75
TAG_HOEHE_M = 0.30
RAND_M = 0.5           # Rand der Huelle, wenn `groesse` fehlt


@dataclass(frozen=True)
class Wand:
    """Eine Linie; Dicke und Hoehe gelten je Raum."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __iter__(self):
        return iter((self.x1, self.y1, self.x2, self.y2))

    @property
    def laenge(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def mitte(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def winkel(self):
        """Richtung von (x1, y1) nach (x2, y2) in Grad."""
        return math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1))


@dataclass(frozen=True)
class Block:
    """Ein Kasten auf dem Boden: Mitte, Groesse, Drehung um die Hochachse."""

    name: str
    x: float
    y: float
    breite: float        # entlang der eigenen x-Achse
    tiefe: float
    hoehe: float = BLOCK_HOEHE_M
    drehung: float = 0.0  # Grad, links positiv

    def ecken(self):
        """Die vier Ecken im Weltframe, gegen den Uhrzeigersinn ab links-unten."""
        c = math.cos(math.radians(self.drehung))
        s = math.sin(math.radians(self.drehung))
        hb, ht = self.breite / 2, self.tiefe / 2
        return tuple(
            (self.x + lx * c - ly * s, self.y + lx * s + ly * c)
            for lx, ly in ((-hb, -ht), (hb, -ht), (hb, ht), (-hb, ht))
        )

    def lokal(self, px, py):
        """Ein Weltpunkt im Rahmen des Blocks (Mitte = Ursprung, x entlang der Breite)."""
        c = math.cos(math.radians(-self.drehung))
        s = math.sin(math.radians(-self.drehung))
        dx, dy = px - self.x, py - self.y
        return dx * c - dy * s, dx * s + dy * c


@dataclass(frozen=True)
class RaumTag:
    id: int
    x: float
    y: float
    grad: float          # Blickrichtung des Tags
    hoehe: float = TAG_HOEHE_M


@dataclass(frozen=True)
class Raum:
    name: str
    beschreibung: str
    start: tuple         # (x, y, grad)
    waende: tuple = ()   # Wand, ...
    bloecke: tuple = ()  # Block, ...
    tags: tuple = ()     # RaumTag, ...
    groesse: tuple | None = None   # (breite, hoehe) oder None -> Huelle
    wand_dicke: float = WAND_DICKE_M
    wand_hoehe: float = WAND_HOEHE_M

    def __post_init__(self):
        # Tupel aus Tests und alten Aufrufern werden Waende; Listen werden Tupel.
        object.__setattr__(self, "waende", tuple(
            w if isinstance(w, Wand) else Wand(*(float(v) for v in w)) for w in self.waende
        ))
        object.__setattr__(self, "bloecke", tuple(self.bloecke))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "start", tuple(float(v) for v in self.start))
        if self.groesse is not None:
            object.__setattr__(self, "groesse", tuple(float(v) for v in self.groesse))


def huelle(raum):
    """(x_min, y_min, x_max, y_max): die Zeichenflaeche.

    Mit `groesse` das Rechteck ab dem Ursprung wie bisher; ohne die Bounding-Box
    aller Elemente plus RAND_M -- eine rekonstruierte Karte hat keine Groesse.
    """
    if raum.groesse is not None:
        return (0.0, 0.0, raum.groesse[0], raum.groesse[1])
    punkte = [(raum.start[0], raum.start[1])]
    for wand in raum.waende:
        punkte += [(wand.x1, wand.y1), (wand.x2, wand.y2)]
    for block in raum.bloecke:
        punkte += list(block.ecken())
    punkte += [(t.x, t.y) for t in raum.tags]
    xs = [p[0] for p in punkte]
    ys = [p[1] for p in punkte]
    return (min(xs) - RAND_M, min(ys) - RAND_M, max(xs) + RAND_M, max(ys) + RAND_M)


def vorlagen():
    """Die mitgelieferten Raeume, ohne Endung."""
    return sorted(p.stem for p in VORLAGEN.glob("*.toml"))


def eigene_raeume(workspace):
    """Die Raeume unter <arbeitsordner>/raeume, ohne Endung."""
    if not workspace:
        return []
    ordner = Path(workspace) / EIGENE_ORDNER
    if not ordner.is_dir():
        return []
    return sorted(p.stem for p in ordner.glob("*.toml"))


def raum_pfad(workspace, name):
    """Wo ein eigener Raum dieses Namens liegt (oder liegen wird)."""
    return Path(workspace) / EIGENE_ORDNER / f"{name}.toml"


def _pfad(name, workspace):
    if workspace:
        eigen = raum_pfad(workspace, name)
        if eigen.is_file():
            return eigen
    mitgeliefert = VORLAGEN / f"{name}.toml"
    if mitgeliefert.is_file():
        return mitgeliefert
    vorhanden = ", ".join(vorlagen())
    raise SpotlabError(
        f"Den Raum '{name}' gibt es nicht. Vorhanden: {vorhanden}. "
        f"Eigene Raeume liegen unter <arbeitsordner>/raeume/<name>.toml."
    )


def _feld(daten, name, pfad, wo="unter [raum]"):
    if name not in daten:
        raise SpotlabError(f"In {pfad.name} fehlt das Feld '{name}' {wo}.")
    return daten[name]


def _bloecke(daten, roh, pfad):
    bloecke = []
    # Alte Schreibweise: achsparallele Rechtecke, tischhoch.
    for h in daten.get("hindernisse", []):
        x, y, breite, hoehe = (float(v) for v in h["rechteck"])
        bloecke.append(Block(
            name=str(h.get("name", "Hindernis")),
            x=x + breite / 2, y=y + hoehe / 2, breite=breite, tiefe=hoehe,
            hoehe=BLOCK_HOEHE_M, drehung=0.0,
        ))
    for b in roh.get("block", []):
        mitte = _feld(b, "mitte", pfad, "bei einem [[block]]")
        groesse = _feld(b, "groesse", pfad, "bei einem [[block]]")
        bloecke.append(Block(
            name=str(b.get("name", "Block")),
            x=float(mitte[0]), y=float(mitte[1]),
            breite=float(groesse[0]), tiefe=float(groesse[1]),
            hoehe=float(groesse[2]) if len(groesse) > 2 else BLOCK_HOEHE_M,
            drehung=float(b.get("drehung", 0.0)),
        ))
    return tuple(bloecke)


def raum_laden(name, workspace=None):
    """Einen Raum laden. Der Arbeitsordner geht vor den Vorlagen."""
    pfad = _pfad(name, workspace)
    try:
        roh = tomllib.loads(pfad.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as fehler:
        raise SpotlabError(f"{pfad.name} ist kein gueltiges TOML: {fehler}") from fehler

    daten = roh.get("raum")
    if not isinstance(daten, dict):
        raise SpotlabError(f"In {pfad.name} fehlt der Abschnitt [raum].")

    tags = tuple(
        RaumTag(id=int(t["id"]), x=float(t["pose"][0]), y=float(t["pose"][1]),
                grad=float(t["pose"][2]), hoehe=float(t.get("hoehe", TAG_HOEHE_M)))
        for t in roh.get("tag", [])
    )
    groesse = daten.get("groesse")
    return Raum(
        name=str(_feld(daten, "name", pfad)),
        beschreibung=str(daten.get("beschreibung", "")),
        start=tuple(float(w) for w in _feld(daten, "start", pfad)),
        waende=tuple(Wand(*(float(w) for w in wand)) for wand in daten.get("waende", [])),
        bloecke=_bloecke(daten, roh, pfad),
        tags=tags,
        groesse=tuple(float(w) for w in groesse) if groesse is not None else None,
        wand_dicke=float(daten.get("wand_dicke", WAND_DICKE_M)),
        wand_hoehe=float(daten.get("wand_hoehe", WAND_HOEHE_M)),
    )


# ------------------------------------------------------------------ Speichern
#
# tomllib liest nur. Der Schreiber deckt genau das ab, was ein Raum braucht:
# Zeichenketten, Zahlen, Zahlenlisten, Tabellen-Arrays.


def _zahl(wert):
    text = f"{float(wert):.4f}".rstrip("0").rstrip(".")
    if text in ("", "-"):
        text = "0"
    return text if "." in text else text + ".0"


def _text(wert):
    return '"' + str(wert).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _liste(werte):
    return "[" + ", ".join(_zahl(w) for w in werte) + "]"


def raum_speichern(raum, pfad):
    """Den Raum als TOML schreiben -- immer in der neuen Schreibweise."""
    zeilen = [
        "[raum]",
        f"name         = {_text(raum.name)}",
        f"beschreibung = {_text(raum.beschreibung)}",
        f"start        = {_liste(raum.start)}",
    ]
    if raum.groesse is not None:
        zeilen.append(f"groesse      = {_liste(raum.groesse)}")
    zeilen.append(f"wand_dicke   = {_zahl(raum.wand_dicke)}")
    zeilen.append(f"wand_hoehe   = {_zahl(raum.wand_hoehe)}")
    zeilen.append("waende = [")
    for wand in raum.waende:
        zeilen.append(f"    {_liste(wand)},")
    zeilen.append("]")
    for block in raum.bloecke:
        zeilen += [
            "",
            "[[block]]",
            f"name    = {_text(block.name)}",
            f"mitte   = {_liste((block.x, block.y))}",
            f"groesse = {_liste((block.breite, block.tiefe, block.hoehe))}",
            f"drehung = {_zahl(block.drehung)}",
        ]
    for tag in raum.tags:
        zeilen += [
            "",
            "[[tag]]",
            f"id    = {int(tag.id)}",
            f"pose  = {_liste((tag.x, tag.y, tag.grad))}",
            f"hoehe = {_zahl(tag.hoehe)}",
        ]
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Tests laufen lassen — grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_raum.py tests/test_welt_kollision.py tests/test_welt_wahrnehmung.py tests/test_backend_sim.py`
Expected: `test_welt_raum.py` grün. `kollision`/`wahrnehmung`/`sim` scheitern noch an `raum.hindernisse` — das sind Task 2 und 3; die Konstruktion der Räume darf nicht mehr scheitern.

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/welt/raum.py tests/test_welt_raum.py tests/test_welt_kollision.py tests/test_welt_wahrnehmung.py tests/test_backend_sim.py
git commit -F msg.txt   # "feat(welt): Raumformat v2 -- Waende mit Dicke, drehbare Bloecke, Tag-Hoehe, raum_speichern"
```

---

### Task 2: Kollision mit gedrehten Blöcken und Wanddicke

**Files:**
- Modify: `src/spotlab/welt/kollision.py:1-60, 93-105`
- Test: `tests/test_welt_kollision.py`

**Interfaces:**
- Consumes: `Block.lokal`, `Block.ecken`, `Raum.wand_dicke` (Task 1)
- Produces: `hindernis_bei(raum, x, y, radius=ROBOTER_RADIUS_M) -> str | None` (Wand: Abstand < radius + wand_dicke/2; Block: Abstand im Blockrahmen < radius; Name), `frei`, `bewege`, `sicht_frei(raum, a, b)` mit gedrehten Blockkanten, neu `abstand_block(block, px, py) -> float`.

- [ ] **Step 1: Tests schreiben** (an `tests/test_welt_kollision.py` anhängen; den Test `test_zu_nah_an_der_wand_ist_nicht_frei` anpassen)

```python
def test_zu_nah_an_der_wand_ist_nicht_frei():
    # Die Wand hat eine Dicke: der Kreis darf erst ab radius + dicke/2 stehen.
    halb = RAUM.wand_dicke / 2
    assert not frei(RAUM, ROBOTER_RADIUS_M + halb - 0.01, 5.0)
    assert frei(RAUM, ROBOTER_RADIUS_M + halb + 0.01, 5.0)


GEDREHT = Raum(
    name="G", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0.0, 0.0, 10.0, 0.0),),
    # 2 m lang, 0.5 m tief, um 45 Grad gedreht: die Laengsachse zeigt nach Nordost.
    bloecke=(Block("Balken", 5.0, 5.0, 2.0, 0.5, drehung=45.0),),
)


def test_ein_gedrehter_block_trifft_dort_wo_seine_ecke_ist():
    from spotlab.welt.kollision import abstand_block, hindernis_bei

    balken = GEDREHT.bloecke[0]
    # Auf der Laengsachse, 0.9 m von der Mitte: im Block (halbe Laenge 1.0).
    auf_achse = (5.0 + 0.9 * 0.7071, 5.0 + 0.9 * 0.7071)
    assert abstand_block(balken, *auf_achse) == 0.0
    assert hindernis_bei(GEDREHT, *auf_achse, radius=0.05) == "Balken"
    # In der Huelle des ungedrehten Blocks, aber neben dem gedrehten: frei.
    neben = (5.6, 5.0)
    assert abstand_block(balken, *neben) == pytest.approx(0.174, abs=0.01)
    assert hindernis_bei(GEDREHT, *neben, radius=0.05) is None


def test_die_sichtlinie_kennt_die_gedrehten_kanten():
    # Von Suedwest nach Nordost durch den Balken: versperrt.
    assert not sicht_frei(GEDREHT, (4.0, 4.0), (6.0, 6.0))
    # Quer dazu, knapp an der schmalen Seite vorbei: frei.
    assert sicht_frei(GEDREHT, (6.0, 4.0), (6.5, 4.5))
```

- [ ] **Step 2: Rot**

Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_kollision.py`
Expected: FAIL (`raum.hindernisse` AttributeError, `abstand_block` fehlt).

- [ ] **Step 3: `kollision.py` anpassen**

Modul-Docstring: Absatz ergänzen „Bloecke sind gedreht: ein Pruefpunkt wird in den Rahmen des Blocks gedreht (`Block.lokal`), danach ist der Abstand der zum achsparallelen Rechteck. Waende haben eine Dicke je Raum; sie zaehlt zum Radius." Dann:

```python
def abstand_block(block, px, py):
    """Abstand eines Weltpunkts zum (gedrehten) Block; 0 im Block."""
    lx, ly = block.lokal(px, py)
    dx = max(abs(lx) - block.breite / 2, 0.0)
    dy = max(abs(ly) - block.tiefe / 2, 0.0)
    return math.hypot(dx, dy)


def hindernis_bei(raum, x, y, radius=ROBOTER_RADIUS_M):
    """Name dessen, was hier im Weg steht -- oder None."""
    halbe_dicke = raum.wand_dicke / 2
    for wand in raum.waende:
        if _abstand_punkt_strecke(x, y, *wand) < radius + halbe_dicke:
            return "Wand"
    for block in raum.bloecke:
        if abstand_block(block, x, y) < radius:
            return block.name
    return None
```

`_abstand_punkt_rechteck` entfällt. In `sicht_frei`:

```python
    for block in raum.bloecke:
        ecken = block.ecken()
        for erste, zweite in zip(ecken, ecken[1:] + ecken[:1]):
            if _schneiden(a, b, erste, zweite):
                return False
```

- [ ] **Step 4: Grün**

Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_kollision.py`
Expected: alle grün (auch `test_durchgang_ist_breiter_als_der_roboter`, `test_jede_vorlage_hat_eine_freie_startpose`).

- [ ] **Step 5: Commit** — `fix(welt): Kollision kennt gedrehte Bloecke und die Wanddicke`

---

### Task 3: Abstandsgitter mit gedrehten Blöcken und Wanddicke

**Files:**
- Modify: `src/spotlab/welt/wahrnehmung.py:59-76`
- Test: `tests/test_welt_wahrnehmung.py`

**Interfaces:**
- Consumes: `Raum.bloecke`, `Block`, `Raum.wand_dicke`
- Produces: `abstandsgitter(raum, pose)` unverändert in Form; Werte an Wänden um `wand_dicke/2` kleiner (≥ 0), Blöcke gedreht.

- [ ] **Step 1: Tests anhängen**

```python
def _wert_bei(raum, pose, x, y):
    from spotlab.welt.wahrnehmung import GITTER_ZELLE_M, abstandsgitter

    werte, _bekannt, ursprung = abstandsgitter(raum, pose)
    spalte = int(round((x - ursprung[0]) / GITTER_ZELLE_M))
    zeile = int(round((y - ursprung[1]) / GITTER_ZELLE_M))
    return werte[zeile][spalte]


def test_das_gitter_kennt_gedrehte_bloecke():
    raum = Raum(name="G", beschreibung="", start=(5.0, 5.0, 0.0),
                bloecke=(Block("Balken", 5.0, 5.0, 2.0, 0.5, drehung=45.0),))
    pose = (5.0, 5.0, 0.0)
    assert _wert_bei(raum, pose, 5.0 + 0.9 * 0.7071, 5.0 + 0.9 * 0.7071) == pytest.approx(0.0, abs=0.03)
    assert _wert_bei(raum, pose, 5.6, 5.0) == pytest.approx(0.174, abs=0.03)


def test_die_wanddicke_zaehlt_im_gitter():
    raum = Raum(name="W", beschreibung="", start=(5.0, 5.0, 0.0),
                waende=((0.0, 4.0, 10.0, 4.0),), wand_dicke=0.10)
    # 0.30 m vor der Wandlinie bleiben 0.25 m bis zur Wandflaeche.
    assert _wert_bei(raum, (5.0, 5.0, 0.0), 5.0, 4.30) == pytest.approx(0.25, abs=0.03)
```

- [ ] **Step 2: Rot** — Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_wahrnehmung.py` — AttributeError `hindernisse`.

- [ ] **Step 3: `_abstaende` ersetzen**

```python
def _abstaende(raum, xs, ys):
    """Je Zelle der Abstand zum naechsten Hindernis, vektorisiert.

    Waende sind Linien mit Dicke: gemessen wird bis zur Wandflaeche, nie unter
    null. Bloecke sind gedreht: die Zellmitten werden in den Blockrahmen gedreht,
    danach ist es der Abstand zum achsparallelen Rechteck -- dieselbe Rechnung
    wie `kollision.abstand_block`, nur fuer 16384 Punkte auf einmal.
    """
    abstand = np.full(xs.shape, np.inf)
    halbe_dicke = raum.wand_dicke / 2
    for x1, y1, x2, y2 in raum.waende:
        dx, dy = x2 - x1, y2 - y1
        laenge2 = dx * dx + dy * dy
        if laenge2 == 0.0:
            zur_linie = np.hypot(xs - x1, ys - y1)
        else:
            t = np.clip(((xs - x1) * dx + (ys - y1) * dy) / laenge2, 0.0, 1.0)
            zur_linie = np.hypot(xs - (x1 + t * dx), ys - (y1 + t * dy))
        abstand = np.minimum(abstand, np.maximum(zur_linie - halbe_dicke, 0.0))
    for block in raum.bloecke:
        c = math.cos(math.radians(-block.drehung))
        s = math.sin(math.radians(-block.drehung))
        dx, dy = xs - block.x, ys - block.y
        lx = dx * c - dy * s
        ly = dx * s + dy * c
        ddx = np.maximum(np.abs(lx) - block.breite / 2, 0.0)
        ddy = np.maximum(np.abs(ly) - block.tiefe / 2, 0.0)
        abstand = np.minimum(abstand, np.hypot(ddx, ddy))
    return abstand
```

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_wahrnehmung.py tests/test_backend_sim.py tests/test_api_world.py tests/test_workshop_beispiele.py -k "not 3d"`
Expected: grün. Das Beispiel `durchgang_finden` muss die Tür weiter finden (Wanddicke 0.06 macht den Korridor 6 cm schmaler).

- [ ] **Step 5: Commit** — `fix(welt): Abstandsgitter kennt gedrehte Bloecke und die Wanddicke`

---

### Task 4: 3D-Welt mit Drehung — `welt_aus_raum` und `Quader.yaw` (matura-spot)

**Files:**
- Modify (matura-spot): `src/spotsim/puppe.py:48, 72-82, 115-122`; Test: `tests/test_puppe.py`
- Modify: `src/spotlab/backends/mujoco.py:46-54, 91-122`; Test: `tests/test_backend_mujoco.py`, `tests/test_naht_spotsim.py`

**Interfaces:**
- Consumes: `Wand.laenge/mitte/winkel`, `Block`, `Raum.wand_dicke/wand_hoehe`, `RaumTag.hoehe`
- Produces: `spotsim.puppe.Quader(name, x, y, z, hx, hy, hz, yaw=0.0)` (Bogenmass), `spotsim.puppe.FASSUNG = 3`, `spotlab.backends.mujoco.PUPPE_FASSUNG = 3`, `welt_aus_raum(raum, puppe)` mit gedrehten Quadern.

- [ ] **Step 1 (matura-spot): Test in `tests/test_puppe.py`**

```python
@needs_asset
def test_ein_gedrehter_quader_steht_dort_wo_seine_drehung_ihn_hinstellt():
    """Ein 2 x 0.2 m Balken, um 90 Grad gedreht, spannt y statt x auf: die Puppe
    bei (0.8, 0) steht dann frei, ungedreht stuende sie in ihm."""
    import math

    from spotsim.puppe import Quader, SpotPuppe, Welt

    def puppe_mit(yaw):
        welt = Welt(quader=(Quader("balken", 0.0, 0.0, 0.25, 1.0, 0.1, 0.25, yaw=yaw),))
        p = SpotPuppe(welt)
        p.setze(0.8, 0.0, 0.0, HOME)
        return p

    gedreht = puppe_mit(math.pi / 2)
    try:
        assert gedreht.kollisionen() == ()
        q = gedreht.model.body("balken").quat
        assert abs(q[0] - math.cos(math.pi / 4)) < 1e-6 and abs(q[3] - math.sin(math.pi / 4)) < 1e-6
    finally:
        gedreht.close()
    ungedreht = puppe_mit(0.0)
    try:
        assert ungedreht.kollisionen() != ()
    finally:
        ungedreht.close()
```

(Die Fixture `needs_asset` und `HOME` gibt es in `tests/test_puppe.py` schon; `kollisionen()` liefert ein Tupel von Kontaktpaaren.)

- [ ] **Step 2: Rot** — Run (in matura-spot): `python -m pytest -q -p no:cacheprovider tests/test_puppe.py -k gedrehter` — TypeError `yaw`.

- [ ] **Step 3 (matura-spot): `Quader.yaw`, Quaternion, Fassung**

```python
FASSUNG = 3      # 3: Quader mit yaw (Raumeditor); 2: weltfestes Gitter

@dataclass(frozen=True)
class Quader:
    """Ein Kasten in der Welt, um die Hochachse gedreht. Halbe Kantenlaengen wie MuJoCo."""

    name: str
    x: float
    y: float
    z: float
    hx: float
    hy: float
    hz: float
    yaw: float = 0.0     # Bogenmass, links positiv
```

In `bau_modell` nach `b.pos = [q.x, q.y, q.z]`: `b.quat = list(_quat_yaw(q.yaw))`.

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_puppe.py tests/test_puppe_wahrnehmung.py`
- [ ] **Step 5: Commit (matura-spot, Branch `puppe-yaw` ab main)** — `feat(puppe): Quader mit yaw -- gedrehte Waende und Bloecke aus dem Raumeditor (FASSUNG 3)`

- [ ] **Step 6 (spotlab): Test in `tests/test_backend_mujoco.py`** (neben den bestehenden, mit derselben `skipif`-Logik für `spotsim`)

```python
def test_welt_aus_raum_dreht_waende_und_bloecke():
    import math

    from spotlab.backends.mujoco import welt_aus_raum
    from spotlab.welt.raum import Block, Raum, RaumTag
    import spotsim.puppe as puppe

    raum = Raum(name="G", beschreibung="", start=(0, 0, 0),
                waende=((1.0, 1.0, 1.0, 4.0),), wand_dicke=0.1, wand_hoehe=2.0,
                bloecke=(Block("Regal", 3.0, 2.0, 1.0, 0.4, 1.8, drehung=30.0),),
                tags=(RaumTag(5, 2.0, 2.0, 0.0, hoehe=0.5),))
    welt = welt_aus_raum(raum, puppe)
    wand = welt.quader[0]
    assert (wand.x, wand.y, wand.z) == (1.0, 2.5, 1.0)
    assert (wand.hx, wand.hy, wand.hz) == (pytest.approx(1.5), 0.05, 1.0)
    assert wand.yaw == pytest.approx(math.pi / 2)
    regal = welt.quader[1]
    assert regal.name == "Regal" and regal.yaw == pytest.approx(math.radians(30))
    assert (regal.hx, regal.hy, regal.hz) == (0.5, 0.2, 0.9)
    assert welt.tags[0].z == 0.5
```

- [ ] **Step 7: Rot** — TypeError/AttributeError (`hindernisse`, alte Konstanten).

- [ ] **Step 8: `welt_aus_raum` ersetzen, Konstanten streichen**

`PUPPE_FASSUNG = 3      # 3: Quader mit yaw`. Die Konstanten `WAND_HOEHE_M`, `WAND_DICKE_M`, `HINDERNIS_HOEHE_M`, `TAG_HOEHE_M` und ihren Kommentar entfernen (die Werte stehen im Raum; `grep -rn "WAND_HOEHE_M\|TAG_HOEHE_M" src tests` muss danach leer sein — Treffer in `film_aus_lauf` o. ä. auf `raum.wand_hoehe` umstellen).

```python
def welt_aus_raum(raum, puppe):
    """Ein `Raum` (Waende, Bloecke, Tags) als `puppe.Welt` (gedrehte Quader, Tags).

    Eine Wand wird ein Kasten mit ihrer Laenge, der Dicke und Hoehe des Raums
    und ihrer Richtung; ein Block ein Kasten mit seiner Drehung; ein Tag eine
    Marke auf seiner Haengehoehe (Grad -> Bogenmass, wie ueberall an der Naht
    zu `welt/`).
    """
    if raum is None:
        return puppe.Welt()
    quader = []
    for i, wand in enumerate(raum.waende):
        if wand.laenge <= 0:
            continue
        mx, my = wand.mitte
        quader.append(puppe.Quader(
            f"wand_{i}", mx, my, raum.wand_hoehe / 2,
            wand.laenge / 2, raum.wand_dicke / 2, raum.wand_hoehe / 2,
            yaw=math.radians(wand.winkel),
        ))
    for b in raum.bloecke:
        quader.append(puppe.Quader(
            b.name, b.x, b.y, b.hoehe / 2, b.breite / 2, b.tiefe / 2, b.hoehe / 2,
            yaw=math.radians(b.drehung),
        ))
    tags = tuple(
        puppe.TagMarke(t.id, t.x, t.y, t.hoehe, math.radians(t.grad)) for t in raum.tags
    )
    return puppe.Welt(quader=tuple(quader), tags=tags)
```

- [ ] **Step 9: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_backend_mujoco.py tests/test_naht_spotsim.py tests/test_film.py tests/test_wiedergabe.py` (matura-spot muss auf `puppe-yaw` stehen).
- [ ] **Step 10: Commit** — `feat(mujoco): welt_aus_raum dreht Waende und Bloecke, Hoehen aus dem Raum (PUPPE_FASSUNG 3)`

---

### Task 5: Gemeinsames Zeichnen — `gui/raumzeichnung.py`, `raumplot.py` benutzt es

**Files:**
- Create: `src/spotlab/gui/raumzeichnung.py`
- Modify: `src/spotlab/gui/raumplot.py:90-101, 120-177`
- Test: `tests/test_gui_raumplot.py`, neu `tests/test_gui_raumzeichnung.py`

**Interfaces:**
- Consumes: `Wand`, `Block.ecken`, `RaumTag`, `huelle`, `ROBOTER_RADIUS_M`, `Palette`
- Produces: `zeichne_raum(maler, raum, meter_zu_schirm, skala, palette, auswahl=frozenset())`, `zeichne_spur(maler, spur, meter_zu_schirm, palette)`, `zeichne_anstoesse(maler, punkte, meter_zu_schirm, palette)`, `zeichne_spot(maler, px, py, blick_grad, skala, palette, gewaehlt=False)`, `wand_polygon(wand, dicke) -> [(x, y) x4]`. `RaumPlot._massstab` rechnet über `huelle`.

- [ ] **Step 1: Tests**

`tests/test_gui_raumzeichnung.py`:

```python
"""Das gemeinsame Zeichnen von Raeumen -- fuer Raumeditor und Uebungsfenster."""
import ast
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QImage, QPainter  # noqa: E402

from spotlab.gui.raumzeichnung import wand_polygon, zeichne_raum, zeichne_spot, zeichne_spur  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import Block, Raum, RaumTag, Wand  # noqa: E402


def test_das_wandpolygon_hat_die_dicke():
    ecken = wand_polygon(Wand(0.0, 0.0, 4.0, 0.0), 0.2)
    ys = sorted(round(y, 6) for _x, y in ecken)
    assert ys == [-0.1, -0.1, 0.1, 0.1]
    assert sorted(round(x, 6) for x, _y in ecken) == [0.0, 0.0, 4.0, 4.0]


def test_zeichnen_mit_allem_und_auswahl_stuerzt_nicht(qapp):
    raum = Raum(name="T", beschreibung="", start=(1.0, 1.0, 30.0),
                waende=((0, 0, 5, 0), (5, 0, 5, 4)),
                bloecke=(Block("Regal", 2.0, 2.0, 1.0, 0.4, drehung=30.0),),
                tags=(RaumTag(1, 4.5, 2.0, 180.0),))
    bild = QImage(400, 300, QImage.Format_RGB32)
    bild.fill(0)
    maler = QPainter(bild)
    skala = 50.0
    zeichne_raum(maler, raum, lambda x, y: (20 + x * skala, 280 - y * skala), skala, DUNKEL,
                 auswahl=frozenset({("block", 0), ("wand", 1)}))
    zeichne_spur(maler, [(1, 1), (2, 1.5)], lambda x, y: (20 + x * skala, 280 - y * skala), DUNKEL)
    zeichne_spot(maler, 70.0, 230.0, 30.0, skala, DUNKEL)
    maler.end()
    assert bild.pixel(70 + 13, 230) != bild.pixel(1, 1)      # der Kreis ist gezeichnet


def test_kein_farbliteral():
    quelle = Path("src/spotlab/gui/raumzeichnung.py").read_text(encoding="utf-8")
    for knoten in ast.walk(ast.parse(quelle)):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            assert not knoten.value.startswith("#"), knoten.value
```

In `tests/test_gui_raumplot.py` ergänzen:

```python
def test_ohne_groesse_zeichnet_die_huelle(qapp):
    from spotlab.gui.raumplot import RaumPlot
    from spotlab.welt.raum import Raum

    plot = RaumPlot(DUNKEL)
    plot.resize(400, 300)
    plot.setze_raum(Raum(name="T", beschreibung="", start=(0, 0, 0), waende=((0, 0, 4, 0),)))
    x, y = plot.schirm_zu_meter(*plot.meter_zu_schirm(2.0, 0.0))
    assert (x, y) == (pytest.approx(2.0), pytest.approx(0.0, abs=1e-6))
```

- [ ] **Step 2: Rot** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumzeichnung.py tests/test_gui_raumplot.py`

- [ ] **Step 3: `raumzeichnung.py` schreiben**

```python
"""Raeume zeichnen -- einmal, fuer Raumeditor und Uebungsfenster.

QPainter wie ueberall. Farben nur aus dem Theme. Die Umrechnung Meter -> Pixel
bringt der Aufrufer mit (`meter_zu_schirm`), weil Editor und Uebungsfenster
verschieden zoomen; `skala` sind Pixel je Meter fuer Radien und Dicken.
"""

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF

from spotlab.welt.kollision import ROBOTER_RADIUS_M

TAG_KANTE_M = 0.15
PFEIL_M = 0.4


def wand_polygon(wand, dicke):
    """Die vier Ecken des Wandbalkens (Weltkoordinaten)."""
    x1, y1, x2, y2 = wand
    laenge = math.hypot(x2 - x1, y2 - y1)
    if laenge == 0.0:
        nx, ny = 0.0, dicke / 2
    else:
        nx, ny = -(y2 - y1) / laenge * dicke / 2, (x2 - x1) / laenge * dicke / 2
    return [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]


def _polygon(punkte, meter_zu_schirm):
    return QPolygonF([QPointF(*meter_zu_schirm(x, y)) for x, y in punkte])


def zeichne_raum(maler, raum, meter_zu_schirm, skala, palette, auswahl=frozenset()):
    """Waende, Bloecke, Tags. Die Auswahl in Akzentfarbe."""
    for i, block in enumerate(raum.bloecke):
        gewaehlt = ("block", i) in auswahl
        maler.setPen(QPen(QColor(palette.akzent if gewaehlt else palette.rand), 2))
        maler.setBrush(QBrush(QColor(palette.flaeche)))
        maler.drawPolygon(_polygon(block.ecken(), meter_zu_schirm))
        px, py = meter_zu_schirm(block.x, block.y)
        maler.setPen(QColor(palette.gedaempft))
        maler.drawText(int(px) + 4, int(py) - 4, block.name)

    for i, wand in enumerate(raum.waende):
        gewaehlt = ("wand", i) in auswahl
        farbe = QColor(palette.akzent if gewaehlt else palette.text)
        maler.setPen(QPen(farbe, 1))
        maler.setBrush(QBrush(farbe))
        dicke = max(raum.wand_dicke, 2.0 / max(skala, 1e-6))
        maler.drawPolygon(_polygon(wand_polygon(wand, dicke), meter_zu_schirm))

    maler.setBrush(Qt.NoBrush)
    for i, tag in enumerate(raum.tags):
        gewaehlt = ("tag", i) in auswahl
        maler.setPen(QPen(QColor(palette.akzent if gewaehlt else palette.zahl), 2))
        px, py = meter_zu_schirm(tag.x, tag.y)
        halb = max(6.0, TAG_KANTE_M / 2 * skala)
        maler.drawRect(int(px - halb), int(py - halb), int(2 * halb), int(2 * halb))
        sx, sy = meter_zu_schirm(tag.x + PFEIL_M * math.cos(math.radians(tag.grad)),
                                 tag.y + PFEIL_M * math.sin(math.radians(tag.grad)))
        maler.drawLine(QPointF(px, py), QPointF(sx, sy))
        maler.drawText(int(px + halb) + 3, int(py) + 4, str(tag.id))


def zeichne_spur(maler, spur, meter_zu_schirm, palette):
    if len(spur) < 2:
        return
    maler.setPen(QPen(QColor(palette.akzent), 2, Qt.DotLine))
    for erster, zweiter in zip(spur, spur[1:]):
        maler.drawLine(QPointF(*meter_zu_schirm(*erster)), QPointF(*meter_zu_schirm(*zweiter)))


def zeichne_anstoesse(maler, punkte, meter_zu_schirm, palette):
    maler.setPen(QPen(QColor(palette.gefahr), 2))
    for x, y in punkte:
        px, py = meter_zu_schirm(x, y)
        maler.drawLine(int(px) - 5, int(py) - 5, int(px) + 5, int(py) + 5)
        maler.drawLine(int(px) - 5, int(py) + 5, int(px) + 5, int(py) - 5)


def zeichne_spot(maler, px, py, blick_grad, skala, palette, gewaehlt=False):
    """Spot als Kreis mit Blickstrich -- `px, py` schon in Pixeln."""
    r = max(4.0, ROBOTER_RADIUS_M * skala)
    maler.setPen(QPen(QColor(palette.akzent if gewaehlt else palette.funktion), 2))
    maler.setBrush(Qt.NoBrush)
    maler.drawEllipse(QPointF(px, py), r, r)
    maler.drawLine(QPointF(px, py), QPointF(
        px + r * math.cos(math.radians(blick_grad)),
        py - r * math.sin(math.radians(blick_grad)),
    ))
```

- [ ] **Step 4: `raumplot.py` umstellen**

`_massstab`: statt `breite, hoehe = self._raum.groesse`:

```python
        x0, y0, x1, y1 = huelle(self._raum)
        breite, hoehe = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        nutzbar_x = max(self.width() - 2 * RAND, 1)
        nutzbar_y = max(self.height() - 2 * RAND, 1)
        skala = min(nutzbar_x / breite, nutzbar_y / hoehe)
        links = (self.width() - breite * skala) / 2 - x0 * skala
        unten = (self.height() + hoehe * skala) / 2 + y0 * skala
        return skala, links, unten
```

`paintEvent`: die Schleifen über `hindernisse`, `waende`, `spur`, `tags`, `anstoesse` und den Spot-Kreis ersetzen durch `zeichne_raum(maler, self._raum, self.meter_zu_schirm, skala, self._p)`, `zeichne_spur(maler, self._spur, self.meter_zu_schirm, self._p)`, `zeichne_anstoesse(maler, self._anstoesse, self.meter_zu_schirm, self._p)`, `zeichne_spot(maler, px, py, blick, skala, self._p)`. Import `from spotlab.welt.raum import huelle`; `SPOT_R_M` und der Import aus `kollision` entfallen aus `raumplot.py`.

- [ ] **Step 5: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumzeichnung.py tests/test_gui_raumplot.py tests/test_gui_uebungsfenster.py tests/test_gui_uebungsraum.py`
- [ ] **Step 6: Commit** — `refactor(gui): Raeume zeichnet raumzeichnung.py -- Wanddicke, gedrehte Bloecke, Huelle`

---

### Task 6: `welt/bearbeitung.py` — Operationen auf dem Raum

**Files:**
- Create: `src/spotlab/welt/bearbeitung.py`
- Test: `tests/test_welt_bearbeitung.py`

**Interfaces:**
- Consumes: `Wand`, `Block`, `RaumTag`, `Raum`, `BLOCK_HOEHE_M`, `kollision.hindernis_bei`, `kollision.abstand_block`
- Produces: Schlüssel `("wand", i) | ("block", i) | ("tag", i) | ("start",) | ("raum",)`; `element(raum, s)`, `lage(raum, s) -> (x, y)`, `mitte(raum, auswahl)`, `verschiebe`, `drehe`, `skaliere`, `dupliziere`, `loesche`, `neue_wand`, `neuer_block`, `neuer_tag`, `setze_start`, `setze_feld`, `FELDER`, Konstanten `RASTER_M=0.05, RASTER_GRAD=5.0, FANG_M=0.10, MINDESTKANTE_M=0.05, GRIFF_RADIUS_M=0.15, VERSATZ_KOPIE_M=0.5, START=("start",), RAUM=("raum",)`.

- [ ] **Step 1: Tests** (`tests/test_welt_bearbeitung.py`)

```python
import pytest

from spotlab.welt import bearbeitung as b
from spotlab.welt.raum import Block, Raum, RaumTag

RAUM = Raum(
    name="T", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 4, 0), (4, 0, 4, 3)),
    bloecke=(Block("Kiste", 2.0, 2.0, 1.0, 0.5),),
    tags=(RaumTag(1, 3.5, 1.5, 180.0),),
)


def test_lage_und_mitte():
    assert b.lage(RAUM, ("wand", 0)) == (2.0, 0.0)
    assert b.lage(RAUM, ("block", 0)) == (2.0, 2.0)
    assert b.lage(RAUM, ("tag", 0)) == (3.5, 1.5)
    assert b.lage(RAUM, ("start",)) == (1.0, 1.0)
    assert b.mitte(RAUM, frozenset({("wand", 0), ("block", 0)})) == (2.0, 1.0)


def test_verschieben_trifft_nur_die_auswahl():
    neu = b.verschiebe(RAUM, frozenset({("block", 0), ("start",)}), 1.0, -0.5)
    assert (neu.bloecke[0].x, neu.bloecke[0].y) == (3.0, 1.5)
    assert neu.start == (2.0, 0.5, 0.0)
    assert neu.waende == RAUM.waende and neu.tags == RAUM.tags


def test_eine_wand_dreht_um_ihre_mitte():
    neu = b.drehe(RAUM, frozenset({("wand", 0)}), 90.0)
    wand = neu.waende[0]
    assert (wand.x1, wand.y1) == (pytest.approx(2.0), pytest.approx(-2.0))
    assert (wand.x2, wand.y2) == (pytest.approx(2.0), pytest.approx(2.0))


def test_ein_block_dreht_um_einen_fremden_punkt_und_sich_selbst():
    neu = b.drehe(RAUM, frozenset({("block", 0)}), 90.0, um=(0.0, 0.0))
    kiste = neu.bloecke[0]
    assert (kiste.x, kiste.y) == (pytest.approx(-2.0), pytest.approx(2.0))
    assert kiste.drehung == 90.0


def test_tag_und_start_drehen_lage_und_blick():
    neu = b.drehe(RAUM, frozenset({("tag", 0), ("start",)}), 180.0, um=(2.0, 1.0))
    assert neu.tags[0].grad == pytest.approx(0.0)
    assert (neu.tags[0].x, neu.tags[0].y) == (pytest.approx(0.5), pytest.approx(0.5))
    assert neu.start[2] == pytest.approx(180.0)


def test_skalieren_mit_achse():
    neu = b.skaliere(RAUM, frozenset({("block", 0)}), 2.0, 1.0, 3.0, um=(2.0, 2.0))
    kiste = neu.bloecke[0]
    assert (kiste.breite, kiste.tiefe, kiste.hoehe) == (2.0, 0.5, 2.25)
    neu = b.skaliere(RAUM, frozenset({("wand", 0)}), 0.5, 0.5, 1.0, um=(0.0, 0.0))
    assert list(neu.waende[0]) == [0.0, 0.0, 2.0, 0.0]


def test_skalieren_haelt_die_mindestkante():
    neu = b.skaliere(RAUM, frozenset({("block", 0)}), 0.001, 0.001, 0.001)
    kiste = neu.bloecke[0]
    assert kiste.breite == kiste.tiefe == kiste.hoehe == b.MINDESTKANTE_M


def test_duplizieren_haengt_kopien_an_und_waehlt_sie():
    neu, auswahl = b.dupliziere(RAUM, frozenset({("block", 0), ("wand", 1)}))
    assert len(neu.bloecke) == 2 and len(neu.waende) == 3
    assert auswahl == frozenset({("block", 1), ("wand", 2)})
    assert (neu.bloecke[1].x, neu.bloecke[1].y) == (2.5, 2.5)
    assert neu.bloecke[1].name == "Kiste Kopie"
    assert list(neu.waende[2]) == [4.5, 0.5, 4.5, 3.5]


def test_loeschen_entfernt_und_leert_die_auswahl():
    neu, auswahl = b.loesche(RAUM, frozenset({("wand", 0), ("tag", 0), ("start",)}))
    assert len(neu.waende) == 1 and list(neu.waende[0]) == [4, 0, 4, 3]
    assert neu.tags == () and neu.start == RAUM.start        # der Start bleibt
    assert auswahl == frozenset()


def test_neue_elemente_bekommen_freie_namen_und_nummern():
    neu, s = b.neue_wand(RAUM, 0, 3, 4, 3)
    assert s == ("wand", 2) and list(neu.waende[2]) == [0, 3, 4, 3]
    neu, s = b.neuer_block(neu, 1.0, 1.0, 0.5, 0.5)
    assert s == ("block", 1) and neu.bloecke[1].name == "Block 1"
    assert neu.bloecke[1].hoehe == 0.75
    neu, s = b.neuer_tag(neu, 0.5, 0.5)
    assert s == ("tag", 1) and neu.tags[1].id == 2                # 1 ist belegt
    neu = b.setze_start(neu, 3.0, 2.0, 45.0)
    assert neu.start == (3.0, 2.0, 45.0)


def test_setze_feld_je_art():
    neu = b.setze_feld(RAUM, ("block", 0), "drehung", 30.0)
    assert neu.bloecke[0].drehung == 30.0
    neu = b.setze_feld(neu, ("block", 0), "name", "Regal")
    assert neu.bloecke[0].name == "Regal"
    neu = b.setze_feld(neu, ("wand", 0), "x2", 5.0)
    assert neu.waende[0].x2 == 5.0
    neu = b.setze_feld(neu, ("tag", 0), "hoehe", 0.5)
    assert neu.tags[0].hoehe == 0.5
    neu = b.setze_feld(neu, ("start",), "grad", 90.0)
    assert neu.start[2] == 90.0
    neu = b.setze_feld(neu, ("raum",), "wand_dicke", 0.1)
    assert neu.wand_dicke == 0.1
    assert b.setze_feld(neu, ("block", 0), "breite", 0.0).bloecke[0].breite == b.MINDESTKANTE_M
    with pytest.raises(ValueError):
        b.setze_feld(neu, ("block", 0), "farbe", 1)
    assert b.FELDER["block"] == ("name", "x", "y", "breite", "tiefe", "hoehe", "drehung")
```

- [ ] **Step 2: Rot** — ModuleNotFoundError.

- [ ] **Step 3: `bearbeitung.py` (erster Teil)**

```python
"""Einen Raum bearbeiten -- reine Funktionen, ohne Qt.

Der `Raum` ist unveraenderlich; jede Operation gibt einen neuen zurueck. Damit
ist Rueckgaengig eine Liste von Schnappschuessen (`Verlauf`), und die Griffe
der 2D-Sicht, die Blender-Tasten (`Modus`) und die Zahlenfelder rufen dieselben
Funktionen. Alles hier ist ohne Fenster testbar -- und Standardbibliothek, wie
der Rest von `welt/`.

Ein Element wird ueber einen Schluessel angesprochen:
    ("wand", i)  ("block", i)  ("tag", i)  ("start",)  ("raum",)
Eine Auswahl ist ein frozenset solcher Schluessel. Indizes gelten fuer den Raum,
aus dem sie stammen: `loesche` gibt deshalb die leere Auswahl zurueck.
"""

import math
from dataclasses import replace

from spotlab.welt.kollision import abstand_block, hindernis_bei
from spotlab.welt.raum import BLOCK_HOEHE_M, Block, RaumTag, Wand

RASTER_M = 0.05
RASTER_GRAD = 5.0
FANG_M = 0.10            # Wandenden fangen sich an anderen Wandenden
MINDESTKANTE_M = 0.05
GRIFF_RADIUS_M = 0.15    # Treffer fuer Tag und Start
VERSATZ_KOPIE_M = 0.5
START = ("start",)
RAUM = ("raum",)

FELDER = {
    "wand": ("x1", "y1", "x2", "y2"),
    "block": ("name", "x", "y", "breite", "tiefe", "hoehe", "drehung"),
    "tag": ("id", "x", "y", "grad", "hoehe"),
    "start": ("x", "y", "grad"),
    "raum": ("name", "beschreibung", "wand_dicke", "wand_hoehe"),
}


def raste(wert, raster=RASTER_M):
    return round(wert / raster) * raster


def _drehe_punkt(x, y, um, grad):
    c, s = math.cos(math.radians(grad)), math.sin(math.radians(grad))
    dx, dy = x - um[0], y - um[1]
    return um[0] + dx * c - dy * s, um[1] + dx * s + dy * c


# ------------------------------------------------------------- Zugriff


def element(raum, schluessel):
    art = schluessel[0]
    if art == "wand":
        return raum.waende[schluessel[1]]
    if art == "block":
        return raum.bloecke[schluessel[1]]
    if art == "tag":
        return raum.tags[schluessel[1]]
    if art == "start":
        return raum.start
    return raum


def lage(raum, schluessel):
    e = element(raum, schluessel)
    art = schluessel[0]
    if art == "wand":
        return e.mitte
    if art in ("block", "tag"):
        return (e.x, e.y)
    if art == "start":
        return (e[0], e[1])
    return (0.0, 0.0)


def mitte(raum, auswahl):
    """Mitte der Auswahl -- Drehpunkt fuer Drehen und Skalieren."""
    if not auswahl:
        return (raum.start[0], raum.start[1])
    lagen = [lage(raum, s) for s in sorted(auswahl)]
    return (sum(p[0] for p in lagen) / len(lagen), sum(p[1] for p in lagen) / len(lagen))


def _ersetze(raum, schluessel, neu):
    art = schluessel[0]
    if art == "wand":
        waende = list(raum.waende)
        waende[schluessel[1]] = neu
        return replace(raum, waende=tuple(waende))
    if art == "block":
        bloecke = list(raum.bloecke)
        bloecke[schluessel[1]] = neu
        return replace(raum, bloecke=tuple(bloecke))
    if art == "tag":
        tags = list(raum.tags)
        tags[schluessel[1]] = neu
        return replace(raum, tags=tuple(tags))
    if art == "start":
        return replace(raum, start=tuple(neu))
    return neu


def _kante(wert):
    return max(float(wert), MINDESTKANTE_M)


# ---------------------------------------------------------- Operationen


def verschiebe(raum, auswahl, dx, dy):
    for s in auswahl:
        e = element(raum, s)
        if s[0] == "wand":
            neu = Wand(e.x1 + dx, e.y1 + dy, e.x2 + dx, e.y2 + dy)
        elif s[0] in ("block", "tag"):
            neu = replace(e, x=e.x + dx, y=e.y + dy)
        elif s[0] == "start":
            neu = (e[0] + dx, e[1] + dy, e[2])
        else:
            continue
        raum = _ersetze(raum, s, neu)
    return raum


def drehe(raum, auswahl, grad, um=None):
    """Um `um` (Vorgabe: Mitte der Auswahl); Waende drehen ihre Enden, Bloecke,
    Tags und Start ausserdem ihre eigene Richtung."""
    um = um if um is not None else mitte(raum, auswahl)
    for s in auswahl:
        e = element(raum, s)
        if s[0] == "wand":
            a = _drehe_punkt(e.x1, e.y1, um, grad)
            z = _drehe_punkt(e.x2, e.y2, um, grad)
            neu = Wand(a[0], a[1], z[0], z[1])
        elif s[0] == "block":
            x, y = _drehe_punkt(e.x, e.y, um, grad)
            neu = replace(e, x=x, y=y, drehung=(e.drehung + grad) % 360.0)
        elif s[0] == "tag":
            x, y = _drehe_punkt(e.x, e.y, um, grad)
            neu = replace(e, x=x, y=y, grad=(e.grad + grad) % 360.0)
        elif s[0] == "start":
            x, y = _drehe_punkt(e[0], e[1], um, grad)
            neu = (x, y, (e[2] + grad) % 360.0)
        else:
            continue
        raum = _ersetze(raum, s, neu)
    return raum


def skaliere(raum, auswahl, fx, fy, fz=1.0, um=None):
    """Lagen um `um` strecken; Bloecke ausserdem in Breite (fx), Tiefe (fy) und Hoehe (fz)."""
    um = um if um is not None else mitte(raum, auswahl)

    def p(x, y):
        return um[0] + (x - um[0]) * fx, um[1] + (y - um[1]) * fy

    for s in auswahl:
        e = element(raum, s)
        if s[0] == "wand":
            a, z = p(e.x1, e.y1), p(e.x2, e.y2)
            neu = Wand(a[0], a[1], z[0], z[1])
        elif s[0] == "block":
            x, y = p(e.x, e.y)
            neu = replace(e, x=x, y=y, breite=_kante(e.breite * fx),
                          tiefe=_kante(e.tiefe * fy), hoehe=_kante(e.hoehe * fz))
        elif s[0] == "tag":
            x, y = p(e.x, e.y)
            neu = replace(e, x=x, y=y)
        elif s[0] == "start":
            x, y = p(e[0], e[1])
            neu = (x, y, e[2])
        else:
            continue
        raum = _ersetze(raum, s, neu)
    return raum


def _freie_nummer(belegt):
    belegt = set(belegt)
    n = 1
    while n in belegt:
        n += 1
    return n


def dupliziere(raum, auswahl):
    """(Raum, neue Auswahl): Kopien VERSATZ_KOPIE_M nach rechts oben, angehaengt."""
    d = VERSATZ_KOPIE_M
    waende, bloecke, tags = list(raum.waende), list(raum.bloecke), list(raum.tags)
    neue = set()
    for s in sorted(auswahl):
        e = element(raum, s)
        if s[0] == "wand":
            waende.append(Wand(e.x1 + d, e.y1 + d, e.x2 + d, e.y2 + d))
            neue.add(("wand", len(waende) - 1))
        elif s[0] == "block":
            bloecke.append(replace(e, x=e.x + d, y=e.y + d, name=f"{e.name} Kopie"))
            neue.add(("block", len(bloecke) - 1))
        elif s[0] == "tag":
            tags.append(replace(e, x=e.x + d, y=e.y + d, id=_freie_nummer(t.id for t in tags)))
            neue.add(("tag", len(tags) - 1))
    return (
        replace(raum, waende=tuple(waende), bloecke=tuple(bloecke), tags=tuple(tags)),
        frozenset(neue),
    )


def loesche(raum, auswahl):
    """(Raum, leere Auswahl). Der Start bleibt immer."""
    weg = {s for s in auswahl if s[0] in ("wand", "block", "tag")}
    return replace(
        raum,
        waende=tuple(w for i, w in enumerate(raum.waende) if ("wand", i) not in weg),
        bloecke=tuple(b for i, b in enumerate(raum.bloecke) if ("block", i) not in weg),
        tags=tuple(t for i, t in enumerate(raum.tags) if ("tag", i) not in weg),
    ), frozenset()


def neue_wand(raum, x1, y1, x2, y2):
    waende = raum.waende + (Wand(float(x1), float(y1), float(x2), float(y2)),)
    return replace(raum, waende=waende), ("wand", len(waende) - 1)


def neuer_block(raum, x, y, breite, tiefe, hoehe=BLOCK_HOEHE_M, name=None):
    if name is None:
        nummern = set()
        for vorhanden in raum.bloecke:
            teile = vorhanden.name.split()
            if len(teile) == 2 and teile[0] == "Block" and teile[1].isdigit():
                nummern.add(int(teile[1]))
        name = f"Block {_freie_nummer(nummern)}"
    block = Block(name, float(x), float(y), _kante(breite), _kante(tiefe), _kante(hoehe))
    bloecke = raum.bloecke + (block,)
    return replace(raum, bloecke=bloecke), ("block", len(bloecke) - 1)


def neuer_tag(raum, x, y, grad=0.0):
    tag = RaumTag(_freie_nummer(t.id for t in raum.tags), float(x), float(y), float(grad))
    tags = raum.tags + (tag,)
    return replace(raum, tags=tags), ("tag", len(tags) - 1)


def setze_start(raum, x, y, grad):
    return replace(raum, start=(float(x), float(y), float(grad)))


def setze_feld(raum, schluessel, feld, wert):
    """Ein Zahlen- oder Textfeld setzen -- der Weg der Eigenschaften-Felder."""
    art = schluessel[0]
    if feld not in FELDER.get(art, ()):
        raise ValueError(f"Ein Element der Art '{art}' hat kein Feld '{feld}'.")
    e = element(raum, schluessel)
    if art == "start":
        werte = {"x": e[0], "y": e[1], "grad": e[2]}
        werte[feld] = float(wert)
        return replace(raum, start=(werte["x"], werte["y"], werte["grad"] % 360.0))
    if feld in ("breite", "tiefe", "hoehe", "wand_dicke", "wand_hoehe"):
        wert = _kante(wert)
    elif feld in ("name", "beschreibung"):
        wert = str(wert)
    elif feld == "id":
        wert = int(wert)
    elif feld in ("drehung", "grad"):
        wert = float(wert) % 360.0
    else:
        wert = float(wert)
    return _ersetze(raum, schluessel, replace(e, **{feld: wert}))
```

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_bearbeitung.py tests/test_welt_raum.py` (`test_welt_importiert_nichts_verbotenes` muss das neue Modul mit abdecken — iteriert es über `welt/*.py`? sonst dort aufnehmen).
- [ ] **Step 5: Commit** — `feat(welt): bearbeitung.py -- verschieben, drehen, skalieren, duplizieren, loeschen, Felder`

---

### Task 7: Rasten, Fang, Treffer, Griffe, Eckenziehen, Prüfung

**Files:**
- Modify: `src/spotlab/welt/bearbeitung.py`
- Test: `tests/test_welt_bearbeitung.py`

**Interfaces:**
- Produces: `fange_ende(raum, x, y, ausser=None) -> (x, y)`, `treffer(raum, x, y, toleranz=0.1) -> schluessel | None`, `im_rahmen(raum, x1, y1, x2, y2) -> frozenset`, `griffe(raum, auswahl) -> list[(schluessel, art, x, y)]` mit `art in {"ende_a", "ende_b", "ecke0".."ecke3", "drehring", "richtung"}`, `ziehe_ecke(raum, schluessel, ecke, x, y)`, `drehring_lage(block)`, `richtung_lage(x, y, grad)`, `pruefe(raum) -> list[str]`, `RING_ABSTAND_M = 0.3`, `PFEIL_M = 0.4`.

- [ ] **Step 1: Tests anhängen**

```python
def test_rasten():
    assert b.raste(1.234) == pytest.approx(1.25)
    assert b.raste(37.0, b.RASTER_GRAD) == 35.0


def test_wandenden_fangen_sich():
    assert b.fange_ende(RAUM, 4.05, 0.08) == (4.0, 0.0)
    assert b.fange_ende(RAUM, 4.05, 0.08, ausser=("wand", 0)) == (4.0, 0.0)
    assert b.fange_ende(RAUM, 2.0, 2.0) == (2.0, 2.0)


def test_treffer_mit_vorrang():
    assert b.treffer(RAUM, 2.0, 0.02) == ("wand", 0)
    assert b.treffer(RAUM, 2.1, 2.1) == ("block", 0)
    assert b.treffer(RAUM, 3.55, 1.5) == ("tag", 0)
    assert b.treffer(RAUM, 1.05, 1.0) == ("start",)
    assert b.treffer(RAUM, 2.0, 1.0) is None
    raum = Raum(name="T", beschreibung="", start=(9, 9, 0),
                bloecke=(Block("K", 2, 2, 2, 2),), tags=(RaumTag(1, 2, 2, 0),))
    assert b.treffer(raum, 2.0, 2.0) == ("tag", 0)          # das Kleinere liegt oben


def test_rahmenauswahl_nimmt_die_mitten():
    assert b.im_rahmen(RAUM, 1.5, -0.5, 2.5, 2.5) == frozenset({("wand", 0), ("block", 0)})
    assert b.im_rahmen(RAUM, 0, 0, 5, 5) == frozenset(
        {("wand", 0), ("wand", 1), ("block", 0), ("tag", 0), ("start",)})


def test_griffe_je_art():
    griffe = b.griffe(RAUM, frozenset({("wand", 0), ("block", 0), ("tag", 0), ("start",)}))
    arten = {(s, art): (x, y) for s, art, x, y in griffe}
    assert arten[(("wand", 0), "ende_a")] == (0.0, 0.0)
    assert arten[(("wand", 0), "ende_b")] == (4.0, 0.0)
    assert arten[(("block", 0), "ecke0")] == (pytest.approx(1.5), pytest.approx(1.75))
    assert arten[(("block", 0), "drehring")] == (pytest.approx(2.5 + b.RING_ABSTAND_M), pytest.approx(2.0))
    assert arten[(("tag", 0), "richtung")] == (pytest.approx(3.5 - b.PFEIL_M), pytest.approx(1.5))
    assert arten[(("start",), "richtung")] == (pytest.approx(1.0 + b.PFEIL_M), pytest.approx(1.0))


def test_eine_ecke_ziehen_laesst_die_gegenecke_stehen():
    neu = b.ziehe_ecke(RAUM, ("block", 0), 2, 3.0, 3.0)      # Ecke 2 = rechts oben
    kiste = neu.bloecke[0]
    assert kiste.ecken()[0] == (pytest.approx(1.5), pytest.approx(1.75))
    assert (kiste.breite, kiste.tiefe) == (pytest.approx(1.5), pytest.approx(1.25))
    assert (kiste.x, kiste.y) == (pytest.approx(2.25), pytest.approx(2.375))


def test_pruefe_nennt_die_probleme():
    raum = Raum(name="P", beschreibung="", start=(2.0, 2.0, 0.0),
                waende=((0, 0, 0, 0),),
                bloecke=(Block("Kiste", 2, 2, 1, 1), Block("Nadel", 5, 5, 0.01, 1)),
                tags=(RaumTag(1, 2, 2, 0), RaumTag(1, 8, 8, 0)))
    hinweise = b.pruefe(raum)
    assert any("Start" in h and "Kiste" in h for h in hinweise)
    assert any("Wand 1" in h for h in hinweise)
    assert any("Nadel" in h for h in hinweise)
    assert any("Tag 1" in h and "doppelt" in h for h in hinweise)
    assert any("Tag 1" in h and "Kiste" in h for h in hinweise)
    assert b.pruefe(RAUM) == []
```

- [ ] **Step 2: Rot**

- [ ] **Step 3: Anhängen an `bearbeitung.py`**

```python
# ------------------------------------------------- Rasten, Fang, Treffer

RING_ABSTAND_M = 0.3     # Drehring: so weit ausserhalb des Blocks
PFEIL_M = 0.4            # Richtungsgriff von Tag und Start


def _abstand_strecke(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    laenge2 = dx * dx + dy * dy
    if laenge2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / laenge2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def fange_ende(raum, x, y, ausser=None):
    """Der naechste fremde Wandendpunkt innerhalb FANG_M, sonst (x, y) selbst."""
    beste, bester_abstand = (x, y), FANG_M
    for i, wand in enumerate(raum.waende):
        if ausser is not None and ausser == ("wand", i):
            continue
        for ex, ey in ((wand.x1, wand.y1), (wand.x2, wand.y2)):
            d = math.hypot(ex - x, ey - y)
            if d < bester_abstand:
                beste, bester_abstand = (ex, ey), d
    return beste


_RANG = {"start": 0, "tag": 1, "block": 2, "wand": 3}


def treffer(raum, x, y, toleranz=0.1):
    """Der Schluessel unter dem Zeiger oder None. Das Kleinere liegt oben."""
    kandidaten = []
    d = math.hypot(raum.start[0] - x, raum.start[1] - y)
    if d <= GRIFF_RADIUS_M + toleranz:
        kandidaten.append((max(d - GRIFF_RADIUS_M, 0.0), _RANG["start"], START))
    for i, tag in enumerate(raum.tags):
        d = math.hypot(tag.x - x, tag.y - y)
        if d <= GRIFF_RADIUS_M + toleranz:
            kandidaten.append((max(d - GRIFF_RADIUS_M, 0.0), _RANG["tag"], ("tag", i)))
    for i, block in enumerate(raum.bloecke):
        d = abstand_block(block, x, y)
        if d <= toleranz:
            kandidaten.append((d, _RANG["block"], ("block", i)))
    halbe_dicke = raum.wand_dicke / 2
    for i, wand in enumerate(raum.waende):
        d = _abstand_strecke(x, y, *wand)
        if d <= toleranz + halbe_dicke:
            kandidaten.append((max(d - halbe_dicke, 0.0), _RANG["wand"], ("wand", i)))
    if not kandidaten:
        return None
    return min(kandidaten)[2]


def im_rahmen(raum, x1, y1, x2, y2):
    """Alle Elemente, deren Lage im Rechteck liegt."""
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    schluessel = [("wand", i) for i in range(len(raum.waende))]
    schluessel += [("block", i) for i in range(len(raum.bloecke))]
    schluessel += [("tag", i) for i in range(len(raum.tags))]
    schluessel.append(START)
    return frozenset(
        s for s in schluessel
        if lo_x <= lage(raum, s)[0] <= hi_x and lo_y <= lage(raum, s)[1] <= hi_y
    )


# ----------------------------------------------------------------- Griffe


def drehring_lage(block):
    c, s = math.cos(math.radians(block.drehung)), math.sin(math.radians(block.drehung))
    r = block.breite / 2 + RING_ABSTAND_M
    return (block.x + r * c, block.y + r * s)


def richtung_lage(x, y, grad):
    return (x + PFEIL_M * math.cos(math.radians(grad)), y + PFEIL_M * math.sin(math.radians(grad)))


def griffe(raum, auswahl):
    """[(schluessel, art, x, y)] -- was die 2D-Sicht als Anfasser zeichnet."""
    ergebnis = []
    for s in sorted(auswahl):
        e = element(raum, s)
        if s[0] == "wand":
            ergebnis.append((s, "ende_a", e.x1, e.y1))
            ergebnis.append((s, "ende_b", e.x2, e.y2))
        elif s[0] == "block":
            for i, (x, y) in enumerate(e.ecken()):
                ergebnis.append((s, f"ecke{i}", x, y))
            ergebnis.append((s, "drehring", *drehring_lage(e)))
        elif s[0] == "tag":
            ergebnis.append((s, "richtung", *richtung_lage(e.x, e.y, e.grad)))
        elif s[0] == "start":
            ergebnis.append((s, "richtung", *richtung_lage(e[0], e[1], e[2])))
    return ergebnis


def ziehe_ecke(raum, schluessel, ecke, x, y):
    """Ecke `ecke` (0..3) eines Blocks auf (x, y) ziehen; die Gegenecke bleibt stehen."""
    block = element(raum, schluessel)
    lx, ly = block.lokal(x, y)
    vorzeichen = ((-1, -1), (1, -1), (1, 1), (-1, 1))[ecke]
    gx, gy = -vorzeichen[0] * block.breite / 2, -vorzeichen[1] * block.tiefe / 2
    breite = _kante(abs(lx - gx))
    tiefe = _kante(abs(ly - gy))
    mx, my = (lx + gx) / 2, (ly + gy) / 2
    c, s = math.cos(math.radians(block.drehung)), math.sin(math.radians(block.drehung))
    neu = replace(block, x=block.x + mx * c - my * s, y=block.y + mx * s + my * c,
                  breite=breite, tiefe=tiefe)
    return _ersetze(raum, schluessel, neu)


# ---------------------------------------------------------------- Pruefung


def pruefe(raum):
    """Hinweise auf Unstimmiges -- als Liste, die der Editor zeigt."""
    hinweise = []
    getroffen = hindernis_bei(raum, raum.start[0], raum.start[1])
    if getroffen is not None:
        was = "einer Wand" if getroffen == "Wand" else f"„{getroffen}“"
        hinweise.append(f"Der Start steht in {was}. Verschiebe ihn im Raumeditor.")
    for i, wand in enumerate(raum.waende):
        if wand.laenge < MINDESTKANTE_M:
            hinweise.append(f"Wand {i + 1} hat keine Laenge.")
    for block in raum.bloecke:
        if min(block.breite, block.tiefe, block.hoehe) < MINDESTKANTE_M:
            hinweise.append(f"„{block.name}“ hat eine Kante unter {MINDESTKANTE_M} m.")
    gesehen = set()
    for tag in raum.tags:
        if tag.id in gesehen:
            hinweise.append(f"Tag {tag.id} ist doppelt vergeben.")
        gesehen.add(tag.id)
        for block in raum.bloecke:
            if abstand_block(block, tag.x, tag.y) == 0.0:
                hinweise.append(f"Tag {tag.id} steckt in „{block.name}“.")
    return hinweise
```

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_bearbeitung.py`
- [ ] **Step 5: Commit** — `feat(welt): Rasten, Fang, Treffer, Griffe, Eckenziehen, Pruefung`

---

### Task 8: `Verlauf` und `Modus` (Blender-Tasten als Zustandsautomat)

**Files:**
- Modify: `src/spotlab/welt/bearbeitung.py`
- Test: `tests/test_welt_bearbeitung.py`

**Interfaces:**
- Produces: `Verlauf(grenze=200)` mit `merke(raum)`, `zurueck() -> Raum | None`, `vor() -> Raum | None`, `aktuell`, `kann_zurueck`, `kann_vor`; `Modus` mit Konstanten `RUHE, BEWEGEN, DREHEN, SKALIEREN`, Attributen `art`, `aktiv`, `achse`, `zahl`, Methoden `beginne(art, raum, auswahl, zeiger)`, `zeiger(x, y, frei=False)`, `taste(name) -> bool`, `vorschau() -> Raum`, `bestaetige() -> Raum`, `abbruch() -> Raum`.

- [ ] **Step 1: Tests anhängen**

```python
def test_verlauf_merkt_geht_zurueck_und_vor():
    v = b.Verlauf(grenze=3)
    r1 = RAUM
    r2 = b.verschiebe(r1, frozenset({("start",)}), 1, 0)
    r3 = b.verschiebe(r2, frozenset({("start",)}), 1, 0)
    v.merke(r1)
    v.merke(r2)
    v.merke(r3)
    assert v.aktuell is r3 and v.kann_zurueck and not v.kann_vor
    assert v.zurueck() is r2 and v.zurueck() is r1 and v.zurueck() is None
    assert v.vor() is r2
    v.merke(RAUM)                       # verwirft r3
    assert not v.kann_vor and v.zurueck() is r2
    for _ in range(5):
        v.merke(RAUM)
    assert len(v._schnappschuesse) == 3


def _tasten(modus, folge):
    for name in folge.split():
        modus.taste(name)


def test_g_x_zahl_enter_bewegt_genau():
    m = b.Modus()
    m.beginne(b.Modus.BEWEGEN, RAUM, frozenset({("block", 0)}), zeiger=(2.0, 2.0))
    assert m.aktiv and m.art == b.Modus.BEWEGEN
    _tasten(m, "x 1 . 5")
    assert m.achse == "x" and m.zahl == "1.5"
    assert (m.vorschau().bloecke[0].x, m.vorschau().bloecke[0].y) == (3.5, 2.0)
    fertig = m.bestaetige()
    assert not m.aktiv and fertig.bloecke[0].x == 3.5


def test_bewegen_folgt_dem_zeiger_gerastet_und_frei():
    m = b.Modus()
    m.beginne(b.Modus.BEWEGEN, RAUM, frozenset({("block", 0)}), zeiger=(2.0, 2.0))
    m.zeiger(2.33, 2.08)
    assert (m.vorschau().bloecke[0].x, m.vorschau().bloecke[0].y) == (
        pytest.approx(2.35), pytest.approx(2.1))
    m.zeiger(2.33, 2.08, frei=True)
    assert m.vorschau().bloecke[0].x == pytest.approx(2.33)
    m.taste("y")                                            # Achssperre: nur y
    assert m.vorschau().bloecke[0].x == 2.0
    m.taste("y")                                            # zweite Achstaste hebt auf
    assert m.achse is None
    assert m.abbruch() is RAUM and not m.aktiv


def test_r_zahl_dreht_um_die_mitte_der_auswahl():
    m = b.Modus()
    m.beginne(b.Modus.DREHEN, RAUM, frozenset({("wand", 0)}), zeiger=(3.0, 0.0))
    _tasten(m, "9 0")
    wand = m.vorschau().waende[0]
    assert (wand.x1, wand.y1) == (pytest.approx(2.0), pytest.approx(-2.0))
    m.taste("Backspace")
    m.taste("Backspace")
    m.zeiger(2.0, 1.0)                                      # 90 Grad vom Startzeiger aus
    assert m.vorschau().waende[0].y2 == pytest.approx(2.0)


def test_s_z_zahl_skaliert_die_hoehe():
    m = b.Modus()
    m.beginne(b.Modus.SKALIEREN, RAUM, frozenset({("block", 0)}), zeiger=(3.0, 2.0))
    _tasten(m, "z 2")
    kiste = m.vorschau().bloecke[0]
    assert (kiste.breite, kiste.tiefe, kiste.hoehe) == (1.0, 0.5, 1.5)
    m2 = b.Modus()
    m2.beginne(b.Modus.SKALIEREN, RAUM, frozenset({("block", 0)}), zeiger=(3.0, 2.0))
    m2.zeiger(4.0, 2.0)                                     # doppelter Abstand zur Mitte
    assert m2.vorschau().bloecke[0].breite == pytest.approx(2.0)
    assert m2.vorschau().bloecke[0].tiefe == pytest.approx(1.0)


def test_ohne_auswahl_beginnt_kein_modus():
    m = b.Modus()
    m.beginne(b.Modus.BEWEGEN, RAUM, frozenset(), zeiger=(0.0, 0.0))
    assert not m.aktiv and m.taste("x") is False
```

- [ ] **Step 2: Rot**

- [ ] **Step 3: Anhängen**

```python
# ---------------------------------------------------------------- Verlauf


class Verlauf:
    """Rueckgaengig als Liste von Schnappschuessen -- der Raum ist unveraenderlich."""

    def __init__(self, grenze=200):
        self._grenze = grenze
        self._schnappschuesse = []
        self._stelle = -1

    @property
    def aktuell(self):
        return self._schnappschuesse[self._stelle] if self._stelle >= 0 else None

    @property
    def kann_zurueck(self):
        return self._stelle > 0

    @property
    def kann_vor(self):
        return self._stelle < len(self._schnappschuesse) - 1

    def merke(self, raum):
        del self._schnappschuesse[self._stelle + 1:]
        self._schnappschuesse.append(raum)
        if len(self._schnappschuesse) > self._grenze:
            del self._schnappschuesse[0]
        self._stelle = len(self._schnappschuesse) - 1

    def zurueck(self):
        if not self.kann_zurueck:
            return None
        self._stelle -= 1
        return self.aktuell

    def vor(self):
        if not self.kann_vor:
            return None
        self._stelle += 1
        return self.aktuell


# ------------------------------------------------------------------ Modus


class Modus:
    """Die Blender-Tasten: G bewegen, R drehen, S skalieren -- als Automat.

    Eingabe sind Tasten und der Zeiger in METERN auf dem Boden; die Sicht
    rechnet Pixel um. So arbeiten 2D und 3D identisch, und der Automat ist ohne
    Fenster testbar. Die Vorschau ist ein Raum; bestaetigt legt der Aufrufer
    sie in den Verlauf.
    """

    RUHE, BEWEGEN, DREHEN, SKALIEREN = "ruhe", "bewegen", "drehen", "skalieren"

    def __init__(self):
        self._ruhe()

    def _ruhe(self):
        self.art = self.RUHE
        self._raum = None
        self._auswahl = frozenset()
        self._start = (0.0, 0.0)
        self._zeiger = (0.0, 0.0)
        self._um = (0.0, 0.0)
        self._frei = False
        self.achse = None
        self.zahl = ""

    @property
    def aktiv(self):
        return self.art != self.RUHE

    def beginne(self, art, raum, auswahl, zeiger):
        if not auswahl:
            return
        self._ruhe()
        self.art = art
        self._raum = raum
        self._auswahl = frozenset(auswahl)
        self._start = self._zeiger = (float(zeiger[0]), float(zeiger[1]))
        self._um = mitte(raum, self._auswahl)

    def zeiger(self, x, y, frei=False):
        self._zeiger = (float(x), float(y))
        self._frei = frei

    def taste(self, name):
        """True, wenn die Taste zum Modus gehoert hat."""
        if not self.aktiv:
            return False
        name = name.lower()
        if name in ("x", "y", "z"):
            self.achse = None if self.achse == name else name
            return True
        if len(name) == 1 and name in "0123456789.-":
            self.zahl += name
            return True
        if name == "backspace":
            self.zahl = self.zahl[:-1]
            return True
        return False

    def _wert(self):
        try:
            return float(self.zahl)
        except ValueError:
            return None

    def vorschau(self):
        if not self.aktiv:
            return self._raum
        wert = self._wert()
        if self.art == self.BEWEGEN:
            if wert is not None:
                dx, dy = (0.0, wert) if self.achse == "y" else (wert, 0.0)
            else:
                dx = self._zeiger[0] - self._start[0]
                dy = self._zeiger[1] - self._start[1]
                if not self._frei:
                    dx, dy = raste(dx), raste(dy)
                if self.achse == "x":
                    dy = 0.0
                elif self.achse == "y":
                    dx = 0.0
            return verschiebe(self._raum, self._auswahl, dx, dy)
        if self.art == self.DREHEN:
            if wert is not None:
                grad = wert
            else:
                a0 = math.atan2(self._start[1] - self._um[1], self._start[0] - self._um[0])
                a1 = math.atan2(self._zeiger[1] - self._um[1], self._zeiger[0] - self._um[0])
                grad = math.degrees(a1 - a0)
                if not self._frei:
                    grad = raste(grad, RASTER_GRAD)
            return drehe(self._raum, self._auswahl, grad, um=self._um)
        if wert is not None:
            f = wert
        else:
            vorher = math.hypot(self._start[0] - self._um[0], self._start[1] - self._um[1])
            nachher = math.hypot(self._zeiger[0] - self._um[0], self._zeiger[1] - self._um[1])
            f = nachher / vorher if vorher > 1e-9 else 1.0
            if not self._frei:
                f = raste(f, 0.05)
        f = max(f, 0.01)
        if self.achse == "x":
            fx, fy, fz = f, 1.0, 1.0
        elif self.achse == "y":
            fx, fy, fz = 1.0, f, 1.0
        elif self.achse == "z":
            fx, fy, fz = 1.0, 1.0, f
        else:
            fx, fy, fz = f, f, 1.0
        return skaliere(self._raum, self._auswahl, fx, fy, fz, um=self._um)

    def bestaetige(self):
        raum = self.vorschau()
        self._ruhe()
        return raum

    def abbruch(self):
        raum = self._raum
        self._ruhe()
        return raum
```

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_welt_bearbeitung.py tests/test_welt_raum.py`
- [ ] **Step 5: Commit** — `feat(welt): Verlauf und Modus -- Rueckgaengig als Liste, Blender-Tasten als Automat`

---

### Task 9: `gui/raumeditor/steuerung.py` — die Steuerung ohne Qt

**Files:**
- Create: `src/spotlab/gui/raumeditor/__init__.py` (leer bis Task 11), `src/spotlab/gui/raumeditor/steuerung.py`
- Test: `tests/test_gui_raumeditor_steuerung.py` (ohne Qt, kein `qapp`)

**Interfaces:**
- Consumes: alles aus `welt.bearbeitung` (Tasks 6–8), `welt.raum.Raum`
- Produces: `Steuerung(raum=None)` mit Attributen `raum, auswahl, verlauf, modus, werkzeug, geaendert, kette, rahmen, zeiger`; Methoden `setze_raum(raum, geaendert=False)`, `setze_werkzeug(name)`, `druecke(x, y, taste="links", shift=False, ctrl=False, toleranz=TOLERANZ_M)`, `bewege(x, y, ctrl=False)`, `lasse_los(x, y, shift=False, ctrl=False)`, `taste(name, shift=False, ctrl=False, alt=False) -> bool`, `setze_feld(schluessel, feld, wert)`, `griffe()`, `hinweise()`, `alle()`, `rueckgaengig()`, `wiederholen()`; Konstanten `WERKZEUGE = ("auswahl", "wand", "block", "tag", "start")`, `TOLERANZ_M = 0.12`.

- [ ] **Step 1: Tests**

```python
"""Die Steuerung des Raumeditors -- Maus in Metern, Tasten als Namen, ohne Qt."""
import pytest

from spotlab.gui.raumeditor.steuerung import TOLERANZ_M, Steuerung
from spotlab.welt.raum import Block, Raum, RaumTag

RAUM = Raum(
    name="T", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 4, 0), (4, 0, 4, 3)),
    bloecke=(Block("Kiste", 2.0, 2.0, 1.0, 0.5),),
    tags=(RaumTag(1, 3.5, 1.5, 180.0),),
)


def klick(st, x, y, **k):
    st.druecke(x, y, **k)
    st.lasse_los(x, y, shift=k.get("shift", False))


def test_klick_waehlt_und_shift_ergaenzt():
    st = Steuerung(RAUM)
    klick(st, 2.0, 2.0)
    assert st.auswahl == {("block", 0)}
    klick(st, 2.0, 0.0, shift=True)
    assert st.auswahl == {("block", 0), ("wand", 0)}
    klick(st, 2.0, 0.0, shift=True)                       # nochmal: abwaehlen
    assert st.auswahl == {("block", 0)}
    klick(st, 2.0, 1.0)                                   # ins Leere
    assert st.auswahl == frozenset() and not st.geaendert


def test_ziehen_verschiebt_gerastet_und_merkt_sich_das():
    st = Steuerung(RAUM)
    st.druecke(2.0, 2.0)
    st.bewege(2.52, 2.03)
    assert (st.raum.bloecke[0].x, st.raum.bloecke[0].y) == (pytest.approx(2.5), pytest.approx(2.05))
    st.lasse_los(2.52, 2.03)
    assert st.geaendert and st.verlauf.kann_zurueck
    assert st.rueckgaengig() and st.raum.bloecke[0].x == 2.0


def test_rahmen_waehlt_mehrere():
    st = Steuerung(RAUM)
    st.druecke(1.5, -0.5)
    st.bewege(2.5, 2.5)
    assert st.rahmen == (1.5, -0.5, 2.5, 2.5)
    st.lasse_los(2.5, 2.5)
    assert st.auswahl == {("wand", 0), ("block", 0)} and st.rahmen is None


def test_wandwerkzeug_zeichnet_eine_kette_mit_fang():
    st = Steuerung(RAUM)
    st.setze_werkzeug("wand")
    klick(st, 4.04, 3.03)                                 # faengt (4, 3)
    assert st.kette == (4.0, 3.0) and len(st.raum.waende) == 2
    klick(st, 0.02, 3.01)
    assert len(st.raum.waende) == 3 and list(st.raum.waende[2]) == [4.0, 3.0, 0.0, 3.0]
    assert st.auswahl == {("wand", 2)} and st.kette == (0.0, 3.0)
    st.taste("escape")
    assert st.kette is None
    st.druecke(1.0, 1.0, taste="rechts")                  # rechts beendet auch
    assert st.kette is None


def test_blockwerkzeug_zieht_ein_rechteck():
    st = Steuerung(RAUM)
    st.setze_werkzeug("block")
    st.druecke(0.5, 1.5)
    st.bewege(1.53, 2.48)
    st.lasse_los(1.53, 2.48)
    kiste = st.raum.bloecke[1]
    assert kiste.name == "Block 1"
    assert (kiste.x, kiste.y, kiste.breite, kiste.tiefe) == (
        pytest.approx(1.0), pytest.approx(2.0), pytest.approx(1.0), pytest.approx(1.0))
    assert st.auswahl == {("block", 1)}


def test_tag_und_start_werkzeug():
    st = Steuerung(RAUM)
    st.setze_werkzeug("tag")
    klick(st, 0.5, 0.5)
    assert st.raum.tags[1].id == 2 and st.auswahl == {("tag", 1)}
    st.setze_werkzeug("start")
    st.druecke(3.0, 2.0)
    st.bewege(3.0, 2.5)                                   # nach oben ziehen: Blick 90 Grad
    st.lasse_los(3.0, 2.5)
    assert st.raum.start == (3.0, 2.0, 90.0) and st.geaendert


def test_griffe_ziehen_ende_ecke_ring_und_richtung():
    st = Steuerung(RAUM)
    klick(st, 2.0, 0.0)                                   # Wand 0
    st.druecke(4.0, 0.0)                                  # Griff ende_b
    st.bewege(4.5, 0.02)
    st.lasse_los(4.5, 0.02)
    assert list(st.raum.waende[0]) == [0.0, 0.0, 4.5, 0.0]
    klick(st, 2.0, 2.0)                                   # Kiste
    st.druecke(2.5, 2.25)                                 # Ecke 2
    st.bewege(3.0, 3.0)
    st.lasse_los(3.0, 3.0)
    assert (st.raum.bloecke[0].breite, st.raum.bloecke[0].tiefe) == (pytest.approx(1.5), pytest.approx(1.25))
    klick(st, st.raum.bloecke[0].x, st.raum.bloecke[0].y)
    ring = next(g for g in st.griffe() if g[1] == "drehring")
    st.druecke(ring[2], ring[3])
    st.bewege(st.raum.bloecke[0].x, st.raum.bloecke[0].y + 2.0)
    st.lasse_los(st.raum.bloecke[0].x, st.raum.bloecke[0].y + 2.0)
    assert st.raum.bloecke[0].drehung == 90.0
    klick(st, 1.0, 1.0)                                   # Start
    st.druecke(1.4, 1.0)                                  # Richtungsgriff
    st.bewege(1.0, 1.6)
    st.lasse_los(1.0, 1.6)
    assert st.raum.start[2] == 90.0


def test_tasten_g_x_zahl_enter_und_rueckgaengig():
    st = Steuerung(RAUM)
    klick(st, 2.0, 2.0)
    assert st.taste("g") and st.modus.aktiv
    for name in "x 1 . 5".split():
        assert st.taste(name)
    assert st.raum.bloecke[0].x == 2.0                    # Vorschau erst nach bewege()
    st.bewege(2.0, 2.0)
    assert st.raum.bloecke[0].x == 3.5
    assert st.taste("return") and not st.modus.aktiv and st.raum.bloecke[0].x == 3.5
    assert st.taste("z", ctrl=True) and st.raum.bloecke[0].x == 2.0
    assert st.taste("y", ctrl=True) and st.raum.bloecke[0].x == 3.5


def test_modus_abbruch_klick_und_escape():
    st = Steuerung(RAUM)
    klick(st, 2.0, 2.0)
    st.taste("g")
    st.bewege(3.0, 2.0)
    st.taste("escape")
    assert st.raum.bloecke[0].x == 2.0 and not st.geaendert
    st.taste("r")
    st.bewege(2.0, 3.0)
    st.druecke(2.0, 3.0)                                  # Linksklick bestaetigt
    assert not st.modus.aktiv and st.raum.bloecke[0].drehung == 90.0 and st.geaendert


def test_loeschen_duplizieren_alles():
    st = Steuerung(RAUM)
    assert st.taste("a") and st.auswahl == st.alle() and len(st.auswahl) == 5
    assert st.taste("a", alt=True) and st.auswahl == frozenset()
    klick(st, 2.0, 2.0)
    assert st.taste("d", shift=True)
    assert len(st.raum.bloecke) == 2 and st.auswahl == {("block", 1)} and st.modus.aktiv
    st.taste("escape")
    assert st.taste("delete") and len(st.raum.bloecke) == 1 and st.auswahl == frozenset()


def test_setze_feld_und_hinweise():
    st = Steuerung(RAUM)
    st.setze_feld(("start",), "x", 2.0)
    st.setze_feld(("start",), "y", 2.0)
    assert any("Start" in h for h in st.hinweise()) and st.geaendert
    with pytest.raises(ValueError):
        st.setze_feld(("block", 0), "farbe", 1)


def test_setze_raum_setzt_alles_zurueck():
    st = Steuerung(RAUM)
    klick(st, 2.0, 2.0)
    st.taste("delete")
    st.setze_raum(RAUM)
    assert st.raum is RAUM and st.auswahl == frozenset() and not st.geaendert
    assert not st.verlauf.kann_zurueck
    assert TOLERANZ_M == 0.12
```

- [ ] **Step 2: Rot** — ModuleNotFoundError.

- [ ] **Step 3: `steuerung.py`**

```python
"""Die Steuerung des Raumeditors -- ohne Qt.

Maus kommt in METERN (die Sicht rechnet Pixel um), Tasten als Namen
("g", "x", "return", "escape", "delete", ...). Was hier steht, ist alles, was der
Editor kann; `sicht2d.py` und `tab.py` sind nur die Haut darum. Deshalb laeuft
jeder Bedienfall als Test ohne Fenster.
"""

import math

from spotlab.welt import bearbeitung as b

WERKZEUGE = ("auswahl", "wand", "block", "tag", "start")
TOLERANZ_M = 0.12        # Treffer um den Zeiger; die Sicht rechnet 8 px um


class Steuerung:
    def __init__(self, raum=None):
        self.modus = b.Modus()
        self.setze_raum(raum)

    def setze_raum(self, raum, geaendert=False):
        self.raum = raum
        self.auswahl = frozenset()
        self.verlauf = b.Verlauf()
        if raum is not None:
            self.verlauf.merke(raum)
        self.modus = b.Modus()
        self.werkzeug = "auswahl"
        self.geaendert = geaendert
        self.kette = None          # Anfang der naechsten Wand (Wandwerkzeug)
        self.rahmen = None         # (x1, y1, x2, y2) waehrend Rahmenauswahl oder Blockziehen
        self.zeiger = (0.0, 0.0)
        self._zug = None

    # ------------------------------------------------------------ innen

    def _uebernimm(self, raum):
        """Eine bestaetigte Aenderung: in den Verlauf, als geaendert merken."""
        self.raum = raum
        self.verlauf.merke(raum)
        self.geaendert = True

    @staticmethod
    def _rast(wert, frei):
        return wert if frei else b.raste(wert)

    @staticmethod
    def _winkel(cx, cy, x, y, frei):
        grad = math.degrees(math.atan2(y - cy, x - cx)) % 360.0
        return grad if frei else b.raste(grad, b.RASTER_GRAD) % 360.0

    # --------------------------------------------------------- Werkzeug

    def setze_werkzeug(self, name):
        if name not in WERKZEUGE:
            raise ValueError(f"Unbekanntes Werkzeug: {name!r}")
        if self.modus.aktiv:
            self.raum = self.modus.abbruch()
        self.werkzeug = name
        self.kette = None
        self._zug = None

    # -------------------------------------------------------------- Maus

    def druecke(self, x, y, taste="links", shift=False, ctrl=False, toleranz=TOLERANZ_M):
        self.zeiger = (x, y)
        if self.raum is None:
            return
        if self.modus.aktiv:
            if taste == "links":
                self._uebernimm(self.modus.bestaetige())
            else:
                self.raum = self.modus.abbruch()
            return
        if taste == "rechts":
            self.kette = None
            return
        if taste != "links":
            return
        if self.werkzeug == "auswahl":
            self._druecke_auswahl(x, y, shift, toleranz)
        elif self.werkzeug == "wand":
            self._druecke_wand(x, y, ctrl)
        elif self.werkzeug == "block":
            self._zug = {"art": "block", "von": (self._rast(x, ctrl), self._rast(y, ctrl))}
            self.rahmen = (*self._zug["von"], *self._zug["von"])
        elif self.werkzeug == "tag":
            raum, s = b.neuer_tag(self.raum, self._rast(x, ctrl), self._rast(y, ctrl))
            self._uebernimm(raum)
            self.auswahl = frozenset({s})
        elif self.werkzeug == "start":
            sx, sy = self._rast(x, ctrl), self._rast(y, ctrl)
            self._zug = {"art": "start_richtung", "raum": self.raum, "von": (sx, sy)}
            self.raum = b.setze_start(self.raum, sx, sy, self.raum.start[2])
            self.auswahl = frozenset({b.START})

    def _druecke_auswahl(self, x, y, shift, toleranz):
        for s, art, gx, gy in b.griffe(self.raum, self.auswahl):
            if math.hypot(gx - x, gy - y) <= toleranz:
                self._zug = {"art": art, "schluessel": s, "raum": self.raum, "von": (x, y)}
                return
        s = b.treffer(self.raum, x, y, toleranz)
        if s is None:
            if not shift:
                self.auswahl = frozenset()
            self._zug = {"art": "rahmen", "von": (x, y)}
            self.rahmen = (x, y, x, y)
            return
        if shift:
            self.auswahl = self.auswahl ^ frozenset({s})
        elif s not in self.auswahl:
            self.auswahl = frozenset({s})
        self._zug = {"art": "verschieben", "von": (x, y), "raum": self.raum,
                     "auswahl": self.auswahl}

    def _druecke_wand(self, x, y, ctrl):
        px, py = b.fange_ende(self.raum, self._rast(x, ctrl), self._rast(y, ctrl))
        if self.kette is None:
            self.kette = (px, py)
            return
        if math.hypot(px - self.kette[0], py - self.kette[1]) < b.MINDESTKANTE_M:
            return
        raum, s = b.neue_wand(self.raum, self.kette[0], self.kette[1], px, py)
        self._uebernimm(raum)
        self.auswahl = frozenset({s})
        self.kette = (px, py)

    def bewege(self, x, y, ctrl=False):
        self.zeiger = (x, y)
        if self.modus.aktiv:
            self.modus.zeiger(x, y, frei=ctrl)
            self.raum = self.modus.vorschau()
            return
        z = self._zug
        if z is None:
            return
        art = z["art"]
        if art in ("rahmen", "block"):
            self.rahmen = (z["von"][0], z["von"][1], self._rast(x, ctrl) if art == "block" else x,
                           self._rast(y, ctrl) if art == "block" else y)
        elif art == "verschieben":
            dx, dy = x - z["von"][0], y - z["von"][1]
            self.raum = b.verschiebe(z["raum"], z["auswahl"], self._rast(dx, ctrl), self._rast(dy, ctrl))
        elif art in ("ende_a", "ende_b"):
            s = z["schluessel"]
            px, py = b.fange_ende(z["raum"], self._rast(x, ctrl), self._rast(y, ctrl), ausser=s)
            fx, fy = ("x1", "y1") if art == "ende_a" else ("x2", "y2")
            self.raum = b.setze_feld(b.setze_feld(z["raum"], s, fx, px), s, fy, py)
        elif art.startswith("ecke"):
            self.raum = b.ziehe_ecke(z["raum"], z["schluessel"], int(art[4:]),
                                     self._rast(x, ctrl), self._rast(y, ctrl))
        elif art == "drehring":
            block = b.element(z["raum"], z["schluessel"])
            grad = self._winkel(block.x, block.y, x, y, ctrl)
            self.raum = b.setze_feld(z["raum"], z["schluessel"], "drehung", grad)
        elif art == "richtung":
            cx, cy = b.lage(z["raum"], z["schluessel"])
            self.raum = b.setze_feld(z["raum"], z["schluessel"], "grad",
                                     self._winkel(cx, cy, x, y, ctrl))
        elif art == "start_richtung":
            sx, sy = z["von"]
            if math.hypot(x - sx, y - sy) >= 0.05:
                self.raum = b.setze_start(z["raum"], sx, sy, self._winkel(sx, sy, x, y, ctrl))

    def lasse_los(self, x, y, shift=False, ctrl=False):
        z, self._zug = self._zug, None
        if z is None or self.raum is None:
            return
        art = z["art"]
        if art == "rahmen":
            x1, y1, x2, y2 = self.rahmen
            self.rahmen = None
            if abs(x2 - x1) > 0.02 or abs(y2 - y1) > 0.02:
                neue = b.im_rahmen(self.raum, x1, y1, x2, y2)
                self.auswahl = (self.auswahl | neue) if shift else neue
            return
        if art == "block":
            x1, y1, x2, y2 = self.rahmen
            self.rahmen = None
            breite, tiefe = abs(x2 - x1), abs(y2 - y1)
            if breite < b.MINDESTKANTE_M or tiefe < b.MINDESTKANTE_M:
                return
            raum, s = b.neuer_block(self.raum, (x1 + x2) / 2, (y1 + y2) / 2, breite, tiefe)
            self._uebernimm(raum)
            self.auswahl = frozenset({s})
            return
        if self.raum is not z["raum"]:
            self._uebernimm(self.raum)       # etwas hat sich bewegt

    # ------------------------------------------------------------ Tasten

    def taste(self, name, shift=False, ctrl=False, alt=False):
        """True, wenn die Taste verarbeitet wurde."""
        if self.raum is None:
            return False
        name = name.lower()
        if self.modus.aktiv:
            if name in ("return", "enter"):
                self._uebernimm(self.modus.bestaetige())
                return True
            if name == "escape":
                self.raum = self.modus.abbruch()
                return True
            return self.modus.taste(name)
        if ctrl and name == "z":
            return self.rueckgaengig()
        if ctrl and name == "y":
            return self.wiederholen()
        if name == "escape":
            self.kette = None
            self.auswahl = frozenset()
            return True
        if name == "a":
            self.auswahl = frozenset() if alt else self.alle()
            return True
        if not self.auswahl:
            return False
        if name in ("g", "r", "s"):
            art = {"g": b.Modus.BEWEGEN, "r": b.Modus.DREHEN, "s": b.Modus.SKALIEREN}[name]
            self.modus.beginne(art, self.raum, self.auswahl, self.zeiger)
            return True
        if name == "d" and shift:
            raum, neue = b.dupliziere(self.raum, self.auswahl)
            self._uebernimm(raum)
            self.auswahl = neue
            self.modus.beginne(b.Modus.BEWEGEN, self.raum, self.auswahl, self.zeiger)
            return True
        if name == "delete":
            raum, self.auswahl = b.loesche(self.raum, self.auswahl)
            self._uebernimm(raum)
            return True
        return False

    def rueckgaengig(self):
        raum = self.verlauf.zurueck()
        if raum is None:
            return False
        self.raum, self.auswahl, self.geaendert = raum, frozenset(), True
        return True

    def wiederholen(self):
        raum = self.verlauf.vor()
        if raum is None:
            return False
        self.raum, self.auswahl, self.geaendert = raum, frozenset(), True
        return True

    # ---------------------------------------------------------- Auskunft

    def alle(self):
        r = self.raum
        return frozenset(
            [("wand", i) for i in range(len(r.waende))]
            + [("block", i) for i in range(len(r.bloecke))]
            + [("tag", i) for i in range(len(r.tags))]
            + [b.START]
        )

    def setze_feld(self, schluessel, feld, wert):
        self._uebernimm(b.setze_feld(self.raum, schluessel, feld, wert))

    def griffe(self):
        if self.raum is None or self.modus.aktiv:
            return []
        return b.griffe(self.raum, self.auswahl)

    def hinweise(self):
        return b.pruefe(self.raum) if self.raum is not None else []
```

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumeditor_steuerung.py`
- [ ] **Step 5: Commit** — `feat(raumeditor): Steuerung ohne Qt -- Werkzeuge, Griffe, Zuege, Tasten, Verlauf`

---

### Task 10: `gui/raumeditor/sicht2d.py` — die 2D-Sicht

**Files:**
- Create: `src/spotlab/gui/raumeditor/sicht2d.py`
- Test: `tests/test_gui_raumeditor_sicht2d.py`

**Interfaces:**
- Consumes: `raumzeichnung.*`, `huelle`, `Palette`
- Produces: `Sicht2D(palette)` mit Signalen `gedrueckt(float, float, str, bool, bool)` (x, y, "links"/"rechts", shift, ctrl), `bewegt(float, float, bool)` (x, y, ctrl), `losgelassen(float, float, bool, bool)`, `taste_gedrueckt(str, bool, bool, bool)` (name, shift, ctrl, alt); Methoden `zeige(raum, auswahl=frozenset(), griffe=(), rahmen=None, kette=None)`, `setze_spur(punkte)`, `setze_anstoesse(punkte)`, `setze_pauspapier(punkte)`, `alles_zeigen()`, `meter_zu_schirm(x, y)`, `schirm_zu_meter(px, py)`, `toleranz_m()`, `skala` (Pixel je Meter).

- [ ] **Step 1: Tests**

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from spotlab.gui.raumeditor.sicht2d import Sicht2D  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import Block, Raum  # noqa: E402

RAUM = Raum(name="T", beschreibung="", start=(1, 1, 0), waende=((0, 0, 4, 0),),
            bloecke=(Block("K", 2, 2, 1, 1),))


def _sicht():
    sicht = Sicht2D(DUNKEL)
    sicht.resize(400, 300)
    sicht.zeige(RAUM, griffe=[(("block", 0), "ecke0", 1.5, 1.5)], rahmen=(0, 0, 1, 1), kette=(0, 0))
    sicht.alles_zeigen()
    return sicht


def test_umrechnung_ist_umkehrbar_und_y_zeigt_nach_oben(qapp):
    sicht = _sicht()
    px, py = sicht.meter_zu_schirm(2.0, 1.0)
    assert sicht.schirm_zu_meter(px, py) == (pytest.approx(2.0), pytest.approx(1.0))
    assert sicht.meter_zu_schirm(2.0, 2.0)[1] < py


def test_klick_kommt_in_metern_mit_umschalttasten(qapp):
    sicht = _sicht()
    empfangen = []
    sicht.gedrueckt.connect(lambda *a: empfangen.append(a))
    sicht.losgelassen.connect(lambda *a: empfangen.append(("los", *a)))
    px, py = sicht.meter_zu_schirm(2.0, 2.0)
    QTest.mouseClick(sicht, Qt.LeftButton, Qt.ShiftModifier, QPoint(int(px), int(py)))
    x, y, taste, shift, ctrl = empfangen[0]
    assert (x, y) == (pytest.approx(2.0, abs=0.02), pytest.approx(2.0, abs=0.02))
    assert taste == "links" and shift and not ctrl
    assert empfangen[1][0] == "los"


def test_tasten_kommen_als_namen(qapp):
    sicht = _sicht()
    empfangen = []
    sicht.taste_gedrueckt.connect(lambda *a: empfangen.append(a))
    QTest.keyClick(sicht, Qt.Key_G)
    QTest.keyClick(sicht, Qt.Key_Z, Qt.ControlModifier)
    QTest.keyClick(sicht, Qt.Key_Return)
    QTest.keyClick(sicht, Qt.Key_Period)
    assert empfangen == [("g", False, False, False), ("z", False, True, False),
                         ("return", False, False, False), (".", False, False, False)]


def test_rad_zoomt_und_home_zeigt_alles(qapp):
    sicht = _sicht()
    vorher = sicht.skala
    sicht.zoome(1.5, sicht.width() / 2, sicht.height() / 2)
    assert sicht.skala == pytest.approx(vorher * 1.5)
    QTest.keyClick(sicht, Qt.Key_Home)
    assert sicht.skala == pytest.approx(vorher)


def test_zeichnen_mit_allem_stuerzt_nicht(qapp):
    sicht = _sicht()
    sicht.setze_spur([(1, 1), (2, 1)])
    sicht.setze_anstoesse([(2.5, 1.0)])
    sicht.setze_pauspapier([(0.1 * i, 0.2) for i in range(50)])
    sicht.grab()          # rendert offscreen
    assert sicht.toleranz_m() > 0
```

- [ ] **Step 2: Rot**

- [ ] **Step 3: `sicht2d.py`**

```python
"""Die 2D-Sicht des Raumeditors: zeichnen, zoomen, schwenken -- und Ereignisse
in METERN an die Steuerung melden.

Kein Modell, keine Regeln: was ein Klick bedeutet, entscheidet `steuerung.py`.
Farben nur aus dem Theme.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from spotlab.gui.raumzeichnung import (
    zeichne_anstoesse, zeichne_raum, zeichne_spot, zeichne_spur,
)
from spotlab.welt.raum import huelle

RAND = 24
GRIFF_PX = 5
TOLERANZ_PX = 8
FEINES_RASTER_AB = 100.0          # Pixel je Meter, ab da 5-cm-Linien

TASTEN = {
    Qt.Key_Return: "return", Qt.Key_Enter: "return", Qt.Key_Escape: "escape",
    Qt.Key_Delete: "delete", Qt.Key_Backspace: "backspace", Qt.Key_Period: ".",
    Qt.Key_Comma: ".", Qt.Key_Minus: "-", Qt.Key_Tab: "tab",
}


class Sicht2D(QWidget):
    gedrueckt = Signal(float, float, str, bool, bool)
    bewegt = Signal(float, float, bool)
    losgelassen = Signal(float, float, bool, bool)
    taste_gedrueckt = Signal(str, bool, bool, bool)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self._raum = None
        self._auswahl = frozenset()
        self._griffe = []
        self._rahmen = None
        self._kette = None
        self._zeiger = None
        self._spur = []
        self._anstoesse = []
        self._pauspapier = []
        self.skala = 60.0             # Pixel je Meter
        self._ursprung = (RAND, 0.0)  # Pixel des Weltpunkts (0, 0); y wird gespiegelt
        self._schwenk = None

    # ------------------------------------------------------------ Fuellen

    def zeige(self, raum, auswahl=frozenset(), griffe=(), rahmen=None, kette=None):
        self._raum, self._auswahl = raum, frozenset(auswahl)
        self._griffe, self._rahmen, self._kette = list(griffe), rahmen, kette
        self.update()

    def setze_spur(self, punkte):
        self._spur = list(punkte)
        self.update()

    def setze_anstoesse(self, punkte):
        self._anstoesse = list(punkte)
        self.update()

    def setze_pauspapier(self, punkte):
        self._pauspapier = list(punkte)
        self.update()

    # -------------------------------------------------------- Umrechnung

    def meter_zu_schirm(self, x, y):
        return self._ursprung[0] + x * self.skala, self._ursprung[1] - y * self.skala

    def schirm_zu_meter(self, px, py):
        return (px - self._ursprung[0]) / self.skala, (self._ursprung[1] - py) / self.skala

    def toleranz_m(self):
        return TOLERANZ_PX / self.skala

    def alles_zeigen(self):
        if self._raum is None:
            return
        x0, y0, x1, y1 = huelle(self._raum)
        breite, hoehe = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        self.skala = min(max(self.width() - 2 * RAND, 1) / breite,
                         max(self.height() - 2 * RAND, 1) / hoehe)
        self._ursprung = ((self.width() - breite * self.skala) / 2 - x0 * self.skala,
                          (self.height() + hoehe * self.skala) / 2 + y0 * self.skala)
        self.update()

    def zoome(self, faktor, px, py):
        """Um den Bildschirmpunkt (px, py) zoomen -- der Punkt darunter bleibt stehen."""
        x, y = self.schirm_zu_meter(px, py)
        self.skala = max(5.0, min(2000.0, self.skala * faktor))
        self._ursprung = (px - x * self.skala, py + y * self.skala)
        self.update()

    # ------------------------------------------------------- Ereignisse

    @staticmethod
    def _tasten(ereignis):
        m = ereignis.modifiers()
        return bool(m & Qt.ShiftModifier), bool(m & Qt.ControlModifier), bool(m & Qt.AltModifier)

    def _punkt(self, ereignis):
        p = ereignis.position()
        return p.x(), p.y()

    def mousePressEvent(self, ereignis):
        self.setFocus()
        px, py = self._punkt(ereignis)
        if ereignis.button() == Qt.MiddleButton:
            self._schwenk = (px, py)
            return
        shift, ctrl, _alt = self._tasten(ereignis)
        taste = "rechts" if ereignis.button() == Qt.RightButton else "links"
        x, y = self.schirm_zu_meter(px, py)
        self.gedrueckt.emit(x, y, taste, shift, ctrl)

    def mouseMoveEvent(self, ereignis):
        px, py = self._punkt(ereignis)
        if self._schwenk is not None:
            dx, dy = px - self._schwenk[0], py - self._schwenk[1]
            self._ursprung = (self._ursprung[0] + dx, self._ursprung[1] + dy)
            self._schwenk = (px, py)
            self.update()
            return
        self._zeiger = (px, py)
        _shift, ctrl, _alt = self._tasten(ereignis)
        x, y = self.schirm_zu_meter(px, py)
        self.bewegt.emit(x, y, ctrl)
        if self._kette is not None:
            self.update()

    def mouseReleaseEvent(self, ereignis):
        if ereignis.button() == Qt.MiddleButton:
            self._schwenk = None
            return
        shift, ctrl, _alt = self._tasten(ereignis)
        x, y = self.schirm_zu_meter(*self._punkt(ereignis))
        self.losgelassen.emit(x, y, shift, ctrl)

    def wheelEvent(self, ereignis):
        schritte = ereignis.angleDelta().y() / 120.0
        p = ereignis.position()
        self.zoome(1.15 ** schritte, p.x(), p.y())

    def keyPressEvent(self, ereignis):
        taste = ereignis.key()
        if taste == Qt.Key_Home:
            self.alles_zeigen()
            return
        shift, ctrl, alt = self._tasten(ereignis)
        if taste in TASTEN:
            name = TASTEN[taste]
        elif Qt.Key_0 <= taste <= Qt.Key_9:
            name = chr(taste)
        elif Qt.Key_A <= taste <= Qt.Key_Z:
            name = chr(taste).lower()
        else:
            super().keyPressEvent(ereignis)
            return
        self.taste_gedrueckt.emit(name, shift, ctrl, alt)

    # ---------------------------------------------------------- Zeichnen

    def _raster(self, maler):
        x0, y0 = self.schirm_zu_meter(0, self.height())
        x1, y1 = self.schirm_zu_meter(self.width(), 0)
        schritte = [1.0]
        if self.skala >= FEINES_RASTER_AB:
            schritte.insert(0, 0.05)
        for schritt in schritte:
            farbe = QColor(self._p.rand)
            if schritt < 1.0:
                farbe.setAlpha(70)
            maler.setPen(QPen(farbe, 1))
            k = math.floor(x0 / schritt)
            while k * schritt <= x1:
                px, _ = self.meter_zu_schirm(k * schritt, 0)
                maler.drawLine(QPointF(px, 0), QPointF(px, self.height()))
                k += 1
            k = math.floor(y0 / schritt)
            while k * schritt <= y1:
                _, py = self.meter_zu_schirm(0, k * schritt)
                maler.drawLine(QPointF(0, py), QPointF(self.width(), py))
                k += 1

    def paintEvent(self, _ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        maler.fillRect(self.rect(), QColor(self._p.hintergrund))
        if self._raum is None:
            maler.setPen(QColor(self._p.gedaempft))
            maler.drawText(self.rect(), Qt.AlignCenter, "Kein Raum geöffnet.")
            return
        self._raster(maler)

        if self._pauspapier:
            farbe = QColor(self._p.gedaempft)
            farbe.setAlpha(120)
            maler.setPen(QPen(farbe, 2))
            for x, y in self._pauspapier:
                maler.drawPoint(QPointF(*self.meter_zu_schirm(x, y)))

        zeichne_raum(maler, self._raum, self.meter_zu_schirm, self.skala, self._p, self._auswahl)
        zeichne_spur(maler, self._spur, self.meter_zu_schirm, self._p)
        zeichne_anstoesse(maler, self._anstoesse, self.meter_zu_schirm, self._p)
        sx, sy, sgrad = self._raum.start
        px, py = self.meter_zu_schirm(sx, sy)
        zeichne_spot(maler, px, py, sgrad, self.skala, self._p, gewaehlt=("start",) in self._auswahl)

        maler.setPen(QPen(QColor(self._p.akzent), 1))
        maler.setBrush(QBrush(QColor(self._p.flaeche)))
        for _s, art, x, y in self._griffe:
            gx, gy = self.meter_zu_schirm(x, y)
            if art == "drehring":
                maler.drawEllipse(QPointF(gx, gy), GRIFF_PX + 1, GRIFF_PX + 1)
            else:
                maler.drawRect(QRectF(gx - GRIFF_PX, gy - GRIFF_PX, 2 * GRIFF_PX, 2 * GRIFF_PX))

        if self._rahmen is not None:
            x1, y1, x2, y2 = self._rahmen
            a, b_ = self.meter_zu_schirm(x1, y1), self.meter_zu_schirm(x2, y2)
            maler.setPen(QPen(QColor(self._p.akzent), 1, Qt.DashLine))
            maler.setBrush(Qt.NoBrush)
            maler.drawRect(QRectF(QPointF(*a), QPointF(*b_)).normalized())

        if self._kette is not None and self._zeiger is not None:
            maler.setPen(QPen(QColor(self._p.warnung), 2, Qt.DashLine))
            maler.drawLine(QPointF(*self.meter_zu_schirm(*self._kette)), QPointF(*self._zeiger))
```

- [ ] **Step 4: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumeditor_sicht2d.py`
- [ ] **Step 5: Commit** — `feat(raumeditor): 2D-Sicht -- zeichnen, zoomen, schwenken, Ereignisse in Metern`

---

### Task 11: Der Tab `RaumeditorView` — und `app.py` schaltet um

**Files:**
- Create: `src/spotlab/gui/raumeditor/tab.py`, `src/spotlab/gui/raumeditor/__init__.py`
- Modify: `src/spotlab/gui/app.py` (alle `"uebungsraum"`-Stellen: Import Z. 38, Dict Z. 97, Stapel Z. 104, `_verdrahte` Z. 141–153, `_setze_arbeitsordner` Z. 201, `_umgebung_fuer_lauf` Z. 308, `_oeffne_uebungsfenster` Z. 343–348, `_lauf_beendet` Z. 481), `src/spotlab/gui/sidebar.py:13`, `tests/test_gui_app.py` (Z. 110, 515–580)
- Test: `tests/test_gui_raumeditor.py`

**Interfaces:**
- Consumes: `Sicht2D` (Task 10), `Steuerung` (Task 9), `raum_laden/raum_speichern/raum_pfad/eigene_raeume/vorlagen`, `bearbeitung.FELDER/START/pruefe`
- Produces: `RaumeditorView(palette)` mit Signalen `meldung(str)`, `config_gespeichert(object)`, `start_gewuenscht()`; Methoden `setze_laeuft(bool)`, `setze_arbeitsordner(pfad)`, `setze_config(cfg)`, `waehle_raum(name)`, `raum()`, `raumname()`, `startpose()`, `lade(lauf_verzeichnis)`, `speichern()`, `speichern_unter()`, `neu()`; Attribute `steuerung`, `sicht`, `starten`, `liste`, `eigenschaften`, `hinweise`, `titel`, `werkzeuge` (QButtonGroup), `umschalter` (3D, in Etappe 1 grau). `app.py` benutzt den Schlüssel `"raumeditor"`.

- [ ] **Step 1: Tests** (`tests/test_gui_raumeditor.py`)

```python
"""Der Tab Raumeditor -- Qt-Haut ueber Steuerung und Sicht."""
import ast
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QInputDialog  # noqa: E402

from spotlab.config import Config, Limits  # noqa: E402
from spotlab.gui.raumeditor import RaumeditorView  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import raum_laden  # noqa: E402


def test_der_editor_importiert_nichts_verbotenes():
    wurzel = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "gui" / "raumeditor"
    verboten = ("bosdyn", "spotlab.backends", "mujoco", "spotsim", "OpenGL", "numpy")
    for datei in wurzel.glob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        namen = set()
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Import):
                namen.update(t.name for t in knoten.names)
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                namen.add(knoten.module)
        schlimm = [n for n in namen if any(n.startswith(v) for v in verboten)]
        assert not schlimm, f"{datei.name} importiert {schlimm}"


def test_die_schnittstelle_fuer_app_py_steht(qapp):
    ansicht = RaumeditorView(DUNKEL)
    for name in ("meldung", "config_gespeichert", "start_gewuenscht", "setze_laeuft",
                 "setze_arbeitsordner", "setze_config", "waehle_raum", "raum", "raumname",
                 "startpose", "lade", "starten"):
        assert hasattr(ansicht, name), name


def test_vorlage_laden_und_abfragen(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    assert ansicht.raum().name == "Möbliert" and ansicht.raumname() == "moebliert"
    assert ansicht.startpose() == raum_laden("moebliert").start
    assert ansicht.liste.count() == 4 + 3 + 2 + 1              # Waende, Bloecke, Tags, Start


def test_klick_in_der_sicht_waehlt_und_die_liste_folgt(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.resize(900, 600)
    ansicht.waehle_raum("moebliert")
    ansicht.sicht.alles_zeigen()
    px, py = ansicht.sicht.meter_zu_schirm(3.1, 1.8)              # der Tisch
    QTest.mouseClick(ansicht.sicht, Qt.LeftButton, Qt.NoModifier, QPoint(int(px), int(py)))
    tisch = next(i for i, b_ in enumerate(ansicht.raum().bloecke) if b_.name == "Tisch")
    assert ansicht.steuerung.auswahl == {("block", tisch)}
    gewaehlt = [w.data(Qt.UserRole) for w in ansicht.liste.selectedItems()]
    assert gewaehlt == [("block", tisch)]


def test_zahlenfeld_aendert_das_modell_und_setzt_den_stern(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    tisch = next(i for i, b_ in enumerate(ansicht.raum().bloecke) if b_.name == "Tisch")
    ansicht.steuerung.auswahl = frozenset({("block", tisch)})
    ansicht._zeige()
    feld = ansicht.eigenschaften.findChild(object, "feld_drehung")
    feld.setValue(30.0)
    feld.editingFinished.emit()
    assert ansicht.raum().bloecke[tisch].drehung == 30.0
    assert ansicht.steuerung.geaendert and "*" in ansicht.titel.text()


def test_speichern_unter_schreibt_die_datei_und_die_konfiguration(qapp, tmp_path, monkeypatch):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.setze_config(Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(tmp_path)))
    ansicht.waehle_raum("leer")
    gespeichert = []
    ansicht.config_gespeichert.connect(gespeichert.append)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("mein zimmer", True))
    ansicht.steuerung.setze_feld(("raum",), "beschreibung", "meins")
    ansicht.speichern()
    assert (tmp_path / "raeume" / "mein zimmer.toml").is_file()
    assert raum_laden("mein zimmer", workspace=tmp_path).beschreibung == "meins"
    assert ansicht.raumname() == "mein zimmer" and not ansicht.steuerung.geaendert
    assert gespeichert[-1].raum == "mein zimmer"


def test_ein_start_im_hindernis_wird_nicht_gestartet(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    ansicht.steuerung.setze_feld(("start",), "x", 3.1)
    ansicht.steuerung.setze_feld(("start",), "y", 1.8)               # im Tisch
    meldungen, starts = [], []
    ansicht.meldung.connect(meldungen.append)
    ansicht.start_gewuenscht.connect(lambda: starts.append(True))
    ansicht.starten.click()
    assert starts == [] and any("Tisch" in m for m in meldungen)


def test_der_startknopf_meldet_nur_den_wunsch_und_sichert_raum_und_start(qapp, tmp_path):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_config(Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(tmp_path)))
    ansicht.waehle_raum("durchgang")
    gespeichert, starts = [], []
    ansicht.config_gespeichert.connect(gespeichert.append)
    ansicht.start_gewuenscht.connect(lambda: starts.append(True))
    ansicht.starten.click()
    assert starts == [True]
    assert gespeichert[-1].raum == "durchgang" and gespeichert[-1].raum_start.startswith("1.00,2.00")


def test_der_knopf_wird_zum_stopp(qapp):
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_laeuft(True)
    assert "Stopp" in ansicht.starten.text()
    starts = []
    ansicht.start_gewuenscht.connect(lambda: starts.append(True))
    ansicht.starten.click()                                          # Stopp: der Wunsch geht raus
    assert starts == [True]
    ansicht.setze_laeuft(False)
    assert "starten" in ansicht.starten.text()


def test_lade_zeigt_raum_spur_und_anstoesse(qapp, tmp_path):
    lauf = tmp_path / "lauf"
    lauf.mkdir()
    (lauf / "ereignisse.jsonl").write_text(
        json.dumps({"t": 0, "art": "verbunden", "daten": {"raum": "moebliert"}}) + "\n"
        + json.dumps({"t": 1, "art": "angestossen", "daten": {"x": 2.0, "y": 1.0}}) + "\n",
        encoding="utf-8")
    (lauf / "zustand.jsonl").write_text(
        json.dumps({"t": 0, "daten": {"pose": [1.0, 1.0, 0.0]}}) + "\n"
        + json.dumps({"t": 1, "daten": {"pose": [1.5, 1.0, 0.0]}}) + "\n"
        + '{"t": 2, "daten": {"po',                                # halbe letzte Zeile
        encoding="utf-8")
    ansicht = RaumeditorView(DUNKEL)
    ansicht.lade(lauf)
    assert ansicht.raumname() == "moebliert"
    assert ansicht.sicht._spur == [(1.0, 1.0), (1.5, 1.0)]
    assert ansicht.sicht._anstoesse == [(2.0, 1.0)]


def test_das_nachspielen_ueberschreibt_keine_offenen_aenderungen(qapp, tmp_path):
    lauf = tmp_path / "lauf"
    lauf.mkdir()
    (lauf / "ereignisse.jsonl").write_text(
        json.dumps({"t": 0, "art": "verbunden", "daten": {"raum": "moebliert"}}) + "\n",
        encoding="utf-8")
    ansicht = RaumeditorView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    ansicht.steuerung.setze_feld(("raum",), "beschreibung", "in Arbeit")
    ansicht.lade(lauf)
    assert ansicht.raum().beschreibung == "in Arbeit"
```

In `tests/test_gui_app.py`: alle `"uebungsraum"` → `"raumeditor"`; in `test_der_virtuelle_lauf_bekommt_raum_und_start_der_ansicht` wird `fenster.ansichten["uebungsraum"]._start_gewaehlt(2.0, 1.0)` zu `fenster.ansichten["raumeditor"].steuerung.setze_feld(("start",), "x", 2.0)`.

- [ ] **Step 2: Rot** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumeditor.py` — ImportError.

- [ ] **Step 3: `__init__.py`**

```python
"""Der Raumeditor: Raeume bauen, in 2D sehen, darin fahren.

Ein Modell (`welt/raum.py`), eine Steuerung ohne Qt (`steuerung.py`), darueber
die Qt-Haut: `sicht2d.py` zeichnet und meldet Ereignisse in Metern, `tab.py`
haelt Werkzeuge, Liste, Eigenschaften und den Startknopf. Kein bosdyn, kein
`spotlab.backends`, kein mujoco -- dieselbe Regel wie ueberall unter gui/.
"""

from spotlab.gui.raumeditor.tab import RaumeditorView

__all__ = ["RaumeditorView"]
```

- [ ] **Step 4: `tab.py`**

```python
"""Der Tab „Raumeditor": Werkzeuge links, Sicht in der Mitte, Liste und
Eigenschaften rechts, der Startknopf unten.

Ersetzt die Ansicht „Übungsraum" und bietet app.py dieselbe Schnittstelle:
`meldung`, `config_gespeichert`, `start_gewuenscht`, `setze_laeuft`,
`setze_arbeitsordner`, `setze_config`, `waehle_raum`, `raum`, `raumname`,
`startpose`, `lade`. DER STARTKNOPF STARTET NICHT SELBST -- er meldet den Wunsch,
und app.py laesst den Editor starten: genau EIN Lauf ist der, auf den Stopp und
NOT-AUS zeigen.

Kein Modell hier: alles, was der Editor kann, steht in `steuerung.py` (ohne Qt).
Dieser Tab uebersetzt Knoepfe, Felder und Dialoge in Aufrufe dorthin.
"""

import json
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.raumeditor.sicht2d import Sicht2D
from spotlab.gui.raumeditor.steuerung import Steuerung
from spotlab.welt import bearbeitung as b
from spotlab.welt.raum import (
    Raum, eigene_raeume, raum_laden, raum_pfad, raum_speichern, vorlagen,
)

START_TEXT = "▶ Offene Datei starten"
STOPP_TEXT = "■ Stopp"
WERKZEUGE = (("auswahl", "Auswählen"), ("wand", "Wand"), ("block", "Block"),
             ("tag", "Tag"), ("start", "Start"))
NEUER_RAUM = Raum(
    name="Neuer Raum", beschreibung="", start=(1.0, 1.0, 0.0),
    waende=((0, 0, 6, 0), (6, 0, 6, 4), (6, 4, 0, 4), (0, 4, 0, 0)),
)
GRAD_FELDER = ("grad", "drehung")
TEXT_FELDER = ("name", "beschreibung")


def _zeilen(pfad):
    """jsonl lesen, halbe letzte Zeile ueberspringen (wie record/read.py)."""
    if not pfad.is_file():
        return []
    saetze = []
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            saetze.append(json.loads(zeile))
        except json.JSONDecodeError:
            continue
    return saetze


def _beschrifte(raum, schluessel):
    art = schluessel[0]
    if art == "wand":
        return f"Wand {schluessel[1] + 1}"
    if art == "block":
        return f"{raum.bloecke[schluessel[1]].name} (Block)"
    if art == "tag":
        return f"Tag {raum.tags[schluessel[1]].id}"
    return "Start"


class RaumeditorView(QWidget):
    meldung = Signal(str)
    config_gespeichert = Signal(object)
    start_gewuenscht = Signal()

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self._config = None
        self._arbeitsordner = None
        self._raumname = ""
        self._eigen = False          # liegt der Raum unter <arbeitsordner>/raeume?
        self._laeuft = False
        self._liste_sperre = False
        self.steuerung = Steuerung()

        # -- links: Werkzeuge und Dateien
        links = QVBoxLayout()
        self.werkzeuge = QButtonGroup(self)
        for name, text in WERKZEUGE:
            knopf = QPushButton(text)
            knopf.setCheckable(True)
            knopf.setObjectName(f"werkzeug_{name}")
            self.werkzeuge.addButton(knopf)
            knopf.clicked.connect(lambda _=False, n=name: self._werkzeug(n))
            links.addWidget(knopf)
        self.werkzeuge.buttons()[0].setChecked(True)
        links.addSpacing(12)
        for text, ziel in (("Neu", self.neu), ("Vorlage laden…", self._vorlage_laden),
                           ("Öffnen…", self._oeffnen), ("Speichern", self.speichern),
                           ("Speichern unter…", self.speichern_unter)):
            knopf = QPushButton(text)
            knopf.clicked.connect(ziel)
            links.addWidget(knopf)
        links.addStretch(1)

        # -- Mitte: Titel, Umschalter, Sicht
        self.titel = QLabel("")
        self.umschalter = QPushButton("3D")
        self.umschalter.setCheckable(True)
        self.umschalter.setEnabled(False)
        self.umschalter.setToolTip("Die 3D-Sicht kommt in der nächsten Etappe.")
        kopf = QHBoxLayout()
        kopf.addWidget(self.titel, 1)
        kopf.addWidget(self.umschalter)
        self.sicht = Sicht2D(palette)
        self.sicht.gedrueckt.connect(self._gedrueckt)
        self.sicht.bewegt.connect(self._bewegt)
        self.sicht.losgelassen.connect(self._losgelassen)
        self.sicht.taste_gedrueckt.connect(self._taste)
        mitte = QVBoxLayout()
        mitte.addLayout(kopf)
        mitte.addWidget(self.sicht, 1)

        # -- rechts: Liste, Eigenschaften, Hinweise
        self.liste = QListWidget()
        self.liste.setSelectionMode(QListWidget.ExtendedSelection)
        self.liste.itemSelectionChanged.connect(self._liste_gewaehlt)
        self.eigenschaften = QWidget()
        self._form = QFormLayout(self.eigenschaften)
        self.hinweise = QLabel("")
        self.hinweise.setWordWrap(True)
        self.hinweise.setObjectName("Gedaempft")
        rechts = QVBoxLayout()
        rechts.addWidget(QLabel("Elemente"))
        rechts.addWidget(self.liste, 2)
        rechts.addWidget(QLabel("Eigenschaften"))
        rechts.addWidget(self.eigenschaften, 1)
        rechts.addWidget(self.hinweise)

        self.starten = QPushButton(START_TEXT)
        self.starten.clicked.connect(self._start_klick)

        oben = QHBoxLayout()
        oben.addLayout(links)
        oben.addLayout(mitte, 4)
        oben.addLayout(rechts, 1)
        aussen = QVBoxLayout(self)
        aussen.addLayout(oben, 1)
        aussen.addWidget(self.starten)

        if vorlagen():
            self.waehle_raum(vorlagen()[0])

    # ---------------------------------------------------------- Zustand

    def setze_laeuft(self, laeuft):
        self._laeuft = laeuft
        self.starten.setText(STOPP_TEXT if laeuft else START_TEXT)

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = Path(pfad) if pfad else None

    def setze_config(self, cfg):
        self._config = cfg
        if cfg and cfg.raum and cfg.raum != self._raumname:
            self.waehle_raum(cfg.raum)

    # ------------------------------------------------------------- Raum

    def _setze(self, raum, name, eigen, geaendert):
        self._raumname, self._eigen = name, eigen
        self.steuerung.setze_raum(raum, geaendert=geaendert)
        self.sicht.setze_spur([])
        self.sicht.setze_anstoesse([])
        self.sicht.zeige(raum)
        self.sicht.alles_zeigen()
        self._zeige()

    def waehle_raum(self, name):
        if not name:
            return
        try:
            raum = raum_laden(name, workspace=self._arbeitsordner)
        except Exception as fehler:
            self.meldung.emit(str(fehler))
            return
        self._setze(raum, name, name in eigene_raeume(self._arbeitsordner), False)

    def neu(self):
        self._setze(NEUER_RAUM, "", False, True)

    def _vorlage_laden(self):
        name, ok = QInputDialog.getItem(self, "Vorlage laden", "Vorlage", vorlagen(), 0, False)
        if ok and name:
            self.waehle_raum(name)

    def _oeffnen(self):
        namen = eigene_raeume(self._arbeitsordner)
        if not namen:
            self.meldung.emit("Noch kein eigener Raum. Speichere zuerst einen unter „Speichern unter…“.")
            return
        name, ok = QInputDialog.getItem(self, "Raum öffnen", "Raum", namen, 0, False)
        if ok and name:
            self.waehle_raum(name)

    def raum(self):
        return self.steuerung.raum

    def raumname(self):
        return self._raumname

    def startpose(self):
        return self.steuerung.raum.start if self.steuerung.raum else None

    # ---------------------------------------------------------- Speichern

    def speichern(self):
        """True, wenn der Raum danach auf der Platte liegt."""
        if not self._eigen or not self._raumname:
            return self.speichern_unter()
        return self._schreibe(self._raumname)

    def speichern_unter(self):
        if self._arbeitsordner is None:
            self.meldung.emit("Kein Arbeitsordner gewählt — unter „Projekte“ einen wählen, dann speichern.")
            return False
        vorschlag = self._raumname if self._eigen else ""
        name, ok = QInputDialog.getText(self, "Raum speichern", "Name des Raums", text=vorschlag)
        name = (name or "").strip()
        if not ok or not name:
            return False
        if any(z in name for z in '/\\:*?"<>|'):
            self.meldung.emit("Der Name darf keine Pfadzeichen enthalten (/ \\ : * ? \" < > |).")
            return False
        return self._schreibe(name)

    def _schreibe(self, name):
        raum = self.steuerung.raum
        if raum is None:
            return False
        pfad = raum_pfad(self._arbeitsordner, name)
        try:
            raum_speichern(raum, pfad)
        except OSError as fehler:
            self.meldung.emit(f"Speichern nach {pfad} scheiterte: {fehler}")
            return False
        self._raumname, self._eigen = name, True
        self.steuerung.geaendert = False
        self._config_merken()
        self._zeige()
        self.meldung.emit(f"Gespeichert: {pfad}")
        return True

    def _config_merken(self):
        if self._config is None or not self._raumname:
            return
        x, y, grad = self.steuerung.raum.start
        self._config = replace(self._config, raum=self._raumname,
                               raum_start=f"{x:.2f},{y:.2f},{grad:.1f}")
        self.config_gespeichert.emit(self._config)

    # -------------------------------------------------------------- Lauf

    def _start_klick(self):
        if self._laeuft:
            self.start_gewuenscht.emit()          # derselbe Knopf heisst jetzt Stopp
            return
        if self.steuerung.raum is None:
            return
        im_weg = [h for h in self.steuerung.hinweise() if h.startswith("Der Start steht")]
        if im_weg:
            self.meldung.emit(im_weg[0])
            return
        if self.steuerung.geaendert and not self.speichern():
            return
        self._config_merken()
        self.start_gewuenscht.emit()

    def lade(self, lauf_verzeichnis):
        ordner = Path(lauf_verzeichnis)
        name, anstoesse = None, []
        for satz in _zeilen(ordner / "ereignisse.jsonl"):
            daten = satz.get("daten") or {}
            if satz.get("art") == "verbunden":
                name = daten.get("raum")
            elif satz.get("art") == "angestossen":
                anstoesse.append((daten.get("x", 0.0), daten.get("y", 0.0)))
        # Offene Aenderungen gehen vor: das Nachspielen eines Laufs darf die
        # Arbeit des Schuelers nicht ueberschreiben.
        if name and (name != self._raumname or not self.steuerung.geaendert):
            self.waehle_raum(name)
        spur = []
        for satz in _zeilen(ordner / "zustand.jsonl"):
            pose = (satz.get("daten") or {}).get("pose")
            if pose and len(pose) >= 2:
                spur.append((pose[0], pose[1]))
        self.sicht.setze_spur(spur)
        self.sicht.setze_anstoesse(anstoesse)

    # ------------------------------------------------------- Ereignisse

    def _werkzeug(self, name):
        self.steuerung.setze_werkzeug(name)
        self._zeige()

    def _gedrueckt(self, x, y, taste, shift, ctrl):
        self.steuerung.druecke(x, y, taste, shift, ctrl, toleranz=self.sicht.toleranz_m())
        self._zeige()

    def _bewegt(self, x, y, ctrl):
        self.steuerung.bewege(x, y, ctrl)
        self._zeige(nur_sicht=True)

    def _losgelassen(self, x, y, shift, ctrl):
        self.steuerung.lasse_los(x, y, shift, ctrl)
        self._zeige()

    def _taste(self, name, shift, ctrl, alt):
        if ctrl and name == "s":
            self.speichern()
            return
        if name == "tab":
            return                                 # 3D-Sicht: naechste Etappe
        self.steuerung.taste(name, shift, ctrl, alt)
        self._zeige()

    def _liste_gewaehlt(self):
        if self._liste_sperre:
            return
        self.steuerung.auswahl = frozenset(w.data(Qt.UserRole) for w in self.liste.selectedItems())
        self._zeige()

    def _feld_geaendert(self, schluessel, feld, widget):
        wert = widget.text() if isinstance(widget, QLineEdit) else widget.value()
        try:
            self.steuerung.setze_feld(schluessel, feld, wert)
        except ValueError as fehler:
            self.meldung.emit(str(fehler))
        self._zeige()

    # ---------------------------------------------------------- Anzeige

    def _zeige(self, nur_sicht=False):
        st = self.steuerung
        self.sicht.zeige(st.raum, st.auswahl, st.griffe(), st.rahmen, st.kette)
        if nur_sicht or st.raum is None:
            return
        self._fuelle_liste()
        self._fuelle_eigenschaften()
        hinweise = st.hinweise()
        self.hinweise.setText("\n".join(hinweise) if hinweise else "Keine Hinweise.")
        stern = " *" if st.geaendert else ""
        name = self._raumname or "ohne Namen"
        self.titel.setText(f"{st.raum.name} — {name}{stern}")

    def _fuelle_liste(self):
        st = self.steuerung
        self._liste_sperre = True
        try:
            self.liste.clear()
            for s in sorted(st.alle(), key=lambda k: (k[0] != "start", k)):
                eintrag = QListWidgetItem(_beschrifte(st.raum, s))
                eintrag.setData(Qt.UserRole, s)
                self.liste.addItem(eintrag)
                eintrag.setSelected(s in st.auswahl)
        finally:
            self._liste_sperre = False

    def _fuelle_eigenschaften(self):
        while self._form.rowCount():
            self._form.removeRow(0)
        st = self.steuerung
        if len(st.auswahl) > 1:
            self._form.addRow(QLabel(f"{len(st.auswahl)} Elemente gewählt"))
            return
        schluessel = next(iter(st.auswahl)) if st.auswahl else b.RAUM
        e = b.element(st.raum, schluessel)
        for feld in b.FELDER[schluessel[0]]:
            if schluessel[0] == "start":
                wert = {"x": e[0], "y": e[1], "grad": e[2]}[feld]
            else:
                wert = getattr(e, feld)
            if feld in TEXT_FELDER:
                widget = QLineEdit(str(wert))
            elif feld == "id":
                widget = QSpinBox()
                widget.setRange(0, 9999)
                widget.setValue(int(wert))
            else:
                widget = QDoubleSpinBox()
                widget.setDecimals(2)
                if feld in GRAD_FELDER:
                    widget.setRange(0.0, 360.0)
                    widget.setSingleStep(5.0)
                else:
                    widget.setRange(-1000.0, 1000.0)
                    widget.setSingleStep(0.05)
                widget.setValue(float(wert))
            widget.setObjectName(f"feld_{feld}")
            widget.editingFinished.connect(
                lambda s=schluessel, f=feld, w=widget: self._feld_geaendert(s, f, w))
            self._form.addRow(feld, widget)
```

- [ ] **Step 5: `sidebar.py`, `app.py`**

`sidebar.py:13`: `("raumeditor", "Raumeditor"),`. In `app.py`: `from spotlab.gui.raumeditor import RaumeditorView`; `"raumeditor": RaumeditorView(self._palette),`; in der Stapelreihenfolge `"raumeditor"`; jede `self.ansichten["uebungsraum"]` → `self.ansichten["raumeditor"]`; die Docstrings von `_umgebung_fuer_lauf` und `_starte_virtuell` sprechen vom Raumeditor („der Knopf im Raumeditor erzwingt das virtuelle Backend"). `views/uebungsraum.py` wird in Task 12 gelöscht.

- [ ] **Step 6: Grün** — Run: `python -m pytest -q -p no:cacheprovider tests/test_gui_raumeditor.py tests/test_gui_app.py`
- [ ] **Step 7: Commit** — `feat(gui): Tab Raumeditor ersetzt Uebungsraum -- Werkzeuge, Liste, Eigenschaften, Startknopf`

---

### Task 12: Aufräumen, Doku, Regeln, Abnahme, Suite

**Files:**
- Delete: `src/spotlab/gui/views/uebungsraum.py`, `tests/test_gui_uebungsraum.py`
- Modify: `README.md:160-216`, `CLAUDE.md` (Nicht verhandelbar, Tests, Umsetzungsstand), `docs/ABNAHME.md` (A23), `tests/test_welt_raum.py::test_nur_wahrnehmung_darf_numpy` (auch `bearbeitung.py` prüfen), `tests/test_naht_spotsim.py` (unverändert grün)

- [ ] **Step 1: Alte Ansicht entfernen**

```bash
git rm src/spotlab/gui/views/uebungsraum.py tests/test_gui_uebungsraum.py
grep -rn "uebungsraum\b\|UebungsraumView\|hindernisse\|Hindernis\b\|WAND_HOEHE_M\|TAG_HOEHE_M" src tests README.md CLAUDE.md docs/ABNAHME.md
```

Jeder verbliebene Treffer wird umgestellt (`views/__init__.py`, Doku); `uebungsfenster.py` behält seinen Namen und seine Regel.

- [ ] **Step 2: README** — Abschnitt „Übungsraum — ohne Roboter fahren" wird „Raumeditor — Räume bauen und ohne Roboter fahren": die Vorlagen-Tabelle bleibt; dazu ein Absatz zum Bauen (Werkzeuge Auswählen/Wand/Block/Tag/Start, Griffe, Zahlenfelder, eigene Räume unter `raeume/`), die Tastentabelle aus der Spec (Abschnitt 3), der Hinweis „Blöcke lassen sich drehen; in der Datei heissen sie `[[block]]`", und der Satz „Der Knopf **„▶ Offene Datei starten"** im Raumeditor speichert vorher, wenn nötig". In „Zuschauen, während es läuft" wird „Ansicht „Übungsraum"" zu „Raumeditor".

- [ ] **Step 3: CLAUDE.md** — unter „Nicht verhandelbar" anhängen:

```markdown
- **`welt/` bleibt Standardbibliothek — auch `bearbeitung.py`.** Das ist der Grund, warum
  die GUI es importieren darf (`tests/test_welt_raum.py`); numpy nur in `wahrnehmung.py`.
- **Der Raumeditor arbeitet auf unveränderlichen Räumen; Undo ist eine Liste von
  Schnappschüssen, kein Kommando-Muster.** Griffe, Blender-Tasten und Zahlenfelder rufen
  dieselben Funktionen aus `welt/bearbeitung.py`; die Steuerung (`gui/raumeditor/
  steuerung.py`) kennt keine Pixel und kein Qt — jeder Bedienfall ist ein Test ohne Fenster.
- **Drehung nach einem Prinzip:** ein Punkt wird in den Rahmen des Blocks gedreht
  (`Block.lokal`), danach rechnet alles achsparallel — Kollision, Gitter, 3D-Welt. Eine
  zweite Formulierung fiele erst auf, wenn ein Block in 2D trifft und in 3D nicht.
- **Der Startknopf im Raumeditor speichert vorher, wenn nötig, und lehnt einen Start im
  Hindernis ab** — `SPOTLAB_RAUM` ist ein Name, und ein Lauf in einem Raum, der so nicht
  auf der Platte liegt, wäre nicht nachspielbar.
```

Unter „Tests": „Der Raumeditor wird über `Steuerung` getestet (Meter, Tastennamen), die Qt-Tests prüfen nur die Haut: Klick → Auswahl, Feld → Modell, Speichern → Datei." Im „Umsetzungsstand" ein Absatz **Stufe 12 (06.09.2026): Raumeditor** (Etappe 1 von 3; 3D-Sicht und Rekonstruktion offen, Spec `docs/superpowers/specs/2026-09-06-raumeditor-design.md`).

- [ ] **Step 4: ABNAHME A23** — „Raum bauen und in 3D fahren": im Raumeditor aus `leer` einen Raum mit einem gedrehten Block bauen, speichern, `backend="mujoco"` starten, `move(forward=…)` gegen den gedrehten Block: `angestossen` nennt den Blocknamen, die Stelle liegt an der gedrehten Kante (Übungsfenster), das Tiefengitter zeigt den Block gedreht (`spot.obstacles().free_distance` in zwei Richtungen).

- [ ] **Step 5: Suite und Linter**

```bash
python -m ruff check src tests
python -m pytest -q -p no:cacheprovider --timeout=300
```

Erwartet: grün (matura-spot auf Branch `puppe-yaw` bzw. gemergt). Dann `superpowers:finishing-a-development-branch` für **beide** Repos: spotlab `raumeditor` → `main`, matura-spot `puppe-yaw` → `main`.

- [ ] **Step 6: Commit** — `docs: Raumeditor Etappe 1 -- README, Regeln, Abnahme A23; Uebungsraum-Ansicht entfernt`
