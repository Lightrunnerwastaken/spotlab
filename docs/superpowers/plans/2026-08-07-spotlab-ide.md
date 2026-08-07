# spotlab IDE Implementierungsplan — Teil 1 (Aufgaben 1–6)

> **Für agentische Arbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development`
> (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Aufgabe für Aufgabe
> umzusetzen. Schritte sind Checkboxen (`- [ ]`).

**Ziel:** Ein vollständig nutzbarer Editor in der spotlab-GUI: eigene Ansicht „Code" mit
Dateibaum, Reitern, Syntaxhervorhebung, deutschen Syntaxfehlern, Vervollständigung, Starten
und anklickbaren Tracebacks.

**Architektur:** Alles, was nicht Widget ist, liegt Qt-frei und SDK-frei in `src/spotlab/editor/`
und wird ohne Fenster geprüft. Die Widgets liegen in `src/spotlab/gui/editor/`. Der Editor
startet Skripte über den bestehenden `workshop/launcher.py::start_script` und stoppt sie über
`LiveView.stoppe()` — kein zweiter Start- und kein zweiter Stoppweg.

**Technik:** Python 3.11+, PySide6, `pygments` (Hervorhebung), `jedi` (optional), `ast`,
`compile()`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-07-spotlab-ide-design.md`

**Teil 2 (Aufgaben 7–14):** `docs/superpowers/plans/2026-08-07-spotlab-ide-teil2.md`

## Globale Vorgaben

Diese Regeln gelten für **jede** Aufgabe, auch wenn sie dort nicht wiederholt werden:

- **`src/spotlab/editor/` benutzt ausschliesslich die Standardbibliothek.** Kein Import aus
  `spotlab.api`, `spotlab.backends`, `spotlab.maps`, kein `bosdyn`, `numpy`, `PIL`, `PySide6`.
  Grund: `api/spot.py` zieht über `motion`/`posture`/`state`/`perception` das ganze SDK herein.
- **Kein `import bosdyn` und kein `import spotlab.backends` unterhalb von `src/spotlab/gui/`.**
  Bestehende Regel, gilt unverändert.
- **Farben ausschliesslich aus `src/spotlab/gui/theme.py`.** Kein Farbliteral im Widget-Code.
- **Python-Bezeichner englisch nur dort, wo der bestehende Code es schon tut; neue Bezeichner
  in `editor/` und `gui/editor/` sind deutsch** (`pruefe`, `finde_stellen`, `Vorschlag`) —
  wie `maps/`, `record/` und `gui/` es bereits halten. Ausnahmeklassen englisch. **Alle Texte
  an Nutzer sind deutsch.**
- **Meldungen sagen, was zu tun ist, und behaupten keine Ursache, die nicht geprüft ist.**
- **Jede Datei wird mit `encoding="utf-8"` gelesen und mit `encoding="utf-8", newline="\n"`
  geschrieben.**
- **Tests laufen ohne Roboter, ohne Netz, ohne `jedi`.** Qt-Tests nutzen die `qapp`-Fixture aus
  `tests/conftest.py` und halten jedes Widget in einer Variablen fest (sonst
  `libshiboken: Internal C++ object already deleted`).
- Vor jedem Commit: `python -m pytest -q` muss vollständig grün sein.

---

## Aufgabe 1: `editor/syntax.py` — Syntaxfehler auf Deutsch

**Dateien:**
- Anlegen: `src/spotlab/editor/__init__.py`
- Anlegen: `src/spotlab/editor/syntax.py`
- Test: `tests/test_editor_syntax.py`

**Schnittstellen:**
- Verbraucht: nichts.
- Liefert: `Fehlerstelle(zeile: int, spalte: int, text: str)`,
  `pruefe(quelltext: str, name: str = "<editor>") -> Fehlerstelle | None`,
  `uebersetze(meldung: str) -> str`, `UEBERSETZUNGEN: tuple[tuple[str, str], ...]`.
  Aufgabe 8 ruft `pruefe`, Aufgabe 8 zeigt `Fehlerstelle` über `CodeEdit.zeige_fehler`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_editor_syntax.py`:

```python
import pytest

from spotlab.editor.syntax import UEBERSETZUNGEN, pruefe, uebersetze


def test_gueltiger_code_ergibt_keine_fehlerstelle():
    assert pruefe("x = 1\n") is None


def test_fehlender_doppelpunkt():
    stelle = pruefe("def f()\n    return 1\n")
    assert stelle.zeile == 1
    assert "Doppelpunkt" in stelle.text


def test_offene_klammer():
    stelle = pruefe("print(1\n")
    assert "Klammer" in stelle.text


def test_offene_zeichenkette():
    stelle = pruefe("s = 'hallo\n")
    assert "Anführungszeichen" in stelle.text


def test_falsche_einrueckung_nennt_die_zeile():
    stelle = pruefe("x = 1\n  y = 2\n")
    assert stelle.zeile == 2
    assert "eingerückt" in stelle.text


