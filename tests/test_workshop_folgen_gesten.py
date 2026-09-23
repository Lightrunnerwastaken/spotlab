"""Gesten im Folgemodus: die offene Hand haelt Spot an, der Daumen hoch laesst ihn weiter.

Der Gestenleser (`folgen.gesten_leser`) haengt am KOERPER-Finder: er liest die Hand
im Rumpf-Ausschnitt des Menschen, dem Spot folgt -- nur dort ist sie gross genug
(gemessen am 16.09.2026: auf dem ganzen Panorama null Haende, im Rumpf-Ausschnitt 31),
und nur dort ist die Frage sinnvoll. Eine Geste nimmt und gibt nur, was das Folgen
ohnehin erlaubt: sie ist kein Fahrbefehl, und jede Schranke gilt weiter.
"""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_workshop_folgen import (
    _ein_koerper,
    _koerperaufnahme,
    _laeuft_takte,
    _Spot,
    _uhr,
)

from spotlab.backends.real import gesten
from spotlab.errors import SpotlabError
from spotlab.workshop import folgen
from spotlab.workshop.folgen import Ziel
from tests_zeitgrenzen import TEST_TIMEOUT_S

# --------------------------------------------------------- Die Sicht des Finders


def test_der_koerperfinder_merkt_sich_was_er_zuletzt_sah():
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_ein_koerper()])
    assert finder.letzte() is None, "vor dem ersten Takt nichts"
    finder(_Spot())
    sicht = finder.letzte()
    assert sicht.nummer == 1
    assert sicht.koerper.schulter == (620.0, 250.0)
    assert sicht.aufnahme.feld.shape == (782, 1239)
    finder(_Spot())
    assert finder.letzte().nummer == 2, "jeder Takt zaehlt, damit niemand ein altes Bild zweimal liest"


def test_ohne_genommenen_koerper_gibt_es_keine_sicht():
    """Ein verworfener Koerper (Kistenhoehe) ist kein Mensch, dem Spot folgt --
    seine Hand zaehlt nicht. Und ein alter Koerper darf nicht stehen bleiben."""
    plan = iter([[_ein_koerper()], [], [_ein_koerper(huefte_zeile=450.0)]])
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: next(plan))
    finder(_Spot())
    assert finder.letzte() is not None
    finder(_Spot())
    assert finder.letzte() is None, "kein Koerper: keine Sicht"


def test_die_staffel_reicht_die_sicht_des_koerperfinders_weiter():
    koerper = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                    koerper_holen=lambda feld: [_ein_koerper()])
    staffel = folgen.zuerst(folgen.tag_finder(), koerper)
    assert staffel.letzte() is None
    staffel(_Spot())
    assert staffel.letzte() is not None and staffel.letzte().nummer == 1


def test_eine_staffel_ohne_koerperfinder_hat_keine_sicht():
    staffel = folgen.zuerst(folgen.tag_finder(), folgen.personen_finder())
    staffel(_Spot())
    assert staffel.letzte() is None


# ------------------------------------------------------------ Der Gestenleser


def _leser_mit(finder, gesten_plan, jeder=1, takte=3, gesehen=None):
    """Ein Gestenleser mit Attrappe: `gesten_plan` liefert je Lesung die Hand-Liste."""
    plan = iter(gesten_plan)

    def haende_holen(feld, ausschnitt):
        if gesehen is not None:
            gesehen.append(ausschnitt)
        return next(plan, [])

    return folgen.gesten_leser(finder, haende_holen=haende_holen, jeder=jeder, takte=takte)


def _offene_hand(conf=0.9):
    from test_backend_gesten import _hand

    return gesten.Hand(_hand(), conf, (0.0, 0.0, 1.0, 1.0))


def _daumen_hoch(conf=0.9):
    from test_backend_gesten import _hand

    return gesten.Hand(_hand((False, False, False, False), daumen="hoch"), conf, (0.0, 0.0, 1.0, 1.0))


def test_der_leser_liest_im_rumpf_ausschnitt_des_gefolgten_koerpers():
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_ein_koerper()])
    gesehen = []
    lies = _leser_mit(finder, [[_offene_hand()]] * 3, gesehen=gesehen)
    spot = _Spot()
    for _ in range(3):
        finder(spot)
        lies(spot)
    erwartet = gesten.rumpf_ausschnitt(_ein_koerper(), breite=1239, hoehe=782)
    assert gesehen == [erwartet] * 3


