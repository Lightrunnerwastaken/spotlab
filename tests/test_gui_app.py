from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from spotlab.gui.app import MainWindow  # noqa: E402


def test_navigation_wechselt_die_ansicht(qapp):
    fenster = MainWindow()
    fenster.leiste.knoepfe["laeufe"].click()
    assert fenster.stapel.currentWidget() is fenster.ansichten["laeufe"]


def test_notaus_der_kopfleiste_erreicht_die_live_ansicht(qapp, monkeypatch):
    gerufen = []
    fenster = MainWindow()
    monkeypatch.setattr(fenster.ansichten["live"], "notaus", lambda: gerufen.append(True))
    fenster.kopf.notaus_knopf.click()
    assert gerufen == [True]


def test_zustandssignal_erreicht_kopf_und_live(qapp, tmp_path):
    from spotlab.record.run import RunRecorder

    fenster = MainWindow()
    rec = RunRecorder(tmp_path, None, backend="dryrun")
    fenster._lauf_begonnen(str(rec.dir))
    fenster._zustand(
        {"daten": {"battery": 55.0, "pose": [1.0, 0.0, 0.0],
                   "velocity": [0.2, 0.0, 0.0], "feet": [True] * 4}}
    )

    assert "55" in fenster.kopf.akku.text()
    assert "1.00" in fenster.ansichten["live"].kachel_pose.text()


def test_ohne_konfiguration_startet_die_spot_ansicht(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", tmp_path / "gibtsnicht.toml")
    fenster = MainWindow()
    assert fenster.stapel.currentWidget() is fenster.ansichten["spot"]


def test_lauf_start_wechselt_zur_live_ansicht(qapp, tmp_path):
    class FakeProzess:
        stdout = None

        def wait(self):
            return 0

    fenster = MainWindow()
    fenster._lauf_gestartet(FakeProzess(), str(tmp_path / "x.py"))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_fehlermeldungen_landen_in_der_statuszeile(qapp):
    fenster = MainWindow()
    fenster._melde("Beobachter kaputt")
    assert "Beobachter kaputt" in fenster.statuszeile.text()


def test_fremd_gestarteter_lauf_schaltet_zur_live_ansicht(qapp, tmp_path):
    """Der F5-Fall aus Abnahmepunkt A11: der Schüler soll sehen, dass es läuft."""
    from spotlab.record.run import RunRecorder

    skript = tmp_path / "hallo_spot.py"
    skript.write_text("print(1)", encoding="utf-8")

    fenster = MainWindow()
    fenster.leiste.knoepfe["laeufe"].click()
    rec = RunRecorder(tmp_path / "runs", skript, backend="dryrun")
    fenster._lauf_begonnen(str(rec.dir))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_titel_zeigt_den_skriptnamen(qapp, tmp_path):
    from spotlab.record.run import RunRecorder

    skript = tmp_path / "hallo_spot.py"
    skript.write_text("print(1)", encoding="utf-8")
    rec = RunRecorder(tmp_path / "runs", skript, backend="dryrun")

    fenster = MainWindow()
    fenster._lauf_begonnen(str(rec.dir))
    assert "hallo_spot.py" in fenster.ansichten["live"].titel.text()


def test_gui_importiert_kein_bosdyn():
    """Entwurfsregel, nicht Stil: die GUI hält nie ein Lease.

    Ein import bosdyn im GUI-Code bricht die Grundsatzentscheidung H1.
    """
    import re
    from pathlib import Path

    import spotlab.gui

    wurzel = Path(spotlab.gui.__file__).parent
    muster = re.compile(r"^\s*(from|import)\s+(bosdyn|spotlab\.backends)", re.M)
    verstoesse = [
        str(p) for p in wurzel.rglob("*.py")
        if muster.search(p.read_text(encoding="utf-8"))
    ]
    assert verstoesse == []


def test_fenster_hat_jetzt_zehn_ansichten(qapp):
    fenster = MainWindow()
    assert set(fenster.ansichten) == {
        "projekte", "code", "live", "laeufe", "karten", "umwelt", "fahren",
        "raumeditor", "anbindungen", "spot",
    }
    assert fenster.stapel.count() == 10


# --------------------------------------------------------------- Ansicht „Code"


class _FakeProzess:
    """Eine Pipe, die sofort endet — der Leser darf nicht hängen bleiben."""

    stdout = ()

    def wait(self):
        return 0


def _lauf_verzeichnis(tmp_path):
    from spotlab.record.run import RunRecorder

    skript = tmp_path / "demo.py"
    skript.write_text("print(1)", encoding="utf-8")
    recorder = RunRecorder(tmp_path / "runs", skript, backend="dryrun")
    recorder.finish("ok")
    return str(recorder.dir)


def test_seitenleiste_hat_die_ansicht_code(qapp):
    from spotlab.gui.sidebar import EINTRAEGE

    assert ("code", "Code") in EINTRAEGE


def test_ein_leser_speist_beide_ansichten(qapp, tmp_path):
    """Zwei OutputReader auf derselben Pipe teilten sich die Zeilen zufällig auf."""
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._starte_leser(_FakeProzess())
    fenster._leser.zeile.emit("Akku: 87 %")
    assert "Akku: 87 %" in fenster.ansichten["code"].ausgabe.toPlainText()
    assert "Akku: 87 %" in fenster.ansichten["live"].ausgabe.toPlainText()


def test_lauf_aus_dem_editor_schaltet_nicht_um(qapp, tmp_path):
    fenster = MainWindow()
    fenster._wechsle("code")
    fenster._lauf_aus_code(_FakeProzess(), "egal.py")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["code"]


def test_lauf_von_aussen_schaltet_weiterhin_um(qapp, tmp_path):
    """F5 in VS Code: der Schüler soll sehen, dass sein Programm läuft."""
    fenster = MainWindow()
    fenster._wechsle("code")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_nach_dem_lauf_schaltet_ein_neuer_fremdlauf_wieder_um(qapp, tmp_path):
    fenster = MainWindow()
    fenster._wechsle("code")
    fenster._lauf_aus_code(_FakeProzess(), "egal.py")
    fenster._lauf_beendet(_lauf_verzeichnis(tmp_path))
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_stopp_aus_dem_editor_geht_an_die_live_ansicht(qapp):
    fenster = MainWindow()
    gerufen = []
    fenster.ansichten["live"].stoppe = lambda: gerufen.append(True)
    fenster.ansichten["code"].stopp_gewuenscht.emit()
    assert gerufen == [True]


def test_seitenleiste_hat_die_ansicht_anbindungen(qapp):
    from spotlab.gui.sidebar import EINTRAEGE

    assert ("anbindungen", "Anbindungen") in EINTRAEGE
    schluessel = [s for s, _ in EINTRAEGE]
    assert schluessel.index("anbindungen") < schluessel.index("spot")


def test_lauf_aus_anbindungen_schaltet_nicht_um(qapp, tmp_path):
    """Wer in „Anbindungen" startet, will die Panels sehen, nicht Telemetrie."""
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._wechsle("anbindungen")
    fenster._lauf_aus_anbindungen(_FakeProzess(), "egal.py")
    fenster._lauf_begonnen(_lauf_verzeichnis(tmp_path))
    assert fenster.stapel.currentWidget() is fenster.ansichten["anbindungen"]


def test_lauf_aus_anbindungen_speist_die_ausgaben(qapp, tmp_path):
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._lauf_aus_anbindungen(_FakeProzess(), "egal.py")
    fenster._leser.zeile.emit("Fortschritt 3/20")
    assert "Fortschritt 3/20" in fenster.ansichten["live"].ausgabe.toPlainText()
    assert "Fortschritt 3/20" in fenster.ansichten["code"].ausgabe.toPlainText()


def test_arbeitsordner_erreicht_die_anbindungen(qapp, tmp_path):
    from spotlab.anbindung.manifest import DATEINAME
    from spotlab.anbindung.speicher import binde_an

    projekt = tmp_path / "fremd"
    projekt.mkdir()
    (projekt / "s.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / DATEINAME).write_text(
        '[projekt]\nname = "fremd"\n\n[[skript]]\nname = "s"\ndatei = "s.py"\n',
        encoding="utf-8",
    )
    arbeit = tmp_path / "werkstatt"
    arbeit.mkdir()
    binde_an(arbeit, projekt)

    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(arbeit))
    assert fenster.ansichten["anbindungen"].liste.count() == 1