def test_unbekannte_meldung_bleibt_im_original():
    # Keine erfundene Erklaerung: eine falsche Faehrte kostet mehr Zeit als
    # der englische Originaltext.
    assert uebersetze("something entirely new") == "Python meldet: something entirely new"


def test_tabelle_ist_spezifisch_vor_allgemein():
    # Die echte Meldung lautet "invalid syntax. Perhaps you forgot a comma?".
    # Stuende das allgemeine Fragment zuerst, kaeme der genauere Hinweis nie zum Zug.
    fragmente = [f for f, _ in UEBERSETZUNGEN]
    assert fragmente.index("Perhaps you forgot a comma") < fragmente.index("invalid syntax")
    assert fragmente.index("unterminated triple-quoted string literal") < fragmente.index(
        "unterminated string literal"
    )


def test_ungueltige_escape_sequenz_erzeugt_keine_warnung(recwarn):
    # "C:\daten" ist auf Windows der erste Pfad, den jemand tippt, und \d ist
    # keine gueltige Escape-Sequenz. Ohne catch_warnings meldete compile() das
    # bei JEDEM Tastendruck.
    assert pruefe(r'pfad = "C:\daten"' + "\n") is None
    assert len(recwarn) == 0


@pytest.mark.parametrize(
    "quelltext, erwartet",
    [
        ("x = 1\ny = [1 2]\n", "Komma"),
        ("if True:\npass\n", "eingerückt"),
        ("1 = 2\n", "Name"),
    ],
)
def test_weitere_anfaengerfehler(quelltext, erwartet):
    stelle = pruefe(quelltext)
    assert stelle is not None
    assert erwartet in stelle.text
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_editor_syntax.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.editor'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/editor/__init__.py`:

```python
"""Qt-freie und SDK-freie Bausteine des eingebauten Editors.

Dieses Paket importiert NICHTS aus spotlab.api, spotlab.backends oder
spotlab.maps und nichts ausserhalb der Standardbibliothek. api/spot.py zieht
ueber motion/posture/state/perception bosdyn, numpy und Pillow herein; ein
Import von dort ketten den Editor an das SDK und braeche die Schichtregel der
GUI. Ein Test in tests/test_editor_verbs.py haelt das fest.
"""
```

`src/spotlab/editor/syntax.py`:

```python
"""Syntaxfehler beim Tippen — auf Deutsch.

compile() aus der Standardbibliothek stellt exakt dieselbe Diagnose, die der
spaetere Lauf melden wuerde: keine Abhaengigkeit, kein Unterprozess. Nur ist
sie englisch, und genau daran scheitert ein Anfaenger. Uebersetzt wird die
Handvoll Meldungen, die Anfaenger wirklich treffen; alles andere bleibt im
Original stehen, mit deutschem Rahmen.
"""

import warnings
from dataclasses import dataclass


@dataclass(frozen=True)
class Fehlerstelle:
    zeile: int      # 1-basiert; 1, wenn Python keine Zeile nennt
    spalte: int     # 1-basiert; 0, wenn unbekannt
    text: str       # deutsch


# GEORDNET: spezifisch vor allgemein. Das erste passende Fragment gewinnt.
UEBERSETZUNGEN = (
    ("Perhaps you forgot a comma", "Hier fehlt vermutlich ein Komma."),
    ("expected ':'", "Hier fehlt ein Doppelpunkt am Zeilenende."),
    ("was never closed", "Diese Klammer wurde nie geschlossen."),
    (
        "unterminated triple-quoted string literal",
        "Dieser mehrzeilige Text wurde nie geschlossen — es fehlen drei Anführungszeichen.",
    ),
    (
        "unterminated string literal",
        "Dieser Text wurde nie geschlossen — es fehlt ein Anführungszeichen.",
    ),
    (
        "expected an indented block",
        "Nach dem Doppelpunkt muss die nächste Zeile eingerückt sein.",
    ),
    ("unexpected indent", "Diese Zeile ist zu weit eingerückt."),
    ("unindent does not match", "Diese Einrückung passt zu keiner Zeile darüber."),
    (
        "inconsistent use of tabs",
        "Hier sind Tabulatoren und Leerzeichen gemischt. spotlab schreibt Leerzeichen.",
    ),
    ("cannot assign to", "Links vom = muss ein Name stehen."),
    (
        "invalid syntax",
        "Hier stimmt etwas nicht — häufig ein fehlender Doppelpunkt oder eine Klammer.",
    ),
)


def uebersetze(meldung):
    for fragment, text in UEBERSETZUNGEN:
        if fragment in meldung:
            return text
    return f"Python meldet: {meldung}"


def pruefe(quelltext, name="<editor>"):
    """Die erste Fehlerstelle — oder None, wenn der Text sich übersetzen lässt."""
    try:
        with warnings.catch_warnings():
            # Ohne das meldet compile() ab 3.12 bei JEDEM Tastendruck eine
            # SyntaxWarning fuer ungueltige Escape-Sequenzen wie "C:\daten".
            warnings.simplefilter("ignore")
            compile(quelltext, name, "exec")
    except SyntaxError as fehler:
        # Faengt auch IndentationError und TabError — beide sind Unterklassen.
        return Fehlerstelle(
            zeile=fehler.lineno or 1,
            spalte=fehler.offset or 0,
            text=uebersetze(fehler.msg or ""),
        )
    except ValueError as fehler:
        # Nullbytes im Text: compile() wirft ValueError, keinen SyntaxError.
        return Fehlerstelle(zeile=1, spalte=0, text=uebersetze(str(fehler)))
    return None
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_editor_syntax.py -q
```

