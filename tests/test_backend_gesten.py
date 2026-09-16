"""Handgesten: MediaPipe-Handflaeche und -Handpose aus dem OpenCV-Zoo, ueber cv2.dnn.

Gemessen am 16.09.2026 ueber 510 gespeicherte Panoramen (ohne absichtliche Gesten):
auf dem GANZEN Panorama (192 px Eingabe) und auf drei Kacheln fand die Handpose
KEINE einzige Hand; auf dem Ausschnitt um den Oberkoerper aus der Koerper-Pose
fand sie welche -- sitzend nah 23 von 40 Takten, stehend auf 2-3 m mit haengenden
Armen 3 von 120. Deshalb liest der Gestenleser die Hand nur beim GEFOLGTEN Koerper,
im Rumpf-Ausschnitt, und eine Geste muss gehalten werden.
"""

from pathlib import Path

import numpy as np
import pytest

from spotlab.backends.real import gesten
from spotlab.errors import SpotlabError

# ------------------------------------------------------------------ Modelle


def test_fehlende_modelle_sagen_wo_sie_herkommen(monkeypatch, tmp_path):
    monkeypatch.setattr(gesten, "MODELL_ORDNER", tmp_path / "leer")
    with pytest.raises(SpotlabError) as fehler:
        gesten.modellpfade(umgebung={})
    text = str(fehler.value)
    assert gesten.BEZUGSQUELLE in text
    assert gesten.MODELL_HANDFLAECHE in text and gesten.MODELL_HANDPOSE in text


def test_der_standardordner_wird_durchsucht(monkeypatch, tmp_path):
    for name in (gesten.MODELL_HANDFLAECHE, gesten.MODELL_HANDPOSE):
        (tmp_path / name).write_bytes(b"x")
    monkeypatch.setattr(gesten, "MODELL_ORDNER", tmp_path)
    handflaeche, handpose = gesten.modellpfade(umgebung={})
    assert handflaeche == tmp_path / gesten.MODELL_HANDFLAECHE
    assert handpose == tmp_path / gesten.MODELL_HANDPOSE


def test_die_umgebung_nennt_einen_anderen_ordner(monkeypatch, tmp_path):
    monkeypatch.setattr(gesten, "MODELL_ORDNER", tmp_path / "leer")
    anderswo = tmp_path / "anderswo"
    anderswo.mkdir()
    for name in (gesten.MODELL_HANDFLAECHE, gesten.MODELL_HANDPOSE):
        (anderswo / name).write_bytes(b"x")
    handflaeche, _ = gesten.modellpfade(umgebung={gesten.ENV_ORDNER: str(anderswo)})
    assert handflaeche == anderswo / gesten.MODELL_HANDFLAECHE


# ------------------------------------------------------- Die Gestenregel


def _hand(finger_offen=(True, True, True, True), daumen="hoch"):
    """21 Landmarken in Bildkoordinaten (y nach unten), Handgelenk bei (100, 200),
    Handflaeche ~40 px. Gestreckte Finger zeigen nach oben, gebeugte enden nahe der
    Handflaeche. `daumen`: "hoch" (gestreckt, Spitze oben), "runter", "angelegt"."""
    lm = np.zeros((21, 3))
    lm[0] = (100.0, 200.0, 0.0)
    for finger, (mcp_x, offen) in enumerate(zip((85.0, 95.0, 105.0, 115.0), finger_offen)):
        basis = 5 + 4 * finger
        lm[basis] = (mcp_x, 160.0, 0.0)
        lm[basis + 1] = (mcp_x, 140.0, 0.0)
        if offen:
            lm[basis + 2] = (mcp_x, 125.0, 0.0)
            lm[basis + 3] = (mcp_x, 110.0, 0.0)
        else:
            lm[basis + 2] = (mcp_x, 155.0, 0.0)
            lm[basis + 3] = (mcp_x, 172.0, 0.0)
    lm[1] = (80.0, 190.0, 0.0)
    lm[2] = (70.0, 175.0, 0.0)
    if daumen == "hoch":
        lm[3] = (66.0, 160.0, 0.0)
        lm[4] = (62.0, 143.0, 0.0)
    elif daumen == "runter":
        lm[3] = (66.0, 190.0, 0.0)
        lm[4] = (62.0, 207.0, 0.0)
    else:
        lm[3] = (78.0, 172.0, 0.0)
        lm[4] = (86.0, 170.0, 0.0)
    return lm


def test_die_offene_hand_heisst_halt():
    assert gesten.geste_aus_landmarken(_hand()) == "halt"
    assert gesten.geste_aus_landmarken(_hand(daumen="angelegt")) == "halt", "der Daumen ist egal"


def test_der_daumen_hoch_heisst_weiter():
    assert gesten.geste_aus_landmarken(_hand((False, False, False, False), daumen="hoch")) == "weiter"


def test_die_faust_und_der_daumen_nach_unten_sind_keine_geste():
    assert gesten.geste_aus_landmarken(_hand((False, False, False, False), daumen="angelegt")) is None
    assert gesten.geste_aus_landmarken(_hand((False, False, False, False), daumen="runter")) is None


