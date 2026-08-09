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


def test_aktive_karte_ueberlebt_schreiben_und_lesen(tmp_path):
    pfad = tmp_path / "config.toml"
    cfg = Config(ip="1.2.3.4", username="u", limits=Limits(), active_map="turnhalle")
    save_config(cfg, pfad)
    assert load_config(pfad).active_map == "turnhalle"


def test_aktive_karte_hat_leere_vorgabe(tmp_path):
    pfad = tmp_path / "config.toml"
    pfad.write_text('[robot]\nip = "1.2.3.4"\nusername = "u"\n', encoding="utf-8")
    assert load_config(pfad).active_map == ""


# ------------------------------------------------- Sicherheitswerte (S1.3)
#
# max_speed und max_turn_rate sind KEINE gewoehnlichen Einstellungen: an ihnen
# haengt, wie schnell ein Schueler den Roboter fahren darf. Ein Tippfehler darf
# nicht dazu fuehren, dass der Deckel wirkungslos wird -- oder schlimmer, dass
# clamp() aus wz=0 eine Dauerdrehung macht (bei negativem max_turn_rate liefert
# max(-w, min(w, 0)) genau das).


def _schreibe(tmp_path, limits_block):
    pfad = tmp_path / "config.toml"
    pfad.write_text(
        '[robot]\nip = "1.2.3.4"\nusername = "u"\n\n[limits]\n' + limits_block,
        encoding="utf-8",
    )
    return pfad


def test_unendliche_hoechstgeschwindigkeit_wird_abgewiesen(tmp_path):
    from spotlab.errors import ConfigBroken

    pfad = _schreibe(tmp_path, "max_speed = inf\nmax_turn_rate = 0.8\n")
    with pytest.raises(ConfigBroken) as fehler:
        load_config(pfad)
    assert "max_speed" in str(fehler.value)


def test_negative_hoechstgeschwindigkeit_wird_abgewiesen(tmp_path):
    from spotlab.errors import ConfigBroken

    pfad = _schreibe(tmp_path, "max_speed = -0.6\nmax_turn_rate = 0.8\n")
    with pytest.raises(ConfigBroken):
        load_config(pfad)


def test_negative_drehrate_wird_abgewiesen(tmp_path):
    """Sonst dreht der Roboter, obwohl wz=0 kommandiert wurde."""
    from spotlab.errors import ConfigBroken

    pfad = _schreibe(tmp_path, "max_speed = 0.6\nmax_turn_rate = -0.8\n")
    with pytest.raises(ConfigBroken) as fehler:
        load_config(pfad)
    assert "max_turn_rate" in str(fehler.value)


def test_null_als_deckel_wird_abgewiesen(tmp_path):
    from spotlab.errors import ConfigBroken

    with pytest.raises(ConfigBroken):
        load_config(_schreibe(tmp_path, "max_speed = 0.0\nmax_turn_rate = 0.8\n"))


def test_nan_wird_abgewiesen(tmp_path):
    from spotlab.errors import ConfigBroken

    with pytest.raises(ConfigBroken):
        load_config(_schreibe(tmp_path, "max_speed = nan\nmax_turn_rate = 0.8\n"))


def test_text_statt_zahl_wird_abgewiesen(tmp_path):
    from spotlab.errors import ConfigBroken

    with pytest.raises(ConfigBroken):
        load_config(_schreibe(tmp_path, 'max_speed = "schnell"\nmax_turn_rate = 0.8\n'))


def test_gueltige_grenzen_kommen_unveraendert_durch(tmp_path):
    """Gegenprobe: die Pruefung darf nicht alles abweisen."""
    cfg = load_config(_schreibe(tmp_path, "max_speed = 0.35\nmax_turn_rate = 0.5\n"))
    assert cfg.limits.max_speed == 0.35
    assert cfg.limits.max_turn_rate == 0.5


def test_kaputtes_toml_nennt_den_reparaturweg(tmp_path):
    """Eine halb gespeicherte Datei sperrte bisher GUI, CLI UND `spotlab login`
    zugleich -- mit rohem tomllib-Traceback."""
    from spotlab.errors import ConfigBroken

    pfad = tmp_path / "config.toml"
    pfad.write_text('[robot\nip = "1.2.3.4"\n', encoding="utf-8")
    with pytest.raises(ConfigBroken) as fehler:
        load_config(pfad)
    assert "spotlab login" in str(fehler.value)
    assert str(pfad) in str(fehler.value)


def test_unlesbare_bytes_nennen_den_reparaturweg(tmp_path):
    from spotlab.errors import ConfigBroken

    pfad = tmp_path / "config.toml"
    pfad.write_bytes(b"\xff\xfe\x00kaputt")
    with pytest.raises(ConfigBroken):
        load_config(pfad)


def test_unbekanntes_backend_wird_abgewiesen(tmp_path):
    """`backend = "reall"` fiele sonst still auf einen unbekannten Wert zurueck."""
    from spotlab.errors import ConfigBroken

    pfad = tmp_path / "config.toml"
    pfad.write_text(
        '[robot]\nip = "1.2.3.4"\nusername = "u"\n\n[defaults]\nbackend = "reall"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigBroken) as fehler:
        load_config(pfad)
    assert "reall" in str(fehler.value)


def test_kaputte_konfiguration_ist_kein_fehlende_konfiguration(tmp_path):
    """Wichtig: ConfigMissing laesst spotlab.connect() still auf dryrun
    zurueckfallen. Eine KAPUTTE Datei darf nicht so behandelt werden -- sonst
    faehrt ein Schueler im Trockenlauf und haelt das fuer den echten Roboter."""
    from spotlab.errors import ConfigBroken, ConfigMissing

    pfad = tmp_path / "config.toml"
    pfad.write_text("[robot\n", encoding="utf-8")
    with pytest.raises(ConfigBroken) as fehler:
        load_config(pfad)
    assert not isinstance(fehler.value, ConfigMissing)
