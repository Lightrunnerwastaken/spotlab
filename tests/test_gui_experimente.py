"""Der Reiter „Experimente": ein Ort fuer alle Versuche, Gehzeit ist der erste.

Bis zum 16.09.2026 hatte die Gehzeit ihren eigenen Reiter. Jeder weitere
Versuch haette einen weiteren Reiter gebraucht -- und die Leiste ist schon voll.
Jetzt gibt es EINEN Reiter mit einer Auswahl; ein neues Experiment ist eine Zeile
in `EXPERIMENTE` plus seine eigene Ansicht, sonst nichts. Anlegen aus der
Oberflaeche heraus gibt es bewusst NICHT -- das bleibt Zukunft, und ein Test
haelt fest, dass es keinen solchen Knopf gibt.
"""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QAbstractButton  # noqa: E402

from spotlab.gui import sidebar  # noqa: E402
from spotlab.gui.views.experimente import EXPERIMENTE, ExperimenteView  # noqa: E402
from spotlab.gui.views.gehzeit import GehzeitView  # noqa: E402

# ------------------------------------------------------------------ Registry


def test_gehzeit_ist_das_erste_und_bisher_einzige_experiment():
    schluessel = [e.schluessel for e in EXPERIMENTE]
    assert schluessel == ["gehzeit"]
    [gehzeit] = EXPERIMENTE
    assert gehzeit.ansicht is GehzeitView
    assert "Gehzeit" in gehzeit.name


def test_jedes_experiment_traegt_schluessel_namen_und_ansicht():
    """Der Vertrag fuer jedes kuenftige Experiment -- drei Felder, mehr braucht die Auswahl nicht."""
    for e in EXPERIMENTE:
        assert e.schluessel and e.name and callable(e.ansicht)


# -------------------------------------------------------------- Die Ansicht


def test_die_auswahl_zeigt_die_experimente_und_gehzeit_ist_vorgewaehlt(qapp):
    ansicht = ExperimenteView()
    assert [ansicht.auswahl.itemData(i) for i in range(ansicht.auswahl.count())] == ["gehzeit"]
    assert ansicht.auswahl.currentData() == "gehzeit"
    assert isinstance(ansicht.aktuelles(), GehzeitView)
    assert ansicht.stapel.currentWidget() is ansicht.aktuelles()


def test_die_gehzeit_ansicht_ist_dieselbe_wie_bisher(qapp):
    """Nichts nachgebaut: die Gehzeit-Ansicht lebt unveraendert im Stapel."""
    ansicht = ExperimenteView()
    assert ansicht.experiment("gehzeit") is ansicht.aktuelles()
    assert isinstance(ansicht.experiment("gehzeit"), GehzeitView)


def test_die_meldung_kommt_durch(qapp):
    ansicht = ExperimenteView()
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht.experiment("gehzeit").meldung.emit("Hallo aus der Gehzeit")
    assert gemeldet == ["Hallo aus der Gehzeit"]


def test_der_arbeitsordner_erreicht_jedes_experiment(qapp, tmp_path):
    ansicht = ExperimenteView()
    bekommen = []
    ansicht.experiment("gehzeit").setze_arbeitsordner = bekommen.append
    ansicht.setze_arbeitsordner(tmp_path)
    assert bekommen == [tmp_path]


def test_ein_unbekanntes_experiment_ist_ein_fehler(qapp):
    with pytest.raises(KeyError):
        ExperimenteView().experiment("kaffeekochen")


def test_es_gibt_keinen_knopf_zum_anlegen(qapp):
    """Bewusst Zukunft: kein 'Neu', kein 'Anlegen', kein 'Erstellen' in diesem Reiter."""
    ansicht = ExperimenteView()
    knoepfe = [k.text().lower() for k in ansicht.findChildren(QAbstractButton)]
    verboten = ("neu", "anlegen", "erstellen", "hinzufügen", "hinzufuegen", "+")
    eigene = [t for t in knoepfe if any(v in t for v in verboten)]
    # Die Gehzeit-Ansicht selbst hat Knoepfe (Starten, Loeschen) -- die sind erlaubt;
    # geprueft wird nur der Rahmen des Reiters ausserhalb des Stapels.
    rahmen = [k.text().lower() for k in ansicht.findChildren(QAbstractButton)
              if not _liegt_im(k, ansicht.stapel)]
    assert not [t for t in rahmen if any(v in t for v in verboten)], (eigene, rahmen)


def _liegt_im(widget, behaelter):
    eltern = widget.parent()
    while eltern is not None:
        if eltern is behaelter:
            return True
        eltern = eltern.parent()
    return False


# ------------------------------------------------------- Leiste und Fenster


def test_die_leiste_kennt_experimente_und_kein_gehzeit_mehr():
    schluessel = [s for s, _ in sidebar.EINTRAEGE]
    assert "experimente" in schluessel
    assert "gehzeit" not in schluessel
    assert schluessel.index("experimente") == schluessel.index("umwelt") + 1, "an der alten Stelle"


def test_das_fenster_hat_den_reiter_und_die_gehzeit_darin(qapp):
    from spotlab.gui.app import MainWindow

    fenster = MainWindow()
    assert "experimente" in fenster.ansichten and "gehzeit" not in fenster.ansichten
    fenster.leiste.knoepfe["experimente"].click()
    assert fenster.stapel.currentWidget() is fenster.ansichten["experimente"]
    assert isinstance(fenster.ansichten["experimente"].experiment("gehzeit"), GehzeitView)
