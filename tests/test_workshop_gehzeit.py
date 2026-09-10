"""Das Gehzeit-Programm: Strecke messen, zusehen, Tabelle schreiben.

Ohne Roboter — der Spot ist hier eine Attrappe, die ein Drehbuch abspielt. Was
geprueft wird, ist die KETTE: Tags zu Strecke, Sichtungen zu Zeiten, Zeiten zu
Durchgaengen, Durchgaenge in eine Tabelle, die ein Mensch weiterfuellen kann.
"""

import json
from dataclasses import dataclass

import pytest

from spotlab.experiment import tabelle
from spotlab.workshop import gehzeit as modul


@dataclass(frozen=True)
class FakeTag:
    id: int
    bearing: float
    distance: float


class FakeSpot:
    """Spielt ein Drehbuch ab: je Aufruf von `tags()` eine Liste von Tags.

    Die beiden Streckentags stehen fest, die Laeufer kommen aus dem Drehbuch.
    """

    recorder = None

    def __init__(self, drehbuch, strecke_tags=((1, 90.0, 5.0), (2, -90.0, 5.0))):
        self._drehbuch = list(drehbuch)
        self._fest = [FakeTag(*t) for t in strecke_tags]
        self.aufrufe = 0

    def tags(self, id=None):
        self.aufrufe += 1
        laeufer = self._drehbuch.pop(0) if self._drehbuch else []
        return list(self._fest) + [FakeTag(*t) for t in laeufer]


def _uhr(schritt=0.2):
    """Eine Uhr, die bei jedem Blick um `schritt` weiterlaeuft."""
    stand = {"t": 0.0}

    def jetzt():
        stand["t"] += schritt
        return stand["t"]

    return jetzt


def _gerade_hindurch(kennung, tempo_m_s=1.0, takte=30, takt_s=0.5, start_m=-1.0):
    """Ein Laeufer quer durch die Strecke: (x, y) je Takt als Tag-Sichtung.

    Die Strecke liegt zwischen (0, +5) und (0, -5); wer sie entlanglaeuft,
    wandert in y von +6 nach -6 und bleibt bei x = 0. In Peilung und Abstand:
    genau links bzw. genau rechts von Spot.
    """
    schritte = []
    for i in range(takte):
        s = start_m + tempo_m_s * takt_s * i
        y = 5.0 - s
        peilung = 90.0 if y >= 0 else -90.0
        schritte.append([(kennung, peilung, abs(y))])
    return schritte


def test_die_kette_von_den_tags_bis_in_die_tabelle(tmp_path):
    drehbuch = _gerade_hindurch(7, tempo_m_s=1.0, takte=30, takt_s=0.5)
    spot = FakeSpot([[] for _ in range(12)] + drehbuch)
    ergebnis = modul.gehzeit(
        spot, ziel=tmp_path / "gehzeit", dauer_s=100.0, takt_s=0.5,
        jetzt=_uhr(0.5), uhr=_uhr(0.5), schlaf=lambda _s: None, laeuft=lambda: True,
        melde=lambda _t: None,
    )
    assert ergebnis["grund"] is None
    assert ergebnis["strecke"].laenge_m == pytest.approx(10.0)
    assert len(ergebnis["durchgaenge"]) == 1

    zeilen = tabelle.lies(tmp_path / "gehzeit" / modul.CSV_NAME)
    assert len(zeilen) == 1
    assert zeilen[0]["personen"] == 1
    assert zeilen[0]["laufzeit_s"] == pytest.approx(10.0, abs=0.6)
    assert zeilen[0]["strecke_m"] == pytest.approx(10.0)
    assert zeilen[0]["gueltig"] is True
    # Was Spot nicht weiss, bleibt leer, bis ein Mensch es eintraegt.
    assert zeilen[0]["gruppengroesse"] is None and zeilen[0]["klasse"] == ""


def test_die_strecke_wird_gemessen_und_aufgeschrieben(tmp_path):
    spot = FakeSpot([[] for _ in range(20)])
    modul.gehzeit(
        spot, ziel=tmp_path / "gehzeit", dauer_s=1.0, takt_s=0.5,
        jetzt=_uhr(0.5), uhr=_uhr(0.5), schlaf=lambda _s: None, laeuft=lambda: True,
        melde=lambda _t: None,
    )
    gemessen = json.loads((tmp_path / "gehzeit" / modul.STRECKE_NAME).read_text("utf-8"))
    assert gemessen["laenge_m"] == pytest.approx(10.0)
    assert gemessen["tag_start"] in (1, 2) and gemessen["tag_ziel"] in (1, 2)
    assert gemessen["proben"] == modul.MESS_PROBEN
    # Ohne den Versatz findet der Nachtrag die Uhrzeit eines Durchgangs nicht.
    assert "wanduhr_versatz" in gemessen


def test_die_streckentags_laufen_nicht_selber_mit(tmp_path):
    """Sie haengen an der Wand — als Laeufer waeren sie zwei sehr geduldige
    Versuchspersonen, die nie ankommen."""
    spot = FakeSpot([[] for _ in range(60)])
    ergebnis = modul.gehzeit(
        spot, ziel=tmp_path / "gehzeit", dauer_s=20.0, takt_s=0.5,
        jetzt=_uhr(0.5), uhr=_uhr(0.5), schlaf=lambda _s: None, laeuft=lambda: True,
        melde=lambda _t: None,
    )
    assert ergebnis["querungen"] == []