def test_projekt_in_spotlab_oeffnen_wechselt_zur_code_ansicht(qapp, tmp_path):
    projekt = tmp_path / "demo"
    (projekt / "runs").mkdir(parents=True)
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    liste = fenster.ansichten["projekte"].projektliste
    # Nicht Zeile 0: dort steht seit dem 06.09.2026 immer "Beispiele".
    zeile = next(i for i in range(liste.count()) if liste.item(i).text() == "demo")
    liste.setCurrentRow(zeile)
    fenster.ansichten["projekte"].spotlab_knopf.click()
    assert fenster.stapel.currentWidget() is fenster.ansichten["code"]
    assert fenster.ansichten["code"].projektwahl.currentText() == "demo"


def test_aktive_karte_wird_gemerkt(qapp, tmp_path, monkeypatch):
    from spotlab.config import Config, Limits, load_config, save_config

    pfad = tmp_path / "config.toml"
    save_config(Config(ip="1.2.3.4", username="u", limits=Limits()), pfad)
    monkeypatch.setattr("spotlab.config.CONFIG_PATH", pfad)

    fenster = MainWindow()
    fenster._merke_aktive_karte("turnhalle")
    assert load_config(pfad).active_map == "turnhalle"


# ======================================= S1.8 zwei gleichzeitige Laeufe
#
# `_lauf_begonnen` setzte den Live-Lauf bedingungslos auf das zuletzt entdeckte
# Verzeichnis. Startet ein Schueler aus "Projekte" und danach aus "Code" -- oder
# laeuft zusaetzlich ein F5-Lauf aus VS Code (A11 sieht das ausdruecklich vor) --
# zeigte die Live-Ansicht auf den falschen Prozess. Stopp und NOT-AUS trafen
# dann einen anderen Lauf als den, der den Roboter haelt.


def _zweit_lauf(tmp_path, name):
    import json

    ordner = tmp_path / name
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "lauf.json").write_text(
        json.dumps({"pid": 4711, "ergebnis": "läuft", "skript": f"{name}.py"}),
        encoding="utf-8",
    )
    (ordner / "zustand.jsonl").write_text("{}\n", encoding="utf-8")
    return ordner


