import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QTextCursor  # noqa: E402

from spotlab.editor.verbs import Vorschlag  # noqa: E402
from spotlab.gui.editor import completer as modul  # noqa: E402
from spotlab.gui.editor.codeedit import CodeEdit  # noqa: E402
from spotlab.gui.editor.completer import (  # noqa: E402
    Vervollstaendigung,
    eigene_vorschlaege,
    zusammenfuehren,
)
from spotlab.gui.theme import DUNKEL  # noqa: E402


def test_eigener_eintrag_gewinnt_bei_namensgleichheit():
    # Nur der eigene traegt Signatur und deutsche Erklaerung.
    eigen = Vorschlag("move", "move(forward=0.0)", "Geht eine feste Strecke.")
    fremd = Vorschlag("move", "move", "Funktion")
    assert zusammenfuehren([eigen], [fremd]) == [eigen]


def test_fremde_ergaenzen_was_wir_nicht_kennen():
    eigen = Vorschlag("move", "move()", "Geht.")
    fremd = Vorschlag("sqrt", "sqrt", "Funktion")
    assert zusammenfuehren([eigen], [fremd]) == [eigen, fremd]


def test_reihenfolge_ist_stabil():
    eigene = [Vorschlag(n, n, "") for n in ("a", "b")]
    fremde = [Vorschlag(n, n, "") for n in ("c", "a", "d")]
    assert [v.name for v in zusammenfuehren(eigene, fremde)] == ["a", "b", "c", "d"]


def test_eigene_vorschlaege_nach_spot_punkt():
    namen = {v.name for v in eigene_vorschlaege("    spot.")}
    assert "navigate_to" in namen


def test_kein_vorschlag_fuer_fremde_namen():
    assert eigene_vorschlaege("roboter.") == []


def _feld():
    from spotlab.gui.editor.codeedit import CodeEdit
    from spotlab.gui.theme import palette_fuer

    return CodeEdit(palette_fuer(False))


def _hilfe_mit(feld, text):
    hilfe = Vervollstaendigung(feld)
    feld.setPlainText(text)
    feld.moveCursor(QTextCursor.End)
    return hilfe


def test_ohne_jedi_kommen_trotzdem_vorschlaege(qapp, monkeypatch):
    """Der Rueckfall ist die Bedingung dafuer, dass die Suite ohne jedi gruen ist."""
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    assert hilfe.modell.rowCount() > 0


