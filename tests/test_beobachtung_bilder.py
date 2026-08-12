"""Der Bildmitschnitt des Beobachter-Modus.

Zwei Sorten Aussagen stehen hier: die SICHERHEITSAUSSAGE (die Bildquelle kann
den Roboter so wenig bewegen wie die Zustandsquelle) und die
DATENAUSSAGE — Bytes kommen unverfälscht auf die Platte, ein Ausfall wird
gezählt statt verschluckt, und der Dauerstrom fasst den quadratischen
Schreibweg von `RunRecorder.image()` nicht an.

Die Datenaussage ist die wichtigere: eine Messfahrt findet einmal statt.
"""

import json
import struct
import time

from spotlab.beobachtung.bilder import Bildmitschnitt
from spotlab.beobachtung.bildquelle import (
    FISHEYE,
    TIEFE,
    Bildquelle,
    TrockeneBildquelle,
    waehle_quellen,
)
from spotlab.record.run import RunRecorder

VERBOTEN = (
    "send_command", "power_on", "power_off", "walk", "move", "stand", "sit",
    "stop", "navigate", "upload_map", "localize", "close",
)


def _recorder(tmp_path):
    return RunRecorder(tmp_path / "runs", None, backend="beobachter")


def _index(recorder):
    text = (recorder.dir / "kamera" / "kamera.jsonl").read_text(encoding="utf-8")
    return [json.loads(z) for z in text.splitlines() if z.strip()]


def _laufe_bis(mitschnitt, mindestens, frist=10.0):
    """Warten, bis genug Saetze da sind — aber nie unbegrenzt.

    Eine feste Schlafzeit waere entweder zu kurz (unter Last) oder verschenkte
    Zeit. `pytest-timeout` ist das Netz darunter, nicht der Ersatz.
    """
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        if mitschnitt.zaehler()["saetze"] >= mindestens:
            return True
        time.sleep(0.02)
    return False


# --------------------------------------------------------------- Sicherheit


def test_die_bildquelle_hat_nur_diese_eine_methode():
    oeffentlich = {n for n in dir(Bildquelle) if not n.startswith("_")}
    assert oeffentlich == {"bilder"}, f"unerwartete Oberflaeche: {oeffentlich}"


def test_die_bildquelle_hat_keine_kommando_methode():
    for name in VERBOTEN:
        assert not hasattr(Bildquelle, name), name


def test_die_quellen_werden_gegen_die_gemeldeten_geschnitten():
    """Ein Name, den der Roboter nicht kennt, laesst sonst den GANZEN Abruf
    scheitern — also alle Kameras, nicht nur die eine."""
    gemeldet = ["frontleft_fisheye_image", "back_fisheye_image", "irgendwas_neues"]
    assert waehle_quellen(gemeldet) == (
        "frontleft_fisheye_image",
        "back_fisheye_image",
    )


def test_tiefe_kommt_nur_auf_verlangen_dazu():
    alle = list(FISHEYE) + list(TIEFE)
    assert waehle_quellen(alle) == FISHEYE
    assert waehle_quellen(alle, tiefe=True) == FISHEYE + TIEFE


# --------------------------------------------------------------- Daten


def test_bilder_landen_als_dateien_mit_index(tmp_path):
    recorder = _recorder(tmp_path)
    mitschnitt = Bildmitschnitt(TrockeneBildquelle(FISHEYE[:2]), recorder, hz=50.0)
    mitschnitt.start()
    assert _laufe_bis(mitschnitt, 3), mitschnitt.zaehler()
    mitschnitt.stop()

    zeilen = _index(recorder)
    assert len(zeilen) >= 6
    for zeile in zeilen:
        assert (recorder.dir / "kamera" / zeile["datei"]).exists()
    assert mitschnitt.zaehler()["fehler"] == 0


