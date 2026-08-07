# spotlab Anbindung Implementierungsplan — Teil 2 (Aufgaben 6–12)

> **Für agentische Arbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development`
> (empfohlen) oder `superpowers:executing-plans`. Schritte sind Checkboxen (`- [ ]`).

**Fortsetzung von** `docs/superpowers/plans/2026-08-07-spotlab-anbindung.md`.
**Die „Globalen Vorgaben" aus Teil 1 gelten unverändert.**

**Voraussetzungen aus Teil 1** (Aufgaben 1–5 abgeschlossen):

| Modul | Was daraus benutzt wird |
|---|---|
| `spotlab.pfade` | `sicherer_name(name, ersatz="ordner")` |
| `spotlab.anbindung.manifest` | `Manifest`, `Skript`, `lies`, `skript_von`, `ManifestFehler`, `DATEINAME` |
| `spotlab.anbindung.speicher` | `Anbindung`, `binde_an`, `anbindungen`, `finde`, `loese`, `panelordner`, `lauf_verzeichnisse_von` |
| `spotlab.anbindung.panel` | `ARTEN`, `Panel`, `schreibe`, `lies`, `panels`, `entferne`, `bild_erlaubt`, `pruefe_inhalt` |
| `spotlab` | `ENV_NUR_TROCKEN` |
| `spotlab.workshop.launcher` | `start_script(pfad, dryrun, argumente, nur_trocken)` |

**Vorhandenes, das wiederverwendet und nicht nachgebaut wird:**

| Baustein | Wo |
|---|---|
| `RunSummary`, `read_run`, `list_runs`, `read_jsonl` | `spotlab.record.read` |
| `MapInfo`, `karten`, `finde`, `lade_graph` | `spotlab.maps.store` |
| `stoppe_freundlich`, `ist_aktiv` | `spotlab.workshop.control` |
| `diagnose`, `Check` | `spotlab.workshop.doctor` |
| `load_config` | `spotlab.config` |
| Kacheln, Tabelle, Kurve | `gui/views/live.py`, `gui/views/runs.py`, `gui/mapplot.py` |

---

## Aufgabe 6: `laufsuche.py` — ein Ort, an dem Läufe gefunden werden

**Warum eine eigene Datei:** Die GUI und der MCP-Server müssen dieselben Läufe finden.
`gui/watcher.py::lauf_verzeichnisse` ist zwar Qt-frei geschrieben, liegt aber in einem Modul,
das PySide6 importiert — der MCP-Server könnte es nicht benutzen, ohne Qt hereinzuziehen.
Zwei Suchen mit verschiedenen Ergebnissen wären genau der Fehler, den Stufe 3 schon hatte.

**Dateien:**
- Anlegen: `src/spotlab/laufsuche.py`
- Ändern: `src/spotlab/gui/watcher.py` (eigene Funktion durch Import ersetzen)
- Test: `tests/test_laufsuche.py`

**Schnittstellen:**
- Verbraucht: `anbindungen`, `lauf_verzeichnisse_von` (Aufgabe 3).
- Liefert: `lauf_verzeichnisse(workspace) -> list[Path]`,
  `finde_lauf(workspace, lauf_id) -> Path | None`.
  `gui/watcher.py` exportiert `lauf_verzeichnisse` unter demselben Namen weiter, damit
  `tests/test_gui_watcher.py` unverändert läuft. Aufgabe 8 benutzt beide.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_laufsuche.py`:

```python
from spotlab.anbindung.manifest import DATEINAME
from spotlab.anbindung.speicher import binde_an
from spotlab.laufsuche import finde_lauf, lauf_verzeichnisse

MANIFEST = '[projekt]\nname = "fremd"\n\n[[skript]]\nname = "s"\ndatei = "scripts/s.py"\n'


def _werkstatt(tmp_path):
    arbeit = tmp_path / "werkstatt"
    (arbeit / "demo" / "runs" / "20260807T101010Z").mkdir(parents=True)
    return arbeit


def _fremdes_projekt(tmp_path):
    projekt = tmp_path / "fremd"
    (projekt / "scripts").mkdir(parents=True)
    (projekt / "scripts" / "s.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(MANIFEST, encoding="utf-8")
    return projekt


def test_findet_laeufe_der_werkstatt(tmp_path):
    arbeit = _werkstatt(tmp_path)
    namen = [p.name for p in lauf_verzeichnisse(arbeit)]
    assert namen == ["20260807T101010Z"]


def test_findet_laeufe_eines_angebundenen_projekts(tmp_path):
    """Ohne das bliebe „Live-Lauf" bei fremden Projekten leer — der Fehler aus Stufe 3.

    Laeufe landen unter <skriptordner>/runs/, also AUSSERHALB des Arbeitsordners.
    """
    arbeit = _werkstatt(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    (projekt / "scripts" / "runs" / "20260807T120000Z").mkdir(parents=True)

    gefunden = {p.name for p in lauf_verzeichnisse(arbeit)}
    assert gefunden == {"20260807T101010Z", "20260807T120000Z"}


def test_kein_doppelter_eintrag(tmp_path):
    arbeit = _werkstatt(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    binde_an(arbeit, projekt)
    (projekt / "scripts" / "runs" / "20260807T120000Z").mkdir(parents=True)
    pfade = lauf_verzeichnisse(arbeit)
    assert len(pfade) == len(set(map(str, pfade)))


def test_fehlendes_fremdprojekt_stoert_nicht(tmp_path):
    import shutil

    arbeit = _werkstatt(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    shutil.rmtree(projekt)
    assert [p.name for p in lauf_verzeichnisse(arbeit)] == ["20260807T101010Z"]


def test_finde_lauf_ueber_beide_orte(tmp_path):
    arbeit = _werkstatt(tmp_path)
    projekt = _fremdes_projekt(tmp_path)
    binde_an(arbeit, projekt)
    (projekt / "scripts" / "runs" / "20260807T120000Z").mkdir(parents=True)

    assert finde_lauf(arbeit, "20260807T101010Z").name == "20260807T101010Z"
    assert finde_lauf(arbeit, "20260807T120000Z").name == "20260807T120000Z"
    assert finde_lauf(arbeit, "gibtsnicht") is None


def test_laufsuche_ist_qt_frei():
    import pathlib

    import spotlab.laufsuche as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in quelle


def test_watcher_exportiert_dieselbe_funktion():
    from spotlab.gui.watcher import lauf_verzeichnisse as aus_watcher

    assert aus_watcher is lauf_verzeichnisse
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_laufsuche.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.laufsuche'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/laufsuche.py`:

```python
"""Wo Laeufe liegen — der EINE Ort, an dem das entschieden wird.

Laeufe liegen an zwei Stellen: unter <arbeitsordner>/<projekt>/runs/ und, bei
angebundenen fremden Projekten, unter <skriptordner>/runs/. Der zweite Ort
liegt AUSSERHALB des Arbeitsordners; ohne ihn bliebe „Live-Lauf" bei fremden
Projekten leer, obwohl der Lauf laeuft — derselbe Fehler wie in Stufe 3.

Abgeleitet statt gesucht: nur die Ordner, die im Manifest stehen. Kein
rekursives Absuchen fremder Repos.

Qt-frei, damit GUI und MCP-Server dieselbe Funktion benutzen. Zwei Suchen mit
verschiedenen Ergebnissen waeren genau der alte Fehler in neuem Gewand.
"""

from pathlib import Path

from spotlab.anbindung.speicher import anbindungen, lauf_verzeichnisse_von


def _laeufe_in(runs):
    try:
        return sorted((p for p in Path(runs).iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        return []


def _runs_wurzeln(workspace):
    """Alle runs/-Ordner: die der Werkstattprojekte und die der Anbindungen."""
    wurzel = Path(workspace)
    wurzeln = []
    try:
        projekte = sorted((p for p in wurzel.iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        projekte = []
    for projekt in projekte:
        runs = projekt / "runs"
        if runs.is_dir():
            wurzeln.append(runs)
    for anbindung in anbindungen(workspace):
        wurzeln.extend(lauf_verzeichnisse_von(anbindung))
    return wurzeln


def lauf_verzeichnisse(workspace):
    """Alle Lauf-Verzeichnisse, ohne Doppelte, in stabiler Reihenfolge."""
    gefunden = {}
    for runs in _runs_wurzeln(workspace):
        for lauf in _laeufe_in(runs):
            gefunden[str(lauf)] = lauf
    return list(gefunden.values())


def finde_lauf(workspace, lauf_id):
    """Das Verzeichnis zu einer Lauf-Kennung — oder None."""
    for lauf in lauf_verzeichnisse(workspace):
        if lauf.name == lauf_id:
            return lauf
    return None
```

In `src/spotlab/gui/watcher.py` die eigene `lauf_verzeichnisse`-Funktion **vollständig
entfernen** und stattdessen importieren:

```python
from spotlab.laufsuche import lauf_verzeichnisse  # noqa: F401  (Re-Export)
from spotlab.record.tail import JsonlTail
from spotlab.workshop.control import ist_aktiv
```

