import pytest
from bosdyn.api import estop_pb2
from bosdyn.client.estop import EstopEndpoint

from spotlab.backends.real import estop as module


class Client:
    def __init__(self, names=('spotlab',)):
        self.config = estop_pb2.EstopConfig(unique_id='own-config')
        for name in names:
            self.config.endpoints.add(name=name, unique_id=f'id-{name}', role='PDB_rooted')
        self.calls = []
        self.fail = None

    def get_config(self, **kwargs):
        return self.config

    def set_config(self, config, config_id, **kwargs):
        self.calls.append('set_config')
        assert config_id == self.config.unique_id
        if self.fail:
            raise self.fail
        self.config = estop_pb2.EstopConfig(unique_id='new-config', endpoints=config.endpoints)
        for ep in self.config.endpoints:
            if not ep.unique_id:
                ep.unique_id = 'new-endpoint'
        return self.config

    def deregister(self, config_id, endpoint, **kwargs):
        assert kwargs['timeout'] == 3
        assert config_id == self.config.unique_id
        self.calls.append('deregister')
        if self.fail:
            raise self.fail

    def register(self, *args):
        raise RuntimeError('registration failed')


class Keepalive:
    def __init__(self, client, error=None):
        self.client, self.error = client, error

    def shutdown(self):
        self.client.calls.append('shutdown')
        if self.error:
            raise self.error


def guard(client, shutdown_error=None):
    result = module.EstopGuard(client)
    endpoint = EstopEndpoint(client, 'spotlab', 5, first_checkin=False)
    endpoint._config_id = 'own-config'
    endpoint.from_proto(estop_pb2.EstopEndpoint(name='spotlab', unique_id='id-spotlab'))
    result._endpoint = endpoint
    result._keepalive = Keepalive(client, shutdown_error)
    return result


def test_own_configuration_removed_before_keepalive_stops():
    client = Client()
    g = guard(client)
    g.stop()
    assert client.calls == ['set_config', 'shutdown']
    assert not client.config.endpoints
    assert g.cleanup_status == 'eigene_konfiguration_entfernt'
    g.stop()
    assert len(client.calls) == 2


def test_tablet_configuration_never_rewritten():
    client = Client(('spotlab', 'Tablet'))
    before = client.config.SerializeToString()
    g = guard(client)
    g.stop()
    assert client.calls == ['deregister', 'shutdown']
    assert client.config.SerializeToString() == before
    assert g.cleanup_status == 'abgemeldet_fremde_konfiguration_erhalten'


@pytest.mark.parametrize('changed', ['config', 'endpoint'])
def test_replaced_registration_is_not_touched(changed):
    client = Client()
    g = guard(client)
    if changed == 'config':
        client.config.unique_id = 'tablet-config'
    else:
        client.config.endpoints[0].unique_id = 'other-device'
    g.stop()
    assert client.calls == ['shutdown']
    assert g.cleanup_status == 'bereits_abgegeben'


def test_shutdown_failure_cannot_skip_removal():
    client = Client()
    guard(client, RuntimeError('shutdown failed')).stop()
    assert client.calls == ['set_config', 'shutdown']
    assert not client.config.endpoints


@pytest.mark.parametrize('error', [RuntimeError('motors on'), TimeoutError('network lost')])
def test_rejected_removal_is_not_reported_as_success(error):
    client = Client()
    client.fail = error
    g = guard(client)
    g.stop()
    assert g.cleanup_status == 'fehlgeschlagen'
    assert client.config.endpoints
    assert client.calls[-1] == 'shutdown'


def test_interrupt_still_stops_keepalive_then_propagates():
    client = Client()
    client.fail = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        guard(client).stop()
    assert client.calls[-1] == 'shutdown'


def test_failed_registration_rolls_back_own_new_configuration():
    client = Client(())
    g = module.EstopGuard(client)
    with pytest.raises(RuntimeError, match='registration failed'):
        g.start()
    assert not client.config.endpoints
    assert client.calls == ['set_config', 'set_config']


def test_failed_acquisition_without_config_id_cannot_remove_someone_else():
    client = Client()
    g = guard(client)
    g._endpoint._config_id = None
    g.stop()
    assert client.calls == ['shutdown']


# ------------------------------------------------ Fruehe Ausstiege sind nachlesbar
#
# Lauf 20260916T143307Z_6fdb5181 (16.09.2026, echter Spot, Software 5.1.3):
# close() lief regulaer durch, danach stand der Endpunkt 'spotlab' weiterhin in
# der Konfiguration des Roboters (157 s ohne gueltige Antwort). diagnose.log
# enthielt KEINE Zeile zur E-Stop-Abgabe: _abmelden() war stumm frueh
# ausgestiegen, und es war nicht nachlesbar, an welcher Bedingung. Rueckblick
# ueber alle 84 Laeufe am echten Roboter seit dem 09.09.2026: nie eine
# Abgabe-Zeile, auch nicht nach einem normalen Ende. Deshalb schreibt jeder
# fruehe Ausstieg, welche Bedingung griff und welche IDs er gesehen hat.


