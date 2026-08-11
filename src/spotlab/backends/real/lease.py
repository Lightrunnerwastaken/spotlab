"""Lease-Erwerb mit Namen, Keepalive und Verlusterkennung.

Der Client meldet sich als `spotlab/<benutzer>@<rechner>` an, damit ein Halter
im Klassenraum einen Namen hat. Erworben wird immer mit acquire, nie implizit
mit take — Übernahme ist eine bewusste Handlung.
"""

import getpass
import socket

from bosdyn.client.exceptions import (
    LeaseUseError,
    ProxyConnectionError,
    RetryableUnavailableError,
    TimedOutError,
)
from bosdyn.client.lease import DisplacedLeaseError, LeaseKeepAlive

from spotlab.errors import LeaseLost, translate


def client_name():
    return f"spotlab/{getpass.getuser()}@{socket.gethostname()}"


def holder_of(lease_client, resource="body"):
    for eintrag in lease_client.list_leases():
        if eintrag.resource != resource:
            continue
        besitzer = eintrag.lease_owner
        return besitzer.client_name or besitzer.user_name or None
    return None


# Ein Keepalive kann aus zwei sehr verschiedenen Gruenden fehlschlagen: das Netz
# hat gehustet, oder jemand hat uebernommen. Nur das Zweite ist ein Lease-Verlust.
VORUEBERGEHEND = (RetryableUnavailableError, TimedOutError, ProxyConnectionError)


def _ist_voruebergehend(ursache):
    if ursache is None:
        return False
    if isinstance(ursache, (DisplacedLeaseError, LeaseUseError)):
        return False
    return isinstance(ursache, VORUEBERGEHEND)


class LeaseGuard:
    def __init__(self, lease_client, take=False, on_lost=None):
        self._client = lease_client
        self._take = take
        self._on_lost = on_lost
        self._keepalive = None
        self.lost = False
        self.previous_holder = None

    def start(self, keepalive_bauen=None):
        self.previous_holder = holder_of(self._client)
        try:
            if self._take:
                self._client.take()
            else:
                self._client.acquire()
        except Exception as fehler:
            uebersetzt = translate(fehler)
            if uebersetzt is not None:
                raise uebersetzt from fehler
            raise

        bauen = keepalive_bauen or self._standard_keepalive
        self._keepalive = bauen(self._client, self._melde_verlust)

    def _standard_keepalive(self, lease_client, bei_verlust):
        return LeaseKeepAlive(
            lease_client,
            must_acquire=False,
            return_at_exit=False,
            on_failure_callback=bei_verlust,
        )

    def _melde_verlust(self, ursache=None):
        """Nur ein ECHTER Verlust bricht den Lauf ab.

        `on_failure_callback` feuert bei jedem fehlgeschlagenen Keepalive, auch
        bei einem einzelnen WLAN-Hänger in der Turnhalle. Der Lauf brach dann ab
        und trug in `lauf.json` das Ergebnis `lease_verloren` — eine Behauptung
        über eine Übernahme, die nie stattgefunden hat. Projektregel: keine
        Ursache behaupten, die nicht geprüft ist.

        Ohne erkennbare Ursache bleibt es beim Abbruch: weiterzufahren, während
        vielleicht jemand anders steuert, wäre die gefährlichere Annahme.
        """
        if _ist_voruebergehend(ursache):
            return
        self.lost = True
        if self._on_lost is not None:
            self._on_lost()

    def raise_if_lost(self):
        if self.lost:
            raise LeaseLost(
                "Kontrolle verloren — jemand anders hat übernommen. Lauf abgebrochen."
            )

    def stop(self):
        if self._keepalive is not None:
            try:
                self._keepalive.shutdown()
            except Exception:
                pass
            finally:
                self._keepalive = None
        try:
            self._client.return_lease(self._client.lease_wallet.get_lease("body"))
        except Exception:
            pass  # Abbau darf nie werfen
