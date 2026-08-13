"""Die Gangkennlinie — Datengrundlage des Sim-Backends.

Der wichtigste Test hier ist der letzte: eine Trockenprobe darf NIE in die
Kalibrierdaten laufen. Alles andere sind Rechenfehler; das waere eine Erfindung,
die aussieht wie eine Messung.
"""

import json
import math

import pytest

from spotlab.kalibrierung import gang


def _satz(t, kontakte, winkel=0.0, fuss_z=-0.52):
    """Eine Abtastung mit vier Fuessen und zwoelf Gelenken."""
    namen = [f"{b}.{g}" for b in ("fl", "fr", "hl", "hr") for g in ("hx", "hy", "kn")]
    # Fusspositionen: vorne x>0, links y>0 -- daraus leitet sich die Zuordnung ab
    lagen = [(0.33, 0.17), (0.33, -0.17), (-0.33, 0.17), (-0.33, -0.17)]
    return {
        "t_robot": t,
        "feet": list(kontakte),
        "feet_detail": [
            {"pos": [x, y, fuss_z], "kontakt": k}
            for (x, y), k in zip(lagen, kontakte)
        ],
        "joints": {n: {"position": winkel, "velocity": 0.0, "load": 0.0} for n in namen},
    }


def _gang(zyklen, punkte_je_zyklus=20, dauer=1.0):
    """Ein sauberer Zweitakt: Bein 0 setzt am Zyklusanfang auf."""
    saetze = []
    for z in range(zyklen):
        for k in range(punkte_je_zyklus):
            phase = k / punkte_je_zyklus
            t = (z + phase) * dauer
            steht = phase < 0.6
            saetze.append(
                _satz(t, [steht, not steht, not steht, steht],
                      winkel=math.sin(2 * math.pi * phase))
            )
    return saetze


# --------------------------------------------------------------- Beinzuordnung


def test_die_beinzuordnung_wird_abgeleitet_nicht_geraten():
    """Welcher Eintrag in `feet` welches Bein ist, steht nicht in der Nachricht
    -- aus der mittleren Fussposition folgt es aber eindeutig."""
    assert gang.bein_zuordnung(_gang(2)) == ["fl", "fr", "hl", "hr"]


def test_ohne_fussdetails_gibt_es_keine_zuordnung():
    """None heisst „nicht bestimmbar", nicht „Standardfall"."""
    ohne = [{k: v for k, v in s.items() if k != "feet_detail"} for s in _gang(2)]
    assert gang.bein_zuordnung(ohne) is None


def test_eine_vertauschte_reihenfolge_wird_erkannt():
    saetze = _gang(2)
    for s in saetze:                      # Fuesse 0 und 2 tauschen
        s["feet_detail"][0], s["feet_detail"][2] = s["feet_detail"][2], s["feet_detail"][0]
    assert gang.bein_zuordnung(saetze) == ["hl", "fr", "fl", "hr"]


# --------------------------------------------------------------- Zyklen


def test_zyklen_laufen_von_aufsetzen_zu_aufsetzen():
    """`_gang(n)` liefert n-2 vollstaendige Zyklen: der Fuss steht schon in der
    ersten Abtastung, dort gibt es also keine Flanke, und der letzte Zyklus hat
    keinen Abschluss."""
    grenzen = gang.zyklen_grenzen(_gang(4), bein=0)
    assert len(grenzen) == 2, grenzen
    for von, bis in grenzen:
        assert bis > von
    assert len(gang.zyklen_grenzen(_gang(7))) == 5


def test_ein_stehender_roboter_hat_keine_zyklen():
    steht = [_satz(i / 10, [True] * 4) for i in range(100)]
    assert gang.zyklen_grenzen(steht) == []


