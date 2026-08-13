"""Der Vergleich Modell gegen Messung.

Die Prüfung selbst muss geprüft werden. Der Kernfehler wäre, dass die
Selbstprüfung die Stelle NICHT herausnimmt — dann käme überall null heraus,
und man hielte einen Zirkelschluss für ein Ergebnis.
"""

import math

import pytest

from spotlab.kalibrierung import gang
from spotlab.kalibrierung.modell import Gangmodell
from spotlab.kalibrierung.pruefung import (
    _abweichung,
    als_text,
    halteprobe,
    lueckenprobe,
    selbstpruefung,
    zusammenfassung,
)

PUNKTE = 8


def _stelle(tempo, versatz=0.0, fenster="B2-1", abschnitt=1, absicht=True, dreh=0.0):
    """Eine Stützstelle, deren Gelenkbahnen eine verschobene Sinuswelle sind."""
    namen = [f"{b}.{g}" for b in ("fl", "fr", "hl", "hr") for g in ("hx", "hy", "kn")]
    bahn = [math.sin(2 * math.pi * k / PUNKTE) + versatz for k in range(PUNKTE)]
    return {
        "tempo_m_s": tempo,
        "drehrate_rad_s": dreh,
        "absicht": {"ziel_m_s": f"{tempo:.2f}"} if absicht else {},
        "zyklusdauer_s": 1.0,
        "zyklusdauer_streuung_s": 0.0,
        "duty": [0.6] * 4,
        "phasen": [0.0, 0.5, 0.25, 0.75],
        "muster": "zweitakt",
        "hoehe_m": 0.51,
        "gelenke": {n: list(bahn) for n in namen},
        "gelenke_streuung": {n: [0.0] * PUNKTE for n in namen},
        "zyklen": 5,
        "herkunft": {"fenster": fenster, "abschnitt": abschnitt,
                     "abschnitte_im_fenster": 3},
    }


def _kennlinie(stellen):
    return {"fassung": 1, "phasenpunkte": PUNKTE, "stuetzstellen": stellen}


# --------------------------------------------------------------- Die Metrik


def test_ein_modell_das_die_stelle_kennt_hat_keinen_fehler():
    """Sanitaetspruefung der Metrik selbst."""
    stelle = _stelle(0.30)
    modell = Gangmodell(_kennlinie([stelle]))
    assert _abweichung(modell, stelle)["rms_rad"] == pytest.approx(0.0, abs=1e-6)


def test_die_metrik_findet_einen_verschobenen_gang():
    """Gegenprobe: eine um 0.5 rad verschobene Bahn muss auch 0.5 ergeben."""
    modell = Gangmodell(_kennlinie([_stelle(0.30, versatz=0.0)]))
    verschoben = _stelle(0.30, versatz=0.5)
    assert _abweichung(modell, verschoben)["rms_rad"] == pytest.approx(0.5, abs=0.01)


# --------------------------------------------------------------- Leave-one-out


def test_die_selbstpruefung_nimmt_die_stelle_wirklich_heraus():
    """DER Test dieser Datei.

    Bleibt die gepruefte Stelle im Modell, sagt es sie perfekt vorher und die
    Pruefung meldet ueberall null -- ein Zirkelschluss, der wie ein Ergebnis
    aussieht.
    """
    stellen = [
        _stelle(0.20, versatz=0.0, abschnitt=1),
        _stelle(0.30, versatz=1.0, abschnitt=2),   # deutlich andere Bahn
        _stelle(0.40, versatz=0.0, abschnitt=3),
    ]
    kennlinie = _kennlinie(stellen)

    # Der direkte Gegensatz: MIT der Stelle im Modell ist der Fehler null.
    mit_allem = Gangmodell(kennlinie)
    assert _abweichung(mit_allem, stellen[1])["rms_rad"] == pytest.approx(0.0, abs=1e-6)

    # Die Selbstpruefung darf genau das NICHT liefern -- sie sagt die Stelle aus
    # ihren Nachbarn vorher und liegt dann um rund 1.0 daneben.
    ergebnisse = {e["tempo_m_s"]: e["rms_rad"] for e in selbstpruefung(kennlinie)}
    assert ergebnisse[0.30] > 0.5, ergebnisse


