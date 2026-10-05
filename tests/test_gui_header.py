import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.config import Config, Limits  # noqa: E402
from spotlab.gui.header import Header  # noqa: E402
from spotlab.workshop.doctor import Check  # noqa: E402


def test_notaus_knopf_sendet_signal(qapp):
    kopf = Header()
    gedrueckt = []
    kopf.notaus.connect(lambda: gedrueckt.append(True))
    kopf.notaus_knopf.click()
    assert gedrueckt == [True]


def test_notaus_ohne_rueckfrage(qapp):
    """Wer den Not-Aus drückt, hat keine Zeit für einen Dialog."""
    import inspect

    import spotlab.gui.header as modul

    quelle = inspect.getsource(modul)
    assert "QMessageBox" not in quelle


def test_erklaerung_steht_dauerhaft_da(qapp):
    # Referenz festhalten: ein Wegwerf-Widget wird sofort abgeräumt und nimmt
    # das C++-Objekt mit (libshiboken-Fehler).
    kopf = Header()
    text = kopf.hinweis.text().lower()
    assert "motoren" in text
    assert "physische" in text or "tablet" in text


def test_konfiguration_wird_angezeigt(qapp):
    kopf = Header()
    kopf.zeige_config(
        Config(ip="192.168.80.3", username="u", nickname="Spot der Kanti", limits=Limits())
    )
    assert "Spot der Kanti" in kopf.status.text()
    assert "192.168.80.3" in kopf.status.text()


@pytest.mark.parametrize("backend, name", [
    ("physics", "Physik 3D"), ("mujoco", "3D-Wiedergabe"), ("sim", "2D"), ("dryrun", "Trockenlauf"),
])
def test_simulation_ersetzt_ip_lease_und_roboterhinweis(qapp, backend, name):
    kopf = Header()
    kopf.zeige_config(Config(ip="192.168.80.3", username="u", nickname="Kanti", limits=Limits()))
    kopf.zeige_simulation(backend)
    assert kopf.status.text() == f"Übungsraum · {name} · kein Roboter"
    assert kopf.lease.isHidden()
    assert "simulation" in kopf.hinweis.text().lower()

    kopf.zeige_getrennt()
    assert "192.168.80.3" in kopf.status.text()
    assert not kopf.lease.isHidden()
    assert "tablet" in kopf.hinweis.text().lower()


def test_der_echte_spot_bekommt_kein_simulationsschild(qapp):
    kopf = Header()
    kopf.zeige_config(Config(ip="192.168.80.3", username="u", nickname="Kanti", limits=Limits()))
    kopf.zeige_simulation("real")
    assert "192.168.80.3" in kopf.status.text()
    assert "tablet" in kopf.hinweis.text().lower()


def test_lauf_zustand_zeigt_akku_live(qapp):
    kopf = Header()
    kopf.zeige_zustand({"daten": {"battery": 61.2, "velocity": [0.3, 0.0, 0.0]}})
    assert "61" in kopf.akku.text()


def test_pruefung_faerbt_die_ampel(qapp):
    kopf = Header()
    kopf.zeige_pruefung(
        [Check("Netz", True, "antwortet"),
         Check("Lease", False, "gehalten von anna", "absprechen")]
    )
    assert kopf.ampel.objectName() in ("Warnung", "Gefahr")

    kopf.zeige_pruefung([Check("Netz", True, "antwortet")])
    assert kopf.ampel.objectName() == "Ok"


def test_getrennt_zustand(qapp):
    kopf = Header()
    kopf.zeige_getrennt()
    assert kopf.ampel.objectName() == "Gedaempft"
