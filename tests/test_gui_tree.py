import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEventLoop, QTimer                 # noqa: E402

from spotlab.gui.editor.tree import Dateibaum                 # noqa: E402


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
