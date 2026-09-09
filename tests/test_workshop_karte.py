"""Der Kern von „Karte verbessern": laden, nachbearbeiten, zurueckschreiben.

Ohne Roboter: `spot` ist eine Attrappe mit `load_map` und `process_map`. Warum
das ueberhaupt ein LAUF ist und keine Arbeit der GUI, steht in
`workshop/karte.py` -- Hochladen braucht ein Lease.
"""

from types import SimpleNamespace

from spotlab.maps.nachbearbeitung import Nachbearbeitung
from spotlab.workshop import karte as kartenarbeit


class _Spot:
    def __init__(self, bericht=None, wegpunkte=3, kanten=2):
        self.protokoll = []
        self.bericht = bericht if bericht is not None else Nachbearbeitung(2, 5, ("gemacht",))
        self._wegpunkte, self._kanten = wegpunkte, kanten

    def load_map(self, name=None):
        self.protokoll.append(("load_map", name))
        graph = SimpleNamespace(waypoints=[0] * self._wegpunkte, edges=[0] * self._kanten)
        return SimpleNamespace(name=name or "aktiv", graph=graph)

    def process_map(self, melde=None, fiducial=True, odometry=True):
        self.protokoll.append(("process_map", fiducial, odometry))
        if melde is not None:
            for text in self.bericht.meldungen:
                melde(text)
        return self.bericht


def test_die_karte_wird_geladen_und_dann_nachbearbeitet():
    spot = _Spot()
    gemeldet = []
    bericht = kartenarbeit.verbessere(spot, "flur", melde=gemeldet.append)
    assert spot.protokoll == [("load_map", "flur"), ("process_map", True, True)]
    assert bericht.neue_kanten == 2
    assert any("flur" in m and "3 Wegpunkte" in m for m in gemeldet)
    assert "gemacht" in gemeldet


def test_ohne_ergebnis_wird_es_gesagt():
    spot = _Spot(bericht=Nachbearbeitung(None, None, ("Dienst fehlt",)))
    gemeldet = []
    kartenarbeit.verbessere(spot, melde=gemeldet.append)
    assert spot.protokoll[0] == ("load_map", None), "ohne Namen die aktive Karte"
    assert any("bleibt, wie sie war" in m for m in gemeldet)


def test_die_schleifenarten_lassen_sich_einschraenken():
    spot = _Spot()
    kartenarbeit.verbessere(spot, "flur", melde=lambda _t: None, fiducial=False)
    assert ("process_map", False, True) in spot.protokoll


def test_karte_aus_der_umgebung():
    assert kartenarbeit.karte_aus_umgebung({"SPOTLAB_KARTE": "flur"}) == "flur"
    assert kartenarbeit.karte_aus_umgebung({}) is None


def test_das_programm_liegt_im_projekt_beispiele(tmp_path):
    assert kartenarbeit.skript_in(tmp_path).name == "karte_verbessern.py"
    assert kartenarbeit.skript_in(tmp_path).parent.name == "Beispiele"


def test_die_vorlage_wird_mit_den_beispielen_ausgeliefert(tmp_path):
    """Sonst startet der Knopf ins Leere -- Laeufe landen neben dem Skript."""
    from spotlab.workshop.beispiele import bereitstellen

    bereitstellen(tmp_path)
    assert kartenarbeit.skript_in(tmp_path).is_file()
