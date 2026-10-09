"""Die Kartenarbeit der Steuerzentrale (Teil 3): laden, verorten, aufnehmen, speichern.

Roboter und Aufnahme sind Attrappen; die langsame Arbeit läuft im Test gleich im selben Faden
(`ausfuehren=lambda f: f()`), die Kartenwände kommen aus einer Attrappe (`waende_laden`).
"""

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spotlab.backends.base import Capability, Verortung
from spotlab.errors import MapError, NotLocalized
from spotlab.maps.session import RecordingStatus
from spotlab.workshop import kartenarbeit as ka
from spotlab.workshop.kartenabgleich import Kartenwaende

T0 = 1000.0


class _Sitzung:
    def __init__(self, protokoll, start_fehler=None, download_fehler=0):
        self.protokoll = protokoll
        self.start_fehler = start_fehler
        self.download_fehler = download_fehler

    def start(self, graph_leeren=False):
        if self.start_fehler:
            raise self.start_fehler
        self.protokoll.append(("start", graph_leeren))

    def waypoint(self, name):
        self.protokoll.append(("wegpunkt", name))
        return "wp-neu"

    def stop(self):
        self.protokoll.append("stop")

    def status(self):
        return RecordingStatus(True, 14, 13, "Aufnahme läuft")

    def nachbearbeiten(self, melde=None, **kw):
        self.protokoll.append("nachbearbeiten")
        if melde:
            melde("Schleifen schliessen …")

    def download(self, wurzel, name, roboter=None):
        if self.download_fehler:
            self.download_fehler -= 1
            raise MapError("Karte herunterladen ist fehlgeschlagen: WLAN weg")
        ziel = Path(wurzel) / name
        ziel.mkdir(parents=True)
        (ziel / "graph").write_bytes(b"")
        self.protokoll.append(("download", name))
        return ziel


class _Backend:
    def __init__(self, kann=True, localize_fehler=0):
        self.protokoll = []
        self.kann = kann
        self.localize_fehler = localize_fehler
        self.v = Verortung("wp-1", (0.0, 0.0, 0.0), (10.0, 20.0, math.radians(90.0)), False, 5, 0)
        self.sitzung = _Sitzung(self.protokoll)

    def capabilities(self):
        return Capability.LOCOMOTION | (Capability.GRAPH_NAV if self.kann else Capability.NONE)

    def upload_map(self, ordner):
        self.protokoll.append(("upload", Path(ordner).name))

    def localize(self):
        if self.localize_fehler:
            self.localize_fehler -= 1
            raise NotLocalized("Der Spot konnte sich nicht verorten.")
        self.protokoll.append("localize")
        return "wp-1"

    def verortung(self):
        return self.v

    def aufnahme_sitzung(self):
        return self.sitzung


def _waende(ordner):
    return Kartenwaende(np.array([[1.0, 0.0]]), [(0.0, 0.0, "Eingang"), (2.0, 0.0, "")],
                        [(0, 1)], "anker")


def _arbeit(tmp_path, backend=None, uhr=None, ausfuehren=lambda f: f(), gesagt=None):
    (tmp_path / "karten" / "flur2").mkdir(parents=True)
    (tmp_path / "karten" / "flur2" / "graph").write_bytes(b"")
    backend = backend or _Backend()
    uhr = uhr if uhr is not None else {"t": T0}
    arbeit = ka.Kartenarbeit(SimpleNamespace(backend=backend), tmp_path,
                             jetzt=lambda: uhr["t"], melde=(gesagt or []).append,
                             ausfuehren=ausfuehren, waende_laden=_waende)
    return arbeit, backend, uhr


def _geladen(tmp_path, **kw):
    arbeit, backend, uhr = _arbeit(tmp_path, **kw)
    arbeit.auftrag(1, "laden", "flur2")
    arbeit.beobachte(uhr["t"])
    return arbeit, backend, uhr


# ------------------------------------------------------------ Laden und Verorten


def test_laden_heisst_hochladen_verorten_und_waende_bereit(tmp_path):
    arbeit, backend, _ = _geladen(tmp_path)
    assert backend.protokoll == [("upload", "flur2"), "localize"]
    assert arbeit.zustand == "verortet" and arbeit.name == "flur2" and arbeit.erledigt == 1


