# spotlab Stufe 10 „Übungsraum" — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Schüler lässt sein Programm ohne Roboter durch ein gezeichnetes Zimmer fahren, sieht die Spur, stösst an Wände und findet AprilTags — mit den Zeiten des echten Geräts.

**Architecture:** Ein neues Modul `welt/` beantwortet rein geometrische Fragen (darf ich dorthin, was sehe ich von hier). `backends/sim.py` bekommt den Raum injiziert, prüft damit jeden Integrationsschritt und übersetzt das Rohergebnis in `Tag` und `ObstacleGrid`. Eine neue GUI-Ansicht liest den Raum und die Spur aus dem Lauf-Verzeichnis und zeichnet beides.

**Tech Stack:** Python 3.11+ (`tomllib` ist Standardbibliothek), numpy, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-spotlab-uebungsraum-design.md`

## Global Constraints

- **Meter und Grad, links positiv** — dieselben Einheiten wie `move(turn=…)`. Nie Radiant nach aussen.
- **`welt/` importiert nichts aus `backends/`, `api/`, `gui/` und kein `bosdyn`.** Es liefert rohe Geometrie; `sim.py` übersetzt in `Tag` und `ObstacleGrid`.
- **Kein Lease-Client und kein E-Stop-Endpunkt unterhalb von `welt/`** — dieselbe Regel wie für `maps/` und `beobachtung/`.
- **Kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `gui/`** (CLAUDE.md), auch nicht mittelbar.
- **Farben nur aus `gui/theme.py`** — ein Farbliteral im Widget-Code bricht den zweiten Hell/Dunkel-Modus.
- **Ohne Raum verhält sich `SimBackend` exakt wie heute.** Kein bestehender Test darf sich ändern müssen.
- **Fehlende Messwerte sind `None`, nie 0** — gilt hier für unbekannte Gitterzellen: unbekannt ist nicht frei.
- **Bezeichner englisch, Meldungen und Doku deutsch.** Ausnahme wie im Repo üblich: Datei- und Feldnamen der Aufzeichnung sind deutsch.
- **`ruff check .` muss grün sein**, und zwar vor den Tests.
- Jeder Task endet mit einem Commit. Commit-Botschaften deutsch, ohne Umlaute.

### Begründete Abweichung von der Spec

§2 der Spec sagt, `welt/` halte sich auf „Standardbibliothek plus `tomllib`". Beim Planen zeigte sich: `abstandsgitter()` rechnet 128 × 128 = **16 384 Zellen** gegen rund zehn Hindernisse. In reinem Python sind das ~164 000 Abstandsrechnungen, gemessen an vergleichbaren Schleifen rund 0.2 s je Abruf — bei 2 Hz ein Drittel eines Kerns für eine Übungsumgebung.

Die Regel wird deshalb **innerhalb von `welt/` geschärft** statt gelockert:

| Datei | erlaubt | wer importiert es |
|---|---|---|
| `welt/raum.py` | nur stdlib + `tomllib` | `sim.py` **und die GUI** |
| `welt/kollision.py` | nur stdlib | `sim.py` |
| `welt/wahrnehmung.py` | stdlib + **numpy** | nur `sim.py` |

Die GUI importiert ausschliesslich `welt/raum.py` und zieht damit weiterhin nichts Schweres herein. Die Zusicherung „kein Qt, kein bosdyn, kein `backends`, kein `api`" gilt unverändert für alle drei. **Task 1 schreibt das als Test fest**, und Task 10 zieht die Spec-Zeile nach.

---

## File Structure

| Datei | Verantwortung | Task |
|---|---|---|
| `src/spotlab/welt/__init__.py` | leer, Paketmarke | 1 |
| `src/spotlab/welt/raum.py` | Datenklassen, TOML laden, Suchreihenfolge | 1 |
| `src/spotlab/welt/vorlagen/*.toml` | leer, moebliert, durchgang | 1 |
| `src/spotlab/welt/kollision.py` | frei / bewege / sicht_frei | 2 |
| `src/spotlab/welt/wahrnehmung.py` | sichtbare Tags, Abstandsgitter | 3 |
| `src/spotlab/backends/sim.py` | Raum einhängen, übersetzen, Anstoss melden | 4 |
| `src/spotlab/config.py` | Felder `raum`, `raum_start` | 5 |
| `src/spotlab/__init__.py` | `connect(raum=…)` | 5 |
| `src/spotlab/gui/raumplot.py` | zeichnet Raum, Spur, Spot | 6 |
| `src/spotlab/gui/views/uebungsraum.py` | Ansicht: wählen, ansehen, starten | 7 |
| `src/spotlab/gui/app.py`, `sidebar.py` | neunte Ansicht registrieren | 7 |
| `README.md`, `spotlab new`-Vorlage | Doku und Beispielprogramm | 9 |

---

## Task 1: Der Raum und seine Vorlagen

**Files:**
- Create: `src/spotlab/welt/__init__.py`, `src/spotlab/welt/raum.py`
- Create: `src/spotlab/welt/vorlagen/leer.toml`, `moebliert.toml`, `durchgang.toml`
- Test: `tests/test_welt_raum.py`

**Interfaces:**
- Consumes: nichts
- Produces: `Raum(name, beschreibung, groesse, start, waende, hindernisse, tags)`, `Hindernis(name, rechteck)`, `RaumTag(id, x, y, grad)`, `raum_laden(name, workspace=None) -> Raum`, `vorlagen() -> list[str]`

- [ ] **Step 1: Write the failing test**

`tests/test_welt_raum.py`:

```python
import pytest

from spotlab.errors import SpotlabError
from spotlab.welt.raum import Raum, raum_laden, vorlagen

BEISPIEL = '''
[raum]
name         = "Prüfraum"
beschreibung = "Nur zum Testen."
groesse      = [4.0, 3.0]
start        = [0.5, 0.5, 90.0]
waende = [
    [0.0, 0.0, 4.0, 0.0],
    [4.0, 0.0, 4.0, 3.0],
]
hindernisse = [
    { name = "Kiste", rechteck = [1.0, 1.0, 0.5, 0.5] },
]

[[tag]]
id = 7
pose = [3.9, 1.5, 180.0]
'''


def _schreibe(ordner, name, inhalt=BEISPIEL):
    raeume = ordner / "raeume"
    raeume.mkdir(parents=True, exist_ok=True)
    (raeume / f"{name}.toml").write_text(inhalt, encoding="utf-8")
    return ordner


def test_laedt_alle_felder(tmp_path):
    raum = raum_laden("pruefraum", workspace=_schreibe(tmp_path, "pruefraum"))
    assert isinstance(raum, Raum)
    assert raum.name == "Prüfraum"
    assert raum.groesse == (4.0, 3.0)
    assert raum.start == (0.5, 0.5, 90.0)
    assert len(raum.waende) == 2
    assert raum.hindernisse[0].name == "Kiste"
    assert raum.hindernisse[0].rechteck == (1.0, 1.0, 0.5, 0.5)
    assert raum.tags[0].id == 7
    assert raum.tags[0].grad == 180.0


def test_arbeitsordner_geht_vor_paket(tmp_path):
    """Eigene Raeume sollen die mitgelieferten ueberschreiben koennen."""
    eigen = BEISPIEL.replace('name         = "Prüfraum"', 'name         = "Eigener"')
    raum = raum_laden("leer", workspace=_schreibe(tmp_path, "leer", eigen))
    assert raum.name == "Eigener"


def test_ohne_arbeitsordner_kommt_die_vorlage():
    raum = raum_laden("leer")
    assert raum.name
    assert len(raum.waende) >= 4


def test_unbekannter_raum_nennt_die_vorhandenen():
    with pytest.raises(SpotlabError) as fehler:
        raum_laden("gibtsnicht")
    text = str(fehler.value)
    assert "gibtsnicht" in text
    assert "leer" in text and "moebliert" in text and "durchgang" in text


def test_fehlendes_feld_nennt_das_feld(tmp_path):
    ohne = BEISPIEL.replace("groesse      = [4.0, 3.0]\n", "")
    with pytest.raises(SpotlabError) as fehler:
        raum_laden("kaputt", workspace=_schreibe(tmp_path, "kaputt", ohne))
    assert "groesse" in str(fehler.value)


def test_kaputtes_toml_wird_uebersetzt(tmp_path):
    with pytest.raises(SpotlabError):
        raum_laden("murks", workspace=_schreibe(tmp_path, "murks", "das ist kein toml ["))


@pytest.mark.parametrize("name", ["leer", "moebliert", "durchgang"])
def test_jede_vorlage_ist_geometrisch_stimmig(name):
    """Was ohne kollision.py pruefbar ist. Die Frage, ob die Startpose FREI
    liegt, kommt in Task 2 dazu -- sie braucht den Roboterradius."""
    raum = raum_laden(name)
    breite, hoehe = raum.groesse
    x, y, _grad = raum.start
    assert 0 < x < breite and 0 < y < hoehe, "Start liegt ausserhalb"
    assert raum.tags, "jede Vorlage soll mindestens einen Tag haben"
    for tag in raum.tags:
        assert 0 <= tag.x <= breite and 0 <= tag.y <= hoehe


def test_vorlagen_nennt_die_drei():
    assert sorted(vorlagen()) == ["durchgang", "leer", "moebliert"]


# ------------------------------------------------------- die Schichtregel


def test_welt_importiert_nichts_verbotenes():
    """welt/ ist reine Geometrie. Ein Import aus backends/ oder api/ waere der
    Anfang eines Kreises, und Qt oder bosdyn machten es untestbar."""
    import ast
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "welt"
    verboten = ("bosdyn", "PySide6", "spotlab.backends", "spotlab.api", "spotlab.gui")
    for datei in wurzel.rglob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        namen = set()
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Import):
                namen.update(t.name for t in knoten.names)
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                namen.add(knoten.module)
        schlimm = [n for n in namen if any(n.startswith(v) for v in verboten)]
        assert not schlimm, f"{datei.name} importiert {schlimm}"


def test_nur_wahrnehmung_darf_numpy():
    """raum.py wird von der GUI importiert und bleibt deshalb leichtgewichtig.

    Ueber `ast`, nicht als Textsuche: der Docstring von raum.py ERWAEHNT numpy,
    um zu begruenden, warum es dort fehlt. Eine Substring-Pruefung schluege
    daran an und pruefte die Dokumentation statt des Codes.
    """
    import ast
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "welt"
    for datei in ("raum.py", "kollision.py"):
        pfad = wurzel / datei
        if not pfad.is_file():
            continue          # kollision.py kommt in Task 2 dazu
        namen = set()
        for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            if isinstance(knoten, ast.Import):
                namen.update(t.name for t in knoten.names)
            elif isinstance(knoten, ast.ImportFrom) and knoten.module:
                namen.add(knoten.module)
        assert not [n for n in namen if n.split(".")[0] == "numpy"],             f"{datei} soll ohne numpy auskommen"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_welt_raum.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'spotlab.welt'`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/welt/__init__.py`: leer lassen (nur Paketmarke).

`src/spotlab/welt/raum.py`:

```python
"""Ein Zimmer als Geometrie: Waende, Hindernisse, Tags.

Reine Standardbibliothek. Das ist kein Zufall, sondern der Grund, warum die GUI
dieses Modul importieren darf: es zieht weder Qt noch bosdyn noch numpy herein,
und die Regel "kein spotlab.backends unterhalb von gui/" bleibt unberuehrt.

Einheiten wie in der Schueler-API: Meter und GRAD, links positiv. Wer
`spot.move(turn=90)` kennt, liest eine Raumdatei ohne Umrechnung.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from spotlab.errors import SpotlabError

VORLAGEN = Path(__file__).parent / "vorlagen"


@dataclass(frozen=True)
class Hindernis:
    name: str
    rechteck: tuple      # (x, y, breite, hoehe), achsparallel, Meter


@dataclass(frozen=True)
class RaumTag:
    id: int
    x: float
    y: float
    grad: float          # Blickrichtung des Tags


@dataclass(frozen=True)
class Raum:
    name: str
    beschreibung: str
    groesse: tuple       # (breite, hoehe) in Metern
    start: tuple         # (x, y, grad)
    waende: tuple        # ((x1, y1, x2, y2), …)
    hindernisse: tuple
    tags: tuple


def vorlagen():
    """Die mitgelieferten Raeume, ohne Endung."""
    return sorted(p.stem for p in VORLAGEN.glob("*.toml"))


def _pfad(name, workspace):
    if workspace:
        eigen = Path(workspace) / "raeume" / f"{name}.toml"
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


def _feld(daten, name, pfad):
    if name not in daten:
        raise SpotlabError(f"In {pfad.name} fehlt das Feld '{name}' unter [raum].")
    return daten[name]


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

    hindernisse = tuple(
        Hindernis(name=str(h.get("name", "Hindernis")), rechteck=tuple(h["rechteck"]))
        for h in daten.get("hindernisse", [])
    )
    tags = tuple(
        RaumTag(id=int(t["id"]), x=float(t["pose"][0]),
                y=float(t["pose"][1]), grad=float(t["pose"][2]))
        for t in roh.get("tag", [])
    )
    return Raum(
        name=str(_feld(daten, "name", pfad)),
        beschreibung=str(daten.get("beschreibung", "")),
        groesse=tuple(float(w) for w in _feld(daten, "groesse", pfad)),
        start=tuple(float(w) for w in _feld(daten, "start", pfad)),
        waende=tuple(tuple(float(w) for w in wand)
                     for wand in _feld(daten, "waende", pfad)),
        hindernisse=hindernisse,
        tags=tags,
    )
```

`src/spotlab/welt/vorlagen/leer.toml`:

```toml
[raum]
name         = "Leer"
beschreibung = "Vier Wände, ein Tag. Für die ersten Schritte."
groesse      = [5.0, 4.0]
start        = [1.0, 1.0, 0.0]
waende = [
    [0.0, 0.0, 5.0, 0.0],
    [5.0, 0.0, 5.0, 4.0],
    [5.0, 4.0, 0.0, 4.0],
    [0.0, 4.0, 0.0, 0.0],
]
hindernisse = []

[[tag]]
id = 1
pose = [4.9, 2.0, 180.0]
```

`src/spotlab/welt/vorlagen/moebliert.toml`:

```toml
[raum]
name         = "Möbliert"
beschreibung = "Ein Zimmer mit Tisch und zwei Stuhlstapeln."
groesse      = [6.0, 4.0]
start        = [1.0, 1.0, 0.0]
waende = [
    [0.0, 0.0, 6.0, 0.0],
    [6.0, 0.0, 6.0, 4.0],
    [6.0, 4.0, 0.0, 4.0],
    [0.0, 4.0, 0.0, 0.0],
]
hindernisse = [
    { name = "Tisch",         rechteck = [2.5, 1.4, 1.2, 0.8] },
    { name = "Stuhlstapel A", rechteck = [4.6, 2.9, 0.6, 0.6] },
    { name = "Stuhlstapel B", rechteck = [1.4, 2.9, 0.6, 0.6] },
]

[[tag]]
id = 1
pose = [5.9, 2.0, 180.0]

[[tag]]
id = 2
pose = [3.1, 3.9, 270.0]
```

`src/spotlab/welt/vorlagen/durchgang.toml` — zwei Zimmer, Lücke von y=1.5 bis
y=2.4 (0.9 m):

```toml
[raum]
name         = "Durchgang"
beschreibung = "Zwei Zimmer, verbunden durch eine Tür. Der Tag liegt drüben."
groesse      = [9.0, 4.0]
start        = [1.0, 2.0, 0.0]
waende = [
    [0.0, 0.0, 9.0, 0.0],
    [9.0, 0.0, 9.0, 4.0],
    [9.0, 4.0, 0.0, 4.0],
    [0.0, 4.0, 0.0, 0.0],
    [4.5, 0.0, 4.5, 1.5],
    [4.5, 2.4, 4.5, 4.0],
]
hindernisse = [
    { name = "Kiste", rechteck = [2.0, 2.8, 0.7, 0.7] },
]

[[tag]]
id = 3
pose = [8.9, 2.0, 180.0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_welt_raum.py -q`
Expected: PASS, alle Tests. Task 1 endet vollständig grün — die Prüfung, ob die
Startpose auch *frei* liegt, kommt in Task 2 dazu, weil sie den Roboterradius
braucht.

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/welt tests/test_welt_raum.py
git commit -m "feat(welt): Raum-Datenmodell, drei Vorlagen, Schichtregel als Test"
```

---

## Task 2: Kollision

**Files:**
- Create: `src/spotlab/welt/kollision.py`
- Test: `tests/test_welt_kollision.py`

**Interfaces:**
- Consumes: `Raum`, `Hindernis` aus Task 1
- Produces: `ROBOTER_RADIUS_M = 0.35`, `MAX_SCHRITT_M = 0.10`, `frei(raum, x, y) -> bool`, `bewege(raum, von, nach) -> (pose, hindernis_name|None)`, `sicht_frei(raum, a, b) -> bool`

- [ ] **Step 1: Write the failing test**

`tests/test_welt_kollision.py`:

```python
import pytest

from spotlab.welt.kollision import (
    MAX_SCHRITT_M,
    ROBOTER_RADIUS_M,
    bewege,
    frei,
    sicht_frei,
)
from spotlab.welt.raum import Hindernis, Raum

# Ein 10 x 10 m grosser Kasten mit einer Kiste in der Mitte.
RAUM = Raum(
    name="T", beschreibung="", groesse=(10.0, 10.0), start=(1.0, 1.0, 0.0),
    waende=(
        (0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0),
        (10.0, 10.0, 0.0, 10.0), (0.0, 10.0, 0.0, 0.0),
    ),
    hindernisse=(Hindernis("Kiste", (5.0, 5.0, 1.0, 1.0)),),
    tags=(),
)


def test_mitte_ist_frei():
    assert frei(RAUM, 2.0, 2.0)


def test_zu_nah_an_der_wand_ist_nicht_frei():
    assert not frei(RAUM, ROBOTER_RADIUS_M - 0.01, 5.0)
    assert frei(RAUM, ROBOTER_RADIUS_M + 0.01, 5.0)


def test_im_hindernis_ist_nicht_frei():
    assert not frei(RAUM, 5.5, 5.5)


def test_knapp_neben_dem_hindernis_ist_nicht_frei():
    """Der Roboter ist ein Kreis -- der Rand zaehlt, nicht der Mittelpunkt."""
    assert not frei(RAUM, 5.0 - ROBOTER_RADIUS_M + 0.05, 5.5)
    assert frei(RAUM, 5.0 - ROBOTER_RADIUS_M - 0.05, 5.5)


def test_freie_fahrt_kommt_an():
    pose, angestossen = bewege(RAUM, (2.0, 2.0, 0.0), (2.5, 2.0, 0.0))
    assert pose[:2] == pytest.approx((2.5, 2.0))
    assert angestossen is None


def test_fahrt_in_die_wand_bleibt_stehen_und_nennt_das_hindernis():
    pose, angestossen = bewege(RAUM, (1.0, 5.0, 0.0), (0.1, 5.0, 0.0))
    assert angestossen == "Wand"
    assert pose[0] > 0.1, "darf nicht bis ins Ziel gefahren sein"
    assert frei(RAUM, pose[0], pose[1]), "muss an einer erlaubten Stelle stehen"


def test_fahrt_in_die_kiste_nennt_ihren_namen():
    _pose, angestossen = bewege(RAUM, (3.0, 5.5, 0.0), (5.5, 5.5, 0.0))
    assert angestossen == "Kiste"


def test_langer_schritt_wird_zerlegt():
    """Ohne Zerlegung springt ein Programm mit langem dt durch die Wand."""
    weit = 3.0
    assert weit > 2 * ROBOTER_RADIUS_M
    pose, angestossen = bewege(RAUM, (2.0, 5.0, 0.0), (2.0 - weit, 5.0, 0.0))
    assert angestossen == "Wand"
    assert pose[0] >= ROBOTER_RADIUS_M - 0.01, "durch die Wand gerutscht"


def test_drehen_in_der_ecke_bleibt_erlaubt():
    """Ein Kreis, der sich dreht, ueberstreicht keine neue Flaeche."""
    ecke = (ROBOTER_RADIUS_M + 0.01, ROBOTER_RADIUS_M + 0.01, 0.0)
    pose, angestossen = bewege(RAUM, ecke, (ecke[0], ecke[1], 3.14))
    assert angestossen is None
    assert pose[2] == pytest.approx(3.14)


def test_teilstrecke_bis_kurz_vor_das_hindernis():
    """Nicht am Startpunkt kleben bleiben: was frei ist, wird gefahren."""
    pose, _ = bewege(RAUM, (1.0, 5.0, 0.0), (0.0, 5.0, 0.0))
    assert pose[0] < 1.0 - MAX_SCHRITT_M


@pytest.mark.parametrize("name", ["leer", "moebliert", "durchgang"])
def test_jede_vorlage_hat_eine_freie_startpose(name):
    """Eine Vorlage mit Startpose in einer Wand waere im Unterricht ein Raetsel.
    Ergaenzt test_jede_vorlage_ist_geometrisch_stimmig aus Task 1."""
    from spotlab.welt.raum import raum_laden

    raum = raum_laden(name)
    x, y, _grad = raum.start
    assert frei(raum, x, y), "Start liegt in einer Wand oder einem Hindernis"


def test_durchgang_ist_breiter_als_der_roboter():
    """0.9 m Luecke gegen 0.70 m Durchmesser -- 10 cm Spiel je Seite."""
    from spotlab.welt.raum import raum_laden

    raum = raum_laden("durchgang")
    senkrechte = [w for w in raum_laden("durchgang").waende if w[0] == w[2]]
    auf_x = {}
    for x1, y1, _x2, y2 in senkrechte:
        auf_x.setdefault(x1, []).append((min(y1, y2), max(y1, y2)))
    luecken = []
    for stuecke in auf_x.values():
        stuecke.sort()
        for (_a1, a2), (b1, _b2) in zip(stuecke, stuecke[1:]):
            if b1 > a2:
                luecken.append(b1 - a2)
    assert luecken, "durchgang.toml hat keine Luecke"
    assert max(luecken) >= 2 * ROBOTER_RADIUS_M + 0.15
    assert raum.name


def test_sichtlinie_durch_den_freien_raum():
    assert sicht_frei(RAUM, (1.0, 1.0), (3.0, 1.0))


def test_sichtlinie_durch_ein_hindernis_ist_versperrt():
    assert not sicht_frei(RAUM, (3.0, 5.5), (8.0, 5.5))


def test_sichtlinie_knapp_am_hindernis_vorbei():
    assert sicht_frei(RAUM, (3.0, 4.5), (8.0, 4.5))


def test_beruehrende_und_parallele_strecken():
    """Grenzfaelle der Schnittpruefung -- hier entstehen die stillen Fehler."""
    parallel = Raum(
        name="P", beschreibung="", groesse=(10.0, 10.0), start=(1.0, 1.0, 0.0),
        waende=((2.0, 0.0, 2.0, 10.0),), hindernisse=(), tags=(),
    )
    assert not sicht_frei(parallel, (1.0, 1.0), (3.0, 1.0))   # kreuzt
    assert sicht_frei(parallel, (3.0, 1.0), (5.0, 1.0))       # dahinter, kreuzt nicht
    assert sicht_frei(parallel, (0.5, 1.0), (1.5, 1.0))       # davor, kreuzt nicht
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_welt_kollision.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'spotlab.welt.kollision'`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/welt/kollision.py`:

```python
"""Darf der Roboter dorthin, und was sieht er von hier aus?

Reine Standardbibliothek, keine Physik -- Abstaende zwischen Punkten, Strecken
und achsparallelen Rechtecken. Was daraus eine spotlab-Form macht, tut
`backends/sim.py`.

DER ROBOTER IST EIN KREIS mit 0.35 m Radius, abgeleitet aus Spots Grundflaeche
(rund 1.1 x 0.5 m). Die Vereinfachung ist bewusst und hat eine Richtung: ein
Kreis kann sich nicht seitlich durch eine schmale Luecke drehen, ein echter Spot
schon. Der Sim bleibt damit eher zu vorsichtig als zu optimistisch -- ausser
beim Drehen (siehe `bewege`).
"""

import math

ROBOTER_RADIUS_M = 0.35
# Laengere Schritte werden zerlegt. `dt` kommt aus der Wanduhr und haengt daran,
# wie oft ein Skript den Zustand abfragt; ohne Zerlegung haenge die Zusicherung
# "kein Programm faehrt durch eine Wand" an der Abfragehaeufigkeit.
MAX_SCHRITT_M = 0.10


def _abstand_punkt_strecke(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    laenge2 = dx * dx + dy * dy
    if laenge2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / laenge2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _abstand_punkt_rechteck(px, py, x, y, breite, hoehe):
    dx = max(x - px, 0.0, px - (x + breite))
    dy = max(y - py, 0.0, py - (y + hoehe))
    return math.hypot(dx, dy)


def hindernis_bei(raum, x, y, radius=ROBOTER_RADIUS_M):
    """Name dessen, was hier im Weg steht -- oder None."""
    for wand in raum.waende:
        if _abstand_punkt_strecke(x, y, *wand) < radius:
            return "Wand"
    for hindernis in raum.hindernisse:
        if _abstand_punkt_rechteck(x, y, *hindernis.rechteck) < radius:
            return hindernis.name
    return None


def frei(raum, x, y, radius=ROBOTER_RADIUS_M):
    return hindernis_bei(raum, x, y, radius) is None


def bewege(raum, von, nach):
    """(neue Pose, Name des Hindernisses oder None).

    Die DREHUNG wird immer uebernommen: ein Kreis, der sich dreht, ueberstreicht
    keine neue Flaeche. Ein Spot in einer Ecke kann sich also herausdrehen -- was
    er in Wirklichkeit auch kann, wenn auch nicht so muehelos.
    """
    x0, y0, _yaw0 = von
    x1, y1, yaw1 = nach
    strecke = math.hypot(x1 - x0, y1 - y0)
    if strecke < 1e-9:
        return (x0, y0, yaw1), None

    schritte = max(1, math.ceil(strecke / MAX_SCHRITT_M))
    letztes_gutes = (x0, y0)
    for i in range(1, schritte + 1):
        anteil = i / schritte
        px = x0 + (x1 - x0) * anteil
        py = y0 + (y1 - y0) * anteil
        getroffen = hindernis_bei(raum, px, py)
        if getroffen is not None:
            return (letztes_gutes[0], letztes_gutes[1], yaw1), getroffen
        letztes_gutes = (px, py)
    return (x1, y1, yaw1), None


def _schneiden(a1, a2, b1, b2):
    """Kreuzen sich die Strecken a und b?"""
    def kreuz(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    d1, d2 = kreuz(b1, b2, a1), kreuz(b1, b2, a2)
    d3, d4 = kreuz(a1, a2, b1), kreuz(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def sicht_frei(raum, a, b):
    """Freie Sichtlinie von a nach b? Waende und Hindernisse verdecken."""
    for x1, y1, x2, y2 in raum.waende:
        if _schneiden(a, b, (x1, y1), (x2, y2)):
            return False
    for hindernis in raum.hindernisse:
        x, y, breite, hoehe = hindernis.rechteck
        ecken = [(x, y), (x + breite, y), (x + breite, y + hoehe), (x, y + hoehe)]
        for erste, zweite in zip(ecken, ecken[1:] + ecken[:1]):
            if _schneiden(a, b, erste, zweite):
                return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_welt_kollision.py tests/test_welt_raum.py -q`
Expected: PASS — beide Dateien, jetzt auch `test_jede_vorlage_ist_stimmig` und `test_durchgang_ist_breiter_als_der_roboter` aus Task 1.

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/welt/kollision.py tests/test_welt_kollision.py
git commit -m "feat(welt): Kollision mit Schrittzerlegung; Drehen bleibt erlaubt"
```

---

## Task 3: Wahrnehmung aus der Geometrie

**Files:**
- Create: `src/spotlab/welt/wahrnehmung.py`
- Test: `tests/test_welt_wahrnehmung.py`

**Interfaces:**
- Consumes: Task 1 und 2 (`sicht_frei`, `hindernis_bei`)
- Produces: `TAG_REICHWEITE_M = 3.0`, `GITTER_ZELLEN = 128`, `GITTER_ZELLE_M = 0.03`, `sichtbare_tags(raum, pose) -> [(RaumTag, dx, dy)]` (Körperframe), `abstandsgitter(raum, pose) -> (werte, bekannt, ursprung)`

- [ ] **Step 1: Write the failing test**

`tests/test_welt_wahrnehmung.py`:

```python
import math

import pytest

from spotlab.welt.wahrnehmung import (
    GITTER_ZELLE_M,
    GITTER_ZELLEN,
    TAG_REICHWEITE_M,
    abstandsgitter,
    sichtbare_tags,
)
from spotlab.welt.raum import Hindernis, Raum, RaumTag


def _raum(tags=(), hindernisse=()):
    return Raum(
        name="T", beschreibung="", groesse=(10.0, 10.0), start=(1.0, 1.0, 0.0),
        waende=(
            (0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0),
            (10.0, 10.0, 0.0, 10.0), (0.0, 10.0, 0.0, 0.0),
        ),
        hindernisse=tuple(hindernisse), tags=tuple(tags),
    )


def test_tag_in_reichweite_wird_gemeldet():
    raum = _raum(tags=(RaumTag(1, 6.0, 5.0, 180.0),))
    gefunden = sichtbare_tags(raum, (5.0, 5.0, 0.0))
    assert len(gefunden) == 1
    tag, dx, dy = gefunden[0]
    assert tag.id == 1
    assert dx == pytest.approx(1.0)      # direkt voraus im Koerperframe
    assert dy == pytest.approx(0.0, abs=1e-9)


def test_koerperframe_dreht_mit():
    """Derselbe Tag, Spot um 90 Grad gedreht: aus 'voraus' wird 'rechts'."""
    raum = _raum(tags=(RaumTag(1, 6.0, 5.0, 180.0),))
    _tag, dx, dy = sichtbare_tags(raum, (5.0, 5.0, math.pi / 2))[0]
    assert dx == pytest.approx(0.0, abs=1e-9)
    assert dy == pytest.approx(-1.0)


def test_tag_ausser_reichweite_wird_nicht_gemeldet():
    zu_weit = 5.0 + TAG_REICHWEITE_M + 0.1
    raum = _raum(tags=(RaumTag(1, zu_weit, 5.0, 180.0),))
    assert sichtbare_tags(raum, (5.0, 5.0, 0.0)) == []


def test_tag_hinter_einem_hindernis_wird_nicht_gemeldet():
    raum = _raum(
        tags=(RaumTag(1, 7.0, 5.0, 180.0),),
        hindernisse=(Hindernis("Kiste", (6.0, 4.5, 0.4, 1.0)),),
    )
    assert sichtbare_tags(raum, (5.0, 5.0, 0.0)) == []


def test_naechster_tag_steht_vorne():
    raum = _raum(tags=(
        RaumTag(2, 7.5, 5.0, 180.0),
        RaumTag(1, 6.0, 5.0, 180.0),
    ))
    assert [t.id for t, _dx, _dy in sichtbare_tags(raum, (5.0, 5.0, 0.0))] == [1, 2]


def test_gitter_hat_die_masse_des_echten_localgrid():
    werte, bekannt, ursprung = abstandsgitter(_raum(), (5.0, 5.0, 0.0))
    assert len(werte) == GITTER_ZELLEN and len(werte[0]) == GITTER_ZELLEN
    assert len(bekannt) == GITTER_ZELLEN
    kante = GITTER_ZELLEN * GITTER_ZELLE_M
    assert ursprung == pytest.approx((5.0 - kante / 2, 5.0 - kante / 2))


def test_gitter_kennt_die_wand():
    """Nahe der Wand muss der Abstand klein werden."""
    werte, _bekannt, ursprung = abstandsgitter(_raum(), (1.0, 5.0, 0.0))
    spalte = int(round((0.0 - ursprung[0]) / GITTER_ZELLE_M))
    zeile = int(round((5.0 - ursprung[1]) / GITTER_ZELLE_M))
    assert werte[zeile][spalte] < 0.1


def test_verdeckte_zellen_sind_unbekannt_nicht_frei():
    """Der Fehler, der einen Roboter in eine Wand faehrt: unbekannt != frei."""
    raum = _raum(hindernisse=(Hindernis("Kiste", (5.5, 4.5, 0.4, 1.0)),))
    werte, bekannt, ursprung = abstandsgitter(raum, (5.0, 5.0, 0.0))
    zeile = int(round((5.0 - ursprung[1]) / GITTER_ZELLE_M))
    # Deutlich hinter der Kiste (0.9 m), damit die Naehe-zum-Hindernis-Regel
    # das Ergebnis nicht verfaelscht.
    spalte_dahinter = int(round((6.8 - ursprung[0]) / GITTER_ZELLE_M))
    assert bekannt[zeile][spalte_dahinter] is False
    # Vor der Kiste sehr wohl bekannt.
    spalte_davor = int(round((5.2 - ursprung[0]) / GITTER_ZELLE_M))
    assert bekannt[zeile][spalte_davor] is True


def test_gitter_liefert_listen_keine_numpy_arrays():
    """welt/ gibt rohe Werte zurueck; sim.py macht daraus ein ObstacleGrid."""
    werte, bekannt, _ursprung = abstandsgitter(_raum(), (5.0, 5.0, 0.0))
    assert isinstance(werte, list) and isinstance(werte[0], list)
    assert isinstance(bekannt, list)


def test_gitter_ist_schnell_genug_fuer_zwei_hertz():
    """Bei 2 Hz darf ein Abruf nicht laenger als eine viertel Sekunde dauern.
    Grosszuegig gewaehlt: geprueft wird die Groessenordnung, nicht der Jitter."""
    import time

    raum = _raum(hindernisse=tuple(
        Hindernis(f"H{i}", (float(i), 2.0, 0.5, 0.5)) for i in range(8)
    ))
    beginn = time.perf_counter()
    abstandsgitter(raum, (5.0, 5.0, 0.0))
    assert time.perf_counter() - beginn < 0.25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_welt_wahrnehmung.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'spotlab.welt.wahrnehmung'`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/welt/wahrnehmung.py`:

```python
"""Was von einer Pose aus zu sehen ist -- als rohe Zahlen.

Hier ist numpy erlaubt, in `raum.py` und `kollision.py` nicht: das Gitter hat
16384 Zellen, und in reiner Python-Schleife kostete ein Abruf rund zwei Zehntel
Sekunden. `raum.py` wird von der GUI importiert und bleibt deshalb leicht;
dieses Modul importiert nur `backends/sim.py`.

Rueckgabe sind LISTEN und rohe dx/dy im Koerperframe -- keine spotlab-Formen.
Ein `Tag` oder ein `ObstacleGrid` daraus zu bauen ist Sache von sim.py, weil
`richtung()` in backends/base.py wohnt und welt/ nichts aus backends/ importiert.
"""

import math

import numpy as np

from spotlab.welt.kollision import sicht_frei

# Geschaetzt, NICHT gemessen. Abnahmepunkt A22 misst den echten Wert am Geraet;
# die Simulation rechnet bislang mit rund 12 m, real werden 2-3 m erwartet.
TAG_REICHWEITE_M = 3.0

# Masse des echten LocalGrid: 128 x 128 Zellen a 3 cm sind 3.84 m Kantenlaenge.
# Der Roboter steht in der Mitte, das Gitter reicht also nur 1.92 m weit -- in
# einem 6-m-Zimmer nicht bis zur gegenueberliegenden Wand. Der echte kann es
# auch nicht.
GITTER_ZELLEN = 128
GITTER_ZELLE_M = 0.03


def sichtbare_tags(raum, pose):
    """[(RaumTag, dx, dy)] im Koerperframe, naechster zuerst.

    KEIN Blickfeld-Kegel: der echte Spot hat fuenf Kameras und sieht rundum.
    Ein Tag zaehlt, wenn er in Reichweite ist und die Sichtlinie frei.
    """
    x, y, yaw = pose
    gefunden = []
    for tag in raum.tags:
        dx_welt, dy_welt = tag.x - x, tag.y - y
        abstand = math.hypot(dx_welt, dy_welt)
        if abstand > TAG_REICHWEITE_M:
            continue
        if not sicht_frei(raum, (x, y), (tag.x, tag.y)):
            continue
        # In den Koerperframe drehen.
        cos, sin = math.cos(-yaw), math.sin(-yaw)
        gefunden.append((
            tag,
            dx_welt * cos - dy_welt * sin,
            dx_welt * sin + dy_welt * cos,
        ))
    gefunden.sort(key=lambda eintrag: math.hypot(eintrag[1], eintrag[2]))
    return gefunden


def _abstaende(raum, xs, ys):
    """Je Zelle der Abstand zum naechsten Hindernis, vektorisiert."""
    abstand = np.full(xs.shape, np.inf)
    for x1, y1, x2, y2 in raum.waende:
        dx, dy = x2 - x1, y2 - y1
        laenge2 = dx * dx + dy * dy
        if laenge2 == 0.0:
            abstand = np.minimum(abstand, np.hypot(xs - x1, ys - y1))
            continue
        t = np.clip(((xs - x1) * dx + (ys - y1) * dy) / laenge2, 0.0, 1.0)
        abstand = np.minimum(abstand, np.hypot(xs - (x1 + t * dx), ys - (y1 + t * dy)))
    for hindernis in raum.hindernisse:
        hx, hy, breite, hoehe = hindernis.rechteck
        dx = np.maximum(np.maximum(hx - xs, 0.0), xs - (hx + breite))
        dy = np.maximum(np.maximum(hy - ys, 0.0), ys - (hy + hoehe))
        abstand = np.minimum(abstand, np.hypot(dx, dy))
    return abstand


def abstandsgitter(raum, pose):
    """(werte, bekannt, ursprung) -- Listen, damit welt/ formfrei bleibt.

    `bekannt` ist False, wo die Sichtlinie durch eine Wand oder ein Hindernis
    laeuft. Unbekannt ist NICHT frei -- das ist der Fehler, der einen Roboter in
    eine Wand faehrt.
    """
    x, y, _yaw = pose
    kante = GITTER_ZELLEN * GITTER_ZELLE_M
    ursprung = (x - kante / 2, y - kante / 2)

    achse = np.arange(GITTER_ZELLEN) * GITTER_ZELLE_M
    xs = ursprung[0] + achse[np.newaxis, :]
    ys = ursprung[1] + achse[:, np.newaxis]
    xs, ys = np.broadcast_arrays(xs, ys)

    werte = _abstaende(raum, xs, ys)

    # Sichtbarkeit: eine Zelle gilt als bekannt, wenn die Strecke vom Roboter
    # dorthin frei ist. Die Pruefung laeuft je Zelle -- 16384 Sichtlinien waeren
    # zu teuer, deshalb die Abkuerzung: Zellen NAEHER als der Roboterradius am
    # naechsten Hindernis sind ohnehin belegt und gelten als bekannt; fuer den
    # Rest entscheidet die Sichtlinie auf einem groeberen Raster (jede vierte
    # Zelle) und wird dazwischen uebernommen.
    bekannt = np.ones(werte.shape, dtype=bool)
    schritt = 4
    for zeile in range(0, GITTER_ZELLEN, schritt):
        for spalte in range(0, GITTER_ZELLEN, schritt):
            zx = ursprung[0] + spalte * GITTER_ZELLE_M
            zy = ursprung[1] + zeile * GITTER_ZELLE_M
            if not sicht_frei(raum, (x, y), (zx, zy)):
                bekannt[zeile:zeile + schritt, spalte:spalte + schritt] = False

    # Zellen IM Hindernis sind bekannt: der Roboter sieht das Hindernis, das
    # ihm die Sicht nimmt -- seine Vorderseite gehoert zum Bekannten.
    # NICHT `werte < ROBOTER_RADIUS_M`: das machte auch Zellen 30 cm DAHINTER
    # bekannt und widerspraeche genau der Zusicherung, um die es hier geht.
    bekannt |= werte <= 0.0

    return werte.tolist(), bekannt.tolist(), ursprung
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_welt_wahrnehmung.py -q`
Expected: PASS, 10 Tests

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/welt/wahrnehmung.py tests/test_welt_wahrnehmung.py
git commit -m "feat(welt): sichtbare Tags und Abstandsgitter; verdeckt heisst unbekannt"
```

---

## Task 4: Der Sim bekommt den Raum

**Files:**
- Modify: `src/spotlab/backends/sim.py` (`__init__` ~Z. 61, `capabilities` ~Z. 87, `world_objects`/`local_grid` ~Z. 93–107, `_fortschreiben` ~Z. 388)
- Test: `tests/test_backend_sim.py` (anhängen)

**Interfaces:**
- Consumes: Tasks 1–3
- Produces: `SimBackend(recorder=None, jetzt=time.time, modell=None, raum=None, start=None)`

- [ ] **Step 1: Write the failing test**

An `tests/test_backend_sim.py` anhängen:

```python
# ------------------------------------------------------- Uebungsraum (Stufe 10)


def _uebungsraum():
    from spotlab.welt.raum import Hindernis, Raum, RaumTag

    return Raum(
        name="T", beschreibung="", groesse=(10.0, 10.0), start=(5.0, 5.0, 0.0),
        waende=(
            (0.0, 0.0, 10.0, 0.0), (10.0, 0.0, 10.0, 10.0),
            (10.0, 10.0, 0.0, 10.0), (0.0, 10.0, 0.0, 0.0),
        ),
        hindernisse=(Hindernis("Kiste", (7.0, 4.5, 0.5, 1.0)),),
        tags=(RaumTag(1, 6.0, 5.0, 180.0),),
    )


class _Mitschreiber:
    def __init__(self):
        self.ereignisse = []

    def event(self, art, **daten):
        self.ereignisse.append((art, daten))

    def sample(self, daten):
        pass


def test_ohne_raum_bleibt_alles_wie_vorher():
    """Die wichtigste Zusicherung: kein bestehender Lauf aendert sich."""
    from spotlab.backends.base import Capability
    from spotlab.backends.sim import SimBackend

    backend = SimBackend()
    assert not backend.capabilities() & Capability.WORLD_OBJECTS
    assert not backend.capabilities() & Capability.LOCAL_GRID
    assert backend.world_objects() == []


def test_mit_raum_kommen_die_faehigkeiten_dazu():
    from spotlab.backends.base import Capability
    from spotlab.backends.sim import SimBackend

    backend = SimBackend(raum=_uebungsraum(), start=(5.0, 5.0, 0.0))
    assert backend.capabilities() & Capability.WORLD_OBJECTS
    assert backend.capabilities() & Capability.LOCAL_GRID


def test_start_setzt_die_pose():
    from spotlab.backends.sim import SimBackend

    backend = SimBackend(raum=_uebungsraum(), start=(3.0, 2.0, 90.0))
    assert backend._pose[0] == pytest.approx(3.0)
    assert backend._pose[1] == pytest.approx(2.0)
    assert backend._pose[2] == pytest.approx(math.radians(90.0))


def test_tags_kommen_in_grad_und_metern():
    from spotlab.backends.base import Tag
    from spotlab.backends.sim import SimBackend

    backend = SimBackend(raum=_uebungsraum(), start=(5.0, 5.0, 0.0))
    gefunden = backend.world_objects(kinds=["apriltag"])
    assert len(gefunden) == 1
    tag = gefunden[0]
    assert isinstance(tag, Tag)
    assert tag.id == 1
    assert tag.distance == pytest.approx(1.0)
    assert tag.bearing == pytest.approx(0.0, abs=1e-6)


def test_gitter_traegt_die_bekannt_maske():
    from spotlab.backends.sim import SimBackend

    backend = SimBackend(raum=_uebungsraum(), start=(5.0, 5.0, 0.0))
    gitter = backend.local_grid()
    assert gitter.cell_size == pytest.approx(0.03)
    assert gitter.known is not None
    assert gitter.cells.shape == gitter.known.shape


def test_anstossen_wird_genau_einmal_gemeldet():
    """Ein Programm, das zehn Sekunden gegen eine Wand drueckt, darf das
    Protokoll nicht mit hundert gleichen Zeilen fluten."""
    from spotlab.backends.sim import SimBackend

    schreiber = _Mitschreiber()
    backend = SimBackend(recorder=schreiber, raum=_uebungsraum(), start=(0.5, 5.0, 0.0))
    for _ in range(5):
        backend._bewege_gegen_welt((0.5, 5.0, 0.0), (0.2, 5.0, 0.0))
    anstoesse = [e for e in schreiber.ereignisse if e[0] == "angestossen"]
    assert len(anstoesse) == 1
    assert anstoesse[0][1]["hindernis"] == "Wand"


def test_nach_freier_fahrt_wird_wieder_gemeldet():
    from spotlab.backends.sim import SimBackend

    schreiber = _Mitschreiber()
    backend = SimBackend(recorder=schreiber, raum=_uebungsraum(), start=(0.5, 5.0, 0.0))
    backend._bewege_gegen_welt((0.5, 5.0, 0.0), (0.2, 5.0, 0.0))
    backend._bewege_gegen_welt((0.5, 5.0, 0.0), (0.6, 5.0, 0.0))   # frei
    backend._bewege_gegen_welt((0.5, 5.0, 0.0), (0.2, 5.0, 0.0))
    assert len([e for e in schreiber.ereignisse if e[0] == "angestossen"]) == 2
```

`import math` und `import pytest` oben in der Testdatei sicherstellen.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_sim.py -q -k "raum or tags or gitter or anstossen or start_setzt"`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'raum'`

- [ ] **Step 3: Write minimal implementation**

In `src/spotlab/backends/sim.py`, `__init__` erweitern:

```python
    def __init__(self, recorder=None, jetzt=time.time, modell=None,
                 raum=None, start=None):
        from spotlab.kalibrierung.modell import lade_modell

        self._recorder = recorder
        self._jetzt = jetzt
        self._modell = modell or lade_modell()
        self._powered = False
        self._zaehler = itertools.count(1)
        self._offen = {}
        self.gesendet = []

        # Stufe 10: ein Zimmer um den Sim herum. Ohne Raum verhaelt sich alles
        # exakt wie vorher -- das ist die Zusicherung, an der jeder bestehende
        # Lauf haengt.
        self._raum = raum
        self._angestossen = False      # Flanke, damit das Protokoll lesbar bleibt

        self._t = jetzt()
        if start is not None:
            self._pose = (float(start[0]), float(start[1]), math.radians(start[2]))
        else:
            self._pose = (0.0, 0.0, 0.0)
        …unveraendert weiter…
```

`capabilities()`:

```python
    def capabilities(self):
        # Keine Kameras, kein GraphNav: dafür gibt es keine Messung. Ein
        # erfundenes Bild wäre schlimmer als gar keins, und `require()` sagt
        # dem Schüler dann ehrlich, was fehlt.
        koennen = Capability.LOCOMOTION | Capability.POSTURE | Capability.POWER
        if self._raum is not None:
            # Mit Raum ist die Wahrnehmung keine Erfindung mehr, sondern
            # Geometrie: sie folgt aus dem, was in der Raumdatei steht.
            koennen |= Capability.WORLD_OBJECTS | Capability.LOCAL_GRID
        return koennen
```

`world_objects` und `local_grid` ersetzen:

```python
    def world_objects(self, kinds=None):
        """Ohne Raum leer -- und das ist die Wahrheit, nicht ein Fehler.

        Mit Raum: die Uebersetzung der rohen Geometrie aus welt/ in Tag. Sie
        passiert HIER, weil `richtung()` in backends/base.py wohnt und welt/
        nichts aus backends/ importiert.
        """
        if self._raum is None:
            return []
        if kinds is not None and "apriltag" not in kinds:
            return []
        from spotlab.welt.wahrnehmung import sichtbare_tags

        self._fortschreiben()
        gefunden = []
        for tag, dx, dy in sichtbare_tags(self._raum, self._pose):
            peilung, distanz = richtung(dx, dy)
            gefunden.append(Tag(
                name=f"world_obj_apriltag_{tag.id:03d}", kind="apriltag",
                bearing=peilung, distance=distanz, world_xy=(tag.x, tag.y),
                time=self._jetzt(), id=tag.id, filtered=False,
            ))
        return gefunden

    def local_grid(self):
        if self._raum is None:
            raise UnsupportedCapability(
                "Die Simulation führt ohne Übungsraum kein Hindernisgitter. "
                "Wähle einen Raum in der Ansicht 'Übungsraum' oder gib ihn an: "
                "spotlab.connect(backend='sim', raum='moebliert')."
            )
        import numpy as np

        from spotlab.welt.wahrnehmung import GITTER_ZELLE_M, abstandsgitter

        self._fortschreiben()
        werte, bekannt, ursprung = abstandsgitter(self._raum, self._pose)
        return ObstacleGrid(
            cells=np.asarray(werte), cell_size=GITTER_ZELLE_M,
            origin=ursprung, time=self._jetzt(), known=np.asarray(bekannt),
        )
```

Importzeile ergänzen:

```python
from spotlab.backends.base import (
    Capability, Feedback, ObstacleGrid, SafetyStatus, Tag, richtung,
)
```

Die Kollisionsstelle in `_fortschreiben` — die Zeile

```python
            self._pose = integriere(self._pose, vx, vy, wz, dt)
```

ersetzen durch:

```python
            neu = integriere(self._pose, vx, vy, wz, dt)
            self._pose = self._bewege_gegen_welt(self._pose, neu)
```

und die Methode hinzufügen:

```python
    def _bewege_gegen_welt(self, von, nach):
        """Ohne Raum unveraendert. Mit Raum: an Waenden bleibt Spot stehen.

        Kein Fehler, kein Abbruch -- der echte Spot wirft auch keine Ausnahme,
        wenn er vor einem Hindernis stehenbleibt. Das Programm laeuft weiter und
        `move()` erreicht sein Ziel eben nicht.
        """
        if self._raum is None:
            return nach
        from spotlab.welt.kollision import bewege

        pose, getroffen = bewege(self._raum, von, nach)
        if getroffen is None:
            self._angestossen = False
        elif not self._angestossen:
            self._angestossen = True
            if self._recorder is not None:
                self._recorder.event(
                    "angestossen",
                    x=round(pose[0], 3), y=round(pose[1], 3), hindernis=getroffen,
                )
        return pose
```

`import math` steht in `sim.py` bereits (Zeile 29).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backend_sim.py tests/test_welt_kollision.py -q`
Expected: PASS — alle bisherigen plus sieben neue

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/backends/sim.py tests/test_backend_sim.py
git commit -m "feat(sim): Uebungsraum einhaengen -- Kollision, Tags, Gitter"
```

---

## Task 5: Raum in Konfiguration und `connect()`

**Files:**
- Modify: `src/spotlab/config.py` (`Config` ~Z. 31)
- Modify: `src/spotlab/__init__.py` (`connect` ~Z. 37, Sim-Zweig ~Z. 90)
- Test: `tests/test_config.py` (anhängen), `tests/test_kette.py` (anhängen)

**Interfaces:**
- Consumes: Task 1 und 4
- Produces: `Config.raum: str`, `Config.raum_start: str`, `startpose_aus(text) -> tuple|None`, `connect(..., raum=None)`

- [ ] **Step 1: Write the failing test**

An `tests/test_config.py` anhängen:

```python
def test_raum_und_startpose_ueberleben_das_speichern(tmp_path, monkeypatch):
    from spotlab.config import Config, Limits, load_config, save_config

    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "config.toml")
    save_config(Config(ip="1.2.3.4", username="u", limits=Limits(),
                       raum="moebliert", raum_start="1.5,2.0,90.0"))
    wieder = load_config()
    assert wieder.raum == "moebliert"
    assert wieder.raum_start == "1.5,2.0,90.0"


def test_startpose_wird_gelesen():
    from spotlab.config import startpose_aus

    assert startpose_aus("1.5,2.0,90.0") == (1.5, 2.0, 90.0)


def test_leere_oder_kaputte_startpose_ist_None():
    """Eine von Hand verdorbene Zeile darf die GUI nicht am Starten hindern."""
    from spotlab.config import startpose_aus

    assert startpose_aus("") is None
    assert startpose_aus("murks") is None
    assert startpose_aus("1.0,2.0") is None
```

An `tests/test_kette.py` anhängen:

```python
def test_connect_nimmt_den_raum_aus_dem_argument(tmp_path, monkeypatch):
    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "sim")
    with spotlab.connect(runs_dir=tmp_path, raum="leer") as spot:
        assert spot.backend._raum is not None
        assert spot.backend._raum.name == "Leer"
        assert spot.tags() == [] or spot.tags()[0].id == 1


def test_verbunden_ereignis_nennt_den_raum(tmp_path, monkeypatch):
    """Die Ansicht liest daraus, welcher Raum gilt."""
    import json

    import spotlab

    monkeypatch.setenv("SPOTLAB_BACKEND", "sim")
    with spotlab.connect(runs_dir=tmp_path, raum="leer") as spot:
        verzeichnis = spot.recorder.dir
    zeilen = [json.loads(z) for z
              in (verzeichnis / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
              if z.strip()]
    verbunden = [z for z in zeilen if z["art"] == "verbunden"][0]
    assert verbunden["daten"]["raum"] == "leer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py tests/test_kette.py -q -k "raum or startpose"`
Expected: FAIL — `TypeError: Config.__init__() got an unexpected keyword argument 'raum'`

- [ ] **Step 3: Write minimal implementation**

In `src/spotlab/config.py`, `Config` erweitern:

```python
    active_map: str = ""  # in der GUI gewählte Karte; leer = keine
    raum: str = ""        # Übungsraum für den Sim; leer = keiner
    # Startpose als "x,y,grad". Ein String statt dreier Felder oder einer Liste:
    # der TOML-Schreiber hier ist bewusst minimal, und "1.5,2.0,90" ist in der
    # Datei genauso lesbar wie drei einzelne Zeilen.
    raum_start: str = ""
```

und darunter:

```python
def startpose_aus(text):
    """(x, y, grad) aus "1.5,2.0,90" — oder None.

    Wirft nie: die Datei ist von Hand änderbar, und eine verdorbene Zeile darf
    die GUI nicht am Starten hindern. Ohne Startpose gilt die des Raums.
    """
    teile = str(text or "").split(",")
    if len(teile) != 3:
        return None
    try:
        return tuple(float(t) for t in teile)
    except ValueError:
        return None
```

In `src/spotlab/__init__.py` die Signatur erweitern:

```python
def connect(
    backend=None, runs_dir=None, script=None, take=False, config_path=None,
    nickname=None, raum=None,
):
```

und den Sim-Zweig ersetzen:

```python
    elif art == "sim":
        from spotlab.backends.sim import SimBackend
        from spotlab.config import startpose_aus
        from spotlab.welt.raum import raum_laden

        # Reihenfolge: Argument vor Konfiguration. Ein Skript, das seinen Raum
        # nennt, soll nicht davon abhaengen, was zuletzt in der GUI stand.
        name = raum or (cfg.raum if cfg else "")
        gewaehlt = raum_laden(name, workspace=cfg.workspace if cfg else None) if name else None
        start = startpose_aus(cfg.raum_start) if cfg else None
        if gewaehlt is not None and start is None:
            start = gewaehlt.start

        roher_roboter, unten = None, SimBackend(recorder, raum=gewaehlt, start=start)
        # Der Hinweis gehört in die Aufzeichnung, nicht nur in den Docstring:
        # wer den Lauf später ansieht, muss sehen, dass hier nichts erprobt ist.
        recorder.event(
            "verbunden", backend="sim", raum=name or None,
            hinweis=unten.hinweis_zur_gueltigkeit(),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py tests/test_kette.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/config.py src/spotlab/__init__.py tests/test_config.py tests/test_kette.py
git commit -m "feat(uebungsraum): Raum und Startpose in Konfiguration und connect()"
```

---

## Task 6: Die Zeichnung

**Files:**
- Create: `src/spotlab/gui/raumplot.py`
- Test: `tests/test_gui_raumplot.py`

**Interfaces:**
- Consumes: Task 1
- Produces: `RaumPlot(palette, parent=None)` mit `setze_raum(raum)`, `setze_spur(punkte)`, `setze_anstoesse(punkte)`, `setze_start(pose)`, `meter_zu_schirm(x, y) -> (px, py)`, `schirm_zu_meter(px, py) -> (x, y)`, Signal `start_gewaehlt(float, float)`

- [ ] **Step 1: Write the failing test**

`tests/test_gui_raumplot.py`:

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.raumplot import RaumPlot  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.welt.raum import raum_laden  # noqa: E402


def _plot(qapp):
    plot = RaumPlot(DUNKEL)
    plot.resize(400, 300)
    plot.setze_raum(raum_laden("moebliert"))
    return plot


def test_umrechnung_ist_umkehrbar(qapp):
    plot = _plot(qapp)
    for x, y in [(0.0, 0.0), (3.0, 2.0), (6.0, 4.0)]:
        px, py = plot.meter_zu_schirm(x, y)
        zurueck = plot.schirm_zu_meter(px, py)
        assert zurueck[0] == pytest.approx(x, abs=0.02)
        assert zurueck[1] == pytest.approx(y, abs=0.02)


def test_y_zeigt_nach_oben(qapp):
    """Auf dem Schirm waechst y nach unten, im Raum nach oben."""
    plot = _plot(qapp)
    _px_unten, py_unten = plot.meter_zu_schirm(1.0, 0.0)
    _px_oben, py_oben = plot.meter_zu_schirm(1.0, 4.0)
    assert py_oben < py_unten


def test_seitenverhaeltnis_bleibt_erhalten(qapp):
    """Ein 6x4-Zimmer darf in einem breiten Fenster nicht verzerrt werden."""
    plot = _plot(qapp)
    plot.resize(800, 300)
    px0, py0 = plot.meter_zu_schirm(0.0, 0.0)
    px1, _ = plot.meter_zu_schirm(1.0, 0.0)
    _, py1 = plot.meter_zu_schirm(0.0, 1.0)
    assert abs((px1 - px0) - (py0 - py1)) < 0.5


def test_klick_liefert_meter(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QMouseEvent

    plot = _plot(qapp)
    gemeldet = []
    plot.start_gewaehlt.connect(lambda x, y: gemeldet.append((x, y)))
    px, py = plot.meter_zu_schirm(3.0, 2.0)
    ereignis = QMouseEvent(
        QMouseEvent.MouseButtonPress, QPoint(int(px), int(py)),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    plot.mousePressEvent(ereignis)
    assert gemeldet
    assert gemeldet[0][0] == pytest.approx(3.0, abs=0.05)


def test_zeichnen_ohne_raum_stuerzt_nicht(qapp):
    from PySide6.QtGui import QPixmap

    plot = RaumPlot(DUNKEL)
    plot.resize(200, 150)
    plot.render(QPixmap(200, 150))      # darf nicht werfen


def test_zeichnen_mit_allem_stuerzt_nicht(qapp):
    from PySide6.QtGui import QPixmap

    plot = _plot(qapp)
    plot.setze_spur([(1.0, 1.0), (2.0, 1.0), (2.0, 2.0)])
    plot.setze_anstoesse([(2.5, 1.4)])
    plot.setze_start((1.0, 1.0, 0.0))
    plot.render(QPixmap(400, 300))


def test_kein_farbliteral(qapp):
    """CLAUDE.md: Farben nur aus theme.py."""
    import re
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[1]
              / "src" / "spotlab" / "gui" / "raumplot.py").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{6}", quelle)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gui_raumplot.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'spotlab.gui.raumplot'`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/gui/raumplot.py`:

```python
"""Draufsicht auf den Uebungsraum: Waende, Hindernisse, Tags, Spur, Spot.

Gezeichnet mit QPainter, wie mapplot.py -- jenes zeichnet GraphNav-Grundrisse
und hat mit Raumgeometrie nichts gemein ausser der Technik.

Importiert `welt.raum` (reine Standardbibliothek), aber weder bosdyn noch
`spotlab.backends`: die Regel aus CLAUDE.md gilt auch hier.
"""

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

RAND = 16
SPOT_R_M = 0.35


class RaumPlot(QWidget):
    start_gewaehlt = Signal(float, float)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self._p = palette
        self._raum = None
        self._spur = []
        self._anstoesse = []
        self._start = None

    # ------------------------------------------------------------- Fuellen

    def setze_raum(self, raum):
        self._raum = raum
        self.update()

    def setze_spur(self, punkte):
        self._spur = list(punkte)
        self.update()

    def setze_anstoesse(self, punkte):
        self._anstoesse = list(punkte)
        self.update()

    def setze_start(self, pose):
        self._start = pose
        self.update()

    # --------------------------------------------------------- Umrechnung

    def _massstab(self):
        """Pixel je Meter, Seitenverhaeltnis erhalten."""
        if self._raum is None:
            return 1.0, RAND, self.height() - RAND
        breite, hoehe = self._raum.groesse
        nutzbar_x = max(self.width() - 2 * RAND, 1)
        nutzbar_y = max(self.height() - 2 * RAND, 1)
        skala = min(nutzbar_x / max(breite, 1e-6), nutzbar_y / max(hoehe, 1e-6))
        # Zentriert, und y wird gespiegelt: im Raum waechst y nach oben.
        links = (self.width() - breite * skala) / 2
        unten = (self.height() + hoehe * skala) / 2
        return skala, links, unten

    def meter_zu_schirm(self, x, y):
        skala, links, unten = self._massstab()
        return links + x * skala, unten - y * skala

    def schirm_zu_meter(self, px, py):
        skala, links, unten = self._massstab()
        return (px - links) / skala, (unten - py) / skala

    # ------------------------------------------------------------ Zeichnen

    def mousePressEvent(self, ereignis):
        if self._raum is None:
            return
        punkt = ereignis.position() if hasattr(ereignis, "position") else ereignis.pos()
        x, y = self.schirm_zu_meter(punkt.x(), punkt.y())
        self.start_gewaehlt.emit(x, y)

    def paintEvent(self, _ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        maler.fillRect(self.rect(), QColor(self._p.hintergrund))
        if self._raum is None:
            maler.setPen(QColor(self._p.gedaempft))
            maler.drawText(self.rect(), Qt.AlignCenter, "Kein Raum gewählt.")
            return

        skala, _links, _unten = self._massstab()

        maler.setPen(Qt.NoPen)
        maler.setBrush(QBrush(QColor(self._p.flaeche)))
        for hindernis in self._raum.hindernisse:
            hx, hy, breite, hoehe = hindernis.rechteck
            ecke = self.meter_zu_schirm(hx, hy + hoehe)
            maler.drawRect(int(ecke[0]), int(ecke[1]),
                           int(breite * skala), int(hoehe * skala))

        maler.setPen(QPen(QColor(self._p.text), 2))
        for x1, y1, x2, y2 in self._raum.waende:
            a = self.meter_zu_schirm(x1, y1)
            b = self.meter_zu_schirm(x2, y2)
            maler.drawLine(QPointF(*a), QPointF(*b))

        if len(self._spur) > 1:
            maler.setPen(QPen(QColor(self._p.akzent), 2, Qt.DotLine))
            for erster, zweiter in zip(self._spur, self._spur[1:]):
                maler.drawLine(QPointF(*self.meter_zu_schirm(*erster)),
                               QPointF(*self.meter_zu_schirm(*zweiter)))

        maler.setPen(QPen(QColor(self._p.zahl), 2))
        for tag in self._raum.tags:
            px, py = self.meter_zu_schirm(tag.x, tag.y)
            maler.drawRect(int(px) - 6, int(py) - 6, 12, 12)
            maler.drawText(int(px) + 9, int(py) + 4, str(tag.id))

        maler.setPen(QPen(QColor(self._p.gefahr), 2))
        for x, y in self._anstoesse:
            px, py = self.meter_zu_schirm(x, y)
            maler.drawLine(int(px) - 5, int(py) - 5, int(px) + 5, int(py) + 5)
            maler.drawLine(int(px) - 5, int(py) + 5, int(px) + 5, int(py) - 5)

        pose = self._spur[-1] if self._spur else None
        blick = self._start[2] if self._start else 0.0
        if pose is None and self._start is not None:
            pose = (self._start[0], self._start[1])
        if pose is not None:
            px, py = self.meter_zu_schirm(pose[0], pose[1])
            r = max(4.0, SPOT_R_M * skala)
            maler.setPen(QPen(QColor(self._p.funktion), 2))
            maler.setBrush(Qt.NoBrush)
            maler.drawEllipse(QPointF(px, py), r, r)
            maler.drawLine(QPointF(px, py), QPointF(
                px + r * math.cos(math.radians(blick)),
                py - r * math.sin(math.radians(blick)),
            ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gui_raumplot.py -q`
Expected: PASS, 7 Tests

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/raumplot.py tests/test_gui_raumplot.py
git commit -m "feat(gui): Draufsicht auf den Uebungsraum"
```

---

## Task 7: Die Ansicht „Übungsraum"

**Files:**
- Create: `src/spotlab/gui/views/uebungsraum.py`
- Modify: `src/spotlab/gui/sidebar.py` (`EINTRAEGE`), `src/spotlab/gui/app.py` (Ansichten, Reihenfolge, `_setze_arbeitsordner`)
- Test: `tests/test_gui_uebungsraum.py`, `tests/test_gui_app.py` (Ansichtszahl)

**Interfaces:**
- Consumes: Tasks 1, 5, 6
- Produces: `UebungsraumView(palette, parent=None)` mit `setze_arbeitsordner(pfad)`, `setze_config(cfg)`, `lade(lauf_verzeichnis)`, Signale `meldung(str)`, `config_gespeichert(object)`, `start_gewuenscht()`

- [ ] **Step 1: Write the failing test**

`tests/test_gui_uebungsraum.py`:

```python
import ast
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.config import Config, Limits  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.gui.views.uebungsraum import UebungsraumView  # noqa: E402

QUELLE = (Path(__file__).resolve().parents[1] / "src" / "spotlab" / "gui"
          / "views" / "uebungsraum.py")


def test_ansicht_importiert_weder_bosdyn_noch_backends():
    """CLAUDE.md: kein bosdyn UND kein spotlab.backends unterhalb von gui/.
    Ueber ast, nicht als Textsuche -- der Docstring erwaehnt beides."""
    namen = set()
    for knoten in ast.walk(ast.parse(QUELLE.read_text(encoding="utf-8"))):
        if isinstance(knoten, ast.Import):
            namen.update(t.name for t in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            namen.add(knoten.module)
    verboten = [n for n in namen
                if n.split(".")[0] == "bosdyn" or n.startswith("spotlab.backends")]
    assert not verboten


def test_zeigt_die_drei_vorlagen(qapp):
    ansicht = UebungsraumView(DUNKEL)
    texte = [ansicht.raeume.itemText(i) for i in range(ansicht.raeume.count())]
    assert sorted(texte) == ["durchgang", "leer", "moebliert"]


def test_raumwahl_zeichnet_den_raum(qapp):
    ansicht = UebungsraumView(DUNKEL)
    ansicht.waehle_raum("moebliert")
    assert ansicht.plot._raum is not None
    assert ansicht.plot._raum.name == "Möbliert"


def test_klick_setzt_die_startpose_und_merkt_sie(qapp):
    ansicht = UebungsraumView(DUNKEL)
    ansicht.setze_config(Config(ip="1.2.3.4", username="u", limits=Limits()))
    ansicht.waehle_raum("leer")
    gemerkt = []
    ansicht.config_gespeichert.connect(gemerkt.append)
    ansicht._start_gewaehlt(2.0, 3.0)
    assert gemerkt, "die Wahl muss in die Konfiguration"
    assert gemerkt[-1].raum == "leer"
    assert gemerkt[-1].raum_start.startswith("2.0,3.0")


def test_startpose_in_einer_wand_wird_abgewiesen(qapp):
    ansicht = UebungsraumView(DUNKEL)
    ansicht.setze_config(Config(ip="1.2.3.4", username="u", limits=Limits()))
    ansicht.waehle_raum("leer")
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht._start_gewaehlt(0.05, 0.05)      # in der Ecke, im Wandradius
    assert gemeldet and "Wand" in gemeldet[0]


def _lauf(tmp_path):
    ereignisse = [
        {"t": 0.0, "art": "verbunden", "daten": {"backend": "sim", "raum": "leer"}},
        {"t": 2.0, "art": "angestossen",
         "daten": {"x": 4.6, "y": 2.0, "hindernis": "Wand"}},
    ]
    (tmp_path / "ereignisse.jsonl").write_text(
        "\n".join(json.dumps(z) for z in ereignisse) + "\n", encoding="utf-8")
    zustand = [
        {"t": 0.1, "daten": {"pose": [1.0, 1.0, 0.0]}},
        {"t": 0.2, "daten": {"pose": [1.5, 1.0, 0.0]}},
        {"t": 0.3, "daten": {"pose": [2.0, 1.0, 0.0]}},
    ]
    (tmp_path / "zustand.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zustand) + "\n", encoding="utf-8")
    return tmp_path


def test_lauf_liefert_raum_spur_und_anstoesse(qapp, tmp_path):
    ansicht = UebungsraumView(DUNKEL)
    ansicht.lade(_lauf(tmp_path))
    assert ansicht.plot._raum.name == "Leer"
    assert len(ansicht.plot._spur) == 3
    assert ansicht.plot._anstoesse == [(4.6, 2.0)]


def test_halbe_letzte_zeile_bricht_nicht(qapp, tmp_path):
    ordner = _lauf(tmp_path)
    with (ordner / "zustand.jsonl").open("a", encoding="utf-8") as datei:
        datei.write('{"t": 0.4, "daten": {"pos')
    ansicht = UebungsraumView(DUNKEL)
    ansicht.lade(ordner)
    assert len(ansicht.plot._spur) == 3


def test_lauf_ohne_raum_zeigt_keinen(qapp, tmp_path):
    """Ein echter Lauf hat kein raum-Feld -- die Ansicht darf nicht stuerzen."""
    (tmp_path / "ereignisse.jsonl").write_text(
        json.dumps({"t": 0.0, "art": "verbunden", "daten": {"backend": "real"}}) + "\n",
        encoding="utf-8")
    ansicht = UebungsraumView(DUNKEL)
    ansicht.lade(tmp_path)
    assert ansicht.plot._raum is None


def test_startknopf_meldet_nur_den_wunsch(qapp):
    """Er startet NICHT selbst -- genau ein Lauf ist der, auf den NOT-AUS zeigt."""
    ansicht = UebungsraumView(DUNKEL)
    gewuenscht = []
    ansicht.start_gewuenscht.connect(lambda: gewuenscht.append(True))
    ansicht.starten.click()
    assert gewuenscht == [True]
```

In `tests/test_gui_app.py` die Ansichtszahl anpassen:

```python
def test_fenster_hat_jetzt_neun_ansichten(qapp):
    fenster = MainWindow()
    assert set(fenster.ansichten) == {
        "projekte", "code", "live", "laeufe", "karten", "umwelt",
        "uebungsraum", "anbindungen", "spot",
    }
    assert fenster.stapel.count() == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gui_uebungsraum.py -q`
Expected: FAIL — `ModuleNotFoundError: spotlab.gui.views.uebungsraum`

- [ ] **Step 3: Write minimal implementation**

`src/spotlab/gui/views/uebungsraum.py`:

```python
"""Der Uebungsraum: Raum waehlen, Start setzen, Programm laufen sehen.

Eigene Ansicht neben „Umwelt": jene zeigt, WAS Spot sieht, diese, WO er ist.

Sie importiert weder bosdyn noch spotlab.backends -- sie liest ausschliesslich
das Lauf-Verzeichnis (`ereignisse.jsonl` fuer Raum und Anstoesse, `zustand.jsonl`
fuer die Spur) und `welt.raum` fuer die Geometrie. Letzteres ist reine
Standardbibliothek.

DER STARTKNOPF STARTET NICHT SELBST. Er meldet den Wunsch; das Fenster reicht
ihn an die Ansicht „Projekte" weiter -- so wie der Stopp-Knopf im Editor an
„Live-Lauf" delegiert. Grund ist die Invariante aus CLAUDE.md: genau EIN Lauf ist
der, auf den Stopp und NOT-AUS zeigen.
"""

import json
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spotlab.gui.raumplot import RaumPlot
from spotlab.welt.kollision import hindernis_bei
from spotlab.welt.raum import raum_laden, vorlagen


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


class UebungsraumView(QWidget):
    meldung = Signal(str)
    config_gespeichert = Signal(object)
    start_gewuenscht = Signal()

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._p = palette
        self._config = None
        self._arbeitsordner = None
        self._raum = None

        self.plot = RaumPlot(palette)
        self.plot.start_gewaehlt.connect(self._start_gewaehlt)

        self.raeume = QComboBox()
        self.raeume.addItems(vorlagen())
        self.raeume.currentTextChanged.connect(self.waehle_raum)

        self.startzeile = QLabel("—")
        self.startzeile.setObjectName("Gedaempft")
        self.starten = QPushButton("Programm starten")
        self.starten.clicked.connect(self.start_gewuenscht.emit)

        rechts = QVBoxLayout()
        rechts.addWidget(QLabel("Raum"))
        rechts.addWidget(self.raeume)
        rechts.addWidget(QLabel("Startposition"))
        rechts.addWidget(QLabel("In die Zeichnung klicken."))
        rechts.addWidget(self.startzeile)
        rechts.addStretch(1)
        rechts.addWidget(self.starten)

        anordnung = QHBoxLayout(self)
        anordnung.addWidget(self.plot, 3)
        anordnung.addLayout(rechts, 1)

        self.waehle_raum(self.raeume.currentText())

    # ----------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._arbeitsordner = Path(pfad) if pfad else None

    def setze_config(self, cfg):
        self._config = cfg
        if cfg and cfg.raum:
            self.raeume.setCurrentText(cfg.raum)

    # -------------------------------------------------------------- Raum

    def waehle_raum(self, name):
        if not name:
            return
        try:
            self._raum = raum_laden(name, workspace=self._arbeitsordner)
        except Exception as fehler:
            self.meldung.emit(str(fehler))
            return
        self.plot.setze_raum(self._raum)
        self.plot.setze_start(self._raum.start)
        self._zeige_start(self._raum.start)

    def _zeige_start(self, pose):
        self.startzeile.setText(f"({pose[0]:.2f}, {pose[1]:.2f}) bei {pose[2]:.0f}°")

    def _start_gewaehlt(self, x, y):
        if self._raum is None:
            return
        getroffen = hindernis_bei(self._raum, x, y)
        if getroffen is not None:
            self.meldung.emit(
                f"Dort steht {'eine Wand' if getroffen == 'Wand' else getroffen} "
                f"im Weg — such eine freie Stelle."
            )
            return
        grad = self._raum.start[2]
        self.plot.setze_start((x, y, grad))
        self._zeige_start((x, y, grad))
        if self._config is not None:
            self._config = replace(
                self._config, raum=self.raeume.currentText(),
                raum_start=f"{x:.2f},{y:.2f},{grad:.1f}",
            )
            self.config_gespeichert.emit(self._config)

    # -------------------------------------------------------------- Lauf

    def lade(self, lauf_verzeichnis):
        ordner = Path(lauf_verzeichnis)
        name = None
        anstoesse = []
        for satz in _zeilen(ordner / "ereignisse.jsonl"):
            daten = satz.get("daten") or {}
            if satz.get("art") == "verbunden":
                name = daten.get("raum")
            elif satz.get("art") == "angestossen":
                anstoesse.append((daten.get("x", 0.0), daten.get("y", 0.0)))

        if name:
            self.waehle_raum(name)
            self.raeume.setCurrentText(name)
        else:
            self._raum = None
            self.plot.setze_raum(None)

        spur = []
        for satz in _zeilen(ordner / "zustand.jsonl"):
            pose = (satz.get("daten") or {}).get("pose")
            if pose and len(pose) >= 2:
                spur.append((pose[0], pose[1]))
        self.plot.setze_spur(spur)
        self.plot.setze_anstoesse(anstoesse)
```

In `src/spotlab/gui/sidebar.py`, `EINTRAEGE` nach `("karten", "Karten")`:

```python
    ("uebungsraum", "Übungsraum"),
```

In `src/spotlab/gui/app.py`: Import, Eintrag im Ansichten-Wörterbuch nach
`"umwelt"`, Aufnahme in die Reihenfolge, sowie in `_setze_arbeitsordner`:

```python
        self.ansichten["uebungsraum"].setze_arbeitsordner(pfad or None)
```

und in `_verdrahte`:

```python
        self.ansichten["uebungsraum"].meldung.connect(self._melde)
        self.ansichten["uebungsraum"].config_gespeichert.connect(self._merke_config)
        self.ansichten["uebungsraum"].start_gewuenscht.connect(
            self.ansichten["projekte"].starte_aktuelles
        )
```

In `src/spotlab/gui/views/projects.py` bekommt der **vorhandene** Startpfad
(`_starte`, Zeile 160) einen öffentlichen Namen — kein zweiter Weg, nur ein
Zugang von aussen:

```python
    def starte_aktuelles(self):
        """Startet, was in dieser Ansicht gewaehlt ist.

        Oeffentlich, damit der Uebungsraum daran delegieren kann, statt einen
        zweiten Startweg zu bauen: genau EIN Lauf ist der, auf den Stopp und
        NOT-AUS zeigen.
        """
        self._starte()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gui_uebungsraum.py tests/test_gui_app.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/spotlab/gui/views/uebungsraum.py src/spotlab/gui/app.py src/spotlab/gui/sidebar.py tests/test_gui_uebungsraum.py tests/test_gui_app.py
git commit -m "feat(gui): Ansicht Uebungsraum -- waehlen, ansehen, starten lassen"
```

---

## Task 8: Beispielprogramm und Doku

**Files:**
- Modify: `README.md`
- Modify: `src/spotlab/workshop/project.py` (`PROJEKT_DATEIEN` Z. 9, `create_project` Z. 46)
- Test: `tests/test_cli.py` (anhängen)

- [ ] **Step 1: Write the failing test**

An `tests/test_cli.py` anhängen:

```python
def test_neues_projekt_bringt_ein_uebungsprogramm(tmp_path):
    """Wer `spotlab new` macht, soll etwas haben, das ohne Roboter laeuft."""
    from spotlab.workshop.project import create_project

    ordner = create_project("probe", wurzel=tmp_path)
    beispiel = ordner / "uebungsraum.py"
    assert beispiel.is_file()
    quelle = beispiel.read_text(encoding="utf-8")
    assert 'backend="sim"' in quelle
    assert "spot.tags()" in quelle
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -q -k uebungsprogramm`
Expected: FAIL — die Datei fehlt

- [ ] **Step 3: Write minimal implementation**

`PROJEKT_DATEIEN` in `project.py` um `"uebungsraum.py"` erweitern und den
Inhalt als Modulkonstante daneben legen (wie `README`):

```python
"""Ohne Roboter üben: Spot fährt durch ein gezeichnetes Zimmer.

Starten: in der Ansicht „Übungsraum" auf „Programm starten" — oder hier mit F5.
Den Raum und die Startposition wählst du in der Ansicht „Übungsraum".
"""

import spotlab

with spotlab.connect(backend="sim") as spot:
    spot.power_on()
    spot.stand()

    spot.move(forward=1.5)
    spot.move(turn=90)

    for tag in spot.tags():
        print(f"Tag {tag.id}: {tag.distance:.1f} m, {tag.bearing:+.0f} Grad")

    gitter = spot.obstacles()
    print("Vor mir frei:", gitter.is_free(0.5, 0.0))
```

README: neuer Abschnitt „Übungsraum" vor „Ein Programm", Verben-Tabelle
unverändert (die Verben sind dieselben), Ansichtszahl von acht auf **neun**,
Spec-Tabelle um Stufe 10 ergänzen.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md src/spotlab/workshop tests/test_cli.py
git commit -m "docs(uebungsraum): Beispielprogramm in der Projektvorlage, README"
```

---

## Task 9: Spec nachziehen

**Files:**
- Modify: `docs/superpowers/specs/2026-09-02-spotlab-uebungsraum-design.md`

- [ ] **Step 1: Die numpy-Abweichung eintragen**

In §2 den Absatz „`welt/` importiert nichts aus `backends/`" um den Satz
ergänzen, der beim Planen entschieden wurde:

> `raum.py` und `kollision.py` halten sich auf Standardbibliothek plus
> `tomllib`; `wahrnehmung.py` benutzt zusätzlich **numpy**, weil das Gitter
> 16 384 Zellen hat und eine reine Python-Schleife rund 0.2 s je Abruf kostete.
> Die GUI importiert nur `raum.py` und zieht damit nichts Schweres herein.

In §11 unter „Neu" ergänzen: `numpy` ist bereits Abhängigkeit, es kommt keine
hinzu.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-09-02-spotlab-uebungsraum-design.md
git commit -m "docs(spec): numpy in welt/wahrnehmung.py, Begruendung nachgetragen"
```

---

## Task 10: Gesamtlauf

**Files:** keine Änderung, nur Nachweis

- [ ] **Step 1: Linter zuerst**

CLAUDE.md: die CI führt `ruff` **vor** den Tests aus.

Run: `ruff check .`
Expected: `All checks passed!`

- [ ] **Step 2: Vollständige Suite**

Run: `python -m pytest -q`
Expected: alle grün. Schlägt genau ein zeitabhängiger Test fehl
(`test_schranke.py` oder `test_messfahrt_ende_zu_ende.py`), einzeln nachfahren —
beide sind als lastabhängig bekannt und haben eigene Aufgaben.

- [ ] **Step 3: Von aussen ausprobieren**

Run:
```bash
SPOTLAB_BACKEND=sim python -c "
import tempfile, pathlib, spotlab
with spotlab.connect(runs_dir=pathlib.Path(tempfile.mkdtemp())/'runs', raum='moebliert') as s:
    s.power_on(); s.stand()
    s.move(forward=1.0)
    print('tags:', [(t.id, round(t.distance,2)) for t in s.tags()])
    g = s.obstacles(); print('gitter:', g.cells.shape, 'frei voraus:', g.is_free(0.5, 0.0))
"
```
Expected: eine Tag-Liste und ein 128×128-Gitter, kein Fehler.

- [ ] **Step 4: Commit (falls Korrekturen nötig waren)**

```bash
git add -A && git commit -m "test(uebungsraum): Gesamtlauf gruen"
```

---

## Self-Review

**Spec-Abdeckung:**

| Spec | Task |
|---|---|
| §4.1 Datenmodell, Suchreihenfolge | 1 |
| §4.2 drei Vorlagen | 1 |
| §4.3 Kollision, Schrittzerlegung, Drehen | 2 |
| §4.4 Tags, Gitter, Verdeckung | 3 |
| §4.5 Sim: Raum, Übersetzung, Einhängen | 4 |
| §4.6 Anstoss-Ereignis als Flanke | 4 |
| §4.7 Ansicht, Startwahl, Delegation | 6, 7 |
| §5 Datenfluss | 4 (Ereignis), 5 (`verbunden` mit Raum), 7 (Lesen) |
| §6 Fehlerbehandlung | 1 (Datei, Feld, TOML), 4 (`UnsupportedCapability`), 7 (Start in der Wand, halbe Zeile, Lauf ohne Raum) |
| §7 Prüfung | in jedem Task, Gesamtlauf in 10 |
| §8 keine Geräte-Abnahme, A22 speist `TAG_REICHWEITE_M` | 3 (Konstante mit Kommentar) |
| §9 Nicht-Ziele | nichts davon gebaut |
| §11 Reihenfolge | Tasks 1→7 wie dort |

**Nicht durch Tasks abgedeckt und richtig so:** §8 nennt A22 als Messung am
Gerät. Sie gehört ins Geräteprotokoll, nicht in einen Implementierungs-Task; die
Konstante trägt bis dahin einen Kommentar, der sie als Schätzung ausweist.

**Typkonsistenz geprüft:** `bewege(raum, von, nach)` gibt überall
`(pose, name|None)` zurück — so verwendet in Task 4. `abstandsgitter` gibt
`(werte, bekannt, ursprung)` als Listen; Task 4 macht daraus numpy-Arrays.
`sichtbare_tags` gibt `(RaumTag, dx, dy)` im Körperframe; Task 4 rechnet mit
`richtung(dx, dy)` in Grad um. `hindernis_bei` heisst in Task 2, 3 und 7
gleich. `raum_laden(name, workspace=None)` hat in Tasks 1, 5 und 7 dieselbe
Signatur.

**Beim Selbstlesen aufgelöst:** Der Plan enthielt zwei Stellen mit „Pfad
selbst suchen". Beide sind jetzt konkret: `ProjectsView._starte()` (Zeile 160)
ist der vorhandene Startweg und bekommt in Task 7 nur einen öffentlichen Namen;
die Projektvorlage ist `workshop/project.py` mit `PROJEKT_DATEIEN` (Zeile 9) und
`create_project(name, wurzel=None)` (Zeile 46).
