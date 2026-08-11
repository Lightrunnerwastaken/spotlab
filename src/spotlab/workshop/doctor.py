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


STUFEN = (
    "Konfiguration", "Netz", "Anmeldung", "Zeitsync", "Zustandsstrom",
    "Not-Aus", "Not-Aus-Endpunkt", "Lease", "Akku",
)

STROM_DIENST = "robot-state-streaming"


def _zustandsstrom(robot):
    """Gibt es den 333-Hz-Zustandsstrom auf diesem Roboter?

    Die Zeile BENUTZT ihn nicht. Sie beantwortet nur, ob die lizenzpflichtige
    Joint-Control-API auf diesem Gerät freigeschaltet ist — dort, wo man ohnehin
    hinschaut, bevor man misst. Beide Antworten sind ok=True: ein fehlender
    Strom ist kein Defekt, und ein rotes Kreuz wäre eine Falschaussage.
    """
    try:
        namen = {getattr(d, "name", "") for d in robot.list_services()}
    except Exception as fehler:
        return Check(
            "Zustandsstrom", True, f"nicht ermittelbar ({type(fehler).__name__})",
            "Ohne die Angabe bleibt es bei RobotState mit rund 10-50 Hz.",
        )
    if STROM_DIENST in namen:
        return Check(
            "Zustandsstrom", True, "verfügbar (333 Hz mit rohem IMU)",
            "spotlab nutzt ihn noch nicht — die Messfenster laufen über RobotState.",
        )
    return Check(
        "Zustandsstrom", True, "nicht vorhanden",
        "Der 333-Hz-Strom braucht die Joint-Control-Lizenz. Ohne ihn liefert "
        "RobotState alles ausser rohem IMU — für die Gates reicht das.",
    )


def _eigener_endpunkt(estop_client):
    """Steht noch ein spotlab-Endpunkt in der Not-Aus-Konfiguration?

    Automatisiert Abnahmepunkt A3. Bisher fragte diese Diagnose nur den
    aggregierten Systemstatus ab — ein zurückgelassener Endpunkt wäre dort
    unsichtbar geblieben, obwohl der Roboter ihn beim nächsten Timeout als
    ausgelöst wertet und der nächste Schüler einen scheinbar defekten Spot
    vorfindet.

    Zwei Fälle, die NICHT dasselbe sind: eine Leiche aus einem abgestürzten Lauf
    (heilt sich beim nächsten Verbinden selbst) und ein zweiter, laufender
    spotlab-Prozess (da muss ein Mensch etwas tun).
    """
    from spotlab.backends.real.estop import (
        ENDPOINT_NAME,
        ESTOP_TIMEOUT_S,
        sekunden_seit_antwort,
    )

    namen = [e.name for e in estop_client.get_config().endpoints]
    if ENDPOINT_NAME not in namen:
        return Check(
            "Not-Aus-Endpunkt", True,
            f"kein '{ENDPOINT_NAME}'-Endpunkt in der Konfiguration",
        )
    seit = sekunden_seit_antwort(estop_client, ENDPOINT_NAME)
    if seit is not None and seit <= ESTOP_TIMEOUT_S:
        return Check(
            "Not-Aus-Endpunkt", False,
            f"ein anderer spotlab-Lauf hält ihn (Rückmeldung vor {seit:.1f} s)",
            "Beende den anderen Lauf, bevor du verbindest.",
        )
    return Check(
        "Not-Aus-Endpunkt", False,
        f"ein '{ENDPOINT_NAME}'-Endpunkt ist zurückgeblieben und meldet sich nicht",
        "Rest eines hart beendeten Laufs. Der nächste Verbindungsaufbau ersetzt "
        "ihn automatisch — nach einem geordneten Ende sollte er aber weg sein "
        "(Abnahmepunkt A3).",
    )


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
        # `create_robot()` macht KEINEN RPC — es baut nur ein Objekt. Ohne den
        # folgenden Aufruf stand „Netz: OK" grün über einem Spot, der gar nicht
        # antwortet, und der Fehler fiel erst eine Stufe später bei „Anmeldung"
        # auf. `get_id()` braucht keine Anmeldung und ist damit die billigste
        # Frage, die wirklich übers Netz geht.
        robot.get_id()
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
    pruefungen.append(_zustandsstrom(robot))

    try:
        from bosdyn.client.estop import EstopClient

        estop_client = robot.ensure_client(EstopClient.default_service_name)
        status = estop_client.get_status()
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
        pruefungen.append(_eigener_endpunkt(estop_client))
    except Exception as fehler:
        pruefungen.append(_fehler("Not-Aus-Endpunkt", fehler, cfg.ip))

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