Erwartet: PASS. Schlägt eine der Meldungsprüfungen fehl, weil diese Python-Version anders
formuliert, **die tatsächliche Meldung mit `python -c "compile(...)"` nachsehen und das
Fragment in `UEBERSETZUNGEN` daran anpassen** — nicht den Test aufweichen.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/editor/__init__.py src/spotlab/editor/syntax.py tests/test_editor_syntax.py
git commit -m "feat(editor): Syntaxfehler auf Deutsch ueber compile()"
```

---

## Aufgabe 2: `editor/traceback.py` — anklickbare Stellen

**Dateien:**
- Anlegen: `src/spotlab/editor/traceback.py`
- Test: `tests/test_editor_traceback.py`

**Schnittstellen:**
- Verbraucht: nichts.
- Liefert: `Stelle(pfad: Path, zeile: int, von: int, bis: int)`,
  `finde_stellen(text: str, wurzel: Path) -> list[Stelle]`, `MUSTER: re.Pattern`.
  Aufgabe 12 ruft `finde_stellen` je angehängter Ausgabezeile.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_editor_traceback.py`:

```python
from spotlab.editor.traceback import finde_stellen


def _projekt(tmp_path):
    projekt = tmp_path / "werkstatt" / "demo"
    projekt.mkdir(parents=True)
    skript = projekt / "runde.py"
    skript.write_text("x = 1\n", encoding="utf-8")
    return tmp_path / "werkstatt", skript


def test_findet_die_eigene_datei(tmp_path):
    wurzel, skript = _projekt(tmp_path)
    text = f'  File "{skript}", line 6, in <module>'
    stellen = finde_stellen(text, wurzel)
    assert len(stellen) == 1
    assert stellen[0].pfad == skript.resolve()
    assert stellen[0].zeile == 6
    assert text[stellen[0].von : stellen[0].bis].startswith('File "')


def test_pfad_ausserhalb_der_werkstatt_bleibt_text(tmp_path):
    # Ein Traceback zeigt fast immer mehr fremde Rahmen als eigene. Waere
    # alles anklickbar, landete ein Schueler in bosdyn/client/... und aenderte es.
    wurzel, _ = _projekt(tmp_path)
    fremd = tmp_path / "site-packages"
    fremd.mkdir()
    bibliothek = fremd / "robot_command.py"
    bibliothek.write_text("y = 2\n", encoding="utf-8")
    text = f'  File "{bibliothek}", line 42, in send'
    assert finde_stellen(text, wurzel) == []


def test_platzhalter_werden_ausgelassen(tmp_path):
    wurzel, _ = _projekt(tmp_path)
    assert finde_stellen('  File "<string>", line 1, in <module>', wurzel) == []
    assert finde_stellen('  File "<stdin>", line 1, in <module>', wurzel) == []


def test_geloeschte_datei_wird_ausgelassen(tmp_path):
    wurzel, _ = _projekt(tmp_path)
    weg = wurzel / "demo" / "gibtsnicht.py"
    assert finde_stellen(f'  File "{weg}", line 3', wurzel) == []


def test_ganzer_traceback_liefert_nur_die_eigenen_zeilen(tmp_path):
    wurzel, skript = _projekt(tmp_path)
    fremd = tmp_path / "site-packages"
    fremd.mkdir()
    bibliothek = fremd / "robot_command.py"
    bibliothek.write_text("y = 2\n", encoding="utf-8")
    text = (
        "Traceback (most recent call last):\n"
        f'  File "{skript}", line 6, in <module>\n'
        "    spot.move(forward=1.0)\n"
        f'  File "{bibliothek}", line 42, in send\n'
        "ValueError: kaputt\n"
    )
    stellen = finde_stellen(text, wurzel)
    assert [s.pfad for s in stellen] == [skript.resolve()]
    assert text[stellen[0].von : stellen[0].bis] == f'File "{skript}", line 6'


def test_leerer_text_ergibt_leere_liste(tmp_path):
    assert finde_stellen("", tmp_path) == []
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_editor_traceback.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.editor.traceback'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/editor/traceback.py`:

