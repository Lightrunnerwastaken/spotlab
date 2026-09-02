import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from spotlab.gui.editor.tree import Dateibaum  # noqa: E402


def _warte_aufs_laden(baum, sekunden=5.0):
    """QFileSystemModel laedt Verzeichnisse in einem eigenen Thread."""
    schleife = QEventLoop()
    baum.modell.directoryLoaded.connect(lambda _pfad: schleife.quit())
    QTimer.singleShot(int(sekunden * 1000), schleife.quit)
    schleife.exec()


def _projekt(tmp_path):
    projekt = tmp_path / "demo"
    lauf = projekt / "runs" / "20260807T101010Z"
    lauf.mkdir(parents=True)
    (lauf / "zustand.jsonl").write_text("{}\n", encoding="utf-8")
    (projekt / "hallo_spot.py").write_text("x = 1\n", encoding="utf-8")
    (projekt / "notiz.md").write_text("# Notiz\n", encoding="utf-8")
    (projekt / "bild.png").write_bytes(b"\x89PNG")
    return projekt


def _sichtbare_namen(baum):
    proxy = baum.ansicht.model()
    wurzel = baum.ansicht.rootIndex()
    return {proxy.data(proxy.index(z, 0, wurzel)) for z in range(proxy.rowCount(wurzel))}


def test_zeigt_python_und_text_dateien(qapp, tmp_path):
    baum = Dateibaum()
    baum.setze_projekt(_projekt(tmp_path))
    _warte_aufs_laden(baum)
    namen = _sichtbare_namen(baum)
    assert "hallo_spot.py" in namen
    assert "notiz.md" in namen


def test_runs_wird_ausgeblendet(qapp, tmp_path):
    # Sonst horcht QFileSystemModel auf zustand.jsonl, in die der Sampler mit
    # 10 Hz schreibt — Aenderungssignale im Zehntelsekundentakt.
    baum = Dateibaum()
    baum.setze_projekt(_projekt(tmp_path))
    _warte_aufs_laden(baum)
    assert "runs" not in _sichtbare_namen(baum)


def test_bilder_werden_nicht_gezeigt(qapp, tmp_path):
    baum = Dateibaum()
    baum.setze_projekt(_projekt(tmp_path))
    _warte_aufs_laden(baum)
    assert "bild.png" not in _sichtbare_namen(baum)


def test_ohne_projekt_bleibt_der_baum_leer(qapp):
    baum = Dateibaum()
    baum.setze_projekt(None)
    assert not baum.ansicht.rootIndex().isValid()


def test_doppelklick_meldet_die_datei(qapp, tmp_path):
    projekt = _projekt(tmp_path)
    baum = Dateibaum()
    baum.setze_projekt(projekt)
    _warte_aufs_laden(baum)
    gewaehlt = []
    baum.datei_gewaehlt.connect(gewaehlt.append)
    proxy = baum.ansicht.model()
    wurzel = baum.ansicht.rootIndex()
    for zeile in range(proxy.rowCount(wurzel)):
        index = proxy.index(zeile, 0, wurzel)
        if proxy.data(index) == "hallo_spot.py":
            baum.ansicht.doubleClicked.emit(index)
    assert gewaehlt == [projekt / "hallo_spot.py"]


# ----------------------------------------------------- Dateien verwalten
#
# Bis zum 02.09.2026 konnte der Baum nur ANZEIGEN. Wer eine Datei anlegen
# wollte, musste die Oberflaeche verlassen -- in einer Unterrichtsoberflaeche
# der haeufigste Handgriff ueberhaupt.


def test_neue_datei_landet_im_angeklickten_ordner(qapp, tmp_path):
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    (projekt / "unterordner").mkdir(parents=True)
    baum.setze_projekt(projekt)

    baum.neue_datei(projekt / "unterordner", "programm.py")
    assert (projekt / "unterordner" / "programm.py").is_file()


def test_neue_datei_bei_einer_datei_landet_daneben(qapp, tmp_path):
    """Rechtsklick auf eine Datei meint ihren Ordner, nicht sie selbst."""
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    (projekt / "vorhanden.py").write_text("x = 1\n", encoding="utf-8")
    baum.setze_projekt(projekt)

    assert baum.zielordner(projekt / "vorhanden.py") == projekt


def test_zielordner_ohne_auswahl_ist_die_projektwurzel(qapp, tmp_path):
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    baum.setze_projekt(projekt)
    assert baum.zielordner(None) == projekt


def test_neue_datei_wird_sofort_geoeffnet(qapp, tmp_path):
    """Sonst sucht man die Datei, die man gerade angelegt hat."""
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    baum.setze_projekt(projekt)
    gemeldet = []
    baum.datei_gewaehlt.connect(gemeldet.append)

    baum.neue_datei(projekt, "frisch.py")
    assert gemeldet == [projekt / "frisch.py"]


def test_name_mit_pfadtrenner_wird_abgewiesen(qapp, tmp_path):
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    baum.setze_projekt(projekt)
    gemeldet = []
    baum.meldung.connect(gemeldet.append)

    assert baum.neue_datei(projekt, "../draussen.py") is None
    assert not (tmp_path / "draussen.py").exists()
    assert gemeldet


