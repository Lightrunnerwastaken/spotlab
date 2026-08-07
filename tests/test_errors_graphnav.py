from bosdyn.api.graph_nav import graph_nav_pb2, recording_pb2

from spotlab.backends.real.graphnav import nav_status
from spotlab.errors.graphnav import AUFNAHME_TEXTE, NAVIGATION_TEXTE, WEGPUNKT_TEXTE


def test_fehlendes_fiducial_sagt_was_zu_tun_ist():
    text = AUFNAHME_TEXTE[recording_pb2.StartRecordingResponse.STATUS_MISSING_FIDUCIALS]
    assert "Fiducial" in text
    assert "hin, dass" in text


def test_alte_karte_auf_dem_roboter_wird_erklaert():
    text = AUFNAHME_TEXTE[
        recording_pb2.StartRecordingResponse.STATUS_NOT_LOCALIZED_TO_EXISTING_MAP
    ]
    assert "Karte" in text and "leeren" in text


def test_wegpunkt_ohne_aufnahme():
    text = WEGPUNKT_TEXTE[recording_pb2.CreateWaypointResponse.STATUS_NOT_RECORDING]
    assert "Aufnahme" in text


def test_am_ziel_ist_fertig():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_REACHED_GOAL)
    assert zustand.fertig is True and zustand.gescheitert is False


def test_unterwegs_ist_weder_fertig_noch_gescheitert():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_FOLLOWING_ROUTE)
    assert zustand.fertig is False and zustand.gescheitert is False


def test_verloren_ist_gescheitert_und_deutsch():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_LOST)
    assert zustand.gescheitert is True
    assert "verloren" in zustand.status


def test_steckengeblieben_fragt_nach_hindernissen():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_STUCK)
    assert zustand.gescheitert is True
    assert "Weg" in zustand.status


def test_ohne_lokalisierung_verweist_auf_localize():
    zustand = nav_status(graph_nav_pb2.NavigationFeedbackResponse.STATUS_NO_LOCALIZATION)
    assert "localize" in zustand.status


def test_alle_texte_sind_deutsche_saetze():
    for tabelle in (AUFNAHME_TEXTE, WEGPUNKT_TEXTE, NAVIGATION_TEXTE):
        for text in tabelle.values():
            assert text and text[0].isupper() and text.endswith((".", "?"))


def test_unbekannter_status_faellt_nicht_um():
    zustand = nav_status(99999)
    assert zustand.gescheitert is True
    assert zustand.status


def test_errors_graphnav_haengt_an_keinem_backend():
    """Regressionstest gegen einen Importzyklus.

    backends/base.py importiert UnsupportedCapability aus errors. Importierte
    errors/graphnav.py seinerseits etwas aus backends, schnappte der Kreis zu,
    sobald backends.base zuerst geladen wird. Die Position der Importzeile
    hilft dagegen nicht — nur die Richtung der Abhängigkeit.
    """
    import pathlib

    import spotlab.errors.graphnav as modul

    quelle = pathlib.Path(modul.__file__).read_text(encoding="utf-8")
    for zeile in quelle.splitlines():
        if zeile.startswith(("import ", "from ")):
            assert "spotlab.backends" not in zeile, zeile


def test_backends_base_ist_zuerst_importierbar():
    """Der Zyklus zeigte sich nur bei dieser Importreihenfolge."""
    import subprocess
    import sys

    ergebnis = subprocess.run(
        [sys.executable, "-c",
         "import spotlab.backends.base; import spotlab.errors; print('ok')"],
        capture_output=True, text=True, timeout=60,
    )
    assert ergebnis.returncode == 0, ergebnis.stderr