def test_eine_gehaltene_offene_hand_heisst_halt_und_zwar_einmal():
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_ein_koerper()])
    lies = _leser_mit(finder, [[_offene_hand()]] * 5, takte=3)
    spot = _Spot()
    gelesen = []
    for _ in range(5):
        finder(spot)
        gelesen.append(lies(spot))
    assert gelesen == [None, None, "halt", None, None]


def test_ohne_koerper_liest_er_nichts_und_die_zaehlung_faellt_zurueck():
    plan = iter([[_ein_koerper()], [_ein_koerper()], [], [_ein_koerper()], [_ein_koerper()], [_ein_koerper()]])
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: next(plan))
    gesehen = []
    lies = _leser_mit(finder, [[_offene_hand()]] * 6, gesehen=gesehen)
    spot = _Spot()
    gelesen = []
    for _ in range(6):
        finder(spot)
        gelesen.append(lies(spot))
    assert len(gesehen) == 5, "im Takt ohne Koerper wird nicht gelesen"
    assert gelesen == [None, None, None, None, None, "halt"], "der Aussetzer setzt zurueck"


def test_ein_altes_bild_wird_nicht_zweimal_gelesen():
    """Der Finder lief nicht (die Staffel fand vorher ein Tag): dieselbe Sicht
    darf die Entprellung nicht vorantreiben."""
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_ein_koerper()])
    gesehen = []
    lies = _leser_mit(finder, [[_offene_hand()]] * 6, gesehen=gesehen)
    spot = _Spot()
    finder(spot)
    assert [lies(spot), lies(spot), lies(spot)] == [None, None, None]
    assert len(gesehen) == 1


def test_jeder_dritte_takt_reicht_und_die_uebersprungenen_zaehlen_nicht():
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_ein_koerper()])
    gesehen = []
    lies = _leser_mit(finder, [[_offene_hand()]] * 9, jeder=3, takte=3, gesehen=gesehen)
    spot = _Spot()
    gelesen = []
    for _ in range(9):
        finder(spot)
        gelesen.append(lies(spot))
    assert len(gesehen) == 3
    assert gelesen == [None] * 8 + ["halt"]


def test_der_vorgabeweg_baut_den_echten_handerkenner_einmal(monkeypatch):
    gebaut = []

    class _Attrappe:
        def __init__(self, *a, **kw):
            gebaut.append(kw)

        def finde(self, feld, ausschnitt=None):
            return [_daumen_hoch()]

    monkeypatch.setattr(gesten, "Handerkenner", _Attrappe)
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_ein_koerper()])
    lies = folgen.gesten_leser(finder, jeder=1, takte=2)
    spot = _Spot()
    finder(spot)
    lies(spot)
    finder(spot)
    assert lies(spot) == "weiter"
    assert len(gebaut) == 1


def test_fehlende_modelle_kommen_als_spotlab_fehler_beim_ersten_lesen(monkeypatch, tmp_path):
    monkeypatch.setattr(gesten, "MODELL_ORDNER", tmp_path / "leer")
    monkeypatch.delenv(gesten.ENV_ORDNER, raising=False)
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_ein_koerper()])
    lies = folgen.gesten_leser(finder, jeder=1)
    spot = _Spot()
    finder(spot)
    with pytest.raises(SpotlabError):
        lies(spot)


# --------------------------------------------------------- Gesten in folge()


def _koerper_ruhig():
    """Ein Koerper, dessen Schulterlinie im Soll der Nasenregel liegt (8 Grad, im Totband).

    Mit der Schulter bei 15 Grad hebt `folge()` die Nase bis zum Anschlag und haelt
    dann von sich aus an (`ZU_HOCH_GRAD`) -- das prueft `test_workshop_folgen`; hier
    soll nur die Geste anhalten."""
    return _ein_koerper(schulter_zeile=320.0)


def _koerper_finder_immer():
    return folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                 koerper_holen=lambda feld: [_koerper_ruhig()])


def _lauf(gesten_plan, takte=8, jeder=1, halten=3, spot=None, melde=None, licht=False):
    """Ein Folgelauf mit Koerper voraus (2 m) und einem Gestenplan je Lesung."""
    spot = spot or _Spot(neigt=True)
    finder = _koerper_finder_immer()
    gesagt = []
    folgen.folge(spot, finder, melde=(melde or gesagt.append), jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(takte), licht=licht,
                 gesten=_leser_mit(finder, gesten_plan, jeder=jeder, takte=halten))
    return spot, gesagt


