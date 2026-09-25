"""Die Folge-Aufnahme: was Spot beim Folgen sah, was er daraus machte, wie lange es dauerte.

Anlass (25.09.2026): der Folgelauf vom Vormittag hatte 191 Takte mit Ziel, einen
Takt-Median von 0.57 s und Lücken bis 100 s -- und die Aufzeichnung konnte nicht
sagen, WO die 0.57 s hingingen und WAS im Bild war. `ziel` steht je Takt im Lauf,
aber ohne Bild, ohne die verworfenen Kästen und ohne Zeiten je Schritt.
"""

import json
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from spotlab.workshop import folgeaufnahme as fa
from spotlab.workshop import folgen
from spotlab.workshop.folgen import Gesichtsaufnahme


def _uhr(schritt=0.01):
    stand = {"t": 0.0}

    def uhr():
        stand["t"] += schritt
        return stand["t"]

    return uhr


def _aufnahme(hoehe=40, breite=60, farbe=True, pano=None):
    form = (hoehe, breite, 3) if farbe else (hoehe, breite)
    feld = (np.arange(np.prod(form)) % 251).astype(np.uint8).reshape(form)
    punkte = np.array([[2.0, 0.1, 0.3], [2.5, -0.2, 0.4], [3.0, 0.0, -0.5]])
    return Gesichtsaufnahme(feld, pano or SimpleNamespace(), None, punkte, 15.0, gier=0.25)


def _zeilen(lauf_dir):
    datei = lauf_dir / fa.ORDNER / fa.INDEX
    return [json.loads(z) for z in datei.read_text(encoding="utf-8").splitlines() if z.strip()]


def test_ein_takt_mit_sicht_steht_als_zeile_mit_bild_und_tiefe(tmp_path):
    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr())
    aufnahme.takt_beginnt()
    nr = aufnahme.sicht(_aufnahme(), "koerper")
    aufnahme.befehl(0.3, 0.1, -15.0)
    aufnahme.takt_endet("folgt")
    bericht = aufnahme.schliessen()

    [zeile] = _zeilen(tmp_path)
    assert zeile["takt"] == 1 and zeile["zustand"] == "folgt"
    [sicht] = zeile["sichten"]
    assert nr == 0 and sicht["nr"] == 0 and sicht["finder"] == "koerper"
    assert sicht["nick_grad"] == pytest.approx(15.0) and sicht["gier"] == pytest.approx(0.25)
    assert (sicht["breite"], sicht["hoehe"]) == (60, 40)
    from PIL import Image

    with Image.open(tmp_path / fa.ORDNER / sicht["bild"]) as bild:
        assert bild.size == (60, 40) and bild.format == "JPEG"
    punkte = np.load(tmp_path / fa.ORDNER / sicht["tiefe"])["punkte"]
    assert punkte.shape == (3, 3)
    assert np.allclose(punkte, _aufnahme().punkte, atol=0.01), "float16 reicht auf den Zentimeter"
    assert zeile["befehl"]["vx"] == pytest.approx(0.3)
    assert zeile["befehl"]["wz_grad"] == pytest.approx(5.73, abs=0.01)
    assert bericht["takte"] == 1 and bericht["sichten"] == 1 and bericht["fehler"] == 0


def test_die_farbe_bleibt_farbe_und_grau_bleibt_grau(tmp_path):
    """Das Panorama ist RGB; ein vertauschter Kanal faellt im Video erst beim Hinsehen auf."""
    from PIL import Image

    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr())
    feld = np.zeros((32, 32, 3), dtype=np.uint8)
    feld[..., 0] = 220                                   # rot im RGB-Panorama
    aufnahme.takt_beginnt()
    aufnahme.sicht(Gesichtsaufnahme(feld, None, None, None, 0.0), "koerper")
    aufnahme.sicht(_aufnahme(farbe=False), "gesicht")
    aufnahme.takt_endet("sucht")
    aufnahme.schliessen()
    [zeile] = _zeilen(tmp_path)
    with Image.open(tmp_path / fa.ORDNER / zeile["sichten"][0]["bild"]) as bild:
        r, g, b = bild.convert("RGB").getpixel((16, 16))
    assert r > 180 and g < 60 and b < 60, "rot bleibt rot"
    assert zeile["sichten"][0]["tiefe"] is None, "ohne Punkte keine Tiefendatei"
    with Image.open(tmp_path / fa.ORDNER / zeile["sichten"][1]["bild"]) as bild:
        assert bild.mode == "L"


