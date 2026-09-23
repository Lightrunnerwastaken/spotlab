"""Nachspielen: ein echter Lauf mit denselben Kommandos im Sim, das Tempo verglichen.

Der Datensatz `tests/daten/tempo_real_20260916` ist ein Ausschnitt einer Fahrt am
Schul-Spot (Tastatur, 0.2 m/s und 0.39 rad/s, mit Stopps). Er steckt auch in der
mitgelieferten Tempokennlinie -- dieser Test prueft also die KETTE (lesen,
nachspielen, vergleichen) und dass sie das alte Verhalten erkennt, nicht die
Gueltigkeit des Modells. Die steht in docs/SIM_ANTWORT.md: Kennlinie aus den
Laeufen bis 16.09.2026, nachgespielt die 26 Laeufe danach.
"""

from pathlib import Path

import pytest

from spotlab.kalibrierung import nachspiel
from spotlab.kalibrierung.tempoantwort import Tempoantwort

LAUF = Path(__file__).parent / "daten" / "tempo_real_20260916"


@pytest.fixture(scope="module")
def gemessen():
    return nachspiel.vergleiche(LAUF)


def test_der_echte_spot_antwortet_verzoegert(gemessen):
    for achse in ("vx", "wz"):
        verzug, anteil = gemessen["echt"]["anpassung"][achse]
        assert 0.1 <= verzug <= 0.4, achse
        assert 0.6 <= anteil <= 1.0, achse


def test_der_sim_trifft_verzug_und_nachlauf(gemessen):
    for achse in ("vx", "wz"):
        echt = gemessen["echt"]["anpassung"][achse][0]
        sim = gemessen["sim"]["anpassung"][achse][0]
        assert sim == pytest.approx(echt, abs=0.08), achse
    echt = [n[1] for n in gemessen["echt"]["nachlauf"] if n[1] is not None]
    sim = [n[1] for n in gemessen["sim"]["nachlauf"] if n[1] is not None]
    assert echt and sim
    assert 0.5 <= sim[0] / echt[0] <= 2.0


def test_mit_sofortiger_antwort_fiele_der_vergleich_durch(gemessen):
    """Die Gegenkontrolle: das alte Verhalten (kommandiert IST erreicht, sofort)
    muss der Vergleich als falsch erkennen -- sonst waere er blind."""
    sofort = nachspiel.vergleiche(LAUF, Tempoantwort.sofort())
    for achse in ("vx", "wz"):
        echt = gemessen["echt"]["anpassung"][achse][0]
        assert abs(sofort["sim"]["anpassung"][achse][0] - echt) > 0.1, achse
    assert all(n[1] == pytest.approx(0.0, abs=1e-6) for n in sofort["sim"]["nachlauf"] if n[1] is not None)


def test_die_kommandozeile_nennt_echt_und_sim(capsys):
    assert nachspiel.main([str(LAUF)]) == 0
    aus = capsys.readouterr().out
    assert "echt" in aus and "sim" in aus and "Verzug" in aus