def test_tiefenbilder_kommen_byte_fuer_byte_an(tmp_path):
    """Die Kernaussage der Aufnahme.

    `api/perception.py::to_png_bytes()` normiert Tiefe fuer die ANZEIGE auf
    8 Bit. Ginge der Mitschnitt darueber, waere jeder Millimeterwert
    unwiederbringlich verloren — und zwar unauffaellig: die Bilder saehen
    richtig aus.
    """
    recorder = _recorder(tmp_path)
    quelle = TrockeneBildquelle(TIEFE[:1])
    erwartet = quelle.bilder()[0].shot.image.data

    mitschnitt = Bildmitschnitt(TrockeneBildquelle(TIEFE[:1]), recorder, hz=50.0)
    mitschnitt.start()
    assert _laufe_bis(mitschnitt, 1), mitschnitt.zaehler()
    mitschnitt.stop()

    datei = recorder.dir / "kamera" / _index(recorder)[0]["datei"]
    roh = datei.read_bytes()
    assert datei.suffix == ".raw"
    assert len(roh) == len(erwartet)
    werte = struct.unpack(f"<{len(roh) // 2}H", roh)
    assert max(werte) > 1000, "Tiefe ist flach — vermutlich auf 8 Bit normiert"
    assert max(werte) > 255, "Werte passen in ein Byte — Aufloesung ist weg"


def test_jede_zeile_traegt_roboterzeit_und_pose(tmp_path):
    """Ohne beides ist ein Bild nicht in den Fahrtweg einzuhaengen —
    und genau dafuer nehmen wir es auf."""
    recorder = _recorder(tmp_path)
    mitschnitt = Bildmitschnitt(TrockeneBildquelle(FISHEYE[:1]), recorder, hz=50.0)
    mitschnitt.start()
    assert _laufe_bis(mitschnitt, 2), mitschnitt.zaehler()
    mitschnitt.stop()

    zeilen = _index(recorder)
    for zeile in zeilen:
        assert zeile["t_robot"] > 0
        assert zeile["pose"] is not None and len(zeile["pose"]) == 7
    # Die Pose wird je Aufnahme neu gelesen, nicht einmal beim Start gemerkt.
    assert zeilen[0]["pose"][0] != zeilen[-1]["pose"][0]


def test_das_quellenblatt_steht_einmal_da(tmp_path):
    """Intrinsik, Extrinsik und Tiefenskala aendern sich nicht — sie gehoeren
    nicht in 18000 Indexzeilen."""
    recorder = _recorder(tmp_path)
    mitschnitt = Bildmitschnitt(TrockeneBildquelle(TIEFE[:1]), recorder, hz=50.0)
    mitschnitt.start()
    assert _laufe_bis(mitschnitt, 3), mitschnitt.zaehler()
    mitschnitt.stop()

    blatt = json.loads(
        (recorder.dir / "kamera" / "quellen.json").read_text(encoding="utf-8")
    )
    assert len(blatt) == 1
    eintrag = blatt[0]
    assert eintrag["tiefenskala"] == 1000.0
    assert eintrag["intrinsik"]["fx"] > 0
    assert eintrag["rahmenbaum"], "ohne Rahmenbaum keine Extrinsik"
    assert "t_robot" not in eintrag, "das Blatt ist konstant, nicht je Aufnahme"

    # Kein Feld des Blatts wiederholt sich in jeder Indexzeile.
    assert "intrinsik" not in _index(recorder)[0]


def test_graustufenbilder_haben_keine_erfundene_tiefenskala(tmp_path):
    """0.0 heisst beim Spot „nicht gesetzt". Als Zahl mittelte sie sich
    durch jede spaetere Rechnung — dieselbe Regel wie bei ground_mu_est."""
    recorder = _recorder(tmp_path)
    mitschnitt = Bildmitschnitt(TrockeneBildquelle(FISHEYE[:1]), recorder, hz=50.0)
    mitschnitt.start()
    assert _laufe_bis(mitschnitt, 1), mitschnitt.zaehler()
    mitschnitt.stop()

    blatt = json.loads(
        (recorder.dir / "kamera" / "quellen.json").read_text(encoding="utf-8")
    )
    assert blatt[0]["tiefenskala"] is None


# --------------------------------------------------------------- Ausfaelle