def test_veraltete_jedi_antwort_wird_verworfen(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    vorher = hilfe.modell.rowCount()
    hilfe._jedi_fertig(-1, [Vorschlag("veraltet", "veraltet", "")])
    assert hilfe.modell.rowCount() == vorher


def test_aktuelle_jedi_antwort_wird_ergaenzt(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    vorher = hilfe.modell.rowCount()
    hilfe._jedi_fertig(hilfe._nummer, [Vorschlag("etwas_neues", "etwas_neues", "Wert")])
    assert hilfe.modell.rowCount() == vorher + 1


def test_einfuegen_schreibt_den_blossen_namen(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.mo")
    hilfe.anfordern(erzwungen=True)
    hilfe._einfuegen("move")
    assert feld.toPlainText() == "spot.move"


def test_einfuegen_versteht_auch_den_anzeigetext(qapp, monkeypatch):
    # Absicherung gegen die Qt-Version: je nach Aufbau liefert
    # QCompleter.activated den completionRole ODER den Anzeigetext.
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    index = hilfe.modell.index(0, 0)
    anzeige = hilfe.modell.data(index)
    name = hilfe.modell.data(index, modul.NAME_ROLLE)
    hilfe._einfuegen(anzeige)
    assert feld.toPlainText() == f"spot.{name}"


def test_anzeige_ist_der_name_signatur_und_hilfe_haben_eigene_rollen(qapp, monkeypatch):
    """Frueher stand alles in EINEM String -- das war das alte Design. Jetzt
    zeichnet ein Delegate die Teile getrennt, also muss das Modell sie trennen."""
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    m = hilfe.modell
    zeile = next(z for z in range(m.rowCount()) if m.data(m.index(z, 0)) == "move")
    index = m.index(zeile, 0)
    assert m.data(index) == "move"
    assert m.data(index, modul.SIGNATUR_ROLLE).startswith("move(")
    assert "Strecke" in m.data(index, modul.HILFE_ROLLE)
    assert m.data(index, modul.ART_ROLLE) == "methode"


def test_mit_jedi_werden_fremde_namen_ergaenzt(qapp):
    """Was jedi abdeckt und wir nicht: math., np., lokale Variablen."""
    pytest.importorskip("jedi")
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "import math\nmath.")
    fremde = hilfe.jedi_lesen(feld.toPlainText(), 2, 5, None)
    assert "sqrt" in {v.name for v in fremde}


# ======================== S1.10 Reiter schliessen waehrend jedi noch laeuft
#
# `feld.deleteLater()` zerstoert das CodeEdit; der Vervollstaendiger haengt
# darunter, der JediWorker-QThread wieder darunter. Laeuft der noch, wird ein
# QThread destruiert, waehrend er arbeitet -- das reisst das GANZE Fenster mit,
# inklusive NOT-AUS-Knopf, und ein laufendes Roboterprogramm im Kindprozess
# bleibt fuehrerlos zurueck.


class _LangsamerWorker:
    """Ein Arbeiter, der noch laeuft, wenn der Reiter geschlossen wird."""

    def __init__(self):
        self.getrennt = False
        self.gewartet = False
        self._laeuft = True

    def isRunning(self):
        return self._laeuft

    @property
    def fertig(self):
        arbeiter = self

        class Signalattrappe:
            def disconnect(self, *a, **kw):
                arbeiter.getrennt = True

        return Signalattrappe()

    def wait(self, ms=None):
        self.gewartet = True
        self._laeuft = False
        return True

    def requestInterruption(self):
        pass


def test_schliesse_trennt_und_wartet_auf_den_arbeiter(qapp):
    feld = _feld()
    v = Vervollstaendigung(feld)
    arbeiter = _LangsamerWorker()
    v._worker = arbeiter
    v.schliesse()
    assert arbeiter.getrennt, "die Antwort haette in ein zerstoertes Widget gezeigt"
    assert arbeiter.gewartet, "der Thread wurde nicht abgewartet"
    assert v._worker is None


def test_schliesse_ohne_arbeiter_ist_harmlos(qapp):
    Vervollstaendigung(_feld()).schliesse()   # darf nicht werfen


def test_eine_verspaetete_antwort_nach_dem_schliessen_wird_ignoriert(qapp):
    """Der Kern: die Antwort darf das zerstoerte Widget nicht mehr anfassen."""
    feld = _feld()
    v = Vervollstaendigung(feld)
    v._nummer = 5
    v.schliesse()
    v._jedi_fertig(5, [("os.path", "os.path")])       # darf nicht werfen


# ------------------------------------------------ Aussehen wie in VS Code


def test_jedi_art_wird_uebersetzt():
    assert modul.art_von("function") == "funktion"
    assert modul.art_von("module") == "modul"
    assert modul.art_von("voellig_unbekannt") == ""


def test_popup_traegt_den_namen_den_das_stylesheet_erwartet(qapp, monkeypatch):
    """CLAUDE.md: Farben nur aus theme.py. Ein QCompleter-Popup ist ein eigenes
    Toplevel-Widget und bekommt sonst Qts Standardlook."""
    from spotlab.gui.theme import stylesheet

    monkeypatch.setattr(modul, "jedi", None)
    hilfe = _hilfe_mit(CodeEdit(DUNKEL), "spot.")
    assert hilfe.completer.popup().objectName() == "Vorschlaege"
    assert "QListView#Vorschlaege" in stylesheet(DUNKEL)
    assert "QFrame#Hilfekasten" in stylesheet(DUNKEL)


def test_popup_zeichnet_mit_eigenem_delegate(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    hilfe = _hilfe_mit(CodeEdit(DUNKEL), "spot.")
    assert isinstance(hilfe.completer.popup().itemDelegate(), modul.VorschlagDelegate)


def test_hilfekasten_zeigt_den_markierten_eintrag(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    m = hilfe.modell
    zeile = next(z for z in range(m.rowCount()) if m.data(m.index(z, 0)) == "move")
    hilfe._markiert(m.index(zeile, 0))
    text = hilfe.hilfekasten.text()
    assert "Strecke" in text
    assert "move(" in text


def test_hilfekasten_verschwindet_mit_dem_popup(qapp, monkeypatch):
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    hilfe._markiert(hilfe.modell.index(0, 0))
    hilfe.completer.popup().hide()
    assert not hilfe.hilfekasten.isVisible()


def test_liste_faellt_nicht_auf_scrollbalkenbreite_zusammen(qapp, monkeypatch):
    """Ein sizeHint, das option.rect.width() zurueckgibt, ist bei der
    Spaltenmessung null -- das Popup war 70 px breit, jeder Name abgeschnitten."""
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    feld.resize(700, 300)
    feld.show()
    hilfe = _hilfe_mit(feld, "spot.")
    hilfe.anfordern(erzwungen=True)
    assert hilfe.completer.popup().width() >= 200


# ==================== S1.11 Vorschlaege im ganzen Editor, nicht nur nach spot.
#
# Bis zum 09.09.2026 kehrte `anfordern` um, sobald die eigene Liste leer war.
# jedi kam damit nur ueber Strg+Leertaste zum Zug -- wer die Tastenkombination
# nicht kannte, sah im ganzen Editor Vorschlaege ausschliesslich nach `spot.`
# und `spotlab.`, obwohl jedi laengst mitinstalliert war.


def _gefragt(hilfe, monkeypatch):
    """Protokolliert, ob `anfordern` jedi ueberhaupt fragt."""
    protokoll = []
    monkeypatch.setattr(
        hilfe, "_frage_jedi", lambda nummer, quelltext=None: protokoll.append(nummer)
    )
    return protokoll


@pytest.mark.parametrize("text, erwartet", [
    ("import math\nmath.", True),          # der Fall des Autors
    ("zahlen = []\nzahlen.ap", True),
    ("import ma", True),
    ("pri", True),
    ("spot.", True),                        # die eigene Liste bleibt, wie sie war
    ("p", False),                           # ein Buchstabe oeffnet keine Liste
    ("", False),
    ("x = 1 + ", False),
    ("# eine Notiz mit pri", False),        # im Kommentar gibt jedi 158 globale Namen
    ('pfad = "C:/Use', False),              # in der Zeichenkette Verzeichnisse des Laptops
    ('"""Fahre zum Fen', False),            # und im Docstring schreibt man Prosa
])
def test_wo_jedi_gefragt_wird_und_wo_nicht(qapp, monkeypatch, text, erwartet):
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, text)
    protokoll = _gefragt(hilfe, monkeypatch)
    hilfe.anfordern()
    assert bool(protokoll) is erwartet


def test_strg_leertaste_fragt_auch_dort_wo_von_selbst_nichts_kaeme(qapp, monkeypatch):
    """Wer ausdruecklich fragt, bekommt die Antwort -- auch im Kommentar."""
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "# eine Notiz")
    protokoll = _gefragt(hilfe, monkeypatch)
    hilfe.anfordern(erzwungen=True)
    assert protokoll


def test_ohne_eigene_liste_erscheint_die_jedi_antwort(qapp, monkeypatch):
    """Die Kette bis zur Anzeige: `math.` hat keine eigene Liste, und trotzdem
    steht am Ende ein Vorschlag im Modell."""
    monkeypatch.setattr(modul, "jedi", None)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "import math\nmath.")
    hilfe.anfordern()
    assert hilfe.modell.rowCount() == 0, "eigene Liste ist hier leer"
    hilfe._jedi_fertig(hilfe._nummer, [Vorschlag("sqrt", "sqrt", "", "funktion")])
    assert [hilfe.modell.data(hilfe.modell.index(0, 0))] == ["sqrt"]


def test_mit_echtem_jedi_kommen_vorschlaege_fuer_ein_modul(qapp):
    """Gegenprobe ohne Attrappe: dieselbe Stelle, echtes jedi."""
    pytest.importorskip("jedi")
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "import math\nmath.")
    fremde = hilfe.jedi_lesen(feld.toPlainText(), 2, 5, None)
    assert "sqrt" in {v.name for v in fremde}
    hilfe.anfordern()
    assert hilfe._worker is not None, "der Arbeiter wurde nie gestartet"
    hilfe.schliesse()


