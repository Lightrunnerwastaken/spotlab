"""Gesichter in Spots Frontkameras -- und die Gegenprobe aus der Geometrie.

Der Erkenner findet Kaesten; ob einer ein Gesicht sein KANN, entscheidet die
Physik: aus Hoehenwinkel und gemessenem Abstand folgt die Hoehe ueber dem Boden.
Ueber die Aufzeichnung vom 12.08.2026 fand YuNet in 4 von 107 Takten etwas --
der beste Treffer war eine Stuhllehne, der zweitbeste ein SCHIENBEIN.
"""

import math

import numpy as np
import pytest

from spotlab.backends.real import gesicht
from spotlab.errors import SpotlabError

# ------------------------------------------------------- Abstand aus Tiefe


def _wolke(abstand, peilung_grad, hoehenwinkel_grad, anzahl=30):
    p, h = math.radians(peilung_grad), math.radians(hoehenwinkel_grad)
    eben = abstand
    x, y = eben * math.cos(p), eben * math.sin(p)
    z = eben * math.tan(h)
    return np.array([[x, y, z]] * anzahl, dtype=float)


def test_der_abstand_kommt_aus_den_punkten_in_dieser_richtung():
    punkte = np.vstack([_wolke(2.0, 0.0, 20.0), _wolke(5.0, 60.0, 0.0)])
    assert gesicht.abstand_in_richtung(punkte, 0.0, 20.0) == pytest.approx(2.0, abs=0.01)
    assert gesicht.abstand_in_richtung(punkte, 60.0, 0.0) == pytest.approx(5.0, abs=0.01)
    assert gesicht.abstand_in_richtung(punkte, -60.0, 0.0) is None


def test_der_median_gewinnt_gegen_einen_ausreisser():
    """Ein einzelner Punkt vor dem Gesicht waere sonst der gemeldete Abstand."""
    punkte = np.vstack([_wolke(3.0, 0.0, 15.0, anzahl=30), _wolke(0.4, 0.0, 15.0, anzahl=1)])
    assert gesicht.abstand_in_richtung(punkte, 0.0, 15.0) == pytest.approx(3.0, abs=0.01)


def test_zu_wenige_punkte_geben_keinen_abstand():
    assert gesicht.abstand_in_richtung(_wolke(2.0, 0.0, 0.0, anzahl=3), 0.0, 0.0) is None
    assert gesicht.abstand_in_richtung(None, 0.0, 0.0) is None
    assert gesicht.abstand_in_richtung(np.zeros((0, 3)), 0.0, 0.0) is None


# ------------------------------------------------------------ Gegenprobe


class _Pano:
    """Ein Panorama, das eine feste Richtung liefert."""

    def __init__(self, peilung, hoehenwinkel):
        self._winkel = (peilung, hoehenwinkel)

    def winkel(self, spalte, zeile):
        return self._winkel


def _mit_kaesten(monkeypatch, kaesten):
    monkeypatch.setattr(gesicht, "kaesten", lambda feld, erkenner_: kaesten)


def test_ein_schienbein_faellt_durch_die_gegenprobe(monkeypatch):
    """Der echte Fehltreffer vom 12.08.2026: ein Bein, einen Meter voraus."""
    _mit_kaesten(monkeypatch, [(320.0, 181.0, 104.0, 210.0, 0.66)])
    punkte = _wolke(1.0, 0.0, 0.0)
    assert gesicht.gesichter(None, _Pano(0.0, 0.0), None, punkte, 0.46) == []


def test_ein_kopf_auf_kopfhoehe_zaehlt(monkeypatch):
    _mit_kaesten(monkeypatch, [(700.0, 100.0, 40.0, 50.0, 0.8)])
    # 3 m voraus, 20 Grad hinauf -> 0.46 + 3*tan(20) = 1.55 m
    punkte = _wolke(3.0, 0.0, 20.0)
    [kopf] = gesicht.gesichter(None, _Pano(0.0, 20.0), None, punkte, 0.46)
    assert kopf.height == pytest.approx(1.55, abs=0.02)
    assert kopf.distance == pytest.approx(3.0, abs=0.01)
    assert kopf.bearing == 0.0 and kopf.score == 0.8


