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


# ------------------------------------------------------------ Puls der Oberfläche


def _runden(n):
    """laeuft() für höchstens n Runden -- das Netz, falls die Zentrale selbst nicht endet."""
    zaehler = {"n": 0}

    def laeuft():
        zaehler["n"] += 1
        return zaehler["n"] <= n

    return laeuft, zaehler


def test_ist_die_gui_weg_endet_die_zentrale_von_selbst(tmp_path):
    # Befund 09.10.2026: die GUI stürzte ab, die Zentrale hielt den echten Spot stehend weiter.
    import json

    from spotlab.record.run import RunRecorder

    spot = _Spot()
    spot.recorder = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    gesagt = []
    z = _zentrale(spot, spot.recorder.dir, melde=gesagt.append)
    protokoll.schreibe_gui_puls(spot.recorder.dir, jetzt=lambda: T0 - protokoll.GUI_FRIST_S - 1)
    laeuft, zaehler = _runden(50)
    z.lauf(laeuft, schlaf=lambda _s: None, mit_blick=False)
    assert zaehler["n"] == 1, "die Zentrale lief trotz totem Puls weiter"
    assert spot.kommandos[-1] == "stop"
    assert any("Oberfläche" in text for text in gesagt), gesagt
    zeilen = (spot.recorder.dir / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(zeile)["art"] == "gui_weg" for zeile in zeilen)