@pytest.fixture
def lebendig(monkeypatch):
    """Welche Laeufe leben, sagt der Test -- nicht die Wanduhr.

    Ob ein Lauf lebt, misst `workshop/control.py::ist_aktiv` am Alter von
    `zustand.jsonl` (Fenster: 2 s), und DAS hat eigene Tests (`test_control.py`,
    mit gesetztem Alter statt echter Wartezeit). Die Tests hier prueften etwas
    anderes: WOHIN Stopp und NOT-AUS zeigen, wenn schon ein Lauf laeuft. Ueber
    die echte Uhr hing das an der Maschinenlast -- vergingen zwischen dem
    Anlegen der Datei und der Behauptung mehr als zwei Sekunden, galt der erste
    Lauf als tot und die Weiche stellte richtig, aber der Test behauptete das
    Gegenteil (einmal in einem vollen Suite-Lauf am 09.09.2026). Eine
    Attrappe hier ist kein Verlust an Deckung, sondern die Trennung zweier
    Fragen: das Messen der Lebenszeichen und die Weiche dahinter.
    """
    from spotlab.gui import app as app_modul

    lebende = set()
    monkeypatch.setattr(app_modul, "ist_aktiv",
                        lambda verzeichnis, *a, **kw: Path(verzeichnis) in lebende)
    return lebende


def test_ein_zweiter_lauf_entfuehrt_den_notaus_nicht(qapp, tmp_path, lebendig):
    """Der erste Lauf laeuft noch -- die Live-Ansicht muss bei ihm bleiben."""
    from spotlab.gui.app import MainWindow

    erst = _zweit_lauf(tmp_path, "lauf_a")
    zweit = _zweit_lauf(tmp_path, "lauf_b")
    lebendig.update({erst, zweit})
    fenster = MainWindow()
    fenster._lauf_begonnen(erst)
    assert fenster.ansichten["live"]._lauf == erst

    fenster._lauf_begonnen(zweit)
    assert fenster.ansichten["live"]._lauf == erst, (
        "Der NOT-AUS zeigt jetzt auf den zweiten Lauf, waehrend der erste faehrt."
    )


def test_der_zweite_lauf_wird_gemeldet(qapp, tmp_path, lebendig):
    """Stillschweigend waere schlimmer als gar nicht: der Schueler glaubt sonst,
    er sehe seinen eben gestarteten Lauf."""
    from spotlab.gui.app import MainWindow

    erst, zweit = _zweit_lauf(tmp_path, "lauf_a"), _zweit_lauf(tmp_path, "lauf_b")
    lebendig.update({erst, zweit})
    fenster = MainWindow()
    meldungen = []
    fenster.ansichten["live"].meldung.connect(meldungen.append)
    fenster._lauf_begonnen(erst)
    fenster._lauf_begonnen(zweit)
    assert meldungen, "kein Hinweis auf den zweiten Lauf"
    assert "zwei" in meldungen[-1].lower() or "läuft bereits" in meldungen[-1].lower()


def test_nach_dem_ende_wird_der_wartende_lauf_uebernommen(qapp, tmp_path, lebendig):
    from spotlab.gui.app import MainWindow

    erst = _zweit_lauf(tmp_path, "lauf_a")
    zweit = _zweit_lauf(tmp_path, "lauf_b")
    lebendig.update({erst, zweit})
    fenster = MainWindow()
    fenster._lauf_begonnen(erst)
    fenster._lauf_begonnen(zweit)
    lebendig.discard(erst)                      # der erste ist fertig
    fenster._lauf_beendet(erst)
    assert fenster.ansichten["live"]._lauf == zweit


def test_ein_wartender_lauf_der_inzwischen_tot_ist_rueckt_nicht_nach(qapp, tmp_path, lebendig):
    """Sonst zeigte die Ansicht auf eine Leiche -- und der NOT-AUS traefe niemanden."""
    from spotlab.gui.app import MainWindow

    erst = _zweit_lauf(tmp_path, "lauf_a")
    zweit = _zweit_lauf(tmp_path, "lauf_b")
    lebendig.update({erst, zweit})
    fenster = MainWindow()
    fenster._lauf_begonnen(erst)
    fenster._lauf_begonnen(zweit)
    lebendig.clear()                            # beide sind inzwischen fertig
    fenster._lauf_beendet(erst)
    assert fenster.ansichten["live"]._lauf is None and fenster._aktiver_lauf is None


def test_ein_toter_erster_lauf_gibt_den_platz_frei(qapp, tmp_path, lebendig):
    """Gegenprobe: sonst blockierte eine Leiche die Ansicht fuer immer."""
    from spotlab.gui.app import MainWindow

    erst = _zweit_lauf(tmp_path, "lauf_a")
    zweit = _zweit_lauf(tmp_path, "lauf_b")
    lebendig.add(zweit)                         # nur der zweite lebt
    fenster = MainWindow()
    fenster._lauf_begonnen(erst)
    fenster._lauf_begonnen(zweit)
    assert fenster.ansichten["live"]._lauf == zweit


def test_derselbe_lauf_nochmal_ist_kein_zweiter(qapp, tmp_path, lebendig):
    from spotlab.gui.app import MainWindow

    erst = _zweit_lauf(tmp_path, "lauf_a")
    lebendig.add(erst)
    fenster = MainWindow()
    meldungen = []
    fenster.ansichten["live"].meldung.connect(meldungen.append)
    fenster._lauf_begonnen(erst)
    fenster._lauf_begonnen(erst)
    assert fenster.ansichten["live"]._lauf == erst
    assert not meldungen


# ============================== S1.8b Kartenaufnahme ueberlebt das Schliessen


