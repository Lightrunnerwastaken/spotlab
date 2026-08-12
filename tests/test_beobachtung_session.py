"""Die Beobachtungssitzung: Lebenszyklus, Leaselosigkeit, Live-Zahlen."""

import json
import math
import time

import pytest

from spotlab.beobachtung.session import Beobachtung


def _lauf(tmp_path):
    return json.loads(next(tmp_path.glob("*/lauf.json")).read_text(encoding="utf-8"))


# ------------------------------------------------------------- Lebenszyklus


def test_trockene_sitzung_zeichnet_auf(tmp_path):
    with Beobachtung.trocken(runs_dir=tmp_path) as b:
        with b.messfenster("B1-Stand", hz=50.0, regler="MEDIUM"):
            pass
    lauf = _lauf(tmp_path)
    assert lauf["backend"] == "beobachter-trocken"
    assert lauf["ergebnis"] == "ok"


def test_backend_name_sagt_dass_niemand_kommandiert_hat(tmp_path):
    """Jede spaetere Auswertung muss sehen, dass tracking_prozent hier
    bedeutungslos waere."""
    with Beobachtung.trocken(runs_dir=tmp_path):
        pass
    assert _lauf(tmp_path)["backend"].startswith("beobachter")


def test_die_probe_ist_von_der_messfahrt_zu_unterscheiden(tmp_path):
    """Bis zum 12.08.2026 hiessen beide „beobachter".

    Damit war in `lauf.json` nicht zu sehen, ob die Gelenkwerte gemessen oder
    erfunden sind — nur matura-spots eigenes Protokoll wusste es, und davon
    weiss spotlab nichts. Beim Bau der Gangkennlinie waere beinahe eine Probe
    in die Kalibrierdaten gelaufen; sie fiel nur heraus, weil `DryRunBackend`
    alle Fuesse am Boden laesst und damit null Gangzyklen liefert. Sobald das
    Sim-Backend die Beine bewegt, faellt sie nicht mehr heraus.
    """
    from spotlab.config import Config

    class FakeRobot:
        def ensure_client(self, name):
            return object()

    trocken = tmp_path / "trocken"
    echt = tmp_path / "echt"
    with Beobachtung.trocken(runs_dir=trocken, bilder_hz=0):
        pass
    Beobachtung.connect(
        Config(ip="1.2.3.4", username="u"), runs_dir=echt,
        verbinder=lambda cfg: FakeRobot(), bilder_hz=0,
    ).beende()

    assert _lauf(trocken)["backend"] != _lauf(echt)["backend"]
    assert "trocken" in _lauf(trocken)["backend"]
    assert "trocken" not in _lauf(echt)["backend"]


def test_auch_das_verbunden_ereignis_nennt_den_richtigen_backend(tmp_path):
    """Sonst widerspraechen sich lauf.json und ereignisse.jsonl."""
    b = Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=0)
    with b:
        pass
    zeilen = (b.lauf_verzeichnis / "ereignisse.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    verbunden = next(
        json.loads(z) for z in zeilen if json.loads(z)["art"] == "verbunden"
    )
    assert verbunden["daten"]["backend"] == _lauf(tmp_path)["backend"]


def test_der_abtaster_wird_garantiert_gestoppt(tmp_path):
    b = Beobachtung.trocken(runs_dir=tmp_path)
    with b:
        pass
    assert b.sampler._thread is None


def test_eine_ausnahme_schliesst_den_lauf_trotzdem_ab(tmp_path):
    with pytest.raises(ValueError):
        with Beobachtung.trocken(runs_dir=tmp_path):
            raise ValueError("mittendrin")
    lauf = _lauf(tmp_path)
    assert lauf["ergebnis"] == "fehler"
    assert "mittendrin" in (lauf["fehler"] or "")