def test_ohne_zwei_tags_gibt_es_keine_messung_und_keinen_absturz(tmp_path):
    """Ein Programm, das mit einem Stacktrace endet, sagt einem Schueler
    weniger als ein Satz."""
    spot = FakeSpot([[] for _ in range(20)], strecke_tags=((1, 0.0, 3.0),))
    gesagt = []
    ergebnis = modul.gehzeit(
        spot, ziel=tmp_path / "gehzeit", dauer_s=5.0, takt_s=0.5,
        jetzt=_uhr(0.5), uhr=_uhr(0.5), schlaf=lambda _s: None, laeuft=lambda: True,
        melde=gesagt.append,
    )
    assert ergebnis["strecke"] is None
    assert "zwei" in ergebnis["grund"]
    assert any("Keine Messung" in satz for satz in gesagt)


def test_eine_wackelige_strecke_wird_abgelehnt(tmp_path):
    """Auf eine Strecke mit einem Meter Unsicherheit laesst sich kein Tempo
    rechnen — und ein stillschweigend gerechnetes waere schlimmer."""
    class Wackelig(FakeSpot):
        def tags(self, id=None):
            self.aufrufe += 1
            weit = 5.0 + (2.0 if self.aufrufe % 2 else 0.0)
            return [FakeTag(1, 90.0, 5.0), FakeTag(2, -90.0, weit)]

    gesagt = []
    ergebnis = modul.gehzeit(
        Wackelig([]), ziel=tmp_path / "gehzeit", dauer_s=5.0, takt_s=0.5,
        jetzt=_uhr(0.5), uhr=_uhr(0.5), schlaf=lambda _s: None, laeuft=lambda: True,
        melde=gesagt.append,
    )
    assert ergebnis["strecke"] is not None
    assert "schwankt" in ergebnis["grund"]
    assert not (tmp_path / "gehzeit" / modul.CSV_NAME).exists()


def test_eine_ausfallende_quelle_beendet_den_versuch_nicht(tmp_path):
    """Sie meldet sich EINMAL. Still uebergehen waere schlimmer: eine leere
    Tabelle saehe aus wie ein Gang, durch den niemand ging."""
    spot = FakeSpot([[] for _ in range(20)])

    def kaputte_quelle(_spot):
        raise RuntimeError("Tracker weg")

    gesagt = []
    ergebnis = modul.gehzeit(
        spot, quelle=kaputte_quelle, ziel=tmp_path / "gehzeit", dauer_s=5.0,
        takt_s=0.5, jetzt=_uhr(0.5), uhr=_uhr(0.5), schlaf=lambda _s: None,
        laeuft=lambda: True, melde=gesagt.append,
    )
    assert ergebnis["grund"] is None
    ausfaelle = [s for s in gesagt if "Quelle fällt aus" in s]
    assert len(ausfaelle) == 1, gesagt


def test_jede_querung_steht_anhaengend_auf_der_platte(tmp_path):
    """Die Tabelle wird neu geschrieben, `querungen.jsonl` waechst nur — ein
    Absturz kostet dort hoechstens die letzte Zeile."""
    drehbuch = _gerade_hindurch(7, tempo_m_s=1.0, takte=30, takt_s=0.5)
    spot = FakeSpot([[] for _ in range(12)] + drehbuch)
    modul.gehzeit(
        spot, ziel=tmp_path / "gehzeit", dauer_s=100.0, takt_s=0.5,
        jetzt=_uhr(0.5), uhr=_uhr(0.5), schlaf=lambda _s: None, laeuft=lambda: True,
        melde=lambda _t: None,
    )
    zeilen = [
        json.loads(z) for z in
        (tmp_path / "gehzeit" / modul.QUERUNGEN_NAME).read_text("utf-8").splitlines()
    ]
    assert len(zeilen) == 1
    assert zeilen[0]["kennung"] == "tag7" and zeilen[0]["verworfen"] is False


def test_der_bildmitschnitt_laeuft_dicht_nur_solange_jemand_geht(tmp_path):
    """Zwei Stunden bei zwei Bildern je Sekunde waeren Gigabytes fuer einen
    leeren Gang."""
    class Mitschnitt:
        def __init__(self):
            self.raten = []

        def setze_rate(self, hz):
            self.raten.append(hz)

    drehbuch = _gerade_hindurch(7, tempo_m_s=1.0, takte=30, takt_s=0.5)
    spot = FakeSpot([[] for _ in range(12)] + drehbuch)
    mitschnitt = Mitschnitt()
    modul.gehzeit(
        spot, ziel=tmp_path / "gehzeit", dauer_s=100.0, takt_s=0.5,
        jetzt=_uhr(0.5), uhr=_uhr(0.5), schlaf=lambda _s: None, laeuft=lambda: True,
        melde=lambda _t: None, mitschnitt=mitschnitt,
    )
    assert modul.BILD_HZ in mitschnitt.raten
    assert modul.BILD_HZ_RUHE in mitschnitt.raten
    assert 0.0 not in mitschnitt.raten, (
        "Rate 0 schaltet den Bildthread nicht ab, sondern nimmt ihm die Wartezeit"
    )


def test_das_programm_bewegt_nichts():
    """Dasselbe Gate wie bei der Sonde: eine Naht ist erst eine Naht, wenn sie
    reisst, sobald jemand durchgreift."""
    import ast
    from pathlib import Path

    quelle = Path(modul.__file__).read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    gerufen = {
        knoten.func.attr
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
    }
    verboten = gerufen & {
        "walk", "move", "stand", "sit", "power_on", "power_off",
        "navigate_to", "send_command", "pose",
    }
    assert not verboten, f"Der Versuch darf nichts bewegen, ruft aber: {sorted(verboten)}"
