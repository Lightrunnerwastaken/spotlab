"""Ausnahmen von spotlab. Klassennamen englisch, Meldungen deutsch (Vorgabe G6)."""


class SpotlabError(Exception):
    """Basis aller spotlab-Fehler. Die Meldung ist Klartext für Schüler."""


class ConfigMissing(SpotlabError):
    """Keine Konfiguration hinterlegt."""


class NotReachable(SpotlabError):
    """Der Roboter ist im Netz nicht erreichbar."""


class BadCredentials(SpotlabError):
    """Benutzername oder Passwort falsch."""


class TimeSyncFailed(SpotlabError):
    """Zeitsynchronisierung mit dem Roboter fehlgeschlagen."""


class LeaseBusy(SpotlabError):
    """Jemand anders hält die Kontrolle."""

    def __init__(self, message, holder=None):
        super().__init__(message)
        self.holder = holder


class LeaseLost(SpotlabError):
    """Die Kontrolle wurde während des Laufs entzogen."""


class EstopEngaged(SpotlabError):
    """Der Not-Aus ist ausgelöst."""


class BatteryEmpty(SpotlabError):
    """Der Akku reicht nicht mehr."""


class CommandRejected(SpotlabError):
    """Der Roboter hat ein Kommando abgelehnt."""


class NotPowered(SpotlabError):
    """Die Motoren sind aus."""


class UnsupportedCapability(SpotlabError):
    """Das aktive Backend kann das nicht."""


from spotlab.errors.translate import translate  # noqa: E402

__all__ = [
    "SpotlabError",
    "ConfigMissing",
    "NotReachable",
    "BadCredentials",
    "TimeSyncFailed",
    "LeaseBusy",
    "LeaseLost",
    "EstopEngaged",
    "BatteryEmpty",
    "CommandRejected",
    "NotPowered",
    "UnsupportedCapability",
    "translate",
]

# Ganz am Ende, nach allen Ausnahmeklassen: errors/graphnav.py importiert
# NavStatus aus backends/base.py, und das importiert UnsupportedCapability von
# hier. Weiter oben stünde ein Importzyklus.
from spotlab.errors.graphnav import (  # noqa: E402
    MapError,
    NavigationError,
    NotLocalized,
)

__all__ += ["MapError", "NavigationError", "NotLocalized"]
