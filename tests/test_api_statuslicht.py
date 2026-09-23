"""Das Statuslicht: eine Farbe, die STEHEN BLEIBT -- nicht blockierend.

`spot.lights()` schlaeft die ganze Dauer und raeumt danach auf. Im Folgetakt geht
das nicht: die Schleife haelt den Totmann, und 2 s Schlaf je Takt waeren 2 s ohne
Fahrbefehl. Deshalb ein eigener Weg: einmal anlegen, bei JEDER AENDERUNG die Farbe
setzen, sonst nur auffrischen, bevor die Frist ablaeuft. Laeuft der Prozess nicht
mehr, erlischt die Farbe von selbst -- die Frist ist der Totmann des Lichts.
"""

import threading
from types import SimpleNamespace

import pytest
from bosdyn.api import audio_visual_pb2 as av

from spotlab.api import signals
from spotlab.api.spot import Spot
from tests_zeitgrenzen import TEST_TIMEOUT_S, warte_bis


class AVClient:
    def __init__(self, result=av.RunBehaviorResponse.RESULT_BEHAVIOR_RUN):
        self.calls = []
        self.result = result
        self.enden = []

    def add_or_modify_behavior(self, name, behavior, **kw):
        self.calls.append(("add", name))
        self.behavior = behavior

    def run_behavior(self, name, end_time_secs, **kw):
        self.calls.append(("run", name))
        self.enden.append(end_time_secs)
        return av.RunBehaviorResponse(status=1, run_result=self.result)

    def stop_behavior(self, name, **kw):
        self.calls.append(("stop", name))

    def delete_behaviors(self, names, **kw):
        self.calls.append(("delete", names[0]))


def _spot(client, dienste=("audio-visual",)):
    robot = SimpleNamespace(
        list_services=lambda: [SimpleNamespace(name=n) for n in dienste],
        ensure_client=lambda name: client,
    )
    return Spot(SimpleNamespace(), robot=robot, recorder=None)


def _uhr(schritt=0.0):
    stand = {"t": 1000.0}

    def jetzt():
        stand["t"] += schritt
        return stand["t"]

    jetzt.stand = stand
    return jetzt


def _arten(client):
    return [n for n, _ in client.calls]


def _sofort(arbeit):
    """Der Bote ohne Faden: die Entscheidungen des Lichts, ohne auf einen Faden zu warten."""
    arbeit()


# ------------------------------------------------------------------ Setzen


def test_eine_farbe_wird_gesetzt_und_bleibt_stehen():
    c = AVClient()
    licht = signals.Statuslicht(_spot(c), jetzt=_uhr(), ausfuehren=_sofort)
    licht.setze("blue")
    assert _arten(c) == ["add", "run"], "einmal anlegen, einmal laufen lassen -- kein Schlaf"
    rgb = c.behavior.led_sequence_group.front_center.solid_color_sequence.color.rgb
    assert (rgb.r, rgb.g) == (0, 0) and rgb.b > 0
    assert c.enden[0] > 1000.0, "die Farbe hat eine Frist: stirbt der Lauf, erlischt sie"


def test_dieselbe_farbe_kostet_keine_weitere_anfrage():
    """Im Folgetakt wird jede halbe Sekunde gesetzt -- das darf nicht jedes Mal
    vier Anfragen an den Roboter schicken."""
    c = AVClient()
    licht = signals.Statuslicht(_spot(c), jetzt=_uhr(), ausfuehren=_sofort)
    for _ in range(5):
        licht.setze("blue")
    assert _arten(c) == ["add", "run"]


def test_eine_andere_farbe_geht_sofort_hinaus():
    c = AVClient()
    licht = signals.Statuslicht(_spot(c), jetzt=_uhr(), ausfuehren=_sofort)
    licht.setze("blue")
    licht.setze("red")
    assert _arten(c) == ["add", "run", "add", "run"]
    rgb = c.behavior.led_sequence_group.front_center.solid_color_sequence.color.rgb
    assert rgb.r > 0 and (rgb.g, rgb.b) == (0, 0)


def test_die_frist_wird_aufgefrischt_bevor_sie_ablaeuft():
    c = AVClient()
    uhr = _uhr()
    licht = signals.Statuslicht(_spot(c), frist_s=12.0, auffrischen_s=5.0, jetzt=uhr,
                                  ausfuehren=_sofort)
    licht.setze("blue")
    uhr.stand["t"] += 4.0
    licht.setze("blue")
    assert _arten(c) == ["add", "run"], "noch nicht faellig"
    uhr.stand["t"] += 2.0
    licht.setze("blue")
    assert _arten(c) == ["add", "run", "run"], "aufgefrischt, ohne die Farbe neu anzulegen"
    assert c.enden[-1] > c.enden[0]