def test_die_zeiten_je_schritt_stehen_in_ihrer_reihenfolge(tmp_path):
    """Zweimal `kameras` in einem Takt heisst: zwei Bildabrufe -- das muss man SEHEN."""
    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr(0.05))
    aufnahme.takt_beginnt()
    with aufnahme.zeit("kameras"):
        pass
    with aufnahme.zeit("koerper"):
        pass
    with aufnahme.zeit("kameras"):
        pass
    aufnahme.zeit_eintragen("yunet", 0.085)
    aufnahme.takt_endet("sucht")
    aufnahme.schliessen()
    [zeile] = _zeilen(tmp_path)
    assert [name for name, _ in zeile["zeiten"]] == ["kameras", "koerper", "kameras", "yunet"]
    assert zeile["zeiten"][0][1] == pytest.approx(0.05)
    assert zeile["zeiten"][3][1] == pytest.approx(0.085)
    assert zeile["arbeit_s"] > 0


def test_eine_zeit_zaehlt_auch_wenn_der_schritt_wirft(tmp_path):
    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr(0.05))
    aufnahme.takt_beginnt()
    with pytest.raises(RuntimeError), aufnahme.zeit("kameras"):
        raise RuntimeError("WLAN weg")
    aufnahme.takt_endet("sucht")
    aufnahme.schliessen()
    assert _zeilen(tmp_path)[0]["zeiten"][0][0] == "kameras"


def test_koerper_gesichter_ziel_und_geste_stehen_mit_urteil_da(tmp_path):
    from spotlab.backends.real.gesicht import Befund
    from spotlab.backends.real.koerper import Koerper, Koerperbefund

    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr())
    aufnahme.takt_beginnt()
    nr = aufnahme.sicht(_aufnahme(), "koerper")
    k = Koerper(huefte=(30.0, 20.0), schulter=(30.0, 10.0), conf=0.9, kasten=(20.0, 5.0, 40.0, 35.0))
    b = Koerperbefund(2.0, 8.0, 0.9, "huefte", distance=1.8, height=0.3, grund="zu tief")
    lm = np.zeros((33, 3))
    aufnahme.koerper(nr, [k], [b], weg="suche", landmarken=[lm])
    kopf = Befund(1.0, 12.0, 0.8, (10.0, 5.0, 8.0, 9.0), distance=2.2, height=1.6, genommen=True)
    aufnahme.gesichter(nr, [kopf])
    ziel = folgen.Ziel(1.0, 2.2, "Gesicht auf 1.60 m", bild_oben=14.0, gier=0.25)
    aufnahme.ziel(ziel, folgen.Ziel(-3.0, 2.2, "Gesicht auf 1.60 m"), echt=True)
    aufnahme.geste("halt")
    aufnahme.befehl(0.0, 0.0, -15.0, schranke="nur 0.4 m frei voraus", angehalten=True)
    aufnahme.takt_endet("angehalten")
    aufnahme.schliessen()

    [zeile] = _zeilen(tmp_path)
    [kz] = zeile["koerper"]
    assert kz["sicht"] == 0 and kz["weg"] == "suche" and kz["grund"] == "zu tief"
    assert kz["genommen"] is False and kz["hoehe"] == pytest.approx(0.3)
    assert kz["huefte"] == [30.0, 20.0] and len(kz["landmarken"]) == 33
    [gz] = zeile["gesichter"]
    assert gz["genommen"] is True and gz["kasten"] == [10.0, 5.0, 8.0, 9.0] and gz["score"] == 0.8
    assert zeile["ziel"]["peilung"] == 1.0 and zeile["ziel"]["peilung_jetzt"] == -3.0
    assert zeile["ziel"]["echt"] is True and zeile["ziel"]["bild_oben"] == 14.0
    assert zeile["geste"] == "halt"
    assert zeile["befehl"]["schranke"] == "nur 0.4 m frei voraus"
    assert zeile["befehl"]["angehalten"] is True


def test_ein_langsamer_schreiber_haelt_den_takt_nicht_auf(tmp_path):
    """Die Aufnahme ist eine Beigabe: ein voller Schreiber verwirft BILDER, nie den Takt."""
    frei = threading.Event()
    geschrieben = []

    def haengt(pfad, feld):
        frei.wait(5.0)
        geschrieben.append(pfad)

    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr(), bild_schreiber=haengt, warteschlange=2)
    beginn = time.monotonic()
    for _ in range(6):
        aufnahme.takt_beginnt()
        aufnahme.sicht(_aufnahme(), "koerper")
        aufnahme.takt_endet("folgt")
    assert time.monotonic() - beginn < 1.0, "der Takt wartet nie auf die Platte"
    frei.set()
    bericht = aufnahme.schliessen()
    zeilen = _zeilen(tmp_path)
    assert len(zeilen) == 6, "jede Zeile kommt an, auch ohne Bild"
    verworfen = [z["sichten"][0] for z in zeilen if z["sichten"][0]["bild"] is None]
    assert verworfen and all("nicht nach" in s["grund"] for s in verworfen)
    assert bericht["verworfen"] == len(verworfen)