def test_ein_zeigefinger_ist_keine_geste():
    assert gesten.geste_aus_landmarken(_hand((True, False, False, False), daumen="angelegt")) is None


def test_eine_haengende_oder_liegende_offene_hand_ist_kein_halt():
    """Gemessen ueber die 31 natuerlichen Haende der Probe: alle mit Fingerspitzen
    UNTER dem Handgelenk (aufrecht -0.3 bis -2.75 Handflaechen) oder knapp darueber
    (+0.30, die Hand auf dem Tablet). Fuenf davon hatten alle vier Finger gestreckt --
    ein Halt daraus waere erfunden."""
    haengend = _hand()
    haengend[:, 1] = 400.0 - haengend[:, 1]          # kopfueber: Spitzen unter dem Gelenk
    assert gesten.geste_aus_landmarken(haengend) is None
    liegend = _hand()
    liegend[5:, 1] = 200.0 - 0.3 * 40.0              # die Spitzen nur 0.3 Handflaechen ueber dem Gelenk
    liegend[:5, 1] = 200.0
    assert gesten.geste_aus_landmarken(liegend) is None


def test_der_daumen_muss_nach_oben_zeigen_nicht_nur_abstehen():
    """Bei haengendem Arm steht der Daumen ab (lang 1.4-2.0), zeigt aber nach unten
    (oben -0.3 bis -1.0): das ist keine Geste."""
    lm = _hand((False, False, False, False), daumen="hoch")
    lm[3] = (66.0, 190.0, 0.0)
    lm[4] = (58.0, 200.0, 0.0)                       # lang, aber waagrecht bis leicht abwaerts
    assert gesten.geste_aus_landmarken(lm) is None


def test_die_regel_haengt_nicht_an_der_bildgroesse():
    """Dieselbe Hand doppelt so gross und verschoben: dasselbe Urteil."""
    gross = _hand((False, False, False, False), daumen="hoch") * 2.0 + (300.0, 50.0, 0.0)
    assert gesten.geste_aus_landmarken(gross) == "weiter"
    assert gesten.geste_aus_landmarken(_hand() * 0.4) == "halt"


# ---------------------------------------------------------- Entprellung


def test_eine_geste_zaehlt_erst_wenn_sie_gehalten_wird():
    e = gesten.Entprellung(takte=3)
    assert e.naechste("halt") is None
    assert e.naechste("halt") is None
    assert e.naechste("halt") == "halt"


def test_eine_gehaltene_geste_wird_nur_einmal_gemeldet():
    e = gesten.Entprellung(takte=3)
    for _ in range(3):
        e.naechste("halt")
    assert e.naechste("halt") is None
    assert e.naechste("halt") is None


def test_ein_aussetzer_oder_ein_wechsel_setzt_die_zaehlung_zurueck():
    e = gesten.Entprellung(takte=3)
    e.naechste("halt")
    e.naechste("halt")
    assert e.naechste(None) is None
    assert e.naechste("halt") is None, "von vorn"
    e.naechste("halt")
    assert e.naechste("weiter") is None, "ein Wechsel zaehlt fuer die neue Geste als erster Takt"
    e.naechste("weiter")
    assert e.naechste("weiter") == "weiter"


def test_nach_einem_aussetzer_darf_dieselbe_geste_wieder_melden():
    e = gesten.Entprellung(takte=2)
    e.naechste("halt")
    assert e.naechste("halt") == "halt"
    e.naechste(None)
    e.naechste("halt")
    assert e.naechste("halt") == "halt"


# ------------------------------------------------- Der Rumpf-Ausschnitt


def _koerper(schulter=(600.0, 250.0), huefte=(600.0, 450.0), schulterbreite=100.0,
             kasten=(500.0, 100.0, 700.0, 700.0)):
    from spotlab.backends.real.koerper import Koerper

    return Koerper(huefte=huefte, schulter=schulter, conf=0.9, kasten=kasten,
                   schulterbreite=schulterbreite)


def test_der_ausschnitt_ist_ein_quadrat_um_die_brust():
    x0, y0, seite = gesten.rumpf_ausschnitt(_koerper(), breite=1239, hoehe=782)
    assert seite == 300, "dreimal die Schulterbreite"
    assert (x0 + seite / 2, y0 + seite / 2) == (600.0, 350.0), "zwischen Schultern und Hueften"


def test_ohne_huefte_liegt_die_brust_unter_den_schultern():
    x0, y0, seite = gesten.rumpf_ausschnitt(_koerper(huefte=None), breite=1239, hoehe=782)
    assert seite == 300
    assert x0 + seite / 2 == 600.0 and y0 + seite / 2 > 250.0


def test_der_ausschnitt_bleibt_im_bild_und_hat_eine_mindestgroesse():
    x0, y0, seite = gesten.rumpf_ausschnitt(_koerper(schulter=(20.0, 30.0), huefte=(20.0, 80.0),
                                                     schulterbreite=20.0), breite=1239, hoehe=782)
    assert (x0, y0) == (0, 0) and seite == gesten.MINDEST_AUSSCHNITT_PX


