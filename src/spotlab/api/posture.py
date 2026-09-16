"""Haltung: aufstehen und hinsetzen.

Beide blockieren, bis der Roboter die Haltung tatsächlich MELDET — nicht bis
eine geschätzte Zeit vergangen ist. sleep() lügt, Rückmeldung nicht.
"""

import time

from bosdyn.client.robot_command import RobotCommandBuilder

from spotlab.api.state import verhaltensfehler
from spotlab.backends.base import Capability, require
from spotlab.errors import VERHALTENSFEHLER_HINWEIS, CommandRejected, SpotlabError

POLL_S = 0.25

# Die Ursachen, wie der Roboter sie nennt — in Worten, die ein Schüler versteht.
URSACHEN = {
    "CAUSE_FALL": "nach einem Sturz",
    "CAUSE_HARDWARE": "wegen eines Hardwarefehlers",
    "CAUSE_LEASE_TIMEOUT": "weil das Lease ausgelaufen ist",
}


def _ursache(fehler):
    """„wegen eines Hardwarefehlers — spot.fl.kna.mc.fault: Current error".

    Das Teil dahinter kommt aus `verhaltensfehler()`; ohne Treffer bleibt es bei
    der Ursache, wie der Roboter sie nennt.
    """
    text = URSACHEN.get(fehler.get("ursache"), str(fehler.get("ursache")))
    hardware = fehler.get("hardware") or []
    if hardware:
        text += " — " + "; ".join(hardware)
    return text


def _ablehnung(backend, was, status):
    """Die Meldung zu einem abgelehnten Kommando — mit Ursache, wenn es eine gibt.

    Lauf 20260911T162238Z am Schul-Spot: `stand()` wurde abgelehnt, und die
    Meldung lautete „vom nächsten Kommando überschrieben". Die wahre Ursache —
    ein Verhaltensfehler nach einem Sturz — stand nur in diagnose.log, weil erst
    der Abbau daran scheiterte. Der Roboter meldet den Fehler aber in JEDEM
    RobotState. Hier wird nachgefragt; ohne Befund bleibt es bei der bisherigen
    Meldung, denn eine Ursache, die nicht geprüft ist, wird nicht behauptet.
    """
    fehler = verhaltensfehler(backend)
    if not fehler:
        return f"Der Roboter hat das Kommando '{was}' abgelehnt: {status}"
    ursachen = ", ".join(_ursache(f) for f in fehler)
    return (
        f"Der Roboter hat das Kommando '{was}' abgelehnt, weil er einen "
        f"Verhaltensfehler hat ({ursachen}). " + VERHALTENSFEHLER_HINWEIS
    )


def warte_auf(backend, kennung, timeout, was, schlaf=time.sleep, jetzt=time.monotonic):
    ende = jetzt() + timeout
    while True:
        rueck = backend.command_feedback(kennung)
        if rueck.rejected:
            raise CommandRejected(_ablehnung(backend, was, rueck.status))
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
