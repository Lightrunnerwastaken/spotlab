"""Das Programm der Steuerzentrale: Wahrnehmung, Tasten, Klickfahrt, Licht und Ton."""

import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from test_workshop_folgen import _baum

from spotlab.backends.base import Capability, ObstacleGrid, Tag
from spotlab.errors import SpotlabError
from spotlab.record import fahrt
from spotlab.record import zentrale as protokoll
from spotlab.workshop import zentrale
from tests_zeitgrenzen import TEST_TIMEOUT_S, warte_bis

T0 = 1000.0


def _gitter_um(x, y, frei=1.0, halb=1.92, zelle=0.03):
    n = int(round(2 * halb / zelle))
    return ObstacleGrid(cells=np.full((n, n), frei), cell_size=zelle, origin=(x - halb, y - halb),
                        time=0.0, known=np.ones((n, n), bool))


class _Spot:
    def __init__(self, gitter="frei", tags=(), licht=False):
        self.kommandos = []
        self._pose = (1.0, 1.0, 0.0)
        self._gitter = gitter
        self._tags = list(tags)
        self._licht = licht
        self.backend = SimpleNamespace(
            capabilities=lambda: Capability.LOCOMOTION | Capability.LOCAL_GRID,
            frame_tree_snapshot=lambda: _baum(*self._pose),
        )

    def obstacles(self):
        if isinstance(self._gitter, Exception):
            raise self._gitter
        return _gitter_um(*self._pose[:2]) if self._gitter == "frei" else self._gitter

    def tags(self):
        return list(self._tags)

    def supports(self, merkmal):
        return self._licht if merkmal in ("lights", "beep") else False

    def walk(self, **kw):
        self.kommandos.append(kw)

    def stop(self):
        self.kommandos.append("stop")

    def beep(self, **kw):
        self.kommandos.append("beep")


class _Licht:
    def __init__(self, protokoll_):
        self.protokoll = protokoll_
        self.fehler = 0
        self.letzter_fehler = None

    def setze(self, farbe):
        self.protokoll.append(("licht", farbe))

    def aus(self):
        self.protokoll.append("licht aus")


def _zentrale(spot, tmp_path, **kw):
    kw.setdefault("jetzt", lambda: T0)
    kw.setdefault("melde", lambda _t: None)
    return zentrale.Zentrale(spot, tmp_path, **kw)


def _fahrten(spot):
    return [k for k in spot.kommandos if isinstance(k, dict)]


# ------------------------------------------------------------ Lagebild


def test_die_wahrnehmung_schreibt_das_lagebild_mit_allen_plaetzen(tmp_path):
    tag = Tag(name="Tag 3", kind="apriltag", bearing=0.0, distance=2.0, world_xy=(3.0, 1.0),
              time=0.0, id=3, filtered=True)
    z = _zentrale(_Spot(tags=[tag]), tmp_path)
    z.wahrnehmen()
    bild = protokoll.lies_lagebild(tmp_path)
    assert (tmp_path / protokoll.LAGEBILD_BILD).exists()
    assert bild["rahmen"] == "vision" and bild["zelle_m"] == pytest.approx(0.05)
    assert bild["breite"] > 0 and bild["hoehe"] > 0 and len(bild["ursprung"]) == 2
    assert bild["spot"]["x"] == pytest.approx(1.0) and bild["spot"]["gier_grad"] == pytest.approx(0.0)
    assert bild["tags"] == [{"id": 3, "x": 3.0, "y": 1.0}]
    assert bild["klickfahrt"]["zustand"] == "keine"
    assert bild["faehigkeiten"] == {"licht": False, "ton": False, "kamera": False}
    assert bild["menschen"] == [] and bild["karte"] is None


def test_ein_tag_bleibt_gemerkt_wenn_er_aus_dem_blick_ist(tmp_path):
    tag = Tag(name="Tag 3", kind="apriltag", bearing=0.0, distance=2.0, world_xy=(3.0, 1.0),
              time=0.0, id=3, filtered=True)
    spot = _Spot(tags=[tag])
    z = _zentrale(spot, tmp_path)
    z.wahrnehmen()
    spot._tags = []
    z.wahrnehmen()
    assert protokoll.lies_lagebild(tmp_path)["tags"] == [{"id": 3, "x": 3.0, "y": 1.0}]