Der Modul-Docstring von `watcher.py` bekommt einen Satz dazu:

```
Wo die Laeufe liegen, entscheidet spotlab.laufsuche — dieselbe Funktion
benutzt der MCP-Server, damit beide dasselbe finden.
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_laufsuche.py tests/test_gui_watcher.py -q
```

Erwartet: beide grün. Die bestehenden Watcher-Tests laufen über den Re-Export weiter.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/laufsuche.py src/spotlab/gui/watcher.py tests/test_laufsuche.py
git commit -m "feat: laufsuche als einziger Ort, an dem Laeufe gefunden werden"
```

---

## Aufgabe 7: `mcp/werkzeuge.py` — Anbinden, Panels, Starten

**Dateien:**
- Anlegen: `src/spotlab/mcp/__init__.py`
- Anlegen: `src/spotlab/mcp/werkzeuge.py`
- Test: `tests/test_mcp_werkzeuge.py`

**Schnittstellen:**
- Verbraucht: alles aus Teil 1, `laufsuche` (Aufgabe 6), `start_script`,
  `stoppe_freundlich`, `load_config`.
- Liefert: `arbeitsordner()`, `projekt_anbinden`, `anbindungen_auflisten`, `panel_setzen`,
  `panel_entfernen`, `skript_starten`, `lauf_stoppen`. Aufgabe 8 ergänzt die Lese-Werkzeuge
  in derselben Datei, Aufgabe 9 meldet alle an.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_mcp_werkzeuge.py`:

```python
import pytest

from spotlab.anbindung.manifest import DATEINAME
from spotlab.mcp import werkzeuge

MANIFEST = """
[projekt]
name = "matura-spot"
beschreibung = "MuJoCo-Simulation"

[[skript]]
name = "Baseline"
datei = "scripts/experiment_baseline.py"
argumente = ["--kurz"]
roboter = false

[[skript]]
name = "Echte Fahrt"
datei = "scripts/sdk_drive.py"
roboter = true
"""


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Arbeitsordner und fremdes Projekt, mit umgebogener Konfiguration."""
    from spotlab.config import Config, Limits

    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = tmp_path / "matura-spot"
    (projekt / "scripts").mkdir(parents=True)
    (projekt / "scripts" / "experiment_baseline.py").write_text(
        "import sys\nprint('args:', ' '.join(sys.argv[1:]))\n", encoding="utf-8"
    )
    (projekt / "scripts" / "sdk_drive.py").write_text("print('faehrt')\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(MANIFEST, encoding="utf-8")

    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(arbeit))
    monkeypatch.setattr(werkzeuge, "load_config", lambda: cfg)
    return arbeit, projekt


def test_arbeitsordner_kommt_aus_der_konfiguration(welt):
    arbeit, _ = welt
    assert werkzeuge.arbeitsordner() == arbeit


def test_ohne_konfiguration_kommt_ein_fehler_statt_absturz(monkeypatch):
    from spotlab.errors import ConfigMissing

    def wirf():
        raise ConfigMissing("keine")

    monkeypatch.setattr(werkzeuge, "load_config", wirf)
    antwort = werkzeuge.anbindungen_auflisten()
    assert "fehler" in antwort[0] if isinstance(antwort, list) else "fehler" in antwort


def test_projekt_anbinden(welt):
    _, projekt = welt
    antwort = werkzeuge.projekt_anbinden(str(projekt))
    assert antwort["name"] == "matura-spot"
    assert [s["name"] for s in antwort["skripte"]] == ["Baseline", "Echte Fahrt"]
    assert antwort["skripte"][1]["roboter"] is True


def test_anbinden_ohne_manifest_meldet_es(welt, tmp_path):
    leer = tmp_path / "leer"
    leer.mkdir()
    antwort = werkzeuge.projekt_anbinden(str(leer))
    assert "fehler" in antwort
    assert DATEINAME in antwort["fehler"]


def test_anbindungen_auflisten(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    liste = werkzeuge.anbindungen_auflisten()
    assert [a["name"] for a in liste] == ["matura-spot"]
    assert liste[0]["vorhanden"] is True
    assert liste[0]["panels"] == []


def test_panel_setzen_und_entfernen(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.panel_setzen(
        "matura-spot", "baseline", "kennzahlen", "Baseline",
        [{"name": "success", "wert": "95 %"}],
    )
    assert antwort["ok"] is True
    assert werkzeuge.anbindungen_auflisten()[0]["panels"] == ["baseline"]
    assert werkzeuge.panel_entfernen("matura-spot", "baseline")["ok"] is True
    assert werkzeuge.panel_entfernen("matura-spot", "baseline")["ok"] is False


def test_panel_mit_ungueltigem_inhalt_wird_benannt(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.panel_setzen("matura-spot", "x", "tabelle", "X", {"spalten": ["a"]})
    assert "fehler" in antwort
    assert "zeilen" in antwort["fehler"]


def test_panel_fuer_unbekanntes_projekt(welt):
    antwort = werkzeuge.panel_setzen("gibtsnicht", "x", "text", "X", {"absaetze": []})
    assert "fehler" in antwort


def test_skript_starten_gibt_eine_lauf_kennung(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.skript_starten("matura-spot", "Baseline")
    assert "fehler" not in antwort, antwort
    assert antwort["gestartet"] is True
    assert antwort["skript"].endswith("experiment_baseline.py")


def test_skript_mit_roboter_wird_verweigert(welt):
    """Erste Lage der Schranke: gar nicht erst starten, mit guter Meldung."""
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.skript_starten("matura-spot", "Echte Fahrt")
    assert "fehler" in antwort
    assert "Fenster" in antwort["fehler"]


def test_unbekanntes_skript(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    antwort = werkzeuge.skript_starten("matura-spot", "gibtsnicht")
    assert "fehler" in antwort
    assert "Baseline" in antwort["fehler"]        # nennt die bekannten


def test_fehlende_skriptdatei(welt):
    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    (projekt / "scripts" / "experiment_baseline.py").unlink()
    antwort = werkzeuge.skript_starten("matura-spot", "Baseline")
    assert "fehler" in antwort


def test_lauf_stoppen_ohne_lauf(welt):
    antwort = werkzeuge.lauf_stoppen("gibtsnicht")
    assert "fehler" in antwort


def test_alle_antworten_sind_json_faehig(welt):
    import json

    _, projekt = welt
    werkzeuge.projekt_anbinden(str(projekt))
    for antwort in (
        werkzeuge.projekt_anbinden(str(projekt)),
        werkzeuge.anbindungen_auflisten(),
        werkzeuge.panel_setzen("matura-spot", "p", "text", "T", {"absaetze": ["a"]}),
    ):
        json.dumps(antwort)          # wirft, wenn etwas nicht serialisierbar ist
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_mcp_werkzeuge.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.mcp'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/mcp/__init__.py`:

```python
"""Der MCP-Server: die Tuer fuer einen Agenten auf dieselben Daten,
die auch ein Mensch und ein Skript sehen — nicht ihr Besitzer.

werkzeuge.py sind gewoehnliche Funktionen; server.py meldet sie nur beim
Protokoll an. Deshalb sind sie ohne Server und ohne Agent pruefbar.
"""
```

`src/spotlab/mcp/werkzeuge.py` (erster Teil — Aufgabe 8 hängt an dieselbe Datei an):

