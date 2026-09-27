"""Der Merkpunkt in `folge()`: festhalten, mitdrehen, beim Richtigen bleiben, schneller hinterher.

Entwurf vom 27.09.2026, freigegeben vom Menschen: Spot merkt sich den Menschen als Punkt
im Raum und hält ihn `merkpunkt.HALTEN_S` lang ohne neues Bild; blind FAHREN darf er
nur den Nachlauf lang, danach dreht er nur noch mit, und ist der Punkt abgelaufen, steht
er und sucht wie bisher. Weit weg darf er schneller als 0.5 m/s -- dann prüfen die
Schranken entsprechend weiter voraus.
"""

import json
import math

import pytest
from test_workshop_folgen import _koerperaufnahme_bei, _Spot

from spotlab.workshop import folgeaufnahme as fa
from spotlab.workshop import folgen, merkpunkt
from spotlab.workshop.folgen import Ziel


def _fahrten(spot):
    return [k for k in spot.kommandos if isinstance(k, dict)]


def _takte(anzahl, schritt, stand):
    """`laeuft` für `folge()`: jeder Takt rückt die Uhr `stand` um `schritt` weiter."""
    zaehler = {"n": 0}

    def laeuft():
        zaehler["n"] += 1
        stand["t"] += schritt
        return zaehler["n"] <= anzahl

    return laeuft


def _gesehen(peilung, abstand, ort=(0.0, 0.0), gier=0.0):
    return Ziel(peilung, abstand, "Körper", gier=gier, ort=ort)


def _bei(x, y):
    return _gesehen(math.degrees(math.atan2(y, x)), math.hypot(x, y))


def _folge(spot, finde, takte, schritt=0.5, **kw):
    stand = {"t": 0.0}
    kw.setdefault("melde", lambda _t: None)
    folgen.folge(spot, finde, jetzt=lambda: stand["t"], schlaf=lambda _s: None,
                 laeuft=_takte(takte, schritt, stand), **kw)


# ------------------------------------------------------------ Bild trägt den Ort


def test_die_bildaufnahme_traegt_den_ort_des_roboters(monkeypatch):
    """Aus DERSELBEN Zustandsabfrage wie Nick und Gier: sie gehören zu diesem Bild."""
    import numpy as np

    from spotlab.backends.real import panorama, tiefe

    abfragen = {"n": 0}

    class _Mit(_Spot):
        @property
        def state(self):
            abfragen["n"] += 1
            from types import SimpleNamespace
            return SimpleNamespace(pose=(1.5, -2.0, 0.7), pitch=-0.1)

    class _Pano:
        def __init__(self, kal, zuschnitt=None):
            pass

        def zusammensetzen(self, bilder):
            return np.zeros((4, 4), dtype="uint8")

    from types import SimpleNamespace
    monkeypatch.setattr(panorama, "kalibrierung_aus", lambda grau: "KAL")
    monkeypatch.setattr(panorama, "bilder_aus", lambda grau: [])
    monkeypatch.setattr(panorama, "Panorama", _Pano)
    monkeypatch.setattr(tiefe, "punkte_aus_bild", lambda a: np.zeros((1, 3)))
    spot = _Mit()
    spot.backend = SimpleNamespace(images=lambda quellen, **kw: [
        SimpleNamespace(source=SimpleNamespace(name=q)) for q in quellen])
    aufnahme = folgen.bildaufnahme(spot, {}, ("a", "b"), ("t",))
    assert aufnahme.ort == pytest.approx((1.5, -2.0)) and aufnahme.gier == pytest.approx(0.7)
    assert abfragen["n"] == 1


def _mit_ort(holen, ort=(2.0, 1.0), gier=0.25):
    from spotlab.workshop.folgen import Gesichtsaufnahme

    def mit(spot, gemerkt, *a, **kw):
        a_ = holen(spot, gemerkt)
        return Gesichtsaufnahme(a_.feld, a_.pano, None, a_.punkte, a_.blick_grad, gier=gier, ort=ort)

    return mit


def test_der_koerperfinder_gibt_den_ort_der_aufnahme_weiter():
    from test_workshop_folgen import _ein_koerper

    finder = folgen.koerper_finder(aufnahme_holen=_mit_ort(_koerperaufnahme_bei(10.0)),
                                   koerper_holen=lambda feld: [_ein_koerper()])
    ziel = finder(_Spot())
    assert ziel.ort == (2.0, 1.0) and ziel.gier == pytest.approx(0.25)


# ------------------------------------------------------------ Wer ist ER?


