"""Ausnahmen von spotlab. Klassennamen englisch, Meldungen deutsch (Vorgabe G6)."""


class SpotlabError(Exception):
    """Basis aller spotlab-Fehler. Die Meldung ist Klartext für Schüler."""


class ConfigMissing(SpotlabError):
    """Keine Konfiguration hinterlegt."""


class ConfigBroken(SpotlabError):
    """Konfiguration vorhanden, aber unbrauchbar.

    Ausdrücklich KEIN Untertyp von ConfigMissing: `spotlab.connect()` fängt
    ConfigMissing ab und fällt still auf den Trockenlauf zurück. Bei einer
    kaputten Datei wäre das die falsche Rettung — der Schüler führe im
    Trockenlauf und hielte das für den echten Roboter.
    """


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


class EstopBusy(SpotlabError):
    """Ein anderer, noch lebender spotlab-Lauf hält den Not-Aus-Endpunkt."""


class EstopEngaged(SpotlabError):
    """Der Not-Aus ist ausgelöst."""


class BatteryEmpty(SpotlabError):
    """Der Akku reicht nicht mehr."""


class CommandRejected(SpotlabError):
    """Der Roboter hat ein Kommando abgelehnt."""


# Der eine Satz, der bei einem Verhaltensfehler zu sagen ist — an EINER Stelle,
# weil er auf zwei Wegen gebraucht wird: wenn der Kommandodienst die Annahme
# verweigert (`translate`) und wenn ein angenommenes Kommando daran scheitert
# (`api/posture.py`). Gelöscht wird der Fehler AM TABLET, absichtlich nicht von
# spotlab: nach einem Sturz soll ein Mensch zuerst hinsehen, bevor der Roboter
# wieder Kommandos annimmt.
VERHALTENSFEHLER_HINWEIS = (
    "Spot nimmt kein Kommando an, bis der Fehler gelöscht ist. Auf dem Tablet "
    "quittieren (nach einem Sturz ist das die Abfrage 'Fehler löschen?'), dann das "
    "Programm erneut starten."
)


class NotPowered(SpotlabError):
    """Die Motoren sind aus."""


class UnsupportedCapability(SpotlabError):
    """Das aktive Backend kann das nicht."""


class ReadOnlySession(SpotlabError):
    """Die Sitzung liest nur — sie hält kein Lease und kann nichts bewegen."""


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
    "ReadOnlySession",
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
