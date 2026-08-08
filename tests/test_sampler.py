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