def test_schliessen_beendet_auch_den_kartenaufnehmer(qapp, tmp_path):
    """Der RecordingWorker ist ein QThread mit einer OFFENEN Robotersitzung.
    closeEvent stoppte nur den RunWatcher; der Thread blieb als Kind eines
    zerstoerten Widgets zurueck -- dasselbe Absturzmuster wie beim JediWorker,
    hier aber mit einer laufenden Verbindung zum Spot."""
    from PySide6.QtGui import QCloseEvent

    from spotlab.gui.app import MainWindow

    fenster = MainWindow()
    beendet = []

    class FakeWorker:
        def schliesse(self):
            beendet.append("schliesse")

        def wait(self, ms):
            return True

    fenster.ansichten["karten"]._worker = FakeWorker()
    fenster.closeEvent(QCloseEvent())
    assert beendet == ["schliesse"], "die Kartenaufnahme lief nach dem Schliessen weiter"


def test_ein_roboterlauf_aus_anbindungen_schaltet_zur_live_ansicht(qapp, tmp_path):
    """S1.9: bei `roboter = true` gehoert der NOT-AUS in Sichtweite.

    Wer in "Anbindungen" startet, will sonst die Panels sehen -- aber fremder
    Code, der den echten Spot bewegt, ist der am wenigsten geprueften Startweg
    im ganzen Fenster."""
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._wechsle("anbindungen")
    fenster._lauf_aus_anbindungen(_FakeProzess(), "fahrt.py")
    fenster.ansichten["anbindungen"].roboterlauf.emit()
    assert fenster.stapel.currentWidget() is fenster.ansichten["live"]


def test_der_stopp_aus_anbindungen_geht_an_dieselbe_live_ansicht(qapp):
    """Projektregel: dieselbe Funktion aufzurufen genuegt nicht -- der
    freundliche Stopp haengt am Lauf-Verzeichnis, das nur die Live-Ansicht hat."""
    fenster = MainWindow()
    gerufen = []
    fenster.ansichten["live"].stoppe = lambda: gerufen.append(True)
    fenster.ansichten["anbindungen"].stopp_gewuenscht.emit()
    assert gerufen == [True]


def test_das_lauf_ende_versteckt_den_stopp_knopf_in_anbindungen(qapp, tmp_path):
    fenster = MainWindow()
    fenster.ansichten["anbindungen"].lauf_laeuft(True)
    fenster._lauf_beendet(_zweit_lauf(tmp_path, "lauf_a"))
    assert fenster.ansichten["anbindungen"].stopp_knopf.isHidden()


def test_fenster_schliessen_fragt_bei_ungespeicherten_aenderungen(qapp, tmp_path):
    """S2.1: X-Knopf und Alt+F4 verwarfen Arbeit kommentarlos, obwohl das
    einzelne Reiter-Schliessen laengst fragt."""
    from PySide6.QtGui import QCloseEvent

    projekt = tmp_path / "demo"
    (projekt / "runs").mkdir(parents=True)
    (projekt / "a.py").write_text("x = 1\n", encoding="utf-8")

    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    code = fenster.ansichten["code"]
    code.oeffne(projekt / "a.py")
    code._verschmutzt(code.reiter.currentWidget(), True)

    gefragt = []
    fenster.frage_beim_schliessen = lambda pfade: gefragt.append(list(pfade)) or "abbrechen"
    ereignis = QCloseEvent()
    fenster.closeEvent(ereignis)
    assert gefragt and gefragt[0][0].name == "a.py"
    assert not ereignis.isAccepted(), "das Fenster wurde trotz Abbruch geschlossen"


def test_ohne_ungespeicherte_aenderungen_wird_nicht_gefragt(qapp, tmp_path):
    from PySide6.QtGui import QCloseEvent

    fenster = MainWindow()
    gefragt = []
    fenster.frage_beim_schliessen = lambda pfade: gefragt.append(True) or "abbrechen"
    ereignis = QCloseEvent()
    ereignis.accept()
    fenster.closeEvent(ereignis)
    assert gefragt == []
    assert ereignis.isAccepted()


# ------------------------------------------------- Der virtuelle Lauf


class _FakeProzess:
    stdout = None

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


def test_ein_virtueller_lauf_oeffnet_das_eigene_fenster(qapp, tmp_path):
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("sim")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    assert fenster.uebungsfenster is not None
    assert fenster.uebungsfenster.isVisible()


def test_ein_trockenlauf_oeffnet_kein_fenster(qapp, tmp_path):
    """Ein Fenster, das bei jedem Lauf aufspringt, wird weggeklickt und dann
    ignoriert."""
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("dryrun")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    assert fenster.uebungsfenster is None


def test_die_posen_des_laufs_landen_im_uebungsfenster(qapp, tmp_path):
    """Die Aufzeichnung fuehrt yaw im BOGENMASS (`zustand.jsonl`), gezeichnet
    wird in Grad. Ohne Umrechnung zeigte der Strich in eine falsche Richtung."""
    import math

    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("sim")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    fenster._zustand({"daten": {"battery": 90.0, "pose": [1.5, 2.0, math.pi / 2]}})

    assert fenster.uebungsfenster.plot.spur()[-1] == (1.5, 2.0)
    assert round(fenster.uebungsfenster.plot.blick()) == 90


def test_der_raum_kommt_aus_dem_verbunden_ereignis(qapp, tmp_path):
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("sim")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    fenster._ereignis({"art": "verbunden", "daten": {"backend": "sim", "raum": "durchgang"}})

    assert fenster.uebungsfenster.plot.raum() is not None


def test_ein_anstoss_wird_im_uebungsfenster_vermerkt(qapp, tmp_path):
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("sim")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    fenster._ereignis({"art": "angestossen", "daten": {"x": 2.0, "y": 3.0}})

    assert fenster.uebungsfenster.plot.anstoesse() == [(2.0, 3.0)]