def test_ohne_tag_im_bild_wird_alle_zwei_sekunden_neu_verortet(tmp_path):
    arbeit, backend, uhr = _arbeit(tmp_path, backend=_Backend(localize_fehler=2))
    backend.v = None
    arbeit.auftrag(1, "laden", "flur2")
    assert arbeit.zustand == "sucht_tag" and "Tag" in arbeit.grund
    uhr["t"] += 1.0
    arbeit.beobachte(uhr["t"])
    assert backend.localize_fehler == 1, "noch keine 2 s: kein neuer Versuch"
    uhr["t"] += ka.VERSUCH_S
    arbeit.beobachte(uhr["t"])
    uhr["t"] += ka.VERSUCH_S
    backend.v = Verortung("wp-1", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), False, 1, 0)
    arbeit.beobachte(uhr["t"])
    arbeit.beobachte(uhr["t"])
    assert arbeit.zustand == "verortet"


def test_eine_unbekannte_karte_setzt_zurueck_und_sagt_warum(tmp_path):
    arbeit, _, _ = _arbeit(tmp_path)
    arbeit.auftrag(1, "laden", "gibtsnicht")
    assert arbeit.zustand == "keine" and "gibtsnicht" in arbeit.grund


def test_verloren_steht_im_zustand(tmp_path):
    arbeit, backend, uhr = _geladen(tmp_path)
    backend.v = Verortung("wp-1", (0.0, 0.0, 0.0), (10.0, 20.0, 0.0), True, 5, 9)
    arbeit.beobachte(uhr["t"] + 0.5)
    assert arbeit.zustand == "verloren"
    assert arbeit.daten(uhr["t"] + 0.5, None)["wiedererkennung"]["verloren"] is True


def test_ohne_graphnav_gibt_es_keine_karten(tmp_path):
    arbeit, backend, _ = _arbeit(tmp_path, backend=_Backend(kann=False))
    arbeit.auftrag(1, "laden", "flur2")
    assert not arbeit.kann and backend.protokoll == [] and "GraphNav" in arbeit.grund
    assert arbeit.erledigt == 1


def test_ein_auftrag_waehrend_einer_arbeit_wird_abgelehnt(tmp_path):
    wartend = []
    arbeit, backend, _ = _arbeit(tmp_path, ausfuehren=wartend.append)
    arbeit.auftrag(1, "laden", "flur2")
    arbeit.auftrag(2, "aufnahme_start", "neu")
    assert arbeit.erledigt == 2 and "warten" in arbeit.grund
    wartend.pop()()
    assert backend.protokoll[0] == ("upload", "flur2") and ("start", True) not in backend.protokoll


def test_jede_nummer_nur_einmal(tmp_path):
    arbeit, backend, _ = _geladen(tmp_path)
    arbeit.auftrag(1, "laden", "flur2")
    assert backend.protokoll.count(("upload", "flur2")) == 1


# ------------------------------------------------------------ Aufnahme


def test_verortet_wird_die_karte_weitergefuehrt(tmp_path):
    arbeit, backend, _ = _geladen(tmp_path)
    arbeit.auftrag(2, "aufnahme_start", "flur2-2")
    assert ("start", False) in backend.protokoll
    assert arbeit.zustand == "nimmt_auf" and arbeit.weiter and arbeit.waende is not None


def test_ohne_karte_beginnt_eine_neue(tmp_path):
    arbeit, backend, _ = _arbeit(tmp_path)
    arbeit.auftrag(1, "aufnahme_start", "neu")
    assert ("start", True) in backend.protokoll and not arbeit.weiter and arbeit.waende is None


def test_ein_gescheiterter_start_laesst_den_zustand_wie_er_war(tmp_path):
    arbeit, backend, _ = _geladen(tmp_path)
    backend.sitzung.start_fehler = MapError("Spot ist nicht in der alten Karte verortet.")
    arbeit.auftrag(2, "aufnahme_start", "flur2-2")
    assert arbeit.zustand == "verortet" and "verortet" in arbeit.grund


