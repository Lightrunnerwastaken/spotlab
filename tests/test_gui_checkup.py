import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.config import Config, Limits  # noqa: E402
from spotlab.gui.views.checkup import CheckupView  # noqa: E402
from spotlab.workshop.doctor import Check  # noqa: E402


def test_felder_werden_aus_der_konfiguration_gefuellt(qapp, tmp_path, monkeypatch):
    from spotlab.config import save_config

    pfad = tmp_path / "config.toml"
    save_config(
        Config(ip="10.0.0.9", username="schueler", nickname="Bello",
               limits=Limits(max_speed=0.4, max_turn_rate=0.5)),
        pfad,
    )
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    ansicht = CheckupView()
    ansicht.lade()
    assert ansicht.ip.text() == "10.0.0.9"
    assert ansicht.benutzer.text() == "schueler"
    assert ansicht.spitzname.text() == "Bello"
    assert abs(ansicht.max_tempo.value() - 0.4) < 1e-9


def test_ohne_konfiguration_bleiben_die_felder_leer(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "gibtsnicht.toml")
    ansicht = CheckupView()
    ansicht.lade()
    assert ansicht.ip.text() == ""


def test_speichern_schreibt_konfiguration_und_passwort(qapp, tmp_path, monkeypatch):
    pfad = tmp_path / "config.toml"
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)
    passwoerter = {}
    monkeypatch.setattr(
        "spotlab.gui.views.checkup.save_password",
        lambda benutzer, wort: passwoerter.update({benutzer: wort}),
    )

    ansicht = CheckupView()
    ansicht.ip.setText("192.168.80.3")
    ansicht.benutzer.setText("schueler")
    ansicht.spitzname.setText("Spot der Kanti")
    ansicht.passwort.setText("geheim")
    ansicht.speichern_knopf.click()

    from spotlab.config import load_config

    assert load_config(pfad).ip == "192.168.80.3"
    assert passwoerter == {"schueler": "geheim"}


def test_leeres_passwort_ueberschreibt_nicht(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "config.toml")
    gerufen = []
    monkeypatch.setattr(
        "spotlab.gui.views.checkup.save_password", lambda *a: gerufen.append(a)
    )

    ansicht = CheckupView()
    ansicht.ip.setText("1.2.3.4")
    ansicht.benutzer.setText("u")
    ansicht.speichern_knopf.click()
    assert gerufen == []


def test_passwortfeld_ist_verdeckt(qapp):
    from PySide6.QtWidgets import QLineEdit

    assert CheckupView().passwort.echoMode() == QLineEdit.Password


def test_pruefergebnisse_werden_angezeigt(qapp):
    ansicht = CheckupView()
    ansicht.zeige_pruefung(
        [Check("Netz", True, "antwortet"),
         Check("Anmeldung", False, "falsch", "spotlab login")]
    )
    text = ansicht.ergebnisse.toPlainText()
    assert "Netz" in text and "spotlab login" in text


def test_speichern_behaelt_karte_raum_und_treppensperre(qapp, tmp_path, monkeypatch):
    """Befund 22.09.2026: `speichere()` baute ein FRISCHES Config-Objekt aus sechs
    Feldern; alles andere fiel auf die Vorgaben zurueck. Wer den Spitznamen aendert,
    verlor damit die aktive Karte, den Uebungsraum, die Startpose -- und `treppen`,
    einen SICHERHEITSWERT (`mobility.mit_grenze` -> `stairs_mode`). Auf der
    Kommandozeile war derselbe Fehler laengst mit `replace()` behoben."""
    from spotlab.config import load_config, save_config

    pfad = tmp_path / "config.toml"
    save_config(
        Config(ip="10.0.0.9", username="anna", nickname="Bello",
               limits=Limits(max_speed=0.4, max_turn_rate=0.5, treppen="aus"),
               active_map="Katakomben", raum="flur", raum_start="1.5,2.0,90",
               editor_command="code", default_backend="mujoco", workspace="D:/arbeit"),
        pfad,
    )
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)
    monkeypatch.setattr("spotlab.gui.views.checkup.save_password", lambda b, w: None)

    ansicht = CheckupView()
    ansicht.lade()
    ansicht.spitzname.setText("Spot")
    ansicht.speichern_knopf.click()

    neu = load_config(pfad)
    assert neu.nickname == "Spot", "das Geaenderte kommt an"
    assert neu.limits.treppen == "aus", "die Treppensperre bleibt -- sie ist eine Sicherheitseinstellung"
    assert neu.active_map == "Katakomben"
    assert neu.raum == "flur" and neu.raum_start == "1.5,2.0,90"
    assert neu.default_backend == "mujoco" and neu.workspace == "D:/arbeit"


def test_speichern_behaelt_was_inzwischen_auf_der_platte_geaendert_wurde(qapp, tmp_path, monkeypatch):
    """Pruefung 23.09.2026: die Ansicht ergaenzte die Kopie, die sie beim START
    geladen hatte. Wer inzwischen `treppen = "aus"` gesetzt hatte (Kommandozeile,
    Hauptfenster), bekam „auto“ zurueck -- ein SICHERHEITSWERT, still ueberschrieben."""
    from dataclasses import replace

    from spotlab.config import load_config, save_config

    pfad = tmp_path / "config.toml"
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)
    monkeypatch.setattr("spotlab.gui.views.checkup.save_password", lambda *a: None)
    save_config(Config(ip="10.0.0.9", username="lehrer", limits=Limits()), pfad)
    ansicht = CheckupView()                      # laedt treppen = auto
    frisch = load_config(pfad)
    save_config(replace(frisch, workspace="C:/ws", limits=replace(frisch.limits, treppen="aus")), pfad)

    ansicht.ip.setText("10.0.0.10")
    ansicht.speichere()
    nachher = load_config(pfad)
    assert nachher.ip == "10.0.0.10"
    assert nachher.limits.treppen == "aus"
    assert nachher.workspace == "C:/ws"


def test_unberuehrte_zahlenfelder_runden_die_grenze_nicht(qapp, tmp_path, monkeypatch):
    """0.125 m/s stand als 0.13 im Feld -- und wurde beim naechsten Speichern zu 0.13."""
    from spotlab.config import load_config, save_config

    pfad = tmp_path / "config.toml"
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)
    monkeypatch.setattr("spotlab.gui.views.checkup.save_password", lambda *a: None)
    save_config(Config(ip="10.0.0.9", username="lehrer",
                       limits=Limits(max_speed=0.125, max_turn_rate=0.4125)), pfad)
    ansicht = CheckupView()
    ansicht.spitzname.setText("Bello")
    ansicht.speichere()
    assert load_config(pfad).limits.max_speed == 0.125
    assert load_config(pfad).limits.max_turn_rate == 0.4125
