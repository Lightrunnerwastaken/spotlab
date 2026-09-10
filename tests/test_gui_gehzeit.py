"""Die Ansicht „Gehzeit" — der Nachtrag im Fenster statt auf der Kommandozeile.

Sie liest und schreibt ausschliesslich Dateien im Lauf-Verzeichnis: die Tabelle,
den Bildindex und die Bilder. Kein Roboter, kein Lease — dieselbe Regel wie bei
allen Ansichten (H1).
"""

import io
import json
from pathlib import Path

import pytest

from spotlab.experiment import ablage, tabelle
from spotlab.experiment.durchgang import durchgaenge_aus
from spotlab.experiment.zeitnahme import Querung

QUELLE = (Path(__file__).resolve().parents[1] / "src" / "spotlab" / "gui"
          / "views" / "gehzeit.py")

pytest.importorskip("PySide6.QtWidgets")


def _importierte_module(pfad):
    """Die tatsaechlich importierten Modulnamen — auch aus Funktionsrumpfen."""
    import ast

    namen = set()
    for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
        if isinstance(knoten, ast.Import):
            namen.update(teil.name for teil in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            namen.add(knoten.module)
    return namen


def test_ansicht_importiert_weder_bosdyn_noch_backends():
    """CLAUDE.md: kein bosdyn UND kein spotlab.backends unterhalb von gui/."""
    verboten = [
        name for name in _importierte_module(QUELLE)
        if name.split(".")[0] == "bosdyn" or name.startswith("spotlab.backends")
    ]
    assert not verboten, f"Die Ansicht darf das nicht importieren: {verboten}"


# --------------------------------------------------------------- Testdaten


def _bild(breite=8, hoehe=6):
    from PIL import Image

    puffer = io.BytesIO()
    Image.new("RGB", (breite, hoehe), (40, 80, 120)).save(puffer, format="JPEG")
    return puffer.getvalue()


def _lauf(wurzel, name="20260910T094103Z_ab12cd34",
          zeiten=(2.0, 4.0, 5.5, 7.0, 8.5, 30.0)):
    # Unter <Arbeitsordner>/Beispiele/runs/, wo `laufsuche` sucht: Laeufe liegen
    # in einem PROJEKT, nicht lose im Arbeitsordner.
    lauf = Path(wurzel) / "Beispiele" / "runs" / name
    (lauf / "kamera").mkdir(parents=True)
    (lauf / "lauf.json").write_text(json.dumps({"id": name}), encoding="utf-8")
    index = []
    for nummer, t in enumerate(zeiten, start=1):
        datei = f"{nummer:06d}_frontleft_fisheye_image.jpg"
        (lauf / "kamera" / datei).write_bytes(_bild())
        index.append({"t": t, "datei": datei, "quelle": "frontleft_fisheye_image"})
    (lauf / "kamera" / "kamera.jsonl").write_text(
        "".join(json.dumps(z) + "\n" for z in index), encoding="utf-8"
    )
    return lauf


def _tabelle(lauf):
    querungen = [
        Querung(kennung="tag7", richtung=1, t_start=5.0, t_ende=9.0,
                dauer_s=4.0, tempo_m_s=2.5),
        Querung(kennung="tag8", richtung=1, t_start=5.4, t_ende=9.6,
                dauer_s=4.2, tempo_m_s=2.38),
        Querung(kennung="tag9", richtung=1, t_start=40.0, t_ende=48.0,
                verworfen=True, grund="gestoppt"),
    ]
    durchgaenge = durchgaenge_aus(querungen)
    pfad = ablage.csv_pfad(lauf)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tabelle.schreibe(pfad, [
        tabelle.zeile_aus(d, strecke_m=10.0, uhrzeit=f"09:41:0{d.nummer}")
        for d in durchgaenge
    ])
    return pfad


# ------------------------------------------------------------ Ohne Fenster


def test_nur_laeufe_mit_versuch_stehen_zur_auswahl(tmp_path):
    """Ein Arbeitsordner hat Dutzende Laeufe; die allermeisten sind keine
    Gehzeit-Messung."""
    from spotlab.gui.views.gehzeit import laeufe_mit_versuch

    _lauf(tmp_path, name="20260910T090000Z_ohne")
    mit = _lauf(tmp_path, name="20260910T094103Z_mit")
    _tabelle(mit)
    gefunden = laeufe_mit_versuch(tmp_path)
    assert [p.name for p in gefunden] == ["20260910T094103Z_mit"]


def test_die_juengsten_laeufe_stehen_oben(tmp_path):
    from spotlab.gui.views.gehzeit import laeufe_mit_versuch

    for name in ("20260910T090000Z_a", "20260910T094103Z_b"):
        _tabelle(_lauf(tmp_path, name=name))
    assert [p.name[:16] for p in laeufe_mit_versuch(tmp_path)] == [
        "20260910T094103Z", "20260910T090000Z",
    ]


def test_eine_tabellenzeile_zeigt_was_zum_entscheiden_noetig_ist(tmp_path):
    from spotlab.gui.views.gehzeit import zeilen_aus

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    zeilen = zeilen_aus(lauf)
    assert len(zeilen) == 2
    erste = zeilen[0]
    assert erste["nummer"] == 1
    assert erste["texte"][1] == "09:41:01"          # Uhrzeit
    assert "4.10" in erste["texte"][3]              # Laufzeit (Median 4.0/4.2)
    assert erste["bilder"] == 4                     # Zeitfenster samt Rand
    assert erste["texte"][6] == ""                  # Gruppe noch offen


def test_ein_verworfener_durchgang_nennt_seinen_grund(tmp_path):
    from spotlab.gui.views.gehzeit import zeilen_aus

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    zweite = zeilen_aus(lauf)[1]
    assert "gestoppt" in zweite["texte"][5]
    assert zweite["texte"][3] == "—", "ohne Messung keine Laufzeit, auch keine 0"


def test_ohne_tabelle_gibt_es_keine_zeilen_und_keinen_absturz(tmp_path):
    from spotlab.gui.views.gehzeit import zeilen_aus

    assert zeilen_aus(_lauf(tmp_path)) == []


# ---------------------------------------------------------------- Ansicht


def test_die_ansicht_zeigt_die_durchgaenge(qapp, tmp_path):
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    ansicht = GehzeitView()
    ansicht.lade(lauf)
    assert ansicht.tabelle.rowCount() == 2
    assert ansicht.tabelle.item(0, 1).text() == "09:41:01"


def test_die_ansicht_zeigt_die_bilder_des_gewaehlten_durchgangs(qapp, tmp_path):
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    ansicht = GehzeitView()
    ansicht.lade(lauf)
    ansicht.waehle_zeile(0)
    assert len(ansicht.bilder()) == 4
    assert ansicht.bild.pixmap() is not None and not ansicht.bild.pixmap().isNull()
    ansicht.weiter()
    assert ansicht.bildnummer() == 1


def test_ein_durchgang_ohne_bilder_zeigt_das_statt_eines_leeren_kastens(qapp, tmp_path):
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    ansicht = GehzeitView()
    ansicht.lade(lauf)
    ansicht.waehle_zeile(1)          # der verworfene Durchgang bei t = 40 s
    assert ansicht.bilder() == []
    assert "keine Bilder" in ansicht.bild.text()


def test_der_eintrag_landet_in_der_tabelle_und_in_der_ansicht(qapp, tmp_path):
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    pfad = _tabelle(lauf)
    ansicht = GehzeitView()
    ansicht.lade(lauf)
    ansicht.waehle_zeile(0)
    ansicht.klasse.setText("4bG")
    ansicht.gruppe.setValue(3)
    ansicht.eintragen.click()

    zeile = tabelle.lies(pfad)[0]
    assert zeile["klasse"] == "4bG" and zeile["gruppengroesse"] == 3
    assert zeile["laufzeit_s"] == pytest.approx(4.1), "Spots Messwerte bleiben stehen"
    assert ansicht.tabelle.item(0, 6).text() == "3"


def test_ohne_gewaehlten_durchgang_sagt_der_eintrag_was_fehlt(qapp, tmp_path):
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    ansicht = GehzeitView()
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht.lade(lauf)
    ansicht.tabelle.clearSelection()
    ansicht.eintragen.click()
    assert gemeldet and "Durchgang" in gemeldet[-1]


def test_die_bilder_eines_durchgangs_lassen_sich_loeschen(qapp, tmp_path):
    """Aufnahmen von Mitschuelern, gemacht fuer EINE Frage."""
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    ansicht = GehzeitView()
    ansicht.lade(lauf)
    ansicht.waehle_zeile(0)
    assert ansicht.loesche_gewaehlte() == 4
    assert ansicht.bilder() == []
    uebrig = sorted(p.name[:6] for p in (lauf / "kamera").glob("*.jpg"))
    assert uebrig == ["000001", "000006"]


def test_vor_dem_loeschen_wird_gefragt(qapp, tmp_path):
    """Loeschen ist endgueltig, und es sind Aufnahmen von Menschen. Der Knopf
    fragt, wie es die Kommandozeile tut."""
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    ansicht = GehzeitView()
    gefragt = []
    ansicht._frage = lambda text: gefragt.append(text) or False
    ansicht.lade(lauf)
    ansicht.waehle_zeile(0)
    ansicht.loeschen.click()
    assert gefragt and "4 Bilder" in gefragt[0]
    assert len(list((lauf / "kamera").glob("*.jpg"))) == 6, "nichts geloescht"

    ansicht.loeschen_alle.click()
    assert len(gefragt) == 2
    assert len(list((lauf / "kamera").glob("*.jpg"))) == 6


def test_alle_bilder_auf_einmal_loeschen(qapp, tmp_path):
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    ansicht = GehzeitView()
    ansicht.lade(lauf)
    assert ansicht.loesche_alle() == 6
    assert list((lauf / "kamera").glob("*.jpg")) == []


def test_die_ansicht_findet_die_laeufe_im_arbeitsordner(qapp, tmp_path):
    from spotlab.gui.views.gehzeit import GehzeitView

    lauf = _lauf(tmp_path)
    _tabelle(lauf)
    ansicht = GehzeitView()
    ansicht.setze_arbeitsordner(tmp_path)
    assert ansicht.auswahl.count() == 1
    assert ansicht.tabelle.rowCount() == 2, "der jüngste Lauf ist gleich geladen"


def test_ohne_arbeitsordner_bleibt_die_ansicht_leer_und_sagt_es(qapp):
    from spotlab.gui.views.gehzeit import GehzeitView

    ansicht = GehzeitView()
    ansicht.setze_arbeitsordner(None)
    assert ansicht.auswahl.count() == 0
    assert ansicht.tabelle.rowCount() == 0
    assert "kein" in ansicht.hinweis.text().lower()


# ----------------------------------------------------------------- Starten


def test_der_startknopf_startet_paketcode_nicht_die_kopie_im_arbeitsordner(qapp, tmp_path):
    """Eine Datei im Arbeitsordner kann ein Schueler bearbeiten — und dann
    startete ein Knopf, der 'misst nur zu' verspricht, etwas, das faehrt."""
    from spotlab.gui.views import gehzeit as ansichtsmodul

    gestartet = {}

    def falscher_start(skript, argumente=None, **kw):
        gestartet["skript"] = Path(skript)
        gestartet["argumente"] = list(argumente or [])
        return object()

    ansicht = ansichtsmodul.GehzeitView()
    ansicht.setze_arbeitsordner(tmp_path)
    ansicht._start = falscher_start
    ansicht.starten.click()

    assert gestartet["skript"].name == "gehzeit.py"
    assert gestartet["skript"].parent.name == "workshop"
    assert "--runs" in gestartet["argumente"]
    assert str(tmp_path / "Beispiele" / "runs") in gestartet["argumente"]


def test_ohne_arbeitsordner_startet_nichts_und_es_wird_gesagt(qapp):
    from spotlab.gui.views.gehzeit import GehzeitView

    ansicht = GehzeitView()
    gemeldet = []
    ansicht.meldung.connect(gemeldet.append)
    ansicht.setze_arbeitsordner(None)
    ansicht.starten.click()
    assert gemeldet and "Arbeitsordner" in gemeldet[-1]
