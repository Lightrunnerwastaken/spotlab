# spotlab Anbindung Implementierungsplan — Teil 1 (Aufgaben 1–5)

> **Für agentische Arbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development`
> (empfohlen) oder `superpowers:executing-plans`. Schritte sind Checkboxen (`- [ ]`).

**Ziel:** Fremde Projekte docken an spotlab an, zeigen deklarative Panels in einer eigenen
Ansicht, und ein MCP-Server gibt einem Agenten Zugriff auf Läufe, Karten und Panels — samt
einer erzwungenen Trockenlauf-Schranke für alles, was der Agent startet.

**Architektur:** `anbindung/` hält Manifest, Ablage und Panels; es hält **keinen Lease-Client
und keinen E-Stop-Endpunkt** und importiert nichts aus `api/`, `backends/`, `maps/`, `gui/`.
`mcp/werkzeuge.py` sind gewöhnliche Funktionen, `mcp/server.py` meldet sie nur beim Protokoll
an. Die GUI liest Panels aus Dateien, wie sie Live-Daten aus dem Lauf-Verzeichnis liest.

**Technik:** Python 3.11+, `tomllib` (Standardbibliothek), `mcp` als Extra `[mcp]`, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-08-07-spotlab-anbindung-design.md`

**Teil 2 (Aufgaben 6–11):** `docs/superpowers/plans/2026-08-07-spotlab-anbindung-teil2.md`

## Globale Vorgaben

Gelten für **jede** Aufgabe, auch wenn sie dort nicht wiederholt werden:

- **`src/spotlab/anbindung/` importiert nichts aus `spotlab.api`, `spotlab.backends`,
  `spotlab.maps`, `spotlab.gui` und kein `bosdyn`.** `spotlab.errors` ist erlaubt und
  erwünscht — `SpotlabError` ist der Fehlertyp, den CLI und GUI abfangen. Kein Lease-Client,
  kein E-Stop-Endpunkt.
- **Kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `src/spotlab/gui/`.**
- **Farben ausschliesslich aus `src/spotlab/gui/theme.py`.** Ein Panel bestimmt keine Farbe.
- **Bezeichner in neuen Modulen deutsch** (`binde_an`, `Anbindung`, `panels`), Ausnahmeklassen
  englisch benannt, **alle Texte an Nutzer deutsch**.
- **Meldungen sagen, was zu tun ist, und behaupten keine ungeprüfte Ursache.**
- **Dateien lesen mit `encoding="utf-8"`, schreiben mit `encoding="utf-8"`.** JSON immer mit
  `ensure_ascii=False`.
- **Tests laufen ohne Roboter, ohne Netz, ohne `mcp`.** Qt-Tests nutzen die `qapp`-Fixture und
  halten jedes Widget in einer Variablen fest.
- Vor jedem Commit: `python -m pytest -q` vollständig grün.

---

## Aufgabe 1: `pfade.py` — `sicherer_name` an einen gemeinsamen Ort

**Warum zuerst:** Aufgabe 2 braucht die Funktion, und sie aus `maps/store.py` zu importieren
würde die Anbindung an die GraphNav-Ablage koppeln — für eine fünfzeilige Regex, die mit
Karten nichts zu tun hat.

**Dateien:**
- Anlegen: `src/spotlab/pfade.py`
- Ändern: `src/spotlab/maps/store.py` (Funktion entfernen, von `pfade` re-exportieren)
- Test: `tests/test_pfade.py`

**Schnittstellen:**
- Verbraucht: nichts.
- Liefert: `sicherer_name(name: str, ersatz: str = "ordner") -> str`.
  Aufgabe 2 benutzt es; `maps/store.py` exportiert es unter demselben Namen weiter, damit
  bestehende Importe und `tests/test_maps_store.py` unverändert laufen.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_pfade.py`:

```python
import pytest

from spotlab.pfade import sicherer_name


@pytest.mark.parametrize(
    "roh, erwartet",
    [
        ("turnhalle", "turnhalle"),
        ("Turnhalle 2", "Turnhalle-2"),
        ("matura-spot", "matura-spot"),
        ("a/b", "a-b"),
        ("../../etc", "etc"),
        ("  rand  ", "rand"),
        ("...", "ordner"),
        ("", "ordner"),
    ],
)
def test_sicherer_name(roh, erwartet):
    assert sicherer_name(roh) == erwartet


def test_ersatz_ist_einstellbar():
    assert sicherer_name("", ersatz="karte") == "karte"


def test_maps_store_exportiert_dieselbe_funktion():
    """Der bestehende Import-Pfad muss weiter tragen."""
    from spotlab.maps.store import sicherer_name as aus_maps

    assert aus_maps is sicherer_name


def test_pfade_ist_frei_von_fremden_importen():
    import pathlib

    import spotlab.pfade as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    for verboten in ("bosdyn", "PySide6", "spotlab.maps", "spotlab.api"):
        assert verboten not in quelle
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_pfade.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.pfade'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/pfade.py`:

```python
"""Pfadhygiene, die mehr als ein Teilsystem braucht.

sicherer_name lag bis Stufe 6 in maps/store.py. Die Anbindung braucht dieselbe
Regel — sie aus maps/store.py zu importieren hiesse aber, sie an die
GraphNav-Ablage zu koppeln, und maps/store.py zieht dafuer bosdyn herein.
Ein gemeinsamer Ort loest beides, ohne zwei Umsetzungen zu haben, die
auseinanderlaufen koennen.
"""

import re

MUSTER = re.compile(r"[^\w.-]+")


def sicherer_name(name, ersatz="ordner"):
    """Ein Name, der garantiert ein einzelnes Verzeichnis unterhalb bleibt."""
    sauber = MUSTER.sub("-", str(name).strip()).strip("-.")
    return sauber or ersatz
```

In `src/spotlab/maps/store.py` die Definition entfernen und stattdessen importieren.
Der Import kommt zu den übrigen `spotlab`-Importen:

```python
from spotlab.errors import SpotlabError
from spotlab.pfade import sicherer_name  # noqa: F401  (Re-Export, historischer Pfad)
```