def test_ohne_gitter_gibt_es_kein_bild_und_es_wird_einmal_gesagt(tmp_path):
    gesagt = []
    z = _zentrale(_Spot(gitter=SpotlabError("kein Raum")), tmp_path, melde=gesagt.append)
    z.wahrnehmen()
    z.wahrnehmen()
    bild = protokoll.lies_lagebild(tmp_path)
    assert bild["breite"] == 0 and not (tmp_path / protokoll.LAGEBILD_BILD).exists()
    assert len([m for m in gesagt if "Hindernisgitter" in m]) == 1


# ------------------------------------------------------------ Fahren


def test_eine_taste_faehrt_und_bricht_die_klickfahrt_ab(tmp_path):
    spot = _Spot()
    z = _zentrale(spot, tmp_path)
    z.wahrnehmen()
    protokoll.schreibe_klickziel(tmp_path, 1, (2.0, 1.0), "normal", jetzt=lambda: T0)
    z.takt()
    assert z.klick.unterwegs
    fahrt.schreibe(tmp_path, 0.4, 0.0, 0.0, jetzt=lambda: T0)
    z.takt()
    assert _fahrten(spot)[-1]["vx"] == pytest.approx(0.4)
    assert z.klick.stand.zustand == "abgebrochen" and "Taste" in z.klick.stand.grund


def test_ein_klick_geradeaus_geht_los(tmp_path):
    spot = _Spot()
    z = _zentrale(spot, tmp_path)
    z.wahrnehmen()
    protokoll.schreibe_klickziel(tmp_path, 1, (2.5, 1.0), "normal", jetzt=lambda: T0)
    z.takt()
    [fahrt_] = _fahrten(spot)
    assert fahrt_["vx"] > 0.0 and fahrt_["stop"] is False


def test_ein_klick_seitlich_dreht_erst(tmp_path):
    spot = _Spot()
    z = _zentrale(spot, tmp_path)
    z.wahrnehmen()
    protokoll.schreibe_klickziel(tmp_path, 1, (1.0, 2.5), "normal", jetzt=lambda: T0)
    z.takt()
    [fahrt_] = _fahrten(spot)
    assert fahrt_["vx"] == 0.0 and fahrt_["wz"] > 0.0


def test_ohne_lebenszeichen_steht_er(tmp_path):
    spot = _Spot()
    uhr = {"t": T0}
    z = _zentrale(spot, tmp_path, jetzt=lambda: uhr["t"])
    z.wahrnehmen()
    protokoll.schreibe_klickziel(tmp_path, 1, (2.5, 1.0), "normal", jetzt=lambda: T0)
    z.takt()
    uhr["t"] = T0 + protokoll.TOTMANN_S + 0.1
    z.takt()
    assert spot.kommandos[-1] == "stop"
    assert z.klick.stand.zustand == "abgebrochen" and "Lebenszeichen" in z.klick.stand.grund


def test_ein_halb_geschriebenes_klickziel_bricht_die_fahrt_nicht_ab(tmp_path):
    """Unter Windows liest der Takt die Datei manchmal genau beim Ersetzen: dann gilt das
    zuletzt gelesene Klickziel weiter -- und dessen Lebenszeichen altert trotzdem."""
    spot = _Spot()
    uhr = {"t": T0}
    z = _zentrale(spot, tmp_path, jetzt=lambda: uhr["t"])
    z.wahrnehmen()
    protokoll.schreibe_klickziel(tmp_path, 1, (2.5, 1.0), "normal", jetzt=lambda: T0)
    z.takt()
    (tmp_path / protokoll.KLICKZIEL).write_text("{halb", encoding="utf-8")
    uhr["t"] = T0 + 0.2
    z.takt()
    assert z.klick.unterwegs, z.klick.stand
    assert _fahrten(spot)[-1]["vx"] > 0.0
    uhr["t"] = T0 + protokoll.TOTMANN_S + 0.1
    z.takt()
    assert z.klick.stand.zustand == "abgebrochen", "ohne neues Lebenszeichen hält er trotzdem"


def test_ein_klick_in_unbekanntes_wird_abgelehnt(tmp_path):
    spot = _Spot()
    z = _zentrale(spot, tmp_path)
    z.wahrnehmen()
    protokoll.schreibe_klickziel(tmp_path, 1, (4.5, 1.0), "normal", jetzt=lambda: T0)
    z.takt()
    assert z.klick.stand.zustand == "abgelehnt" and "unbekannt" in z.klick.stand.grund
    assert not _fahrten(spot)


