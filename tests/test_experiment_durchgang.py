"""Welche Querungen zusammengehoeren — und dass es nur ein VORSCHLAG ist.

Ob drei Leute eine Gruppe sind oder drei Einzelne, die zufaellig gleichzeitig
losgehen, kann Spot nicht wissen. Er kann sagen, WER GLEICHZEITIG unterwegs war;
den Rest entscheidet der Mensch, nachdem er den Abschnitt angesehen hat.
"""

import pytest

from spotlab.experiment.durchgang import durchgaenge_aus
from spotlab.experiment.zeitnahme import Querung


def _gut(kennung, t_start, dauer):
    return Querung(kennung=kennung, richtung=1, t_start=t_start,
                   t_ende=t_start + dauer, dauer_s=dauer, tempo_m_s=10.0 / dauer)


def _verworfen(kennung, t_start, t_ende, grund="gestoppt"):
    return Querung(kennung=kennung, richtung=1, t_start=t_start, t_ende=t_ende,
                   verworfen=True, grund=grund)


def test_wer_gleichzeitig_laeuft_bildet_einen_durchgang():
    durchgaenge = durchgaenge_aus([_gut("A", 0.0, 9.0), _gut("B", 1.0, 9.5)])
    assert len(durchgaenge) == 1
    d = durchgaenge[0]
    assert d.nummer == 1
    assert d.personen == 2 and d.gemessen == 2 and d.verworfen == 0
    assert d.t_start == pytest.approx(0.0)
    assert d.t_ende == pytest.approx(10.5)


def test_eine_lange_pause_trennt_zwei_durchgaenge():
    durchgaenge = durchgaenge_aus(
        [_gut("A", 0.0, 9.0), _gut("B", 60.0, 8.0)], luecke_s=5.0
    )
    assert [d.nummer for d in durchgaenge] == [1, 2]
    assert [d.personen for d in durchgaenge] == [1, 1]


def test_eine_kurze_luecke_trennt_nicht():
    """Der Nachzuegler einer Gruppe geht ein paar Sekunden spaeter los."""
    durchgaenge = durchgaenge_aus(
        [_gut("A", 0.0, 9.0), _gut("B", 11.0, 9.0)], luecke_s=5.0
    )
    assert len(durchgaenge) == 1


def test_die_laufzeit_ist_der_median_der_mitglieder():
    """Nicht der Mittelwert: ein Mitglied, dessen Tag einmal springt, zoege ihn
    mit. Und die Spanne steht daneben — weit auseinanderliegende Zeiten sind der
    Hinweis, dass es gar keine Gruppe war."""
    durchgaenge = durchgaenge_aus(
        [_gut("A", 0.0, 8.0), _gut("B", 0.0, 10.0), _gut("C", 0.0, 9.0)]
    )
    d = durchgaenge[0]
    assert d.laufzeit_s == pytest.approx(9.0)
    assert d.spanne_s == pytest.approx(2.0)


def test_verworfene_querungen_zaehlen_zum_durchgang_aber_nicht_zur_zeit():
    """Wer stehen geblieben ist, war trotzdem dabei — der Mensch soll ihn im
    Abschnitt sehen. In die Laufzeit geht er nicht ein."""
    durchgaenge = durchgaenge_aus(
        [_gut("A", 0.0, 9.0), _verworfen("B", 0.5, 14.0)]
    )
    d = durchgaenge[0]
    assert d.personen == 2 and d.gemessen == 1 and d.verworfen == 1
    assert d.laufzeit_s == pytest.approx(9.0)
    assert not d.gueltig, "Ein Durchgang mit einem Abbruch gilt nicht"
    assert d.gruende == ("gestoppt",)


def test_ein_durchgang_ohne_gueltige_querung_hat_keine_laufzeit():
    """Fehlende Messwerte sind None, nie 0."""
    durchgaenge = durchgaenge_aus([_verworfen("A", 0.0, 5.0, "verloren")])
    d = durchgaenge[0]
    assert d.laufzeit_s is None and d.spanne_s is None
    assert not d.gueltig


def test_ein_sauberer_einzelgaenger_gilt():
    d = durchgaenge_aus([_gut("A", 0.0, 9.0)])[0]
    assert d.gueltig and d.personen == 1


def test_die_reihenfolge_kommt_aus_der_zeit_nicht_aus_der_eingabe():
    durchgaenge = durchgaenge_aus(
        [_gut("B", 60.0, 8.0), _gut("A", 0.0, 9.0)], luecke_s=5.0
    )
    assert [d.querungen[0].kennung for d in durchgaenge] == ["A", "B"]


def test_ohne_querungen_gibt_es_keine_durchgaenge():
    assert durchgaenge_aus([]) == []