def test_vorhandene_datei_wird_nicht_ueberschrieben(qapp, tmp_path):
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    (projekt / "da.py").write_text("wichtig\n", encoding="utf-8")
    baum.setze_projekt(projekt)
    gemeldet = []
    baum.meldung.connect(gemeldet.append)

    assert baum.neue_datei(projekt, "da.py") is None
    assert (projekt / "da.py").read_text(encoding="utf-8") == "wichtig\n"
    assert gemeldet


def test_unsichtbare_endung_wird_erklaert(qapp, tmp_path):
    """Der Baum zeigt nur py/md/txt/json. Eine angelegte .csv verschwaende
    sofort wieder, und der Schueler suchte eine Datei, die es gibt."""
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    baum.setze_projekt(projekt)
    gemeldet = []
    baum.meldung.connect(gemeldet.append)

    assert baum.neue_datei(projekt, "daten.csv") is None
    assert gemeldet and ".py" in gemeldet[0]


def test_neuer_ordner_wird_angelegt(qapp, tmp_path):
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    baum.setze_projekt(projekt)

    baum.neuer_ordner(projekt, "bilder")
    assert (projekt / "bilder").is_dir()


def test_umbenennen_behaelt_den_inhalt(qapp, tmp_path):
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    (projekt / "alt.py").write_text("inhalt\n", encoding="utf-8")
    baum.setze_projekt(projekt)

    baum.umbenennen(projekt / "alt.py", "neu.py")
    assert not (projekt / "alt.py").exists()
    assert (projekt / "neu.py").read_text(encoding="utf-8") == "inhalt\n"


def test_umbenennen_auf_vorhandenen_namen_wird_abgewiesen(qapp, tmp_path):
    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    (projekt / "a.py").write_text("a\n", encoding="utf-8")
    (projekt / "b.py").write_text("b\n", encoding="utf-8")
    baum.setze_projekt(projekt)
    gemeldet = []
    baum.meldung.connect(gemeldet.append)

    assert baum.umbenennen(projekt / "a.py", "b.py") is None
    assert (projekt / "b.py").read_text(encoding="utf-8") == "b\n"
    assert gemeldet


def test_loeschen_geht_in_den_papierkorb_nicht_endgueltig(qapp, tmp_path, monkeypatch):
    """Ein Schueler, der aus Versehen loescht, soll es zurueckholen koennen.
    Deshalb send2trash und NICHT Path.unlink."""
    from spotlab.gui.editor import tree as modul

    gekippt = []
    monkeypatch.setattr(modul, "in_den_papierkorb", lambda p: gekippt.append(p))

    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    datei = projekt / "weg.py"
    datei.write_text("x\n", encoding="utf-8")
    baum.setze_projekt(projekt)

    baum.loeschen(datei)
    assert gekippt == [datei]
    assert datei.exists(), "die Attrappe loescht nicht -- echt geloescht waere falsch"


def test_loeschen_meldet_die_datei_damit_der_reiter_zugeht(qapp, tmp_path, monkeypatch):
    """Sonst zeigt ein offener Reiter auf eine verschwundene Datei, und das
    naechste Speichern legt sie wortlos wieder an."""
    from spotlab.gui.editor import tree as modul

    monkeypatch.setattr(modul, "in_den_papierkorb", lambda p: None)

    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    datei = projekt / "weg.py"
    datei.write_text("x\n", encoding="utf-8")
    baum.setze_projekt(projekt)
    entfernt = []
    baum.datei_entfernt.connect(entfernt.append)

    baum.loeschen(datei)
    assert entfernt == [datei]


def test_ohne_send2trash_gibt_es_keinen_loeschen_eintrag(qapp, tmp_path, monkeypatch):
    """Wie bei jedi: fehlt das Paket, kann die Oberflaeche eben weniger --
    aber sie scheitert nicht."""
    from spotlab.gui.editor import tree as modul

    monkeypatch.setattr(modul, "in_den_papierkorb", None)

    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    baum.setze_projekt(projekt)
    menue = baum.baue_menue(projekt / "irgendwas.py")
    beschriftungen = [a.text() for a in menue.actions()]
    assert not any("öschen" in t for t in beschriftungen)


def test_menue_bietet_die_vier_eintraege(qapp, tmp_path, monkeypatch):
    from spotlab.gui.editor import tree as modul

    monkeypatch.setattr(modul, "in_den_papierkorb", lambda p: None)

    baum = Dateibaum()
    projekt = tmp_path / "demo"
    projekt.mkdir()
    baum.setze_projekt(projekt)
    beschriftungen = [a.text() for a in baum.baue_menue(projekt / "x.py").actions()]
    assert any("Neue Datei" in t for t in beschriftungen)
    assert any("Neuer Ordner" in t for t in beschriftungen)
    assert any("Umbenennen" in t for t in beschriftungen)
    assert any("öschen" in t for t in beschriftungen)