**Achtung beim Aufrufort:** `maps/store.py` rief bisher `sicherer_name(name)` mit dem
Rückfallwert `"karte"`. Diese Aufrufe müssen jetzt `sicherer_name(name, ersatz="karte")`
lauten, sonst heisst ein leerer Kartenname plötzlich `ordner`. Alle Aufrufstellen in
`maps/store.py` durchgehen.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_pfade.py tests/test_maps_store.py -q
```

Erwartet: beide grün. Schlägt ein Kartentest fehl, ist der `ersatz`-Parameter an einer
Aufrufstelle vergessen worden.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/pfade.py src/spotlab/maps/store.py tests/test_pfade.py
git commit -m "refactor: sicherer_name nach pfade.py, maps/store re-exportiert"
```

---

## Aufgabe 2: `anbindung/manifest.py` — die Projektbeschreibung

**Dateien:**
- Anlegen: `src/spotlab/anbindung/__init__.py`
- Anlegen: `src/spotlab/anbindung/manifest.py`
- Test: `tests/test_anbindung_manifest.py`

**Schnittstellen:**
- Verbraucht: `SpotlabError` aus `spotlab.errors`.
- Liefert: `DATEINAME = "spotlab.toml"`, `ManifestFehler(SpotlabError)`,
  `Skript(name, datei, argumente, roboter, beschreibung)`,
  `Manifest(name, beschreibung, projekt, skripte)`,
  `lies(projektpfad) -> Manifest`, `als_json(manifest) -> dict`, `aus_json(daten) -> Manifest`,
  `skript_von(manifest, name) -> Skript | None`.
  Aufgabe 3 legt die Kopie ab, Aufgabe 7 startet die Skripte.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_anbindung_manifest.py`:

```python
import pytest

from spotlab.anbindung.manifest import (
    DATEINAME,
    ManifestFehler,
    als_json,
    aus_json,
    lies,
    skript_von,
)

VOLLSTAENDIG = """
[projekt]
name = "matura-spot"
beschreibung = "MuJoCo-Simulation des Spot"

[[skript]]
name = "Baseline, 20 Episoden"
datei = "scripts/experiment_baseline.py"
argumente = ["--episoden", "20", "--archiv"]
roboter = false
beschreibung = "Frontier-Exploration"

[[skript]]
name = "Fahrt auf dem echten Spot"
datei = "scripts/sdk_drive.py"
roboter = true
"""


def _projekt(tmp_path, inhalt=VOLLSTAENDIG):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "experiment_baseline.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / DATEINAME).write_text(inhalt, encoding="utf-8")
    return tmp_path


def test_liest_projekt_und_skripte(tmp_path):
    manifest = lies(_projekt(tmp_path))
    assert manifest.name == "matura-spot"
    assert manifest.beschreibung.startswith("MuJoCo")
    assert manifest.projekt == tmp_path.resolve()
    assert [s.name for s in manifest.skripte] == [
        "Baseline, 20 Episoden",
        "Fahrt auf dem echten Spot",
    ]


def test_pfade_werden_gegen_das_projekt_aufgeloest(tmp_path):
    manifest = lies(_projekt(tmp_path))
    assert manifest.skripte[0].datei == (tmp_path / "scripts" / "experiment_baseline.py").resolve()
    assert manifest.skripte[0].datei.is_absolute()


def test_argumente_sind_ein_tupel(tmp_path):
    manifest = lies(_projekt(tmp_path))
    assert manifest.skripte[0].argumente == ("--episoden", "20", "--archiv")


def test_standardwerte(tmp_path):
    manifest = lies(_projekt(tmp_path))
    zweites = manifest.skripte[1]
    assert zweites.argumente == ()
    assert zweites.beschreibung == ""
    assert zweites.roboter is True
    assert manifest.skripte[0].roboter is False


def test_fehlende_datei(tmp_path):
    with pytest.raises(ManifestFehler) as fehler:
        lies(tmp_path)
    assert DATEINAME in str(fehler.value)
    assert str(tmp_path) in str(fehler.value)


def test_kaputtes_toml_nennt_die_datei(tmp_path):
    (tmp_path / DATEINAME).write_text("[projekt\nname =", encoding="utf-8")
    with pytest.raises(ManifestFehler) as fehler:
        lies(tmp_path)
    assert DATEINAME in str(fehler.value)


def test_fehlender_projektname(tmp_path):
    with pytest.raises(ManifestFehler) as fehler:
        lies(_projekt(tmp_path, '[projekt]\nbeschreibung = "x"\n'))
    assert "name" in str(fehler.value)


def test_skript_ohne_datei_nennt_die_nummer(tmp_path):
    inhalt = '[projekt]\nname = "p"\n\n[[skript]]\nname = "eins"\n'
    with pytest.raises(ManifestFehler) as fehler:
        lies(_projekt(tmp_path, inhalt))
    text = str(fehler.value)
    assert "datei" in text and "1" in text


def test_argumente_muessen_texte_sein(tmp_path):
    inhalt = (
        '[projekt]\nname = "p"\n\n[[skript]]\nname = "eins"\n'
        'datei = "a.py"\nargumente = [1, 2]\n'
    )
    with pytest.raises(ManifestFehler) as fehler:
        lies(_projekt(tmp_path, inhalt))
    assert "argumente" in str(fehler.value)


def test_json_hin_und_zurueck(tmp_path):
    manifest = lies(_projekt(tmp_path))
    wieder = aus_json(als_json(manifest))
    assert wieder == manifest


def test_skript_von_findet_und_gibt_sonst_none(tmp_path):
    manifest = lies(_projekt(tmp_path))
    assert skript_von(manifest, "Baseline, 20 Episoden").roboter is False
    assert skript_von(manifest, "gibtsnicht") is None