def test_strg_c_wird_als_abgebrochen_verbucht(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        with Beobachtung.trocken(runs_dir=tmp_path):
            raise KeyboardInterrupt()
    assert _lauf(tmp_path)["ergebnis"] == "abgebrochen"


def test_zweimal_beenden_ist_harmlos(tmp_path):
    b = Beobachtung.trocken(runs_dir=tmp_path)
    b.beende()
    b.beende()
    assert _lauf(tmp_path)["ergebnis"] == "ok"


def test_connect_holt_weder_lease_noch_estop(tmp_path):
    """Der ganze Grund, warum das Werkzeug vor A1 benutzbar ist."""
    from spotlab.config import Config

    gerufen = []

    class FakeRobot:
        def ensure_client(self, name):
            gerufen.append(name)
            return object()

    b = Beobachtung.connect(
        Config(ip="1.2.3.4", username="u"),
        runs_dir=tmp_path,
        verbinder=lambda cfg: FakeRobot(),
    )
    b.beende()
    assert gerufen, "es wurde gar kein Client geholt"
    for name in gerufen:
        assert "lease" not in name.lower(), name
        assert "estop" not in name.lower(), name


def test_messfenster_landet_in_den_ereignissen(tmp_path):
    with Beobachtung.trocken(runs_dir=tmp_path) as b:
        with b.messfenster("B2-Fahrt", hz=50.0, ziel_m_s="0.12"):
            pass
        verzeichnis = b.lauf_verzeichnis
    zeilen = (verzeichnis / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
    fenster = [json.loads(z) for z in zeilen if json.loads(z)["art"] == "messfenster"]
    assert [f["daten"]["phase"] for f in fenster] == ["start", "ende"]
    assert fenster[0]["daten"]["ziel_m_s"] == "0.12"


def test_zustand_liefert_die_letzte_abtastung(tmp_path):
    b = Beobachtung.trocken(runs_dir=tmp_path)
    try:
        assert b.sampler._einmal() is True
        assert "pose" in b.zustand()
    finally:
        b.beende()


# ------------------------------------------------------------- Live-Zahlen


class _Verlauf:
    """Ein Abtaster, der nur einen vorgegebenen Verlauf liefert."""

    def __init__(self, saetze):
        self._saetze = tuple(saetze)
        self._thread = None

    def verlauf(self):
        return self._saetze

    def takt(self):
        return 50.0, True

    def setze_takt(self, hz, reich):
        pass

    def stop(self, timeout=2.0):
        pass


def _satz(t, x=0.0, y=0.0, yaw=0.0):
    return {"t_robot": t, "pose": [x, y, yaw]}


def _sitzung(saetze):
    return Beobachtung(quelle=None, recorder=None, sampler=_Verlauf(saetze))


def test_tempo_ist_weg_durch_zeit():
    saetze = [_satz(t / 50.0, x=0.2 * (t / 50.0)) for t in range(100)]
    assert _sitzung(saetze).tempo() == pytest.approx(0.2, abs=0.005)


def test_tempo_nimmt_den_betrag_nicht_die_x_komponente():
    """Beim Tablet-Fahren liegt die Fahrtrichtung nicht auf der odom-x-Achse."""
    saetze = [
        _satz(t / 50.0, x=0.12 * (t / 50.0), y=0.16 * (t / 50.0)) for t in range(100)
    ]
    assert _sitzung(saetze).tempo() == pytest.approx(0.2, abs=0.005)


def test_tempo_waehlt_nach_zeit_nicht_nach_anzahl():
    """Bei 10 Hz umfassen 512 Eintraege ueber 50 s -- ein Tempo darueber
    waere kein Tempo mehr, sondern ein Sitzungsmittel."""
    stillstand = [_satz(t / 10.0, x=0.0) for t in range(30)]        # 3 s
    fahrt = [_satz(3.0 + t / 10.0, x=0.3 * (t / 10.0)) for t in range(1, 21)]
    assert _sitzung(stillstand + fahrt).tempo() == pytest.approx(0.3, abs=0.02)


def test_tempo_ohne_genug_punkte_ist_none():
    assert _sitzung([_satz(0.0), _satz(0.02)]).tempo() is None
    assert _sitzung([]).tempo() is None


def test_drehrate_summiert_ueber_den_umschlag_hinweg():
    """2.5 Umdrehungen sind 2.5 Umdrehungen, nicht der Rest modulo 2 pi.
    Genau diesen Fehler hat matura-spot bei _Monitor schon einmal gemacht."""
    dauer, umdrehungen, n = 2.0, 2.5, 200
    saetze = [
        _satz(
            dauer * i / n,
            yaw=(umdrehungen * 2 * math.pi * i / n + math.pi) % (2 * math.pi) - math.pi,
        )
        for i in range(n + 1)
    ]
    erwartet = umdrehungen * 2 * math.pi / dauer
    assert _sitzung(saetze).drehrate() == pytest.approx(erwartet, rel=0.02)


def test_drehrate_hat_ein_vorzeichen():
    n = 100
    saetze = [_satz(2.0 * i / n, yaw=-0.5 * (2.0 * i / n)) for i in range(n + 1)]
    assert _sitzung(saetze).drehrate() == pytest.approx(-0.5, rel=0.02)


def test_ohne_zeitstempel_gibt_es_keine_zahl():
    """Fehlende Messwerte sind None, nie 0."""
    saetze = [{"pose": [0.0, 0.0, 0.0]} for _ in range(10)]
    sitzung = _sitzung(saetze)
    assert sitzung.tempo() is None
    assert sitzung.drehrate() is None


def test_stillstand_ist_null_nicht_none():
    """Gegenprobe: gemessene Null und fehlende Messung sind zweierlei."""
    saetze = [_satz(t / 50.0) for t in range(100)]
    assert _sitzung(saetze).tempo() == pytest.approx(0.0, abs=1e-9)


# ------------------------------------------------------------- Messfahrt-Umfang


def _erste_abtastung(verzeichnis):
    zeilen = (verzeichnis / "zustand.jsonl").read_text(encoding="utf-8").splitlines()
    return json.loads(zeilen[0])["daten"]


def test_ausserhalb_der_fenster_wird_reich_abgetastet(tmp_path):
    """Anders als im Schuelerlauf — und das ist Absicht.

    Nur der reiche Satz traegt µ, Schlupf, Motortemperaturen und Faults. Eine
    Messfahrt findet einmal statt; was zwischen den Fenstern fehlt, ist weg.
    """
    b = Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=0)
    with b:
        pass
    daten = _erste_abtastung(b.lauf_verzeichnis)
    for schluessel in ("feet_detail", "motor_temps", "faults", "velocity_vision"):
        assert schluessel in daten, schluessel


def test_die_schlanken_schluessel_bleiben_unveraendert(tmp_path):
    """Gegenprobe zur Regel „neue Felder kommen dazu, nie an ihre Stelle":
    die Live-Ansicht und alte Aufzeichnungen haengen an genau diesen."""
    b = Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=0)
    with b:
        pass
    daten = _erste_abtastung(b.lauf_verzeichnis)
    assert len(daten["pose"]) == 3
    assert len(daten["feet"]) == 4


