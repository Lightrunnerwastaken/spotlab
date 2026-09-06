"""Rekonstruieren im Tab: Arbeiter, Dialog, Pauspapier neben der Raumdatei."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("bosdyn.api")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from spotlab.gui.raumeditor import RaumeditorView  # noqa: E402
from spotlab.gui.raumeditor.rekonstruktion_dialog import (  # noqa: E402
    RekonstruktionsArbeiter,
    RekonstruktionsDialog,
)
from spotlab.gui.theme import DUNKEL  # noqa: E402
from spotlab.maps.rekonstruktion import Einstellungen, Ergebnis  # noqa: E402
from spotlab.welt import pauspapier  # noqa: E402
from spotlab.welt.raum import raum_laden, raum_pfad  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from test_maps_rekonstruktion import synthetische_karte  # noqa: E402

from tests_zeitgrenzen import TEST_TIMEOUT_S  # noqa: E402


def _warte_auf(signal, qapp):
    """Bis das Signal kommt, hoechstens TEST_TIMEOUT_S -- mit Zeitgrenze, nie haengend."""
    schleife = QEventLoop()
    ergebnis = []
    signal.connect(lambda *a: (ergebnis.append(a), schleife.quit()))
    QTimer.singleShot(int(TEST_TIMEOUT_S * 1000), schleife.quit)
    schleife.exec()
    return ergebnis


def test_der_arbeiter_liefert_ein_ergebnis(qapp, tmp_path):
    karte = synthetische_karte(tmp_path / "gang")
    arbeiter = RekonstruktionsArbeiter(karte, Einstellungen())
    fortschritte = []
    arbeiter.fortschritt.connect(fortschritte.append)
    arbeiter.start()
    gekommen = _warte_auf(arbeiter.fertig, qapp)
    arbeiter.wait(int(TEST_TIMEOUT_S * 1000))
    assert gekommen and isinstance(gekommen[0][0], Ergebnis)
    assert gekommen[0][0].bericht["wegpunkte"] == 6
    assert any("Schnappschuss" in f for f in fortschritte)


def test_der_arbeiter_meldet_einen_kaputten_ordner_als_fehler(qapp, tmp_path):
    arbeiter = RekonstruktionsArbeiter(tmp_path / "kein_ordner", Einstellungen())
    arbeiter.start()
    gekommen = _warte_auf(arbeiter.fehler, qapp)
    arbeiter.wait(int(TEST_TIMEOUT_S * 1000))
    assert gekommen and "graph" in gekommen[0][0]


def test_der_dialog_uebernimmt_das_ergebnis_in_den_tab(qapp, tmp_path):
    karte = synthetische_karte(tmp_path / "gang")
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    dialog = RekonstruktionsDialog(ansicht, tmp_path)
    dialog.ordner_feld.setText(str(karte))
    dialog.vorschau()
    gekommen = _warte_auf(dialog.ergebnis_da, qapp)
    assert gekommen and dialog.ergebnis is not None
    assert "Wände" in dialog.bericht.toPlainText() or "waende" in dialog.bericht.toPlainText()
    assert "Treppen: 0" in dialog.bericht.toPlainText() and "Treppen" in dialog.status.text()
    ansicht.uebernimm_rekonstruktion(dialog.ergebnis)
    assert ansicht.raumname() == "" and ansicht.steuerung.geaendert
    assert len(ansicht.raum().waende) >= 3
    assert len(ansicht.sicht._pauspapier) > 1000 and len(ansicht.sicht3d._pauspapier) > 1000


def test_speichern_legt_das_pauspapier_neben_die_raumdatei(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from spotlab.maps.rekonstruktion import rekonstruiere

    karte = synthetische_karte(tmp_path / "gang")
    ansicht = RaumeditorView(DUNKEL)
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht.uebernimm_rekonstruktion(rekonstruiere(karte))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("gang", True))
    assert ansicht.speichern()
    pfad = raum_pfad(tmp_path, "gang")
    assert pfad.is_file() and pauspapier.pfad_zu(pfad).is_file()
    assert len(pauspapier.lies(pauspapier.pfad_zu(pfad))) > 1000
    # Neu laden: der Raum kommt mit seinem Pauspapier zurueck.
    andere = RaumeditorView(DUNKEL)
    andere.setze_arbeitsordner(tmp_path)
    andere.waehle_raum("gang")
    assert andere.raum() == raum_laden("gang", workspace=tmp_path)
    assert len(andere.sicht._pauspapier) > 1000
