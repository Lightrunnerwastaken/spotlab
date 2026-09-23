"""Was die GUI beim Start NICHT laden darf.

Gemessen am 23.09.2026 (warm, Entwicklungsrechner): `import spotlab.gui.app`
2.2 s, davon das Spot-SDK 1.2 s (ueber die Fehleruebersetzung), der
Passwort-Tresor 0.4 s (ueber die Konfiguration) und jedi 0.3 s (ueber den
Editor). Alle drei braucht die GUI erst, wenn etwas geschieht: ein Fehler vom
Roboter, ein Login, eine Vervollstaendigung. Kalt, nach dem Hochfahren, dauerte
der Start 17 s.

Geprueft in einem frischen Prozess: im Testlauf selbst sind die Module laengst
geladen.
"""

import subprocess
import sys

import pytest

pytest.importorskip("PySide6.QtWidgets")

# `bosdyn.client`, nicht `bosdyn`: die Protobuf-Texte der Kartenfehler
# (errors/graphnav.py, 0.1 s) duerfen bleiben, der Client (1.2 s) nicht.
SCHWER = ("bosdyn.client", "keyring", "jedi")


def _geladen_nach(code):
    pruefung = (
        f"{code}\n"
        "import sys\n"
        f"print(','.join(m for m in {SCHWER!r} if m in sys.modules))\n"
    )
    ergebnis = subprocess.run([sys.executable, "-c", pruefung], capture_output=True,
                              text=True, timeout=120)
    assert ergebnis.returncode == 0, ergebnis.stderr
    return ergebnis.stdout.strip().splitlines()[-1] if ergebnis.stdout.strip() else ""


def test_die_gui_laedt_beim_import_kein_sdk_keinen_tresor_kein_jedi():
    assert _geladen_nach("import spotlab.gui.app") == ""


def test_ein_gewoehnlicher_fehler_laedt_das_sdk_nicht():
    code = ("from spotlab.errors import translate\n"
            "assert translate(ValueError('x')) is None")
    assert _geladen_nach(code) == ""


def test_ein_sdk_fehler_wird_weiter_uebersetzt():
    from bosdyn.client.exceptions import UnableToConnectToRobotError

    from spotlab.errors import NotReachable, translate

    fehler = UnableToConnectToRobotError(None, "weg")
    assert isinstance(translate(fehler, ip="192.168.80.3"), NotReachable)