def test_anbindung_ist_frei_von_sdk_und_qt():
    """Die Schichtregel als Test — auf die richtige Regel gerichtet."""
    import pathlib

    import spotlab.anbindung as paket

    wurzel = pathlib.Path(paket.__file__).parent
    verboten = ("bosdyn", "spotlab.backends", "spotlab.api", "spotlab.maps", "spotlab.gui")
    treffer = [
        f"{p.name}: {v}"
        for p in wurzel.rglob("*.py")
        for v in verboten
        if v in p.read_text(encoding="utf-8")
    ]
    assert treffer == []
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_anbindung_manifest.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.anbindung'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/anbindung/__init__.py`:

```python
"""Fremde Projekte an spotlab andocken.

Dieses Paket importiert nichts aus api/, backends/, maps/ oder gui/ und haelt
weder Lease-Client noch E-Stop-Endpunkt — dieselbe Bedingung, unter der maps/
von der GUI benutzt werden darf. spotlab.errors ist erlaubt: SpotlabError ist
der Fehlertyp, den CLI und GUI bereits abfangen.
"""
```

`src/spotlab/anbindung/manifest.py`:

```python
"""Die Beschreibung eines fremden Projekts.

Sie liegt im fremden Repo und nicht in spotlabs Arbeitsordner: dort gehoert sie
hin, dort liegt sie in git, und wer das Repo klont, bekommt die Anbindung mit.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from spotlab.errors import SpotlabError

DATEINAME = "spotlab.toml"


class ManifestFehler(SpotlabError):
    """Nennt immer Datei UND Feld — sonst sucht man in der falschen Zeile."""


@dataclass(frozen=True)
class Skript:
    name: str
    datei: Path             # absolut, gegen das Projektverzeichnis aufgeloest
    argumente: tuple
    roboter: bool           # faehrt dieses Skript den echten Spot?
    beschreibung: str


@dataclass(frozen=True)
class Manifest:
    name: str
    beschreibung: str
    projekt: Path
    skripte: tuple


def lies(projektpfad):
    """Liest <projektpfad>/spotlab.toml. Wirft ManifestFehler mit deutschem Text."""
    projekt = Path(projektpfad).resolve()
    datei = projekt / DATEINAME
    if not datei.is_file():
        raise ManifestFehler(
            f"In {projekt} liegt keine {DATEINAME}. Lege sie dort an, damit spotlab "
            "das Projekt anbinden kann."
        )
    try:
        roh = tomllib.loads(datei.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as fehler:
        raise ManifestFehler(f"{datei} liess sich nicht lesen: {fehler}") from fehler

    kopf = roh.get("projekt") or {}
    name = str(kopf.get("name") or "").strip()
    if not name:
        raise ManifestFehler(f"In {datei} fehlt unter [projekt] das Feld `name`.")

    skripte = tuple(
        _skript(eintrag, nummer, projekt, datei)
        for nummer, eintrag in enumerate(roh.get("skript") or [], start=1)
    )
    return Manifest(
        name=name,
        beschreibung=str(kopf.get("beschreibung") or ""),
        projekt=projekt,
        skripte=skripte,
    )


def _skript(eintrag, nummer, projekt, datei):
    name = str(eintrag.get("name") or "").strip()
    if not name:
        raise ManifestFehler(f"In {datei} fehlt bei Skript {nummer} das Feld `name`.")
    roh_datei = str(eintrag.get("datei") or "").strip()
    if not roh_datei:
        raise ManifestFehler(
            f"In {datei} fehlt bei Skript {nummer} („{name}“) das Feld `datei`."
        )
    argumente = eintrag.get("argumente") or []
    if not all(isinstance(a, str) for a in argumente):
        raise ManifestFehler(
            f"In {datei} müssen bei Skript {nummer} („{name}“) alle `argumente` "
            "Texte sein — auch Zahlen, also [\"--episoden\", \"20\"]."
        )
    return Skript(
        name=name,
        datei=(projekt / roh_datei).resolve(),
        argumente=tuple(argumente),
        # Kein Standardwert True: das machte den haeufigen Fall zur Ausnahme.
        # Die Sicherheit haengt an der Schranke in Aufgabe 5, nicht an diesem Feld.
        roboter=bool(eintrag.get("roboter", False)),
        beschreibung=str(eintrag.get("beschreibung") or ""),
    )


def als_json(manifest):
    return {
        "name": manifest.name,
        "beschreibung": manifest.beschreibung,
        "projekt": str(manifest.projekt),
        "skripte": [
            {
                "name": s.name,
                "datei": str(s.datei),
                "argumente": list(s.argumente),
                "roboter": s.roboter,
                "beschreibung": s.beschreibung,
            }
            for s in manifest.skripte
        ],
    }


def aus_json(daten):
    return Manifest(
        name=daten.get("name", ""),
        beschreibung=daten.get("beschreibung", ""),
        projekt=Path(daten.get("projekt", "")),
        skripte=tuple(
            Skript(
                name=s.get("name", ""),
                datei=Path(s.get("datei", "")),
                argumente=tuple(s.get("argumente") or ()),
                roboter=bool(s.get("roboter", False)),
                beschreibung=s.get("beschreibung", ""),
            )
            for s in daten.get("skripte") or []
        ),
    )


def skript_von(manifest, name):
    for skript in manifest.skripte:
        if skript.name == name:
            return skript
    return None
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_anbindung_manifest.py -q
```

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/anbindung/ tests/test_anbindung_manifest.py
git commit -m "feat(anbindung): Manifest fremder Projekte aus spotlab.toml"
```

---

## Aufgabe 3: `anbindung/speicher.py` — der Anbindungsordner

**Dateien:**
- Anlegen: `src/spotlab/anbindung/speicher.py`
- Test: `tests/test_anbindung_speicher.py`

**Schnittstellen:**
- Verbraucht: `sicherer_name` (Aufgabe 1); `Manifest`, `lies`, `als_json`, `aus_json` (Aufgabe 2).
- Liefert: `Anbindung(name, ordner, manifest, quelle, angebunden, vorhanden)`,
  `wurzel(workspace)`, `binde_an(workspace, projektpfad, jetzt=None) -> Anbindung`,
  `anbindungen(workspace) -> list[Anbindung]`, `finde(workspace, name) -> Anbindung`,
  `loese(workspace, name) -> bool`, `panelordner(anbindung) -> Path`,
  `lauf_verzeichnisse_von(anbindung) -> list[Path]`.
  Aufgabe 4 legt Panels hinein, Aufgabe 5 leitet Lauf-Verzeichnisse ab.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_anbindung_speicher.py`:

```python
import json

import pytest

from spotlab.anbindung.manifest import DATEINAME, ManifestFehler
from spotlab.anbindung.speicher import (
    anbindungen,
    binde_an,
    finde,
    lauf_verzeichnisse_von,
    loese,
    panelordner,
    wurzel,
)

MANIFEST = """
[projekt]
name = "matura-spot"
beschreibung = "MuJoCo-Simulation"

[[skript]]
name = "Baseline"
datei = "scripts/experiment_baseline.py"
argumente = ["--episoden", "20"]

[[skript]]
name = "Zweites im selben Ordner"
datei = "scripts/explorer_demo.py"
"""


def _fremdes_projekt(tmp_path, name="matura-spot", inhalt=MANIFEST):
    projekt = tmp_path / name
    (projekt / "scripts").mkdir(parents=True)
    (projekt / "scripts" / "experiment_baseline.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / "scripts" / "explorer_demo.py").write_text("y = 2\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(inhalt, encoding="utf-8")
    return projekt


def test_anbinden_legt_den_ordner_an(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = _fremdes_projekt(tmp_path)
    gebunden = binde_an(arbeit, projekt)
    assert gebunden.ordner == wurzel(arbeit) / "matura-spot"
    assert (gebunden.ordner / "anbindung.json").is_file()
    assert panelordner(gebunden).is_dir()
    assert gebunden.vorhanden is True


def test_anbindung_json_enthaelt_manifest_und_quelle(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = _fremdes_projekt(tmp_path)
    gebunden = binde_an(arbeit, projekt)
    daten = json.loads((gebunden.ordner / "anbindung.json").read_text(encoding="utf-8"))
    assert daten["quelle"] == str(projekt.resolve())
    assert daten["manifest"]["name"] == "matura-spot"
    assert daten["angebunden"]


def test_auflisten_und_finden(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    binde_an(arbeit, _fremdes_projekt(tmp_path, "eins"))
    binde_an(arbeit, _fremdes_projekt(tmp_path, "zwei", MANIFEST.replace("matura-spot", "zwei")))
    assert {a.name for a in anbindungen(arbeit)} == {"matura-spot", "zwei"}
    assert finde(arbeit, "zwei").name == "zwei"


def test_finden_ohne_treffer_wirft(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    with pytest.raises(Exception) as fehler:
        finde(arbeit, "gibtsnicht")
    assert "gibtsnicht" in str(fehler.value)


def test_erneutes_anbinden_laesst_panels_stehen(tmp_path):
    """Ein Agent, der nach jeder Manifestaenderung neu anbindet, darf nichts verlieren."""
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = _fremdes_projekt(tmp_path)
    gebunden = binde_an(arbeit, projekt)
    (panelordner(gebunden) / "test.json").write_text("{}", encoding="utf-8")
    wieder = binde_an(arbeit, projekt)
    assert (panelordner(wieder) / "test.json").is_file()


def test_verschwundenes_projekt_bleibt_lesbar(tmp_path):
    """Panels bleiben sichtbar, nur die Skripte gehen aus."""
    import shutil

    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    shutil.rmtree(projekt)
    gebunden = finde(arbeit, "matura-spot")
    assert gebunden.vorhanden is False
    assert gebunden.manifest.name == "matura-spot"      # aus der Kopie
    assert str(projekt.resolve()) == str(gebunden.quelle)


def test_gefaehrlicher_projektname_bleibt_im_ordner(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = _fremdes_projekt(tmp_path, "boes", MANIFEST.replace("matura-spot", "../../weg"))
    gebunden = binde_an(arbeit, projekt)
    assert gebunden.ordner.parent == wurzel(arbeit)
    assert ".." not in gebunden.ordner.name


def test_ohne_manifest_wirft(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    leer = tmp_path / "leer"
    leer.mkdir()
    with pytest.raises(ManifestFehler):
        binde_an(arbeit, leer)


def test_loesen_entfernt_den_ordner(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    binde_an(arbeit, _fremdes_projekt(tmp_path))
    assert loese(arbeit, "matura-spot") is True
    assert anbindungen(arbeit) == []
    assert loese(arbeit, "matura-spot") is False


def test_lauf_verzeichnisse_kommen_aus_dem_manifest(tmp_path):
    """Ohne das bliebe „Live-Lauf" bei fremden Projekten leer — der Fehler aus Stufe 3."""
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = _fremdes_projekt(tmp_path)
    gebunden = binde_an(arbeit, projekt)
    assert lauf_verzeichnisse_von(gebunden) == [(projekt / "scripts" / "runs").resolve()]


def test_leerer_arbeitsordner_ergibt_leere_liste(tmp_path):
    assert anbindungen(tmp_path / "gibtsnicht") == []
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_anbindung_speicher.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.anbindung.speicher'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/anbindung/speicher.py`:

