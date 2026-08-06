"""Die tief verschachtelte SDK-Rückmeldung auf den schmalen Feedback-Typ abbilden.

Ohne diese Naht müsste jedes Verb in api/ Protobuf-Interna kennen und das
Trockenlauf-Backend sie nachbauen.
"""

from bosdyn.api import basic_command_pb2 as bc

from spotlab.backends.base import Feedback

_ABGELEHNT = {
    bc.RobotCommandFeedbackStatus.STATUS_COMMAND_OVERRIDDEN:
        "vom nächsten Kommando überschrieben",
    bc.RobotCommandFeedbackStatus.STATUS_COMMAND_TIMED_OUT:
        "abgelaufen (zu spät nachgesendet)",
    bc.RobotCommandFeedbackStatus.STATUS_ROBOT_FROZEN:
        "Roboter ist eingefroren (Not-Aus?)",
    bc.RobotCommandFeedbackStatus.STATUS_UNKNOWN:
        "unbekannter Zustand",
}


def to_feedback(antwort):
    mobility = antwort.feedback.synchronized_feedback.mobility_command_feedback

    if mobility.status in _ABGELEHNT:
        return Feedback(done=False, status=_ABGELEHNT[mobility.status], rejected=True)

    welches = mobility.WhichOneof("feedback")

    if welches == "stand_feedback":
        fertig = mobility.stand_feedback.status == bc.StandCommand.Feedback.STATUS_IS_STANDING
        return Feedback(done=fertig, status="steht" if fertig else "steht auf")

    if welches == "sit_feedback":
        fertig = mobility.sit_feedback.status == bc.SitCommand.Feedback.STATUS_IS_SITTING
        return Feedback(done=fertig, status="sitzt" if fertig else "setzt sich")

    if welches == "se2_trajectory_feedback":
        status = mobility.se2_trajectory_feedback.status
        if status == bc.SE2TrajectoryCommand.Feedback.STATUS_AT_GOAL:
            return Feedback(done=True, status="angekommen")
        if status == bc.SE2TrajectoryCommand.Feedback.STATUS_STOPPED:
            return Feedback(done=True, status="angekommen (vorzeitig gestoppt)")
        return Feedback(done=False, status="unterwegs")

    if welches == "stop_feedback":
        return Feedback(done=True, status="gestoppt")

    if welches == "se2_velocity_feedback":
        return Feedback(done=True, status="fährt")

    return Feedback(done=False, status="läuft")