```python
"""Die Werkzeuge als gewoehnliche Funktionen.

Jede nimmt und liefert nur JSON-faehige Werte. Fehler kommen als
{"fehler": "..."} zurueck statt als Ausnahme: ein Absturz mitten im Protokoll
nimmt dem Agenten die Moeglichkeit, den Fehler zu lesen und zu beheben.

Der Server schreibt NIE in das fremde Projekt. Er liest dessen Manifest und
schreibt ausschliesslich unterhalb von anbindungen/.
"""

import functools
from pathlib import Path

from spotlab.anbindung import panel as panelmodul
from spotlab.anbindung import speicher
from spotlab.anbindung.manifest import skript_von
from spotlab.config import load_config
from spotlab.errors import SpotlabError
from spotlab.laufsuche import finde_lauf, lauf_verzeichnisse
from spotlab.workshop.control import ist_aktiv, stoppe_freundlich
from spotlab.workshop.launcher import start_script


def arbeitsordner():
    cfg = load_config()
    if not cfg.workspace:
        raise SpotlabError(
            "Es ist kein Arbeitsordner eingerichtet. Wähle ihn im Fenster unter "
            "„Projekte“ oder richte spotlab mit `spotlab login` ein."
        )
    return Path(cfg.workspace)


def _antwortet(funktion):
    """Wandelt SpotlabError in {"fehler": ...} statt in einen Protokollabbruch."""

    @functools.wraps(funktion)
    def huelle(*args, **kwargs):
        try:
            return funktion(*args, **kwargs)
        except SpotlabError as fehler:
            return {"fehler": str(fehler)}
        except OSError as fehler:
            return {"fehler": f"Dateizugriff fehlgeschlagen: {fehler}"}

    return huelle


def _als_liste(funktion):
    """Wie _antwortet, aber fuer Werkzeuge, die eine Liste liefern."""

    @functools.wraps(funktion)
    def huelle(*args, **kwargs):
        try:
            return funktion(*args, **kwargs)
        except SpotlabError as fehler:
            return [{"fehler": str(fehler)}]
        except OSError as fehler:
            return [{"fehler": f"Dateizugriff fehlgeschlagen: {fehler}"}]

    return huelle


def _skript_json(skript):
    return {
        "name": skript.name,
        "datei": str(skript.datei),
        "argumente": list(skript.argumente),
        "roboter": skript.roboter,
        "beschreibung": skript.beschreibung,
    }


def _anbindung_json(anbindung):
    return {
        "name": anbindung.name,
        "beschreibung": anbindung.manifest.beschreibung,
        "quelle": str(anbindung.quelle),
        "vorhanden": anbindung.vorhanden,
        "angebunden": anbindung.angebunden,
        "skripte": [_skript_json(s) for s in anbindung.manifest.skripte],
        "panels": [p.name for p in panelmodul.panels(anbindung)],
    }


# ----------------------------------------------------------------- Anbinden


@_antwortet
def projekt_anbinden(pfad):
    """Liest die spotlab.toml des Projekts und bindet es an."""
    gebunden = speicher.binde_an(arbeitsordner(), Path(pfad))
    return _anbindung_json(gebunden)


@_als_liste
def anbindungen_auflisten():
    """Alle angebundenen Projekte mit Skripten und Panelnamen."""
    return [_anbindung_json(a) for a in speicher.anbindungen(arbeitsordner())]


@_antwortet
def panel_setzen(projekt, name, art, titel, inhalt):
    """Schreibt oder ersetzt ein Panel. Arten: kennzahlen, tabelle, reihe, bild, text."""
    anbindung = speicher.finde(arbeitsordner(), projekt)
    pfad = panelmodul.schreibe(anbindung, name, art, titel, inhalt)
    return {"ok": True, "pfad": str(pfad)}


@_antwortet
def panel_entfernen(projekt, name):
    anbindung = speicher.finde(arbeitsordner(), projekt)
    return {"ok": panelmodul.entferne(anbindung, name)}


# ----------------------------------------------------------------- Ausführen


@_antwortet
def skript_starten(projekt, name):
    """Startet ein registriertes Skript — erzwungen ohne Roboter."""
    wurzel = arbeitsordner()
    anbindung = speicher.finde(wurzel, projekt)
    skript = skript_von(anbindung.manifest, name)
    if skript is None:
        bekannt = ", ".join(s.name for s in anbindung.manifest.skripte) or "keine"
        raise SpotlabError(
            f"„{name}“ ist in {projekt} nicht registriert. Bekannt sind: {bekannt}."
        )
    if skript.roboter:
        # Erste Lage der Schranke: gar nicht erst starten, mit guter Meldung.
        # Die Durchsetzung haengt nicht daran (siehe ENV_NUR_TROCKEN).
        raise SpotlabError(
            f"„{name}“ fährt den echten Spot. Starte es selbst im Fenster unter "
            "„Anbindungen“ — ein Agent darf den Roboter nicht in Bewegung setzen."
        )

    vorher = {str(p) for p in lauf_verzeichnisse(wurzel)}
    start_script(skript.datei, argumente=skript.argumente, nur_trocken=True)
    return {
        "gestartet": True,
        "skript": str(skript.datei),
        "argumente": list(skript.argumente),
        "hinweis": (
            "Der Lauf läuft im Trockenlauf. Die Kennung erscheint in "
            "`laeufe_auflisten`, sobald die Aufzeichnung angelegt ist."
        ),
        "laeufe_vorher": len(vorher),
    }


@_antwortet
def lauf_stoppen(lauf_id):
    """Freundlicher Stopp über die stopp-Markierung."""
    verzeichnis = finde_lauf(arbeitsordner(), lauf_id)
    if verzeichnis is None:
        raise SpotlabError(f"Es gibt keinen Lauf mit der Kennung „{lauf_id}“.")
    if not ist_aktiv(verzeichnis):
        return {"ok": False, "grund": "Dieser Lauf läuft nicht mehr."}
    stoppe_freundlich(verzeichnis)
    return {"ok": True}
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_mcp_werkzeuge.py -q
```

Erwartet: PASS. `test_skript_starten_gibt_eine_lauf_kennung` startet einen echten
Python-Prozess; das Skript druckt nur und endet sofort.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/mcp/ tests/test_mcp_werkzeuge.py
git commit -m "feat(mcp): Anbinden, Panels und Starten als gewoehnliche Funktionen"
```

---

## Aufgabe 8: `mcp/werkzeuge.py` — die Lese-Werkzeuge

**Dateien:**
- Ändern: `src/spotlab/mcp/werkzeuge.py`
- Test: `tests/test_mcp_lesen.py`

**Schnittstellen:**
- Verbraucht: `read_run`, `read_jsonl` aus `spotlab.record.read`; `karten`, `finde`,
  `lade_graph` aus `spotlab.maps.store`; `diagnose` aus `spotlab.workshop.doctor`.
- Liefert zusätzlich: `laeufe_auflisten`, `lauf_lesen`, `zustand_zusammenfassen`,
  `karten_auflisten`, `karte_lesen`, `spot_pruefen`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_mcp_lesen.py`:

```python
import json

import pytest

from spotlab.mcp import werkzeuge


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    from spotlab.config import Config, Limits

    arbeit = tmp_path / "werkstatt"
    (arbeit / "demo").mkdir(parents=True)
    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=str(arbeit))
    monkeypatch.setattr(werkzeuge, "load_config", lambda: cfg)
    return arbeit


def _lauf(arbeit, ergebnis="ok", abtastungen=None):
    from spotlab.record.run import RunRecorder

    skript = arbeit / "demo" / "hallo.py"
    skript.write_text("print(1)\n", encoding="utf-8")
    recorder = RunRecorder(arbeit / "demo" / "runs", skript, backend="dryrun")
    for satz in abtastungen or []:
        recorder.sample(satz)
    recorder.finish(ergebnis)
    return recorder


def _abtastung(t, x=0.0, v=0.0, akku=90.0):
    return {
        "t": t,
        "pose": [x, 0.0, 0.0],
        "velocity": [v, 0.0, 0.0],
        "battery": akku,
        "feet": [True, True, True, True],
    }


def test_laeufe_auflisten(welt):
    _lauf(welt)
    liste = werkzeuge.laeufe_auflisten()
    assert len(liste) == 1
    assert liste[0]["ergebnis"] == "ok"
    assert liste[0]["id"]


def test_laeufe_auflisten_begrenzt(welt):
    for _ in range(3):
        _lauf(welt)
    assert len(werkzeuge.laeufe_auflisten(anzahl=2)) == 2


def test_lauf_lesen_gibt_pfade_und_keine_inhalte(welt):
    """Der wichtigste Entwurfspunkt: keine Massendaten ins Kontextfenster."""
    recorder = _lauf(welt, abtastungen=[_abtastung(0.0), _abtastung(0.1)])
    antwort = werkzeuge.lauf_lesen(recorder.id)
    assert antwort["ergebnis"] == "ok"
    assert antwort["abtastungen_n"] == 2
    assert antwort["pfade"]["zustand"].endswith("zustand.jsonl")
    assert antwort["pfade"]["ereignisse"].endswith("ereignisse.jsonl")
    text = json.dumps(antwort)
    assert "battery" not in text          # keine Messwerte in der Antwort


def test_lauf_lesen_unbekannt(welt):
    assert "fehler" in werkzeuge.lauf_lesen("gibtsnicht")


def test_zustand_zusammenfassen_rechnet(welt):
    saetze = [_abtastung(i * 0.1, x=i * 0.05, v=0.5, akku=90 - i) for i in range(11)]
    recorder = _lauf(welt, abtastungen=saetze)
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert antwort["abtastungen"] == 11
    assert antwort["dauer_s"] == pytest.approx(1.0, abs=0.01)
    assert antwort["strecke_m"] == pytest.approx(0.5, abs=0.01)
    assert antwort["tempo_max"] == pytest.approx(0.5, abs=0.01)
    assert antwort["akku_von"] == 90.0
    assert antwort["akku_bis"] == 80.0
    assert antwort["luecken"] == []


def test_zustand_zusammenfassen_findet_luecken(welt):
    """Eine unbemerkte Luecke macht den Real->Sim-Vergleich still ungueltig."""
    saetze = [_abtastung(0.0), _abtastung(0.1), _abtastung(1.4), _abtastung(1.5)]
    recorder = _lauf(welt, abtastungen=saetze)
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert len(antwort["luecken"]) == 1
    luecke = antwort["luecken"][0]
    assert luecke["von_s"] == pytest.approx(0.1)
    assert luecke["laenge_s"] == pytest.approx(1.3)


def test_zustand_zusammenfassen_ohne_abtastungen(welt):
    recorder = _lauf(welt)
    antwort = werkzeuge.zustand_zusammenfassen(recorder.id)
    assert antwort["abtastungen"] == 0
    assert antwort["luecken"] == []


def test_karten_auflisten_ohne_karten(welt):
    assert werkzeuge.karten_auflisten() == []


def test_karte_lesen_unbekannt(welt):
    assert "fehler" in werkzeuge.karte_lesen("gibtsnicht")


def test_spot_pruefen_faengt_fehler(welt, monkeypatch):
    from spotlab.workshop.doctor import Check

    monkeypatch.setattr(
        werkzeuge, "diagnose", lambda: [Check("Netz", True, "erreichbar", "")]
    )
    liste = werkzeuge.spot_pruefen()
    assert liste == [{"name": "Netz", "ok": True, "detail": "erreichbar", "rat": ""}]


def test_alle_lese_antworten_sind_json_faehig(welt):
    recorder = _lauf(welt, abtastungen=[_abtastung(0.0)])
    for antwort in (
        werkzeuge.laeufe_auflisten(),
        werkzeuge.lauf_lesen(recorder.id),
        werkzeuge.zustand_zusammenfassen(recorder.id),
        werkzeuge.karten_auflisten(),
    ):
        json.dumps(antwort)
```

