from spotlab.editor.traceback import finde_stellen


def _projekt(tmp_path):
    projekt = tmp_path / "werkstatt" / "demo"
    projekt.mkdir(parents=True)
    skript = projekt / "runde.py"
    skript.write_text("x = 1\n", encoding="utf-8")
    return tmp_path / "werkstatt", skript


def test_findet_die_eigene_datei(tmp_path):
    wurzel, skript = _projekt(tmp_path)
    text = f'  File "{skript}", line 6, in <module>'
    stellen = finde_stellen(text, wurzel)
    assert len(stellen) == 1
    assert stellen[0].pfad == skript.resolve()
    assert stellen[0].zeile == 6
    assert text[stellen[0].von : stellen[0].bis].startswith('File "')


def test_pfad_ausserhalb_der_werkstatt_bleibt_text(tmp_path):
    # Ein Traceback zeigt fast immer mehr fremde Rahmen als eigene. Waere
    # alles anklickbar, landete ein Schueler in bosdyn/client/... und aenderte es.
    wurzel, _ = _projekt(tmp_path)
    fremd = tmp_path / "site-packages"
    fremd.mkdir()
    bibliothek = fremd / "robot_command.py"
    bibliothek.write_text("y = 2\n", encoding="utf-8")
    text = f'  File "{bibliothek}", line 42, in send'
    assert finde_stellen(text, wurzel) == []


def test_platzhalter_werden_ausgelassen(tmp_path):
    wurzel, _ = _projekt(tmp_path)
    assert finde_stellen('  File "<string>", line 1, in <module>', wurzel) == []
    assert finde_stellen('  File "<stdin>", line 1, in <module>', wurzel) == []


def test_geloeschte_datei_wird_ausgelassen(tmp_path):
    wurzel, _ = _projekt(tmp_path)
    weg = wurzel / "demo" / "gibtsnicht.py"
    assert finde_stellen(f'  File "{weg}", line 3', wurzel) == []


def test_ganzer_traceback_liefert_nur_die_eigenen_zeilen(tmp_path):
    wurzel, skript = _projekt(tmp_path)
    fremd = tmp_path / "site-packages"
    fremd.mkdir()
    bibliothek = fremd / "robot_command.py"
    bibliothek.write_text("y = 2\n", encoding="utf-8")
    text = (
        "Traceback (most recent call last):\n"
        f'  File "{skript}", line 6, in <module>\n'
        "    spot.move(forward=1.0)\n"
        f'  File "{bibliothek}", line 42, in send\n'
        "ValueError: kaputt\n"
    )
    stellen = finde_stellen(text, wurzel)
    assert [s.pfad for s in stellen] == [skript.resolve()]
    assert text[stellen[0].von : stellen[0].bis] == f'File "{skript}", line 6'


def test_leerer_text_ergibt_leere_liste(tmp_path):
    assert finde_stellen("", tmp_path) == []
