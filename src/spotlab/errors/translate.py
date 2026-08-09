"""bosdyn-Ausnahmen in deutschen Klartext übersetzen.

Jede übersetzte Ausnahme behält die originale als __cause__: für die Schüler
Klartext, für die Entwicklung die volle Wahrheit.
"""

from bosdyn.client.auth import InvalidLoginError, TemporarilyLockedOutError
from bosdyn.client.exceptions import (
    LeaseUseError,
    ProxyConnectionError,
    RetryableUnavailableError,
    RpcError,
    TimedOutError,
    UnableToConnectToRobotError,
    UnauthenticatedError,
    UnknownDnsNameError,
)
from bosdyn.client.lease import DisplacedLeaseError, ResourceAlreadyClaimedError
from bosdyn.client.robot_command import ExpiredError, NoTimeSyncError, TooDistantError


def _mit_ursache(fehler, ursprung):
    fehler.__cause__ = ursprung
    return fehler


def translate(exc, *, ip=None):
    """bosdyn-Ausnahme → SpotlabError, oder None wenn nicht übersetzbar."""
    from spotlab import errors as E

    ziel = ip or "dem Roboter"

    if isinstance(
        exc,
        (
            UnableToConnectToRobotError,
            UnknownDnsNameError,
            ProxyConnectionError,
            RetryableUnavailableError,
            TimedOutError,
        ),
    ):
        return _mit_ursache(
            E.NotReachable(f"Ich erreiche {ziel} nicht. Bist du im WLAN des Spot?"), exc
        )

    if isinstance(exc, InvalidLoginError):
        return _mit_ursache(
            E.BadCredentials(
                "Benutzername oder Passwort stimmt nicht — neu hinterlegen mit "
                "`spotlab login`."
            ),
            exc,
        )

    if isinstance(exc, TemporarilyLockedOutError):
        return _mit_ursache(
            E.BadCredentials(
                "Zu viele Fehlversuche. Der Roboter sperrt den Login kurz — in einer "
                "Minute erneut versuchen, danach `spotlab login`."
            ),
            exc,
        )

    if isinstance(exc, UnauthenticatedError):
        return _mit_ursache(
            E.BadCredentials("Nicht angemeldet. Zugangsdaten hinterlegen mit `spotlab login`."),
            exc,
        )

    if isinstance(exc, ResourceAlreadyClaimedError):
        halter = _halter_aus(exc)
        wer = halter or "Jemand anders"
        return _mit_ursache(
            E.LeaseBusy(
                f"{wer} steuert den Spot gerade. Mit `spotlab lease --take` übernehmen "
                f"— aber erst absprechen.",
                holder=halter,
            ),
            exc,
        )

    if isinstance(exc, (DisplacedLeaseError, LeaseUseError)):
        return _mit_ursache(
            E.LeaseLost("Kontrolle verloren — jemand anders hat übernommen. Lauf abgebrochen."),
            exc,
        )

    # Die drei Zeit-Fehler des Kommandodienstes. Sie sehen für einen Schüler wie
    # ein kaputter Roboter aus, sind aber immer ein Programmfehler auf UNSERER
    # Seite — `end_time_secs` ist ein Zeitpunkt in Sekunden seit dem 1.1.1970,
    # keine Dauer. Die Meldung sagt das, statt zum Neustart zu raten.
    if isinstance(exc, ExpiredError):
        return _mit_ursache(
            E.CommandRejected(
                "Der Roboter hat ein bereits abgelaufenes Kommando bekommen. Das ist "
                "ein Fehler in spotlab, nicht in deinem Programm — bitte melden."
            ),
            exc,
        )

    if isinstance(exc, TooDistantError):
        return _mit_ursache(
            E.CommandRejected(
                "Die Gültigkeit des Kommandos reicht dem Roboter zu weit in die "
                "Zukunft. Fehler in spotlab, nicht in deinem Programm — bitte melden."
            ),
            exc,
        )

    if isinstance(exc, NoTimeSyncError):
        return _mit_ursache(
            E.NotReachable(
                "Die Uhren von Laptop und Roboter sind nicht synchronisiert. Verbindung "
                "trennen und neu aufbauen; hält es an, hilft `spotlab doctor`."
            ),
            exc,
        )

    if isinstance(exc, RpcError):
        return _mit_ursache(E.NotReachable(f"Die Verbindung zu {ziel} ist abgebrochen."), exc)

    return None


def _halter_aus(exc):
    """Halternamen aus der Lease-Antwort ziehen, wenn vorhanden."""
    antwort = getattr(exc, "response", None)
    besitzer = getattr(antwort, "lease_owner", None)
    if besitzer is None:
        return None
    name = besitzer.client_name or besitzer.user_name
    return name or None
