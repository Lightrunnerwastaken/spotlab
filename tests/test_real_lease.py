import pytest
from bosdyn.api import lease_pb2
from bosdyn.client.lease import ResourceAlreadyClaimedError

from spotlab.backends.real.lease import LeaseGuard, client_name, holder_of
from spotlab.errors import LeaseBusy, LeaseLost


class FakeLeaseClient:
    def __init__(self, besitzer=None, blockiert=False, mit_antwort=False):
        self._besitzer = besitzer
        self._blockiert = blockiert
        self._mit_antwort = mit_antwort
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
            antwort = None
            if self._mit_antwort:
                antwort = lease_pb2.AcquireLeaseResponse()
                antwort.lease_owner.client_name = self._besitzer or ""
            raise ResourceAlreadyClaimedError(response=antwort)
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


# --------------------------------------------- Das Lease eines toten Laufs


def _halter_dieses_rechners(pid):
    """So nennt der Roboter einen spotlab-Lauf DIESES Rechners: Name, Skript, PID."""
    import socket

    return f"spotlab{socket.gethostname()}:__main__.py-{pid}"


def test_ein_abgestuerzter_eigener_lauf_wird_als_solcher_erkannt():
    """Nach dem NOT-AUS haelt genau so einer das Lease -- der Prozess ist tot."""
    from spotlab.backends.real import lease as lease_modul

    assert lease_modul.eigener_toter_lauf(_halter_dieses_rechners(29228),
                                          lebt=lambda _p: False) == 29228


def test_ein_laufender_eigener_prozess_ist_keine_leiche():
    from spotlab.backends.real import lease as lease_modul

    assert lease_modul.eigener_toter_lauf(_halter_dieses_rechners(29228),
                                          lebt=lambda _p: True) is None


def test_ein_fremder_rechner_und_das_tablet_zaehlen_nie_als_leiche():
    """Ein anderer Laptop kann eine tote PID-Nummer haben, die es hier zufaellig gibt --
    und ein Tablet hat gar keine. Beides darf nie als 'niemand steuert' gelten."""
    from spotlab.backends.real import lease as lease_modul

    for halter in ("spotlabANDERER-LAPTOP:__main__.py-29228",
                   "bosdyn.android.spotapp 2c4e3c0060f5edde",
                   _halter_dieses_rechners(29228).replace("spotlab", "fremdprogramm"),
                   "", None):
        assert lease_modul.eigener_toter_lauf(halter, lebt=lambda _p: False) is None


def test_ohne_nummer_am_ende_gibt_es_keine_leiche():
    import socket

    from spotlab.backends.real import lease as lease_modul

    assert lease_modul.eigener_toter_lauf(f"spotlab{socket.gethostname()}:__main__.py",
                                          lebt=lambda _p: False) is None


def test_die_pruefung_wirft_nie_und_antwortet_im_zweifel_mit_ja():
    """Die vorsichtige Richtung: lieber 'jemand steuert' als ein falsches 'niemand steuert'.
    Und eine Nummer, die es nicht geben kann, darf keine Ausnahme ausloesen."""
    from spotlab.backends.real import lease as lease_modul

    assert lease_modul.lebt(2**31 - 1) is False, "diese Nummer laeuft sicher nicht"
    assert lease_modul.lebt("keine zahl") is True, "unlesbar heisst im Zweifel: lebt"
    assert lease_modul.lebt(None) is True


def test_der_eigene_prozess_lebt():
    import os

    from spotlab.backends.real import lease as lease_modul

    assert lease_modul.lebt(os.getpid()) is True


def test_ein_totes_eigenes_lease_sagt_es_und_nennt_die_pid(monkeypatch):
    """Die Meldung, die am 18.09.2026 fehlte: der Halter WAR tot, und spotlab sagte
    trotzdem 'steuert den Spot gerade -- erst absprechen'. Mit wem denn?"""
    from spotlab.backends.real import lease as lease_modul

    monkeypatch.setattr(lease_modul, "lebt", lambda _pid: False)
    halter = _halter_dieses_rechners(29228)
    wache = LeaseGuard(FakeLeaseClient(besitzer=halter, blockiert=True, mit_antwort=True))
    with pytest.raises(LeaseBusy) as info:
        wache.start()
    text = str(info.value)
    assert "29228" in text
    assert "NOT-AUS" in text
    assert "niemand" in text.lower(), "es steuert gerade NIEMAND -- das ist die Nachricht"
    assert "absprechen" not in text, "mit einem toten Prozess spricht sich niemand ab"
    assert info.value.holder == halter


def test_ein_lebender_fremder_halter_bleibt_die_alte_warnung(monkeypatch):
    from spotlab.backends.real import lease as lease_modul

    monkeypatch.setattr(lease_modul, "lebt", lambda _pid: False)
    wache = LeaseGuard(FakeLeaseClient(besitzer="bosdyn.android.spotapp", blockiert=True,
                                       mit_antwort=True))
    with pytest.raises(LeaseBusy) as info:
        wache.start()
    assert "absprechen" in str(info.value) and "NOT-AUS" not in str(info.value)


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


# ================================== S4.8 der Abbau darf nicht selbst scheitern
#
# `stop()` faengt beide Ausnahmen ab und schreibt sie ins Protokoll -- nur war
# `protokoll` in dieser Datei nie importiert. Der Handler warf also NameError,
# und ausgerechnet der Pfad, der einen Fehler ueberleben sollte, riss die
# ganze Sitzung mit: Lease gehalten, Motoren an, Lauf ohne Abschluss.
# Kein Test hatte das gedeckt, weil beide Attrappen brav zurueckkehrten.
# Gefunden hat es der Linter (ruff F821), nicht die 844 Tests.


class SperrigerClient(FakeLeaseClient):
    def return_lease(self, *a, **kw):
        raise RuntimeError("Netz weg")


class SperrigesKeepalive:
    def shutdown(self):
        raise RuntimeError("Faden haengt")


def test_stop_uebersteht_ein_scheiterndes_keepalive():
    wache = LeaseGuard(FakeLeaseClient())
    wache._keepalive = SperrigesKeepalive()
    wache.stop()                                  # darf nicht werfen
    assert wache._keepalive is None               # trotzdem losgelassen


def test_stop_uebersteht_eine_scheiternde_rueckgabe():
    LeaseGuard(SperrigerClient()).stop()


def test_stop_schreibt_das_scheitern_ins_protokoll(tmp_path):
    from spotlab import protokoll

    protokoll.setze_ziel(tmp_path)
    try:
        LeaseGuard(SperrigerClient()).stop()
    finally:
        protokoll.setze_ziel(None)
    geschrieben = "".join(p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
    assert "Lease-Rueckgabe gescheitert" in geschrieben