```python
"""Der Anbindungsordner — Ablage und Datenkanal in einem.

<arbeitsordner>/anbindungen/<name>/
    anbindung.json          Manifest-Kopie, Quellpfad, Zeitpunkt
    panels/<name>.json

Registrieren heisst: diesen Ordner anlegen. Etwas zeigen heisst: eine Datei
hineinschreiben. Ein Begriff, nicht zwei.

Das Manifest wird HINEINKOPIERT, nicht nur verlinkt: dann braucht die GUI das
fremde Repo nicht. Ist die Platte ab oder der Ordner umbenannt, bleiben die
Panels sichtbar und nur die Skript-Knoepfe gehen aus.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from spotlab.anbindung.manifest import Manifest, als_json, aus_json, lies
from spotlab.errors import SpotlabError
from spotlab.pfade import sicherer_name

ORDNER = "anbindungen"
BESCHREIBUNG = "anbindung.json"
PANELS = "panels"


@dataclass(frozen=True)
class Anbindung:
    name: str
    ordner: Path
    manifest: Manifest
    quelle: Path
    angebunden: str
    vorhanden: bool


def wurzel(workspace):
    return Path(workspace) / ORDNER


def panelordner(anbindung):
    return anbindung.ordner / PANELS


def binde_an(workspace, projektpfad, jetzt=None):
    """Liest das Manifest und legt den Anbindungsordner an. Idempotent."""
    manifest = lies(projektpfad)
    ordner = wurzel(workspace) / sicherer_name(manifest.name, ersatz="projekt")
    (ordner / PANELS).mkdir(parents=True, exist_ok=True)
    zeit = (jetzt or datetime.now(UTC)).isoformat()
    (ordner / BESCHREIBUNG).write_text(
        json.dumps(
            {
                "quelle": str(manifest.projekt),
                "angebunden": zeit,
                "manifest": als_json(manifest),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return _lade(ordner)


def anbindungen(workspace):
    try:
        ordner = sorted(
            (p for p in wurzel(workspace).iterdir() if p.is_dir()), key=lambda p: p.name
        )
    except OSError:
        return []
    gefunden = []
    for eintrag in ordner:
        geladen = _lade(eintrag)
        if geladen is not None:
            gefunden.append(geladen)
    return gefunden


def finde(workspace, name):
    for anbindung in anbindungen(workspace):
        if anbindung.name == name or anbindung.ordner.name == name:
            return anbindung
    raise SpotlabError(
        f"Es ist kein Projekt namens „{name}“ angebunden. "
        "Bekannte Projekte zeigt die Ansicht „Anbindungen“."
    )


def loese(workspace, name):
    import shutil

    try:
        anbindung = finde(workspace, name)
    except SpotlabError:
        return False
    shutil.rmtree(anbindung.ordner, ignore_errors=True)
    return not anbindung.ordner.exists()


def lauf_verzeichnisse_von(anbindung):
    """Wo die Laeufe dieses Projekts landen.

    start_script startet mit cwd=<skriptordner>, und connect() legt Laeufe unter
    <skriptordner>/runs/ an. Das liegt AUSSERHALB des Arbeitsordners, den der
    RunWatcher durchsucht — ohne diese Ableitung bliebe „Live-Lauf" bei fremden
    Projekten leer, obwohl der Lauf laeuft. Derselbe Fehler wie in Stufe 3.

    Abgeleitet statt gesucht: nur die Ordner, die im Manifest stehen, kein
    rekursives Absuchen fremder Repos.
    """
    gesehen = {}
    for skript in anbindung.manifest.skripte:
        runs = (skript.datei.parent / "runs").resolve()
        gesehen[str(runs)] = runs
    return list(gesehen.values())


def _lade(ordner):
    datei = Path(ordner) / BESCHREIBUNG
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    manifest = aus_json(daten.get("manifest") or {})
    quelle = Path(daten.get("quelle") or "")
    return Anbindung(
        name=manifest.name or Path(ordner).name,
        ordner=Path(ordner),
        manifest=manifest,
        quelle=quelle,
        angebunden=daten.get("angebunden") or "",
        vorhanden=quelle.is_dir(),
    )
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_anbindung_speicher.py -q
```

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/anbindung/speicher.py tests/test_anbindung_speicher.py
git commit -m "feat(anbindung): Anbindungsordner als Ablage und Datenkanal"
```

---

## Aufgabe 4: `anbindung/panel.py` — die fünf Arten

**Dateien:**
- Anlegen: `src/spotlab/anbindung/panel.py`
- Test: `tests/test_anbindung_panel.py`

**Schnittstellen:**
- Verbraucht: `Anbindung`, `panelordner` (Aufgabe 3).
- Liefert: `ARTEN`, `Panel(name, titel, art, stand, inhalt, fehler)`,
  `schreibe(anbindung, name, art, titel, inhalt, jetzt=None) -> Path`,
  `lies(pfad) -> Panel`, `panels(anbindung) -> list[Panel]`,
  `entferne(anbindung, name) -> bool`, `bild_erlaubt(pfad, anbindung) -> bool`,
  `pruefe_inhalt(art, inhalt) -> str | None`.
  Aufgabe 6 schreibt Panels über MCP, Aufgabe 9 zeichnet sie.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_anbindung_panel.py`:

```python
import pytest

from spotlab.anbindung.manifest import DATEINAME
from spotlab.anbindung.panel import (
    ARTEN,
    bild_erlaubt,
    entferne,
    lies,
    panels,
    pruefe_inhalt,
    schreibe,
)
from spotlab.anbindung.speicher import binde_an, panelordner

MANIFEST = '[projekt]\nname = "p"\n\n[[skript]]\nname = "s"\ndatei = "s.py"\n'


@pytest.fixture()
def gebunden(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = tmp_path / "fremd"
    projekt.mkdir()
    (projekt / "s.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(MANIFEST, encoding="utf-8")
    return binde_an(arbeit, projekt)


KENNZAHLEN = [{"name": "success", "wert": "95 %", "hinweis": "19 von 20"}]


def test_alle_fuenf_arten_sind_bekannt():
    assert ARTEN == ("kennzahlen", "tabelle", "reihe", "bild", "text")


def test_schreiben_und_lesen_im_kreis(gebunden):
    pfad = schreibe(gebunden, "baseline", "kennzahlen", "Baseline", KENNZAHLEN)
    panel = lies(pfad)
    assert panel.fehler is None
    assert panel.name == "baseline"
    assert panel.titel == "Baseline"
    assert panel.art == "kennzahlen"
    assert panel.inhalt == KENNZAHLEN
    assert panel.stand


def test_ueberschreiben_ersetzt(gebunden):
    schreibe(gebunden, "baseline", "kennzahlen", "Alt", KENNZAHLEN)
    schreibe(gebunden, "baseline", "kennzahlen", "Neu", KENNZAHLEN)
    assert [p.titel for p in panels(gebunden)] == ["Neu"]


def test_atomares_schreiben_laesst_keine_reste(gebunden):
    schreibe(gebunden, "baseline", "kennzahlen", "Baseline", KENNZAHLEN)
    reste = list(panelordner(gebunden).glob("*.neu"))
    assert reste == []


def test_kaputtes_json_ergibt_ein_panel_mit_fehler(gebunden):
    """Ein halb geschriebenes Panel darf die Ansicht nicht leeren."""
    pfad = panelordner(gebunden) / "halb.json"
    pfad.write_text('{"titel": "abgeschnit', encoding="utf-8")
    panel = lies(pfad)
    assert panel.fehler is not None
    assert panel.name == "halb"


def test_ein_kaputtes_panel_laesst_die_anderen_stehen(gebunden):
    schreibe(gebunden, "gut", "kennzahlen", "Gut", KENNZAHLEN)
    (panelordner(gebunden) / "kaputt.json").write_text("{", encoding="utf-8")
    ergebnis = {p.name: p.fehler is None for p in panels(gebunden)}
    assert ergebnis == {"gut": True, "kaputt": False}


def test_unbekannte_art_nennt_die_bekannten(gebunden):
    pfad = panelordner(gebunden) / "fremd.json"
    pfad.write_text('{"art": "torte", "titel": "x", "inhalt": []}', encoding="utf-8")
    panel = lies(pfad)
    assert panel.fehler is not None
    assert "kennzahlen" in panel.fehler


@pytest.mark.parametrize(
    "art, inhalt",
    [
        ("kennzahlen", [{"name": "a", "wert": "1"}]),
        ("tabelle", {"spalten": ["a"], "zeilen": [["1"]]}),
        ("reihe", {"x": [0, 1], "y": [1.0, 2.0], "x_name": "t", "y_name": "v"}),
        ("bild", {"pfad": "out/bild.png"}),
        ("text", {"absaetze": ["hallo"]}),
    ],
)
def test_gueltige_inhalte(art, inhalt):
    assert pruefe_inhalt(art, inhalt) is None


@pytest.mark.parametrize(
    "art, inhalt",
    [
        ("kennzahlen", {"name": "a"}),                      # kein Liste
        ("kennzahlen", [{"wert": "1"}]),                    # ohne name
        ("tabelle", {"spalten": ["a"]}),                    # ohne zeilen
        ("tabelle", {"spalten": ["a", "b"], "zeilen": [["1"]]}),   # Zeile zu kurz
        ("reihe", {"x": [0, 1], "y": [1.0]}),               # ungleich lang
        ("bild", {}),                                        # ohne pfad
        ("text", {"absaetze": "kein Liste"}),
    ],
)
def test_ungueltige_inhalte_werden_benannt(art, inhalt):
    grund = pruefe_inhalt(art, inhalt)
    assert grund and isinstance(grund, str)


def test_schreiben_mit_ungueltigem_inhalt_wirft(gebunden):
    from spotlab.errors import SpotlabError

    with pytest.raises(SpotlabError):
        schreibe(gebunden, "x", "tabelle", "X", {"spalten": ["a"]})


def test_bild_aus_dem_projekt_ist_erlaubt(gebunden):
    ziel = gebunden.quelle / "out" / "bild.png"
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(b"\x89PNG")
    assert bild_erlaubt(ziel, gebunden) is True


def test_bild_aus_dem_anbindungsordner_ist_erlaubt(gebunden):
    ziel = gebunden.ordner / "eigen.png"
    ziel.write_bytes(b"\x89PNG")
    assert bild_erlaubt(ziel, gebunden) is True


def test_bild_von_ausserhalb_ist_verboten(gebunden, tmp_path):
    """Eine Datei, die sagt „zeig das hier", darf nicht auf Beliebiges deuten."""
    fremd = tmp_path / "geheim.png"
    fremd.write_bytes(b"\x89PNG")
    assert bild_erlaubt(fremd, gebunden) is False


def test_entfernen(gebunden):
    schreibe(gebunden, "weg", "kennzahlen", "Weg", KENNZAHLEN)
    assert entferne(gebunden, "weg") is True
    assert entferne(gebunden, "weg") is False


def test_panelname_kann_nicht_ausbrechen(gebunden):
    pfad = schreibe(gebunden, "../../weg", "kennzahlen", "X", KENNZAHLEN)
    assert pfad.parent == panelordner(gebunden)
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_anbindung_panel.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.anbindung.panel'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/anbindung/panel.py`:

```python
"""Panels: was ein fremdes Projekt zu sagen hat, als Daten statt als Code.

Fuenf Arten, jede auf ein Widget, das spotlab schon hat. Ein Panel waehlt KEINE
Farben — sonst gibt es einen Hell/Dunkel-Modus, in dem fremde Daten unlesbar sind.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from spotlab.anbindung.speicher import panelordner
from spotlab.errors import SpotlabError
from spotlab.pfade import sicherer_name

ARTEN = ("kennzahlen", "tabelle", "reihe", "bild", "text")


@dataclass(frozen=True)
class Panel:
    name: str
    titel: str
    art: str
    stand: str
    inhalt: object
    fehler: str | None = None


def pruefe_inhalt(art, inhalt):
    """Gibt einen deutschen Grund zurueck — oder None, wenn der Inhalt passt."""
    if art == "kennzahlen":
        if not isinstance(inhalt, list):
            return "`inhalt` muss bei `kennzahlen` eine Liste sein."
        for eintrag in inhalt:
            if not isinstance(eintrag, dict) or "name" not in eintrag or "wert" not in eintrag:
                return "Jede Kennzahl braucht `name` und `wert`."
        return None
    if art == "tabelle":
        if not isinstance(inhalt, dict) or "spalten" not in inhalt or "zeilen" not in inhalt:
            return "`inhalt` braucht bei `tabelle` die Felder `spalten` und `zeilen`."
        spalten = inhalt["spalten"]
        if not isinstance(spalten, list) or not isinstance(inhalt["zeilen"], list):
            return "`spalten` und `zeilen` müssen Listen sein."
        for zeile in inhalt["zeilen"]:
            if not isinstance(zeile, list) or len(zeile) != len(spalten):
                return f"Jede Zeile braucht genau {len(spalten)} Werte."
        return None
    if art == "reihe":
        if not isinstance(inhalt, dict) or "x" not in inhalt or "y" not in inhalt:
            return "`inhalt` braucht bei `reihe` die Felder `x` und `y`."
        if not isinstance(inhalt["x"], list) or not isinstance(inhalt["y"], list):
            return "`x` und `y` müssen Listen sein."
        if len(inhalt["x"]) != len(inhalt["y"]):
            return "`x` und `y` müssen gleich lang sein."
        return None
    if art == "bild":
        if not isinstance(inhalt, dict) or not inhalt.get("pfad"):
            return "`inhalt` braucht bei `bild` das Feld `pfad`."
        return None
    if art == "text":
        if not isinstance(inhalt, dict) or not isinstance(inhalt.get("absaetze"), list):
            return "`inhalt` braucht bei `text` das Feld `absaetze` als Liste."
        return None
    return f"Unbekannte Art „{art}“. Bekannt sind: {', '.join(ARTEN)}."


def schreibe(anbindung, name, art, titel, inhalt, jetzt=None):
    grund = pruefe_inhalt(art, inhalt)
    if grund is not None:
        raise SpotlabError(grund)
    ordner = panelordner(anbindung)
    ordner.mkdir(parents=True, exist_ok=True)
    sicher = sicherer_name(name, ersatz="panel")
    ziel = ordner / f"{sicher}.json"
    daten = {
        "titel": str(titel),
        "art": art,
        "stand": (jetzt or datetime.now(UTC)).isoformat(),
        "inhalt": inhalt,
    }
    # Atomar: erst daneben, dann umbenennen. Ein Leser sieht nie eine halbe Datei.
    zwischen = ordner / f"{sicher}.json.neu"
    zwischen.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(zwischen, ziel)
    return ziel


def lies(pfad):
    """Wirft NIE.

    Ein Panel, das im Sekundentakt ueberschrieben wird, ist regelmaessig fuer
    Millisekunden halb geschrieben. Eine Ansicht, die daran leer wird, flackert
    im Betrieb — und EIN kaputtes Panel darf die anderen vier nicht loeschen.
    """
    pfad = Path(pfad)
    name = pfad.stem
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as fehler:
        return Panel(name, name, "", "", None, f"Datei nicht lesbar: {fehler}")
    if not isinstance(daten, dict):
        return Panel(name, name, "", "", None, "Die Datei enthält kein JSON-Objekt.")
    art = str(daten.get("art") or "")
    titel = str(daten.get("titel") or name)
    stand = str(daten.get("stand") or "")
    inhalt = daten.get("inhalt")
    grund = pruefe_inhalt(art, inhalt)
    return Panel(name, titel, art, stand, inhalt, grund)


def panels(anbindung):
    ordner = panelordner(anbindung)
    try:
        dateien = sorted(ordner.glob("*.json"), key=lambda p: p.name)
    except OSError:
        return []
    return [lies(p) for p in dateien]


def entferne(anbindung, name):
    ziel = panelordner(anbindung) / f"{sicherer_name(name, ersatz='panel')}.json"
    try:
        ziel.unlink()
    except OSError:
        return False
    return True


def bild_erlaubt(pfad, anbindung):
    """Nur unterhalb des Projekts oder des Anbindungsordners.

    Dieselbe Regel und derselbe Grund wie bei den anklickbaren Tracebacks in
    Stufe 5: eine Datei, die sagt „zeig das hier", darf nicht auf Beliebiges im
    Dateisystem deuten.
    """
    try:
        ziel = Path(pfad).resolve()
    except (OSError, ValueError):
        return False
    for erlaubt in (anbindung.quelle, anbindung.ordner):
        try:
            if ziel.is_relative_to(Path(erlaubt).resolve()):
                return True
        except (OSError, ValueError):
            continue
    return False
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_anbindung_panel.py -q
```

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/anbindung/panel.py tests/test_anbindung_panel.py
git commit -m "feat(anbindung): Panels in fuenf Arten, kaputte Dateien isoliert"
```

---

## Aufgabe 5: Die Trockenlauf-Schranke

**Dateien:**
- Ändern: `src/spotlab/__init__.py` (`ENV_NUR_TROCKEN`, Prüfung in `connect`)
- Ändern: `src/spotlab/workshop/launcher.py` (`argumente`, `nur_trocken`)
- Test: `tests/test_schranke.py`

**Schnittstellen:**
- Verbraucht: nichts.
- Liefert: `spotlab.ENV_NUR_TROCKEN = "SPOTLAB_NUR_TROCKEN"`;
  `start_script(pfad, dryrun=False, argumente=(), nur_trocken=False, starter=subprocess.Popen)`.
  Aufgabe 7 startet damit.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_schranke.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

from spotlab import ENV_NUR_TROCKEN
from spotlab.workshop.launcher import start_script

QUELLE = str(Path(__file__).resolve().parents[1] / "src")


def _umgebung(**extra):
    return {**os.environ, "PYTHONPATH": QUELLE, "PYTHONUTF8": "1", **extra}


def _lauf(tmp_path, quelltext, **extra):
    skript = tmp_path / "versuch.py"
    skript.write_text(quelltext, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(skript)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=_umgebung(**extra),
    )


def test_ohne_schranke_laeuft_der_trockenlauf(tmp_path):
    ergebnis = _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect(backend='dryrun') as spot:\n    print('ok')\n",
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "ok" in ergebnis.stdout


def test_schranke_erlaubt_den_trockenlauf(tmp_path):
    ergebnis = _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect(backend='dryrun') as spot:\n    print('ok')\n",
        **{ENV_NUR_TROCKEN: "1"},
    )
    assert ergebnis.returncode == 0, ergebnis.stderr


def test_schranke_weist_explizites_real_ab(tmp_path):
    """DER Test dieser Aufgabe.

    SPOTLAB_BACKEND allein genuegt nicht: connect() liest
    `backend or os.environ.get(...)`, ein explizites backend="real"
    ueberschreibt die Variable. Ein veraltetes Manifest darf den Roboter
    nicht bewegen koennen.
    """
    ergebnis = _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect(backend='real') as spot:\n    print('nie')\n",
        **{ENV_NUR_TROCKEN: "1"},
    )
    assert ergebnis.returncode != 0
    assert "nie" not in ergebnis.stdout
    assert "ohne Roboter" in (ergebnis.stdout + ergebnis.stderr)


def test_schranke_weist_auch_die_backend_variable_ab(tmp_path):
    ergebnis = _lauf(
        tmp_path,
        "import spotlab\nwith spotlab.connect() as spot:\n    print('nie')\n",
        **{ENV_NUR_TROCKEN: "1", "SPOTLAB_BACKEND": "real"},
    )
    assert ergebnis.returncode != 0
    assert "nie" not in ergebnis.stdout


def test_start_script_reicht_argumente_durch(tmp_path):
    skript = tmp_path / "args.py"
    skript.write_text("import sys\nprint('|'.join(sys.argv[1:]))\n", encoding="utf-8")
    prozess = start_script(skript, argumente=("--episoden", "20", "--archiv"))
    ausgabe = prozess.stdout.read()
    prozess.wait()
    assert "--episoden|20|--archiv" in ausgabe


def test_start_script_setzt_die_schranke(tmp_path):
    skript = tmp_path / "zeig.py"
    skript.write_text(
        f"import os\nprint(os.environ.get({ENV_NUR_TROCKEN!r}))\n", encoding="utf-8"
    )
    prozess = start_script(skript, nur_trocken=True)
    ausgabe = prozess.stdout.read()
    prozess.wait()
    assert "1" in ausgabe


def test_start_script_setzt_die_schranke_nicht_von_selbst(tmp_path):
    skript = tmp_path / "zeig.py"
    skript.write_text(
        f"import os\nprint(os.environ.get({ENV_NUR_TROCKEN!r}, 'nicht gesetzt'))\n",
        encoding="utf-8",
    )
    prozess = start_script(skript)
    ausgabe = prozess.stdout.read()
    prozess.wait()
    assert "nicht gesetzt" in ausgabe
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_schranke.py -q
```

