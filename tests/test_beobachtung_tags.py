"""Tag-Beobachtungen mitschreiben — die fehlende Haelfte der Lehrer-Aufnahme.

Der Beobachter schreibt Bilder mit, aber keine erkannten Objekte. Fuer den
Versuch „der Tag ist der Lehrer" (matura-spot, `notes/VISION_umweltbezug.md`)
ist genau das die Label-Quelle: der Tag am Stuhl sagt bei jedem Bild, wo der
Stuhl ist.

Dieselbe Sicherheitsaussage wie bei `Zustandsquelle` und `Bildquelle`:
`WorldObjectClient` liest nur, es gibt keine Kommando-Methode, und deshalb
bleibt der Beobachter-Modus vor Abnahmepunkt A1 benutzbar.
"""

import json
from pathlib import Path

import pytest

from spotlab.beobachtung.tagquelle import Tagquelle, TrockeneTagquelle
from spotlab.beobachtung.tags import Tagmitschnitt
from spotlab.record.run import RunRecorder

QUELLE = (Path(__file__).resolve().parents[1] / "src" / "spotlab" / "beobachtung"
          / "tagquelle.py")


# --------------------------------------------------------------- Die Quelle


def test_die_tagquelle_hat_genau_eine_methode():
    """Staerker als eine Pruefung zur Laufzeit: es gibt nichts zu missbrauchen.

    Dieselbe Form wie `Zustandsquelle`. Wer hier eine zweite Methode
    hinzufuegt, muss sich fragen, ob der Beobachter noch leaselos ist.
    """
    oeffentlich = [n for n in dir(Tagquelle) if not n.startswith("_")]
    assert oeffentlich == ["objekte"]


def test_die_tagquelle_kennt_keine_kommandos():
    quelltext = QUELLE.read_text(encoding="utf-8")
    for verboten in ("robot_command", "RobotCommandBuilder", "LeaseClient",
                     "EstopClient", "power_on"):
        assert verboten not in quelltext, f"{verboten} gehoert nicht in beobachtung/"


class FakeWeltClient:
    def __init__(self, antwort=None, fehler=None):
        self.aufrufe = []
        self._antwort = antwort
        self._fehler = fehler

    def list_world_objects(self, object_type=None, **kw):
        self.aufrufe.append(object_type)
        if self._fehler is not None:
            raise self._fehler
        return self._antwort


def _antwort_mit(*objekte):
    from bosdyn.api import world_object_pb2 as wo

    antwort = wo.ListWorldObjectResponse()
    antwort.world_objects.extend(objekte)
    return antwort


def test_die_quelle_fragt_nur_nach_fiducials():
    """Alles zu holen waere mehr Bytes ueber das WLAN fuer Objekte, die niemand
    labelt — und der Mitschnitt laeuft eine halbe Stunde."""
    from bosdyn.api import world_object_pb2 as wo

    client = FakeWeltClient(_antwort_mit())
    Tagquelle(client).objekte()
    assert client.aufrufe == [[wo.WORLD_OBJECT_APRILTAG]]


def test_die_quelle_gibt_die_objekte_weiter():
    from bosdyn.api import world_object_pb2 as wo

    objekt = wo.WorldObject(id=7, name="world_obj_apriltag_007")
    objekt.apriltag_properties.tag_id = 7
    gefunden = Tagquelle(FakeWeltClient(_antwort_mit(objekt))).objekte()
    assert [o.apriltag_properties.tag_id for o in gefunden] == [7]


# ------------------------------------------------------------ Die Attrappe


def test_die_trockene_quelle_baut_echte_protos():
    """Wie `TrockeneBildquelle`: die Attrappe faelscht die ZAHLEN, nicht das
    Format. Nur so durchlaeuft die Probe dieselbe Schreib- und Indexlogik."""
    from bosdyn.api import world_object_pb2 as wo

    objekte = TrockeneTagquelle().objekte()
    assert objekte and all(isinstance(o, wo.WorldObject) for o in objekte)
    tag = objekte[0]
    assert tag.apriltag_properties.tag_id > 0
    assert tag.apriltag_properties.dimensions.x > 0


def test_die_trockene_quelle_traegt_einen_rahmenbaum_mit_vision():
    """Ohne `vision` im Schnappschuss ist die Tag-Pose nicht in die Welt zu
    rechnen — und genau das braucht die Labelerzeugung."""
    tag = TrockeneTagquelle().objekte()[0]
    rahmen = set(tag.transforms_snapshot.child_to_parent_edge_map)
    assert "vision" in rahmen
    assert tag.apriltag_properties.frame_name_fiducial in rahmen


def test_die_trockene_quelle_bewegt_den_tag_nicht():
    """Der Stuhl steht still. Ein wandernder Attrappen-Tag wuerde in der Probe
    einen Fehler verdecken, den es am Geraet nicht gibt."""
    quelle = TrockeneTagquelle()
    lagen = []
    for _ in range(3):
        tag = quelle.objekte()[0]
        kante = tag.transforms_snapshot.child_to_parent_edge_map[
            tag.apriltag_properties.frame_name_fiducial
        ]
        lagen.append(kante.parent_tform_child.position.x)
    assert len(set(lagen)) == 1


# ----------------------------------------------------------- Der Mitschnitt


def _recorder(tmp_path):
    return RunRecorder(tmp_path, None, backend="beobachter-trocken")


def _zeilen(recorder):
    pfad = Path(recorder.dir) / "tags" / "tags.jsonl"
    if not pfad.is_file():
        return []
    return [json.loads(z) for z in pfad.read_text(encoding="utf-8").splitlines() if z.strip()]