**Hinweis zum Test:** `RunRecorder` hat eine Methode zum Aufzeichnen einer Abtastung. Ihren
genauen Namen vor dem Schreiben in `src/spotlab/record/run.py` nachsehen und im Test
verwenden; im Plan steht `recorder.sample(satz)` als Platzhalter für **die vorhandene**
Methode. Ist sie anders benannt, den Test anpassen — **nicht** die Quelle.

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_mcp_lesen.py -q
```

Erwartet: `AttributeError: module 'spotlab.mcp.werkzeuge' has no attribute 'laeufe_auflisten'`.

- [ ] **Schritt 3: Umsetzen**

An `src/spotlab/mcp/werkzeuge.py` anhängen; die Importe oben ergänzen:

```python
from spotlab.maps import store as kartenspeicher
from spotlab.record.read import read_jsonl, read_run
from spotlab.workshop.doctor import diagnose
```

```python
# ----------------------------------------------------------------- Lesen

SOLLTAKT_S = 0.1        # StateSampler laeuft mit 10 Hz
LUECKE_AB_S = 2 * SOLLTAKT_S


def _lauf_json(zusammenfassung):
    return {
        "id": zusammenfassung.id,
        "gestartet": zusammenfassung.gestartet,
        "dauer_s": zusammenfassung.dauer_s,
        "backend": zusammenfassung.backend,
        "ergebnis": zusammenfassung.ergebnis,
        "fehler": zusammenfassung.fehler,
        "skript": zusammenfassung.skript,
        "ereignisse_n": zusammenfassung.ereignisse_n,
        "abtastungen_n": zusammenfassung.abtastungen_n,
    }


@_als_liste
def laeufe_auflisten(projekt=None, anzahl=20):
    """Die neuesten Läufe. Mit `projekt` nur die eines angebundenen Projekts."""
    wurzel = arbeitsordner()
    if projekt:
        anbindung = speicher.finde(wurzel, projekt)
        erlaubt = {str(p) for p in speicher.lauf_verzeichnisse_von(anbindung)}
        verzeichnisse = [
            v for v in lauf_verzeichnisse(wurzel) if str(v.parent) in erlaubt
        ]
    else:
        verzeichnisse = lauf_verzeichnisse(wurzel)
    neueste = sorted(verzeichnisse, key=lambda p: p.name, reverse=True)[: max(1, int(anzahl))]
    return [_lauf_json(read_run(v)) for v in neueste]


@_antwortet
def lauf_lesen(lauf_id):
    """Metadaten und PFADE — bewusst keine Messdaten.

    zustand.jsonl laeuft mit 10 Hz: fuenf Minuten sind 3000 Zeilen. Wer die
    Reihe braucht, liest sie mit den eigenen Dateiwerkzeugen und kann dabei
    filtern.
    """
    verzeichnis = _verzeichnis_von(lauf_id)
    daten = _lauf_json(read_run(verzeichnis))
    daten["pfade"] = {
        "verzeichnis": str(verzeichnis),
        "zustand": str(verzeichnis / "zustand.jsonl"),
        "ereignisse": str(verzeichnis / "ereignisse.jsonl"),
        "bilder": str(verzeichnis / "bilder"),
    }
    daten["laeuft"] = ist_aktiv(verzeichnis)
    return daten


@_antwortet
def zustand_zusammenfassen(lauf_id):
    """Was man sonst nur durch Laden der ganzen Datei erführe.

    Die Abtastluecken sind der eigentliche Zweck: fuer die Real->Sim-Eichung
    macht eine unbemerkte Luecke den Vergleich still ungueltig, und das muss
    vor der ersten Zahl sichtbar sein, nicht nach der letzten.
    """
    verzeichnis = _verzeichnis_von(lauf_id)
    saetze = [s for s in read_jsonl(verzeichnis / "zustand.jsonl") if isinstance(s, dict)]
    if not saetze:
        return {"lauf": lauf_id, "abtastungen": 0, "luecken": []}

    zeiten = [float(s.get("t", 0.0)) for s in saetze]
    strecke, tempo_max, dreh_max = 0.0, 0.0, 0.0
    vorige = None
    for satz in saetze:
        pose = satz.get("pose") or [0.0, 0.0, 0.0]
        if vorige is not None:
            strecke += ((pose[0] - vorige[0]) ** 2 + (pose[1] - vorige[1]) ** 2) ** 0.5
        vorige = pose
        tempo = satz.get("velocity") or [0.0, 0.0, 0.0]
        tempo_max = max(tempo_max, (tempo[0] ** 2 + tempo[1] ** 2) ** 0.5)
        dreh_max = max(dreh_max, abs(tempo[2]) if len(tempo) > 2 else 0.0)

    luecken = [
        {"von_s": round(zeiten[i - 1], 3), "laenge_s": round(zeiten[i] - zeiten[i - 1], 3)}
        for i in range(1, len(zeiten))
        if zeiten[i] - zeiten[i - 1] > LUECKE_AB_S
    ]
    dauer = zeiten[-1] - zeiten[0]
    akkus = [s.get("battery") for s in saetze if s.get("battery") is not None]
    return {
        "lauf": lauf_id,
        "abtastungen": len(saetze),
        "dauer_s": round(dauer, 3),
        "takt_ist_hz": round(len(saetze) / dauer, 2) if dauer > 0 else 0.0,
        "takt_soll_hz": round(1 / SOLLTAKT_S, 2),
        "strecke_m": round(strecke, 3),
        "tempo_max": round(tempo_max, 3),
        "drehrate_max": round(dreh_max, 3),
        "akku_von": akkus[0] if akkus else None,
        "akku_bis": akkus[-1] if akkus else None,
        "luecken": luecken,
    }


@_als_liste
def karten_auflisten():
    return [
        {
            "name": k.name,
            "aufgezeichnet": k.aufgezeichnet,
            "roboter": k.roboter,
            "wegpunkte": k.wegpunkte,
            "kanten": k.kanten,
            "ordner": str(k.dir),
        }
        for k in kartenspeicher.karten(arbeitsordner())
    ]


@_antwortet
def karte_lesen(name):
    """Wegpunkte und Grundriss einer Karte."""
    from spotlab.maps.geometry import grundriss

    kartenordner = kartenspeicher.finde(arbeitsordner(), name)
    graph = kartenspeicher.lade_graph(kartenordner.dir)
    riss = grundriss(graph)
    return {
        "name": kartenordner.name,
        "wegpunkte": [
            {"id": p.id, "name": p.name, "x": round(p.x, 3), "y": round(p.y, 3)}
            for p in riss.punkte
        ],
        "kanten": [[a, b] for a, b in riss.kanten],
    }


@_als_liste
def spot_pruefen():
    """Dieselbe Prüfung wie `spotlab doctor` — braucht Netz und Anmeldung."""
    return [
        {"name": c.name, "ok": c.ok, "detail": c.detail, "rat": c.rat} for c in diagnose()
    ]


def _verzeichnis_von(lauf_id):
    verzeichnis = finde_lauf(arbeitsordner(), lauf_id)
    if verzeichnis is None:
        raise SpotlabError(
            f"Es gibt keinen Lauf mit der Kennung „{lauf_id}“. "
            "`laeufe_auflisten` nennt die vorhandenen."
        )
    return verzeichnis
```

**Vor dem Schreiben prüfen:** die Feldnamen von `maps.geometry.Punkt` und `Grundriss` in
`src/spotlab/maps/geometry.py` nachsehen und `karte_lesen` daran anpassen — die oben
verwendeten `p.id`, `p.name`, `p.x`, `p.y`, `riss.punkte`, `riss.kanten` sind die erwartete
Form; weicht sie ab, gilt die Quelle.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_mcp_lesen.py -q
python -m pytest -q
```

