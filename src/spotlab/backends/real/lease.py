"""Lease-Erwerb mit Namen, Keepalive und Verlusterkennung.

Der Client meldet sich als `spotlab/<benutzer>@<rechner>` an, damit ein Halter
im Klassenraum einen Namen hat. Erworben wird immer mit acquire, nie implizit
mit take — Übernahme ist eine bewusste Handlung.
"""

import getpass
import os
import re
import socket
import subprocess

from bosdyn.client.exceptions import (
    LeaseUseError,
    ProxyConnectionError,
    RetryableUnavailableError,
    TimedOutError,
)
from bosdyn.client.lease import DisplacedLeaseError, LeaseKeepAlive

from spotlab import protokoll
from spotlab.errors import LeaseBusy, LeaseLost, translate


def client_name():
    return f"spotlab/{getpass.getuser()}@{socket.gethostname()}"


def holder_of(lease_client, resource="body"):
    for eintrag in lease_client.list_leases():
        if eintrag.resource != resource:
            continue
        besitzer = eintrag.lease_owner
        return besitzer.client_name or besitzer.user_name or None
    return None


# Der Roboter nennt einen spotlab-Lauf so: Name, Rechner, Skript, Prozessnummer —
# zum Beispiel `spotlabLIGHTRUNNER-LEG:__main__.py-29228`.
_PID_AM_ENDE = re.compile(r"-(\d+)\s*$")


def lebt(pid):
    """Läuft auf DIESEM Rechner ein Prozess mit dieser Nummer? Im Zweifel ja.

    Im Zweifel ja ist die vorsichtige Richtung: ein falsches „lebt nicht“ hiesse
    „niemand steuert den Spot“, und das ist die gefährlichere Auskunft. Wirft nie.

    Kein `os.kill(pid, 0)` unter Windows — dort kennt `os.kill` kein Signal 0 und
    BEENDET den Prozess stattdessen. Die Frage darf den Gefragten nicht töten.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return True
    if os.name == "nt":
        try:
            ergebnis = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, check=False, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return True
        return str(pid) in (ergebnis.stdout or "")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def eigener_toter_lauf(halter, rechner=None, lebt=None):
    """Die Prozessnummer eines spotlab-Laufs DIESES Rechners, der nicht mehr läuft — sonst None.

    Genau das hinterlässt der NOT-AUS: er tötet den Laufprozess hart, `close()`
    läuft nie, und das Lease bleibt beim Toten stehen. Der nächste Start prallt
    daran ab, und spotlab sagte bis zum 18.09.2026 „steuert den Spot gerade —
    erst absprechen". Mit wem denn?

    Streng, weil die Auskunft „niemand steuert“ die gefährlichere ist: der Name
    muss mit `spotlab` beginnen, DIESEN Rechner nennen und auf eine Nummer enden,
    und der Prozess muss nachweislich weg sein. Ein Tablet, ein anderer Laptop
    und ein laufender eigener Prozess fallen alle heraus.
    """
    if not halter:
        return None
    rechner = socket.gethostname() if rechner is None else rechner
    if not halter.startswith("spotlab") or rechner.lower() not in halter.lower():
        return None
    treffer = _PID_AM_ENDE.search(halter)
    if treffer is None:
        return None
    pid = int(treffer.group(1))
    prueft = lebt if lebt is not None else globals()["lebt"]
    return None if prueft(pid) else pid


# Ein Keepalive kann aus zwei sehr verschiedenen Gruenden fehlschlagen: das Netz
# hat gehustet, oder jemand hat uebernommen. Nur das Zweite ist ein Lease-Verlust.
VORUEBERGEHEND = (RetryableUnavailableError, TimedOutError, ProxyConnectionError)


def _ist_voruebergehend(ursache):
    if ursache is None:
        return False
    if isinstance(ursache, (DisplacedLeaseError, LeaseUseError)):
        return False
    return isinstance(ursache, VORUEBERGEHEND)


def _leiche_statt_fremder(busy):
    """Aus „jemand steuert“ wird „niemand steuert“, wenn der Halter nachweislich tot ist."""
    pid = eigener_toter_lauf(busy.holder)
    if pid is None:
        return busy
    return LeaseBusy(
        f"Das Lease hängt noch an einem abgestürzten spotlab-Lauf dieses Rechners "
        f"(Prozess {pid}, läuft nicht mehr) — typisch nach dem NOT-AUS, der den Lauf hart "
        f"tötet, bevor er es zurückgeben kann. Es steuert also gerade NIEMAND den Spot. "
        f"Zurück kommst du im Reiter „Fahren“ mit dem Häkchen „🔓 Kontrolle übernehmen“ und "
        f"einem neuen Start, auf der Kommandozeile mit `spotlab lease --take`.",
        holder=busy.holder,
    )


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
            if isinstance(uebersetzt, LeaseBusy):
                uebersetzt = _leiche_statt_fremder(uebersetzt)
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
            except Exception as fehler:
                protokoll.notiere("Lease-Keepalive beenden gescheitert", fehler)
            finally:
                self._keepalive = None
        try:
            self._client.return_lease(self._client.lease_wallet.get_lease("body"))
        except Exception as fehler:
            protokoll.notiere("Lease-Rueckgabe gescheitert", fehler)
