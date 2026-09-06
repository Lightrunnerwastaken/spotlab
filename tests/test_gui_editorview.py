import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtTest import QTest  # noqa: E402

from spotlab.gui.editor.view import EditorView  # noqa: E402
from spotlab.gui.theme import DUNKEL  # noqa: E402
from tests_zeitgrenzen import TEST_TIMEOUT_S  # noqa: E402


def _werkstatt(tmp_path):
    projekt = tmp_path / "demo"
    (projekt / "runs").mkdir(parents=True)
    (projekt / "hallo_spot.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path, projekt


def _ansicht(tmp_path):
    ordner, projekt = _werkstatt(tmp_path)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    return ansicht, ordner, projekt


# ----------------------------------------------------------------- Reiter


def test_datei_oeffnen_legt_einen_reiter_an(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    assert ansicht.reiter.count() == 1
    assert ansicht.reiter.currentWidget().toPlainText() == "x = 1\n"


def test_dieselbe_datei_zweimal_oeffnen_gibt_denselben_reiter(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.oeffne(projekt / "hallo_spot.py")
    assert ansicht.reiter.count() == 1


def test_frisch_geoeffneter_reiter_ist_nicht_verschmutzt(qapp, tmp_path):
    """rehighlight() aendert Formatierung, und Qt zaehlt das als Inhaltsaenderung.

    Mit textChanged waere jeder Reiter schon beim Oeffnen als geaendert markiert
    — und der Punkt im Titel damit bedeutungslos.
    """
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    QTest.qWait(400)          # Ruhepause abwarten: hier laeuft neu_lexen
    assert ansicht.reiter.tabText(0) == "hallo_spot.py"
    assert ansicht.aktueller_reiter().verschmutzt is False


def test_rueckgaengig_bis_zum_urzustand_loescht_die_marke(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    feld = ansicht.reiter.currentWidget()
    feld.insertPlainText("# neu\n")
    assert ansicht.reiter.tabText(0).startswith("●")
    feld.undo()
    assert ansicht.reiter.tabText(0) == "hallo_spot.py"


def test_aenderung_markiert_den_reiter(qapp, tmp_path):
    # Getippt, nicht setPlainText: das setzt Qts Modified-Flag zurueck und
    # kommt im Programm nur beim Laden und Neuladen vor, wo genau das stimmt.
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    QTest.keyClicks(ansicht.reiter.currentWidget(), "y")
    assert ansicht.reiter.tabText(0).startswith("●")


def test_speichern_schreibt_lf_und_utf8(qapp, tmp_path):
    # Ohne newline="\n" schreibt Python auf Windows CRLF, und jede Datei sieht
    # danach in git vollstaendig geaendert aus.
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht.oeffne(ziel)
    ansicht.reiter.currentWidget().setPlainText("s = 'grün'\n")
    assert ansicht.speichere_aktuellen() is True
    roh = ziel.read_bytes()
    assert b"\r\n" not in roh
    assert roh.decode("utf-8") == "s = 'grün'\n"
    assert not ansicht.reiter.tabText(0).startswith("●")


def test_nicht_utf8_wird_abgelehnt(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    kaputt = projekt / "latin.py"
    kaputt.write_bytes(b"s = '\xe4\xf6\xfc'\n")
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht.oeffne(kaputt)
    assert ansicht.reiter.count() == 0          # kein halb geladener Reiter
    assert gemeldet and "UTF-8" in gemeldet[0]


def test_fremde_aenderung_wird_erkannt(qapp, tmp_path):
    # Folgt direkt daraus, dass VS Code eine Option bleibt: beide Editoren
    # haben regelmaessig dieselbe Datei offen.
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht.oeffne(ziel)
    eintrag = ansicht.aktueller_reiter()
    ziel.write_text("von VS Code geschrieben\n", encoding="utf-8")
    assert ansicht.fremd_geaendert(eintrag) is True


def test_abbrechen_bei_fremder_aenderung_schreibt_nicht(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht.oeffne(ziel)
    ansicht.reiter.currentWidget().setPlainText("meins\n")
    ziel.write_text("fremd\n", encoding="utf-8")
    ansicht.frage_bei_konflikt = lambda pfad: "abbrechen"
    assert ansicht.speichere_aktuellen() is False
    assert ziel.read_text(encoding="utf-8") == "fremd\n"


def test_neu_laden_bei_fremder_aenderung(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht.oeffne(ziel)
    ansicht.reiter.currentWidget().setPlainText("meins\n")
    ziel.write_text("fremd\n", encoding="utf-8")
    ansicht.frage_bei_konflikt = lambda pfad: "neu_laden"
    assert ansicht.speichere_aktuellen() is False
    assert ansicht.reiter.currentWidget().toPlainText() == "fremd\n"


def test_ueberschreiben_bei_fremder_aenderung(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht.oeffne(ziel)
    ansicht.reiter.currentWidget().setPlainText("meins\n")
    ziel.write_text("fremd\n", encoding="utf-8")
    ansicht.frage_bei_konflikt = lambda pfad: "ueberschreiben"
    assert ansicht.speichere_aktuellen() is True
    assert ziel.read_text(encoding="utf-8") == "meins\n"


def test_projektwahl_listet_die_projekte(qapp, tmp_path):
    ordner, _ = _werkstatt(tmp_path)
    (ordner / "zweites" / "runs").mkdir(parents=True)
    ansicht = EditorView(DUNKEL)
    ansicht.setze_arbeitsordner(ordner)
    eintraege = {ansicht.projektwahl.itemText(i) for i in range(ansicht.projektwahl.count())}
    assert {"demo", "zweites"} <= eintraege


def test_syntaxfehler_erscheint_nach_der_ruhepause(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.reiter.currentWidget().setPlainText("def f()\n    return 1\n")
    QTest.qWait(400)
    assert "Doppelpunkt" in ansicht.reiter.currentWidget().toolTip()


# ----------------------------------------------------------------- Ausgabe


def test_ausgabe_macht_eigene_zeilen_anklickbar(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ansicht.zeige_ausgabe("Traceback (most recent call last):")
    ansicht.zeige_ausgabe(f'  File "{ziel}", line 1, in <module>')
    assert len(ansicht.ausgabe.stellen()) == 1
    von, bis, pfad, zeile = ansicht.ausgabe.stellen()[0]
    assert pfad == ziel.resolve() and zeile == 1
    assert ansicht.ausgabe.toPlainText()[von:bis].startswith('File "')


def test_ausgabe_laesst_fremde_zeilen_in_ruhe(qapp, tmp_path):
    ansicht, ordner, _projekt = _ansicht(tmp_path)
    fremd = ordner.parent / "fremd.py"
    fremd.write_text("x = 1\n", encoding="utf-8")
    ansicht.zeige_ausgabe(f'  File "{fremd}", line 3, in send')
    assert ansicht.ausgabe.stellen() == []


def test_klick_auf_eine_stelle_oeffnet_die_datei(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ziel = projekt / "hallo_spot.py"
    ziel.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    ansicht.zeige_ausgabe(f'  File "{ziel}", line 3, in <module>')
    _von, _bis, pfad, zeile = ansicht.ausgabe.stellen()[0]
    ansicht.springe_zu(pfad, zeile)
    assert ansicht.reiter.count() == 1
    assert ansicht.reiter.currentWidget().textCursor().blockNumber() == 2


# ----------------------------------------------------------------- Starten


def test_starten_startet_wirklich_einen_prozess(qapp, tmp_path):
    """Attrappen pruefen nur, dass die richtigen Argumente gebaut werden — nicht,
    dass das Betriebssystem damit etwas anfangen kann. Genau daran ging
    „In VS Code öffnen" durch die ganze Suite."""
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    skript = projekt / "hallo_spot.py"
    skript.write_text("raise ValueError('kaputt')\n", encoding="utf-8")
    ansicht.oeffne(skript)
    ansicht.setze_backend("dryrun")

    gestartet = []
    ansicht.lauf_gestartet.connect(lambda p, s: gestartet.append((p, s)))
    ansicht.start_knopf.click()
    assert gestartet, "kein Prozess gestartet"

    prozess, _pfad = gestartet[0]
    for zeile in prozess.stdout:
        ansicht.zeige_ausgabe(zeile.rstrip("\n"))
    prozess.wait(timeout=TEST_TIMEOUT_S)

    # Ein echter Python-Traceback, echt erzeugt, echt zerlegt.
    assert "ValueError" in ansicht.ausgabe.toPlainText()
    assert [p for _v, _b, p, _z in ansicht.ausgabe.stellen()] == [skript.resolve()]


def test_starten_speichert_vorher(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    skript = projekt / "hallo_spot.py"
    ansicht.oeffne(skript)
    ansicht.reiter.currentWidget().setPlainText("print('neu')\n")
    ansicht.setze_backend("dryrun")
    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    assert skript.read_text(encoding="utf-8") == "print('neu')\n"
    for prozess in prozesse:
        prozess.wait(timeout=TEST_TIMEOUT_S)


def test_knopf_wird_zu_stopp_und_meldet_den_wunsch(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.setze_backend("dryrun")
    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    assert "Stopp" in ansicht.start_knopf.text()

    gewuenscht = []
    ansicht.stopp_gewuenscht.connect(lambda: gewuenscht.append(True))
    ansicht.start_knopf.click()
    assert gewuenscht == [True]

    ansicht.lauf_beendet()
    assert "Starten" in ansicht.start_knopf.text()
    for prozess in prozesse:
        prozess.wait(timeout=TEST_TIMEOUT_S)


def test_starten_ohne_offene_datei_meldet_es(qapp, tmp_path):
    ansicht, _ordner, _projekt = _ansicht(tmp_path)
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht.start_knopf.click()
    assert gemeldet and "Datei" in gemeldet[0]


def test_reiter_schliessen_beendet_den_jedi_arbeiter(qapp, tmp_path):
    """S1.10: erst den Arbeiter beenden, dann das Feld zerstoeren.

    Umgekehrt wird ein arbeitender QThread destruiert -- das reisst das ganze
    Fenster mit, samt NOT-AUS-Knopf, und ein laufendes Roboterprogramm im
    Kindprozess bleibt fuehrerlos zurueck.
    """
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    feld = ansicht.reiter.currentWidget()
    hilfe = ansicht._reiter[feld].hilfe

    # Mitschreiben, NICHT ersetzen: ein Lambda an dieser Stelle haette den
    # echten Schutz abgeschaltet und genau den Zustand hinterlassen, den der
    # Test verhindern soll -- ein lebender QThread unter einem zerstoerten
    # Widget. Das hat in der vollen Suite prompt Python zum Absturz gebracht.
    echt = hilfe.schliesse
    geschlossen = []

    def spion():
        geschlossen.append(True)
        echt()

    hilfe.schliesse = spion
    ansicht._schliesse(ansicht.reiter.currentIndex())
    assert geschlossen == [True]

    # Die aufgeschobene Zerstoerung HIER abarbeiten. Sonst liegt sie in der
    # Warteschlange, bis irgendein spaeterer Test eine verschachtelte
    # Ereignisschleife laufen laesst -- und stuerzt dort ab, weit weg von der
    # Ursache. Genau das ist beim Bauen passiert: der Absturz zeigte auf
    # test_gui_tree.py, ausgeloest hat ihn diese Zeile.
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


# ============================= S2.2 alle verschmutzten Reiter vor dem Start
#
# Gespeichert wurde nur der AKTUELLE Reiter. Ein Mehrdatei-Projekt lief damit
# mit der alten Fassung der importierten Dateien -- der Schueler sucht den
# Fehler im Code, den er gerade geaendert hat, und der ist gar nicht drin.


def test_starten_speichert_alle_geaenderten_dateien(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    hilfsdatei = projekt / "hilfe.py"
    hilfsdatei.write_text("def f():\n    return 1\n", encoding="utf-8")

    ansicht.oeffne(hilfsdatei)
    ansicht.reiter.currentWidget().setPlainText("def f():\n    return 2\n")
    ansicht.reiter.currentWidget().document().setModified(True)
    ansicht._verschmutzt(ansicht.reiter.currentWidget(), True)

    ansicht.oeffne(projekt / "hallo_spot.py")          # anderer Reiter ist aktiv
    assert ansicht.speichere_alle_geaenderten() is True
    assert hilfsdatei.read_text(encoding="utf-8") == "def f():\n    return 2\n"


def test_speichere_alle_meldet_fehlschlag(qapp, tmp_path):
    """Ein Konflikt in irgendeiner Datei muss den Start verhindern."""
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.reiter.currentWidget().setPlainText("meins\n")
    ansicht._verschmutzt(ansicht.reiter.currentWidget(), True)
    (projekt / "hallo_spot.py").write_text("fremd\n", encoding="utf-8")
    ansicht.frage_bei_konflikt = lambda pfad: "abbrechen"
    assert ansicht.speichere_alle_geaenderten() is False


def test_ohne_aenderungen_ist_speichere_alle_erfolgreich(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    assert ansicht.speichere_alle_geaenderten() is True


def test_offene_aenderungen_werden_gemeldet(qapp, tmp_path):
    """S2.1: das Hauptfenster fragt damit vor dem Schliessen."""
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    assert ansicht.ungespeicherte() == []
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht._verschmutzt(ansicht.reiter.currentWidget(), True)
    assert [p.name for p in ansicht.ungespeicherte()] == ["hallo_spot.py"]


def test_der_stopp_knopf_faellt_zurueck_wenn_der_lauf_nie_beginnt(qapp, tmp_path):
    """S2.12: startet ein Skript und stirbt sofort -- ein Syntaxfehler reicht --,
    legt es nie ein Lauf-Verzeichnis an. Der Watcher meldet also nie ein Ende,
    und der Knopf blieb fuer immer auf `Stopp`. Der Schueler kann danach nichts
    mehr starten."""
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht._setze_laeuft(True)
    assert ansicht.start_knopf.text().startswith("■")
    ansicht.lauf_beendet()
    assert ansicht.start_knopf.text().startswith("▶")


def test_ein_sofort_gestorbener_prozess_gibt_den_knopf_frei(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    kaputt = projekt / "kaputt.py"
    kaputt.write_text("def f(\n", encoding="utf-8")     # Syntaxfehler
    ansicht.oeffne(kaputt)
    ansicht.setze_backend("dryrun")
    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    for prozess in prozesse:
        prozess.wait(timeout=TEST_TIMEOUT_S)
    QTest.qWait(200)
    ansicht.pruefe_lauf_lebt()
    assert ansicht.start_knopf.text().startswith("▶"), "Knopf haengt auf Stopp fest"


def _arbeite_zerstoerungen_ab():
    """CLAUDE.md: wer deleteLater() ausloest, arbeitet es auch ab.

    Sonst liegt die Zerstoerung in der Warteschlange, bis ein spaeterer Test
    eine verschachtelte Ereignisschleife laufen laesst -- und stuerzt DORT ab.
    Genau so ist schon einmal ein "Fatal Python error: Aborted" in
    test_gui_tree.py entstanden, ausgeloest von hier.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_geloeschte_datei_schliesst_ihren_reiter(qapp, tmp_path):
    """Sonst zeigt ein Reiter auf eine verschwundene Datei -- und das naechste
    Speichern legte sie wortlos wieder an."""
    from spotlab.gui.editor.view import EditorView
    from spotlab.gui.theme import DUNKEL

    projekt = tmp_path / "demo"
    projekt.mkdir()
    datei = projekt / "weg.py"
    datei.write_text("x = 1\n", encoding="utf-8")

    ansicht = EditorView(DUNKEL)
    ansicht.setze_projekt(projekt)
    ansicht.oeffne(datei)
    assert ansicht.reiter.count() == 1

    ansicht.schliesse_pfad(datei)
    assert ansicht.reiter.count() == 0
    _arbeite_zerstoerungen_ab()


def test_unbekannter_pfad_schliesst_nichts(qapp, tmp_path):
    from spotlab.gui.editor.view import EditorView
    from spotlab.gui.theme import DUNKEL

    projekt = tmp_path / "demo"
    projekt.mkdir()
    datei = projekt / "bleibt.py"
    datei.write_text("x = 1\n", encoding="utf-8")

    ansicht = EditorView(DUNKEL)
    ansicht.setze_projekt(projekt)
    ansicht.oeffne(datei)
    ansicht.schliesse_pfad(projekt / "andere.py")
    assert ansicht.reiter.count() == 1
    _arbeite_zerstoerungen_ab()


def test_starte_aktuelles_ohne_offene_datei_meldet_klartext(qapp, tmp_path):
    """Der Uebungsraum delegiert hierher -- schweigen waere dort ein toter Knopf."""
    from spotlab.gui.editor.view import EditorView
    from spotlab.gui.theme import DUNKEL

    projekt = tmp_path / "demo"
    projekt.mkdir()
    ansicht = EditorView(DUNKEL)
    ansicht.setze_projekt(projekt)
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)

    ansicht.starte_aktuelles()
    assert gemeldet and "ffne zuerst" in gemeldet[0]


def test_starte_aktuelles_startet_die_offene_datei(qapp, tmp_path, monkeypatch):
    from spotlab.gui.editor import view as modul
    from spotlab.gui.editor.view import EditorView
    from spotlab.gui.theme import DUNKEL

    gestartet = []

    class _Prozess:
        stdout = None

        def poll(self):
            return None

    monkeypatch.setattr(modul, "start_script",
                        lambda pfad, **kw: gestartet.append(pfad) or _Prozess())

    projekt = tmp_path / "demo"
    projekt.mkdir()
    datei = projekt / "lauf.py"
    datei.write_text("x = 1\n", encoding="utf-8")

    ansicht = EditorView(DUNKEL)
    ansicht.setze_projekt(projekt)
    ansicht.oeffne(datei)
    ansicht.starte_aktuelles()
    assert gestartet == [datei]
    _arbeite_zerstoerungen_ab()


# ------------------------------------------------------- Wo laeuft es?


def _abgefangener_start(ansicht, monkeypatch):
    """start_script durch eine Attrappe ersetzen und die Argumente einsammeln."""
    gesehen = {}

    class Attrappe:
        stdout = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def falscher_start(pfad, **kw):
        gesehen.update(kw)
        return Attrappe()

    monkeypatch.setattr("spotlab.gui.editor.view.start_script", falscher_start)
    return gesehen


def test_die_wahl_uebungsraum_startet_das_sim_backend(qapp, tmp_path, monkeypatch):
    """Der Trockenlauf HAT keine Position -- er kann im Raum gar nichts zeigen.
    Genau daran scheiterte der erste Versuch: `backend: dryrun`, Pose blieb
    (0, 0, 0)."""
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    gesehen = _abgefangener_start(ansicht, monkeypatch)

    ansicht.setze_backend("sim")
    ansicht.start_knopf.click()

    assert gesehen["backend"] == "sim"


def test_der_uebungsraum_kann_den_echten_spot_nicht_erreichen(qapp, tmp_path, monkeypatch):
    """`connect(backend="real")` im Skript schlaegt die Umgebungsvariable.
    Ohne die Obergrenze faehre ein virtueller Lauf den Roboter."""
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    gesehen = _abgefangener_start(ansicht, monkeypatch)

    ansicht.setze_backend("sim")
    ansicht.start_knopf.click()

    assert gesehen["nur_trocken"] is True


def test_echter_spot_bekommt_keine_obergrenze(qapp, tmp_path, monkeypatch):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    gesehen = _abgefangener_start(ansicht, monkeypatch)

    ansicht.setze_backend("real")
    ansicht.start_knopf.click()

    assert gesehen["backend"] == "real"
    assert gesehen["nur_trocken"] is False


def test_das_gewaehlte_backend_ist_abfragbar(qapp, tmp_path):
    ansicht, _ordner, _projekt = _ansicht(tmp_path)
    ansicht.setze_backend("sim")
    assert ansicht.gewaehltes_backend() == "sim"
    ansicht.setze_backend("dryrun")
    assert ansicht.gewaehltes_backend() == "dryrun"


def test_ein_unbekanntes_backend_aendert_die_wahl_nicht(qapp, tmp_path):
    """load_config() darf die GUI nicht in einen Zustand bringen, den die
    Auswahl gar nicht kennt."""
    ansicht, _ordner, _projekt = _ansicht(tmp_path)
    ansicht.setze_backend("sim")
    ansicht.setze_backend("quatsch")
    assert ansicht.gewaehltes_backend() == "sim"


def test_der_laufzustand_wird_gemeldet(qapp, tmp_path):
    """Damit der Uebungsraum-Knopf mitwandert, statt auf Start stehenzubleiben."""
    ansicht, _ordner, _projekt = _ansicht(tmp_path)
    gemeldet = []
    ansicht.laeuft_geaendert.connect(gemeldet.append)
    ansicht._setze_laeuft(True)
    ansicht.lauf_beendet()
    assert gemeldet == [True, False]


def test_die_wahl_erreicht_wirklich_einen_kindprozess(qapp, tmp_path):
    """CLAUDE.md: wo ein externer Prozess im Spiel ist, startet mindestens ein
    Test ihn wirklich. Die Attrappe oben prueft nur, dass das Argument gebaut
    wird -- nicht, dass `connect()` im Kind es auch sieht."""
    import json

    ansicht, _ordner, projekt = _ansicht(tmp_path)
    skript = projekt / "virtuell.py"
    skript.write_text(
        "import spotlab\n"
        "with spotlab.connect() as spot:\n"
        "    spot.power_on()\n"
        "    spot.move(forward=0.3)\n",
        encoding="utf-8",
    )
    ansicht.oeffne(skript)
    ansicht.setze_backend("sim")

    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    assert prozesse, "kein Prozess gestartet"
    ausgabe = prozesse[0].stdout.read()
    assert prozesse[0].wait(timeout=TEST_TIMEOUT_S) == 0, ausgabe

    laeufe = sorted((projekt / "runs").glob("*/lauf.json"))
    assert laeufe, f"kein Lauf angelegt. Ausgabe:\n{ausgabe}"
    lauf = json.loads(laeufe[-1].read_text(encoding="utf-8"))
    assert lauf["backend"] == "sim", "der Trockenlauf hat keine Position"


def test_die_zusatzumgebung_geht_an_den_start(qapp, tmp_path, monkeypatch):
    """Der Editor kennt keine Raeume -- das Hauptfenster haengt hier ein, was
    in der Ansicht „Übungsraum" gewaehlt ist."""
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    gesehen = _abgefangener_start(ansicht, monkeypatch)

    ansicht.zusatz_umgebung = lambda: {"SPOTLAB_RAUM": "moebliert"}
    ansicht.setze_backend("sim")
    ansicht.start_knopf.click()

    assert gesehen["umgebung"] == {"SPOTLAB_RAUM": "moebliert"}


def test_raum_und_startpose_erreichen_wirklich_den_sim(qapp, tmp_path):
    """Die ganze Kette in einem echten Kindprozess: GUI -> Umgebung ->
    connect() -> SimBackend. Genau hier riss sie am 04.09.2026 -- der Lauf
    hatte `"raum": null` und startete bei (0, 0)."""
    import json

    ansicht, _ordner, projekt = _ansicht(tmp_path)
    skript = projekt / "im_raum.py"
    skript.write_text(
        "import spotlab\n"
        "with spotlab.connect() as spot:\n"
        "    spot.power_on()\n"
        "    spot.stand()\n",
        encoding="utf-8",
    )
    ansicht.oeffne(skript)
    ansicht.setze_backend("sim")
    ansicht.zusatz_umgebung = lambda: {
        "SPOTLAB_RAUM": "durchgang", "SPOTLAB_RAUM_START": "2.00,3.00,90.0",
    }

    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    ausgabe = prozesse[0].stdout.read()
    assert prozesse[0].wait(timeout=TEST_TIMEOUT_S) == 0, ausgabe

    lauf = sorted((projekt / "runs").glob("*"))[-1]
    verbunden = json.loads((lauf / "ereignisse.jsonl").read_text(encoding="utf-8")
                           .splitlines()[0])
    assert verbunden["daten"]["raum"] == "durchgang"

    erste = json.loads((lauf / "zustand.jsonl").read_text(encoding="utf-8")
                       .splitlines()[0])
    assert erste["daten"]["pose"][:2] == [2.0, 3.0]


# ------------------------------------------------------- Uebungsraum 3D


def test_mujoco_steht_nur_zur_wahl_wenn_spotsim_da_ist(monkeypatch):
    """Ein Eintrag, der beim Start mit ModuleNotFoundError stirbt, ist keine
    Wahl. Geprueft per find_spec -- die GUI importiert kein MuJoCo."""
    from spotlab.gui.editor import view as modul

    monkeypatch.setattr(modul.importlib.util, "find_spec", lambda name: None)
    assert "mujoco" not in [n for _, n in modul.verfuegbare_backends()]
    assert "sim" in [n for _, n in modul.verfuegbare_backends()]

    monkeypatch.setattr(modul.importlib.util, "find_spec", lambda name: object())
    assert "mujoco" in [n for _, n in modul.verfuegbare_backends()]


def test_die_auswahl_zeigt_die_verfuegbaren_backends(qapp, tmp_path, monkeypatch):
    from spotlab.gui.editor import view as modul

    monkeypatch.setattr(modul.importlib.util, "find_spec", lambda name: object())
    ansicht, _ordner, _projekt = _ansicht(tmp_path)
    namen = [ansicht.backendwahl.itemData(i) for i in range(ansicht.backendwahl.count())]
    assert namen == ["real", "dryrun", "sim", "mujoco"]


def test_die_umgebung_darf_den_start_verweigern(qapp, tmp_path, monkeypatch):
    """Das Hauptfenster haengt hier den Raum ein -- und lehnt ab, wenn der
    Raum nicht auf der Platte liegt. Dann darf kein Prozess starten, und der
    Grund muss in der Meldung stehen."""
    from spotlab.errors import SpotlabError

    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    gesehen = _abgefangener_start(ansicht, monkeypatch)
    meldungen = []
    ansicht.meldung.connect(meldungen.append)

    def verweigert():
        raise SpotlabError("Nicht gestartet: der Raum ist nicht gespeichert.")

    ansicht.zusatz_umgebung = verweigert
    ansicht.setze_backend("sim")
    ansicht.start_knopf.click()

    assert gesehen == {} and not ansicht.laeuft()
    assert meldungen[-1].startswith("Nicht gestartet")
