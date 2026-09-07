"""fahren.py: mit W A S D Q E durch den Raum -- der Kern mit Attrappen-Spot und Uhr."""

from spotlab.record import fahrt
from spotlab.workshop import fahren


class _Spot:
    def __init__(self):
        self.befehle = []

    def walk(self, vx=0.0, vy=0.0, wz=0.0, duration=1.0, stop=True):
        self.befehle.append(("walk", round(vx, 3), round(vy, 3), round(wz, 3), stop))

    def stop(self):
        self.befehle.append(("stop",))


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def schlaf(self, s):
        self.t += s


def test_ein_frischer_befehl_faehrt_ein_alter_haelt_einmal(tmp_path):
    spot, uhr = _Spot(), _Uhr()
    fahrt.schreibe(tmp_path, 0.4, 0.0, 0.8, jetzt=uhr)
    runden = iter([True] * 4 + [False])
    fahren.fahre(spot, tmp_path, jetzt=uhr, schlaf=uhr.schlaf, takt_s=0.3, laeuft=lambda: next(runden))
    # Runde 1 und 2 frisch (0.3 s alt), danach aelter als TOTMANN_S: einmal anhalten,
    # dann Ruhe -- und am Ende der Schleife haelt er noch einmal, immer.
    assert spot.befehle == [("walk", 0.4, 0.0, 0.8, False), ("walk", 0.4, 0.0, 0.8, False),
                            ("stop",), ("stop",)]


def test_am_ende_haelt_er_immer(tmp_path):
    spot, uhr = _Spot(), _Uhr()
    fahren.fahre(spot, tmp_path, jetzt=uhr, schlaf=uhr.schlaf, laeuft=lambda: False)
    assert spot.befehle == [("stop",)]


def test_das_programm_liegt_im_projekt_beispiele(tmp_path):
    """Laeufe landen neben dem Skript. Ein Skript im PAKET legte sie unter
    src/spotlab/workshop/runs/ an, wo der Watcher nie sucht -- das Uebungsfenster
    erfuhr das Lauf-Verzeichnis nie, die Tasten schrieben ins Leere (07.09.2026)."""
    from spotlab.workshop.beispiele import bereitstellen

    bereitstellen(tmp_path)
    skript = fahren.skript_in(tmp_path)
    assert skript == tmp_path / "Beispiele" / "fahren.py" and skript.is_file()
    quelle = skript.read_text(encoding="utf-8")
    assert "spotlab.connect(" in quelle and "power_on()" in quelle and "stand()" in quelle
    assert "from spotlab.workshop.fahren import fahre" in quelle
    assert not hasattr(fahren, "SKRIPT"), "kein Skript im Paket -- Laeufe landen neben dem Skript"


def test_fahren_faehrt_wirklich_als_prozess(tmp_path):
    """Ein Prozess, der wirklich startet: fahren.py im 2D-Sim, Befehle ueber fahrt.json,
    Bewegung in der Aufzeichnung, freundlicher Stopp beendet ihn."""
    import json
    import time

    from spotlab.workshop.beispiele import bereitstellen
    from spotlab.workshop.control import stoppe_freundlich
    from spotlab.workshop.launcher import start_script
    from tests_zeitgrenzen import TEST_TIMEOUT_S

    bereitstellen(tmp_path)
    skript = fahren.skript_in(tmp_path)
    prozess = start_script(skript, backend="sim", nur_trocken=True,
                           umgebung={"SPOTLAB_RAUM": "leer"})
    lauf = None
    try:
        from spotlab.laufsuche import lauf_verzeichnisse

        frist = time.monotonic() + TEST_TIMEOUT_S
        while lauf is None and time.monotonic() < frist:
            laeufe = lauf_verzeichnisse(tmp_path)          # so sucht auch der Watcher
            lauf = laeufe[0] if laeufe else None
            time.sleep(0.1)
        assert lauf is not None, "kein Lauf-Verzeichnis"
        ende = time.monotonic() + 4.0                 # aufstehen dauert; dann rollt es
        while time.monotonic() < ende:
            fahrt.schreibe(lauf, 0.4, 0.0, 0.0)
            time.sleep(0.1)
        stoppe_freundlich(lauf)
        prozess.wait(timeout=TEST_TIMEOUT_S)
    finally:
        if prozess.poll() is None:
            prozess.kill()
    zeilen = [json.loads(z) for z in (lauf / "zustand.jsonl").read_text(encoding="utf-8").splitlines()
              if z.strip()]
    xs = [z["daten"]["pose"][0] for z in zeilen if "pose" in (z.get("daten") or {})]
    assert xs and max(xs) - min(xs) > 0.2, (min(xs) if xs else None, max(xs) if xs else None)