def test_zu_wenige_zyklen_ergeben_keine_kennlinie():
    """Ein Mittelwert aus zwei Zyklen behauptet mehr, als er weiss."""
    mittel, streuung, zyklen = gang.mittlerer_zyklus(_gang(2))
    assert mittel == {} and streuung == {}
    assert zyklen < gang.MINDESTZYKLEN


# --------------------------------------------------------------- Mittelung


def test_der_mittlere_zyklus_hat_die_form_der_einzelnen():
    mittel, streuung, zyklen = gang.mittlerer_zyklus(_gang(7))
    assert zyklen == 5
    bahn = mittel["fl.hy"]
    assert len(bahn) == gang.PHASENPUNKTE
    # Alle Zyklen sind gleich -- die Streuung muss verschwinden.
    assert max(streuung["fl.hy"]) < 1e-9
    # und die Form ist der Sinus, mit dem gebaut wurde
    for k, wert in enumerate(bahn):
        assert wert == pytest.approx(math.sin(2 * math.pi * k / gang.PHASENPUNKTE), abs=0.06)


def test_die_streuung_zeigt_uneinheitliche_zyklen():
    saetze = _gang(6)
    for s in saetze[40:60]:                   # einen Zyklus verbiegen
        s["joints"]["fl.hy"]["position"] += 0.5
    _, streuung, _ = gang.mittlerer_zyklus(saetze)
    assert max(streuung["fl.hy"]) > 0.1
    assert max(streuung["fr.hy"]) < 1e-9, "nur das verbogene Gelenk darf streuen"


def test_interpolation_trifft_die_stuetzstellen():
    phasen = [0.0, 0.25, 0.5, 0.75, 1.0]
    werte = [0.0, 1.0, 2.0, 3.0, 4.0]
    raster = gang._interpoliere(phasen, werte, 4)
    assert raster == pytest.approx([0.0, 1.0, 2.0, 3.0])


def test_die_phase_eins_zaehlt_nicht_doppelt():
    """Der letzte Punkt eines Zyklus IST der erste des naechsten."""
    raster = gang._interpoliere([0.0, 1.0], [0.0, 10.0], 5)
    assert raster[0] == 0.0
    assert max(raster) < 10.0


# --------------------------------------------------------------- Standhoehe


def test_die_standhoehe_ist_der_rumpf_ueber_den_fuessen():
    """NICHT odom-z. Am 12.08.2026 standen dort 0.265 m, waehrend der Rumpf
    0.514 m ueber den Fuessen stand -- odom-z misst gegen den Ursprung des
    odom-Frames, also gegen den Ort beim Hochfahren."""
    saetze = [_satz(i / 10, [True] * 4, fuss_z=-0.514) for i in range(20)]
    for s in saetze:
        s["z"] = 0.265                    # was in zustand.jsonl steht
    assert gang.standhoehe(saetze) == pytest.approx(0.514)


def test_fuesse_ohne_kontakt_zaehlen_nicht_zur_standhoehe():
    saetze = [_satz(i / 10, [True, True, True, False], fuss_z=-0.5) for i in range(20)]
    for s in saetze:
        s["feet_detail"][3]["pos"][2] = -0.2      # angehobener Fuss
    assert gang.standhoehe(saetze) == pytest.approx(0.5)


def test_duty_zaehlt_je_bein():
    saetze = _gang(4)
    werte = gang.duty(saetze)
    assert len(werte) == 4
    assert werte[0] == pytest.approx(0.6, abs=0.05)
    assert werte[1] == pytest.approx(0.4, abs=0.05)


# --------------------------------------------------------------- Die Sperre