def test_die_offene_hand_haelt_spot_an_und_er_sagt_es():
    spot, gesagt = _lauf([[_offene_hand()]] * 8)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten[0]["vx"] > 0.0, "vor der Geste faehrt er auf den Koerper zu"
    assert all(k["vx"] == 0.0 and k["wz"] == 0.0 for k in fahrten[3:]), "nach dem Halt steht er"
    assert all(k["nick_grad"] != 0.0 for k in fahrten[3:]), "und haelt die Nase oben"
    assert [m for m in gesagt if "Halt" in m and "offene Hand" in m], "gesagt"
    assert len([m for m in gesagt if "Halt" in m]) == 1, "einmal"


def test_der_daumen_hoch_laesst_ihn_weitergehen():
    plan = [[_offene_hand()]] * 3 + [[]] + [[_daumen_hoch()]] * 3 + [[]] * 3
    spot, gesagt = _lauf(plan, takte=10)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert all(k["vx"] == 0.0 for k in fahrten[3:6]), "angehalten, auch waehrend der Daumen gehalten wird"
    assert fahrten[6]["vx"] > 0.0, "mit der dritten Daumen-Lesung faehrt er wieder"
    assert fahrten[-1]["vx"] > 0.0, "und bleibt dabei, wenn die Hand weg ist"
    assert [m for m in gesagt if "Daumen" in m and "weiter" in m.lower()]


def test_eine_geste_faehrt_nie_dorthin_wo_das_folgen_nicht_faehrt():
    """`weiter` ist kein Fahrbefehl: mit einer Wand voraus bleibt er nach dem Daumen stehen."""
    spot = _Spot(neigt=True, frei=0.2)
    plan = [[_offene_hand()]] * 3 + [[]] + [[_daumen_hoch()]] * 3 + [[]] * 3
    spot, gesagt = _lauf(plan, takte=10, spot=spot)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert all(k["vx"] == 0.0 for k in fahrten), "die Schranke gilt vor und nach jeder Geste"
    assert [m for m in gesagt if "Stehen geblieben" in m]


def test_ein_daumen_ohne_halt_aendert_nichts_wird_aber_gesehen():
    spot, gesagt = _lauf([[_daumen_hoch()]] * 5, takte=5)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert all(k["vx"] > 0.0 for k in fahrten), "er fuhr schon"
    assert [m for m in gesagt if "Daumen" in m], "trotzdem gesagt, damit man weiss, dass er sie sah"


def test_angehalten_dreht_er_nicht_einmal_mit():
    """Halt heisst stehen, nicht nur nicht vorwaerts: ein Ziel seitlich bringt kein wz."""
    spot = _Spot(neigt=True)
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: [_koerper_ruhig()])
    seitlich = lambda s: Ziel(30.0, 2.0, "Körper")  # noqa: E731
    seitlich.letzte = finder.letzte

    def staffel(s):
        finder(s)
        return seitlich(s)

    staffel.letzte = finder.letzte
    folgen.folge(spot, staffel, melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(8), gesten=_leser_mit(staffel, [[_offene_hand()]] * 8))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten[0]["wz"] != 0.0
    assert all(k["wz"] == 0.0 for k in fahrten[3:])


def test_ohne_ziel_bleibt_ein_halt_bestehen_und_ein_weiter_faehrt_nicht_los():
    """Zwischen den Gesten verschwindet der Mensch: Halt bleibt, und `weiter` ohne
    Ziel ist kein Losfahren -- ohne Ziel steht er ohnehin."""
    plan = iter([[_koerper_ruhig()]] * 3 + [[]] * 3 + [[_koerper_ruhig()]] * 4)
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: next(plan, []))
    # Gelesen wird nur, wenn ein Koerper da ist: drei offene Haende, dann vier Daumen.
    gesten_plan = [[_offene_hand()]] * 3 + [[_daumen_hoch()]] * 4
    spot = _Spot(neigt=True)
    folgen.folge(spot, finder, melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(10), gesten=_leser_mit(finder, gesten_plan))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert all(k["vx"] == 0.0 for k in fahrten[3:8]), "Halt, dann ohne Ziel, dann Halt weiter"
    assert fahrten[8]["vx"] > 0.0 and fahrten[-1]["vx"] > 0.0, "erst der dreimal gelesene Daumen mit Ziel faehrt"


