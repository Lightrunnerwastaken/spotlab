"""Lage: Batteriewechsel-Haltung und Aufrichten -- der Kern hinter den Knoepfen im Tab „Fahren".

Gemessen am 16.09.2026 am Geraet (Software 5.1.3): das Rollkommando bringt Spot in
~5 s auf die Seite, und er schaltet die Motoren SELBST ab, sobald er kippt
(Rollwinkel ~ -113 Grad, Endlage ~ -131). Die Rueckmeldung des Kommandos blieb dabei
STATUS_UNKNOWN -- deshalb zaehlt hier der Koerper (Rollwinkel, Motoren), nie die
Meldung. Self-right brachte ihn in ~3.5 s von -134 auf 0 Grad.
"""

import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from spotlab.errors import SpotlabError
from spotlab.workshop import lage
from tests_zeitgrenzen import TEST_TIMEOUT_S

ROOT = Path(__file__).resolve().parents[1]


class _Spot:
    """Ein Spot, dessen Koerper eine vorgegebene Folge von Lagen durchlaeuft --
    je Blick auf `state` die naechste (dann die letzte, fuer immer)."""

    def __init__(self, rollen=(0.0,), powered=(True,), robot=object(), akku=42.0):
        self._rollen, self._powered = list(rollen), list(powered)
        self.robot = robot
        self.battery = akku
        self.gesendet, self.kommandos = [], []
        self._i = 0

    def _bei(self, folge):
        return folge[min(self._i, len(folge) - 1)]

    @property
    def state(self):
        zustand = SimpleNamespace(roll=math.radians(self._bei(self._rollen)),
                                  powered=self._bei(self._powered))
        self._i += 1
        return zustand

    @property
    def is_powered(self):
        return self._bei(self._powered)

    def power_on(self):
        self.kommandos.append("power_on")

    def power_off(self, safe=True):
        self.kommandos.append(("power_off", safe))

    def sit(self):
        self.kommandos.append("sit")

    def send(self, command):
        self.gesendet.append(command)
        return 1


def _uhr(schritt=0.5):
    stand = {"t": 0.0}

    def jetzt():
        stand["t"] += schritt
        return stand["t"]

    return jetzt


def _lauf(spot, aktion, **kw):
    gesagt = []
    if aktion == "akku":
        text = lage.umlegen(spot, kw.pop("seite", "links"), melde=gesagt.append,
                            jetzt=_uhr(), schlaf=lambda _s: None, **kw)
    else:
        text = lage.aufrichten(spot, melde=gesagt.append, jetzt=_uhr(), schlaf=lambda _s: None, **kw)
    return text, gesagt


# ------------------------------------------------------------ Umlegen (Akku)


def test_umlegen_schickt_das_rollkommando_zur_gewaehlten_seite_und_hoert_beim_motor_aus_auf():
    spot = _Spot(rollen=[0.0, -40.0, -113.0], powered=[True, True, False])
    text, gesagt = _lauf(spot, "akku", seite="links")
    assert spot.kommandos == ["power_on"], "Motoren an, aber KEIN power_off: Spot schaltet selbst ab"
    assert len(spot.gesendet) == 1
    assert "battery_change_pose_request" in str(spot.gesendet[0])
    assert "HINT_LEFT" in str(spot.gesendet[0])
    assert "Motoren von selbst aus" in text and "-113" in text and "linken Seite" in text
    assert any("Rollwinkel -45" in m or "Rollwinkel -40" in m for m in gesagt), "der Verlauf wird gesagt"


def test_rechts_heisst_rechts():
    spot = _Spot(rollen=[0.0, 113.0], powered=[True, False])
    text, _ = _lauf(spot, "akku", seite="rechts")
    assert "HINT_RIGHT" in str(spot.gesendet[0]) and "rechten Seite" in text


def test_liegt_er_aber_bleibt_unter_strom_schaltet_das_programm_sicher_ab():
    spot = _Spot(rollen=[-100.0], powered=[True])
    text, _ = _lauf(spot, "akku", warte_s=3.0)
    assert ("power_off", True) in spot.kommandos
    assert "linken Seite" in text and "Motoren aus" in text


def test_kippt_er_nicht_ist_das_ein_fehler_mit_rat():
    spot = _Spot(rollen=[0.0], powered=[True])
    with pytest.raises(SpotlabError) as fehler:
        _lauf(spot, "akku", warte_s=3.0)
    assert "nicht auf der Seite" in str(fehler.value) and "Tablet" in str(fehler.value)
    assert ("power_off", True) not in spot.kommandos, "aufrecht und unter Strom: nichts abschalten, der Mensch sieht nach"