def test_ein_klick_ohne_ziel_bricht_ab(tmp_path):
    z = _zentrale(_Spot(), tmp_path)
    z.wahrnehmen()
    protokoll.schreibe_klickziel(tmp_path, 1, (2.5, 1.0), "normal", jetzt=lambda: T0)
    z.takt()
    protokoll.schreibe_klickziel(tmp_path, 2, None, "normal", jetzt=lambda: T0)
    z.takt()
    assert z.klick.stand.zustand == "abgebrochen"


# ------------------------------------------------------------ Licht und Ton


def test_licht_ohne_av_dienst_wird_einmal_gesagt(tmp_path):
    gesagt = []
    z = _zentrale(_Spot(licht=False), tmp_path, melde=gesagt.append)
    protokoll.schreibe_aktion(tmp_path, 1, "licht", "gruen")
    z.takt()
    protokoll.schreibe_aktion(tmp_path, 2, "licht", "rot")
    z.takt()
    assert len([m for m in gesagt if "Licht" in m]) == 1


def test_licht_und_ton_je_nummer_einmal(tmp_path):
    spot = _Spot(licht=True)
    z = _zentrale(spot, tmp_path, licht=_Licht(spot.kommandos), hintergrund=lambda f: f())
    protokoll.schreibe_aktion(tmp_path, 1, "licht", "gruen")
    z.takt()
    z.takt()
    protokoll.schreibe_aktion(tmp_path, 2, "ton")
    z.takt()
    protokoll.schreibe_aktion(tmp_path, 3, "licht", "aus")
    z.takt()
    assert spot.kommandos == [("licht", "green"), "beep", "licht aus"]


def test_am_ende_erst_anhalten_dann_licht_aus(tmp_path):
    spot = _Spot(licht=True)
    z = _zentrale(spot, tmp_path, licht=_Licht(spot.kommandos))
    runden = {"n": 0}

    def laeuft():
        runden["n"] += 1
        return runden["n"] <= 2

    z.lauf(laeuft, schlaf=lambda _s: None, mit_blick=False)
    assert spot.kommandos[-2:] == ["stop", "licht aus"]


# ------------------------------------------------------------ Menschensuche (Teil 2)