def test_die_selbstpruefung_meldet_den_abstand_zum_naechsten():
    """Ohne ihn ist ein Fehler nicht einzuordnen: eine Vorhersage ueber
    0.17 m/s hinweg darf schlechter sein als eine ueber 0.01."""
    stellen = [_stelle(0.20), _stelle(0.30, abschnitt=2), _stelle(0.60, abschnitt=3)]
    nach_tempo = {e["tempo_m_s"]: e for e in selbstpruefung(_kennlinie(stellen))}
    assert nach_tempo[0.30]["abstand_zum_naechsten_m_s"] == pytest.approx(0.10)
    assert nach_tempo[0.60]["abstand_zum_naechsten_m_s"] == pytest.approx(0.30)


# --------------------------------------------------------------- Lueckenprobe


def test_die_lueckenprobe_entfernt_das_ganze_band():
    """Die Selbstpruefung ist zu optimistisch, wenn Nachbarn dicht stehen.
    Erst ein ganzes entferntes Band zeigt, was der Sim in einer ungemessenen
    Zone tut."""
    stellen = [
        _stelle(0.10, versatz=0.0, abschnitt=1),
        _stelle(0.20, versatz=1.0, abschnitt=2),
        _stelle(0.25, versatz=1.0, abschnitt=3),
        _stelle(0.60, versatz=0.0, abschnitt=4),
    ]
    e = lueckenprobe(_kennlinie(stellen), 0.15, 0.30)
    assert e["stellen"] == 2
    # Beide werden aus 0.10 und 0.60 vorhergesagt, also aus versatz 0.0 --
    # der Fehler muss nahe bei 1.0 liegen.
    assert e["rms_median"] > 0.5, e
    for x in e["ergebnisse"]:
        assert x["abstand_zum_naechsten_m_s"] >= 0.05


def test_ohne_stellen_im_band_passiert_nichts():
    e = lueckenprobe(_kennlinie([_stelle(0.10), _stelle(0.60, abschnitt=2)]), 0.2, 0.3)
    assert e["stellen"] == 0 and e["ergebnisse"] == []


# --------------------------------------------------------------- Halteprobe


def test_die_halteprobe_nimmt_nur_ungesehene_stellen():
    """Fenster ohne Absicht gehen nicht ins Modell -- nur die duerfen hier
    geprueft werden, sonst ist es wieder ein Zirkelschluss."""
    stellen = [
        _stelle(0.30, abschnitt=1),
        _stelle(0.31, fenster="B7", abschnitt=1, absicht=False),
        _stelle(0.32, fenster="B6", abschnitt=1, absicht=False),
    ]
    geprueft = {e["fenster"] for e in halteprobe(_kennlinie(stellen))}
    assert geprueft == {"B6", "B7"}


def test_die_negativkontrolle_faellt_auf_wenn_die_metrik_blind_ist():
    """Sind Treppe und Ebene gleich gut, misst die Metrik nicht, was sie
    behauptet -- dann muss die Kontrolle NICHT bestanden melden."""
    gleich = [
        _stelle(0.30, abschnitt=1),
        _stelle(0.30, fenster="B7", absicht=False),
        _stelle(0.30, fenster="B6", absicht=False),
    ]
    assert zusammenfassung(_kennlinie(gleich))["negativkontrolle_bestanden"] is False

    schlechter = [
        _stelle(0.30, abschnitt=1),
        _stelle(0.30, fenster="B7", absicht=False),
        _stelle(0.30, fenster="B6", absicht=False, versatz=1.0),
    ]
    assert zusammenfassung(_kennlinie(schlechter))["negativkontrolle_bestanden"] is True


def test_ohne_haltedaten_gibt_es_kein_urteil():
    """None heisst „nicht durchfuehrbar", nicht „bestanden"."""
    ohne = _kennlinie([_stelle(0.30), _stelle(0.40, abschnitt=2)])
    assert zusammenfassung(ohne)["negativkontrolle_bestanden"] is None


# --------------------------------------------------------------- An echten Daten


def test_die_ausgelieferte_kennlinie_besteht_die_negativkontrolle():
    """Am 12.08.2026: eben 4.6 Grad, Treppe 15.3 Grad. Wuerde die Treppe
    ploetzlich gleich gut, waere entweder die Metrik kaputt oder in der
    Kennlinie steckte Treppendaten."""
    z = zusammenfassung(gang.lade())
    assert z["negativkontrolle_bestanden"] is True
    assert z["halteprobe_treppe_B6"]["rms_mittel"] > z["halteprobe_eben_B7"]["rms_mittel"]


def test_der_bericht_nennt_die_falle():
    """Wer den Bericht liest, muss sehen, dass die Selbstpruefung optimistisch
    ist -- sonst haelt er 0.8 Grad fuer die Guete des Sims."""
    text = als_text(gang.lade())
    assert "Optimistisch" in text
    assert "Negativkontrolle" in text
    assert "Grad" in text