def test_eine_unbekannte_seite_wird_vor_dem_einschalten_abgelehnt():
    spot = _Spot()
    with pytest.raises(SpotlabError):
        _lauf(spot, "akku", seite="oben")
    assert spot.kommandos == [] and spot.gesendet == []


def test_ohne_echten_roboter_wird_geschickt_und_gesagt_nicht_gewartet():
    """Trockenlauf und Sims kennen keine Rollwinkel: das Kommando geht raus (damit die
    Aufzeichnung es zeigt), gewartet wird nicht, und der Text sagt es."""
    spot = _Spot(robot=None)
    text, _ = _lauf(spot, "akku")
    assert len(spot.gesendet) == 1 and "kein echter Roboter" in text
    assert spot._i == 0, "kein Blick auf den Koerper"


# ---------------------------------------------------------------- Aufrichten


def test_aufrichten_schickt_selfright_wartet_auf_ruhe_und_setzt_sich():
    spot = _Spot(rollen=[-130.0, -60.0, 5.0, 3.0, 2.0, 1.0, 1.0, 1.0])
    text, gesagt = _lauf(spot, "aufrichten")
    assert spot.kommandos == ["power_on", "sit"]
    assert len(spot.gesendet) == 1 and "selfright_request" in str(spot.gesendet[0])
    assert "sitzt" in text
    assert any("aufrecht" in m for m in gesagt)


def test_die_ruhe_muss_anhalten_ein_kurzes_aufrecht_reicht_nicht():
    """Waehrend des Self-right geht der Winkel durch null -- erst RUHE_S ruhig heisst oben."""
    spot = _Spot(rollen=[-130.0, 5.0, -50.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    text, _ = _lauf(spot, "aufrichten")
    assert "sitzt" in text
    assert spot._i >= 7, "nach dem Rueckfall auf -50 zaehlt die Ruhe von vorn"


def test_wer_schon_aufrecht_liegt_setzt_sich_nur():
    spot = _Spot(rollen=[3.0])
    text, gesagt = _lauf(spot, "aufrichten")
    assert spot.gesendet == [] and spot.kommandos == ["power_on", "sit"]
    assert any("schon aufrecht" in m for m in gesagt)


def test_bleibt_er_liegen_ist_das_ein_fehler():
    spot = _Spot(rollen=[-130.0])
    with pytest.raises(SpotlabError) as fehler:
        _lauf(spot, "aufrichten", warte_s=3.0)
    assert "nicht aufrecht" in str(fehler.value)
    assert "sit" not in spot.kommandos, "liegend setzt er sich nicht"


def test_aufrichten_ohne_echten_roboter_schickt_und_setzt_sich():
    spot = _Spot(robot=None)
    text, _ = _lauf(spot, "aufrichten")
    assert "selfright_request" in str(spot.gesendet[0]) and "sit" in spot.kommandos
    assert "kein echter Roboter" in text


# -------------------------------------------------------------- Hauptprogramm


def test_die_argumente_nennen_aktion_seite_laufordner_und_uebernahme():
    assert lage.argumente(["akku", "rechts", "--runs", "x", "--uebernehmen"]) == ("akku", "rechts", "x", True)
    assert lage.argumente(["aufrichten"]) == ("aufrichten", "links", None, False)
    with pytest.raises(SpotlabError):
        lage.argumente(["tanzen"])
    with pytest.raises(SpotlabError):
        lage.argumente(["akku", "oben"])
    with pytest.raises(SpotlabError):
        lage.argumente([])


@pytest.mark.parametrize("aktion", ["akku", "aufrichten"])
def test_das_hauptprogramm_laeuft_ohne_roboter_als_prozess_und_hinterlaesst_seinen_lauf(aktion, tmp_path):
    """Paketcode, wie der Knopf ihn startet: das Lauf-Verzeichnis kommt AUSDRUECKLICH
    mit (`--runs`), sonst laege es zwischen den Quelltexten."""
    env = dict(os.environ, SPOTLAB_BACKEND="dryrun", SPOTLAB_NUR_TROCKEN="1",
               PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    runs = tmp_path / "runs"
    ergebnis = subprocess.run([sys.executable, str(lage.SKRIPT), aktion, "rechts", "--runs", str(runs)],
                              cwd=tmp_path, env=env, capture_output=True, text=True,
                              timeout=TEST_TIMEOUT_S)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "Fertig" in ergebnis.stdout
    assert list(runs.glob("*/lauf.json")), "der Lauf liegt im genannten Ordner"
    assert not list((lage.SKRIPT.parent / "runs").glob("*")) if (lage.SKRIPT.parent / "runs").exists() else True