class _KameraSpot(_Spot):
    """Ein Spot mit Bild- und Tiefenkameras -- nur dann gibt es eine Menschensuche."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.backend.capabilities = lambda: (Capability.LOCOMOTION | Capability.LOCAL_GRID
                                             | Capability.CAMERAS)


class _Suche:
    """Eine Such-Attrappe: gibt je Runde die nächste Liste aus `runden` zurück."""

    def __init__(self, *runden):
        self.runden = list(runden)
        self.gefragt = []

    def runde(self, stufe, t):
        self.gefragt.append((stufe, t))
        if not self.runden:
            return [], {}
        return self.runden.pop(0)


def _mensch(x, y, t=T0, quelle="vorne"):
    from spotlab.workshop.menschensuche import Mensch

    return Mensch(x, y, 2.0, 0.0, quelle, t)


def _stufe(z, tmp_path, stufe, nummer=1):
    protokoll.schreibe_aktion(tmp_path, nummer, "suche", stufe=stufe)
    z.takt()


def test_die_suche_ist_aus_bis_der_tab_eine_stufe_schickt(tmp_path):
    suche = _Suche(([_mensch(2.0, 1.0)], {}))
    z = _zentrale(_KameraSpot(), tmp_path, suche=suche)
    z.suchen(T0)
    z.wahrnehmen()
    assert suche.gefragt == []
    bild = protokoll.lies_lagebild(tmp_path)
    assert bild["suche"]["stufe"] == "aus" and bild["suche"]["kann"] is True
    assert bild["menschen"] == []


def test_eine_stufe_kommt_ueber_die_aktion_und_die_menschen_ins_lagebild(tmp_path):
    suche = _Suche(([_mensch(2.0, 1.0)], {}))
    z = _zentrale(_KameraSpot(), tmp_path, suche=suche)
    _stufe(z, tmp_path, "normal")
    z.suchen(T0)
    z.wahrnehmen(T0 + 0.5)
    assert suche.gefragt == [("normal", T0)]
    bild = protokoll.lies_lagebild(tmp_path)
    assert bild["menschen"] == [{"x": 2.0, "y": 1.0, "alter_s": 0.5, "quelle": "vorne",
                                 "gefolgt": False}]
    assert bild["suche"]["stufe"] == "normal" and bild["suche"]["grund"] is None


def test_die_rundenzeit_steht_im_lagebild(tmp_path):
    uhr = {"t": T0}

    class _Langsam(_Suche):
        def runde(self, stufe, t):
            uhr["t"] += 0.8                  # die Runde dauert 0.8 s
            return [], {}

    z = _zentrale(_KameraSpot(), tmp_path, suche=_Langsam(), jetzt=lambda: uhr["t"])
    _stufe(z, tmp_path, "rundum")
    z.suchen()
    z.wahrnehmen(T0 + 1.0)
    assert protokoll.lies_lagebild(tmp_path)["suche"]["runde_s"] == pytest.approx(0.8)


def test_ein_mensch_verblasst_und_ist_nach_drei_sekunden_weg(tmp_path):
    z = _zentrale(_KameraSpot(), tmp_path, suche=_Suche(([_mensch(2.0, 1.0)], {}), ([], {})))
    _stufe(z, tmp_path, "normal")
    z.suchen(T0)
    z.suchen(T0 + 2.0)                     # nichts gefunden: der alte bleibt, blasser
    z.wahrnehmen(T0 + 2.0)
    assert protokoll.lies_lagebild(tmp_path)["menschen"][0]["alter_s"] == pytest.approx(2.0)
    z.wahrnehmen(T0 + 3.5)
    assert protokoll.lies_lagebild(tmp_path)["menschen"] == []


def test_ein_neuer_fund_ersetzt_den_alten_in_der_naehe(tmp_path):
    z = _zentrale(_KameraSpot(), tmp_path, suche=_Suche(
        ([_mensch(2.0, 1.0), _mensch(6.0, 1.0)], {}),
        ([_mensch(2.4, 1.1, t=T0 + 0.5)], {})))
    _stufe(z, tmp_path, "normal")
    z.suchen(T0)
    z.suchen(T0 + 0.5)
    z.wahrnehmen(T0 + 0.5)
    orte = sorted((m["x"], m["y"]) for m in protokoll.lies_lagebild(tmp_path)["menschen"])
    assert orte == [(2.4, 1.1), (6.0, 1.0)], "derselbe Mensch einmal, der ferne bleibt"


def test_ohne_kameras_ist_die_suche_grau_und_sagt_warum(tmp_path):
    suche = _Suche(([_mensch(2.0, 1.0)], {}))
    z = _zentrale(_Spot(), tmp_path, suche=suche)
    _stufe(z, tmp_path, "normal")
    z.suchen(T0)
    z.wahrnehmen()
    stand = protokoll.lies_lagebild(tmp_path)["suche"]
    assert suche.gefragt == [] and stand["kann"] is False and "kamera" in stand["grund"].lower()


def test_der_grund_einer_quelle_steht_im_lagebild(tmp_path):
    z = _zentrale(_KameraSpot(), tmp_path,
                  suche=_Suche(([_mensch(2.0, 1.0)], {"hinten": "RuntimeError: Kamera weg"})))
    _stufe(z, tmp_path, "rundum")
    z.suchen(T0)
    z.wahrnehmen()
    bild = protokoll.lies_lagebild(tmp_path)
    assert "hinten" in bild["suche"]["grund"] and len(bild["menschen"]) == 1


def test_eine_stolpernde_suche_haelt_die_zentrale_nicht_an(tmp_path):
    class _Kaputt:
        def runde(self, stufe, t):
            raise RuntimeError("Modell fehlt")

    gesagt = []
    z = _zentrale(_KameraSpot(), tmp_path, suche=_Kaputt(), melde=gesagt.append)
    _stufe(z, tmp_path, "normal")
    z.suchen(T0)
    z.suchen(T0 + 1)
    z.wahrnehmen()
    assert "Modell fehlt" in protokoll.lies_lagebild(tmp_path)["suche"]["grund"]
    assert len([m for m in gesagt if "Modell fehlt" in m]) == 1


def test_die_pause_nach_einer_runde(tmp_path):
    from spotlab.workshop import menschensuche

    z = _zentrale(_KameraSpot(), tmp_path, suche=_Suche())
    assert z.suchen(T0) == zentrale.SUCHE_LEERLAUF_S
    _stufe(z, tmp_path, "sparsam")
    assert z.suchen(T0) == menschensuche.SPARSAM_PAUSE_S
    _stufe(z, tmp_path, "normal", nummer=2)
    assert z.suchen(T0) == 0.0


def test_im_lauf_sucht_ein_eigener_faden(tmp_path):
    suche = _Suche(*[([_mensch(2.0, 1.0)], {})] * 50)
    z = _zentrale(_KameraSpot(), tmp_path, suche=suche)
    protokoll.schreibe_aktion(tmp_path, 1, "suche", stufe="normal")
    ende = time.monotonic() + TEST_TIMEOUT_S

    def laeuft():
        return not suche.gefragt and time.monotonic() < ende

    z.lauf(laeuft, schlaf=lambda _s: time.sleep(0.01), mit_blick=False)
    assert suche.gefragt, "der Suchfaden hat gesucht, während der Fahrtakt lief"


# ------------------------------------------------------------ Hauptprogramm


def test_die_argumente():
    assert zentrale.argumente(["--runs", "X", "--uebernehmen"]) == ("X", True)
    assert zentrale.argumente([]) == (None, False)
    with pytest.raises(SpotlabError):
        zentrale.argumente(["--los"])
    with pytest.raises(SpotlabError):
        zentrale.argumente(["--runs"])


# ------------------------------------------------------------ Kette im Übungsraum


def test_im_2d_uebungsraum_geht_spot_per_klick_durch_die_tuer(tmp_path):
    """Raum „durchgang“: Start (1, 2), Wand bei x = 4.5 mit Tür von y = 1.5 bis 2.4. Zur Tür,
    hindurch (die Skizze merkt sich das Zimmer drüben), zurück -- und dann ein Klick auf eine
    schon gesehene Stelle hinter der Wand: die Gerade dorthin geht durch die Wand, der Weg
    durch die Tür."""
    import spotlab

    with spotlab.connect(backend="sim", raum="durchgang", runs_dir=tmp_path) as spot:
        spot.power_on()
        spot.stand()
        lauf_dir = spot.recorder.dir
        z = zentrale.Zentrale(spot, lauf_dir, melde=lambda _t: None)
        halt = threading.Event()
        faden = threading.Thread(target=z.lauf, args=(lambda: not halt.is_set(),),
                                 kwargs={"mit_blick": False}, daemon=True)
        faden.start()
        try:
            warte_bis(lambda: protokoll.lies_lagebild(lauf_dir), "das erste Lagebild")
            # Das letzte Ziel: von (3.8, 1.95) nach (5.1, 3.0) kreuzt die Gerade x = 4.5 bei
            # y = 2.5 -- in der Wand über der Tür. Gesehen wurde es von (5.2, 2.0) aus.
            wege = {}
            ziele = [(2.6, 2.0), (4.0, 1.95), (5.2, 2.0), (3.8, 1.95), (5.1, 3.0)]
            for nummer, ziel in enumerate(ziele, start=1):
                def herzschlag(nummer=nummer, ziel=ziel):
                    protokoll.schreibe_klickziel(lauf_dir, nummer, ziel, "schnell")

                def stand(nummer=nummer):
                    bild = protokoll.lies_lagebild(lauf_dir) or {}
                    k = bild.get("klickfahrt") or {}
                    if k.get("nummer") != nummer:
                        return None
                    wege[nummer] = max(wege.get(nummer, 0), len(k.get("weg") or []))
                    return k if k.get("zustand") != "unterwegs" else None

                ergebnis = warte_bis(stand, f"Klick {nummer} nach {ziel} ist zu Ende",
                                     zwischendurch=herzschlag, takt_s=0.1)
                assert ergebnis["zustand"] == "angekommen", ergebnis
            assert wege[5] >= 2, f"hinter die Wand ging es über einen Zwischenpunkt ({wege})"
        finally:
            halt.set()
            faden.join(timeout=10)
    ereignisse = (lauf_dir / "ereignisse.jsonl").read_text(encoding="utf-8")
    assert '"angestossen"' not in ereignisse