```python
"""Tracebacks in anklickbare Stellen zerlegen.

Anklickbar wird nur, was in der Werkstatt liegt. Ein Traceback zeigt fast
immer mehr Rahmen aus fremdem Code als aus eigenem; waere alles anklickbar,
landete ein Schueler mit einem Klick in bosdyn/client/robot_command.py und
aenderte es.

Die Offsets sind relativ zum uebergebenen Text. Die Ansicht ruft die Funktion
je angehaengter Ausgabezeile auf, die Tests ueber ganze Tracebacks — beides
geht, weil die Funktion ueber den Text nichts annimmt.
"""

import re
from dataclasses import dataclass
from pathlib import Path

MUSTER = re.compile(r'File "(?P<pfad>[^"]+)", line (?P<zeile>\d+)')


@dataclass(frozen=True)
class Stelle:
    pfad: Path
    zeile: int
    von: int
    bis: int


def finde_stellen(text, wurzel):
    """Fundstellen unterhalb `wurzel`, mit Offsets relativ zu `text`."""
    try:
        grenze = Path(wurzel).resolve()
    except (OSError, ValueError):
        return []

    gefunden = []
    for treffer in MUSTER.finditer(text):
        try:
            pfad = Path(treffer.group("pfad")).resolve()
        except (OSError, ValueError):
            continue
        # is_file() faengt "<string>", "<stdin>", geloeschte temporaere Dateien
        # und ungueltige Windows-Namen ab: Path.is_file schluckt OSError und
        # ValueError und liefert dann False.
        if not pfad.is_file():
            continue
        if not pfad.is_relative_to(grenze):
            continue
        gefunden.append(
            Stelle(
                pfad=pfad,
                zeile=int(treffer.group("zeile")),
                von=treffer.start(),
                bis=treffer.end(),
            )
        )
    return gefunden
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_editor_traceback.py -q
```

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/editor/traceback.py tests/test_editor_traceback.py
git commit -m "feat(editor): Tracebacks zerlegen, nur eigene Dateien anklickbar"
```

---

## Aufgabe 3: `editor/verbs.py` — die eigene API als Vorschlagsliste

**Dateien:**
- Anlegen: `src/spotlab/editor/verbs.py`
- Test: `tests/test_editor_verbs.py`

**Schnittstellen:**
- Verbraucht: nichts (liest `src/spotlab/api/spot.py` und `src/spotlab/__init__.py` als **Text**).
- Liefert: `Vorschlag(name: str, signatur: str, hilfe: str)`,
  `methoden(quelltext: str, klasse: str) -> list[Vorschlag]`,
  `funktionen(quelltext: str) -> list[Vorschlag]`,
  `spot_verben() -> tuple[Vorschlag, ...]`, `spotlab_verben() -> tuple[Vorschlag, ...]`,
  `praefix(text_vor_cursor: str) -> str | None`, `teilwort(text_vor_cursor: str) -> str`.
  Aufgabe 9 baut darauf die Vervollständigung, Aufgabe 5 prüft damit die Docstrings.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_editor_verbs.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spotlab.editor.verbs import (
    funktionen,
    methoden,
    praefix,
    spot_verben,
    spotlab_verben,
    teilwort,
)

QUELLE = '''
class Beispiel:
    def _versteckt(self):
        pass

    def geh(self, weite=1.0, drehung=0.0):
        """Geht eine Strecke.

        Und hier steht noch mehr, was nicht in die Liste gehört.
        """

    @property
    def akku(self):
        """Ladestand in Prozent."""


def frei(a, b=2):
    """Eine Funktion auf Modulebene."""
'''


def test_private_methoden_kommen_nicht_vor():
    assert [v.name for v in methoden(QUELLE, "Beispiel")] == ["geh", "akku"]


def test_signatur_ohne_self():
    geh = methoden(QUELLE, "Beispiel")[0]
    assert geh.signatur == "geh(weite=1.0, drehung=0.0)"


def test_hilfe_ist_die_erste_docstring_zeile():
    assert methoden(QUELLE, "Beispiel")[0].hilfe == "Geht eine Strecke."


def test_property_hat_keine_klammern():
    # Eine Eigenschaft als move()-artigen Eintrag darzustellen waere eine Falle.
    akku = methoden(QUELLE, "Beispiel")[1]
    assert akku.signatur == "akku"
    assert akku.hilfe == "Ladestand in Prozent."


def test_funktionen_auf_modulebene():
    frei = funktionen(QUELLE)[0]
    assert frei.name == "frei"
    assert frei.signatur == "frei(a, b=2)"


def test_unbekannte_klasse_ergibt_leere_liste():
    assert methoden(QUELLE, "GibtsNicht") == []


def test_unparsbarer_text_ergibt_leere_liste():
    # Der Editor darf an einer kaputten Quelldatei nie scheitern.
    assert methoden("class (", "Beispiel") == []
    assert funktionen("def (") == []


def test_spot_verben_kommen_aus_der_echten_api():
    namen = {v.name for v in spot_verben()}
    assert {"move", "walk", "stand", "sit", "cameras", "navigate_to", "load_map"} <= namen
    assert {"battery", "state", "is_powered"} <= namen
    assert not any(n.startswith("_") for n in namen)


def test_spotlab_verben_enthalten_connect():
    assert "connect" in {v.name for v in spotlab_verben()}


@pytest.mark.parametrize(
    "vorher, erwartet",
    [
        ("spot.", "spot"),
        ("spot.mo", "spot"),
        ("    x = spot.", "spot"),
        ("spot.move(spot.", "spot"),
        ("spotlab.", "spotlab"),
        ("# spot.", None),
        ("roboter.", None),   # Namensregel, keine Inferenz — dort greift jedi
        ("x = 1", None),
        ("", None),
        ("zeile eins\nspot.", "spot"),
    ],
)
def test_praefix(vorher, erwartet):
    assert praefix(vorher) == erwartet


@pytest.mark.parametrize(
    "vorher, erwartet",
    [("spot.", ""), ("spot.mov", "mov"), ("x = na", "na"), ("", "")],
)
def test_teilwort(vorher, erwartet):
    assert teilwort(vorher) == erwartet


def test_editor_zieht_weder_sdk_noch_qt_herein():
    """Die Schichtregel als Test, im Unterprozess mit echter Importreihenfolge.

    Ein Import von spotlab.api.spot waere der bequeme Weg zur Introspektion und
    zoege bosdyn, numpy und Pillow in die GUI.
    """
    quelle = Path(__file__).resolve().parents[1] / "src"
    code = (
        "import sys\n"
        "import spotlab.editor.syntax\n"
        "import spotlab.editor.traceback\n"
        "import spotlab.editor.verbs as v\n"
        "assert v.spot_verben(), 'Verbliste ist leer'\n"
        "assert v.spotlab_verben(), 'Paketliste ist leer'\n"
        "verboten = [m for m in ('bosdyn', 'numpy', 'PIL', 'PySide6') if m in sys.modules]\n"
        "print(','.join(verboten))\n"
    )
    ergebnis = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(quelle), "PYTHONUTF8": "1"},
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert ergebnis.stdout.strip() == ""
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_editor_verbs.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.editor.verbs'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/editor/verbs.py`:

```python
"""Die eigene API als Vorschlagsliste — gelesen, nicht importiert.

api/spot.py zieht ueber motion/posture/state/perception bosdyn, numpy und
Pillow herein. Ein Import waere der bequeme Weg und ketten den Editor an das
SDK. Mit ast bleibt die Vervollstaendigung auch dort brauchbar, wo das SDK
gar nicht installiert ist, und hat keine Seiteneffekte.

Die Quelldateien werden ueber reine Pfadarithmetik gefunden: editor/ und api/
sind Geschwister unter src/spotlab/. Kein Import, keine Ladereihenfolge.
"""

import ast
import functools
import re
from dataclasses import dataclass
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
SPOT_QUELLE = WURZEL / "api" / "spot.py"
PAKET_QUELLE = WURZEL / "__init__.py"

ZIELE = ("spot", "spotlab")
ZIEL_MUSTER = re.compile(r"(?P<ziel>[A-Za-z_][A-Za-z_0-9]*)\.[A-Za-z_0-9]*$")


@dataclass(frozen=True)
class Vorschlag:
    name: str
    signatur: str   # "move(forward=0.0, left=0.0, ...)" — bei @property nur der Name
    hilfe: str      # erste Docstring-Zeile, deutsch; "" wenn keine


def _erste_zeile(knoten):
    text = (ast.get_docstring(knoten) or "").strip()
    return text.splitlines()[0].strip() if text else ""


def _ist_property(knoten):
    return any(
        isinstance(d, ast.Name) and d.id == "property" for d in knoten.decorator_list
    )


def _vorschlag(knoten):
    if _ist_property(knoten):
        # Eine Eigenschaft mit Klammern anzuzeigen waere eine Falle.
        return Vorschlag(knoten.name, knoten.name, _erste_zeile(knoten))
    try:
        args = ast.unparse(knoten.args)
    except Exception:
        args = ""
    args = args.removeprefix("self").removeprefix(", ")
    return Vorschlag(knoten.name, f"{knoten.name}({args})", _erste_zeile(knoten))


def _oeffentliche(koerper):
    for knoten in koerper:
        passend = isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
        if passend and not knoten.name.startswith("_"):
            yield _vorschlag(knoten)


def _baum(quelltext):
    try:
        return ast.parse(quelltext)
    except (SyntaxError, ValueError):
        return None


def methoden(quelltext, klasse):
    baum = _baum(quelltext)
    if baum is None:
        return []
    for knoten in baum.body:
        if isinstance(knoten, ast.ClassDef) and knoten.name == klasse:
            return list(_oeffentliche(knoten.body))
    return []


def funktionen(quelltext):
    baum = _baum(quelltext)
    return [] if baum is None else list(_oeffentliche(baum.body))


def _lies(pfad):
    try:
        return pfad.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


@functools.lru_cache(maxsize=1)
def spot_verben():
    return tuple(methoden(_lies(SPOT_QUELLE), "Spot"))


@functools.lru_cache(maxsize=1)
def spotlab_verben():
    return tuple(funktionen(_lies(PAKET_QUELLE)))


def praefix(text_vor_cursor):
    """Das Ziel links vom Punkt — oder None.

    Eine Namensregel, keine Inferenz, und das soll sie sein: unsere Vorlage
    schreibt `with spotlab.connect() as spot:`, und praktisch jedes
    Schuelerskript uebernimmt das. Wer die Variable `roboter` nennt, bekommt
    von uns nichts — dort greift jedi, das den Typ wirklich herleiten kann.
    """
    zeile = text_vor_cursor.rsplit("\n", 1)[-1]
    if "#" in zeile:
        # Grob, aber in die sichere Richtung: `print("# spot.")` verliert nur
        # einen Vorschlag, statt einen im Kommentar aufzudraengen.
        return None
    treffer = ZIEL_MUSTER.search(zeile)
    if treffer is None:
        return None
    ziel = treffer.group("ziel")
    return ziel if ziel in ZIELE else None


def teilwort(text_vor_cursor):
    """Das angefangene Wort am Cursor — der Praefix fuer die Filterung."""
    zeile = text_vor_cursor.rsplit("\n", 1)[-1]
    ende = len(zeile)
    while ende > 0 and (zeile[ende - 1].isalnum() or zeile[ende - 1] == "_"):
        ende -= 1
    return zeile[ende:]
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_editor_verbs.py -q
```

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/editor/verbs.py tests/test_editor_verbs.py
git commit -m "feat(editor): Verbliste per ast aus der eigenen API, ohne Import"
```

---

## Aufgabe 4: `editor/indent.py` — Einrückungsregeln als Textarbeit

**Dateien:**
- Anlegen: `src/spotlab/editor/indent.py`
- Test: `tests/test_editor_indent.py`

**Schnittstellen:**
- Verbraucht: nichts.
- Liefert: `EINRUECKUNG: str` (vier Leerzeichen),
  `einrueckung_von(zeile: str) -> str`, `naechste_einrueckung(zeile: str) -> str`,
  `ausruecken(zeile: str) -> int` (wie viele Leerzeichen vorne wegfallen).
  Aufgabe 8 benutzt alle drei in `CodeEdit`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_editor_indent.py`:

```python
import pytest

from spotlab.editor.indent import EINRUECKUNG, ausruecken, einrueckung_von, naechste_einrueckung


def test_einrueckung_ist_vier_leerzeichen():
    assert EINRUECKUNG == "    "


@pytest.mark.parametrize(
    "zeile, erwartet",
    [("x = 1", ""), ("    x = 1", "    "), ("        x = 1", "        "), ("", "")],
)
def test_einrueckung_von(zeile, erwartet):
    assert einrueckung_von(zeile) == erwartet


@pytest.mark.parametrize(
    "zeile, erwartet",
    [
        ("x = 1", ""),
        ("    x = 1", "    "),
        ("def f():", "    "),
        ("    if True:", "        "),
        ("    if True:   ", "        "),   # Leerzeichen hinter dem Doppelpunkt
        ("d = {'a': 1}", ""),              # Doppelpunkt nicht am Zeilenende
    ],
)
def test_naechste_einrueckung(zeile, erwartet):
    assert naechste_einrueckung(zeile) == erwartet


@pytest.mark.parametrize(
    "zeile, erwartet",
    [("        x", 4), ("    x", 4), ("  x", 2), ("x", 0), ("", 0)],
)
def test_ausruecken(zeile, erwartet):
    assert ausruecken(zeile) == erwartet
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_editor_indent.py -q
```

Erwartet: `ModuleNotFoundError: No module named 'spotlab.editor.indent'`.

- [ ] **Schritt 3: Umsetzen**

`src/spotlab/editor/indent.py`:

```python
"""Einrueckung als Textarbeit.

Im Widget bleibt damit nur noch das Einfuegen uebrig — die Regeln selbst
werden hier ohne Fenster geprueft.
"""

EINRUECKUNG = "    "


def einrueckung_von(zeile):
    """Die fuehrenden Leerzeichen einer Zeile."""
    return zeile[: len(zeile) - len(zeile.lstrip(" "))]


def naechste_einrueckung(zeile):
    """Womit die Folgezeile beginnt: gleich viel, nach ':' eine Ebene mehr."""
    tiefe = einrueckung_von(zeile)
    return tiefe + EINRUECKUNG if zeile.rstrip().endswith(":") else tiefe


def ausruecken(zeile):
    """Wie viele fuehrende Leerzeichen bei Shift+Tab wegfallen (hoechstens eine Ebene)."""
    return min(len(einrueckung_von(zeile)), len(EINRUECKUNG))
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_editor_indent.py -q
```

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/editor/indent.py tests/test_editor_indent.py
git commit -m "feat(editor): Einrueckungsregeln Qt-frei"
```

---

## Aufgabe 5: Deutsche Docstrings für `Spot`

**Warum das eine eigene Aufgabe ist:** von den vierzehn öffentlichen Namen in `api/spot.py`
trägt heute **einzig `robot`** einen Docstring. Ohne diese Aufgabe zeigt die Vervollständigung
nackte Signaturen, und der grösste Einzelnutzen des Editors — dass die Vorschlagsliste
zugleich die Dokumentation ist — fiele weg.

**Dateien:**
- Ändern: `src/spotlab/api/spot.py` (Docstrings für jede öffentliche Methode und Eigenschaft)
- Test: `tests/test_editor_verbs.py` (ergänzen)

**Schnittstellen:**
- Verbraucht: `spot_verben()` aus Aufgabe 3.
- Liefert: keine neue API — nur Inhalt. **Keine Signatur wird geändert.**

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `tests/test_editor_verbs.py` anhängen:

```python
def test_jeder_vorschlag_hat_eine_deutsche_hilfe():
    """Die Vorschlagsliste IST die Dokumentation — leere Hilfe heisst kein Nutzen."""
    ohne = sorted(v.name for v in spot_verben() if not v.hilfe)
    assert ohne == []