Erwartet: beide grün.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/mcp/werkzeuge.py tests/test_mcp_lesen.py
git commit -m "feat(mcp): Lese-Werkzeuge — Struktur und Pfade statt Massendaten"
```

---

## Aufgabe 9: `mcp/server.py` und `spotlab mcp`

**Dateien:**
- Anlegen: `src/spotlab/mcp/server.py`
- Ändern: `src/spotlab/cli.py` (Unterbefehl `mcp`)
- Ändern: `pyproject.toml` (Extra `[mcp]`)
- Test: `tests/test_mcp_server.py`

**Schnittstellen:**
- Verbraucht: alle Werkzeuge aus Aufgaben 7 und 8.
- Liefert: `WERKZEUGE: tuple[tuple[callable, str], ...]`, `baue_server()`, `main()`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_mcp_server.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spotlab.mcp.server import WERKZEUGE

QUELLE = str(Path(__file__).resolve().parents[1] / "src")


def test_alle_zwoelf_werkzeuge_sind_angemeldet():
    namen = {f.__name__ for f, _ in WERKZEUGE}
    assert namen == {
        "projekt_anbinden",
        "anbindungen_auflisten",
        "panel_setzen",
        "panel_entfernen",
        "skript_starten",
        "lauf_stoppen",
        "laeufe_auflisten",
        "lauf_lesen",
        "zustand_zusammenfassen",
        "karten_auflisten",
        "karte_lesen",
        "spot_pruefen",
    }


def test_jedes_werkzeug_hat_eine_deutsche_beschreibung():
    for funktion, beschreibung in WERKZEUGE:
        assert beschreibung.strip(), funktion.__name__
        assert len(beschreibung) > 20, funktion.__name__


def test_ohne_mcp_paket_meldet_die_cli_den_installationsbefehl(monkeypatch, capsys):
    import spotlab.cli as cli

    monkeypatch.setattr(cli, "_mcp_vorhanden", lambda: False)
    code = cli.main(["mcp"])
    ausgabe = capsys.readouterr()
    assert code == 1
    assert "pip install" in (ausgabe.out + ausgabe.err)


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("mcp") is None,
    reason="Extra [mcp] nicht installiert",
)
def test_server_startet_wirklich_und_antwortet(tmp_path):
    """Ein echter Unterprozess mit echtem Handshake.

    Attrappen pruefen nur, dass die richtigen Argumente gebaut werden — nicht,
    dass das Betriebssystem und das Protokoll damit etwas anfangen koennen.
    """
    prozess = subprocess.Popen(
        [sys.executable, "-m", "spotlab.cli", "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env={**os.environ, "PYTHONPATH": QUELLE, "PYTHONUTF8": "1"},
    )
    try:
        anfrage = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        prozess.stdin.write(json.dumps(anfrage) + "\n")
        prozess.stdin.flush()
        zeile = prozess.stdout.readline()
        antwort = json.loads(zeile)
        assert antwort["id"] == 1
        assert "serverInfo" in antwort["result"]
    finally:
        prozess.kill()
        prozess.wait(timeout=10)
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_mcp_server.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.mcp.server'`.

- [ ] **Schritt 3: Das Extra installieren und umsetzen**

```bash
python -m pip install "mcp>=1.2"
```

In `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
gui = ["PySide6>=6.6", "pygments>=2.17", "jedi>=0.19"]
mcp = ["mcp>=1.2"]
```

`src/spotlab/mcp/server.py`:

```python
"""Der stdio-Server.

Er meldet die Funktionen aus werkzeuge.py beim Protokoll an und tut sonst
nichts. Alle Fachlogik liegt dort — deshalb ist sie ohne Server pruefbar.

Braucht weder GUI noch Roboter, nur den Arbeitsordner.
"""

from spotlab.mcp import werkzeuge

# Reihenfolge wie in der Spec: anbinden, ausfuehren, lesen.
WERKZEUGE = (
    (werkzeuge.projekt_anbinden,
     "Bindet ein fremdes Projekt an spotlab an. Erwartet den Pfad zum Ordner, "
     "in dem die spotlab.toml liegt."),
    (werkzeuge.anbindungen_auflisten,
     "Nennt alle angebundenen Projekte mit ihren Skripten und Panelnamen."),
    (werkzeuge.panel_setzen,
     "Schreibt oder ersetzt ein Panel in der Ansicht „Anbindungen“. Arten: "
     "kennzahlen, tabelle, reihe, bild, text."),
    (werkzeuge.panel_entfernen,
     "Entfernt ein Panel eines angebundenen Projekts."),
    (werkzeuge.skript_starten,
     "Startet ein im Manifest registriertes Skript. Der Lauf ist IMMER ein "
     "Trockenlauf ohne Roboter; Skripte mit roboter=true werden abgelehnt."),
    (werkzeuge.lauf_stoppen,
     "Beendet einen laufenden Lauf freundlich (Spot setzt sich hin)."),
    (werkzeuge.laeufe_auflisten,
     "Nennt die neuesten Läufe, wahlweise nur die eines angebundenen Projekts."),
    (werkzeuge.lauf_lesen,
     "Metadaten, Ergebnis und Dateipfade eines Laufs. Gibt bewusst keine "
     "Messdaten zurück — die Reihen liest man mit eigenen Dateiwerkzeugen."),
    (werkzeuge.zustand_zusammenfassen,
     "Dauer, Strecke, Spitzentempo, Akku und vor allem die Abtastlücken einer "
     "Zustandsreihe. Grundlage für den Vergleich echter Läufe mit Simulationen."),
    (werkzeuge.karten_auflisten,
     "Nennt die aufgezeichneten GraphNav-Karten."),
    (werkzeuge.karte_lesen,
     "Wegpunkte und Kanten einer Karte als Grundriss."),
    (werkzeuge.spot_pruefen,
     "Prüft Netz, Anmeldung, Zeitsync, Not-Aus, Lease und Akku — wie `spotlab doctor`."),
)


def baue_server():
    """Legt den FastMCP-Server an und meldet die Werkzeuge an."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("spotlab")
    for funktion, beschreibung in WERKZEUGE:
        server.add_tool(funktion, name=funktion.__name__, description=beschreibung)
    return server


def main():
    baue_server().run()
    return 0
```

**Vor dem Schreiben prüfen:** Ob `FastMCP.add_tool` in der installierten Version diese
Signatur hat (`python -c "from mcp.server.fastmcp import FastMCP; help(FastMCP.add_tool)"`).
Weicht sie ab, `baue_server` daran anpassen — `WERKZEUGE` und die Werkzeugfunktionen bleiben
unverändert, das ist der Sinn der Trennung.

In `src/spotlab/cli.py`:

```python
    unter.add_parser("mcp", help="MCP-Server über stdin/stdout starten (für Agenten)")
```

und in `_fuehre_aus`:

```python
    if args.kommando == "mcp":
        return _mcp()
```

sowie:

```python
def _mcp_vorhanden():
    import importlib.util

    return importlib.util.find_spec("mcp") is not None


def _mcp():
    if not _mcp_vorhanden():
        print(
            "Der MCP-Server braucht das Extra `mcp`.\n"
            '  pip install "spotlab[mcp]"',
            file=sys.stderr,
        )
        return 1
    from spotlab.mcp.server import main as server_main

    return server_main()
```

**`_utf8_ausgabe()` darf beim MCP-Server nichts umkonfigurieren, was das Protokoll stört.**
Es setzt die Kodierung auf UTF-8 — das ist für JSON-RPC richtig und bleibt.

Damit `python -m spotlab.cli` funktioniert, braucht `cli.py` am Ende:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_mcp_server.py -q
python -m pytest -q
```

Erwartet: beide grün. Der Handshake-Test läuft jetzt wirklich, weil `mcp` installiert ist.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/mcp/server.py src/spotlab/cli.py pyproject.toml tests/test_mcp_server.py
git commit -m "feat(mcp): stdio-Server und `spotlab mcp`"
```

---

## Aufgabe 10: Ansicht „Anbindungen"

**Dateien:**
- Anlegen: `src/spotlab/gui/views/anbindungen.py`
- Test: `tests/test_gui_anbindungen.py`

**Schnittstellen:**
- Verbraucht: `speicher`, `panel` (Teil 1); `start_script`; `theme`.
- Liefert: `AnbindungenView(palette, parent=None)` mit `setze_arbeitsordner(pfad)`,
  `aktualisiere()`, Signalen `meldung(str)`, `lauf_gestartet(object, str)`,
  Attributen `.liste`, `.panelbereich`, `.skriptknoepfe`; ausserdem `panel_widget(panel, ...)`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_gui_anbindungen.py`:

```python
import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.anbindung.manifest import DATEINAME                  # noqa: E402
from spotlab.anbindung.panel import schreibe                      # noqa: E402
from spotlab.anbindung.speicher import binde_an                   # noqa: E402
from spotlab.gui.theme import DUNKEL                              # noqa: E402
from spotlab.gui.views.anbindungen import AnbindungenView         # noqa: E402

