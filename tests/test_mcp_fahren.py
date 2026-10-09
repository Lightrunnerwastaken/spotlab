"""Die Werkzeuge des Agenten (MCP) gegen eine Attrappe der Zentrale — ohne Roboter."""

import json
import threading
import time

import pytest
from test_mcp_agentlage import _lagebild

from spotlab.mcp import fahren
from spotlab.record import agent as agentdatei
from spotlab.record.run import RunRecorder


@pytest.fixture
def wurzel(tmp_path, monkeypatch):
    monkeypatch.setattr(fahren, "arbeitsordner", lambda: tmp_path)
    monkeypatch.setattr(fahren, "_zustand", {"puls": None, "lauf": None, "nummer": 0})
    monkeypatch.setattr(fahren, "BESTAETIGUNG_S", 0.5)
    monkeypatch.setattr(fahren, "BEFEHL_WARTE_S", 2.0)
    yield tmp_path
    puls = fahren._zustand["puls"]
    if puls is not None:
        puls.halt()


class _Zentrale:
    """Liest `agent_befehl.json` wie die Zentrale und schreibt Lagebild und Zustand.

    `antwort(befehl, seit_s)` gibt (zustand, grund) — oder None: dann wird der Befehl gar
    nicht bestätigt (eine Zentrale, die hängt)."""

    def __init__(self, wurzel, antwort, backend="sim"):
        from spotlab.workshop import zentrale

        self.recorder = RunRecorder(fahren._beispiel_runs(wurzel), zentrale.SKRIPT,
                                    backend=backend)
        self.lauf = self.recorder.dir
        self.antwort = antwort
        self.gesehen = []                     # (nummer, lebt) jedes gelesenen Befehls
        self._halt = threading.Event()
        self._agent = {"nummer": 0, "art": None, "zustand": "keiner", "grund": "", "warum": "",
                       "agent": "", "seit": None, "tiefe": None, "freigabe": False,
                       "braucht_freigabe": False}
        self._seit = {}
        self._schreibe()
        self._faden = threading.Thread(target=self._lauf, daemon=True)
        self._faden.start()

    def _schreibe(self):
        _lagebild(self.lauf, t=time.time(), agent=dict(self._agent))
        with (self.lauf / "zustand.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "daten": {"pose": [0.0, 0.0, 0.0]}}) + "\n")

    def _lauf(self):
        while not self._halt.wait(0.03):
            befehl = agentdatei.lies_befehl(self.lauf)
            if befehl is not None:
                self.gesehen.append((befehl.nummer, befehl.lebt))
                anfang = self._seit.setdefault(befehl.nummer, time.monotonic())
                ergebnis = self.antwort(befehl, time.monotonic() - anfang)
                if ergebnis is not None:
                    zustand, grund = ergebnis
                    self._agent.update(nummer=befehl.nummer, art=befehl.art, zustand=zustand,
                                       grund=grund, warum=befehl.warum, agent=befehl.agent)
            self._schreibe()

    def ende(self):
        self._halt.set()
        self._faden.join(5)
        self.recorder.finish("ok")


@pytest.fixture
def zentrale_mit(wurzel):
    gebaut = []

    def bauen(antwort, backend="sim"):
        z = _Zentrale(wurzel, antwort, backend)
        gebaut.append(z)
        return z

    yield bauen
    for z in gebaut:
        z.ende()


# ------------------------------------------------------------ ohne Zentrale


@pytest.mark.parametrize("werkzeug, argumente", [
    ("lage", {}), ("skizze", {}), ("kamerabild", {}), ("tiefe_messen", {}),
    ("fahre_zu", {"x": 1, "y": 0, "warum": "hin"}), ("drehe", {"grad": 90, "warum": "schauen"}),
    ("stoss", {"vx": 0.2, "vy": 0, "wz": 0, "dauer_s": 1, "warum": "ein Stück"}),
    ("folge_mensch", {"x": 1, "y": 0, "warum": "ihm nach"}), ("stopp", {}), ("warten", {}),
    ("zentrale_beenden", {}), ("licht", {"farbe": "rot"}), ("piep", {}),
    ("suche", {"stufe": "normal"}),
])
def test_ohne_zentrale_sagt_jedes_werkzeug_was_zu_tun_ist(wurzel, werkzeug, argumente):
    antwort = getattr(fahren, werkzeug)(**argumente)
    assert "zentrale_starten" in antwort["fehler"], antwort


def test_der_status_ohne_zentrale(wurzel):
    assert fahren.zentrale_status()["laeuft"] is False


def test_ein_unbekannter_ort_wird_abgelehnt(wurzel):
    assert "ort" in fahren.zentrale_starten("mond")["fehler"]


# ------------------------------------------------------------ Befehle


def test_ein_fahrbefehl_wird_bestaetigt_lebt_und_kommt_an(zentrale_mit):
    z = zentrale_mit(lambda b, s: ("unterwegs", "") if s < 0.8 else ("angekommen", ""))
    antwort = fahren.fahre_zu(2.0, 1.0, warum="zur Tür")
    assert antwort["zustand"] == "angekommen", antwort
    befehl = agentdatei.lies_befehl(z.lauf)
    assert (befehl.art, befehl.werte, befehl.warum) == ("ziel", {"x": 2.0, "y": 1.0}, "zur Tür")
    lebenszeichen = sorted({lebt for nummer, lebt in z.gesehen if nummer == antwort["nummer"]})
    assert len(lebenszeichen) >= 3, "der Puls frischt das Lebenszeichen auf"
    assert max(b - a for a, b in zip(lebenszeichen, lebenszeichen[1:])) < \
        agentdatei.AGENT_TOTMANN_S


def test_ohne_bestaetigung_antwortet_die_zentrale_nicht_und_der_puls_hoert_auf(zentrale_mit):
    z = zentrale_mit(lambda b, s: None)
    antwort = fahren.drehe(90, warum="umsehen")
    assert "antwortet nicht" in antwort["fehler"]
    time.sleep(0.1)
    lebt = agentdatei.lies_befehl(z.lauf).lebt
    time.sleep(0.6)
    assert agentdatei.lies_befehl(z.lauf).lebt == lebt, "nach der Absage kein Lebenszeichen mehr"


def test_ein_langer_befehl_laeuft_weiter_und_warten_holt_das_ende(zentrale_mit, monkeypatch):
    monkeypatch.setattr(fahren, "BEFEHL_WARTE_S", 0.3)
    zentrale_mit(lambda b, s: ("unterwegs", "") if s < 1.0 else ("angekommen", ""))
    antwort = fahren.fahre_relativ(1.0, 0.0, warum="ein Stück vor")
    assert antwort["zustand"] == "läuft noch"
    ende = fahren.warten(5)
    assert ende["befehl"]["zustand"] == "angekommen" and "spot" in ende["lage"]


def test_eine_ablehnung_kommt_mit_grund(zentrale_mit):
    zentrale_mit(lambda b, s: ("abgelehnt", "keine Freigabe — ein Mensch muss …"))
    antwort = fahren.stoss(0.2, 0.0, 0.0, 1.0, warum="ein Stück")
    assert antwort["zustand"] == "abgelehnt" and "Freigabe" in antwort["grund"]


def test_die_nummern_zaehlen_ueber_das_was_schon_im_lauf_steht(zentrale_mit):
    z = zentrale_mit(lambda b, s: ("erledigt", ""))
    agentdatei.schreibe_befehl(z.lauf, 41, "stopp", {}, "", "frueher")
    assert fahren.stopp()["nummer"] == 42


def test_warum_ist_pflicht(zentrale_mit):
    zentrale_mit(lambda b, s: ("angekommen", ""))
    assert "warum" in fahren.fahre_zu(1.0, 0.0, warum="  ")["fehler"]


# ------------------------------------------------------------ Besitz


def test_ein_zweiter_agent_findet_die_zentrale_belegt(zentrale_mit, monkeypatch):
    z = zentrale_mit(lambda b, s: ("erledigt" if b.art == "stopp" else "angekommen", ""))
    agentdatei.schreibe_besitz(z.lauf, "codex", 4711)
    monkeypatch.setattr(fahren, "_lebt", lambda pid: True)
    antwort = fahren.fahre_zu(1.0, 0.0, warum="hin")
    assert "belegt von codex" in antwort["fehler"]
    assert fahren.stopp()["zustand"] == "erledigt", "anhalten darf jeder"
    monkeypatch.setattr(fahren, "_lebt", lambda pid: False)
    assert fahren.fahre_zu(1.0, 0.0, warum="hin")["zustand"] == "angekommen"
    assert agentdatei.lies_besitz(z.lauf)["agent"] == fahren.AGENT_NAME


# ------------------------------------------------------------ Sehen und Aufzeichnung


def test_lage_und_skizze_stehen_in_der_aufzeichnung_und_das_bild_liegt_ab(zentrale_mit):
    z = zentrale_mit(lambda b, s: ("angekommen", ""))
    assert "richtungen" in fahren.lage()
    bild = fahren.skizze(radius_m=2)
    assert isinstance(bild, fahren.Bildantwort) and bild.format == "png"
    assert "+y" in bild.text["legende"]
    zeilen = [json.loads(z_) for z_ in (z.lauf / "agent.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert [zeile["werkzeug"] for zeile in zeilen] == ["lage", "skizze"]
    assert zeilen[1]["argumente"] == {"radius_m": 2}
    assert len(list((z.lauf / "agent").glob("*_skizze.png"))) == 1


def test_im_2d_uebungsraum_gibt_es_kein_kamerabild(zentrale_mit):
    zentrale_mit(lambda b, s: None, backend="sim")
    assert "Kein Bild" in fahren.kamerabild()["hinweis"]


def test_im_3d_uebungsraum_sagt_das_bild_was_es_zeigt(zentrale_mit):
    z = zentrale_mit(lambda b, s: None, backend="mujoco")
    (z.lauf / "ansicht.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    bild = fahren.kamerabild()
    assert bild.format == "jpeg" and "VON AUSSEN" in bild.text["was"]


def test_der_status_nennt_ort_und_wer_steuert(zentrale_mit):
    z = zentrale_mit(lambda b, s: None, backend="mujoco")
    agentdatei.schreibe_besitz(z.lauf, "claude", 99999)
    status = fahren.zentrale_status()
    assert (status["laeuft"], status["ort"], status["antwortet"]) == (True, "3d", True)
    assert status["steuert"]["agent"] == "claude"


def test_eine_falsche_zahl_nennt_das_argument(zentrale_mit):
    zentrale_mit(lambda b, s: ("angekommen", ""))
    antwort = fahren.fahre_zu("links", 0.0, warum="hin")
    assert "x muss eine Zahl sein" in antwort["fehler"]