def test_der_startknopf_im_uebungsraum_erzwingt_das_sim_backend(qapp):
    """Er darf NICHT erben, was im Editor eingestellt ist -- sonst startet ein
    Knopf in der Ansicht „Übungsraum" den echten Spot."""
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("real")
    fenster.ansichten["raumeditor"].starten.click()
    # 2D oder 3D, je nachdem, was auf diesem Laptop laeuft -- nie der Roboter.
    assert fenster.ansichten["code"].gewaehltes_backend() in ("sim", "mujoco")


def test_der_knopf_im_uebungsraum_wandert_mit_dem_lauf(qapp):
    fenster = MainWindow()
    fenster.ansichten["code"]._setze_laeuft(True)
    assert "Stopp" in fenster.ansichten["raumeditor"].starten.text()
    fenster.ansichten["code"].lauf_beendet()
    assert "starten" in fenster.ansichten["raumeditor"].starten.text()


def test_der_stopp_im_uebungsfenster_geht_an_die_live_ansicht(qapp, tmp_path, monkeypatch):
    """Delegation, keine zweite Kopie: der freundliche Stopp haengt am
    Lauf-Verzeichnis, das nur LiveView vom Watcher bekommt."""
    fenster = MainWindow()
    gestoppt = []
    monkeypatch.setattr(fenster.ansichten["live"], "stoppe",
                        lambda: gestoppt.append(True))
    fenster.ansichten["code"].setze_backend("sim")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    fenster.uebungsfenster.stopp.click()
    assert gestoppt == [True]


def test_der_virtuelle_lauf_bekommt_raum_und_start_der_ansicht(qapp, tmp_path, monkeypatch):
    """Der Lauf vom 04.09.2026 hatte `"raum": null` und startete bei (0, 0):
    die Konfiguration kannte den Raum nicht, weil niemand in die Zeichnung
    geklickt hatte. Was auf dem Bildschirm steht, geht jetzt direkt mit --
    so, wie es auf der Platte liegt: ein geaenderter Raum wird vorher
    gespeichert, sonst faehrt der Lauf in einem anderen Raum als dem
    gezeigten (06.09.2026)."""
    from PySide6.QtWidgets import QInputDialog

    fenster = MainWindow()
    fenster.ansichten["raumeditor"].setze_arbeitsordner(tmp_path)
    fenster.ansichten["raumeditor"].waehle_raum("moebliert")
    fenster.ansichten["raumeditor"].steuerung.setze_feld(("start",), "x", 2.0)
    fenster.ansichten["code"].setze_backend("sim")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("mein raum", True))

    umgebung = fenster.ansichten["code"].zusatz_umgebung()
    assert umgebung["SPOTLAB_RAUM"] == "mein raum"
    assert umgebung["SPOTLAB_RAUM_START"].startswith("2.00,1.00")
    assert (tmp_path / "raeume" / "mein raum.toml").is_file()


def test_ein_echter_lauf_bekommt_keinen_raum(qapp):
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("real")
    assert fenster.ansichten["code"].zusatz_umgebung() == {}


# ------------------------------------------------- Uebungsraum 3D


def test_der_uebungsraum_knopf_nimmt_3d_wenn_es_da_ist(qapp, monkeypatch):
    from spotlab.gui.editor import view as modul

    monkeypatch.setattr(modul.importlib.util, "find_spec", lambda name: object())
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("real")
    fenster.ansichten["raumeditor"].starten.click()
    assert fenster.ansichten["code"].gewaehltes_backend() == "mujoco"


def test_der_uebungsraum_knopf_nimmt_2d_ohne_spotsim(qapp, monkeypatch):
    from spotlab.gui.editor import view as modul

    monkeypatch.setattr(modul.importlib.util, "find_spec", lambda name: None)
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("real")
    fenster.ansichten["raumeditor"].starten.click()
    assert fenster.ansichten["code"].gewaehltes_backend() == "sim"


def test_auch_der_3d_lauf_bekommt_raum_und_start(qapp, monkeypatch):
    from spotlab.gui.editor import view as modul

    monkeypatch.setattr(modul.importlib.util, "find_spec", lambda name: object())
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("mujoco")
    assert fenster.ansichten["code"].zusatz_umgebung().get("SPOTLAB_RAUM")