def test_die_geste_steht_in_der_aufzeichnung_beim_echten_schreiber(tmp_path):
    """Die Attrappe nimmt jede Art an -- der echte `RunRecorder` hat eine
    Erlaubnisliste (`record/events.py`). Genau daran scheiterte `kein_ziel` am 16.09.2026."""
    from spotlab.record.run import RunRecorder

    spot = _Spot(neigt=True)
    spot.recorder = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    gesagt = []
    plan = [[_offene_hand()]] * 3 + [[]] + [[_daumen_hoch()]] * 3
    _lauf(plan, takte=7, spot=spot, melde=gesagt.append)
    zeilen = [json.loads(z) for z in
              (spot.recorder.dir / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
              if z.strip()]
    gesten_zeilen = [z for z in zeilen if z["art"] == "geste"]
    assert [z["daten"]["geste"] for z in gesten_zeilen] == ["halt", "weiter"]
    assert gesten_zeilen[0]["daten"]["angehalten"] is True
    assert gesten_zeilen[1]["daten"]["angehalten"] is False
    assert not [m for m in gesagt if "nicht aufzeichnen" in m]


def test_fehlende_handmodelle_sagen_es_einmal_und_das_folgen_geht_weiter():
    def lies(spot):
        raise SpotlabError("Die Handmodelle fehlen")

    spot = _Spot(neigt=True)
    gesagt = []
    folgen.folge(spot, _koerper_finder_immer(), melde=gesagt.append, jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6), gesten=lies)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert len(fahrten) == 6 and all(k["vx"] > 0.0 for k in fahrten), "gefolgt wie ohne Gesten"
    klagen = [m for m in gesagt if "Handmodelle" in m]
    assert len(klagen) == 1 and "ohne Gesten" in klagen[0]


def test_ein_stolpernder_leser_wird_einmal_gemeldet_und_weiter_gefragt():
    aufrufe = {"n": 0}

    def lies(spot):
        aufrufe["n"] += 1
        raise RuntimeError("Kamera stolpert")

    spot = _Spot(neigt=True)
    gesagt = []
    folgen.folge(spot, _koerper_finder_immer(), melde=gesagt.append, jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6), gesten=lies)
    assert aufrufe["n"] == 6, "ein Stolperer schaltet die Gesten nicht ab"
    assert len([m for m in gesagt if "Kamera stolpert" in m]) == 1


def test_ohne_gesten_aendert_sich_nichts():
    spot = _Spot(neigt=True)
    folgen.folge(spot, _koerper_finder_immer(), melde=lambda _t: None, jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(4))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert len(fahrten) == 4 and all(k["vx"] > 0.0 for k in fahrten)


def test_die_vorlage_liest_gesten_beim_gefolgten_koerper():
    quelle = (Path(folgen.__file__).parent / "beispiele" / "folgen.py").read_text(encoding="utf-8")
    assert "gesten=folgen.gesten_leser(" in quelle
    assert "offene Hand" in quelle and "Daumen" in quelle, "die zwei Zeichen stehen im Text fuer Schueler"


def test_die_ereignisart_geste_ist_erlaubt():
    from spotlab.record.events import ARTEN

    assert "geste" in ARTEN


def test_der_gestenleser_verlangt_einen_finder_mit_sicht():
    with pytest.raises(ValueError):
        folgen.gesten_leser(folgen.tag_finder())
    assert folgen.gesten_leser(SimpleNamespace(letzte=lambda: None)) is not None


# ------------------------------------------- Das Statuslicht am Roboter (22.09.2026)


class _Licht:
    """Merkt sich die Farbfolge -- ohne Wiederholungen, wie sie ein Mensch sieht."""

    def __init__(self):
        self.folge = []
        self.aus_gerufen = 0
        self.moeglich = True

    def setze(self, farbe):
        if farbe is not None and (not self.folge or self.folge[-1] != farbe):
            self.folge.append(farbe)

    def aus(self):
        self.aus_gerufen += 1


def test_ohne_ziel_gelb_mit_ziel_blau():
    """Wer danebensteht, soll ohne Laptop sehen, ob Spot ihn hat."""
    licht = _Licht()
    plan = iter([[], [_koerper_ruhig()], [_koerper_ruhig()]])
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: next(plan, []))
    spot = _Spot(neigt=True)
    folgen.folge(spot, finder, melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(3), licht=licht, nachlauf_s=0.0)
    assert licht.folge == [folgen.LICHT_SUCHT, folgen.LICHT_FOLGT]
    assert licht.aus_gerufen == 1, "am Ende gibt der Lauf die LEDs zurueck"


