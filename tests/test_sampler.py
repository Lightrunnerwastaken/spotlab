import threading

from spotlab.backends.dryrun import DryRunBackend
from spotlab.record.run import RunRecorder
from spotlab.record.sampler import StateSampler


def test_abtaster_schreibt_und_stoppt(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=200.0)
    abtaster.start()
    threading.Event().wait(0.15)
    abtaster.stop()
    rec.finish("ok")

    zeilen = (rec.dir / "zustand.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) >= 2
    assert abtaster._thread is None


def test_abtaster_ueberlebt_fehler_im_backend(tmp_path):
    class Kaputt(DryRunBackend):
        def robot_state(self):
            raise RuntimeError("Verbindung weg")

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(Kaputt(), rec, hz=200.0)
    abtaster.start()
    threading.Event().wait(0.1)
    abtaster.stop()  # darf nicht werfen
    rec.finish("ok")


def test_stopp_markierung_bricht_den_lauf_ab(tmp_path, monkeypatch):
    """Die GUI legt <lauf>/stopp an; der Abtaster löst KeyboardInterrupt im Hauptthread aus."""
    from spotlab.record.run import STOPP_DATEI

    gerufen = []
    monkeypatch.setattr("spotlab.record.sampler._thread.interrupt_main",
                        lambda: gerufen.append(True))

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=200.0)
    abtaster.start()
    threading.Event().wait(0.05)
    (rec.dir / STOPP_DATEI).touch()
    threading.Event().wait(0.15)
    abtaster.stop()
    rec.finish("abgebrochen")

    assert gerufen, "interrupt_main wurde nicht aufgerufen"


def test_stopp_wird_nur_einmal_ausgeloest(tmp_path, monkeypatch):
    """Sonst hagelt es KeyboardInterrupts, während der Abbau läuft."""
    from spotlab.record.run import STOPP_DATEI

    gerufen = []
    monkeypatch.setattr("spotlab.record.sampler._thread.interrupt_main",
                        lambda: gerufen.append(True))

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    (rec.dir / STOPP_DATEI).touch()
    abtaster = StateSampler(DryRunBackend(), rec, hz=500.0)
    abtaster.start()
    threading.Event().wait(0.2)
    abtaster.stop()
    rec.finish("abgebrochen")

    assert len(gerufen) == 1


# --------------------------------------------------- Takt und Umfang (Stufe 7)


def test_takt_umschalten_wirkt(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=10.0)
    assert abtaster.takt() == (10.0, False)
    abtaster.setze_takt(50.0, True)
    assert abtaster.takt() == (50.0, True)


def _saetze(rec):
    import json

    return [
        json.loads(z)
        for z in (rec.dir / "zustand.jsonl").read_text(encoding="utf-8").splitlines()
        if z.strip()
    ]


def test_reicher_takt_schreibt_reiche_saetze(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=200.0)
    abtaster.setze_takt(200.0, True)
    abtaster.start()
    threading.Event().wait(0.15)
    abtaster.stop()
    saetze = _saetze(rec)
    assert saetze and "feet_detail" in saetze[-1]["daten"]


def test_schlanker_takt_schreibt_schlanke_saetze(tmp_path):
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=200.0)
    abtaster.start()
    threading.Event().wait(0.15)
    abtaster.stop()
    saetze = _saetze(rec)
    assert saetze
    assert "feet_detail" not in saetze[-1]["daten"]
    # Die vier Immer-Felder fehlen trotzdem nie.
    assert {"z", "roll", "pitch", "t_robot"} <= set(saetze[-1]["daten"])


def test_langsamer_backend_erzeugt_keine_bursts(tmp_path):
    """Nichts wird nachgeholt — sonst saehen Bursts in der Auswertung wie Dynamik aus."""
    import time as _time

    class Langsam(DryRunBackend):
        def robot_state(self):
            _time.sleep(0.02)
            return super().robot_state()

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(Langsam(), rec, hz=1000.0)      # Soll 1 ms, Ist ~20 ms
    abtaster.start()
    threading.Event().wait(0.3)
    abtaster.stop()
    assert 3 <= len(_saetze(rec)) <= 30, len(_saetze(rec))


# ------------------------------------------- Ringpuffer fuer die Live-Anzeige
#
# Die Live-Anzeige des Beobachter-Modus liest von hier. Ein zweiter
# Abfragestrom nebenher waere eine zweite Wahrheit ueber denselben Roboter --
# und wuerde die Messung stoeren, um die es eigentlich geht.


def _abtaster(tmp_path, hz=50.0):
    return StateSampler(DryRunBackend(), RunRecorder(tmp_path, None, backend="dryrun"), hz=hz)


def test_verlauf_ist_anfangs_leer(tmp_path):
    assert _abtaster(tmp_path).verlauf() == ()


def test_verlauf_haelt_die_geschriebenen_abtastungen(tmp_path):
    abtaster = _abtaster(tmp_path)
    for _ in range(3):
        assert abtaster._einmal() is True
    verlauf = abtaster.verlauf()
    assert len(verlauf) == 3
    assert all("pose" in satz and "t_robot" in satz for satz in verlauf)


def test_verlauf_ist_begrenzt(tmp_path):
    """Eine lange Sitzung darf nicht den Speicher fuellen."""
    from spotlab.record.sampler import RING

    abtaster = _abtaster(tmp_path)
    for _ in range(RING + 25):
        abtaster._einmal()
    assert len(abtaster.verlauf()) == RING