def _zwei_koerper_aufnahme():
    """Zwei Menschen: A genau voraus in 2 m, B bei +20 Grad in 3 m (Spalte 480)."""
    import numpy as np
    from test_backend_koerper import _Pano, _wolke

    from spotlab.workshop.folgen import Gesichtsaufnahme

    def holen(spot, gemerkt, *a, **kw):
        feld = np.zeros((782, 1239), dtype="uint8")
        punkte = np.vstack([_wolke(2.0, 0.0, 10.0), _wolke(3.0, 20.0, 10.0)])
        return Gesichtsaufnahme(feld, _Pano(), None, punkte, 0.0, gier=0.0, ort=(0.0, 0.0))

    return holen


def _koerper_bei_spalte(spalte):
    from spotlab.backends.real.koerper import Koerper

    return Koerper(huefte=(spalte, 300.0), schulter=(spalte, 250.0), conf=0.95,
                   kasten=(spalte - 60.0, 100.0, spalte + 60.0, 700.0))


def test_ohne_wahl_nimmt_der_koerperfinder_den_naechsten():
    finder = folgen.koerper_finder(aufnahme_holen=_zwei_koerper_aufnahme(),
                                   koerper_holen=lambda feld: [_koerper_bei_spalte(480.0),
                                                               _koerper_bei_spalte(620.0)])
    ziel = finder(_Spot())
    assert ziel.distance == pytest.approx(2.0, abs=0.05)
    assert finder.letzte().koerper.huefte[0] == 620.0


def test_der_koerperfinder_laesst_in_folge_den_merkpunkt_waehlen():
    """Die Wahl kommt über `folgen.waehle_ziel` -- und die Sicht für die Handzeichen ist
    die des GEWÄHLTEN Menschen, nicht die des nächsten."""
    finder = folgen.koerper_finder(aufnahme_holen=_zwei_koerper_aufnahme(),
                                   koerper_holen=lambda feld: [_koerper_bei_spalte(480.0),
                                                               _koerper_bei_spalte(620.0)])
    marke = folgen._WAHL.set(lambda kandidaten: max(kandidaten, key=lambda z: z.distance))
    try:
        ziel = finder(_Spot())
    finally:
        folgen._WAHL.reset(marke)
    assert ziel.distance == pytest.approx(3.0, abs=0.05) and ziel.bearing == pytest.approx(20.0)
    assert finder.letzte().koerper.huefte[0] == 480.0


def test_waehlt_der_merkpunkt_keinen_sagt_der_befund_es():
    finder = folgen.koerper_finder(aufnahme_holen=_zwei_koerper_aufnahme(),
                                   koerper_holen=lambda feld: [_koerper_bei_spalte(620.0)])
    marke = folgen._WAHL.set(lambda kandidaten: None)
    try:
        assert finder(_Spot()) is None
    finally:
        folgen._WAHL.reset(marke)
    assert finder.letzte() is None
    assert "Merkpunkt" in finder.befund()


def test_ein_zweiter_mensch_naeher_lenkt_ihn_nicht_ab():
    """Zwei Takte folgt er einem Menschen 3 m voraus; dann tritt ein zweiter näher
    heran, schräg links. Spot bleibt beim ersten: kein Drehen, Tempo nach 3 m."""
    plan = [[_bei(3.0, 0.0)], [_bei(3.0, 0.0)], [_bei(1.6, 1.2), _bei(3.1, 0.0)]]

    def finde(_s):
        return folgen.waehle_ziel(plan.pop(0)) if plan else None

    spot = _Spot()
    _folge(spot, finde, 3)
    dritte = _fahrten(spot)[2]
    assert dritte["wz"] == 0.0, "der Fremde steht bei +37 Grad -- er dreht nicht zu ihm"
    assert dritte["vx"] == pytest.approx(folgen.befehl(Ziel(0.0, 3.1))[0]), "Tempo nach 3.1 m"


def test_ausserhalb_von_folge_waehlt_waehle_ziel_den_naechsten():
    nah, fern = _bei(2.0, 0.0), _bei(4.0, 0.0)
    assert folgen.waehle_ziel([fern, nah]) is nah
    assert folgen.waehle_ziel([]) is None


# ------------------------------------------------------------ Festhalten