class _Signalattrappe:
    def __init__(self, protokoll, name):
        self._protokoll, self._name = protokoll, name

    def connect(self, ziel):
        self._protokoll.append((self._name, ziel))

    def disconnect(self, ziel=None):
        self._protokoll.append((self._name, "getrennt"))


class _Attrappenworker:
    """Zaehlt, woran der Vervollstaendiger den Arbeiter haengt -- und laeuft."""

    def __init__(self, *args, **kw):
        self.args = args
        self.verbunden = []
        self.gestartet = False
        self.laeuft = False
        self.fertig = _Signalattrappe(self.verbunden, "fertig")
        self.finished = _Signalattrappe(self.verbunden, "finished")

    def deleteLater(self):
        pass

    def isRunning(self):
        return self.laeuft

    def start(self):
        self.gestartet = True
        self.laeuft = True

    def wait(self, ms=None):
        self.laeuft = False
        return True


def test_jeder_arbeiter_raeumt_sich_selbst_ab(qapp, monkeypatch):
    """Ein Arbeiter je Tastendruck: ohne `deleteLater` blieben sie alle als
    Kinder haengen, bis der Reiter zugeht. Bei zwei Anfragen nach `spot.` fiel
    das nicht auf, bei Vorschlaegen im ganzen Editor sind es Hunderte."""
    monkeypatch.setattr(modul, "JediWorker", _Attrappenworker)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "import math\nmath.")
    hilfe.anfordern()
    arbeiter = hilfe._worker
    assert arbeiter.gestartet
    assert ("finished", arbeiter.deleteLater) in arbeiter.verbunden
    assert ("fertig", hilfe._jedi_fertig) in arbeiter.verbunden