def test_verlauf_ist_eine_kopie(tmp_path):
    abtaster = _abtaster(tmp_path)
    abtaster._einmal()
    erste = abtaster.verlauf()
    abtaster._einmal()
    assert len(erste) == 1, "der zurueckgegebene Verlauf hat sich mitveraendert"


def test_ein_fehlschlag_landet_nicht_im_ring(tmp_path):
    """Sonst zeigte die Live-Anzeige eine Zahl aus einer Abtastung, die es
    nie gab."""

    class Kaputt(DryRunBackend):
        def robot_state(self):
            raise RuntimeError("Verbindung weg")

    abtaster = StateSampler(
        Kaputt(), RunRecorder(tmp_path, None, backend="dryrun"), hz=50.0
    )
    assert abtaster._einmal() is False
    assert abtaster.verlauf() == ()


# ------------------------------- Der Takt muss die Rate wirklich liefern (12.08.2026)


def test_der_takt_wartet_nicht_ueber_event_wait():
    """Die 34 Hz einer 50-Hz-Messfahrt lagen an EINER Zeile.

    `threading.Event.wait()` geht unter Windows ueber den GROBEN Zeitgeber
    (Aufloesung 15.6 ms): 20 ms angefordert -> 31 ms geliefert -> 32 statt
    50 Hz. `time.sleep()` nutzt seit Python 3.11 hochaufloesende Timer.
    Gemessen am 12.08.2026: 34.0 gegen 49.0 Hz im vollen Takt; die reale
    Messfahrt kam auf 34.1 Hz.

    Geprueft wird die QUELLE, nicht die Laufzeit -- ein Ratentest haengt an der
    Maschinenlast und pruefte die falsche Sache. Der Fehler, gegen den dieser
    Test steht, ist jemand, der `_warte()` wieder durch `self._stopp.wait()`
    ersetzt, weil es kuerzer aussieht.
    """
    import inspect
    import re

    schleife = inspect.getsource(StateSampler._schleife)
    assert not re.search(r"_stopp\.wait\(", schleife), (
        "Der Takt wartet wieder ueber Event.wait() -- das kostet unter Windows "
        "ein Drittel der Abtastrate."
    )
    assert "_warte(" in schleife


def test_die_wartezeit_ist_genauer_als_der_grobe_zeitgeber(tmp_path):
    """Gegenprobe zur Quelltextpruefung: die Zahl muss auch stimmen.

    Grenze bei 26 ms fuer 20 ms angefordert. Der alte Weg lieferte im Median
    30.9 ms, der neue 20.4 -- dazwischen ist Luft fuer Last. Median statt
    Maximum, damit ein einzelner Aussetzer den Test nicht kippt.
    """
    import statistics
    import time

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=50.0)
    zeiten = []
    for _ in range(15):
        t = time.perf_counter()
        abtaster._warte(0.020)
        zeiten.append((time.perf_counter() - t) * 1000)
    rec.finish("ok")
    median = statistics.median(zeiten)
    assert median < 26.0, f"Median {median:.1f} ms -- der grobe Zeitgeber ist zurueck"


def test_ein_gesetzter_stopp_beendet_die_wartezeit_sofort(tmp_path):
    """In Stuecken schlafen hat genau diesen Zweck: bei 10 Hz (100 ms Periode)
    darf ein Stopp nicht erst nach einer vollen Periode greifen."""
    import time

    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(DryRunBackend(), rec, hz=10.0)
    abtaster._stopp.set()
    t = time.perf_counter()
    abtaster._warte(1.0)
    rec.finish("ok")
    assert (time.perf_counter() - t) < 0.05


def test_ein_ratenwechsel_waehrend_der_abtastung_wirkt_schon_auf_den_naechsten_tick(tmp_path):
    """Die Periode wird NACH dem Zeitstempel der Abtastung gelesen.

    Vorher las die Schleife die Periode, holte dann den Zustand und stempelte
    ihn. Fiel das Hochschalten auf 50 Hz dazwischen, trug die Abtastung einen
    Stempel NACH dem Fensterstart, schlief aber noch den alten 100-ms-Takt --
    und der Lueckenmelder mass diesen Takt gegen die 50-Hz-Erwartung des
    Fensters: "Luecke 0.101 s", einmal in fuenf Laeufen (06.09.2026,
    test_die_messfahrt_meldet_keine_falschen_luecken). Hier faellt der
    Wechsel absichtlich IN die Abtastung.
    """

    class Umschalter(DryRunBackend):
        abtaster = None

        def robot_state(self):
            zustand = super().robot_state()
            if self.abtaster is not None and self.abtaster.takt()[0] == 10.0:
                self.abtaster.setze_takt(50.0, True)
            return zustand

    backend = Umschalter()
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    abtaster = StateSampler(backend, rec, hz=10.0)
    backend.abtaster = abtaster
    abtaster.start()
    threading.Event().wait(0.25)
    abtaster.stop()
    rec.finish("ok")

    saetze = _saetze(rec)
    assert len(saetze) >= 3, len(saetze)
    abstand = saetze[1]["t"] - saetze[0]["t"]
    assert abstand < 0.06, f"alter 100-ms-Takt nach dem Wechsel: {abstand:.3f} s"