def test_ein_schreibfehler_wird_gezaehlt_nicht_geworfen(tmp_path):
    def kaputt(pfad, feld):
        raise OSError("Platte voll")

    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr(), bild_schreiber=kaputt)
    aufnahme.takt_beginnt()
    aufnahme.sicht(_aufnahme(), "koerper")
    aufnahme.takt_endet("folgt")
    bericht = aufnahme.schliessen()
    assert bericht["fehler"] == 1 and "Platte voll" in bericht["letzter_fehler"]
    assert len(_zeilen(tmp_path)) == 1


def test_ohne_aktive_aufnahme_tut_die_mitschrift_nichts():
    keine = fa.aktiv()
    with keine.zeit("kameras"):
        pass
    assert keine.sicht(_aufnahme(), "koerper") is None
    keine.koerper(0, [], [])
    keine.takt_endet("folgt")
    assert not keine


def test_aktiviert_gilt_nur_innerhalb(tmp_path):
    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr())
    with aufnahme.aktiviert():
        assert fa.aktiv() is aufnahme
    assert fa.aktiv() is not aufnahme
    aufnahme.schliessen()


def test_die_kameras_stehen_einmal_da_und_bauen_dasselbe_panorama(tmp_path):
    """Offline muss `winkel()` genau so rechnen wie im Lauf -- sonst sitzt jede
    Markierung im Video daneben. Also die Kalibrierung selbst, nicht ein Nachbau."""
    pytest.importorskip("bosdyn.api")
    from test_backend_panorama import _paar

    from spotlab.backends.real import panorama

    pano = panorama.Panorama(panorama.kalibrierung_aus(_paar(90)), zuschnitt=panorama.ALLES)
    aufnahme = fa.Folgeaufnahme(tmp_path, uhr=_uhr())
    for _ in range(2):
        aufnahme.takt_beginnt()
        aufnahme.sicht(_aufnahme(pano=pano), "koerper")
        aufnahme.takt_endet("sucht")
    aufnahme.schliessen()
    nachgebaut = fa.panorama_laden(tmp_path)
    assert (nachgebaut.breite, nachgebaut.hoehe) == (pano.breite, pano.hoehe)
    for spalte, zeile in ((0, 0), (pano.breite / 2, pano.hoehe / 3), (pano.breite - 1, pano.hoehe - 1)):
        assert nachgebaut.winkel(spalte, zeile) == pytest.approx(pano.winkel(spalte, zeile))
    assert nachgebaut.kamerahoehe(15.0) == pytest.approx(pano.kamerahoehe(15.0))


# ------------------------------------------------------------ Im Folgemodus


def _spot(neigt=True):
    from test_workshop_folgen import _Spot

    return _Spot(neigt=neigt)


def test_folge_mit_aufnahme_schreibt_je_takt_was_der_koerperfinder_sah(tmp_path):
    from test_workshop_folgen import _ein_koerper, _koerperaufnahme, _laeuft_takte

    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_ein_koerper()])
    spot = _spot()
    folgen.folge(spot, finder, melde=lambda _t: None, schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(3), lauf_dir=tmp_path, aufnahme=True)
    zeilen = _zeilen(tmp_path)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert len(zeilen) == 3 == len(fahrten)
    for zeile, fahrt in zip(zeilen, fahrten):
        assert zeile["zustand"] == "folgt"
        assert zeile["sichten"][0]["finder"] == "koerper"
        assert (tmp_path / fa.ORDNER / zeile["sichten"][0]["bild"]).is_file()
        [k] = zeile["koerper"]
        assert k["genommen"] is True and k["punkt"] == "huefte"
        assert zeile["ziel"]["echt"] is True and zeile["ziel"]["name"].startswith("Körper")
        assert zeile["befehl"]["nick_grad"] == pytest.approx(fahrt["nick_grad"])
        assert zeile["befehl"]["vx"] == pytest.approx(fahrt["vx"], abs=1e-3)
        namen = [name for name, _ in zeile["zeiten"]]
        assert "koerper" in namen and "koerper_probe" in namen and "walk" in namen