class KaputteQuelle:
    def bilder(self):
        raise ConnectionError("WLAN weg")


def test_ein_ausfall_wird_gezaehlt_und_nicht_geworfen(tmp_path):
    """Der Mitschnitt laeuft im Hintergrund einer Messfahrt. Wirft er, ist die
    Fahrt hin — verschluckt er, merkt es niemand, bis der Roboter weg ist."""
    recorder = _recorder(tmp_path)
    mitschnitt = Bildmitschnitt(KaputteQuelle(), recorder, hz=50.0)
    mitschnitt.start()
    ende = time.monotonic() + 10.0
    while time.monotonic() < ende and mitschnitt.zaehler()["fehler"] < 2:
        time.sleep(0.02)
    mitschnitt.stop()

    stand = mitschnitt.zaehler()
    assert stand["fehler"] >= 2
    assert stand["bilder"] == 0
    assert "WLAN weg" in stand["letzter_fehler"]


class EineKameraKaputt:
    """Vier heile Antworten und eine, die beim Ablegen scheitert."""

    def __init__(self):
        self._echt = TrockeneBildquelle(FISHEYE[:2])

    def bilder(self):
        antworten = self._echt.bilder()
        return [antworten[0], object()]


def test_eine_kaputte_kamera_kostet_nicht_die_anderen(tmp_path):
    recorder = _recorder(tmp_path)
    mitschnitt = Bildmitschnitt(EineKameraKaputt(), recorder, hz=50.0)
    mitschnitt.start()
    assert _laufe_bis(mitschnitt, 3), mitschnitt.zaehler()
    mitschnitt.stop()

    stand = mitschnitt.zaehler()
    assert stand["bilder"] >= 3, "die heile Kamera haette schreiben muessen"
    assert stand["fehler"] >= 3, "die kaputte haette auffallen muessen"


def test_der_zaehler_meldet_die_erreichte_rate(tmp_path):
    """Bricht der Bildtakt unter WLAN-Last ein, muss man das WAEHREND der
    Fahrt sehen — nachher ist es eine Feststellung ohne Handlungsmoeglichkeit."""
    recorder = _recorder(tmp_path)
    mitschnitt = Bildmitschnitt(TrockeneBildquelle(FISHEYE[:1]), recorder, hz=20.0)
    mitschnitt.start()
    assert _laufe_bis(mitschnitt, 5), mitschnitt.zaehler()
    mitschnitt.stop()

    stand = mitschnitt.zaehler()
    assert stand["hz_soll"] == 20.0
    assert stand["hz_ist"] is not None and stand["hz_ist"] > 0


# --------------------------------------------------------------- Abgrenzung


def test_der_dauerstrom_fasst_bilder_json_nicht_an(tmp_path):
    """`RunRecorder.image()` schreibt `bilder.json` bei jedem Bild komplett neu
    und legt ein Ereignis an — quadratisch in der Bildzahl. Und `bilder/` ist
    das Verzeichnis, das `gui/watcher.py` bei JEDEM Takt globbt.

    Beides traegt eine Handvoll Schnappschuesse, keinen Dauerstrom.
    """
    recorder = _recorder(tmp_path)
    mitschnitt = Bildmitschnitt(TrockeneBildquelle(FISHEYE[:2]), recorder, hz=50.0)
    mitschnitt.start()
    assert _laufe_bis(mitschnitt, 4), mitschnitt.zaehler()
    mitschnitt.stop()

    assert list((recorder.dir / "bilder").iterdir()) == []
    ereignisse = (recorder.dir / "ereignisse.jsonl")
    text = ereignisse.read_text(encoding="utf-8") if ereignisse.exists() else ""
    assert '"art": "bild"' not in text


def test_ohne_bilder_entsteht_kein_kamera_verzeichnis(tmp_path):
    """Ein leeres `kamera/` in jedem Schuelerlauf saehe aus, als waere eine
    Aufnahme misslungen."""
    recorder = _recorder(tmp_path)
    recorder.sample({"battery": 50.0})
    assert not (recorder.dir / "kamera").exists()
