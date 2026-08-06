"""Lease-Erwerb mit Namen, Keepalive und Verlusterkennung.

Der Client meldet sich als `spotlab/<benutzer>@<rechner>` an, damit ein Halter
im Klassenraum einen Namen hat. Erworben wird immer mit acquire, nie implizit
mit take — Übernahme ist eine bewusste Handlung.
"""

import getpass
import socket

from bosdyn.client.lease import LeaseKeepAlive

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
            on_failure_callback=lambda _msg: bei_verlust(),
        )

    def _melde_verlust(self):
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