def test_ohne_tiefenpunkte_zaehlt_kein_kasten(monkeypatch):
    """Ohne Entfernung gibt es keine Gegenprobe -- und ohne Gegenprobe ist ein
    Schienbein ein Gesicht."""
    _mit_kaesten(monkeypatch, [(700.0, 100.0, 40.0, 50.0, 0.99)])
    assert gesicht.gesichter(None, _Pano(0.0, 20.0), None, np.zeros((0, 3)), 0.46) == []


def test_das_naechste_gesicht_steht_vorne(monkeypatch):
    _mit_kaesten(monkeypatch, [(0.0, 0.0, 40.0, 50.0, 0.8), (500.0, 0.0, 40.0, 50.0, 0.9)])

    class _Zwei:
        def __init__(self):
            self._folge = [(0.0, 20.0), (30.0, 20.0)]

        def winkel(self, spalte, zeile):
            return self._folge[0] if spalte < 100 else self._folge[1]

    punkte = np.vstack([_wolke(4.0, 0.0, 20.0), _wolke(2.5, 30.0, 20.0)])
    gefunden = gesicht.gesichter(None, _Zwei(), None, punkte, 0.46)
    assert [round(g.distance, 1) for g in gefunden] == [2.5, 4.0]


# --------------------------------------------------------------- Modell


def test_ein_fehlendes_modell_sagt_wo_es_herkommt(tmp_path, monkeypatch):
    """Unabhaengig davon, ob auf DIESEM Rechner ein Modell liegt.

    Bis zum 11.09.2026 stand hier kein `monkeypatch`, und der Test bestand nur,
    solange niemand das Modell abgelegt hatte: geprueft wird der Fall "nirgends
    gefunden", und der Standardordner ist der dritte der drei Orte, an denen
    gesucht wird. Sobald das Modell wirklich da war, fiel er -- ein Test, der am
    Zustand des Entwicklungsrechners haengt, prueft die falsche Sache
    (CLAUDE.md, Abschnitt Tests).
    """
    monkeypatch.setattr(gesicht, "MODELL_ORDNER", tmp_path / "leer")
    with pytest.raises(SpotlabError, match="OpenCV-Zoo"):
        gesicht.modellpfad(tmp_path / "gibtsnicht.onnx", umgebung={})


def test_der_standardordner_zaehlt_als_letzter(tmp_path, monkeypatch):
    """Der Ort, an den die Anleitung das Modell legen laesst.

    Die Gegenprobe zum Test darueber: ohne sie prueft niemand mehr, dass der
    Standardordner ueberhaupt durchsucht wird.
    """
    monkeypatch.setattr(gesicht, "MODELL_ORDNER", tmp_path)
    pfad = tmp_path / gesicht.MODELL_DATEI
    pfad.write_bytes(b"x")
    assert gesicht.modellpfad(umgebung={}) == pfad


def test_ein_vorhandenes_modell_wird_genommen(tmp_path):
    pfad = tmp_path / "modell.onnx"
    pfad.write_bytes(b"x")
    assert gesicht.modellpfad(pfad, umgebung={}) == pfad


def test_die_umgebungsvariable_zaehlt_wenn_kein_pfad_kommt(tmp_path):
    """Damit eine schon vorhandene Kopie nicht kopiert werden muss."""
    pfad = tmp_path / "modell.onnx"
    pfad.write_bytes(b"x")
    assert gesicht.modellpfad(umgebung={gesicht.ENV_MODELL: str(pfad)}) == pfad


# ============ Mit echtem Erkenner, echtem Bild und echter Geometrie
#
# Braucht OpenCV und das YuNet-Modell (SPOTLAB_GESICHTSMODELL oder
# ~/.spotlab/modelle/). Fehlt eines, wird uebersprungen -- die Aussage oben
# steht auch ohne, weil sie Geometrie ist und kein Modell.


def _modell_da():
    try:
        gesicht.modellpfad()
        return True
    except SpotlabError:
        return False


