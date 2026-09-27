"""Folgen per Klick: der eingewickelte Körperfinder nimmt am Anfang nur den Angeklickten."""

import math

import pytest

from spotlab.workshop import folgen
from spotlab.workshop import klickfolgen as kf
from spotlab.workshop.folgen import Ziel

LAGE = (1.0, 1.0, 0.0)            # Spot bei (1, 1), Nase nach +x


def _welt(peilung, abstand, lage=LAGE):
    x, y, gier = lage
    w = gier + math.radians(peilung)
    return x + abstand * math.cos(w), y + abstand * math.sin(w)


class _Innen:
    """Ein Körperfinder-Ersatz: sieht je Aufruf die nächste Liste und wählt wie der echte."""

    def __init__(self, *takte):
        self.takte = list(takte)
        self.hinweis = "Hinweis vom Körperfinder"

    def __call__(self, spot):
        kandidaten = self.takte.pop(0) if self.takte else []
        if not kandidaten:
            return None
        return folgen.waehle_ziel(kandidaten)

    def befund(self):
        return "2 Körper, 2 genommen"

    def letzte(self):
        return "sicht"


def _finder(innen, ziel, lage=LAGE, gesehen=None):
    return kf.KlickFinder(innen, ziel, lage_holen=lambda spot: lage, gesehen=gesehen)


def _in_folge(finder, wahl=lambda k: min(k, key=lambda z: z.distance) if k else None):
    """Wie `folge()`: der Merkpunkt wählt (hier: der nächste) -- der Finder läuft darunter."""
    marke = folgen._WAHL.set(wahl)
    try:
        return finder(object())
    finally:
        folgen._WAHL.reset(marke)


def test_von_zwei_menschen_nimmt_er_den_angeklickten():
    nah, fern = Ziel(0.0, 2.0), Ziel(40.0, 3.0)
    f = _finder(_Innen([nah, fern]), _welt(40.0, 3.0))
    assert _in_folge(f) is fern, "nicht der nächste, sondern der angeklickte"
    assert f.treffer == 1


def test_steht_keiner_beim_klick_nimmt_er_keinen_und_sagt_es():
    f = _finder(_Innen([Ziel(0.0, 2.0)]), _welt(60.0, 3.0))
    assert _in_folge(f) is None and f.treffer == 0
    assert "angeklickt" in f.befund()


def test_nach_zwei_treffern_entscheidet_der_merkpunkt():
    nah, fern = Ziel(0.0, 2.0), Ziel(40.0, 3.0)
    f = _finder(_Innen([nah, fern], [nah, fern], [nah, fern]), _welt(40.0, 3.0))
    assert _in_folge(f) is fern and _in_folge(f) is fern
    assert _in_folge(f) is nah, "ab dem dritten Takt wählt der Merkpunkt (hier: der nächste)"


def test_die_bezugsstelle_wandert_mit_dem_menschen():
    """Er geht 0.8 m je Takt weg -- nach zwei Takten 1.6 m vom Klick, aber je Takt nah genug."""
    klick = _welt(0.0, 2.0)
    f = _finder(_Innen([Ziel(0.0, 2.8)], [Ziel(0.0, 3.6)]), klick)
    assert _in_folge(f).distance == pytest.approx(2.8)
    assert _in_folge(f).distance == pytest.approx(3.6)


def test_ohne_lage_nimmt_er_am_anfang_keinen():
    f = kf.KlickFinder(_Innen([Ziel(0.0, 2.0)]), _welt(0.0, 2.0),
                       lage_holen=lambda spot: (_ for _ in ()).throw(RuntimeError("kein Baum")))
    assert _in_folge(f) is None


def test_ausserhalb_von_folge_waehlt_er_selbst():
    nah, fern = Ziel(0.0, 2.0), Ziel(40.0, 3.0)
    f = _finder(_Innen([nah, fern]), _welt(40.0, 3.0))
    assert f(object()) is fern


def test_hinweis_befund_und_sicht_kommen_vom_koerperfinder():
    f = _finder(_Innen(), (0.0, 0.0))
    assert f.hinweis == "Hinweis vom Körperfinder"
    assert f.letzte() == "sicht" and "2 Körper" in f.befund()


def test_was_er_sieht_geht_in_die_draufsicht():
    gemeldet = []
    nah, fern = Ziel(0.0, 2.0), Ziel(40.0, 3.0)
    f = _finder(_Innen([nah, fern]), _welt(40.0, 3.0),
                gesehen=lambda punkte, gewaehlt: gemeldet.append((punkte, gewaehlt)))
    _in_folge(f)
    [(punkte, gewaehlt)] = gemeldet
    assert [(round(x, 2), round(y, 2)) for x, y, *_ in punkte] == [
        (3.0, 1.0), tuple(round(v, 2) for v in _welt(40.0, 3.0))]
    assert gewaehlt == pytest.approx(_welt(40.0, 3.0))


def test_mit_dem_echten_merkpunkt_bleibt_er_beim_angeklickten():
    """Wie `folge()` je Takt: der Merkpunkt wählt, der Finder läuft darunter, das Ziel wird
    aufgenommen. Der Angeklickte steht weiter weg als der andere -- und bleibt es, auch
    nachdem der Finder nach zwei Treffern nur noch durchreicht."""
    from spotlab.workshop import merkpunkt

    def bei(x, y):
        return Ziel(math.degrees(math.atan2(y, x)), math.hypot(x, y), gier=0.0, ort=(0.0, 0.0))

    anderer, er = bei(2.0, 0.0), bei(3.0, 1.5)
    f = kf.KlickFinder(_Innen(*[[anderer, er]] * 5), (3.0, 1.5), lage_holen=lambda s: (0, 0, 0))
    merk = merkpunkt.Merkpunkt()
    for t in (0.0, 0.5, 1.0, 1.5, 2.0):
        ziel = _in_folge(f, wahl=lambda k, t=t: merk.waehle(t, k))
        assert ziel is er, f"bei t = {t}"
        merk.aufnehmen(t, ziel)
