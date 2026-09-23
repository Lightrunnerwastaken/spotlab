"""bosdyn-Ausnahmen in deutschen Klartext übersetzen.

Jede übersetzte Ausnahme behält die originale als __cause__: für die Schüler
Klartext, für die Entwicklung die volle Wahrheit.
"""

# Das SDK erst beim ersten Fehler laden: es kostet 1.2 s, und `spotlab.errors`
# importiert jedes Programm -- die GUI, jedes Sim-Skript, die Kommandozeile.


def _mit_ursache(fehler, ursprung):
    fehler.__cause__ = ursprung
    return fehler


def translate(exc, *, ip=None):
    """bosdyn-Ausnahme → SpotlabError, oder None wenn nicht übersetzbar."""
    # Was nicht aus dem SDK stammt, kann es nicht übersetzen -- und braucht es
    # dafür auch nicht zu laden.
    if not any(k.__module__.startswith("bosdyn") for k in type(exc).__mro__):
        return None
    from bosdyn.client.auth import InvalidLoginError, TemporarilyLockedOutError
    from bosdyn.client.exceptions import (
        InvalidRequestError,
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
    from bosdyn.client.robot_command import (
        BehaviorFaultError,
        ExpiredError,
        NoTimeSyncError,
        TooDistantError,
    )

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

    # Lauf 20260911T162238Z: der Roboter verweigerte jedes Kommando, und der
    # Grund stand nur in diagnose.log. Ein Verhaltensfehler löscht sich nicht
    # von selbst — die Meldung muss sagen, wo er gelöscht wird.
    if isinstance(exc, BehaviorFaultError):
        return _mit_ursache(
            E.CommandRejected(
                "Spot hat einen Verhaltensfehler (Sturz, Hardware oder abgelaufenes "
                "Lease). " + E.VERHALTENSFEHLER_HINWEIS
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

    motoren = _motorfreigabe(exc, E)
    if motoren is not None:
        return _mit_ursache(motoren, exc)

    if isinstance(exc, InvalidRequestError):
        # Laut SDK: die Argumente sind falsch, UNABHÄNGIG vom Zustand des
        # Roboters. Neustarten hilft also nicht -- und das sagt die Meldung.
        grund = getattr(exc, "error_message", "") or type(exc).__name__
        return _mit_ursache(
            E.CommandRejected(
                f"Der Roboter hat die Anfrage als ungültig abgewiesen ({grund}). Das liegt "
                "an den Werten des Kommandos, nicht am Zustand des Roboters: bei einem "
                "Rohkommando über `spot.send()` die Felder prüfen, sonst ist es ein "
                "Fehler in spotlab -- bitte mit dieser Meldung melden."
            ),
            exc,
        )

    if isinstance(exc, RpcError):
        return _mit_ursache(E.NotReachable(f"Die Verbindung zu {ziel} ist abgebrochen."), exc)

    return None


def _motorfreigabe(exc, E):
    """Warum die Motoren nicht angehen -- oder aus sind. None, wenn es nicht darum geht.

    Der häufigste Fehler am Gerät: `power_on()` bei ausgelöstem Not-Aus. Die
    Texte sagen, was zu tun ist, und behaupten nicht, WER den Not-Aus hält:
    neben dem Tablet kann es ein zurückgelassener Endpunkt sein (CLAUDE.md,
    E-Stop-Abgabe) -- das zeigt `spotlab doctor`.
    """
    from bosdyn.client.power import (
        BatteryMissingError,
        EstoppedError,
        FaultedError,
        KeepaliveMotorsOffError,
        ShorePowerConnectedError,
    )
    from bosdyn.client.robot_command import NotPoweredOnError

    if isinstance(exc, EstoppedError):
        return E.EstopEngaged(
            "Ein Not-Aus ist ausgelöst, deshalb gehen die Motoren nicht an. Am Tablet "
            "nachsehen und den Not-Aus freigeben, dann das Programm erneut starten. "
            "Wer den Not-Aus hält, zeigt `spotlab doctor`."
        )
    if isinstance(exc, FaultedError):
        return E.NotPowered(
            "Spot meldet einen Fehler (etwa an einem Motor) und lässt die Motoren nicht "
            "an. Auf dem Tablet steht, welcher: dort ansehen und quittieren, dann das "
            "Programm erneut starten."
        )
    if isinstance(exc, BatteryMissingError):
        return E.BatteryEmpty(
            "Spot erkennt keinen Akku, ohne ihn gehen die Motoren nicht an. Akku "
            "einsetzen und einrasten lassen, dann das Programm erneut starten."
        )
    if isinstance(exc, ShorePowerConnectedError):
        return E.NotPowered(
            "Spot hängt am Ladekabel, so gehen die Motoren nicht an. Kabel abziehen, "
            "dann das Programm erneut starten."
        )
    if isinstance(exc, KeepaliveMotorsOffError):
        return E.NotPowered(
            "Eine Keepalive-Regel auf dem Roboter verlangt gerade „Motoren aus“, deshalb "
            "gehen sie nicht an. Am Tablet nachsehen, wer sie gesetzt hat; hilft das "
            "nicht, Spot neu starten."
        )
    if isinstance(exc, NotPoweredOnError):
        return E.NotPowered(
            "Die Motoren sind aus, so nimmt Spot kein Bewegungskommando an. Im Programm "
            "vorher `spot.power_on()` aufrufen. Waren sie schon an, hat sie jemand "
            "ausgeschaltet (Not-Aus oder Tablet) -- dort nachsehen."
        )
    return None


def _halter_aus(exc):
    """Halternamen aus der Lease-Antwort ziehen, wenn vorhanden."""
    antwort = getattr(exc, "response", None)
    besitzer = getattr(antwort, "lease_owner", None)
    if besitzer is None:
        return None
    name = besitzer.client_name or besitzer.user_name
    return name or None