def test_hilfen_sind_einzeilig_und_kurz():
    zu_lang = sorted(v.name for v in spot_verben() if len(v.hilfe) > 90)
    assert zu_lang == []
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_editor_verbs.py::test_jeder_vorschlag_hat_eine_deutsche_hilfe -q
```

Erwartet: FAIL — die Liste enthält `battery`, `camera`, `cameras`, `close`, `is_powered`,
`load_map`, `localize`, `move`, `navigate_to`, `power_off`, `power_on`, `send`, `sit`,
`stand`, `state`, `stop`, `walk`, `waypoints`.

- [ ] **Schritt 3: Umsetzen**

In `src/spotlab/api/spot.py` je eine deutsche Zeile als Docstring einfügen. **Nur Docstrings —
kein Verhalten, keine Signatur ändern.** Die vorhandene Zeile bei `robot` bleibt.

```python
    def power_on(self):
        """Schaltet die Motoren ein. Spot steht davon noch nicht auf."""

    def power_off(self, safe=True):
        """Schaltet die Motoren ab; mit safe=True setzt Spot sich vorher hin."""

    @property
    def is_powered(self):
        """True, solange die Motoren eingeschaltet sind."""

    @property
    def battery(self):
        """Ladestand des Akkus in Prozent."""

    def stand(self, height=0.0, timeout=10.0, schlaf=None):
        """Steht auf. height hebt oder senkt den Körper in Metern."""

    def sit(self, timeout=10.0, schlaf=None):
        """Setzt sich hin."""

    def move(self, forward=0.0, left=0.0, turn=0.0, timeout=30.0):
        """Geht eine feste Strecke in Metern und dreht sich um turn im Bogenmass."""

    def walk(self, vx=0.0, vy=0.0, wz=0.0, duration=1.0):
        """Fährt duration Sekunden lang mit den angegebenen Geschwindigkeiten."""

    def stop(self):
        """Hält sofort an."""

    def cameras(self):
        """Nennt die Namen der Kameras, die dieser Spot hat."""

    def camera(self, name):
        """Holt ein Bild der genannten Kamera und zeichnet es auf."""

    @property
    def state(self):
        """Der aktuelle Zustand: Pose, Geschwindigkeit, Füsse, Akku."""

    def load_map(self, name=None):
        """Lädt eine GraphNav-Karte; ohne Namen die aktive aus der Konfiguration."""

    def localize(self):
        """Bestimmt über ein Fiducial, wo Spot auf der geladenen Karte steht."""

    def navigate_to(self, ziel, timeout=120.0):
        """Fährt autonom zum genannten Wegpunkt der geladenen Karte."""

    def waypoints(self):
        """Nennt die Wegpunkte der geladenen Karte."""

    def send(self, command, end_time_secs=None):
        """Schickt ein rohes RobotCommand-Protobuf an den Roboter."""

    def close(self):
        """Beendet die Verbindung. connect() ruft das am Ende selbst auf."""
```

**Wichtig:** Der Docstring kommt jeweils als erste Zeile **in** den Methodenkörper, vor den
bestehenden Code. Bei `navigate_to` steht danach unverändert die `if self._karte is None:`-Prüfung.

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_editor_verbs.py -q
python -m pytest -q
```

Erwartet: beide grün. Die zweite Zeile stellt sicher, dass keine Methode versehentlich
beschädigt wurde.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/api/spot.py tests/test_editor_verbs.py
git commit -m "docs(api): deutsche Docstrings fuer jede oeffentliche Methode von Spot"
```

---

## Aufgabe 6: `gui/theme.py` — fünf Farben für die Hervorhebung

**Dateien:**
- Ändern: `src/spotlab/gui/theme.py`
- Test: `tests/test_gui_theme.py` (ergänzen)

**Schnittstellen:**
- Verbraucht: nichts.
- Liefert: `Palette.schluesselwort`, `.zeichenkette`, `.kommentar`, `.zahl`, `.funktion`
  in `DUNKEL` und `HELL`. Aufgabe 7 baut daraus die Textformate; Aufgaben 8–12 benutzen die
  vorhandenen Felder für die neuen Widgets.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `tests/test_gui_theme.py` anhängen (falls die Datei anders heisst, in die bestehende
Theme-Testdatei):

```python
SYNTAXFELDER = ("schluesselwort", "zeichenkette", "kommentar", "zahl", "funktion")