@pytest.mark.skipif(not _modell_da(), reason="YuNet-Modell nicht abgelegt")
def test_das_echte_schienbein_faellt_durch_die_gegenprobe():
    """Takt 50 der Aufzeichnung: YuNet setzt einen Kasten mit 0.66 auf ein Bein.
    Mit Tiefenpunkten auf einem Meter ist der Kasten rund einen halben Meter
    ueber dem Boden -- und damit kein Gesicht.

    Gefuettert wird hier das ROHE Bild (`mit_ausgleich=False`). Das ist kein
    Umgehen des neuen Verhaltens, sondern sein Gegenteil: geprueft wird die
    GEOMETRIE, und dafuer braucht der Test einen Fehltreffer. Mit Ausgleich
    setzt YuNet auf diesem Takt gar keinen Kasten mehr (gemessen 11.09.2026) --
    ein kleiner Nebenbeleg fuer den Ausgleich, aber dann prueft dieser Test
    nichts mehr.
    """
    pytest.importorskip("cv2")
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).parent))
    from test_backend_panorama import _paar

    from spotlab.backends.real import panorama

    kameras = panorama.kalibrierung_aus(_paar(90))
    pano = panorama.Panorama(kameras, zuschnitt=panorama.ALLES)
    feld = pano.zusammensetzen(panorama.bilder_aus(_paar(50)))
    erkenner_ = gesicht.erkenner(pano.breite, pano.hoehe, mindestscore=0.5)

    roh = gesicht.kaesten(feld, erkenner_, mit_ausgleich=False)
    assert roh, "der Erkenner findet hier etwas -- genau das ist der Fehltreffer"

    # Die Person ging dicht vorbei: Tiefenpunkte auf einem Meter, rundum.
    punkte = np.vstack([_wolke(1.0, p, h, anzahl=40)
                        for p in range(-60, 61, 5) for h in (-20, 0, 20)])
    befunde = gesicht.beurteile(feld, pano, erkenner_, punkte, pano.kamerahoehe(),
                                kaesten_holen=lambda f, e: roh)
    assert befunde, "der Kasten steht im Bericht"
    assert not any(b.genommen for b in befunde), "aber keiner wird genommen"
    # WELCHE Schranke greift, haengt an der synthetischen Punktwolke dieses
    # Tests; festgehalten wird, dass ein GRUND dasteht -- der Kasten
    # verschwindet nicht stillschweigend.
    assert all(b.grund for b in befunde)


# ============ Mit geneigtem Koerper
#
# Der Hoehenwinkel aus dem Panorama ist KOERPERFEST. Hebt Spot die Nase,
# erscheint derselbe Punkt weiter unten im Bild -- ohne Korrektur laege ein
# Gesicht auf drei Metern bei 15 Grad Neigung rund 80 cm zu tief.


def test_ohne_korrektur_faellt_ein_gesicht_bei_geneigtem_koerper_durch(monkeypatch):
    """Die Gegenprobe rechnet den Nick heraus -- sonst verwirft sie den Kopf."""
    _mit_kaesten(monkeypatch, [(700.0, 100.0, 40.0, 50.0, 0.8)])
    # Der Kopf steht 3 m voraus auf 1.55 m, der Koerper ist 15 Grad geneigt.
    # Im Bild erscheint er deshalb bei 20 - 15 = 5 Grad.
    punkte = _wolke(3.0, 0.0, 20.0)
    pano = _Pano(0.0, 5.0)

    ohne = gesicht.gesichter(None, pano, None, punkte, 0.46)
    assert ohne == [], "ohne Korrektur passt weder Richtung noch Hoehe"

    [kopf] = gesicht.gesichter(None, pano, None, punkte, 0.56, blick_grad=15.0)
    assert kopf.elevation == pytest.approx(20.0)
    assert kopf.height == pytest.approx(0.56 + 3.0 * math.tan(math.radians(20.0)), abs=0.01)


def test_die_kamera_hebt_sich_mit_der_nase():
    """Sie sitzt 38 cm vor der Koerpermitte -- bei 15 Grad steigt sie gut 10 cm."""
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).parent))
    from test_backend_panorama import _paar

    from spotlab.backends.real import panorama

    pano = panorama.Panorama(panorama.kalibrierung_aus(_paar(90)))
    flach = pano.kamerahoehe()
    geneigt = pano.kamerahoehe(15.0)
    assert geneigt - flach == pytest.approx(0.10, abs=0.02)
    assert pano.kamerahoehe(0.0) == pytest.approx(flach)


