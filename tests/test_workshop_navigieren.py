"""Der Kern der Navigation aus dem Karten-Tab: Karte, Verortung, Ziele aus `ziel.json`.

Ohne Roboter und ohne Qt: `spot` ist eine Attrappe mit `load_map`, `localize`,
`navigate_to` und `stop`; die Uhr ist eine Funktion, die statt zu schlafen
das Drehbuch weiterspielt (Ziele klicken, „Stopp" druecken). Was der Lauf der
GUI meldet, steht in `navigation.json` -- hier mitgeschrieben, Stand fuer Stand.
"""

from types import SimpleNamespace

import pytest

from spotlab.errors import NavigationError, NotLocalized, SpotlabError
from spotlab.record import navigation as datei
from spotlab.record.run import STOPP_DATEI
from spotlab.workshop import navigieren


class _Backend:
    def __init__(self):
        self.ortung = ("wp0", (0.5, 0.0, 90.0))

    def localization(self):
        return self.ortung


class _Spot:
    def __init__(self, klappt_ab=1, kaputt=(), unterwegs=None):
        self.backend = _Backend()
        self.protokoll = []
        self.klappt_ab = klappt_ab          # der wievielte localize()-Versuch klappt
        self.kaputt = set(kaputt)           # Ziele, die scheitern
        self.unterwegs = unterwegs          # Drehbuch waehrend einer Fahrt
        self._versuche = 0

    def load_map(self, karte):
        self.protokoll.append(("load_map", karte))
        return SimpleNamespace(name=karte or "aktiv")

    def localize(self):
        self._versuche += 1
        if self._versuche < self.klappt_ab:
            raise NotLocalized("kein Tag im Bild")
        self.protokoll.append("localize")
        return "wp0"

    def navigate_to(self, ziel, timeout=120.0, abbruch=None):
        self.protokoll.append(("navigate_to", ziel))
        if ziel in self.kaputt:
            raise NavigationError("Der Spot hat sich verloren.")
        for _ in range(3):                  # drei Nachsende-Takte
            if self.unterwegs is not None:
                self.unterwegs(ziel)
            if abbruch is not None and abbruch():
                self.protokoll.append(("abgebrochen", ziel))
                return False
        self.backend.ortung = (ziel, (0.0, 0.0, 0.0))
        return True

    def stop(self):
        self.protokoll.append("stop")


class _Drehbuch:
    """Statt zu schlafen: beim n-ten Warten auf ein Ziel etwas tun, am Ende „Stopp"."""

    def __init__(self, lauf_dir, stopp_nach=2, klicks=None, stopp_nach_verorten=None):
        self.lauf_dir = lauf_dir
        self.stopp_nach = stopp_nach                    # Wartetakte ohne Ziel bis „Stopp"
        self.klicks = klicks or {}                      # Wartetakt -> (wegpunkt, nr)
        self.stopp_nach_verorten = stopp_nach_verorten  # Verortungspausen bis „Stopp"
        self.pausen = []

    def __call__(self, dauer):
        self.pausen.append(dauer)
        warten = self.pausen.count(navigieren.TAKT_S)
        verorten = self.pausen.count(navigieren.VERORTEN_PAUSE_S)
        if dauer == navigieren.TAKT_S and warten in self.klicks:
            datei.schreibe_ziel(self.lauf_dir, *self.klicks[warten])
        if warten >= self.stopp_nach or (
                self.stopp_nach_verorten is not None and verorten >= self.stopp_nach_verorten):
            (self.lauf_dir / STOPP_DATEI).write_text("", encoding="utf-8")


@pytest.fixture
def staende(monkeypatch):
    gesehen = []
    original = datei.schreibe_stand

    def mitschreiben(lauf_dir, status, **felder):
        gesehen.append((status, felder.get("ziel"), felder.get("text", "")))
        return original(lauf_dir, status, **felder)

    monkeypatch.setattr(navigieren.datei, "schreibe_stand", mitschreiben)
    return gesehen


def _fahrten(spot):
    return [e for e in spot.protokoll if isinstance(e, tuple) and e[0] in ("navigate_to", "abgebrochen")]


def test_ohne_ziel_wartet_der_lauf_und_stopp_beendet_ihn(tmp_path, staende):
    spot = _Spot()
    drehbuch = _Drehbuch(tmp_path, stopp_nach=2)
    navigieren.navigiere(spot, tmp_path, karte="flur", schlaf=drehbuch)
    assert spot.protokoll == [("load_map", "flur"), "localize", "stop"]
    assert [s[0] for s in staende] == ["lade_karte", "bereit", "beendet"]
    assert drehbuch.pausen == [navigieren.TAKT_S] * 2, "gewartet, nicht gedreht"
    stand = datei.lies_stand(tmp_path)
    assert stand["status"] == "beendet" and stand["karte"] == "flur"
    assert stand["standort"] == "wp0" and stand["versatz"] == [0.5, 0.0, 90.0]


def test_die_verortung_wird_wiederholt_bis_sie_klappt(tmp_path, staende):
    spot = _Spot(klappt_ab=3)
    drehbuch = _Drehbuch(tmp_path, stopp_nach=1)
    navigieren.navigiere(spot, tmp_path, schlaf=drehbuch)
    assert spot._versuche == 3 and "localize" in spot.protokoll
    verorte = [s for s in staende if s[0] == "verorte"]
    assert len(verorte) == 2 and "kein Tag" in verorte[0][2]
    assert drehbuch.pausen[:2] == [navigieren.VERORTEN_PAUSE_S] * 2


