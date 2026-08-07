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