def test_beide_paletten_haben_die_syntaxfarben():
    for palette in (DUNKEL, HELL):
        for feld in SYNTAXFELDER:
            wert = getattr(palette, feld)
            assert wert.startswith("#") and len(wert) == 7


def test_syntaxfarben_sind_unterscheidbar():
    for palette in (DUNKEL, HELL):
        farben = {getattr(palette, feld) for feld in SYNTAXFELDER}
        assert len(farben) == 5          # keine zwei Token sehen gleich aus
        assert palette.text not in farben  # und keine faellt mit dem Fliesstext zusammen


def test_neue_stylesheet_regeln_bringen_keine_fremden_farben():
    import re

    for palette in (DUNKEL, HELL):
        erlaubt = {getattr(palette, f.name) for f in fields(palette)}
        gefunden = set(re.findall(r"#[0-9a-fA-F]{6}", stylesheet(palette)))
        assert gefunden <= erlaubt
```

Der Import am Kopf der Datei muss `fields` aus `dataclasses` und `stylesheet` enthalten:

```python
from dataclasses import fields

from spotlab.gui.theme import DUNKEL, HELL, Palette, palette_fuer, stylesheet
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

```bash
python -m pytest tests/test_gui_theme.py -q
```

Erwartet: FAIL mit `AttributeError: 'Palette' object has no attribute 'schluesselwort'`.

- [ ] **Schritt 3: Umsetzen**

In `src/spotlab/gui/theme.py` die Felder an `Palette` anhängen:

```python
@dataclass(frozen=True)
class Palette:
    hintergrund: str
    flaeche: str
    rand: str
    text: str
    gedaempft: str
    akzent: str
    ok: str
    warnung: str
    gefahr: str
    # Syntaxhervorhebung. Angewendet werden sie ueber QTextCharFormat, nicht
    # ueber das Stylesheet — deshalb stehen sie unten nicht noch einmal.
    schluesselwort: str
    zeichenkette: str
    kommentar: str
    zahl: str
    funktion: str
```

Werte ergänzen:

```python
DUNKEL = Palette(
    hintergrund="#1e1f22",
    flaeche="#26282c",
    rand="#34373d",
    text="#d7dae0",
    gedaempft="#868d97",
    akzent="#579dff",
    ok="#3fb950",
    warnung="#d29922",
    gefahr="#e5484d",
    schluesselwort="#c678dd",
    zeichenkette="#98c379",
    kommentar="#7f848e",
    zahl="#d19a66",
    funktion="#61afef",
)

HELL = Palette(
    hintergrund="#f4f5f7",
    flaeche="#ffffff",
    rand="#dfe1e6",
    text="#1f2328",
    gedaempft="#6b7280",
    akzent="#0b5cd5",
    ok="#1a7f37",
    warnung="#9a6700",
    gefahr="#d1372f",
    schluesselwort="#a626a4",
    zeichenkette="#2a7d3f",
    kommentar="#8a9099",
    zahl="#97600a",
    funktion="#2f5fd0",
)
```

Am Ende von `stylesheet(p)` — vor dem schliessenden `"""` — die Regeln für die neuen Widgets
anhängen:

```python
QTreeView {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 8px;
}}
QTreeView::item {{ padding: 3px 2px; }}
QTreeView::item:selected {{ background: {p.rand}; color: {p.text}; }}
QTabWidget::pane {{ border: 1px solid {p.rand}; border-radius: 8px; }}
QTabBar::tab {{
    background: transparent;
    color: {p.gedaempft};
    padding: 6px 12px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.akzent}; }}
QComboBox {{
    background: {p.flaeche};
    border: 1px solid {p.rand};
    border-radius: 7px;
    padding: 5px 8px;
}}
QSplitter::handle {{ background: {p.rand}; }}
```

- [ ] **Schritt 4: Tests laufen lassen**

```bash
python -m pytest tests/test_gui_theme.py -q
python -m pytest -q
```

Erwartet: beide grün. Falls ein bestehender Test `Palette(...)` mit Positionsargumenten baut,
fehlen ihm jetzt fünf — dann dort auf Schlüsselwortargumente umstellen oder `DUNKEL`/`HELL`
benutzen.

**Zum Aussehen:** Die Werte sind ein Ausgangspunkt. Im Offscreen-Modus gibt es keine Schriften;
beurteilt wird die Hervorhebung erst auf einem echten Desktop nach Aufgabe 14.

- [ ] **Schritt 5: Committen**

```bash
git add src/spotlab/gui/theme.py tests/test_gui_theme.py
git commit -m "feat(gui): fuenf Syntaxfarben und Stile fuer Baum, Reiter und Splitter"
```

---

**Ende Teil 1.** Weiter mit `docs/superpowers/plans/2026-08-07-spotlab-ide-teil2.md`
(Aufgaben 7–14: Widgets, Ansicht „Code", Verdrahtung, Dokumentation).