def test_ohne_schulter_gibt_es_keinen_ausschnitt():
    assert gesten.rumpf_ausschnitt(_koerper(schulter=None), breite=1239, hoehe=782) is None


def test_ohne_schulterbreite_hilft_der_kasten():
    """Aeltere Koerper ohne `schulterbreite`: der Kasten ueber alle Punkte ist ~1.5x so breit."""
    x0, y0, seite = gesten.rumpf_ausschnitt(_koerper(schulterbreite=None, kasten=(450.0, 100.0, 750.0, 700.0)),
                                            breite=1239, hoehe=782)
    assert seite == 600


# ------------------------------------------------------- Der Handerkenner


def _handflaeche_bei(x, y, score=0.9):
    """Eine Zeile des Handflaechen-Erkenners: Kasten, 7 Landmarken, Punktzahl."""
    return np.array([x - 20, y - 20, x + 20, y + 20] + [x, y] * 7 + [score], dtype=np.float32)


def _handpose_vorgabe(conf=0.95):
    def handpose(bgr, handflaeche):
        x, y = float(handflaeche[4]), float(handflaeche[5])
        lm = _hand() + (x - 100.0, y - 200.0, 0.0)
        return np.r_[np.array([x - 30, y - 60, x + 30, y + 10]), lm.reshape(-1), lm.reshape(-1), 0.9, conf]

    return handpose


def test_der_erkenner_gibt_haende_in_panorama_koordinaten():
    erkenner = gesten.Handerkenner(handflaeche=lambda bgr: [_handflaeche_bei(50.0, 60.0)],
                                   handpose=_handpose_vorgabe())
    feld = np.zeros((782, 1239, 3), dtype=np.uint8)
    haende = erkenner.finde(feld, ausschnitt=(400, 200, 300))
    assert len(haende) == 1
    hand = haende[0]
    assert hand.conf == pytest.approx(0.95)
    assert tuple(hand.landmarken[0, :2]) == (450.0, 260.0), "Handgelenk um den Ausschnitt versetzt"
    assert hand.kasten[0] == pytest.approx(420.0)
    assert erkenner.suchen == 1


def test_der_erkenner_sieht_nur_den_ausschnitt():
    gesehen = []

    def handflaeche(bgr):
        gesehen.append(bgr.shape)
        return []

    erkenner = gesten.Handerkenner(handflaeche=handflaeche, handpose=_handpose_vorgabe())
    feld = np.zeros((782, 1239, 3), dtype=np.uint8)
    assert erkenner.finde(feld, ausschnitt=(900, 500, 400)) == []
    assert gesehen == [(282, 339, 3)], "am Rand beschnitten, nie ausserhalb"
    assert erkenner.finde(feld) == []
    assert gesehen[-1] == (782, 1239, 3)


def test_eine_handflaeche_ohne_pose_ist_keine_hand():
    erkenner = gesten.Handerkenner(handflaeche=lambda bgr: [_handflaeche_bei(50.0, 60.0)],
                                   handpose=lambda bgr, p: None)
    assert erkenner.finde(np.zeros((100, 100, 3), dtype=np.uint8)) == []


def test_ein_graues_feld_wird_dreikanalig_gereicht():
    formen = []

    def handflaeche(bgr):
        formen.append(bgr.shape)
        return []

    gesten.Handerkenner(handflaeche=handflaeche, handpose=_handpose_vorgabe()).finde(
        np.zeros((50, 80), dtype=np.uint8))
    assert formen == [(50, 80, 3)]


def test_geste_der_hand_nimmt_die_sicherste():
    schwach = gesten.Hand(_hand((False, False, False, False), daumen="hoch"), 0.6, (0, 0, 1, 1))
    stark = gesten.Hand(_hand(), 0.9, (0, 0, 1, 1))
    assert gesten.geste_der_haende([schwach, stark]) == "halt"
    assert gesten.geste_der_haende([]) is None


# ------------------------------------------------------ Der echte Erkenner


@pytest.mark.skipif(not all((gesten.MODELL_ORDNER / n).is_file()
                            for n in (gesten.MODELL_HANDFLAECHE, gesten.MODELL_HANDPOSE)),
                    reason="Handmodelle nicht abgelegt")
def test_der_echte_erkenner_laeuft_auf_der_aufzeichnung_ohne_hand():
    """Der leere Gang vom 12.08.2026: keine Hand, kein Fehler -- die Verkettung
    Handflaeche -> Handpose auf den echten Dateien."""
    from PIL import Image

    daten = Path(__file__).parent / "daten" / "blick_real_20260812"
    bild = np.asarray(Image.open(daten / "takt90_frontleft.jpg").convert("L"))
    erkenner = gesten.Handerkenner()
    assert erkenner.finde(bild) == []
    assert erkenner.finde(bild, ausschnitt=(100, 100, 300)) == []
    assert erkenner.suchen == 2
