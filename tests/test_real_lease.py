import pytest
from bosdyn.api import lease_pb2
from bosdyn.client.lease import ResourceAlreadyClaimedError

from spotlab.backends.real.lease import LeaseGuard, client_name, holder_of
from spotlab.errors import LeaseBusy, LeaseLost


class FakeLeaseClient:
    def __init__(self, besitzer=None, blockiert=False):
        self._besitzer = besitzer
        self._blockiert = blockiert
        self.acquired = self.taken = self.returned = 0
        self.lease_wallet = self

    def get_lease(self, *a):
        return None

    def list_leases(self):
        ressource = lease_pb2.LeaseResource(resource="body")
        if self._besitzer:
            ressource.lease_owner.client_name = self._besitzer
        return [ressource]

    def acquire(self, resource="body", **kw):
        if self._blockiert:
            raise ResourceAlreadyClaimedError(response=None)
        self.acquired += 1
        return object()

    def take(self, resource="body", **kw):
        self.taken += 1
        return object()

    def return_lease(self, *a, **kw):
        self.returned += 1


def test_client_name_traegt_benutzer_und_rechner():
    name = client_name()
    assert name.startswith("spotlab/") and "@" in name


def test_halter_wird_gelesen():
    assert holder_of(FakeLeaseClient(besitzer="spotlab/anna@laptop7")) == "spotlab/anna@laptop7"


def test_freies_lease_hat_keinen_halter():
    assert holder_of(FakeLeaseClient()) is None


def test_belegtes_lease_wird_zu_klartext():
    wache = LeaseGuard(FakeLeaseClient(besitzer="spotlab/anna@laptop7", blockiert=True))
    with pytest.raises(LeaseBusy) as info:
        wache.start()
    assert "spotlab lease --take" in str(info.value)


def test_take_uebernimmt_bewusst():
    client = FakeLeaseClient(besitzer="spotlab/anna@laptop7", blockiert=True)
    wache = LeaseGuard(client, take=True)
    wache.start(keepalive_bauen=lambda *_a, **_k: None)
    assert client.taken == 1 and client.acquired == 0
    wache.stop()


def test_verlust_wird_gemerkt_und_geworfen():
    wache = LeaseGuard(FakeLeaseClient())
    wache.start(keepalive_bauen=lambda *_a, **_k: None)
    wache._melde_verlust()
    assert wache.lost is True
    with pytest.raises(LeaseLost):
        wache.raise_if_lost()


def test_stop_ohne_start_wirft_nicht():
    LeaseGuard(FakeLeaseClient()).stop()


# ============================ S2.5 ein WLAN-Aussetzer ist kein Lease-Verlust
#
# `on_failure_callback` feuert bei JEDEM fehlgeschlagenen Keepalive, auch bei
# einem einzelnen Netzhaenger. Der Lauf brach daraufhin ab und trug in lauf.json
# `lease_verloren` -- eine Behauptung ueber eine Uebernahme, die nie stattfand.
# Die Projektregel verlangt, keine ungepruefte Ursache zu behaupten.


def test_ein_netzhaenger_gilt_nicht_als_verlust():
    from bosdyn.client.exceptions import RetryableUnavailableError

    from spotlab.backends.real.lease import LeaseGuard

    wache = LeaseGuard(FakeLeaseClient())
    wache._melde_verlust(RetryableUnavailableError(OSError("kurz weg")))
    assert wache.lost is False


def test_eine_echte_uebernahme_gilt_als_verlust():
    from bosdyn.client.lease import DisplacedLeaseError

    from spotlab.backends.real.lease import LeaseGuard

    wache = LeaseGuard(FakeLeaseClient())
    wache._melde_verlust(DisplacedLeaseError(response=None))
    assert wache.lost is True


def test_ein_lease_use_error_gilt_als_verlust():
    from bosdyn.client.exceptions import LeaseUseError

    from spotlab.backends.real.lease import LeaseGuard

    wache = LeaseGuard(FakeLeaseClient())
    wache._melde_verlust(LeaseUseError(None, None))
    assert wache.lost is True


def test_ohne_ausnahme_wird_im_zweifel_der_verlust_angenommen():
    """Kennen wir die Ursache nicht, ist Vorsicht richtig: lieber abbrechen als
    weiterfahren, waehrend vielleicht jemand anders steuert."""
    from spotlab.backends.real.lease import LeaseGuard

    wache = LeaseGuard(FakeLeaseClient())
    wache._melde_verlust(None)
    assert wache.lost is True