def test_eine_trockenprobe_kommt_nicht_in_die_kennlinie(tmp_path):
    """Der wichtigste Test dieser Datei.

    Bis zum 12.08.2026 hiessen Probe und Messfahrt beide „beobachter", und die
    Probe fiel nur heraus, weil `DryRunBackend` alle Fuesse am Boden laesst.
    Sobald das Sim-Backend die Beine bewegt, faellt sie nicht mehr heraus --
    dann stuenden erfundene Gelenkwerte in den Kalibrierdaten und saehen aus
    wie eine Messung.
    """
    from spotlab.beobachtung.session import Beobachtung
    from spotlab.kalibrierung.aus_laeufen import sammle

    with Beobachtung.trocken(runs_dir=tmp_path, bilder_hz=0) as b:
        with b.messfenster("B2-1", hz=50.0, ziel_m_s="0.12"):
            pass

    stuetzstellen, bericht = sammle(tmp_path)
    assert stuetzstellen == []
    assert any("übersprungen" in z for z in bericht), bericht
    assert any("trocken" in z for z in bericht), bericht


def test_ein_unbekannter_backend_name_wird_uebersprungen(tmp_path):
    """Die Liste ist eine ERLAUBNIS, keine Sperrliste -- sonst liesse ein
    neuer Backend-Name kuenftig alles durch."""
    from spotlab.kalibrierung.aus_laeufen import sammle
    from spotlab.record.run import RunRecorder

    rec = RunRecorder(tmp_path, None, backend="irgendwas-neues")
    rec.sample({"t_robot": 1.0, "feet": [True] * 4})
    rec.finish("ok")

    stuetzstellen, bericht = sammle(tmp_path)
    assert stuetzstellen == []
    assert any("irgendwas-neues" in z for z in bericht), bericht


def test_die_kennlinie_traegt_ihre_herkunft(tmp_path):
    """Ohne Lauf-ID und Zyklenzahl ist eine Kalibrierzahl nicht nachprüfbar."""
    ziel = tmp_path / "gang.json"
    stelle = gang.Stuetzstelle(
        tempo_m_s=0.21, drehrate_rad_s=0.0, absicht={"ziel_m_s": "0.21"},
        zyklusdauer_s=1.67, zyklusdauer_streuung_s=0.05, duty=[0.8] * 4,
        phasen=[0.0, 0.5, 0.25, 0.75], muster="viertakt", hoehe_m=0.514,
        gelenke={"fl.hy": [0.0] * gang.PHASENPUNKTE},
        gelenke_streuung={"fl.hy": [0.0] * gang.PHASENPUNKTE},
        zyklen=15, herkunft={"lauf": "20260812T112135Z_x", "fenster": "B2-4"},
    )
    gang.schreibe([stelle], ziel, bemerkung="Probe")
    inhalt = json.loads(ziel.read_text(encoding="utf-8"))
    assert inhalt["phasenpunkte"] == gang.PHASENPUNKTE
    assert "keine Physik" in inhalt["hinweis"]
    eine = inhalt["stuetzstellen"][0]
    assert eine["herkunft"]["lauf"] == "20260812T112135Z_x"
    assert eine["zyklen"] == 15
    assert eine["tempo_m_s"] == 0.21


def test_ohne_datei_wirft_lade_mit_klarer_ansage(tmp_path):
    with pytest.raises(FileNotFoundError, match="Messfahrten"):
        gang.lade(tmp_path / "gibtsnicht.json")


# --------------------------------------------------------------- Verschmolzene Zyklen


def _gang_mit_verpasstem_aufsetzer(zyklen, punkte=20, dauer=1.0, bei=2):
    """Wie `_gang`, aber im Zyklus `bei` wird EIN Aufsetzer nicht erkannt.

    Genau das tut die Kontakterkennung am echten Roboter gelegentlich: bei B2-7
    lagen 26 Zyklen zwischen 0.65 und 0.81 s und vier bei 1.17 bis 1.54 --
    glatt das Doppelte.
    """
    saetze = _gang(zyklen, punkte, dauer)
    # Die GANZE Standphase unterdruecken, nicht nur ihren Anfang: sonst
    # verschiebt sich der Aufsetzer bloss, statt auszufallen. Ohne die Flanke
    # kommt der naechste Aufsetzer erst einen Zyklus spaeter -- der Zyklus
    # davor ist dann doppelt so lang.
    beginn = bei * punkte
    for s in saetze[beginn:beginn + punkte]:
        s["feet"][0] = False
        s["feet_detail"][0]["kontakt"] = False
    return saetze