# ============ Das Urteil je Kasten
#
# Bis zum 11.09.2026 gab `gesichter()` nur die genommenen Kaesten zurueck. Am
# Geraet hiess das Ergebnis damit immer "nichts gefunden" -- ohne zu sagen, ob
# YuNet gar keinen Kasten setzte oder ob die Gegenprobe ihn verwarf, und wenn ja
# an welcher Schranke. Fuer A34 Teil 3 ("notieren, ob trotzdem etwas durchkommt")
# reicht das nicht: verworfen heisst protokolliert, nicht verschwiegen.


class _PanoZeile:
    """Hoehenwinkel aus der Bildzeile -- fuer zwei Kaesten in einem Bild."""

    def winkel(self, spalte, zeile):
        return 0.0, (200.0 - zeile) / 5.0


def test_ein_genommener_kasten_traegt_seine_zahlen(monkeypatch):
    _mit_kaesten(monkeypatch, [(700.0, 100.0, 40.0, 50.0, 0.9)])
    befunde = gesicht.beurteile(None, _Pano(0.0, 20.0), None, _wolke(3.0, 0.0, 20.0), 0.46)
    assert len(befunde) == 1
    b = befunde[0]
    assert b.genommen and b.grund is None
    assert b.score == pytest.approx(0.9)
    assert b.distance == pytest.approx(3.0, abs=0.01)
    assert b.height == pytest.approx(1.55, abs=0.02)


def test_ein_kasten_ohne_tiefenpunkte_nennt_genau_das(monkeypatch):
    """Der haeufigste Fall am Geraet -- und der, der bisher wie 'kein Gesicht'
    aussah. Ohne Abstand gibt es keine Gegenprobe, also zaehlt der Kasten nicht;
    aber man muss erfahren, DASS einer da war."""
    _mit_kaesten(monkeypatch, [(700.0, 100.0, 40.0, 50.0, 0.8)])
    befunde = gesicht.beurteile(None, _Pano(0.0, 20.0), None, np.zeros((0, 3)), 0.46)
    assert len(befunde) == 1
    b = befunde[0]
    assert not b.genommen and b.grund == gesicht.OHNE_TIEFE
    assert b.distance is None and b.height is None, "kein Messwert, also None"
    assert b.score == pytest.approx(0.8), "die Punktzahl steht trotzdem da"


def test_ein_kasten_zu_tief_nennt_die_hoehe_und_die_schranke(monkeypatch):
    """Das Schienbein vom 12.08.2026 -- und derselbe Zweig, der am 11.09.2026
    einen HOCKENDEN Menschen verwerfen wuerde: die untere Schranke steht bei
    1.0 m, und ein hockender Kopf liegt genau dort."""
    _mit_kaesten(monkeypatch, [(320.0, 181.0, 104.0, 210.0, 0.66)])
    befunde = gesicht.beurteile(None, _Pano(0.0, 0.0), None, _wolke(1.0, 0.0, 0.0), 0.46)
    assert len(befunde) == 1
    b = befunde[0]
    assert not b.genommen and b.grund == gesicht.ZU_TIEF
    assert b.height == pytest.approx(0.46, abs=0.02), "gemessen, nur zu tief"
    assert b.distance == pytest.approx(1.0, abs=0.01)


def test_gesichter_ist_die_auswahl_aus_den_befunden(monkeypatch):
    """Eine Formulierung, nicht zwei. Sonst misst die Messprobe etwas anderes,
    als der Folgemodus tut -- und das faellt erst am Geraet auf, wo niemand es
    nachrechnet."""
    # Die MITTE des Kastens bestimmt den Winkel: Zeile 100 -> 20 Grad hinauf,
    # Zeile 200 -> waagrecht.
    _mit_kaesten(monkeypatch, [(700.0, 80.0, 40.0, 40.0, 0.9),
                               (320.0, 180.0, 40.0, 40.0, 0.66)])
    pano = _PanoZeile()
    punkte = np.vstack([_wolke(3.0, 0.0, 20.0), _wolke(1.0, 0.0, 0.0)])

    befunde = gesicht.beurteile(None, pano, None, punkte, 0.46)
    assert len(befunde) == 2, "beide Kaesten stehen im Bericht"
    assert [b.genommen for b in befunde] == [True, False]
    assert befunde[1].grund == gesicht.ZU_TIEF

    gefunden = gesicht.gesichter(None, pano, None, punkte, 0.46)
    assert [round(g.distance, 2) for g in gefunden] == [
        round(b.distance, 2) for b in befunde if b.genommen
    ]