Erwartet: `ImportError: cannot import name 'ENV_NUR_TROCKEN' from 'spotlab'`.

- [ ] **Schritt 3: Umsetzen**

In `src/spotlab/__init__.py` neben `ENV_BACKEND`:

```python
ENV_BACKEND = "SPOTLAB_BACKEND"
ENV_NUR_TROCKEN = "SPOTLAB_NUR_TROCKEN"
```

In `connect()`, direkt **nach** der Zeile, die `art` bestimmt:

```python
    art = backend or os.environ.get(ENV_BACKEND) or (cfg.default_backend if cfg else "dryrun")

    # Obergrenze, nicht Vorgabe. SPOTLAB_BACKEND allein genuegt nicht: ein
    # explizites backend="real" ueberschreibt die Variable und kaeme an den
    # Roboter. Abgewiesen statt stillschweigend heruntergestuft — ein Skript,
    # das glaubt, es fahre den echten Spot, meldet sonst Unsinn.
    if os.environ.get(ENV_NUR_TROCKEN) == "1" and art != "dryrun":
        raise SpotlabError(
            "Dieser Lauf wurde ohne Roboter gestartet und darf keinen anfordern. "
            "Starte das Programm selbst im Fenster, wenn der Spot fahren soll."
        )
```

`SpotlabError` wird in `connect()` bereits importiert (`from spotlab.errors import
ConfigMissing, LeaseLost, SpotlabError`) — die Zeile steht vor dieser Stelle.

**Wichtig:** Die Prüfung muss **vor** dem Anlegen des `RunRecorder` stehen, sonst entsteht
ein leeres Lauf-Verzeichnis für einen Lauf, den es nie gab.

In `src/spotlab/workshop/launcher.py`:

```python
def _umgebung(dryrun, nur_trocken=False):
    umgebung = dict(os.environ)
    if dryrun:
        umgebung[ENV_BACKEND] = "dryrun"
    if nur_trocken:
        umgebung[ENV_NUR_TROCKEN] = "1"
    ...
```

mit `ENV_NUR_TROCKEN = "SPOTLAB_NUR_TROCKEN"` neben dem bestehenden `ENV_BACKEND` in
derselben Datei, und:

```python
def start_script(pfad, dryrun=False, argumente=(), nur_trocken=False, starter=subprocess.Popen):
    """Startet das Skript und kehrt SOFORT zurück. Gibt den Prozess-Handle zurück.

    `argumente` wird als Liste an den Prozess gereicht, nie über eine Shell
    zusammengesetzt. `nur_trocken` setzt die Obergrenze aus __init__.py.
    """
    skript = Path(pfad).resolve()
    if not skript.exists():
        raise SpotlabError(f"Die Datei {skript} gibt es nicht.")

    return starter(
        [sys.executable, "-u", str(skript), *argumente],
        cwd=str(skript.parent),
        env=_umgebung(dryrun, nur_trocken=nur_trocken),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
```

`run_script` bleibt unverändert; es reicht seine Argumente nicht weiter, weil die
Kommandozeile keine kennt.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_schranke.py -q
python -m pytest -q
```

Erwartet: beide grün. Schlägt `test_schranke_weist_explizites_real_ab` mit einem
Verbindungsfehler statt der Meldung fehl, steht die Prüfung zu spät — sie muss vor jedem
Netzzugriff greifen.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/__init__.py src/spotlab/workshop/launcher.py tests/test_schranke.py
git commit -m "feat: Trockenlauf-Schranke als Obergrenze, Argumente fuer start_script"
```

---

**Ende Teil 1.** Weiter mit `docs/superpowers/plans/2026-08-07-spotlab-anbindung-teil2.md`
(Aufgaben 6–11: MCP-Werkzeuge, Server, Watcher, Ansicht, Verdrahtung, Doku).
