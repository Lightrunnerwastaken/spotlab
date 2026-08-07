import pytest

from spotlab.editor.syntax import UEBERSETZUNGEN, pruefe, uebersetze


def test_gueltiger_code_ergibt_keine_fehlerstelle():
    assert pruefe("x = 1\n") is None


def test_fehlender_doppelpunkt():
    stelle = pruefe("def f()\n    return 1\n")
    assert stelle.zeile == 1
    assert "Doppelpunkt" in stelle.text


def test_offene_klammer():
    stelle = pruefe("print(1\n")
    assert "Klammer" in stelle.text


def test_offene_zeichenkette():
    stelle = pruefe("s = 'hallo\n")
    assert "Anführungszeichen" in stelle.text


def test_falsche_einrueckung_nennt_die_zeile():
    stelle = pruefe("x = 1\n  y = 2\n")
    assert stelle.zeile == 2
    assert "eingerückt" in stelle.text


def test_unbekannte_meldung_bleibt_im_original():
    # Keine erfundene Erklaerung: eine falsche Faehrte kostet mehr Zeit als
    # der englische Originaltext.
    assert uebersetze("something entirely new") == "Python meldet: something entirely new"


def test_tabelle_ist_spezifisch_vor_allgemein():
    # Die echte Meldung lautet "invalid syntax. Perhaps you forgot a comma?".
    # Stuende das allgemeine Fragment zuerst, kaeme der genauere Hinweis nie zum Zug.
    fragmente = [f for f, _ in UEBERSETZUNGEN]
    assert fragmente.index("Perhaps you forgot a comma") < fragmente.index("invalid syntax")
    assert fragmente.index("unterminated triple-quoted string literal") < fragmente.index(
        "unterminated string literal"
    )


def test_ungueltige_escape_sequenz_erzeugt_keine_warnung(recwarn):
    # "C:\daten" ist auf Windows der erste Pfad, den jemand tippt, und \d ist
    # keine gueltige Escape-Sequenz. Ohne catch_warnings meldete compile() das
    # bei JEDEM Tastendruck.
    assert pruefe(r'pfad = "C:\daten"' + "\n") is None
    assert len(recwarn) == 0


@pytest.mark.parametrize(
    "quelltext, erwartet",
    [
        ("x = 1\ny = [1 2]\n", "Komma"),
        ("if True:\npass\n", "eingerückt"),
        ("1 = 2\n", "Name"),
    ],
)
def test_weitere_anfaengerfehler(quelltext, erwartet):
    stelle = pruefe(quelltext)
    assert stelle is not None
    assert erwartet in stelle.text