def test_das_echte_programm_setzt_spot_hin_wenn_die_gui_weg_ist(tmp_path):
    """Die ganze Kette als eigener Prozess im 2D-Übungsraum: ein toter Puls, und das Programm
    endet selbst -- hält an, setzt Spot hin, baut ab. Ohne GUI und ohne Stopp-Datei."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    import spotlab

    quelle = str(Path(spotlab.__file__).resolve().parents[1])
    env = dict(os.environ, SPOTLAB_BACKEND="sim", SPOTLAB_RAUM="durchgang", SPOTLAB_NUR_TROCKEN="1",
               PYTHONUTF8="1",               # wie der Startweg der GUI (gui/launcher.py)
               PYTHONPATH=os.pathsep.join([quelle] + [os.environ.get("PYTHONPATH", "")]))
    prozess = subprocess.Popen(
        [sys.executable, "-m", "spotlab.workshop.zentrale", "--runs", str(tmp_path)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        errors="replace")
    try:
        lauf = warte_bis(lambda: next((p for p in tmp_path.iterdir() if p.is_dir()), None)
                         if prozess.poll() is None else "tot", "das Lauf-Verzeichnis")
        assert lauf != "tot", prozess.communicate()[0][-3000:]
        warte_bis(lambda: (lauf / protokoll.LAGEBILD).exists() or prozess.poll() is not None,
                  "das erste Lagebild")
        assert prozess.poll() is None, prozess.communicate()[0][-3000:]
        protokoll.schreibe_gui_puls(lauf, jetzt=lambda: time.time() - protokoll.GUI_FRIST_S - 5)
        ausgabe, _ = prozess.communicate(timeout=TEST_TIMEOUT_S)
    finally:
        if prozess.poll() is None:
            prozess.kill()
            prozess.communicate()
    assert prozess.returncode == 0, ausgabe[-3000:]
    assert "Oberfläche" in ausgabe, ausgabe[-3000:]
    ereignisse = [json.loads(z) for z in (lauf / "ereignisse.jsonl").read_text(
        encoding="utf-8").splitlines()]
    arten = [(e["art"], e["daten"].get("name")) for e in ereignisse]
    weg = arten.index(("gui_weg", None))
    assert ("kommando", "sit") in arten[weg:], arten[weg:]
    assert json.loads((lauf / "lauf.json").read_text(encoding="utf-8"))["ergebnis"] == "ok"


@pytest.mark.parametrize("puls_alter", [None, protokoll.GUI_FRIST_S - 1])
def test_ein_frischer_oder_fehlender_puls_haelt_die_zentrale_nicht_an(tmp_path, puls_alter):
    spot = _Spot()
    z = _zentrale(spot, tmp_path)
    if puls_alter is not None:
        protokoll.schreibe_gui_puls(tmp_path, jetzt=lambda: T0 - puls_alter)
    laeuft, zaehler = _runden(3)
    z.lauf(laeuft, schlaf=lambda _s: None, mit_blick=False)
    assert zaehler["n"] == 4                     # drei Runden, dann sagte laeuft() nein


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


# ------------------------------------------------------------ Folgen per Klick (Teil 2)


class _Folge:
    """Ersatz für `folgen.folge`: ruft `laeuft()` wie der echte Takt; `je_takt(n)` darf
    zwischendurch Dateien schreiben oder die Uhr stellen."""

    def __init__(self, je_takt=None, takte=50):
        self.je_takt = je_takt or (lambda n, kw: None)
        self.takte = takte
        self.kw = None
        self.n = 0

    def __call__(self, spot, **kw):
        self.kw = kw
        while self.n < self.takte and kw["laeuft"]():
            self.n += 1
            self.je_takt(self.n, kw)
        spot.stop()


def _menschklick(tmp_path, nummer=1, ziel=(3.0, 1.0), uhr=None):
    protokoll.schreibe_klickziel(tmp_path, nummer, ziel, "normal", art="mensch",
                                 jetzt=(lambda: uhr["t"]) if uhr else (lambda: T0))


def _folgende(tmp_path, folge, uhr=None, **kw):
    uhr = uhr if uhr is not None else {"t": T0}
    kw.setdefault("koerper_finder", lambda: (lambda spot: None))
    z = _zentrale(_KameraSpot(), tmp_path, suche=_Suche(), folgen_mit=folge,
                  jetzt=lambda: uhr["t"], **kw)
    return z, uhr


def test_ein_klick_auf_einen_menschen_uebergibt_an_den_folgemodus(tmp_path):
    gesehen = {}

    def je_takt(n, kw):
        z.wahrnehmen()
        gesehen["stand"] = protokoll.lies_lagebild(tmp_path)["klickfahrt"]
        gesehen["suche"] = z.suchen()

    folge = _Folge(je_takt, takte=1)
    z, _ = _folgende(tmp_path, folge)
    _stufe(z, tmp_path, "normal")
    _menschklick(tmp_path)
    z.takt()
    assert folge.kw is not None, "der Folgemodus hat übernommen"
    assert gesehen["stand"]["zustand"] == "folgt" and gesehen["stand"]["nummer"] == 1
    assert gesehen["suche"] == zentrale.SUCHE_LEERLAUF_S, "die Suche pausiert beim Folgen"
    assert z.klick.stand.zustand == "abgebrochen" and not z._folgt


def test_eine_taste_beendet_das_folgen_und_faehrt_danach(tmp_path):
    def je_takt(n, kw):
        if n == 2:
            fahrt.schreibe(tmp_path, 0.4, 0.0, 0.0, jetzt=lambda: T0)

    z, _ = _folgende(tmp_path, _Folge(je_takt))
    spot = z.spot
    _menschklick(tmp_path)
    z.takt()
    assert "Taste" in z.klick.stand.grund
    z.takt()
    assert _fahrten(spot)[-1]["vx"] == pytest.approx(0.4)


def test_ein_neuer_klick_beendet_das_folgen(tmp_path):
    def je_takt(n, kw):
        if n == 2:
            protokoll.schreibe_klickziel(tmp_path, 2, (2.0, 1.0), "normal", jetzt=lambda: T0)

    folge = _Folge(je_takt)
    z, _ = _folgende(tmp_path, folge)
    z.wahrnehmen()
    _menschklick(tmp_path)
    z.takt()
    assert folge.n == 2 and "Klick" in z.klick.stand.grund
    z.takt()
    assert z.klick.stand.nummer == 2 and z.klick.unterwegs, "der neue Klick fährt"


def test_ohne_lebenszeichen_endet_das_folgen(tmp_path):
    def je_takt(n, kw):
        if n == 2:
            uhr["t"] = T0 + protokoll.TOTMANN_S + 0.1

    uhr = {"t": T0}
    folge = _Folge(je_takt)
    z, _ = _folgende(tmp_path, folge, uhr=uhr)
    _menschklick(tmp_path, uhr=uhr)
    z.takt()
    assert folge.n == 2 and "Lebenszeichen" in z.klick.stand.grund


def test_stopp_beendet_das_folgen(tmp_path):
    halt = {"an": False}

    def je_takt(n, kw):
        halt["an"] = n >= 3

    folge = _Folge(je_takt)
    z, _ = _folgende(tmp_path, folge)
    z._laeuft = lambda: not halt["an"]
    _menschklick(tmp_path)
    z.takt()
    assert folge.n == 3 and "Stopp" in z.klick.stand.grund


def test_wer_nicht_zu_finden_ist_wird_nicht_ewig_gesucht(tmp_path):
    def je_takt(n, kw):
        uhr["t"] += 1.0
        _menschklick(tmp_path, uhr=uhr)         # der Tab lebt

    uhr = {"t": T0}
    folge = _Folge(je_takt)
    z, _ = _folgende(tmp_path, folge, uhr=uhr)
    _menschklick(tmp_path, uhr=uhr)
    z.takt()
    assert folge.n < 50 and "nicht zu finden" in z.klick.stand.grund


def test_der_gefolgte_steht_hervorgehoben_im_lagebild(tmp_path):
    from spotlab.workshop.folgen import Ziel, waehle_ziel

    def innen(spot):
        return waehle_ziel([Ziel(0.0, 2.0), Ziel(90.0, 2.0)])

    def je_takt(n, kw):
        kw["finder"](z.spot)
        z.wahrnehmen()

    z, _ = _folgende(tmp_path, _Folge(je_takt, takte=1), koerper_finder=lambda: innen)
    _menschklick(tmp_path, ziel=(3.0, 1.0))      # Spot bei (1, 1): 2 m voraus
    z.takt()
    menschen = protokoll.lies_lagebild(tmp_path)["menschen"]
    gefolgt = [(m["x"], m["y"]) for m in menschen if m["gefolgt"]]
    andere = [(m["x"], m["y"]) for m in menschen if not m["gefolgt"]]
    assert gefolgt == [(3.0, 1.0)] and andere == [(1.0, 3.0)]


def test_nach_dem_folgen_kommt_die_gewaehlte_lichtfarbe_zurueck(tmp_path):
    spot = _KameraSpot(licht=True)
    folge = _Folge(lambda n, kw: kw["licht"].aus(), takte=1)
    z = _zentrale(spot, tmp_path, suche=_Suche(), folgen_mit=folge, licht=_Licht(spot.kommandos),
                  koerper_finder=lambda: (lambda s: None))
    protokoll.schreibe_aktion(tmp_path, 1, "licht", "gruen")
    z.takt()
    _menschklick(tmp_path)
    z.takt()
    licht = [k for k in spot.kommandos if k != "stop"]
    assert licht == [("licht", "green"), "licht aus", ("licht", "green")]


def test_ohne_kameras_wird_ein_menschenklick_abgelehnt(tmp_path):
    folge = _Folge()
    z = _zentrale(_Spot(), tmp_path, folgen_mit=folge)
    _menschklick(tmp_path)
    z.takt()
    assert folge.kw is None and z.klick.stand.zustand == "abgelehnt"
    assert "kamera" in z.klick.stand.grund.lower()


# ------------------------------------------------------------ Karten (Teil 3)


class _Karten:
    """Eine Kartenarbeit-Attrappe: merkt sich Aufträge, Beobachtungen und das Ende."""

    def __init__(self, kommandos=None, abgleich=None):
        self.auftraege = []
        self.beobachtet = []
        self.kommandos = kommandos if kommandos is not None else []
        self._abgleich = abgleich

    def auftrag(self, nummer, was, name=None):
        self.auftraege.append((nummer, was, name))

    def beobachte(self, t):
        self.beobachtet.append(t)

    def abgleiche(self, skizze, spot_xy, t):
        return self._abgleich

    def daten(self, t, abgleich):
        return {"name": "flur2", "zustand": "verortet",
                "raster": None if abgleich is None else {"breite": abgleich.breite}}

    def beenden(self):
        self.kommandos.append("karte beenden")


def test_ein_kartenauftrag_kommt_bei_der_kartenarbeit_an(tmp_path):
    karten = _Karten()
    z = _zentrale(_Spot(), tmp_path, kartenarbeit=karten)
    protokoll.schreibe_kartenauftrag(tmp_path, 1, "laden", name="flur2")
    z.takt()
    assert karten.auftraege[0] == (1, "laden", "flur2")


def test_das_lagebild_traegt_die_karte_und_ihr_bild(tmp_path):
    import numpy as np

    from spotlab.workshop import kartenabgleich, skizze

    s = skizze.Skizze()
    abgleich = kartenabgleich.abgleich(s, np.array([[1.0, 1.0], [1.5, 1.0]]), (1.0, 1.0), T0)
    karten = _Karten(abgleich=abgleich)
    z = _zentrale(_Spot(), tmp_path, kartenarbeit=karten)
    z.wahrnehmen(T0)
    bild = protokoll.lies_lagebild(tmp_path)
    assert karten.beobachtet == [T0]
    assert bild["karte"] == {"name": "flur2", "zustand": "verortet",
                             "raster": {"breite": abgleich.breite}}
    assert (tmp_path / protokoll.LAGEBILD_KARTE).is_file()


def test_ohne_abgleich_gibt_es_kein_kartenbild(tmp_path):
    z = _zentrale(_Spot(), tmp_path, kartenarbeit=_Karten())
    z.wahrnehmen(T0)
    assert protokoll.lies_lagebild(tmp_path)["karte"]["raster"] is None
    assert not (tmp_path / protokoll.LAGEBILD_KARTE).exists()


def test_am_ende_wird_die_karte_erst_nach_dem_anhalten_gespeichert(tmp_path):
    spot = _Spot()
    z = _zentrale(spot, tmp_path, kartenarbeit=_Karten(kommandos=spot.kommandos))
    runden = {"n": 0}

    def laeuft():
        runden["n"] += 1
        return runden["n"] <= 2

    z.lauf(laeuft, schlaf=lambda _s: None, mit_blick=False)
    assert spot.kommandos.index("stop") < spot.kommandos.index("karte beenden")


def test_ein_kartenauftrag_kommt_auch_waehrend_des_folgens_an(tmp_path):
    karten = _Karten()

    def je_takt(n, kw):
        if n == 1:
            protokoll.schreibe_kartenauftrag(tmp_path, 7, "wegpunkt", name="Tür")

    z, _ = _folgende(tmp_path, _Folge(je_takt, takte=3), kartenarbeit=karten)
    _menschklick(tmp_path)
    z.takt()
    assert (7, "wegpunkt", "Tür") in karten.auftraege


# ------------------------------------------------------------ Hauptprogramm


def test_die_argumente():
    assert zentrale.argumente(["--runs", "X", "--uebernehmen"]) == ("X", True, None)
    assert zentrale.argumente([]) == (None, False, None)
    assert zentrale.argumente(["--arbeitsordner", "W", "--runs", "X"]) == ("X", False, "W")
    with pytest.raises(SpotlabError):
        zentrale.argumente(["--arbeitsordner"])
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


# ------------------------------------------------------------ Flüssiger (27.09.2026)


def test_das_lagebild_traegt_den_versatz_von_odom_nach_vision(tmp_path):
    """Der Tab zeichnet Spot 10-mal je Sekunde aus `zustand.jsonl` (odom). Mit dem Versatz aus
    DEMSELBEN Rahmenbaum wie die Lage in „vision“ landet er in der Skizze am richtigen Ort."""
    import math

    from bosdyn.client.frame_helpers import BODY_FRAME_NAME, ODOM_FRAME_NAME, get_a_tform_b
    from test_workshop_folgen import _auseinander

    spot = _auseinander(0.6)
    z = _zentrale(spot, tmp_path)
    z.wahrnehmen()
    bild = protokoll.lies_lagebild(tmp_path)
    tx, ty, dg = bild["vision_von_odom"]
    odom = get_a_tform_b(spot.backend.frame_tree_snapshot(), ODOM_FRAME_NAME, BODY_FRAME_NAME)
    x = tx + math.cos(dg) * odom.x - math.sin(dg) * odom.y
    y = ty + math.sin(dg) * odom.x + math.cos(dg) * odom.y
    assert (x, y) == pytest.approx((bild["spot"]["x"], bild["spot"]["y"]), abs=1e-3)
    assert abs(ty) == pytest.approx(0.6, abs=1e-6), "die Rahmen liegen 0.6 m quer auseinander"


def test_ohne_odom_im_rahmenbaum_gibt_es_keinen_versatz(tmp_path):
    z = _zentrale(_Spot(), tmp_path)
    z.wahrnehmen()
    assert protokoll.lies_lagebild(tmp_path)["vision_von_odom"] is None


def test_die_wahrnehmung_wartet_nur_den_rest_ihres_takts():
    assert zentrale.wahrnehmungs_pause(0.03) == pytest.approx(zentrale.WAHRNEHMUNG_S - 0.03)
    assert zentrale.wahrnehmungs_pause(0.4) == zentrale.WAHRNEHMUNG_MIN_S, \
        "ein langsames Gitter (3D-Übungsraum) bekommt nur die Mindestpause"
    assert zentrale.WAHRNEHMUNG_S <= 0.25