def test_verloren_haelt_er_den_punkt_aber_faehrt_nur_eine_sekunde_blind():
    """Gesehen bei +20 Grad in 3 m, dann nichts mehr; Takt 0.5 s. Eine Sekunde fährt er
    blind weiter, bis HALTEN_S dreht er nur noch hin, danach steht er und sucht."""
    plan = [_gesehen(20.0, 3.0)]
    spot = _Spot()
    _folge(spot, lambda _s: plan.pop(0) if plan else None, 10)
    fahrten = _fahrten(spot)
    fahrend = [f for f in fahrten if f["vx"] > 0.0]
    drehend = [f for f in fahrten if f["vx"] == 0.0 and f["wz"] > 0.0]
    assert len(fahrend) == 2, "der gesehene Takt und eine halbe Sekunde blind"
    assert len(drehend) == 5, "bis 3 s nach dem Bild dreht er nur noch mit"
    assert len(fahrten) == 7 and spot.kommandos[-1] == "stop"


def test_der_gemerkte_punkt_rechnet_die_eigene_fahrt_heraus():
    """Gesehen 3 m voraus; im nächsten Takt ist Spot 1 m gefahren und sieht nichts: der
    Mensch ist jetzt 2 m weg, nicht mehr 3 -- das Tempo richtet sich danach."""
    spot = _Spot()
    plan = [_gesehen(0.0, 3.0)]

    def finde(s):
        if plan:
            return plan.pop(0)
        s._pose = (1.0, 0.0, 0.0)
        return None

    _folge(spot, finde, 2)
    zweite = _fahrten(spot)[1]
    assert zweite["vx"] == pytest.approx(folgen.ANNAEHERUNG * (2.0 - folgen.WUNSCH_ABSTAND_M))


def test_beim_umrunden_dreht_er_in_die_laufrichtung_weiter():
    """Der Mensch läuft mit 1 m/s nach links und verschwindet: der gemerkte Punkt wandert
    weiter, Spot dreht weiter nach links statt beim letzten Winkel stehen zu bleiben."""
    plan = [_bei(3.0, 0.5 * i) for i in range(4)]
    spot = _Spot()
    _folge(spot, lambda _s: plan.pop(0) if plan else None, 5)
    fahrten = _fahrten(spot)
    zuletzt_gesehen, gehalten = fahrten[3], fahrten[4]
    assert gehalten["wz"] > zuletzt_gesehen["wz"] > 0.0


def test_ein_ziel_ohne_ort_haelt_wie_bisher_nur_den_nachlauf():
    """Ein Tag hat keinen Ort im Bild -- für ihn bleibt es beim alten Nachlauf."""
    plan = [Ziel(20.0, 3.0, "Tag 3")]
    spot = _Spot()
    _folge(spot, lambda _s: plan.pop(0) if plan else None, 6)
    assert len(_fahrten(spot)) == 2, "der gesehene Takt und eine halbe Sekunde Nachlauf"


def test_halten_s_null_haelt_nichts_fest():
    plan = [_gesehen(20.0, 3.0)]
    spot = _Spot()
    _folge(spot, lambda _s: plan.pop(0) if plan else None, 6, halten_s=0.0, nachlauf_s=0.0)
    assert len(_fahrten(spot)) == 1


# ------------------------------------------------------------ Schneller hinterher


def test_weit_weg_darf_er_schneller_als_nah():
    assert folgen.befehl(Ziel(0.0, 2.5))[0] <= folgen.MAX_TEMPO_M_S
    assert folgen.befehl(Ziel(0.0, 3.0))[0] == pytest.approx(0.75)
    assert folgen.befehl(Ziel(0.0, 4.0))[0] == pytest.approx(folgen.MAX_TEMPO_WEIT_M_S)
    assert folgen.MAX_TEMPO_WEIT_M_S == 1.0, "freigegeben vom Menschen am 27.09.2026"


def test_das_tempo_des_menschen_kommt_dazu():
    """Wer mit 0.2 m/s weggeht, wird nicht mit 0.21 verfolgt, sondern mit 0.41."""
    ohne = folgen.befehl(Ziel(0.0, 1.95))[0]
    mit = folgen.befehl(Ziel(0.0, 1.95), weg_tempo=0.2)[0]
    assert mit == pytest.approx(ohne + 0.2)
    assert folgen.befehl(Ziel(0.0, 2.2), weg_tempo=0.5)[0] == pytest.approx(folgen.MAX_TEMPO_M_S)
    assert folgen.befehl(Ziel(0.0, 1.95), weg_tempo=-0.5)[0] == 0.0, "kommt er näher, bremst Spot"
    assert folgen.befehl(Ziel(0.0, 1.7), weg_tempo=0.5)[0] == 0.0, "im Wunschabstand bleibt er stehen"