MANIFEST = """
[projekt]
name = "matura-spot"

[[skript]]
name = "Baseline"
datei = "scripts/lauf.py"
roboter = false
"""


def _welt(tmp_path):
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    projekt = tmp_path / "matura-spot"
    (projekt / "scripts").mkdir(parents=True)
    (projekt / "scripts" / "lauf.py").write_text("print(1)\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(MANIFEST, encoding="utf-8")
    return arbeit, projekt, binde_an(arbeit, projekt)


def test_liste_zeigt_angebundene_projekte(qapp, tmp_path):
    arbeit, _, _ = _welt(tmp_path)
    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    assert ansicht.liste.count() == 1
    assert ansicht.liste.item(0).text() == "matura-spot"


def test_alle_fuenf_arten_zeichnen(qapp, tmp_path):
    arbeit, _, gebunden = _welt(tmp_path)
    bild = gebunden.ordner / "b.png"
    bild.write_bytes(b"\x89PNG\r\n\x1a\n")
    schreibe(gebunden, "a", "kennzahlen", "K", [{"name": "x", "wert": "1"}])
    schreibe(gebunden, "b", "tabelle", "T", {"spalten": ["a"], "zeilen": [["1"]]})
    schreibe(gebunden, "c", "reihe", "R", {"x": [0, 1], "y": [1, 2]})
    schreibe(gebunden, "d", "bild", "B", {"pfad": str(bild)})
    schreibe(gebunden, "e", "text", "X", {"absaetze": ["hallo"]})

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    ansicht.liste.setCurrentRow(0)
    assert ansicht.panelbereich.count() == 5


def test_ein_kaputtes_panel_laesst_die_anderen_stehen(qapp, tmp_path):
    """Die Ansicht darf an einer halb geschriebenen Datei nicht leer werden."""
    arbeit, _, gebunden = _welt(tmp_path)
    schreibe(gebunden, "gut", "kennzahlen", "Gut", [{"name": "x", "wert": "1"}])
    (gebunden.ordner / "panels" / "kaputt.json").write_text("{", encoding="utf-8")

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    ansicht.liste.setCurrentRow(0)
    assert ansicht.panelbereich.count() == 2          # gut + Fehlerkarte


def test_bild_von_ausserhalb_wird_nicht_geladen(qapp, tmp_path):
    arbeit, _, gebunden = _welt(tmp_path)
    fremd = tmp_path / "fremd.png"
    fremd.write_bytes(b"\x89PNG\r\n\x1a\n")
    schreibe(gebunden, "b", "bild", "B", {"pfad": str(fremd)})

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    ansicht.liste.setCurrentRow(0)
    texte = ansicht.paneltexte()
    assert any("ausserhalb" in t.lower() or "außerhalb" in t.lower() for t in texte)


def test_skriptknopf_startet_wirklich(qapp, tmp_path):
    arbeit, _, _ = _welt(tmp_path)
    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    ansicht.liste.setCurrentRow(0)
    gestartet = []
    ansicht.lauf_gestartet.connect(lambda p, s: gestartet.append((p, s)))
    assert len(ansicht.skriptknoepfe) == 1
    ansicht.skriptknoepfe[0].click()
    assert gestartet
    prozess, _skript = gestartet[0]
    prozess.wait()


def test_fehlende_quelle_schaltet_die_knoepfe_ab(qapp, tmp_path):
    import shutil

    arbeit, projekt, gebunden = _welt(tmp_path)
    schreibe(gebunden, "a", "kennzahlen", "K", [{"name": "x", "wert": "1"}])
    shutil.rmtree(projekt)

    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(arbeit)
    ansicht.liste.setCurrentRow(0)
    assert all(not k.isEnabled() for k in ansicht.skriptknoepfe)
    assert ansicht.panelbereich.count() == 1          # Panels bleiben sichtbar
    assert str(projekt) in ansicht.hinweis.text()


def test_ohne_anbindungen_bleibt_die_ansicht_leer(qapp, tmp_path):
    ansicht = AnbindungenView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.liste.count() == 0
    assert ansicht.panelbereich.count() == 0
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_anbindungen.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.gui.views.anbindungen'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/gui/views/anbindungen.py`:

```python
"""Was ein fremdes Projekt zu sagen hat.

„Code" zeigt, was das Programm sagt; „Live-Lauf", was der Roboter tut;
„Anbindungen", was ein fremdes Projekt zu sagen hat.

Panels sind Daten, kein Code: der GUI-Prozess ist der Prozess mit dem NOT-AUS,
und fremder Qt-Code im selben Event-Loop braeche genau den Failsafe, um den
Stufe 1 herumgebaut ist.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spotlab.anbindung import panel as panelmodul
from spotlab.anbindung import speicher
from spotlab.errors import SpotlabError
from spotlab.workshop.launcher import start_script


class Kurve(QWidget):
    """Eine Zahlenreihe als Linie. Wie gui/mapplot.py: QPainter statt Bibliothek."""

    def __init__(self, x, y, palette, parent=None):
        super().__init__(parent)
        self._x = list(x)
        self._y = list(y)
        self._palette = palette
        self.setMinimumHeight(120)

    def paintEvent(self, ereignis):
        maler = QPainter(self)
        maler.setRenderHint(QPainter.Antialiasing)
        if len(self._x) < 2:
            return
        rand = 8
        breite = max(1, self.width() - 2 * rand)
        hoehe = max(1, self.height() - 2 * rand)
        x_min, x_max = min(self._x), max(self._x)
        y_min, y_max = min(self._y), max(self._y)
        x_spanne = (x_max - x_min) or 1.0
        y_spanne = (y_max - y_min) or 1.0
        maler.setPen(QPen(self._palette.akzent, 2))
        punkte = [
            (
                rand + (wert_x - x_min) / x_spanne * breite,
                rand + hoehe - (wert_y - y_min) / y_spanne * hoehe,
            )
            for wert_x, wert_y in zip(self._x, self._y)
        ]
        for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
            maler.drawLine(int(x1), int(y1), int(x2), int(y2))


def _karte(titel, palette):
    rahmen = QFrame()
    rahmen.setObjectName("Flaeche")
    anordnung = QVBoxLayout(rahmen)
    kopf = QLabel(titel)
    kopf.setObjectName("Titel")
    anordnung.addWidget(kopf)
    return rahmen, anordnung


def panel_widget(panel, anbindung, palette):
    """Ein Panel als Widget. Gibt (Widget, Text) zurück; Text nur für Tests."""
    rahmen, anordnung = _karte(panel.titel or panel.name, palette)

    if panel.fehler:
        hinweis = QLabel(f"Dieses Panel ist unbrauchbar: {panel.fehler}")
        hinweis.setObjectName("Warnung")
        hinweis.setWordWrap(True)
        anordnung.addWidget(hinweis)
        return rahmen, hinweis.text()

    if panel.art == "kennzahlen":
        gitter = QGridLayout()
        for spalte, eintrag in enumerate(panel.inhalt):
            wert = QLabel(str(eintrag.get("wert", "")))
            wert.setObjectName("Kachelwert")
            name = QLabel(str(eintrag.get("name", "")))
            name.setObjectName("Kachelname")
            gitter.addWidget(wert, 0, spalte)
            gitter.addWidget(name, 1, spalte)
            hinweis = str(eintrag.get("hinweis", ""))
            if hinweis:
                zusatz = QLabel(hinweis)
                zusatz.setObjectName("Gedaempft")
                gitter.addWidget(zusatz, 2, spalte)
        anordnung.addLayout(gitter)
        return rahmen, ""

    if panel.art == "tabelle":
        spalten = panel.inhalt["spalten"]
        zeilen = panel.inhalt["zeilen"]
        tabelle = QTableWidget(len(zeilen), len(spalten))
        tabelle.setHorizontalHeaderLabels([str(s) for s in spalten])
        tabelle.verticalHeader().setVisible(False)
        for z, zeile in enumerate(zeilen):
            for s, wert in enumerate(zeile):
                tabelle.setItem(z, s, QTableWidgetItem(str(wert)))
        anordnung.addWidget(tabelle)
        return rahmen, ""

    if panel.art == "reihe":
        beschriftung = QLabel(
            f"{panel.inhalt.get('y_name', 'Wert')} über {panel.inhalt.get('x_name', 'x')}"
        )
        beschriftung.setObjectName("Gedaempft")
        anordnung.addWidget(beschriftung)
        anordnung.addWidget(Kurve(panel.inhalt["x"], panel.inhalt["y"], palette))
        return rahmen, ""

    if panel.art == "bild":
        pfad = Path(panel.inhalt["pfad"])
        if not panelmodul.bild_erlaubt(pfad, anbindung):
            text = (
                "Dieses Bild liegt ausserhalb des Projekts und wird nicht geladen. "
                "Lege es unter das Projektverzeichnis."
            )
            hinweis = QLabel(text)
            hinweis.setObjectName("Warnung")
            hinweis.setWordWrap(True)
            anordnung.addWidget(hinweis)
            return rahmen, text
        bild = QLabel()
        pixmap = QPixmap(str(pfad))
        if pixmap.isNull():
            text = f"{pfad.name} liess sich nicht als Bild lesen."
            bild.setText(text)
            bild.setObjectName("Warnung")
        else:
            bild.setPixmap(pixmap.scaledToWidth(520, Qt.SmoothTransformation))
            text = ""
        anordnung.addWidget(bild)
        return rahmen, text

    absaetze = QLabel("\n\n".join(str(a) for a in panel.inhalt["absaetze"]))
    absaetze.setWordWrap(True)
    anordnung.addWidget(absaetze)
    return rahmen, ""


class AnbindungenView(QWidget):
    meldung = Signal(str)
    lauf_gestartet = Signal(object, str)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self._palette = palette
        self._ordner = None
        self._anbindungen = []
        self.skriptknoepfe = []
        self._texte = []

        self.liste = QListWidget()
        self.liste.currentRowChanged.connect(lambda _: self._zeige())
        self.anbinden_knopf = QPushButton("Projekt anbinden…")
        self.anbinden_knopf.clicked.connect(self._anbinden)

        links = QWidget()
        links_anordnung = QVBoxLayout(links)
        links_anordnung.setContentsMargins(0, 0, 0, 0)
        links_anordnung.addWidget(QLabel("Angebundene Projekte"))
        links_anordnung.addWidget(self.liste, 1)
        links_anordnung.addWidget(self.anbinden_knopf)
        links.setFixedWidth(230)

        self.hinweis = QLabel("")
        self.hinweis.setObjectName("Gedaempft")
        self.hinweis.setWordWrap(True)

        self.knopfzeile = QHBoxLayout()
        knopfhuelle = QWidget()
        knopfhuelle.setLayout(self.knopfzeile)

        self._panelhuelle = QWidget()
        self.panelbereich = QVBoxLayout(self._panelhuelle)
        self.panelbereich.setAlignment(Qt.AlignTop)
        rollbereich = QScrollArea()
        rollbereich.setWidgetResizable(True)
        rollbereich.setWidget(self._panelhuelle)

        rechts = QVBoxLayout()
        rechts.addWidget(knopfhuelle)
        rechts.addWidget(self.hinweis)
        rechts.addWidget(rollbereich, 1)

        aussen = QHBoxLayout(self)
        aussen.addWidget(links)
        aussen.addLayout(rechts, 1)

    # ------------------------------------------------------------- Zustand

    def setze_arbeitsordner(self, pfad):
        self._ordner = Path(pfad) if pfad else None
        self.aktualisiere()

    def aktualisiere(self):
        merker = self.liste.currentRow()
        self.liste.clear()
        self._anbindungen = (
            speicher.anbindungen(self._ordner) if self._ordner is not None else []
        )
        for anbindung in self._anbindungen:
            self.liste.addItem(anbindung.name)
        if self._anbindungen:
            self.liste.setCurrentRow(min(max(merker, 0), len(self._anbindungen) - 1))
        else:
            self._zeige()

    def gewaehlt(self):
        zeile = self.liste.currentRow()
        if 0 <= zeile < len(self._anbindungen):
            return self._anbindungen[zeile]
        return None

    def paneltexte(self):
        """Nur für Tests: die Hinweistexte der gezeichneten Panels."""
        return list(self._texte)

    # ------------------------------------------------------------- Anzeige

    def _leere(self, anordnung):
        while anordnung.count():
            eintrag = anordnung.takeAt(0)
            widget = eintrag.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _zeige(self):
        self._leere(self.panelbereich)
        self._leere(self.knopfzeile)
        self.skriptknoepfe = []
        self._texte = []
        anbindung = self.gewaehlt()
        if anbindung is None:
            self.hinweis.setText("")
            return

        if anbindung.vorhanden:
            self.hinweis.setText(str(anbindung.quelle))
        else:
            self.hinweis.setText(
                f"Der Projektordner {anbindung.quelle} ist nicht mehr da. "
                "Die Panels bleiben sichtbar, die Skripte lassen sich nicht starten."
            )

        for skript in anbindung.manifest.skripte:
            beschriftung = f"▶ {skript.name}"
            if skript.roboter:
                beschriftung += "  (mit Roboter)"
            knopf = QPushButton(beschriftung)
            knopf.setToolTip(skript.beschreibung or str(skript.datei))
            knopf.setEnabled(anbindung.vorhanden)
            knopf.clicked.connect(lambda _=False, s=skript: self._starte(s))
            self.knopfzeile.addWidget(knopf)
            self.skriptknoepfe.append(knopf)
        self.knopfzeile.addStretch(1)

        for panel in panelmodul.panels(anbindung):
            widget, text = panel_widget(panel, anbindung, self._palette)
            self.panelbereich.addWidget(widget)
            self._texte.append(text)

    # ------------------------------------------------------------- Aktionen

    def _anbinden(self):
        if self._ordner is None:
            self.meldung.emit("Wähle zuerst einen Arbeitsordner in „Projekte“.")
            return
        gewaehlt = QFileDialog.getExistingDirectory(self, "Projekt mit spotlab.toml wählen")
        if not gewaehlt:
            return
        try:
            speicher.binde_an(self._ordner, Path(gewaehlt))
        except SpotlabError as fehler:
            QMessageBox.warning(self, "spotlab", str(fehler))
            return
        self.aktualisiere()

    def _starte(self, skript):
        """Hier sitzt ein Mensch vor dem NOT-AUS — keine Trockenlauf-Schranke.

        Die Schranke gilt fuer den Agenten, nicht fuer den Menschen.
        """
        try:
            prozess = start_script(skript.datei, argumente=skript.argumente)
        except SpotlabError as fehler:
            self.meldung.emit(str(fehler))
            return
        self.lauf_gestartet.emit(prozess, str(skript.datei))
```

**Farben:** `Kurve` benutzt `palette.akzent`; alles andere hängt an `objectName` und damit am
Stylesheet. Kein Farbliteral.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_anbindungen.py -q
```

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/views/anbindungen.py tests/test_gui_anbindungen.py
git commit -m "feat(gui): Ansicht Anbindungen mit fuenf Panel-Arten"
```

---

## Aufgabe 11: Verdrahtung im Hauptfenster

**Dateien:**
- Ändern: `src/spotlab/gui/sidebar.py`
- Ändern: `src/spotlab/gui/app.py`
- Test: `tests/test_gui_app.py` (ergänzen)

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `tests/test_gui_app.py` anhängen:

```python
def test_seitenleiste_hat_die_ansicht_anbindungen(qapp):
    from spotlab.gui.sidebar import EINTRAEGE

    assert ("anbindungen", "Anbindungen") in EINTRAEGE
    schluessel = [s for s, _ in EINTRAEGE]
    assert schluessel.index("anbindungen") < schluessel.index("spot")


def test_fenster_hat_jetzt_sieben_ansichten(qapp):
    fenster = MainWindow()
    assert set(fenster.ansichten) == {
        "projekte", "code", "anbindungen", "live", "laeufe", "karten", "spot"
    }
    assert fenster.stapel.count() == 7


def test_lauf_aus_anbindungen_schaltet_nicht_um(qapp, tmp_path):
    """Wer in „Anbindungen" auf ein Skript drückt, will die Panels sehen, nicht Telemetrie.

    Ein elfminütiger Experimentlauf schreibt seinen Fortschritt in ein Panel —
    genau in die Ansicht, aus der er gestartet wurde.
    """
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._wechsle("anbindungen")
    fenster._lauf_aus_anbindungen(_FakeProzess(), "egal.py")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["anbindungen"]


def test_lauf_aus_anbindungen_speist_die_ausgaben(qapp, tmp_path):
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._lauf_aus_anbindungen(_FakeProzess(), "egal.py")
    fenster._leser.zeile.emit("Fortschritt 3/20")
    assert "Fortschritt 3/20" in fenster.ansichten["live"].ausgabe.toPlainText()
    assert "Fortschritt 3/20" in fenster.ansichten["code"].ausgabe.toPlainText()


def test_arbeitsordner_erreicht_die_anbindungen(qapp, tmp_path):
    from spotlab.anbindung.manifest import DATEINAME
    from spotlab.anbindung.speicher import binde_an

    projekt = tmp_path / "fremd"
    projekt.mkdir()
    (projekt / "s.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(
        '[projekt]\nname = "fremd"\n\n[[skript]]\nname = "s"\ndatei = "s.py"\n',
        encoding="utf-8",
    )
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    binde_an(arbeit, projekt)

    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(arbeit))
    assert fenster.ansichten["anbindungen"].liste.count() == 1
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_app.py -q
```

Erwartet: FAIL bei `test_seitenleiste_hat_die_ansicht_anbindungen`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/gui/sidebar.py`:

```python
EINTRAEGE = (
    ("projekte", "Projekte"),
    ("code", "Code"),
    ("live", "Live-Lauf"),
    ("laeufe", "Läufe"),
    ("karten", "Karten"),
    ("anbindungen", "Anbindungen"),
    ("spot", "Spot"),
)
```

`src/spotlab/gui/app.py` — Import:

```python
from spotlab.gui.views.anbindungen import AnbindungenView
```

Ansicht anlegen und in den Stapel legen:

```python
            "karten": MapsView(),
            "anbindungen": AnbindungenView(self._palette),
            "spot": CheckupView(),
        }
        self.stapel = QStackedWidget()
        for schluessel in (
            "projekte", "code", "live", "laeufe", "karten", "anbindungen", "spot"
        ):
            self.stapel.addWidget(self.ansichten[schluessel])