# ============ Aufhellen vor dem Erkennen
#
# Gemessen an 60 echten Panoramen vom 11.09.2026 (Person vor dem Roboter,
# Median-Helligkeit 36 von 255). Bei der Produktionsschwelle 0.6 fand YuNet:
#
#     roh                      0 von 60 Takten
#     Histogrammausgleich      2 von 60, beide gesichtsgross, beste 0.71
#     Perzentil-Streckung      0 von 60
#     CLAHE                    0 von 60
#
# Der eine Kasten, den das ROHE Bild bei 0.37 hergab, war 493x551 px gross --
# ein halbes Bild, kein Gesicht. Der Unterschied ist also nicht die Anzahl,
# sondern die ART: einmal Unsinn unter der Schwelle, einmal ein richtiges
# Gesicht darueber.


def test_aufhellen_macht_ein_dunkles_bild_hell():
    dunkel = np.full((100, 200), 30, dtype=np.uint8)
    dunkel[40:60, 80:120] = 60
    hell = gesicht.aufhellen(dunkel)
    assert hell.max() > dunkel.max(), "der Kontrast wird gespreizt"
    assert hell.dtype == np.uint8 and hell.shape == dunkel.shape


def test_aufhellen_laesst_die_schwarzen_ecken_schwarz():
    """Der Zuschnitt ALLES hat schwarze Ecken -- rund ein Drittel der Flaeche.

    Sie sind kein Bildinhalt: waeren sie in der Kennlinie, verschoebe schon die
    Form des Zuschnitts die Helligkeit des Bildes.
    """
    feld = np.full((100, 200), 40, dtype=np.uint8)
    feld[:, :60] = 0                     # die Ecke
    hell = gesicht.aufhellen(feld)
    assert (hell[:, :60] == 0).all(), "schwarz bleibt schwarz"
    assert hell[:, 60:].min() > 0


def test_aufhellen_haelt_die_reihenfolge_der_helligkeiten():
    """Eine monotone Kennlinie: was dunkler war, bleibt dunkler. Sonst
    verschoebe das Aufhellen Kanten, statt sie sichtbar zu machen."""
    feld = np.array([[10, 20, 30, 40, 50]] * 4, dtype=np.uint8)
    hell = gesicht.aufhellen(feld)
    zeile = [int(v) for v in hell[0]]
    assert zeile == sorted(zeile)


def test_aufhellen_ueberlebt_ein_ganz_schwarzes_bild():
    """Ein abgerissener Bildabruf darf nicht in eine Division durch null laufen."""
    leer = np.zeros((50, 50), dtype=np.uint8)
    assert gesicht.aufhellen(leer).shape == leer.shape


def test_kaesten_fuettert_den_erkenner_mit_dem_aufgehellten_bild():
    """Die Naht: das Aufhellen sitzt genau dort, wo das Bild den Erkenner
    trifft -- nicht in der Fahransicht, die ein Mensch anschaut."""

    class Erkenner:
        def __init__(self):
            self.bekommen = None

        def setInputSize(self, groesse):
            pass

        def detect(self, bild):
            self.bekommen = bild
            return 1, None

    feld = np.full((80, 120), 25, dtype=np.uint8)
    feld[30:50, 40:70] = 70

    erkenner_ = Erkenner()
    gesicht.kaesten(feld, erkenner_)
    assert erkenner_.bekommen.max() > feld.max(), "aufgehellt angekommen"

    roh = Erkenner()
    gesicht.kaesten(feld, roh, mit_ausgleich=False)
    assert roh.bekommen.max() == feld.max(), "abschaltbar, fuer den Vergleich"
