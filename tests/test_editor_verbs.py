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
from tests_zeitgrenzen import TEST_TIMEOUT_S

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


def test_jeder_vorschlag_hat_eine_deutsche_hilfe():
    """Die Vorschlagsliste IST die Dokumentation — leere Hilfe heisst kein Nutzen."""
    ohne = sorted(v.name for v in spot_verben() if not v.hilfe)
    assert ohne == []


def test_hilfen_sind_einzeilig_und_kurz():
    zu_lang = sorted(v.name for v in spot_verben() if len(v.hilfe) > 90)
    assert zu_lang == []


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
        timeout=TEST_TIMEOUT_S,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert ergebnis.stdout.strip() == ""


def test_art_unterscheidet_methode_und_eigenschaft():
    """Ohne Art gibt es kein Icon — und eine Eigenschaft mit Methoden-Icon
    verleitet dazu, Klammern zu tippen."""
    nach_name = {v.name: v for v in methoden(QUELLE, "Beispiel")}
    assert nach_name["geh"].art == "methode"
    assert nach_name["akku"].art == "eigenschaft"