def test_ein_verschmolzener_zyklus_wird_verworfen():
    saetze = _gang_mit_verpasstem_aufsetzer(8)
    roh = gang.zyklen_grenzen(saetze)
    behalten, dauern, verworfen = gang.brauchbare_zyklen(saetze)
    assert verworfen >= 1, "der doppelt lange Zyklus haette auffallen muessen"
    assert len(behalten) == len(roh) - verworfen
    assert max(dauern) < 1.5 * min(dauern)


def test_ein_verschmolzener_zyklus_verfaelscht_die_bahn_nicht():
    """Der eigentliche Grund fuer die Aussortierung.

    Ein verschmolzener Zyklus wird auf dieselbe Phase 0..1 normiert wie ein
    echter und zieht zwei Schritte in den Platz von einem. Die gemittelte
    Gelenkbahn wird dadurch nicht ungenauer, sondern falsch.
    """
    sauber, _, _ = gang.mittlerer_zyklus(_gang(9))
    gestoert, _, _ = gang.mittlerer_zyklus(_gang_mit_verpasstem_aufsetzer(9))
    abweichung = max(
        abs(a - b) for a, b in zip(sauber["fl.hy"], gestoert["fl.hy"])
    )
    assert abweichung < 0.05, f"die Bahn weicht um {abweichung:.3f} ab"


def test_die_zahl_der_verworfenen_zyklen_steht_in_der_herkunft():
    """Sonst saehe eine gesaeuberte Kennlinie sauberer aus als die Messung."""
    _, _, verworfen = gang.brauchbare_zyklen(_gang_mit_verpasstem_aufsetzer(8))
    assert verworfen > 0


def test_ohne_stoerung_wird_nichts_verworfen():
    """Gegenprobe -- ein Filter, der immer zuschlaegt, ist kein Filter."""
    behalten, _, verworfen = gang.brauchbare_zyklen(_gang(8))
    assert verworfen == 0
    assert len(behalten) == 6


# --------------------------------------------------------------- Abschnitte


def _fahrt(zyklen, tempo, punkte=20, dauer=0.8, x0=0.0, t0=0.0):
    """Ein Gang mit echter Vorwaertsbewegung, damit `segmente` ein Tempo findet."""
    saetze = []
    for z in range(zyklen):
        for k in range(punkte):
            phase = k / punkte
            t = t0 + (z + phase) * dauer
            steht = phase < 0.6
            satz = _satz(t, [steht, not steht, not steht, steht],
                         winkel=math.sin(2 * math.pi * phase))
            satz["pose"] = [x0 + tempo * (t - t0), 0.0, 0.0]
            saetze.append(satz)
    return saetze


def test_ein_stetiger_gang_ergibt_abschnitte():
    stuecke = gang.segmente(_fahrt(14, tempo=0.3))
    assert len(stuecke) >= 2, stuecke
    for _, tempo, drehrate in stuecke:
        assert tempo == pytest.approx(0.3, abs=0.02)
        assert abs(drehrate) < 0.01