def test_der_eingebaute_erkenner_sagt_spur_oder_suche_und_gibt_das_skelett(tmp_path, monkeypatch):
    from test_workshop_folgen import _ein_koerper, _koerperaufnahme, _laeuft_takte

    from spotlab.backends.real import koerper as koerpermodul

    class _Erkenner:
        def __init__(self, *a, **kw):
            self.letzter_weg, self.letzte_landmarken = None, None

        def finde(self, feld):
            self.letzter_weg = "spur"
            self.letzte_landmarken = np.full((33, 3), 7.0)
            return [_ein_koerper()]

    monkeypatch.setattr(koerpermodul, "Koerpererkenner", _Erkenner)
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme)
    folgen.folge(_spot(), finder, melde=lambda _t: None, schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(1), lauf_dir=tmp_path, aufnahme=True)
    [k] = _zeilen(tmp_path)[0]["koerper"]
    assert k["weg"] == "spur" and k["landmarken"][0] == [7.0, 7.0, 7.0]


def test_ohne_ziel_steht_der_takt_als_sucht_da(tmp_path):
    from test_workshop_folgen import _koerperaufnahme, _laeuft_takte

    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme, koerper_holen=lambda feld: [])
    folgen.folge(_spot(), finder, melde=lambda _t: None, schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(2), lauf_dir=tmp_path, aufnahme=True)
    zeilen = _zeilen(tmp_path)
    assert [z["zustand"] for z in zeilen] == ["sucht", "sucht"]
    assert all(z["ziel"] is None and z["koerper"] == [] for z in zeilen)
    assert all(z["sichten"] for z in zeilen), "auch ein leeres Bild ist ein Befund"


def test_der_nachlauf_steht_als_nachlauf_da(tmp_path):
    from test_workshop_folgen import _laeuft_takte

    plan = iter([folgen.Ziel(0.0, 3.0, "Tag 1"), None, None])
    folgen.folge(_spot(), lambda _s: next(plan, None), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2), lauf_dir=tmp_path,
                 aufnahme=True, nachlauf_s=10.0)
    assert [z["zustand"] for z in _zeilen(tmp_path)] == ["folgt", "nachlauf"]
    assert _zeilen(tmp_path)[1]["ziel"]["echt"] is False


def test_eine_schranke_steht_im_befehl(tmp_path):
    from test_workshop_folgen import _laeuft_takte, _Spot

    spot = _Spot(frei=0.2, neigt=True)
    folgen.folge(spot, lambda _s: folgen.Ziel(0.0, 3.0, "Tag 1"), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(1), lauf_dir=tmp_path, aufnahme=True)
    [zeile] = _zeilen(tmp_path)
    assert zeile["befehl"]["vx"] == 0.0 and "frei voraus" in zeile["befehl"]["schranke"]
    assert "gitter" in [name for name, _ in zeile["zeiten"]]


def test_ohne_ablage_sagt_folge_es_bevor_sich_etwas_bewegt():
    from test_workshop_folgen import _laeuft_takte

    spot = _spot()
    with pytest.raises(ValueError, match="Aufnahme"):
        folgen.folge(spot, lambda _s: None, melde=lambda _t: None, schlaf=lambda _s: None,
                     laeuft=_laeuft_takte(1), aufnahme=True)
    assert spot.kommandos == []


def test_die_aufnahme_nimmt_den_lauf_des_schreibers(tmp_path):
    """Im Beispiel steht `lauf_dir=spot.recorder.dir` -- aber auch ohne: der Lauf ist bekannt."""
    from test_workshop_folgen import _laeuft_takte

    spot = _spot()
    spot.recorder = SimpleNamespace(dir=tmp_path, zeitmarke=_uhr(0.1), event=lambda *a, **k: None)
    folgen.folge(spot, lambda _s: None, melde=lambda _t: None, schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(2), aufnahme=True)
    zeilen = _zeilen(tmp_path)
    assert len(zeilen) == 2 and zeilen[1]["t"] > zeilen[0]["t"]


def test_ein_kaputter_schreiber_haelt_den_roboter_nicht_an_und_wird_einmal_gesagt(tmp_path):
    from test_workshop_folgen import _ein_koerper, _koerperaufnahme, _laeuft_takte

    def kaputt(pfad, feld):
        raise OSError("Platte voll")

    def lauf(aufnahme):
        finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                       koerper_holen=lambda feld: [_ein_koerper()])
        gemeldet, spot = [], _spot()
        folgen.folge(spot, finder, melde=gemeldet.append, schlaf=lambda _s: None,
                     laeuft=_laeuft_takte(3), lauf_dir=tmp_path, aufnahme=aufnahme)
        return spot.kommandos, gemeldet

    ohne, _ = lauf(None)
    mit, gemeldet = lauf(fa.Folgeaufnahme(tmp_path, bild_schreiber=kaputt))
    assert mit == ohne, "dieselben Befehle wie ganz ohne Aufnahme"
    assert len([m for m in gemeldet if "Platte voll" in m]) == 1
