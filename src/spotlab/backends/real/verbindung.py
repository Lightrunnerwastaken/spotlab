"""Der gemeinsame Anfang jeder Roboterverbindung: Auth und Zeitsync.

Von RealSpot.connect (das danach E-Stop und Lease holt) UND von der
Aufzeichnungssitzung benutzt (die beides NICHT holt). Ohne diese Trennung
stünde die Fehlerübersetzung zweimal im Code.
"""

from bosdyn.client import create_standard_sdk

from spotlab.config import load_password
from spotlab.errors import TimeSyncFailed, translate

SDK_NAME = "spotlab"


def standard_robot(cfg):
    sdk = create_standard_sdk(SDK_NAME)
    return sdk.create_robot(cfg.ip)


def verbinde(cfg, robot_bauen=None, passwort_lesen=None):
    """Angemeldeter, zeitsynchroner Roboter — ohne Lease, ohne E-Stop."""
    robot = (robot_bauen or standard_robot)(cfg)

    try:
        robot.authenticate(cfg.username, (passwort_lesen or load_password)(cfg.username))
    except Exception as fehler:
        uebersetzt = translate(fehler, ip=cfg.ip)
        if uebersetzt is not None:
            raise uebersetzt from fehler
        raise

    try:
        robot.time_sync.wait_for_sync()
    except Exception as fehler:
        raise TimeSyncFailed(
            "Die Uhr deines Laptops weicht zu stark von der des Roboters ab; "
            "die Zeitsynchronisierung ist fehlgeschlagen. Windows-Uhrzeit "
            "automatisch stellen lassen und erneut versuchen."
        ) from fehler

    return robot
