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
    ansicht.trockenlauf.setChecked(True)

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
    ansicht.trockenlauf.setChecked(True)
    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    assert skript.read_text(encoding="utf-8") == "print('neu')\n"
    for prozess in prozesse:
        prozess.wait(timeout=TEST_TIMEOUT_S)


def test_knopf_wird_zu_stopp_und_meldet_den_wunsch(qapp, tmp_path):
    ansicht, _ordner, projekt = _ansicht(tmp_path)
    ansicht.oeffne(projekt / "hallo_spot.py")
    ansicht.trockenlauf.setChecked(True)
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
    ansicht.trockenlauf.setChecked(True)
    prozesse = []
    ansicht.lauf_gestartet.connect(lambda p, s: prozesse.append(p))
    ansicht.start_knopf.click()
    for prozess in prozesse:
        prozess.wait(timeout=TEST_TIMEOUT_S)
    QTest.qWait(200)
    ansicht.pruefe_lauf_lebt()
    assert ansicht.start_knopf.text().startswith("▶"), "Knopf haengt auf Stopp fest"
