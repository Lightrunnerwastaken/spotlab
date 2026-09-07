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


def test_das_programm_ist_eine_datei_die_sich_starten_laesst():
    assert fahren.SKRIPT.is_file() and fahren.SKRIPT.name == "fahren.py"
    quelle = fahren.SKRIPT.read_text(encoding="utf-8")
    assert "spotlab.connect(" in quelle and "power_on()" in quelle and "stand()" in quelle
