"""Der Nachtrag: den Abschnitt ansehen, Gruppengroesse eintragen, Bilder loeschen.

Der Teil, den ausdruecklich ein MENSCH macht. Spot liefert Zeiten und einen
Vorschlag; ob drei Leute eine Gruppe waren, sieht man auf den Bildern.

Und danach sollen die Bilder weg koennen: es sind Aufnahmen von Schuelerinnen
und Schuelern im Schulhaus, aufgenommen fuer eine einzige Frage, die nach der
Eingabe beantwortet ist.
"""

import json

import pytest

from spotlab.experiment import nachtrag, tabelle
from spotlab.experiment.durchgang import durchgaenge_aus
from spotlab.experiment.zeitnahme import Querung


def _lauf_mit_bildern(tmp_path):
    lauf = tmp_path / "lauf"
    (lauf / "kamera").mkdir(parents=True)
    zeilen = []
    for nummer, t in enumerate([0.5, 4.0, 5.0, 6.0, 9.9, 30.0], start=1):
        datei = f"{nummer:06d}_frontleft_fisheye_image.jpg"
        (lauf / "kamera" / datei).write_bytes(b"jpeg")
        zeilen.append({"t": t, "datei": datei, "quelle": "frontleft_fisheye_image"})
    (lauf / "kamera" / "kamera.jsonl").write_text(
        "".join(json.dumps(z) + "\n" for z in zeilen), encoding="utf-8"
    )
    return lauf


def _tabelle_schreiben(lauf):
    querung = Querung(kennung="tag7", richtung=1, t_start=5.0, t_ende=9.0,
                      dauer_s=4.0, tempo_m_s=2.5)
    d = durchgaenge_aus([querung])[0]
    pfad = nachtrag.csv_pfad(lauf)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tabelle.schreibe(pfad, [tabelle.zeile_aus(d, strecke_m=10.0, uhrzeit="09:41:03")])
    return pfad


def test_die_bilder_eines_durchgangs_kommen_aus_dem_zeitfenster(tmp_path):
    lauf = _lauf_mit_bildern(tmp_path)
    pfade = nachtrag.bilder_zu(lauf, 5.0, 9.0, rand_s=1.0)
    assert [p.name[:6] for p in pfade] == ["000002", "000003", "000004", "000005"]


def test_ohne_bildindex_gibt_es_eben_keine_bilder(tmp_path):
    """Ein Lauf ohne Kameras ist kein Fehler — die Zeiten stehen trotzdem."""
    lauf = tmp_path / "leer"
    lauf.mkdir()
    assert nachtrag.bilder_zu(lauf, 0.0, 10.0) == []


def test_die_bildzeiten_werden_einmal_gelesen_und_dann_gezaehlt(tmp_path):
    """Die Ansicht zaehlt die Bilder je Durchgang. Den Index dafuer je Zeile neu
    zu lesen waere bei einer halben Stunde Aufnahme und dreissig Durchgaengen
    hunderttausend JSON-Zeilen — dieselbe Falle wie `huelle` je Bildpunkt."""
    lauf = _lauf_mit_bildern(tmp_path)
    zeiten = nachtrag.bildzeiten(lauf)
    assert zeiten == sorted(zeiten)
    assert nachtrag.zaehle_bilder(zeiten, 5.0, 9.0, rand_s=1.0) == 4
    assert nachtrag.zaehle_bilder(zeiten, 100.0, 110.0) == 0
    assert nachtrag.zaehle_bilder([], 0.0, 10.0) == 0


def test_die_uebersicht_zeigt_was_der_mensch_zum_entscheiden_braucht(tmp_path):
    lauf = _lauf_mit_bildern(tmp_path)
    _tabelle_schreiben(lauf)
    zeilen = nachtrag.uebersicht(lauf)
    assert len(zeilen) == 1
    assert "09:41:03" in zeilen[0]
    assert "1 Person" in zeilen[0] or "1 " in zeilen[0]
    assert "4.00 s" in zeilen[0]


def test_der_eintrag_landet_in_der_tabelle(tmp_path):
    lauf = _lauf_mit_bildern(tmp_path)
    pfad = _tabelle_schreiben(lauf)
    nachtrag.trage_ein(lauf, 1, klasse="4bG", gruppengroesse=3)
    zeile = tabelle.lies(pfad)[0]
    assert zeile["klasse"] == "4bG" and zeile["gruppengroesse"] == 3
    # Spots Messwerte bleiben stehen.
    assert zeile["laufzeit_s"] == pytest.approx(4.0)


def test_die_bilder_lassen_sich_nach_dem_eintrag_loeschen(tmp_path):
    """Aufnahmen von Schuelern, gemacht fuer EINE Frage. Ist sie beantwortet,
    muessen sie weggehen koennen."""
    lauf = _lauf_mit_bildern(tmp_path)
    _tabelle_schreiben(lauf)
    geloescht = nachtrag.loesche_bilder(lauf, 5.0, 9.0, rand_s=1.0)
    assert geloescht == 4
    uebrig = sorted(p.name for p in (lauf / "kamera").glob("*.jpg"))
    assert uebrig == ["000001_frontleft_fisheye_image.jpg",
                      "000006_frontleft_fisheye_image.jpg"]


def test_der_index_zeigt_nach_dem_loeschen_nicht_mehr_auf_leere_dateien(tmp_path):
    lauf = _lauf_mit_bildern(tmp_path)
    nachtrag.loesche_bilder(lauf, 5.0, 9.0, rand_s=1.0)
    zeilen = [
        json.loads(z) for z in
        (lauf / "kamera" / "kamera.jsonl").read_text("utf-8").splitlines() if z.strip()
    ]
    assert [z["t"] for z in zeilen] == [0.5, 30.0]
    for zeile in zeilen:
        assert (lauf / "kamera" / zeile["datei"]).exists()


def test_alle_bilder_auf_einmal_loeschen(tmp_path):
    lauf = _lauf_mit_bildern(tmp_path)
    assert nachtrag.loesche_alle_bilder(lauf) == 6
    assert list((lauf / "kamera").glob("*.jpg")) == []


def test_das_hauptprogramm_fragt_nur_was_offen_ist(tmp_path, monkeypatch):
    lauf = _lauf_mit_bildern(tmp_path)
    pfad = _tabelle_schreiben(lauf)
    gesagt, antworten = [], iter(["4bG", "3", "n"])
    nachtrag._hauptprogramm(
        [str(lauf)], eingabe=lambda _frage: next(antworten), drucke=gesagt.append
    )
    zeile = tabelle.lies(pfad)[0]
    assert zeile["klasse"] == "4bG" and zeile["gruppengroesse"] == 3
    # Die Bilder bleiben, weil auf die Loeschfrage 'n' kam.
    assert list((lauf / "kamera").glob("*.jpg"))

    gesagt.clear()
    nachtrag._hauptprogramm(
        [str(lauf)], eingabe=lambda _frage: "", drucke=gesagt.append
    )
    assert any("nichts offen" in satz.lower() for satz in gesagt), gesagt


def test_ohne_tabelle_sagt_es_das_statt_zu_stuerzen(tmp_path):
    gesagt = []
    nachtrag._hauptprogramm([str(tmp_path)], eingabe=lambda _f: "", drucke=gesagt.append)
    assert any("keine" in satz.lower() for satz in gesagt), gesagt