```

In `_verdrahte`:

```python
        self.ansichten["anbindungen"].meldung.connect(self._melde)
        self.ansichten["anbindungen"].lauf_gestartet.connect(self._lauf_aus_anbindungen)
```

Dazu die Methode, **neben** `_lauf_aus_code` und aus demselben Grund:

```python
    def _lauf_aus_anbindungen(self, prozess, skript):
        # Kein Ansichtswechsel: wer dort startet, will die Panels sehen, nicht
        # Telemetrie. Ein elfminuetiger Experimentlauf schreibt seinen
        # Fortschritt genau in die Ansicht, aus der er gestartet wurde.
        self._start_aus = "anbindungen"
        self._starte_leser(prozess)
```

und in `_lauf_begonnen` die Bedingung erweitern:

```python
        if self._start_aus in ("code", "anbindungen"):
            return
```

In `_setze_arbeitsordner`:

```python
        self.ansichten["anbindungen"].setze_arbeitsordner(pfad or None)
```

In `_lauf_beendet` zusätzlich, damit die Panels eines gerade beendeten Laufs frisch sind:

```python
        self.ansichten["anbindungen"].aktualisiere()
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest -q
```

Erwartet: alles grün.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/sidebar.py src/spotlab/gui/app.py tests/test_gui_app.py
git commit -m "feat(gui): Ansicht Anbindungen verdrahtet"
```