def test_in_folge_geht_das_tempo_des_menschen_in_den_befehl():
    """Der Mensch geht 0.1 m/s geradeaus weg, 1.9 bis 2.0 m: Spot fährt 0.34 statt 0.24."""
    plan = [_bei(1.9 + 0.05 * i, 0.0) for i in range(3)]
    spot = _Spot()
    _folge(spot, lambda _s: plan.pop(0) if plan else None, 3)
    dritte = _fahrten(spot)[2]
    assert dritte["vx"] == pytest.approx(folgen.ANNAEHERUNG * (2.0 - folgen.WUNSCH_ABSTAND_M) + 0.1)


def test_schnell_prueft_er_weiter_voraus_und_nimmt_sonst_das_alte_tempo():
    """Bei 1 m/s müssen 1.8 m frei sein. Sind es 1.5, fährt er 0.5 wie bisher -- nicht null."""
    assert folgen.vorausschau_m(folgen.MAX_TEMPO_M_S) == 0.0
    assert folgen.FREIRAUM_M + folgen.vorausschau_m(1.0) == pytest.approx(1.8)
    for frei, erwartet in ((5.0, 1.0), (1.5, folgen.MAX_TEMPO_M_S), (0.7, 0.0)):
        spot = _Spot(frei=frei)
        _folge(spot, lambda _s: _gesehen(0.0, 4.0), 1)
        fahrten = _fahrten(spot)
        vx = fahrten[0]["vx"] if fahrten else 0.0
        assert vx == pytest.approx(erwartet), f"{frei} m frei"


def test_gebremst_statt_gestanden_steht_in_der_aufnahme(tmp_path):
    spot = _Spot(frei=1.5)
    _folge(spot, lambda _s: _gesehen(0.0, 4.0), 1, lauf_dir=tmp_path, aufnahme=True)
    [zeile] = _zeilen(tmp_path)
    assert zeile["befehl"]["vx"] == pytest.approx(folgen.MAX_TEMPO_M_S)
    assert zeile["befehl"]["schranke"].startswith("langsamer: nur 1.5 m frei")


def test_schnell_prueft_auch_kopfraum_und_zone_weiter_voraus(monkeypatch):
    gefragt = {"kopfraum": [], "zone": []}

    def kopfraum(spot, meter=folgen.KOPFRAUM_M, **kw):
        gefragt["kopfraum"].append(meter)
        return (meter <= 1.2, "Überhang 1.30 m voraus")

    def zone(spot, raum, strecke=folgen.ZONE_VORAUS_M):
        gefragt["zone"].append(strecke)
        return True, ""

    monkeypatch.setattr(folgen, "kopfraum_frei", kopfraum)
    monkeypatch.setattr(folgen, "zone_voraus", zone)
    spot = _Spot()
    _folge(spot, lambda _s: _gesehen(0.0, 4.0), 1)
    assert gefragt["kopfraum"][0] == pytest.approx(folgen.KOPFRAUM_M + folgen.vorausschau_m(1.0))
    assert gefragt["zone"][0] == pytest.approx(folgen.ZONE_VORAUS_M + folgen.vorausschau_m(1.0))
    assert _fahrten(spot)[0]["vx"] == pytest.approx(folgen.MAX_TEMPO_M_S)


# ------------------------------------------------------------ Aufnahme


def _zeilen(lauf_dir):
    datei = lauf_dir / fa.ORDNER / fa.INDEX
    return [json.loads(z) for z in datei.read_text(encoding="utf-8").splitlines() if z.strip()]


def test_die_aufnahme_zeigt_den_merkpunkt_und_das_halten(tmp_path):
    plan = [_gesehen(20.0, 3.0)]
    spot = _Spot()
    _folge(spot, lambda _s: plan.pop(0) if plan else None, 4, lauf_dir=tmp_path, aufnahme=True)
    zeilen = _zeilen(tmp_path)
    assert [z["zustand"] for z in zeilen] == ["folgt", "nachlauf", "haelt", "haelt"]
    assert zeilen[0]["merkpunkt"]["alter_s"] == 0.0
    assert zeilen[2]["merkpunkt"]["alter_s"] == pytest.approx(1.0)
    assert zeilen[0]["merkpunkt"]["x"] == pytest.approx(3.0 * math.cos(math.radians(20.0)), abs=1e-3)


def test_der_film_kennt_das_halten():
    from spotlab.workshop import folgenfilm

    assert "haelt" in folgenfilm.ZUSTAND_FARBE
    assert "hält" in folgenfilm.LEGENDE


def test_die_konstanten_des_merkpunkts_passen_zum_nachlauf():
    assert merkpunkt.HALTEN_S >= folgen.NACHLAUF_S