def test_aus_stoppt_und_loescht():
    c = AVClient()
    licht = signals.Statuslicht(_spot(c), jetzt=_uhr(), ausfuehren=_sofort)
    licht.setze("blue")
    licht.aus()
    assert _arten(c)[-2:] == ["stop", "delete"]
    licht.aus()
    assert _arten(c).count("delete") == 1, "zweimal aus ist kein zweites Loeschen"


def test_ohne_farbe_wird_nichts_gesendet():
    c = AVClient()
    licht = signals.Statuslicht(_spot(c), jetzt=_uhr(), ausfuehren=_sofort)
    licht.setze(None)
    assert c.calls == []


# -------------------------------------------------- Nie den Lauf anhalten


def test_ein_fehler_am_licht_haelt_den_lauf_nicht_an():
    """Eine Beigabe darf den Regler nie stoppen -- dieselbe Regel wie beim
    Gesichtserkenner im Fahrblick."""
    class _Kaputt(AVClient):
        def run_behavior(self, name, end_time_secs, **kw):
            raise RuntimeError("AV-Dienst hustet")

    c = _Kaputt()
    licht = signals.Statuslicht(_spot(c), jetzt=_uhr(), ausfuehren=_sofort)
    licht.setze("blue")          # wirft nicht
    assert licht.fehler == 1 and "hustet" in licht.letzter_fehler
    licht.aus()                  # wirft auch nicht


def test_ein_abgelehntes_verhalten_zaehlt_als_fehler_und_schweigt_nicht():
    c = AVClient(av.RunBehaviorResponse.RESULT_LOW_PRIORITY)
    licht = signals.Statuslicht(_spot(c), jetzt=_uhr(), ausfuehren=_sofort)
    licht.setze("blue")
    assert licht.fehler == 1 and "LOW_PRIORITY" in licht.letzter_fehler


def test_ohne_av_dienst_gibt_es_kein_licht_und_das_sagt_es():
    c = AVClient()
    licht = signals.Statuslicht(_spot(c, dienste=()), jetzt=_uhr(), ausfuehren=_sofort)
    assert licht.moeglich is False
    licht.setze("blue")
    assert c.calls == [], "kein Versuch, kein Fehlerzaehler -- dieses Backend hat keine LEDs"
    assert licht.fehler == 0


def test_ohne_roboter_bleibt_es_still():
    """Trockenlauf und Sims: das Protobuf waere baubar, aber es gibt nichts zu leuchten."""
    licht = signals.Statuslicht(Spot(SimpleNamespace(), robot=None, recorder=None), jetzt=_uhr(), ausfuehren=_sofort)
    assert licht.moeglich is False
    licht.setze("red")
    licht.aus()


def test_die_farben_des_folgemodus_sind_bekannt():
    for name in ("blue", "yellow", "red"):
        assert name in signals.COLORS


@pytest.mark.parametrize("farbe", ["blau", "", "kein_farbname"])
def test_ein_unbekannter_farbname_wirft_nicht_sondern_zaehlt(farbe):
    c = AVClient()
    licht = signals.Statuslicht(_spot(c), jetzt=_uhr(), ausfuehren=_sofort)
    licht.setze(farbe)
    assert c.calls == [] and licht.fehler == 1


# ------------------------------------------- Rueckoff und Bote (p07, 22.09.2026)


class _Kaputt(AVClient):
    def run_behavior(self, name, end_time_secs, **kw):
        self.calls.append(("run", name))
        raise RuntimeError("AV-Dienst: DEADLINE_EXCEEDED")