def test_jeder_abschnitt_traegt_sein_eigenes_tempo():
    """Der Fensterschnitt mittelt Anfahren und Anhalten mit -- ein Abschnitt
    nicht. Genau dafuer gibt es sie.

    Der schnelle Teil ist absichtlich LANG: ein Abschnitt, der genau ueber den
    Tempowechsel faellt, wird von der Stetigkeitspruefung verworfen (gemessen
    an dieser Attrappe: Haelften 0.365 gegen 0.500). Damit ein sauberer
    schneller Abschnitt entsteht, muss einer vollstaendig dahinter liegen.
    """
    langsam = _fahrt(7, tempo=0.10)
    ende = langsam[-1]
    schnell = _fahrt(14, tempo=0.50, x0=ende["pose"][0],
                     t0=ende["t_robot"] + 0.04)
    tempi = sorted(t for _, t, _ in gang.segmente(langsam + schnell))
    assert tempi, "gar keine Abschnitte"
    assert min(tempi) == pytest.approx(0.10, abs=0.02)
    assert max(tempi) == pytest.approx(0.50, abs=0.02)
    # Und nichts dazwischen: der Uebergang selbst ist keine Gangart.
    assert not [t for t in tempi if 0.15 < t < 0.45], tempi


def test_ein_beschleunigender_abschnitt_faellt_weg():
    """Eine gemittelte Gelenkbahn ueber eine Beschleunigung hinweg beschreibt
    keine Gangart -- derselbe Grund wie beim verschmolzenen Zyklus."""
    saetze = _fahrt(7, tempo=0.1)
    # Zweite Haelfte kraeftig beschleunigen
    mitte = len(saetze) // 2
    for i, s in enumerate(saetze[mitte:], start=1):
        s["pose"][0] = saetze[mitte - 1]["pose"][0] + 0.02 * i * i
    stetig = [t for _, t, _ in gang.segmente(saetze)]
    assert not any(t for t in stetig if t > 0.5), stetig


def test_ein_start_stopp_fenster_erzeugt_keine_langsame_gangart():
    """Der Fall vom 12.08.2026, B2-1 im Lauf 20260812T111801Z.

    Der Fensterschnitt war 0.054 m/s; die Abschnitte darin lagen zwischen 0.08
    und 0.77. Die alte Stuetzstelle behauptete eine langsame Gangart, die es
    nie gab -- und war der UNTERSTE Punkt der Kennlinie.
    """
    steht = [
        _satz(i * 0.04, [True] * 4) | {"pose": [0.0, 0.0, 0.0]}
        for i in range(150)
    ]
    laeuft = _fahrt(10, tempo=0.7, t0=steht[-1]["t_robot"] + 0.04)
    stuecke = gang.segmente(steht + laeuft)
    tempi = [t for _, t, _ in stuecke]
    assert tempi, "gar keine Abschnitte gefunden"
    # Kein Abschnitt darf ein langsames Gehen behaupten: der Roboter stand
    # entweder oder lief schnell.
    assert all(t > 0.3 for t in tempi), tempi


def test_die_herkunft_nennt_fenster_und_abschnitt(tmp_path):
    """Mehrere Stuetzstellen aus demselben Fenster sind KEINE unabhaengigen
    Messungen. Wer das nicht sieht, zaehlt sie als solche."""
    inhalt = json.loads(gang.DATEI.read_text(encoding="utf-8"))
    stellen = inhalt["stuetzstellen"]
    assert stellen
    for s in stellen:
        assert "fenster" in s["herkunft"]
        assert s["herkunft"]["abschnitt"] >= 1
        assert s["herkunft"]["abschnitt"] <= s["herkunft"]["abschnitte_im_fenster"]


def test_die_ausgelieferte_kennlinie_hat_keinen_anfahr_punkt():
    """Gegenprobe an den echten Daten: der unterste Punkt muss eine Gangart
    sein, kein Mittelwert aus Stehen und Rennen. Erkennbar an der Kadenz --
    0.054 m/s bei 0.75 s Zyklusdauer waere ein Widerspruch."""
    from spotlab.kalibrierung.modell import lade_modell

    modell = lade_modell()
    langsamste = min(modell.fahren, key=lambda s: s["tempo_m_s"])
    # Langsam gehen heisst LANGE Zyklen. Ein kurzer Zyklus bei kleinem Tempo
    # bedeutet Treten auf der Stelle.
    assert langsamste["zyklusdauer_s"] > 1.5, langsamste["herkunft"]
