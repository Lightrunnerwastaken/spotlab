"""Die Erkennermodelle reisen im Schueler-ZIP mit.

Ohne sie findet der Folgemodus nie jemanden, und die Handzeichen bleiben stumm.
Das Release-Werkzeug nimmt nur Dateien mit der festgehaltenen Pruefsumme -- der
OpenCV-Zoo fuehrt die Modelle ueber git-lfs, und ein gewoehnlicher Download
liefert einen 132-Byte-Zeiger, der wie eine Datei aussieht und keine ist.
`einrichten.cmd` legt sie danach dorthin, wo spotlab sucht.
"""

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _lade(name):
    quelle = ROOT/'tools'/f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, quelle)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


release = _lade('schueler_release')
einrichtung = _lade('modelle_einrichten')

ZEIGER = (b'version https://git-lfs.github.com/spec/v1\n'
          b'oid sha256:8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4\n'
          b'size 232589\n')


def _summe(daten):
    return hashlib.sha256(daten).hexdigest()


def test_das_zip_bringt_genau_die_modelle_die_spotlab_sucht():
    from spotlab.backends.real import gesicht, gesten, koerper
    gesucht = {gesicht.MODELL_DATEI, koerper.MODELL_ERKENNER, koerper.MODELL_POSE,
               gesten.MODELL_HANDFLAECHE, gesten.MODELL_HANDPOSE}
    assert set(release.MODELLE) == gesucht


def test_jedes_modell_steht_mit_seiner_lizenz_im_lizenztext():
    text = (ROOT/'tools/modelle_lizenzen.txt').read_text(encoding='utf-8')
    for name in release.MODELLE:
        assert name in text
    assert 'MIT License' in text and 'Copyright (c) 2020 Shiqi Yu' in text
    assert 'Apache License' in text and 'END OF TERMS AND CONDITIONS' in text


def test_passende_modelle_werden_genommen(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'MODELLE', {'a.onnx': _summe(b'eins'), 'b.onnx': _summe(b'zwei')})
    (tmp_path/'a.onnx').write_bytes(b'eins')
    (tmp_path/'b.onnx').write_bytes(b'zwei')
    (tmp_path/'fremd.onnx').write_bytes(b'nicht im ZIP')
    assert release.modelle(tmp_path) == [tmp_path/'a.onnx', tmp_path/'b.onnx']


def test_ein_lfs_zeiger_kommt_nicht_ins_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'MODELLE', {'a.onnx': _summe(b'eins')})
    (tmp_path/'a.onnx').write_bytes(ZEIGER)
    with pytest.raises(ValueError, match=r'a\.onnx.*git-lfs'):
        release.modelle(tmp_path)


def test_ein_fehlendes_modell_bricht_den_bau_ab(tmp_path, monkeypatch):
    monkeypatch.setattr(release, 'MODELLE', {'a.onnx': _summe(b'eins')})
    with pytest.raises(ValueError, match=r'a\.onnx'):
        release.modelle(tmp_path)


def test_einrichten_legt_fehlende_modelle_ab(tmp_path):
    quelle, ziel = tmp_path/'zip', tmp_path/'home'/'.spotlab'/'modelle'
    quelle.mkdir()
    (quelle/'a.onnx').write_bytes(b'eins')
    (quelle/'LIZENZEN.txt').write_text('Lizenz', encoding='utf-8')
    assert einrichtung.einrichten(quelle, ziel) == ['a.onnx']
    assert (ziel/'a.onnx').read_bytes() == b'eins'
    assert (ziel/'LIZENZEN.txt').read_text(encoding='utf-8') == 'Lizenz'


def test_einrichten_ersetzt_einen_zeiger_und_laesst_gleiches_stehen(tmp_path):
    quelle, ziel = tmp_path/'zip', tmp_path/'modelle'
    quelle.mkdir()
    ziel.mkdir()
    (quelle/'a.onnx').write_bytes(b'eins')
    (quelle/'b.onnx').write_bytes(b'zwei')
    (ziel/'a.onnx').write_bytes(ZEIGER)
    (ziel/'b.onnx').write_bytes(b'zwei')
    assert einrichtung.einrichten(quelle, ziel) == ['a.onnx']
    assert (ziel/'a.onnx').read_bytes() == b'eins'


def test_einrichten_ohne_modelle_im_zip_meldet_es(tmp_path):
    with pytest.raises(FileNotFoundError, match='modelle'):
        einrichtung.einrichten(tmp_path/'modelle', tmp_path/'ziel')
