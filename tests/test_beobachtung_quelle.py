"""Die Sicherheitsaussage des Beobachter-Modus, als Test.

Der Modus darf den Roboter nicht bewegen koennen. Nicht „soll nicht" —
„kann nicht": die Quelle hat gar keine Kommando-Methode. Das ist staerker als
eine Capability-Pruefung, die erst zur Laufzeit wirft.

Daran haengt, ob das Werkzeug vor Abnahmepunkt A1 benutzt werden darf.
"""

import re
from pathlib import Path

from spotlab.beobachtung.quelle import Zustandsquelle

WURZEL = Path(__file__).resolve().parents[1] / "src" / "spotlab" / "beobachtung"

VERBOTEN = (
    "send_command", "power_on", "power_off", "walk", "move", "stand", "sit",
    "stop", "navigate", "navigate_step", "upload_map", "localize", "close",
)


class FakeStateClient:
    def __init__(self):
        self.abrufe = 0

    def get_robot_state(self):
        self.abrufe += 1
        return "zustand"


def test_die_quelle_liefert_den_zustand():
    client = FakeStateClient()
    assert Zustandsquelle(client).robot_state() == "zustand"
    assert client.abrufe == 1


def test_die_quelle_hat_nur_diese_eine_methode():
    oeffentlich = {n for n in dir(Zustandsquelle) if not n.startswith("_")}
    assert oeffentlich == {"robot_state"}, f"unerwartete Oberflaeche: {oeffentlich}"


def test_die_quelle_hat_keine_kommando_methode():
    for name in VERBOTEN:
        assert not hasattr(Zustandsquelle, name), name


def test_die_quelle_genuegt_dem_abtaster():
    """StateSampler braucht vom Backend genau robot_state() -- sonst nichts."""
    import inspect

    from spotlab.record.sampler import StateSampler

    quelltext = inspect.getsource(StateSampler)
    benutzt = set(re.findall(r"self\._backend\.(\w+)", quelltext))
    assert benutzt == {"robot_state"}, (
        f"Der Abtaster benutzt inzwischen mehr als robot_state(): {benutzt}. "
        "Dann reicht die Nur-Lese-Quelle nicht mehr."
    )


def test_kein_lease_und_kein_estop_unter_beobachtung():
    """Dieselbe harte Regel wie bei maps/. Geprueft ueber IMPORTZEILEN --
    ein Treffer im Docstring war in diesem Projekt schon zweimal ein Fehlalarm."""
    muster = re.compile(r"^\s*(?:from|import)\s+.*(lease|estop)", re.IGNORECASE | re.M)
    dateien = list(WURZEL.rglob("*.py"))
    assert dateien, "Verzeichnis beobachtung/ nicht gefunden"
    for datei in dateien:
        treffer = muster.findall(datei.read_text(encoding="utf-8"))
        assert not treffer, f"{datei.name} importiert Lease oder E-Stop: {treffer}"