def test_nach_einem_fehler_setzt_das_licht_bis_zur_auffrischfrist_aus():
    """Befund p07: nach einem Fehler blieb `_gesendet` leer, und JEDER Takt schickte eine
    neue Anfrage mit bis zu 5 s Frist -- sechs in sechs Takten. Jetzt: einmal versucht,
    dann Ruhe bis zur naechsten Auffrischfrist -- auch fuer eine andere Farbe."""
    c = _Kaputt()
    uhr = _uhr()
    licht = signals.Statuslicht(_spot(c), auffrischen_s=5.0, jetzt=uhr, ausfuehren=_sofort)
    for _ in range(6):
        licht.setze("blue")
    licht.setze("red")
    assert _arten(c) == ["add", "run"], "ein Versuch, nicht einer je Takt"
    assert licht.fehler == 1 and "DEADLINE" in licht.letzter_fehler
    uhr.stand["t"] += 4.9
    licht.setze("blue")
    assert _arten(c) == ["add", "run"], "noch im Rueckoff"
    uhr.stand["t"] += 0.2
    licht.setze("blue")
    assert _arten(c).count("run") == 2, "nach der Frist der naechste Versuch"
    assert licht.fehler == 2


def test_nach_dem_rueckoff_geht_es_normal_weiter():
    class _Einmal(AVClient):
        def __init__(self):
            super().__init__()
            self.kaputt = True

        def run_behavior(self, name, end_time_secs, **kw):
            if self.kaputt:
                self.kaputt = False
                self.calls.append(("run", name))
                raise RuntimeError("einmal nicht")
            return super().run_behavior(name, end_time_secs, **kw)

    c = _Einmal()
    uhr = _uhr()
    licht = signals.Statuslicht(_spot(c), auffrischen_s=5.0, jetzt=uhr, ausfuehren=_sofort)
    licht.setze("blue")
    uhr.stand["t"] += 5.0
    licht.setze("blue")
    assert licht.fehler == 1 and _arten(c).count("run") == 2, "nach dem Rueckoff geschickt"
    licht.setze("blue")
    licht.setze("blue")
    assert _arten(c).count("run") == 2, "zurueck im ruhigen Takt: gleiche Farbe kostet nichts"
    licht.setze("red")
    assert _arten(c)[-2:] == ["add", "run"] and _arten(c).count("run") == 3, \
        "eine neue Farbe geht wieder sofort hinaus"


class _Haengt(AVClient):
    """Ein AV-Dienst, der beim ersten `haengt_bei` haengt, bis der Test ihn loslaesst."""

    def __init__(self, haengt_bei="add"):
        super().__init__()
        self.haengt_bei = haengt_bei
        self.drin = threading.Event()
        self.los = threading.Event()
        self.zurueck = threading.Event()

    def _haenge(self, art):
        if art == self.haengt_bei and not self.zurueck.is_set():
            self.drin.set()
            self.los.wait(TEST_TIMEOUT_S)
            self.zurueck.set()

    def add_or_modify_behavior(self, name, behavior, **kw):
        super().add_or_modify_behavior(name, behavior, **kw)
        self._haenge("add")

    def stop_behavior(self, name, **kw):
        super().stop_behavior(name, **kw)
        self._haenge("stop")


def test_ein_haengender_dienst_haelt_setze_und_aus_nicht_auf():
    """Das Licht darf den Aufrufer nie aufhalten -- `setze` kehrt zurueck, WAEHREND die
    Anfrage am Roboter noch haengt, und `aus` wartet nur `aus_warte_s`."""
    c = _Haengt()
    licht = signals.Statuslicht(_spot(c), aus_warte_s=0.01)
    try:
        licht.setze("blue")
        assert c.drin.wait(TEST_TIMEOUT_S), "der Bote hat die Anfrage geschickt"
        licht.setze("red")
        licht.setze("yellow")
        licht.aus()
        assert not c.zurueck.is_set(), "alles zurueckgekehrt, waehrend der Dienst noch haengt"
    finally:
        c.los.set()
    warte_bis(lambda: licht._leer.is_set(), "der Bote ist zurueck")
    assert _arten(c)[-2:] == ["stop", "delete"], "nach dem Haenger: der letzte Wunsch war aus"


def test_waehrend_der_bote_unterwegs_ist_gilt_der_neueste_wunsch():
    c = _Haengt()
    licht = signals.Statuslicht(_spot(c))
    licht.setze("blue")
    assert c.drin.wait(TEST_TIMEOUT_S)
    licht.setze("red")
    licht.setze("yellow")
    c.los.set()
    warte_bis(lambda: licht._leer.is_set() and _arten(c).count("run") == 2,
              "der Bote hat nach blau den neuesten Wunsch geschickt")
    rgb = c.behavior.led_sequence_group.front_center.solid_color_sequence.color.rgb
    assert rgb.r > 0 and rgb.g > 0 and rgb.b == 0, "gelb, nicht rot: der Zwischenwunsch faellt weg"
    assert _arten(c) == ["add", "run", "add", "run"]
