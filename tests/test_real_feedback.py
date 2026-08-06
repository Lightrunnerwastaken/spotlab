from bosdyn.api import basic_command_pb2 as bc
from bosdyn.api import robot_command_pb2 as rc

from spotlab.backends.real.feedback import to_feedback


def _mobility():
    antwort = rc.RobotCommandFeedbackResponse()
    return antwort, antwort.feedback.synchronized_feedback.mobility_command_feedback


def test_stehend_ist_fertig():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.stand_feedback.status = bc.StandCommand.Feedback.STATUS_IS_STANDING
    rueck = to_feedback(antwort)
    assert rueck.done is True and "steht" in rueck.status


def test_aufstehen_laeuft_noch():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.stand_feedback.status = bc.StandCommand.Feedback.STATUS_IN_PROGRESS
    assert to_feedback(antwort).done is False


def test_sitzend_ist_fertig():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.sit_feedback.status = bc.SitCommand.Feedback.STATUS_IS_SITTING
    assert to_feedback(antwort).done is True


def test_am_ziel_ist_fertig():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.se2_trajectory_feedback.status = bc.SE2TrajectoryCommand.Feedback.STATUS_AT_GOAL
    rueck = to_feedback(antwort)
    assert rueck.done is True and "angekommen" in rueck.status


def test_vorzeitig_gestoppt_gilt_als_beendet():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_PROCESSING
    mobility.se2_trajectory_feedback.status = bc.SE2TrajectoryCommand.Feedback.STATUS_STOPPED
    assert to_feedback(antwort).done is True


def test_ueberschriebenes_kommando_gilt_als_abgelehnt():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_COMMAND_OVERRIDDEN
    assert to_feedback(antwort).rejected is True


def test_abgelaufenes_kommando_gilt_als_abgelehnt():
    antwort, mobility = _mobility()
    mobility.status = bc.RobotCommandFeedbackStatus.STATUS_COMMAND_TIMED_OUT
    assert to_feedback(antwort).rejected is True