def test_stopp_waehrend_der_verortung_beendet_ohne_fahrt(tmp_path, staende):
    spot = _Spot(klappt_ab=99)
    navigieren.navigiere(spot, tmp_path, schlaf=_Drehbuch(tmp_path, stopp_nach_verorten=2))
    assert _fahrten(spot) == [] and "localize" not in spot.protokoll
    assert staende[-1][0] == "beendet"


def test_ein_ziel_wird_gefahren_und_gemeldet(tmp_path, staende):
    spot = _Spot()
    datei.schreibe_ziel(tmp_path, "wp3", 1)
    navigieren.navigiere(spot, tmp_path, schlaf=_Drehbuch(tmp_path, stopp_nach=1))
    assert _fahrten(spot) == [("navigate_to", "wp3")]
    assert ("unterwegs", "wp3", "") in staende and ("angekommen", "wp3", "") in staende
    assert datei.lies_stand(tmp_path)["standort"] == "wp3", "die Lage kommt vom Backend"


def test_dasselbe_ziel_faehrt_nicht_zweimal_eine_neue_nummer_schon(tmp_path, staende):
    spot = _Spot()
    datei.schreibe_ziel(tmp_path, "wp3", 1)
    drehbuch = _Drehbuch(tmp_path, stopp_nach=3, klicks={1: ("wp3", 2)})   # noch einmal geklickt
    navigieren.navigiere(spot, tmp_path, schlaf=drehbuch)
    assert _fahrten(spot) == [("navigate_to", "wp3"), ("navigate_to", "wp3")]


def test_ein_neues_ziel_bricht_die_fahrt_ab_und_faehrt_das_neue(tmp_path, staende):
    def unterwegs(ziel):
        if ziel == "wp1":
            datei.schreibe_ziel(tmp_path, "wp2", 2)     # Klick waehrend der Fahrt

    spot = _Spot(unterwegs=unterwegs)
    datei.schreibe_ziel(tmp_path, "wp1", 1)
    navigieren.navigiere(spot, tmp_path, schlaf=_Drehbuch(tmp_path, stopp_nach=1))
    assert _fahrten(spot) == [("navigate_to", "wp1"), ("abgebrochen", "wp1"), ("navigate_to", "wp2")]
    assert ("angekommen", "wp2", "") in staende
    assert not any(s[0] == "angekommen" and s[1] == "wp1" for s in staende)
    assert any(s[0] == "bereit" and "Neues Ziel" in s[2] for s in staende)


def test_ein_gescheitertes_ziel_beendet_den_lauf_nicht(tmp_path, staende):
    spot = _Spot(kaputt={"kaputt"})
    datei.schreibe_ziel(tmp_path, "kaputt", 1)
    drehbuch = _Drehbuch(tmp_path, stopp_nach=3, klicks={1: ("wp2", 2)})
    navigieren.navigiere(spot, tmp_path, schlaf=drehbuch)
    gescheitert = [s for s in staende if s[0] == "gescheitert"]
    assert len(gescheitert) == 1 and gescheitert[0][1] == "kaputt" and "verloren" in gescheitert[0][2]
    assert _fahrten(spot) == [("navigate_to", "kaputt"), ("navigate_to", "wp2")]
    assert ("angekommen", "wp2", "") in staende


def test_stopp_waehrend_der_fahrt_haelt_an(tmp_path, staende):
    def unterwegs(_ziel):
        (tmp_path / STOPP_DATEI).write_text("", encoding="utf-8")

    spot = _Spot(unterwegs=unterwegs)
    datei.schreibe_ziel(tmp_path, "wp1", 1)
    navigieren.navigiere(spot, tmp_path, schlaf=_Drehbuch(tmp_path))
    assert _fahrten(spot) == [("navigate_to", "wp1"), ("abgebrochen", "wp1")]
    assert spot.protokoll[-1] == "stop" and staende[-1][0] == "beendet"
    assert not any(s[0] == "angekommen" for s in staende)


def test_die_stoppdatei_ist_der_vorgabe_schalter(tmp_path, staende):
    spot = _Spot()
    (tmp_path / STOPP_DATEI).write_text("", encoding="utf-8")
    navigieren.navigiere(spot, tmp_path, schlaf=lambda _s: None)
    assert "localize" not in spot.protokoll and staende[-1][0] == "beendet"


def test_ein_kartenfehler_wird_gemeldet_und_weitergereicht(tmp_path, staende):
    class _Ohne(_Spot):
        def load_map(self, karte):
            raise SpotlabError("Es ist keine Karte ausgewählt.")

    with pytest.raises(SpotlabError, match="keine Karte"):
        navigieren.navigiere(_Ohne(), tmp_path, laeuft=lambda: True)
    assert staende[-1][0] == "gescheitert" and "keine Karte" in staende[-1][2]


def test_ohne_ortung_im_backend_bleibt_der_stand_ohne_lage(tmp_path):
    spot = _Spot()

    def kaputt():
        raise RuntimeError("weg")

    spot.backend.localization = kaputt
    navigieren.navigiere(spot, tmp_path, schlaf=_Drehbuch(tmp_path, stopp_nach=1))
    stand = datei.lies_stand(tmp_path)
    assert stand["status"] == "beendet" and stand["standort"] is None and stand["versatz"] is None


def test_karte_aus_der_umgebung():
    assert navigieren.karte_aus_umgebung({"SPOTLAB_KARTE": "flur"}) == "flur"
    assert navigieren.karte_aus_umgebung({"SPOTLAB_KARTE": ""}) is None
    assert navigieren.karte_aus_umgebung({}) is None