def test_das_handzeichen_halt_macht_rot_und_der_daumen_wieder_blau():
    """Genau dafuer ist das Licht da: ohne es sieht niemand, ob das Zeichen ankam."""
    licht = _Licht()
    plan = [[_offene_hand()]] * 3 + [[_daumen_hoch()]] * 3
    _lauf(plan, takte=6, licht=licht)
    assert licht.folge == [folgen.LICHT_FOLGT, folgen.LICHT_ANGEHALTEN, folgen.LICHT_FOLGT]


def test_angehalten_und_ziel_weg_bleibt_rot():
    """Rot heisst 'ich stehe wegen deines Zeichens' -- das gilt auch ohne Ziel."""
    licht = _Licht()
    plan = iter([[_koerper_ruhig()]] * 3 + [[]] * 2)
    finder = folgen.koerper_finder(aufnahme_holen=_koerperaufnahme,
                                   koerper_holen=lambda feld: next(plan, []))
    spot = _Spot(neigt=True)
    folgen.folge(spot, finder, melde=lambda _t: None, jetzt=_uhr(0.05), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(5), licht=licht, nachlauf_s=0.0,
                 gesten=_leser_mit(finder, [[_offene_hand()]] * 3))
    assert licht.folge == [folgen.LICHT_FOLGT, folgen.LICHT_ANGEHALTEN]


def test_ein_licht_das_nicht_geht_haelt_den_lauf_nicht_an():
    class _Kaputt:
        moeglich = True

        def setze(self, farbe):
            raise RuntimeError("AV-Dienst weg")

        def aus(self):
            raise RuntimeError("auch das noch")

    spot = _Spot(neigt=True)
    gesagt = []
    folgen.folge(spot, _koerper_finder_immer(), melde=gesagt.append, jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(4), licht=_Kaputt())
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert len(fahrten) == 4, "gefolgt wie ohne Licht"
    assert len([m for m in gesagt if "Licht" in m]) == 1, "einmal gesagt, nicht je Takt"


class _AV:
    """Der AV-Dienst am Kopf -- auf Wunsch kaputt oder haengend, und er schreibt mit."""

    def __init__(self, protokoll=None, kaputt=False, haengt=False):
        self.protokoll = protokoll if protokoll is not None else []
        self.kaputt, self.haengt = kaputt, haengt
        self.drin, self.los, self.zurueck = (threading.Event() for _ in range(3))

    def add_or_modify_behavior(self, name, behavior, **kw):
        self.protokoll.append("av_add")
        if self.haengt and not self.zurueck.is_set():
            self.drin.set()                  # wie ein RPC, der seine 5 s Frist ausschoepft
            self.los.wait(TEST_TIMEOUT_S)
            self.zurueck.set()

    def run_behavior(self, name, end_time_secs, **kw):
        from bosdyn.api import audio_visual_pb2 as av

        self.protokoll.append("av_run")
        if self.kaputt:
            raise RuntimeError("AV-Dienst: DEADLINE_EXCEEDED")
        return av.RunBehaviorResponse(run_result=av.RunBehaviorResponse.RESULT_BEHAVIOR_RUN)

    def stop_behavior(self, name, **kw):
        self.protokoll.append("av_stop")

    def delete_behaviors(self, names, **kw):
        self.protokoll.append("av_delete")


def _mit_av(spot, av):
    spot.robot = SimpleNamespace(list_services=lambda: [SimpleNamespace(name="audio-visual")],
                                 ensure_client=lambda name: av)
    return spot


def _sofort(arbeit):
    arbeit()


def test_ein_kaputtes_licht_wird_einmal_gesagt():
    """Befund p07: `Statuslicht.setze` faengt jeden Fehler selbst und zaehlt ihn nur --
    der Zweig in `folge()`, der „Das Licht am Kopf geht nicht" sagen soll, kam nie
    dran. Jetzt liest `folge()` den Zaehler des Lichts."""
    from spotlab.api.signals import Statuslicht

    spot = _mit_av(_Spot(neigt=True), _AV(kaputt=True))
    gesagt = []
    licht = Statuslicht(spot, jetzt=_uhr(1.0), ausfuehren=_sofort)
    folgen.folge(spot, _koerper_finder_immer(), melde=gesagt.append, jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(12), licht=licht)
    ueber_licht = [m for m in gesagt if "Licht" in m]
    assert len(ueber_licht) == 1, gesagt
    assert "DEADLINE" in ueber_licht[0] and "folgt weiter" in ueber_licht[0]
    assert len([k for k in spot.kommandos if isinstance(k, dict)]) == 12, "gefolgt wie ohne Licht"


