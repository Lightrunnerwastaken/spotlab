import pytest

from spotlab.config import Config, Limits, load_config, load_password, save_config
from spotlab.errors import ConfigMissing


def test_speichern_und_lesen_ist_verlustfrei(tmp_path):
    pfad = tmp_path / "config.toml"
    cfg = Config(
        ip="192.168.80.3",
        username="student",
        nickname="Spot der Kanti",
        limits=Limits(max_speed=0.4, max_turn_rate=0.5),
        editor_command="code",
        default_backend="dryrun",
    )
    save_config(cfg, pfad)
    assert load_config(pfad) == cfg


def test_fehlende_datei_meldet_klartext(tmp_path):
    with pytest.raises(ConfigMissing) as info:
        load_config(tmp_path / "gibtsnicht.toml")
    assert "spotlab login" in str(info.value)


def test_vorgabewerte_wenn_abschnitte_fehlen(tmp_path):
    pfad = tmp_path / "config.toml"
    pfad.write_text('[robot]\nip = "10.0.0.1"\nusername = "u"\n', encoding="utf-8")
    cfg = load_config(pfad)
    assert cfg.limits == Limits()
    assert cfg.editor_command == "code"
    assert cfg.default_backend == "real"
    assert cfg.nickname == "Spot"


def test_passwort_faellt_auf_umgebungsvariable_zurueck(monkeypatch):
    monkeypatch.setattr("spotlab.config.keyring.get_password", lambda *_: None)
    monkeypatch.setenv("BOSDYN_CLIENT_PASSWORD", "geheim")
    assert load_password("student") == "geheim"


def test_ohne_passwort_klare_meldung(monkeypatch):
    monkeypatch.setattr("spotlab.config.keyring.get_password", lambda *_: None)
    monkeypatch.delenv("BOSDYN_CLIENT_PASSWORD", raising=False)
    with pytest.raises(ConfigMissing) as info:
        load_password("student")
    assert "spotlab login" in str(info.value)


def test_umlaute_im_spitznamen_ueberleben(tmp_path):
    pfad = tmp_path / "config.toml"
    cfg = Config(ip="1.2.3.4", username="u", nickname='Spot "Grüezi" \\ Kanti', limits=Limits())
    save_config(cfg, pfad)
    assert load_config(pfad).nickname == 'Spot "Grüezi" \\ Kanti'


def test_arbeitsordner_ueberlebt_schreiben_und_lesen(tmp_path):
    pfad = tmp_path / "config.toml"
    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(), workspace=r"D:\Schule\Spot")
    save_config(cfg, pfad)
    assert load_config(pfad).workspace == r"D:\Schule\Spot"


def test_arbeitsordner_hat_leere_vorgabe(tmp_path):
    pfad = tmp_path / "config.toml"
    pfad.write_text('[robot]\nip = "1.2.3.4"\nusername = "u"\n', encoding="utf-8")
    assert load_config(pfad).workspace == ""