def _protokolliert(tmp_path, aktion):
    from spotlab import protokoll

    protokoll.setze_ziel(tmp_path)
    try:
        aktion()
    finally:
        protokoll.setze_ziel(None)
    datei = tmp_path / protokoll.DATEINAME
    return datei.read_text(encoding="utf-8") if datei.exists() else ""


def test_geaenderte_konfigurations_id_steht_mit_beiden_ids_im_protokoll(tmp_path):
    client = Client()
    g = guard(client)
    client.config.unique_id = 'tablet-config'
    text = _protokolliert(tmp_path, g.stop)
    assert 'E-Stop-Abgabe uebersprungen' in text
    assert 'Konfigurations-ID' in text
    assert 'own-config' in text and 'tablet-config' in text
    assert g.cleanup_status == 'bereits_abgegeben'


def test_fremde_endpunkt_id_steht_mit_eigener_und_aktiver_id_im_protokoll(tmp_path):
    client = Client()
    g = guard(client)
    client.config.endpoints[0].unique_id = 'other-device'
    text = _protokolliert(tmp_path, g.stop)
    assert 'E-Stop-Abgabe uebersprungen' in text
    assert 'Endpunkt' in text
    assert 'id-spotlab' in text and 'other-device' in text
    # Die andere Bedingung darf nicht beschuldigt werden: die Config-ID stimmte.
    assert 'Konfigurations-ID geaendert' not in text
    assert g.cleanup_status == 'bereits_abgegeben'


def test_fehlende_eigene_registrierung_steht_im_protokoll(tmp_path):
    client = Client()
    g = guard(client)
    g._endpoint._config_id = None
    text = _protokolliert(tmp_path, g.stop)
    assert 'E-Stop-Abgabe uebersprungen' in text
    assert 'keine eigene Registrierung' in text
    assert client.calls == ['shutdown']


def test_eine_zu_ende_gefuehrte_abgabe_meldet_kein_ueberspringen(tmp_path):
    client = Client()
    text = _protokolliert(tmp_path, guard(client).stop)
    assert 'E-Stop-Abgabe: eigene_konfiguration_entfernt' in text
    assert 'uebersprungen' not in text


# ------------------------------------------------ Hypothese zu Lauf 20260916T143307Z
#
# Was am Roboter beobachtet wurde, passt zu KEINER Aenderung durch das
# Motor-Aus: die Abgabe kam in allen 84 Laeufen seit dem neuen Abbau nicht zu
# Ende, auch nach normalen Enden. Der alte Abbau (SDK deregister() mit derselben
# Konfigurations-ID) war dagegen bis zum 09.09. stumm erfolgreich -- die
# Konfigurations-ID stimmt also am Ende noch. Bleibt der Endpunkt-Abgleich:
# RegisterEstopEndpoint gibt laut Proto einen Endpunkt zurueck, dessen
# unique_id "vom Server vergeben" ist, waehrend GetEstopConfig weiter den
# Konfigurationsplatz zeigt. Ob der echte Roboter sich so verhaelt, muss der
# naechste Lauf mit der Protokollzeile zeigen; dieses Modell zeigt nur, dass
# die Zeile den Fall dann erklaert.


class RegistrierungVergibtNeueId(Client):
    def register(self, target_config_id, endpoint, **kwargs):
        assert target_config_id == self.config.unique_id
        for ep in self.config.endpoints:
            if ep.name == endpoint._name:
                registriert = estop_pb2.EstopEndpoint()
                registriert.CopyFrom(ep)
                registriert.unique_id = 'registriert-' + ep.unique_id
                return registriert
        raise AssertionError('Endpunkt nicht in der Konfiguration')

    def check_in(self, *args, **kwargs):
        return None


class StillerKeepalive:
    def __init__(self, endpoint, **kwargs):
        self.endpoint = endpoint

    def allow(self):
        pass

    def shutdown(self):
        pass


def test_hypothese_zurueckgelassener_endpunkt_wird_im_protokoll_erklaert(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'EstopKeepAlive', StillerKeepalive)
    client = RegistrierungVergibtNeueId(())
    g = module.EstopGuard(client)
    g.start()
    assert g._endpoint.unique_id == 'registriert-new-endpoint'
    text = _protokolliert(tmp_path, g.stop)
    # Der Befund vom Roboter: der eigene Endpunkt bleibt in der Konfiguration ...
    assert [ep.name for ep in client.config.endpoints] == ['spotlab']
    assert g.cleanup_status == 'bereits_abgegeben'
    # ... aber jetzt steht im Protokoll, woran es lag: an den beiden IDs.
    assert 'E-Stop-Abgabe uebersprungen' in text
    assert 'registriert-new-endpoint' in text
    assert "('spotlab', 'new-endpoint')" in text
