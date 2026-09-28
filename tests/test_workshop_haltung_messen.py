"""Das Messprogramm für Abnahme A41 (Physik Stufe B, 28.09.2026) -- ohne Roboter geprüft."""
import json


def test_das_messprogramm_faehrt_die_acht_posen_und_setzt_sich(tmp_path):
    """Ohne Roboter (Trockenlauf) und ohne Warten: die Befehlsfolge, die A41 am Gerät fährt."""
    import importlib.util
    from pathlib import Path

    import spotlab

    quelle = Path(spotlab.__file__).parent / 'workshop' / 'beispiele' / 'haltung_messen.py'
    spec = importlib.util.spec_from_file_location('haltung_messen', quelle)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    with spotlab.connect(backend='dryrun', runs_dir=tmp_path, config_path=tmp_path / 'fehlt.toml') as spot:
        modul.messe(spot, schlaf=lambda s: None)
        lauf = spot.recorder.dir
    namen = [json.loads(z)['daten'].get('name')
             for z in (lauf / 'ereignisse.jsonl').read_text(encoding='utf-8').splitlines()
             if z.strip() and json.loads(z)['art'] == 'kommando']
    assert namen.count('pose') == 16 and namen.index('stand') < namen.index('pose') < namen.index('sit')
    assert (lauf / 'lauf.json').is_file()
