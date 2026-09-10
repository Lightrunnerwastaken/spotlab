"""Die Zeitnahme: mehrere gleichzeitig, und verworfen heisst protokolliert.

Der Kern des Versuchs. Ein Mensch mit der Stoppuhr kann eine Gruppe messen; hier
laeuft fuer jede erkannte Person eine eigene Uhr. Und der Fall, den der Autor
ausdruecklich genannt hat — 'wenn die zB stoppen wird das ergebnis verworfen' —
ist hier kein Sonderfall, sondern eine der drei Verwerfungsregeln.
"""

import pytest

from spotlab.experiment.strecke import Punkt, Strecke
from spotlab.experiment.zeitnahme import Sicht, Zeitnahme

STRECKE = Strecke(
    start=Punkt(0.0, 5.0), ziel=Punkt(0.0, -5.0), laenge_m=10.0,
    streuung_m=0.02, tag_start=1, tag_ziel=2, proben=5,
)


def _laufe(zeitnahme, kennung, punkte, quer_m=0.0):
    """Reicht (t, s)-Paare durch und sammelt alle fertigen Querungen."""
    fertig = []
    for t, s in punkte:
        fertig += zeitnahme.beobachte(t, [Sicht(kennung, s, quer_m)])
    return fertig


def test_eine_saubere_querung_wird_gemessen():
    z = Zeitnahme(STRECKE)
    # 1 m/s, von -2 m vor der Startlinie bis 2 m hinter dem Ziel.
    fertig = _laufe(z, "A", [(float(i), -2.0 + i) for i in range(15)])
    assert len(fertig) == 1
    q = fertig[0]
    assert not q.verworfen and q.grund is None
    assert q.t_start == pytest.approx(2.0)
    assert q.t_ende == pytest.approx(12.0)
    assert q.dauer_s == pytest.approx(10.0)
    assert q.tempo_m_s == pytest.approx(1.0)
    assert q.richtung == 1


def test_die_uhr_startet_AUF_der_linie_nicht_beim_naechsten_bild():
    """Bei 5 Hz waeren das sonst bis zu 0.2 s Fehler auf jede Messung — bei
    einer Laufzeit von 8 s sind 0.2 s zweieinhalb Prozent."""
    z = Zeitnahme(STRECKE)
    # Abtastungen bei 0.0/0.5/1.0 ...; die Linie wird zwischen zwei Bildern
    # ueberquert.
    punkte = [(0.0, -0.75), (0.5, -0.25), (1.0, 0.25)]
    punkte += [(1.0 + 0.5 * i, 0.25 + 0.5 * i) for i in range(1, 22)]
    fertig = _laufe(z, "A", punkte)
    assert len(fertig) == 1
    assert fertig[0].t_start == pytest.approx(0.75)


def test_rueckwaerts_zaehlt_genauso():
    """Im Gang laufen die Klassen in beide Richtungen."""
    z = Zeitnahme(STRECKE)
    fertig = _laufe(z, "A", [(float(i), 12.0 - i) for i in range(15)])
    assert len(fertig) == 1
    q = fertig[0]
    assert not q.verworfen
    assert q.richtung == -1
    assert q.dauer_s == pytest.approx(10.0)


def test_mehrere_laufen_gleichzeitig():
    """Der Grund fuer das ganze Programm: eine Stoppuhr je Person."""
    z = Zeitnahme(STRECKE)
    fertig = []
    for i in range(16):
        t = float(i)
        fertig += z.beobachte(t, [
            Sicht("A", -2.0 + 1.0 * i, 0.0),
            Sicht("B", -3.0 + 1.0 * i, 0.5),
        ])
    nach_kennung = {q.kennung: q for q in fertig}
    assert set(nach_kennung) == {"A", "B"}
    assert nach_kennung["A"].t_start == pytest.approx(2.0)
    assert nach_kennung["B"].t_start == pytest.approx(3.0)
    assert all(not q.verworfen for q in fertig)