def test_wegpunkte_nur_waehrend_der_aufnahme(tmp_path):
    arbeit, backend, _ = _arbeit(tmp_path)
    arbeit.auftrag(1, "wegpunkt", "Punkt 1")
    assert ("wegpunkt", "Punkt 1") not in backend.protokoll and "Aufnahme" in arbeit.grund
    arbeit.auftrag(2, "aufnahme_start", "neu")
    arbeit.auftrag(3, "wegpunkt", "Punkt 1")
    assert ("wegpunkt", "Punkt 1") in backend.protokoll


def test_waehrend_der_aufnahme_wird_nicht_geladen(tmp_path):
    arbeit, backend, _ = _arbeit(tmp_path)
    arbeit.auftrag(1, "aufnahme_start", "neu")
    arbeit.auftrag(2, "laden", "flur2")
    assert ("upload", "flur2") not in backend.protokoll and "Aufnahme" in arbeit.grund


def test_beenden_schliesst_schleifen_speichert_und_uebernimmt_die_karte(tmp_path):
    arbeit, backend, _ = _arbeit(tmp_path)
    arbeit.auftrag(1, "aufnahme_start", "gang")
    arbeit.auftrag(2, "aufnahme_stopp", "gang")
    assert backend.protokoll[-3:] == ["stop", "nachbearbeiten", ("download", "gang")]
    assert arbeit.name == "gang" and arbeit.waende is not None
    assert arbeit.zustand in ("verortet", "sucht_tag")


def test_ein_vorhandener_name_wird_nie_ueberschrieben(tmp_path):
    arbeit, backend, _ = _geladen(tmp_path)
    arbeit.auftrag(2, "aufnahme_start", "flur2")
    arbeit.auftrag(3, "aufnahme_stopp", "flur2")
    assert ("download", "flur2-2") in backend.protokoll and arbeit.name == "flur2-2"


def test_ein_gescheitertes_herunterladen_laesst_nochmal_versuchen(tmp_path):
    arbeit, backend, _ = _arbeit(tmp_path)
    backend.sitzung.download_fehler = 1
    arbeit.auftrag(1, "aufnahme_start", "gang")
    arbeit.auftrag(2, "aufnahme_stopp", "gang")
    assert arbeit.zustand == "nicht_gespeichert" and "nochmal" in arbeit.grund
    arbeit.auftrag(3, "aufnahme_stopp", "gang")
    assert backend.protokoll.count("stop") == 1 and backend.protokoll.count("nachbearbeiten") == 1
    assert ("download", "gang") in backend.protokoll and arbeit.name == "gang"


def test_am_programmende_wird_eine_laufende_aufnahme_gespeichert(tmp_path):
    arbeit, backend, _ = _arbeit(tmp_path)
    arbeit.auftrag(1, "aufnahme_start", "gang")
    arbeit.beenden()
    assert backend.protokoll[-3:] == ["stop", "nachbearbeiten", ("download", "gang")]


def test_ohne_aufnahme_tut_das_programmende_nichts(tmp_path):
    arbeit, backend, _ = _geladen(tmp_path)
    vorher = list(backend.protokoll)
    arbeit.beenden()
    assert backend.protokoll == vorher


# ------------------------------------------------------------ Lagebild


def test_die_wegpunkte_liegen_im_rahmen_der_skizze(tmp_path):
    arbeit, _, uhr = _geladen(tmp_path)
    daten = arbeit.daten(uhr["t"], None)
    [a, b] = daten["wegpunkte"]
    assert (a["x"], a["y"], a["name"]) == (pytest.approx(10.0), pytest.approx(20.0), "Eingang")
    assert (b["x"], b["y"]) == (pytest.approx(10.0), pytest.approx(22.0)), "um 90 Grad gedreht"
    assert daten["kanten"] == [[0, 1]] and daten["name"] == "flur2" and daten["auftrag"] == 1


def test_das_urteil_des_roboters_ueber_die_letzten_30_s(tmp_path):
    arbeit, backend, uhr = _geladen(tmp_path)
    for dt, an, ab in ((0.0, 10, 0), (10.0, 20, 1), (40.0, 40, 3)):
        backend.v = Verortung("wp-1", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), False, an, ab)
        arbeit.beobachte(uhr["t"] + dt)
    w = arbeit.daten(uhr["t"] + 40.0, None)["wiedererkennung"]
    assert (w["angenommen"], w["abgelehnt"]) == (20, 2)