---

## Aufgabe 12: Dokumentation

**Dateien:**
- Ändern: `CLAUDE.md`
- Anlegen: `docs/ANBINDUNG.md` (Anleitung für fremde Projekte)

- [ ] **Schritt 1: `CLAUDE.md` ergänzen**

Unter „Nicht verhandelbar":

```markdown
- **Fremde Projekte liefern Daten, keinen Code.** Panels sind deklarative JSON-Dateien, die
  spotlab mit den eigenen Widgets zeichnet. Ein Qt-Plugin-System liefe im Prozess mit dem
  NOT-AUS-Knopf; eine Schleife oder ein Absturz darin nähme dem Fenster den Failsafe, um den
  Stufe 1 herumgebaut ist.
- **`SPOTLAB_NUR_TROCKEN=1` ist eine Obergrenze, keine Vorgabe.** `connect()` weist ein
  explizites `backend="real"` damit ab, statt es stillschweigend herunterzustufen.
  `SPOTLAB_BACKEND` genügt dafür nicht: `art = backend or os.environ.get(...)` — ein
  Skriptargument überschreibt die Variable. Ein veraltetes Manifest darf den Roboter nicht
  bewegen können.
- **`anbindung/` importiert nichts aus `api/`, `backends/`, `maps/`, `gui/`** und hält weder
  Lease-Client noch E-Stop-Endpunkt — dieselbe Regel wie `maps/`. `spotlab.errors` ist
  erlaubt.
- **Wo Läufe liegen, entscheidet `laufsuche.py` — an genau einer Stelle.** Läufe fremder
  Projekte liegen unter `<skriptordner>/runs/`, also ausserhalb des Arbeitsordners. Zwei
  Suchen mit verschiedenen Ergebnissen sind der Fehler aus Stufe 3 in neuem Gewand.
```

Unter „Regeln":

```markdown
- Panels bestimmen keine Farben. Ein Panel, das eine Farbe mitbringt, ist in einem der beiden
  Modi unlesbar.
- Bildpfade eines Panels dürfen nur ins Projekt oder in den Anbindungsordner zeigen —
  dieselbe Regel wie bei den anklickbaren Tracebacks.
- `anbindung/panel.py::lies` wirft nie. Ein Panel, das im Sekundentakt überschrieben wird,
  ist regelmässig halb geschrieben; eine Ansicht, die daran leer wird, flackert im Betrieb.
```

„Umsetzungsstand" ersetzen:

```markdown
Fundament (1+2), GUI (3), GraphNav (4), Editor (5) und die Anbindung fremder Projekte samt
MCP-Server (6) sind vollständig. Offen und bewusst nicht gebaut: Sim-Adapter,
NN-Anbindung, Mehrbenutzer-Dienst, Arm und Docking.
Spec: `docs/superpowers/specs/2026-08-07-spotlab-anbindung-design.md`.
```

- [ ] **Schritt 2: `docs/ANBINDUNG.md` schreiben**

Kurze Anleitung für ein fremdes Projekt, mit genau diesen Teilen:

1. `spotlab.toml` anlegen — vollständiges Beispiel wie in Aufgabe 2.
2. Anbinden: `spotlab gui` → „Anbindungen" → „Projekt anbinden…", oder über den Agenten
   `projekt_anbinden`.
3. Ein Panel aus dem eigenen Code schreiben — mit lauffähigem Beispiel:

```python
from spotlab.anbindung import panel, speicher

anbindung = speicher.finde("D:/…/werkstatt", "matura-spot")
panel.schreibe(
    anbindung, "baseline", "kennzahlen", "Baseline, 20 Episoden",
    [{"name": "success", "wert": "95 %", "hinweis": "19 von 20"}],
)
```

4. Die fünf Arten mit je einem Beispiel.
5. Der MCP-Server: `pip install "spotlab[mcp]"`, Start über `spotlab mcp`, die zwölf
   Werkzeuge in einer Tabelle.
6. **Die Trockenlauf-Schranke**, ausdrücklich: was ein Agent starten darf und was nicht.

- [ ] **Schritt 3: Ganze Suite laufen lassen**

```bash
python -m pytest -q
```

- [ ] **Schritt 4: Auf einem echten Desktop ansehen**

```bash
spotlab gui
```

Die Ansicht „Anbindungen" mit allen fünf Panel-Arten prüfen, in hell und dunkel. **Im
Offscreen-Modus gibt es keine Schriften** — das Aussehen lässt sich nur hier beurteilen.

- [ ] **Schritt 5: Committen**

```bash
git add CLAUDE.md docs/ANBINDUNG.md
git commit -m "docs: Anbindungsregeln in CLAUDE.md, Anleitung fuer fremde Projekte"
```

---

## Selbstprüfung des Plans

**Abdeckung der Spec:**

| Spec | Aufgabe |
|---|---|
| §4.1 Manifest | 2 |
| §4.2 Anbindungsordner (+ `sicherer_name` an gemeinsamen Ort) | 1, 3 |
| §4.3 Panels, fünf Arten, `bild_erlaubt`, atomar | 4 |
| §4.4 zwölf Werkzeuge | 7, 8 |
| §4.5 stdio-Server, `spotlab mcp` | 9 |
| §4.6 Ansicht „Anbindungen" | 10, 11 |
| §4.7 Trockenlauf-Schranke, beide Lagen | 5 (zweite Lage), 7 (erste Lage) |
| §4.8 `start_script` mit Argumenten | 5 |
| §3 Watcher findet fremde Läufe | 6 |
| §6 Fehlerbehandlung | als Tests in 2, 3, 4, 7, 10 |
| §7 Prüfung, drei echte Prozesse | 5 (Schranke), 7 (Start), 9 (Handshake) |
| §11 Abhängigkeit `mcp` | 9 |

**Namen, die über Aufgaben hinweg gleich bleiben müssen:** `sicherer_name`, `Manifest`,
`Skript`, `skript_von`, `ManifestFehler`, `Anbindung`, `binde_an`, `anbindungen`, `finde`,
`panelordner`, `lauf_verzeichnisse_von`, `ARTEN`, `Panel`, `schreibe`, `panels`,
`bild_erlaubt`, `pruefe_inhalt`, `ENV_NUR_TROCKEN`, `lauf_verzeichnisse`, `finde_lauf`,
`arbeitsordner`, `WERKZEUGE`, `AnbindungenView.setze_arbeitsordner`,
`AnbindungenView.aktualisiere`.

**Bewusst offen gelassen und im Plan markiert:** der genaue Name der Abtast-Methode auf
`RunRecorder` (Aufgabe 8), die Feldnamen in `maps/geometry.py` (Aufgabe 8) und die Signatur
von `FastMCP.add_tool` (Aufgabe 9). Alle drei sind vor dem Schreiben in der Quelle
nachzusehen; dort gilt die Quelle, nicht der Plan.