def test_ein_takt_schreibt_eine_zeile_mit_zeit_und_objekten(tmp_path):
    recorder = _recorder(tmp_path)
    mitschnitt = Tagmitschnitt(TrockeneTagquelle(), recorder, hz=2.0)
    mitschnitt._einmal()
    zeilen = _zeilen(recorder)
    assert len(zeilen) == 1
    assert zeilen[0]["t"] >= 0.0
    assert len(zeilen[0]["objekte"]) == 1
    assert zeilen[0]["objekte"][0]["apriltagProperties"]["tagId"] == 1


def test_der_ganze_schnappschuss_wird_mitgeschrieben(tmp_path):
    """Was hier fehlt, fehlt fuer immer: die Labelerzeugung braucht die
    Tag-Pose IM RAHMENBAUM, und die Aufnahme findet einmal statt."""
    recorder = _recorder(tmp_path)
    Tagmitschnitt(TrockeneTagquelle(), recorder, hz=2.0)._einmal()
    objekt = _zeilen(recorder)[0]["objekte"][0]
    assert "childToParentEdgeMap" in objekt["transformsSnapshot"]
    assert "vision" in objekt["transformsSnapshot"]["childToParentEdgeMap"]


def test_ein_gescheiterter_abruf_wird_gezaehlt_statt_geworfen(tmp_path):
    """Ein WLAN-Hänger darf die Messfahrt nicht kippen — aber er darf auch
    nicht unsichtbar bleiben."""
    class Kaputt:
        def objekte(self):
            raise RuntimeError("Funk weg")

    recorder = _recorder(tmp_path)
    mitschnitt = Tagmitschnitt(Kaputt(), recorder, hz=2.0)
    mitschnitt._einmal()          # wirft nicht
    zaehler = mitschnitt.zaehler()
    assert zaehler["fehler"] == 1
    assert "Funk weg" in zaehler["letzter_fehler"]
    assert _zeilen(recorder) == []


def test_leere_takte_werden_auch_geschrieben(tmp_path):
    """'Vier Sekunden lang keinen Tag gesehen' ist eine Information, die man
    beim Auswerten braucht — dieselbe Regel wie bei der erfolglosen Tag-Abfrage
    in `api/world.py`."""
    class Leer:
        def objekte(self):
            return []

    recorder = _recorder(tmp_path)
    Tagmitschnitt(Leer(), recorder, hz=2.0)._einmal()
    zeilen = _zeilen(recorder)
    assert len(zeilen) == 1 and zeilen[0]["objekte"] == []


def test_der_zaehler_zaehlt_takte_und_tags(tmp_path):
    recorder = _recorder(tmp_path)
    mitschnitt = Tagmitschnitt(TrockeneTagquelle(), recorder, hz=2.0)
    for _ in range(3):
        mitschnitt._einmal()
    zaehler = mitschnitt.zaehler()
    assert zaehler["takte"] == 3 and zaehler["tags"] == 3


def test_start_und_stop_sind_idempotent(tmp_path):
    recorder = _recorder(tmp_path)
    mitschnitt = Tagmitschnitt(TrockeneTagquelle(), recorder, hz=50.0)
    mitschnitt.start()
    mitschnitt.start()
    mitschnitt.stop()
    mitschnitt.stop()
    assert _zeilen(recorder), "der Thread hat mindestens einen Takt geschrieben"


def test_rate_null_startet_keinen_thread(tmp_path):
    """Dieselbe Entscheidung wie beim Bildmitschnitt: 0 heisst 'gar nicht',
    und das wird beim Start entschieden, nicht mitten im Takt."""
    recorder = _recorder(tmp_path)
    mitschnitt = Tagmitschnitt(TrockeneTagquelle(), recorder, hz=0.0)
    mitschnitt.start()
    mitschnitt.stop()
    assert _zeilen(recorder) == []


# ------------------------------------------------------------ Verdrahtung


def test_die_trockenprobe_legt_bilder_und_tags_an(tmp_path):
    from spotlab.beobachtung.session import Beobachtung

    sitzung = Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=50.0, tags_hz=50.0)
    try:
        assert sitzung.tagzaehler() is not None
    finally:
        sitzung.beende()
    lauf = Path(sitzung.lauf_verzeichnis)
    assert (lauf / "kamera" / "kamera.jsonl").is_file()
    assert (lauf / "tags" / "tags.jsonl").is_file()


def test_ohne_tags_bleibt_alles_wie_bisher(tmp_path):
    from spotlab.beobachtung.session import Beobachtung

    sitzung = Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=0.0, tags_hz=0.0)
    try:
        assert sitzung.tagzaehler() is None
    finally:
        sitzung.beende()
    assert not (Path(sitzung.lauf_verzeichnis) / "tags").exists()


def test_die_tagrate_steht_im_verbunden_ereignis(tmp_path):
    """Wer den Lauf spaeter ansieht, muss wissen, ob Tags mitgeschrieben
    wurden — eine leere Datei und ein abgeschalteter Mitschnitt sehen sonst
    gleich aus."""
    from spotlab.beobachtung.session import Beobachtung
    from spotlab.record.read import read_jsonl

    sitzung = Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=0.0, tags_hz=2.0)
    sitzung.beende()
    saetze = read_jsonl(Path(sitzung.lauf_verzeichnis) / "ereignisse.jsonl")
    verbunden = [s for s in saetze if s["art"] == "verbunden"][0]
    assert verbunden["daten"]["tags_hz"] == pytest.approx(2.0)
