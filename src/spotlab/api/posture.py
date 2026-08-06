"""Haltung: aufstehen und hinsetzen.

Beide blockieren, bis der Roboter die Haltung tatsächlich MELDET — nicht bis
eine geschätzte Zeit vergangen ist. sleep() lügt, Rückmeldung nicht.
"""

import time

from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.backends.base import Capability, require
from spotlab.errors import CommandRejected, SpotlabError

POLL_S = 0.25


def warte_auf(backend, kennung, timeout, was, schlaf=time.sleep, jetzt=time.monotonic):
    ende = jetzt() + timeout
    while True:
        rueck = backend.command_feedback(kennung)
        if rueck.rejected:
            raise CommandRejected(
                f"Der Roboter hat das Kommando '{was}' abgelehnt: {rueck.status}"
            )
        if rueck.done:
            return
        if jetzt() >= ende:
            raise SpotlabError(
                f"Der Roboter hat '{was}' nicht innerhalb von {timeout:.0f} s "
                f"abgeschlossen (zuletzt: {rueck.status})."
            )
        schlaf(POLL_S)


def _protokolliere(recorder, name, **daten):
    if recorder is not None:
        recorder.event("kommando", name=name, **daten)


def stand(backend, recorder, height=0.0, timeout=10.0, schlaf=time.sleep):
    require(backend, Capability.POSTURE, "aufstehen")
    kommando = RobotCommandBuilder.synchro_stand_command(body_height=float(height))
    _protokolliere(recorder, "stand", height=float(height))
    kennung = backend.send_command(kommando)
    warte_auf(backend, kennung, timeout, "aufstehen", schlaf)
    if recorder is not None:
        recorder.event("rückmeldung", name="stand", status="steht")


def sit(backend, recorder, timeout=10.0, schlaf=time.sleep):
    require(backend, Capability.POSTURE, "hinsetzen")
    kommando = RobotCommandBuilder.synchro_sit_command()
    _protokolliere(recorder, "sit")
    kennung = backend.send_command(kommando)
    warte_auf(backend, kennung, timeout, "hinsetzen", schlaf)
    if recorder is not None:
        recorder.event("rückmeldung", name="sit", status="sitzt")