def test_das_messfenster_faellt_hinterher_auf_reich_zurueck(tmp_path):
    """`Messfenster` stellt den vorherigen Takt wieder her. Waere die Basis
    weiterhin schlank, verlöre die Messfahrt nach dem ersten Fenster
    unbemerkt genau die Felder, für die sie gefahren wird."""
    b = Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=0)
    with b:
        with b.messfenster("B1", hz=50.0):
            pass
        assert b.sampler.takt() == (10.0, True)


def test_bilder_laufen_mit_und_stehen_vor_dem_abschluss(tmp_path):
    b = Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=50.0)
    with b:
        ende = time.monotonic() + 10.0
        while time.monotonic() < ende and b.bildzaehler()["bilder"] < 3:
            time.sleep(0.02)
    assert b.bildzaehler()["bilder"] >= 3
    assert b.mitschnitt._thread is None, "der Bildthread laeuft nach dem Abbau weiter"
    assert _lauf(tmp_path)["ergebnis"] == "ok"


def test_ohne_kameradienst_laeuft_die_messfahrt_trotzdem(tmp_path):
    """Die Zustandsabtastung ist die Hauptmessung. Sie darf nicht daran
    scheitern, dass ein Kameradienst fehlt — aber das Fehlen darf auch nicht
    stumm bleiben."""
    from spotlab.config import Config

    class FakeRobot:
        def ensure_client(self, name):
            if "image" in name:
                raise RuntimeError("kein Kameradienst")
            return object()

    b = Beobachtung.connect(
        Config(ip="1.2.3.4", username="u"),
        runs_dir=tmp_path,
        verbinder=lambda cfg: FakeRobot(),
    )
    b.beende()
    assert b.mitschnitt is None
    assert b.bildzaehler() is None
    assert "Kameradienst" in b.bild_hinweis
    assert _lauf(tmp_path)["ergebnis"] == "ok"