def test_waehrend_der_aufnahme_zaehlt_das_lagebild_mit(tmp_path):
    arbeit, _, uhr = _arbeit(tmp_path)
    arbeit.auftrag(1, "aufnahme_start", "gang")
    arbeit.beobachte(uhr["t"])
    auf = arbeit.daten(uhr["t"], None)["aufnahme"]
    assert (auf["wegpunkte"], auf["kanten"], auf["name"]) == (14, 13, "gang")


def test_der_abgleich_nimmt_die_waende_in_die_skizze(tmp_path):
    from spotlab.workshop import skizze as sk

    arbeit, _, uhr = _geladen(tmp_path)
    s = sk.Skizze()
    s.ursprung = (5.0, 15.0)
    s.zustand = np.full((200, 200), sk.FREI, np.uint8)
    s.zeit = np.full((200, 200), uhr["t"])
    a = arbeit.abgleiche(s, (10.0, 20.0), uhr["t"])
    assert a is not None and a.fehlt == 1, "die eine Kartenwand bei (10, 21) sieht Spot frei"


# ------------------------------------------------------------ Zwei Auftraggeber (Agenten, Teil 2)


def test_tab_und_agent_zaehlen_getrennt(tmp_path):
    arbeit, backend, _ = _geladen(tmp_path)              # Tab-Auftrag 1: laden
    assert arbeit.auftrag(1, "aufnahme_start", "neu", quelle="agent") is None
    assert ("start", False) in backend.protokoll, "Agent 1 ist ein anderer Auftrag als Tab 1"
    arbeit.auftrag(2, "wegpunkt", "Tür", quelle="agent")
    assert ("wegpunkt", "Tür") in backend.protokoll
    assert arbeit.erledigt == 1, "der Tab sieht nur seine eigenen Nummern"


def test_eine_ablehnung_gibt_den_grund_zurueck(tmp_path):
    arbeit, _, _ = _arbeit(tmp_path)
    grund = arbeit.auftrag(1, "wegpunkt", "Tür", quelle="agent")
    assert grund and "Aufnahme" in grund
    ohne, _, _ = _arbeit(tmp_path / "ohne", backend=_Backend(kann=False))
    assert "GraphNav" in ohne.auftrag(1, "laden", "flur2", quelle="agent")


def test_arbeitet_sagt_ob_spot_beschaeftigt_ist(tmp_path):
    wartend = []
    arbeit, _, _ = _arbeit(tmp_path, ausfuehren=wartend.append)
    assert not arbeit.arbeitet
    arbeit.auftrag(1, "laden", "flur2", quelle="agent")
    assert arbeit.arbeitet
    wartend.pop()()
    assert not arbeit.arbeitet


def test_die_navigationskarte_nur_geladen_verortet_und_ohne_aufnahme(tmp_path):
    from spotlab.errors import SpotlabError

    arbeit, _, _ = _arbeit(tmp_path)
    with pytest.raises(SpotlabError, match="karte_laden"):
        arbeit.navigationskarte()
    arbeit.auftrag(1, "laden", "flur2")
    karte = arbeit.navigationskarte()
    assert karte.name == "flur2" and karte.dir.name == "flur2"
    arbeit.auftrag(2, "aufnahme_start", "neu")
    with pytest.raises(SpotlabError, match="aufnahme_beenden"):
        arbeit.navigationskarte()


def test_unverortet_gibt_es_keine_navigation(tmp_path):
    from spotlab.errors import SpotlabError

    arbeit, _, _ = _arbeit(tmp_path, backend=_Backend(localize_fehler=1))
    arbeit.auftrag(1, "laden", "flur2")
    assert arbeit.zustand == "sucht_tag"
    with pytest.raises(SpotlabError, match="Tag"):
        arbeit.navigationskarte()


def test_gespeichert_als_nennt_den_freien_namen(tmp_path):
    arbeit, _, _ = _geladen(tmp_path)
    assert arbeit.gespeichert_als is None
    arbeit.auftrag(2, "aufnahme_start", "flur2")
    arbeit.auftrag(3, "aufnahme_stopp", "flur2")
    assert arbeit.gespeichert_als == "flur2-2"