def test_wer_stehen_bleibt_wird_verworfen():
    """Ausdruecklicher Wunsch des Autors — und der haeufigste Stoerfall im Gang:
    zwei bleiben stehen und reden."""
    z = Zeitnahme(STRECKE, stopp_dauer_s=1.5)
    punkte = [(0.0, -1.0), (1.0, 0.0), (2.0, 1.0), (3.0, 2.0)]
    punkte += [(4.0 + 0.5 * i, 2.0) for i in range(8)]   # vier Sekunden Stillstand
    fertig = _laufe(z, "A", punkte)
    assert len(fertig) == 1
    q = fertig[0]
    assert q.verworfen and q.grund == "gestoppt"
    # Fehlende Messwerte sind None, nie 0 (Projektregel).
    assert q.dauer_s is None and q.tempo_m_s is None
    assert q.t_start == pytest.approx(1.0)


def test_eine_kurze_pause_verwirft_noch_nicht():
    """Ein Bild ohne Fortschritt ist Messrauschen, kein Stehenbleiben."""
    z = Zeitnahme(STRECKE, stopp_dauer_s=1.5)
    punkte = [(0.0, -1.0), (1.0, 0.0), (2.0, 1.0), (2.5, 1.0), (3.0, 1.0)]
    punkte += [(3.0 + 1.0 * i, 1.0 + 1.0 * i) for i in range(1, 12)]
    fertig = _laufe(z, "A", punkte)
    assert len(fertig) == 1
    assert not fertig[0].verworfen, fertig[0].grund


def test_wer_umkehrt_wird_verworfen():
    z = Zeitnahme(STRECKE)
    punkte = [(0.0, -1.0), (1.0, 0.5), (2.0, 2.0), (3.0, 1.0), (4.0, -0.5), (5.0, -2.0)]
    fertig = _laufe(z, "A", punkte)
    assert len(fertig) == 1
    assert fertig[0].verworfen and fertig[0].grund == "umgekehrt"


def test_wer_verloren_geht_wird_verworfen_und_nicht_vergessen():
    """Ein halb gemessener Lauf, der stillschweigend verschwindet, waere die
    gefaehrlichste Variante: die Tabelle saehe vollstaendig aus."""
    z = Zeitnahme(STRECKE, verlust_s=2.0)
    fertig = _laufe(z, "A", [(0.0, -1.0), (1.0, 0.5), (2.0, 2.0)])
    assert fertig == []
    fertig = z.beobachte(5.0, [])
    assert len(fertig) == 1
    assert fertig[0].verworfen and fertig[0].grund == "verloren"


def test_wer_nur_danebensteht_startet_keine_uhr():
    """Der Korridor trennt den Gang vom Rest des Raums."""
    z = Zeitnahme(STRECKE, korridor_m=1.5)
    fertig = _laufe(z, "A", [(float(i), -2.0 + i) for i in range(15)], quer_m=3.0)
    assert fertig == []


def test_wer_mitten_auf_der_strecke_auftaucht_bekommt_keine_zeit():
    """Ohne Uebertritt der Startlinie gibt es keinen Startzeitpunkt — und eine
    geratene Startzeit waere schlimmer als gar keine Messung."""
    z = Zeitnahme(STRECKE)
    fertig = _laufe(z, "A", [(float(i), 4.0 + i) for i in range(15)])
    assert fertig == []


def test_laufende_zaehlt_die_offenen_uhren():
    """Daran haengt der Bildmitschnitt: aufnehmen, solange jemand unterwegs
    ist."""
    z = Zeitnahme(STRECKE)
    assert z.laufende() == 0
    z.beobachte(0.0, [Sicht("A", -1.0, 0.0)])
    z.beobachte(1.0, [Sicht("A", 1.0, 0.0)])
    assert z.laufende() == 1
    for i in range(2, 14):
        z.beobachte(float(i), [Sicht("A", 1.0 + (i - 1) * 1.0, 0.0)])
    assert z.laufende() == 0
