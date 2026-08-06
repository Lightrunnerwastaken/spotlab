"""`spotlab doctor` — beantwortet „warum geht es nicht" in der Reihenfolge,
in der die Dinge tatsächlich schiefgehen.

Die Kette bricht nach dem ersten Fehlschlag ab: ohne Netz keine Anmeldung, ohne
Anmeldung kein Lease. Weiterzuprüfen erzeugte nur Folgefehler, die vom
eigentlichen Problem ablenken.
"""

from dataclasses import dataclass

from spotlab.errors import ConfigMissing, translate


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    rat: str = ""


STUFEN = ("Konfiguration", "Netz", "Anmeldung", "Zeitsync", "Not-Aus", "Lease", "Akku")


def diagnose(cfg=None, robot_bauen=None, passwort_lesen=None):
    from spotlab.backends.real.estop import LEVEL_NAMEN
    from spotlab.backends.real.lease import holder_of
    from spotlab.backends.real.session import _standard_robot
    from spotlab.config import load_config, load_password

    robot_bauen = robot_bauen or _standard_robot
    passwort_lesen = passwort_lesen or load_password
    pruefungen = []

    if cfg is None:
        try:
            cfg = load_config()
        except ConfigMissing as fehler:
            return [
                Check(
                    "Konfiguration", False, str(fehler),
                    "Einmalig einrichten mit `spotlab login`.",
                )
            ]
    pruefungen.append(
        Check("Konfiguration", True, f"{cfg.nickname} unter {cfg.ip} als '{cfg.username}'")
    )

    try:
        robot = robot_bauen(cfg)
    except Exception as fehler:
        return pruefungen + [_fehler("Netz", fehler, cfg.ip)]
    pruefungen.append(Check("Netz", True, f"{cfg.ip} antwortet"))

    try:
        robot.authenticate(cfg.username, passwort_lesen(cfg.username))
    except Exception as fehler:
        return pruefungen + [_fehler("Anmeldung", fehler, cfg.ip)]
    pruefungen.append(Check("Anmeldung", True, f"als '{cfg.username}' angemeldet"))

    try:
        robot.time_sync.wait_for_sync()
    except Exception as fehler:
        return pruefungen + [
            Check("Zeitsync", False, str(fehler),
                  "Windows-Uhrzeit automatisch stellen lassen.")
        ]
    pruefungen.append(Check("Zeitsync", True, "Uhren laufen synchron"))

    try:
        from bosdyn.client.estop import EstopClient

        status = robot.ensure_client(EstopClient.default_service_name).get_status()
        stufe = LEVEL_NAMEN.get(status.stop_level, "unbekannt")
        frei = stufe == "frei"
        pruefungen.append(
            Check("Not-Aus", frei, stufe, "" if frei else "Am Tablet oder Knopf freigeben.")
        )
        if not frei:
            return pruefungen
    except Exception as fehler:
        return pruefungen + [_fehler("Not-Aus", fehler, cfg.ip)]

    try:
        from bosdyn.client.lease import LeaseClient

        halter = holder_of(robot.ensure_client(LeaseClient.default_service_name))
        if halter and not halter.startswith("spotlab/"):
            pruefungen.append(
                Check("Lease", False, f"gehalten von {halter}",
                      "Absprechen, dann `spotlab lease --take`.")
            )
        elif halter:
            pruefungen.append(
                Check("Lease", False, f"gehalten von {halter}",
                      "Läuft dort noch ein Skript? Sonst `spotlab lease --take`.")
            )
        else:
            pruefungen.append(Check("Lease", True, "frei"))
    except Exception as fehler:
        return pruefungen + [_fehler("Lease", fehler, cfg.ip)]

    try:
        from bosdyn.client.robot_state import RobotStateClient

        zustand = robot.ensure_client(RobotStateClient.default_service_name).get_robot_state()
        prozent = (
            zustand.battery_states[0].charge_percentage.value
            if zustand.battery_states
            else 0.0
        )
        genug = prozent >= 20.0
        pruefungen.append(
            Check("Akku", genug, f"{prozent:.0f} %",
                  "" if genug else "Auf die Ladestation stellen.")
        )
    except Exception as fehler:
        pruefungen.append(_fehler("Akku", fehler, cfg.ip))

    return pruefungen


def _fehler(name, fehler, ip):
    uebersetzt = translate(fehler, ip=ip)
    if uebersetzt is not None:
        return Check(name, False, type(fehler).__name__, str(uebersetzt))
    return Check(name, False, f"{type(fehler).__name__}: {fehler}", "")
