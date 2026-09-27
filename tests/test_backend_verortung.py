"""Die Verortung für die Steuerzentrale (Teil 3): wo Spot in der Karte steht und in der Skizze.

Beides kommt aus EINER `GetLocalizationStateResponse` -- die Lage im Seed-Rahmen der Karte aus
`localization`, die im Rahmen „vision“ aus `robot_kinematics` derselben Antwort. Nur so gehören
die beiden Lagen zum selben Augenblick, und die Karte fällt deckungsgleich auf die Skizze.
"""

import math

import pytest
from bosdyn.api.graph_nav import graph_nav_pb2
from test_workshop_folgen import _baum

from spotlab.backends.base import Verortung
from spotlab.backends.real import graphnav


class _Karte:
    def __init__(self, antwort):
        self.antwort = antwort

    def get_localization_state(self, **kw):
        return self.antwort


class _Robot:
    def __init__(self, antwort):
        self._client = _Karte(antwort)

    def ensure_client(self, name):
        return self._client


def _antwort(wegpunkt="wp-3", seed=(2.0, 1.0, math.radians(90.0)), vision=(5.0, 6.0, 0.3),
             verloren=False, angenommen=18, abgelehnt=2):
    a = graph_nav_pb2.GetLocalizationStateResponse()
    a.localization.waypoint_id = wegpunkt
    x, y, gier = seed
    a.localization.seed_tform_body.position.x = x
    a.localization.seed_tform_body.position.y = y
    a.localization.seed_tform_body.rotation.w = math.cos(gier / 2.0)
    a.localization.seed_tform_body.rotation.z = math.sin(gier / 2.0)
    if vision is not None:
        a.robot_kinematics.transforms_snapshot.CopyFrom(_baum(*vision))
    a.lost_detector_state.is_lost = verloren
    a.lost_detector_state.total_num_accepted_localizations = angenommen
    a.lost_detector_state.total_num_rejected_localizations = abgelehnt
    return a


def test_verortet_kommen_beide_lagen_aus_derselben_antwort():
    v = graphnav.verortung(_Robot(_antwort()))
    assert isinstance(v, Verortung) and v.wegpunkt == "wp-3"
    assert v.seed == pytest.approx((2.0, 1.0, math.radians(90.0)))
    assert v.vision == pytest.approx((5.0, 6.0, 0.3))
    assert (v.verloren, v.angenommen, v.abgelehnt) == (False, 18, 2)


def test_nicht_verortet_ist_keine_verortung():
    assert graphnav.verortung(_Robot(_antwort(wegpunkt=""))) is None


def test_verloren_steht_in_der_verortung():
    assert graphnav.verortung(_Robot(_antwort(verloren=True))).verloren is True


def test_ohne_vision_im_rahmenbaum_fehlt_nur_die_lage_in_der_skizze():
    v = graphnav.verortung(_Robot(_antwort(vision=None)))
    assert v.vision is None and v.seed == pytest.approx((2.0, 1.0, math.radians(90.0)))


def test_realspot_reicht_die_verortung_durch():
    from spotlab.backends.real.session import RealSpot

    spot = RealSpot.__new__(RealSpot)
    spot._robot = _Robot(_antwort())
    assert spot.verortung().wegpunkt == "wp-3"


def test_die_aufnahme_nimmt_die_clients_derselben_verbindung():
    from spotlab.backends.real.session import RealSpot
    from spotlab.maps.session import RecordingSession

    gefragt = []

    class _Verbindung:
        def ensure_client(self, name):
            gefragt.append(name)
            return f"client:{name}"

    spot = RealSpot.__new__(RealSpot)
    spot._robot = _Verbindung()
    sitzung = spot.aufnahme_sitzung()
    assert isinstance(sitzung, RecordingSession) and sitzung._robot is spot._robot
    assert len(gefragt) == 3, "Aufnahme, GraphNav, Nachbearbeitung"