def test_ein_haengendes_licht_verlaengert_keinen_takt():
    """Befund p07: jeder AV-Aufruf lief im Takt der Schleife, mit bis zu 5 s Frist. Hier
    haengt die erste Anfrage am Kopf, bis der Test sie loslaesst: alle Takte muessen
    WAEHREND des Haengers durchlaufen, im Abstand des Takts auf der Attrappen-Uhr."""
    from spotlab.api.signals import Statuslicht

    av = _AV(haengt=True)
    spot = _mit_av(_Spot(neigt=True), av)
    uhr = {"t": 0.0}

    def jetzt():
        return uhr["t"]

    def schlaf(s):
        uhr["t"] += s

    zeiten = []
    fahre = spot.walk
    spot.walk = lambda **kw: (zeiten.append(uhr["t"]), fahre(**kw))
    licht = Statuslicht(spot, jetzt=jetzt, aus_warte_s=0.01)
    try:
        folgen.folge(spot, _koerper_finder_immer(), melde=lambda _t: None, jetzt=jetzt,
                     schlaf=schlaf, laeuft=_laeuft_takte(20), licht=licht)
        haengt_noch = av.drin.is_set() and not av.zurueck.is_set()
    finally:
        av.los.set()
    assert haengt_noch, "alle Takte liefen, waehrend die Anfrage am Kopf hing"
    assert len(zeiten) == 20
    abstaende = [b - a for a, b in zip(zeiten, zeiten[1:])]
    assert all(a == pytest.approx(folgen.TAKT_S) for a in abstaende), abstaende
    assert spot.kommandos[-1] == "stop"


def test_am_ende_haelt_spot_zuerst_an_dann_kommt_das_licht():
    """Befund p08: im `finally` stand `licht.aus()` VOR `spot.stop()` -- bei einem langsamen
    AV-Dienst fuhr Spot mit dem letzten Befehl weiter, bis dessen Endzeit ablief (3.0 s zu
    spaet gemessen). `fahren.fahre` macht es seit jeher andersherum."""
    from spotlab.api.signals import Statuslicht

    spot = _Spot(neigt=True)
    _mit_av(spot, _AV(protokoll=spot.kommandos))
    zaehler = {"n": 0}

    def laeuft():
        zaehler["n"] += 1
        if zaehler["n"] > 3:
            raise KeyboardInterrupt          # der freundliche Stopp aus der GUI
        return True

    with pytest.raises(KeyboardInterrupt):
        folgen.folge(spot, _koerper_finder_immer(), melde=lambda _t: None, jetzt=_uhr(0.05),
                     schlaf=lambda _s: None, laeuft=laeuft,
                     licht=Statuslicht(spot, jetzt=_uhr(1.0), ausfuehren=_sofort))
    ende = spot.kommandos[spot.kommandos.index("stop"):]
    assert ende[:1] == ["stop"] and "av_stop" in ende and "av_delete" in ende, spot.kommandos


def test_ohne_licht_bleibt_alles_wie_vorher():
    spot = _Spot(neigt=True)
    folgen.folge(spot, _koerper_finder_immer(), melde=lambda _t: None, jetzt=_uhr(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3), licht=False)
    assert len([k for k in spot.kommandos if isinstance(k, dict)]) == 3


def test_die_vorlage_erklaert_die_farben():
    """Wer danebensteht, muss wissen, was gelb, blau und rot bedeuten -- sonst ist
    das Licht nur Dekoration."""
    quelle = (Path(folgen.__file__).parent / "beispiele" / "folgen.py").read_text(encoding="utf-8")
    for wort in ("gelb", "blau", "rot", "LED"):
        assert wort in quelle, wort


def test_ein_ausgefallener_finder_sagt_warum_statt_nur_zu_schweigen():
    """Befund der Beta-Durchsicht: fehlen OpenCV oder die Modelle, faellt der Finder
    aus, `zuerst()` verschluckt den Grund ins Protokoll, und der Lauf sagt nur
    'Noch kein Ziel'. Genau der verlorene Nachmittag vom 16.09.2026, nur mit einer
    anderen Ursache. Beide Finder tragen jetzt einen `hinweis`, den `folge()` einmal
    ausgibt -- mit dem Ordner, in den die Modelle gehoeren."""
    for finder in (folgen.koerper_finder(), folgen.gesicht_finder()):
        hinweis = getattr(finder, "hinweis", "")
        assert "Modell" in hinweis, hinweis
        assert "opencv" in hinweis.lower() or "OpenCV" in hinweis
        assert ".spotlab" in hinweis, "der Ordner steht dabei"