# ============ S1.12 Genau EINE jedi-Anfrage zur Zeit
#
# jedi spricht mit einem Hilfsprozess ueber eine Pipe, und die teilen sich alle
# Scripts. Sechs gleichzeitige Anfragen auf `math.sq` am 09.09.2026: fuenfmal
# Muell (`UnpicklingError: invalid load key`, `'AccessPath' object has no
# attribute 'suffix'`) und ein Thread, der nach 60 s immer noch nicht zurueck
# war. Mit Serialisierung: sechsmal das richtige Ergebnis in 160 ms. Vorher fiel
# das kaum auf, weil nur `spot.` ueberhaupt fragte -- jetzt fragt jeder
# Tastendruck.


def test_jedi_wird_nie_zweimal_gleichzeitig_gefragt(monkeypatch):
    import threading
    import time
    from types import SimpleNamespace

    laufend, hoechststand = [], []

    class _Skript:
        def complete(self, zeile, spalte):
            laufend.append(1)                 # append/pop sind in CPython atomar
            hoechststand.append(len(laufend))
            time.sleep(0.02)
            laufend.pop()
            return []

    monkeypatch.setattr(modul, "jedi", SimpleNamespace(Script=lambda **kw: _Skript()))
    faeden = [threading.Thread(target=modul.jedi_lesen, args=("x", 1, 1, None))
              for _ in range(6)]
    for faden in faeden:
        faden.start()
    for faden in faeden:
        faden.join(timeout=10)
    assert not any(f.is_alive() for f in faeden), "ein Faden kam nicht zurueck"
    assert len(hoechststand) == 6 and max(hoechststand) == 1


def test_solange_einer_laeuft_faengt_keiner_an_und_der_neueste_gewinnt(qapp, monkeypatch):
    """Die Sperre allein genuegte fuer die Richtigkeit -- die Arbeiter stauten
    sich dann aber vor ihr, einer je Tastendruck."""
    erzeugt = []

    class _Worker(_Attrappenworker):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            erzeugt.append(self)

    monkeypatch.setattr(modul, "JediWorker", _Worker)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "import math\nmath.")
    hilfe.anfordern()
    assert len(erzeugt) == 1 and hilfe._auftrag is None

    feld.insertPlainText("s")
    hilfe.anfordern()
    feld.insertPlainText("q")
    hilfe.anfordern()
    assert len(erzeugt) == 1, "es laeuft schon einer"
    assert hilfe._auftrag is not None, "der Auftrag wartet"

    erzeugt[0].laeuft = False                  # der Faden ist zu Ende
    hilfe._starte_auftrag()                    # daran haengt das finished-Signal
    assert len(erzeugt) == 2
    assert erzeugt[1].args[1].endswith("math.sq"), "der Zwischenstand faellt weg"
    assert hilfe._auftrag is None


def test_nach_dem_schliessen_faengt_kein_wartender_auftrag_mehr_an(qapp, monkeypatch):
    erzeugt = []

    class _Worker(_Attrappenworker):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            erzeugt.append(self)

    monkeypatch.setattr(modul, "JediWorker", _Worker)
    feld = CodeEdit(DUNKEL)
    hilfe = _hilfe_mit(feld, "import math\nmath.")
    hilfe.anfordern()
    feld.insertPlainText("s")
    hilfe.anfordern()
    assert hilfe._auftrag is not None
    hilfe.schliesse()
    assert hilfe._auftrag is None
    hilfe._starte_auftrag()
    assert len(erzeugt) == 1