def test_die_ansicht_des_laufs_erreicht_das_uebungsfenster(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QImage

    from spotlab.gui.editor import view as modul

    monkeypatch.setattr(modul.importlib.util, "find_spec", lambda name: object())
    fenster = MainWindow()
    fenster.ansichten["code"].setze_backend("mujoco")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    assert fenster.uebungsfenster is not None and fenster.uebungsfenster.isVisible()

    pfad = tmp_path / "ansicht.jpg"
    bild = QImage(16, 9, QImage.Format_RGB32)
    bild.fill(QColor(10, 20, 30))
    bild.save(str(pfad), "JPG")
    fenster._ansicht(str(pfad))
    assert not fenster.uebungsfenster.bild.isHidden()


def test_der_arbeitsordner_bekommt_die_beispiele(qapp, tmp_path):
    """„Immer zu finden": die GUI legt den Ordner an und zeigt ihn als Projekt."""
    fenster = MainWindow()
    fenster._setze_arbeitsordner(str(tmp_path))
    assert (tmp_path / "Beispiele" / "durchgang_finden.py").is_file()
    wahl = fenster.ansichten["code"].projektwahl
    assert "Beispiele" in [wahl.itemText(i) for i in range(wahl.count())]


def test_ein_ungespeicherter_raum_startet_keinen_lauf(qapp, tmp_path, monkeypatch):
    """Der Lauf vom 06.09.2026: die rekonstruierten Katakomben waren nie
    gespeichert, der Start kam aus „Code" -- am Raumeditor-Knopf vorbei.
    `SPOTLAB_RAUM` ging leer mit, MuJoCo fuhr ohne Waende, und die Zeichnung
    zeigte die Waende trotzdem."""
    from PySide6.QtWidgets import QInputDialog

    from spotlab.errors import SpotlabError

    fenster = MainWindow()
    fenster.ansichten["raumeditor"].setze_arbeitsordner(tmp_path)
    fenster.ansichten["raumeditor"].neu()
    fenster.ansichten["code"].setze_backend("sim")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    with pytest.raises(SpotlabError, match="gespeichert"):
        fenster.ansichten["code"].zusatz_umgebung()


def test_ein_lauf_ohne_raum_zeigt_keine_waende(qapp, tmp_path):
    """Die Zeichnung ist aus der Ansicht vorbelegt; sagt das `verbunden`-
    Ereignis „kein Raum", muss sie das zeigen, statt Waende zu behaupten,
    die der Lauf nie hatte."""
    fenster = MainWindow()
    fenster.ansichten["raumeditor"].waehle_raum("moebliert")
    fenster.ansichten["code"].setze_backend("sim")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    assert fenster.uebungsfenster.plot.raum() is not None            # vorbelegt
    fenster._ereignis({"art": "verbunden", "daten": {"backend": "sim", "raum": None}})
    assert fenster.uebungsfenster.plot.raum() is None
    assert "keinem Raum" in fenster.uebungsfenster.zeile.text()


def test_hoehe_und_nick_des_laufs_erreichen_das_uebungsfenster(qapp, tmp_path):
    fenster = MainWindow()
    fenster.ansichten["raumeditor"].waehle_raum("moebliert")
    fenster.ansichten["code"].setze_backend("sim")
    fenster._lauf_aus_code(_FakeProzess(), str(tmp_path / "x.py"))
    fenster._zustand({"t": 1.0, "daten": {"pose": [1.0, 2.0, 0.0], "z": 1.72, "pitch": -0.2094}})
    assert "1.72 m" in fenster.uebungsfenster.hoehe.text() and "-12°" in fenster.uebungsfenster.hoehe.text()


def test_fahren_startet_das_programm_aus_beispiele_und_das_fenster_kennt_es(qapp, tmp_path, monkeypatch):
    from dataclasses import replace

    from spotlab.config import Config, Limits

    fenster = MainWindow()
    fenster._config = replace(fenster._config or Config(ip="", username="", limits=Limits()),
                              workspace=str(tmp_path))
    gestartet = []
    monkeypatch.setattr(fenster.ansichten["code"], "starte_skript", lambda pfad: gestartet.append(pfad))
    fenster.ansichten["raumeditor"].fahrt_gewuenscht.emit()
    assert gestartet == [tmp_path / "Beispiele" / "fahren.py"] and gestartet[0].is_file()
    assert fenster.ansichten["code"].gewaehltes_backend() in ("sim", "mujoco")
    fenster._oeffne_uebungsfenster("fahren.py")
    assert fenster.uebungsfenster.tastenfahrt.aktiv
    fenster.uebungsfenster.close()


def test_der_tab_fahren_startet_dasselbe_programm_am_echten_spot(qapp, tmp_path, monkeypatch):
    """Derselbe Startweg wie der Fahrmodus im Raumeditor, nur mit dem Backend „real":
    das Programm aus Beispiele, der Editor als der eine Startweg, die App merkt sich,
    dass der Lauf in den Tab gehoert."""
    from dataclasses import replace

    from spotlab.config import Config, Limits

    fenster = MainWindow()
    fenster._config = replace(fenster._config or Config(ip="", username="", limits=Limits()),
                              workspace=str(tmp_path))
    gestartet = []
    monkeypatch.setattr(fenster.ansichten["code"], "starte_skript", lambda pfad: gestartet.append(pfad))
    fenster.ansichten["fahren"].fahrt_gewuenscht.emit()
    assert gestartet == [tmp_path / "Beispiele" / "fahren.py"]
    assert fenster.ansichten["code"].gewaehltes_backend() == "real"
    assert fenster._fahrt_erwartet == "real"


def test_der_tab_fahren_faehrt_wirklich_ueber_knopf_watcher_und_tasten(qapp, tmp_path, monkeypatch):
    """Die ganze Kette wie beim Fahrmodus, mit dem Trockenlauf-Backend an Stelle des
    Roboters: Knopf im Tab, echter Prozess, der Watcher meldet den Lauf, der Tab
    bekommt das Verzeichnis und die Tastatur, W wird ein walk-Kommando in der
    Aufzeichnung. Der Tab bleibt vorne -- dort kommen die Tasten an."""
    import json
    import time
    from dataclasses import replace
    from pathlib import Path

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from spotlab.config import Config, Limits
    from spotlab.gui import app as app_modul
    from spotlab.workshop.control import stoppe_freundlich
    from tests_zeitgrenzen import TEST_TIMEOUT_S

    monkeypatch.setattr(app_modul, "FAHREN_BACKEND", "dryrun")
    fenster = MainWindow()
    fenster._config = replace(fenster._config or Config(ip="", username="", limits=Limits()),
                              workspace=str(tmp_path))
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._wechsle("fahren")
    tab = fenster.ansichten["fahren"]
    tab.fahrt_gewuenscht.emit()
    assert fenster.ansichten["code"].laeuft(), fenster.statuszeile.text()
    prozess = fenster.ansichten["code"]._prozess
    lauf = None
    try:
        frist = time.monotonic() + TEST_TIMEOUT_S
        while lauf is None and time.monotonic() < frist:
            qapp.processEvents()
            time.sleep(0.05)
            lauf = tab.tastenfahrt.lauf_dir if tab.laeuft() else None
        assert lauf is not None, "der Watcher hat dem Tab nie das Lauf-Verzeichnis gemeldet"
        assert fenster.stapel.currentWidget() is tab
        QTest.keyPress(tab, Qt.Key_W)
        ende = time.monotonic() + 2.0
        while time.monotonic() < ende:
            qapp.processEvents()
            time.sleep(0.02)
        QTest.keyRelease(tab, Qt.Key_W)
        stoppe_freundlich(lauf)
        prozess.wait(timeout=TEST_TIMEOUT_S)
    finally:
        if prozess.poll() is None:
            prozess.kill()
    zeilen = (Path(lauf) / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
    kommandos = [json.loads(z)["daten"].get("name") for z in zeilen
                 if z.strip() and json.loads(z)["art"] == "kommando"]
    assert "walk" in kommandos, kommandos
    meta = json.loads((Path(lauf) / "lauf.json").read_text(encoding="utf-8"))
    assert meta["backend"] == "dryrun"


def test_fahren_ohne_arbeitsordner_sagt_es(qapp, monkeypatch):
    fenster = MainWindow()
    fenster._config = None
    gestartet, meldungen = [], []
    monkeypatch.setattr(fenster.ansichten["code"], "starte_skript", lambda pfad: gestartet.append(pfad))
    monkeypatch.setattr(fenster, "_melde", meldungen.append)
    fenster.ansichten["raumeditor"].fahrt_gewuenscht.emit()
    assert gestartet == [] and meldungen and "Arbeitsordner" in meldungen[0]


def test_fahren_faehrt_wirklich_ueber_knopf_watcher_und_tasten(qapp, tmp_path, monkeypatch):
    """Die ganze Kette, wie sie beim Autor scheiterte (07.09.2026): Knopf im Raumeditor,
    echter Prozess, der Watcher meldet den Lauf, das Uebungsfenster erfaehrt das
    Verzeichnis, W schreibt fahrt.json, Spot bewegt sich in der Aufzeichnung."""
    import json
    import time
    from dataclasses import replace

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from spotlab.config import Config, Limits
    from spotlab.gui import app as app_modul
    from spotlab.workshop.control import stoppe_freundlich
    from tests_zeitgrenzen import TEST_TIMEOUT_S

    monkeypatch.setattr(app_modul, "verfuegbare_backends", lambda: [("2D", "sim")])
    fenster = MainWindow()
    fenster._config = replace(fenster._config or Config(ip="", username="", limits=Limits()),
                              workspace=str(tmp_path))
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster.ansichten["raumeditor"].waehle_raum("leer")
    fenster.ansichten["raumeditor"].fahrt_gewuenscht.emit()
    assert fenster.ansichten["code"].laeuft(), fenster.statuszeile.text()
    prozess = fenster.ansichten["code"]._prozess
    lauf = None
    try:
        frist = time.monotonic() + TEST_TIMEOUT_S
        while lauf is None and time.monotonic() < frist:
            qapp.processEvents()
            time.sleep(0.05)
            if fenster.uebungsfenster is not None:
                lauf = fenster.uebungsfenster.tastenfahrt.lauf_dir
        assert lauf is not None, "der Watcher hat dem Uebungsfenster nie das Lauf-Verzeichnis gemeldet"
        assert fenster.uebungsfenster.tastenfahrt.aktiv and fenster.uebungsfenster.isVisible()
        QTest.keyPress(fenster.uebungsfenster, Qt.Key_W)
        ende = time.monotonic() + 4.0                 # der 200-ms-Takt frischt den Befehl auf
        while time.monotonic() < ende:
            qapp.processEvents()
            time.sleep(0.02)
        QTest.keyRelease(fenster.uebungsfenster, Qt.Key_W)
        stoppe_freundlich(lauf)
        prozess.wait(timeout=TEST_TIMEOUT_S)
    finally:
        if prozess.poll() is None:
            prozess.kill()
        if fenster.uebungsfenster is not None:
            fenster.uebungsfenster.close()
    zeilen = [json.loads(z) for z in (lauf / "zustand.jsonl").read_text(encoding="utf-8").splitlines()
              if z.strip()]
    xs = [z["daten"]["pose"][0] for z in zeilen if "pose" in (z.get("daten") or {})]
    assert xs and max(xs) - min(xs) > 0.2, (min(xs) if xs else None, max(xs) if xs else None)


# ------------------------------------------------------- Navigation (Tab Karten)


def _karte_im_arbeitsordner(tmp_path, name="turnhalle"):
    from bosdyn.api.graph_nav import map_pb2

    from spotlab.maps.store import karten_wurzel, speichere_metadaten

    graph = map_pb2.Graph()
    for kennung, wegname, x in (("wp0", "start", 0.0), ("wp1", "kueche", 2.0)):
        wp = graph.waypoints.add()
        wp.id = kennung
        wp.annotations.name = wegname
        anker = graph.anchoring.anchors.add()
        anker.id = kennung
        anker.seed_tform_waypoint.rotation.w = 1.0
        anker.seed_tform_waypoint.position.x = x
    kante = graph.edges.add()
    kante.id.from_waypoint, kante.id.to_waypoint = "wp0", "wp1"
    ordner = karten_wurzel(tmp_path) / name
    ordner.mkdir(parents=True)
    (ordner / "graph").write_bytes(graph.SerializeToString())
    speichere_metadaten(ordner, name, "SN-1", graph)
    return ordner


def test_der_karten_tab_startet_navigieren_am_echten_spot_ueber_den_einen_startweg(qapp, tmp_path, monkeypatch):
    """Wie beim Tab „Fahren": das mitgelieferte Programm aus Beispiele, Backend
    „real" erzwungen, die gewaehlte Karte geht als SPOTLAB_KARTE mit."""
    from dataclasses import replace

    from spotlab import ENV_KARTE
    from spotlab.config import Config, Limits

    _karte_im_arbeitsordner(tmp_path)
    fenster = MainWindow()
    fenster._config = replace(fenster._config or Config(ip="", username="", limits=Limits()),
                              workspace=str(tmp_path))
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster.ansichten["code"].setze_backend("sim")
    fenster.ansichten["karten"].liste.setCurrentRow(0)
    gestartet = []
    monkeypatch.setattr(fenster.ansichten["code"], "starte_skript", lambda pfad: gestartet.append(pfad))
    fenster.ansichten["karten"].navigation_gewuenscht.emit()
    assert gestartet == [tmp_path / "Beispiele" / "navigieren.py"]
    assert (tmp_path / "Beispiele" / "navigieren.py").is_file()
    assert fenster.ansichten["code"].gewaehltes_backend() == "real"
    assert fenster._navigation_erwartet == "turnhalle"
    assert fenster._umgebung_fuer_lauf() == {ENV_KARTE: "turnhalle"}


def test_navigation_ohne_gewaehlte_karte_sagt_es(qapp, tmp_path, monkeypatch):
    from dataclasses import replace

    from spotlab.config import Config, Limits

    fenster = MainWindow()
    fenster._config = replace(fenster._config or Config(ip="", username="", limits=Limits()),
                              workspace=str(tmp_path))
    fenster._setze_arbeitsordner(str(tmp_path))
    gestartet, meldungen = [], []
    monkeypatch.setattr(fenster.ansichten["code"], "starte_skript", lambda pfad: gestartet.append(pfad))
    monkeypatch.setattr(fenster, "_melde", meldungen.append)
    fenster.ansichten["karten"].navigation_gewuenscht.emit()
    assert gestartet == [] and meldungen and "Karte" in meldungen[0]
    assert fenster._navigation_erwartet is False


def test_die_navigation_laeuft_wirklich_ueber_knopf_prozess_und_watcher(qapp, tmp_path, monkeypatch):
    """Die ganze Kette mit dem Trockenlauf an Stelle des Roboters: Knopf im Tab,
    echter Prozess, der Watcher meldet den Lauf, der Tab bekommt das Verzeichnis
    und den Stand aus `navigation.json`. Der Trockenlauf hat kein GraphNav -- der
    Lauf scheitert beim Laden der Karte, und GENAU DAS steht dann im Tab."""
    import json
    import time
    from dataclasses import replace
    from pathlib import Path

    from spotlab.config import Config, Limits
    from spotlab.gui import app as app_modul
    from spotlab.record import navigation
    from tests_zeitgrenzen import TEST_TIMEOUT_S

    monkeypatch.setattr(app_modul, "NAVIGATION_BACKEND", "dryrun")
    _karte_im_arbeitsordner(tmp_path)
    fenster = MainWindow()
    fenster._config = replace(fenster._config or Config(ip="", username="", limits=Limits()),
                              workspace=str(tmp_path))
    fenster._setze_arbeitsordner(str(tmp_path))
    fenster._wechsle("karten")
    tab = fenster.ansichten["karten"]
    tab.liste.setCurrentRow(0)
    begonnen, staende = [], []
    original_beginnt, original_stand = tab.lauf_beginnt, tab.zeige_navigation
    monkeypatch.setattr(tab, "lauf_beginnt", lambda *a, **k: (begonnen.append(a), original_beginnt(*a, **k)))
    monkeypatch.setattr(tab, "zeige_navigation", lambda s: (staende.append(s), original_stand(s)))
    tab.navigation_gewuenscht.emit()
    assert fenster.ansichten["code"].laeuft(), fenster.statuszeile.text()
    prozess = fenster.ansichten["code"]._prozess
    try:
        frist = time.monotonic() + TEST_TIMEOUT_S
        while (prozess.poll() is None or not begonnen or fenster._aktiver_lauf is not None) \
                and time.monotonic() < frist:
            qapp.processEvents()
            time.sleep(0.05)
    finally:
        if prozess.poll() is None:
            prozess.kill()
    assert begonnen, "der Watcher hat dem Tab nie das Lauf-Verzeichnis gemeldet"
    lauf = Path(begonnen[0][0])
    stand = navigation.lies_stand(lauf)
    assert stand is not None and stand["status"] == "gescheitert", stand
    assert "GraphNav" in stand["text"] or "navigieren" in stand["text"].lower(), stand["text"]
    assert any(s["status"] == "gescheitert" for s in staende), "der Stand kam nie im Tab an"
    meta = json.loads((lauf / "lauf.json").read_text(encoding="utf-8"))
    assert meta["backend"] == "dryrun"
    assert not tab.laeuft() and fenster._navigation_erwartet is False
