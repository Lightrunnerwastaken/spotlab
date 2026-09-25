"""Das Video und der Kurzbericht zur Folge-Aufnahme (`workshop/folgenfilm.py`).

Das Video läuft in ECHTZEIT: jedes Bild steht, bis das nächste kam. Ein Film, der
jedes Bild gleich lang zeigt, verschwiege genau das Stocken, das er zeigen soll.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from spotlab.workshop import folgeaufnahme as fa
from spotlab.workshop import folgen, folgenfilm
from spotlab.workshop.folgen import Gesichtsaufnahme


class _Uhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _feld(hoehe=90, breite=160):
    feld = np.zeros((hoehe, breite, 3), dtype=np.uint8)
    feld[..., 1] = 90
    return feld


def _aufnahme_schreiben(lauf_dir, takte=4, takt_s=0.5):
    """Eine kleine Aufnahme: Takt 1-2 Koerper genommen, Takt 3 Nachlauf, Takt 4 sucht."""
    from spotlab.backends.real.koerper import Koerper, Koerperbefund

    uhr = _Uhr()
    aufnahme = fa.Folgeaufnahme(lauf_dir, uhr=uhr)
    for n in range(takte):
        uhr.t = 10.0 + n * takt_s
        aufnahme.takt_beginnt()
        punkte = np.array([[2.0, 0.0, 0.2]] * 10)
        nr = aufnahme.sicht(Gesichtsaufnahme(_feld(), None, None, punkte, 15.0, gier=0.0), "koerper")
        with aufnahme.zeit("kameras"):
            uhr.t += 0.2
        with aufnahme.zeit("koerper"):
            uhr.t += 0.06
        if n < 2:
            k = Koerper(huefte=(80.0, 60.0), schulter=(80.0, 30.0), conf=0.9, kasten=(60.0, 10.0, 100.0, 85.0))
            b = Koerperbefund(1.0, 5.0, 0.9, "huefte", distance=1.9, height=0.9, genommen=True)
            aufnahme.koerper(nr, [k], [b], weg="spur" if n else "suche")
            ziel = folgen.Ziel(1.0, 1.9, "Körper, Hüfte auf 0.90 m", bild_oben=12.0, gier=0.0)
            aufnahme.ziel(ziel, ziel, echt=True)
            aufnahme.befehl(0.2, 0.02, -15.0)
            aufnahme.takt_endet("folgt")
        elif n == 2:
            ziel = folgen.Ziel(1.0, 1.9, "Körper, Hüfte auf 0.90 m")
            aufnahme.ziel(ziel, ziel, echt=False)
            aufnahme.befehl(0.2, 0.0, -15.0, schranke="nur 0.4 m frei voraus")
            aufnahme.takt_endet("nachlauf")
        else:
            aufnahme.befehl(0.0, 0.0, -15.0)
            aufnahme.takt_endet("sucht")
    aufnahme.schliessen()


class _Sammler:
    """Statt ffmpeg: die Bilder in einer Liste."""

    def __init__(self):
        self.bilder = []

    def __call__(self, pfad, fps):
        self.fps = fps
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def append_data(self, bild):
        self.bilder.append(np.asarray(bild))


def test_ohne_aufnahme_sagt_der_film_was_zu_tun_ist(tmp_path):
    with pytest.raises(Exception, match="folgen_aufnahme"):
        folgenfilm.takte_laden(tmp_path)


def test_der_film_laeuft_in_echtzeit_und_haelt_jedes_bild_bis_zum_naechsten(tmp_path):
    _aufnahme_schreiben(tmp_path)
    sammler = _Sammler()
    ergebnis = folgenfilm.film(tmp_path, fps=10, breite=320, gesicht=False, schreiber=sammler)
    # vier Takte zu 0.5 s ab t=10.0, der letzte endet bei 11.5 + 0.26 Arbeit
    assert ergebnis["bilder"] == len(sammler.bilder)
    assert 17 <= len(sammler.bilder) <= 19, "rund 1.8 s bei 10 Bildern je Sekunde"
    hoehe, breite, kanaele = sammler.bilder[0].shape
    assert breite == 320 and hoehe % 2 == 0 and kanaele == 3, "gerade Masse fuer libx264"
    assert all(b.shape == sammler.bilder[0].shape for b in sammler.bilder)
    assert not np.array_equal(sammler.bilder[0], sammler.bilder[-1]), "der Zustand aendert sich"


def test_ein_takt_ueber_eine_sekunde_sprengt_den_balken_nicht(tmp_path):
    """Lauf 20260925T125326Z: ein Takt mit 1.1 s Arbeit, der Balken lief ueber seinen
    Rand, und PIL brach das ganze Video ab (x1 < x0)."""
    uhr = _Uhr()
    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=uhr)
    uhr.t = 1.0
    aufnahme.takt_beginnt()
    aufnahme.sicht(Gesichtsaufnahme(_feld(), None, None, None, 15.0), "koerper")
    for name in ("kameras", "koerper", "yunet", "walk"):
        aufnahme.zeit_eintragen(name, 0.4)
    uhr.t = 2.6
    aufnahme.takt_endet("sucht")
    aufnahme.schliessen()
    sammler = _Sammler()
    folgenfilm.film(tmp_path, fps=5, breite=320, gesicht=False, schreiber=sammler)
    assert sammler.bilder


def test_der_zeitplan_zeigt_das_letzte_bild_vor_jedem_zeitpunkt():
    takte = [{"t": 0.0, "arbeit_s": 0.3, "sichten": [{"nr": 0, "t": 0.1, "bild": "a.jpg"}]},
             {"t": 1.0, "arbeit_s": 0.3, "sichten": []},
             {"t": 1.5, "arbeit_s": 0.3, "sichten": [{"nr": 0, "t": 1.6, "bild": "b.jpg"}]}]
    plan = folgenfilm.zeitplan(takte, fps=5)
    zeiten = [t for t, _, _ in plan]
    assert zeiten[0] == pytest.approx(0.0) and zeiten[-1] <= 1.8 + 1e-9
    bei = {round(t, 1): (takt, sicht) for t, takt, sicht in plan}
    assert bei[0.0] == (0, None), "vor dem ersten Bild gibt es keins"
    assert bei[0.2] == (0, (0, 0))
    assert bei[1.2] == (1, (0, 0)), "Takt 1 ohne Bild: das alte bleibt stehen"
    assert bei[1.6] == (2, (2, 0))


def test_der_bericht_sagt_wohin_die_zeit_geht_und_wie_oft_er_folgte(tmp_path):
    _aufnahme_schreiben(tmp_path)
    takte, quelle = folgenfilm.takte_laden(tmp_path)
    assert quelle == "aufnahme"
    text = folgenfilm.bericht(takte)
    assert "4 Takte" in text
    assert "kameras" in text and "200 ms" in text
    assert "folgt 50 %" in text and "nachlauf 25 %" in text and "sucht 25 %" in text
    assert "Spur 1" in text and "Suche 1" in text
    assert "frei voraus" in text, "die bremsende Schranke wird gezaehlt"


def test_der_bericht_zaehlt_zwei_bildabrufe_in_einem_takt():
    takte = [{"t": 0.0, "arbeit_s": 0.6, "zustand": "folgt", "sichten": [{}, {}],
              "zeiten": [["kameras", 0.2], ["koerper", 0.06], ["kameras", 0.2], ["yunet", 0.08]],
              "koerper": [], "gesichter": [], "ziel": None, "befehl": None}]
    assert "Zwei Bildabrufe in einem Takt: 1" in folgenfilm.bericht(takte)


def test_ein_alter_lauf_ohne_aufnahme_kommt_aus_den_ereignissen(tmp_path):
    """Vor der Aufnahme gab es nur `ziel` und `kein_ziel`: Leiste und Zeitstrahl gehen, Bilder nicht."""
    zeilen = [
        {"t": 5.0, "art": "ziel", "daten": {"finder": "Körper, Hüfte auf 0.90 m", "peilung": 3.0,
                                            "peilung_jetzt": 1.0, "abstand": 1.9, "bild_oben": 12.0,
                                            "echt": True, "vx": 0.2, "wz_grad": 1.0, "takt_s": 0.55,
                                            "gesperrt": False}},
        {"t": 5.6, "art": "ziel", "daten": {"finder": "Gesicht auf 1.60 m", "peilung": 2.0,
                                            "peilung_jetzt": 2.0, "abstand": 2.5, "bild_oben": None,
                                            "echt": False, "vx": 0.3, "wz_grad": 0.0, "takt_s": 0.6,
                                            "gesperrt": False}},
        {"t": 6.2, "art": "ziel", "daten": {"finder": None, "weg": True}},
        {"t": 11.0, "art": "kein_ziel", "daten": {"seit_s": 5.1, "je_gesehen": True, "befund": "x"}},
    ]
    (tmp_path / "ereignisse.jsonl").write_text(
        "\n".join(json.dumps(z, ensure_ascii=False) for z in zeilen) + "\n", encoding="utf-8")
    takte, quelle = folgenfilm.takte_laden(tmp_path)
    assert quelle == "ereignisse"
    assert [t["zustand"] for t in takte] == ["folgt", "nachlauf", "sucht"]
    assert takte[0]["ziel"]["abstand"] == 1.9 and takte[0]["befehl"]["vx"] == 0.2
    assert takte[2]["ziel"] is None
    sammler = _Sammler()
    folgenfilm.film(tmp_path, fps=5, breite=320, gesicht=False, schreiber=sammler)
    assert len(sammler.bilder) >= 5


def test_offline_sucht_das_gesicht_dort_wo_der_koerper_lief(tmp_path):
    """Die Staffel fragt das Gesicht nur, wenn der Koerper nichts fand. Offline laeuft
    es auf JEDER Koerper-Sicht -- so sieht man, wann es auch getragen haette."""
    _aufnahme_schreiben(tmp_path)
    takte, _ = folgenfilm.takte_laden(tmp_path)

    class _Pano:
        breite, hoehe = 160, 90

        def winkel(self, spalte, zeile):
            # Kastenmitte (80.5, 25) liegt mit 15 Grad Nick genau auf den Punkten (2 m, +5.7 Grad).
            return (80.0 - spalte) / 4.0, (25.0 - zeile) / 4.0 - 9.3

        def kamerahoehe(self, blick_grad=0.0):
            return 0.5

    gesehen = []

    def kaesten(feld, erkenner_):
        gesehen.append(feld.shape)
        return [(76.0, 20.0, 9.0, 10.0, 0.8)]

    anzahl = folgenfilm.gesicht_offline(tmp_path, takte, _Pano(), erkenner_=object(),
                                        kaesten_holen=kaesten)
    assert anzahl == 4 and len(gesehen) == 4
    assert gesehen[0] == (90, 160, 3), "das gespeicherte Panorama, in Farbe"
    for takt in takte:
        [g] = takt["gesichter_offline"]
        assert g["sicht"] == 0 and g["kasten"] == [76.0, 20.0, 9.0, 10.0]
        assert g["abstand"] is not None, "mit der gespeicherten Tiefe gegengeprueft"
    assert "offline" in folgenfilm.bericht(takte)


def test_ohne_opencv_oder_modell_laeuft_der_film_ohne_offline_gesicht(tmp_path, monkeypatch):
    _aufnahme_schreiben(tmp_path, takte=2)

    def kein_modell(*a, **kw):
        from spotlab.errors import SpotlabError

        raise SpotlabError("YuNet fehlt")

    monkeypatch.setattr(folgenfilm, "_gesichtserkenner", kein_modell)
    monkeypatch.setattr(fa, "panorama_laden", lambda lauf: SimpleNamespace(breite=160, hoehe=90))
    meldungen = []
    folgenfilm.film(tmp_path, fps=5, breite=320, schreiber=_Sammler(), melde=meldungen.append)
    assert any("YuNet fehlt" in m for m in meldungen)


@pytest.mark.skipif(folgenfilm._imageio() is None, reason="imageio mit ffmpeg fehlt")
def test_der_echte_film_ist_eine_mp4_datei(tmp_path):
    _aufnahme_schreiben(tmp_path, takte=2)
    ergebnis = folgenfilm.film(tmp_path, fps=5, breite=320, gesicht=False)
    assert ergebnis["pfad"] == tmp_path / folgenfilm.DATEI
    assert ergebnis["pfad"].stat().st_size > 1000
    assert (tmp_path / folgenfilm.BERICHT).is_file(), "der Bericht liegt neben dem Video"


# ------------------------------------ Eine Aufnahme fuer beide Finder, YOLOX (25.09.2026)


def test_eine_geteilte_sicht_zaehlt_fuer_das_gesicht_und_bekommt_kein_offline_gesicht(tmp_path):
    """Seit die Staffel die Bilder teilt, heisst eine Sicht `koerper+gesicht`: das
    Gesicht lief darauf schon im Lauf, offline waere es doppelt."""
    uhr = _Uhr()
    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=uhr)
    bild = Gesichtsaufnahme(_feld(), None, None, np.array([[2.0, 0.0, 0.2]] * 10), 15.0)
    aufnahme.takt_beginnt()
    aufnahme.sicht(bild, "koerper")
    aufnahme.sicht(bild, "gesicht")
    aufnahme.zeit_eintragen("bilder", 0.09)
    aufnahme.takt_endet("sucht")
    aufnahme.schliessen()
    takte, _ = folgenfilm.takte_laden(tmp_path)
    gezaehlt = []
    anzahl = folgenfilm.gesicht_offline(tmp_path, takte, object(), erkenner_=object(),
                                        kaesten_holen=lambda feld, e: gezaehlt.append(1) or [])
    assert anzahl == 0 and not gezaehlt
    text = folgenfilm.bericht(takte)
    assert "Gesicht (im Lauf): 1 Sichten" in text
    assert "Zwei Bildabrufe" not in text


def test_der_bericht_nennt_die_suchwege_samt_yolox():
    takte = [{"t": float(i), "arbeit_s": 0.3, "zustand": "folgt", "zeiten": [], "sichten": [],
              "gesichter": [], "ziel": None, "befehl": None,
              "koerper": [{"weg": w, "genommen": True, "grund": None, "sicht": 0}]}
             for i, w in enumerate(["yolox", "spur", "spur", "yolox-kasten"])]
    text = folgenfilm.bericht(takte)
    assert "Spur 2" in text and "YOLOX 1" in text and "YOLOX ohne Skelett 1" in text


def test_zwei_abrufe_zaehlen_auch_mit_dem_neuen_namen():
    takte = [{"t": 0.0, "arbeit_s": 0.6, "zustand": "sucht", "sichten": [{}, {}],
              "zeiten": [["bilder", 0.09], ["bilder", 0.09]], "koerper": [], "gesichter": [],
              "ziel": None, "befehl": None}]
    assert "Zwei Bildabrufe in einem Takt: 1" in folgenfilm.bericht(takte)
