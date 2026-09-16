"""Folgen: der Regler, die Finder und die Schranken -- alles ohne Roboter.

Ein Roboter, der von selbst einem Menschen hinterherlaeuft, ist ein anderer Fall
als einer, den jemand faehrt. Deshalb steht hier jede Schranke einzeln, und der
Regler ist eine reine Funktion.
"""

from types import SimpleNamespace

import pytest

from spotlab.backends.base import Capability
from spotlab.record.run import STOPP_DATEI
from spotlab.workshop import folgen
from spotlab.workshop.folgen import Ziel

# ------------------------------------------------------------------ Regler


def test_weit_weg_geht_er_vorwaerts():
    vx, wz = folgen.befehl(Ziel(0.0, 3.0))
    assert vx > 0.0 and wz == 0.0
    assert vx <= folgen.MAX_TEMPO_M_S, "das Tempo ist gedeckelt"


def test_im_wunschabstand_bleibt_er_stehen():
    assert folgen.befehl(Ziel(0.0, folgen.WUNSCH_ABSTAND_M)).__getitem__(0) == 0.0
    assert folgen.befehl(Ziel(0.0, folgen.WUNSCH_ABSTAND_M + folgen.TOLERANZ_M))[0] == 0.0


@pytest.mark.parametrize("abstand", [0.0, 0.5, 0.9, folgen.MIN_ABSTAND_M])
def test_naeher_als_der_mindestabstand_faehrt_er_nie(abstand):
    """Und rueckwaerts auch nicht: nach hinten sieht Spot nichts."""
    assert folgen.befehl(Ziel(0.0, abstand))[0] == 0.0


def test_seitlich_dreht_er_erst_und_geht_dann():
    vx, wz = folgen.befehl(Ziel(90.0, 4.0))
    assert vx == 0.0 and wz > 0.0, "erst die Nase hin"
    vx, _ = folgen.befehl(Ziel(10.0, 4.0))
    assert vx > 0.0


def test_die_drehrate_ist_gedeckelt():
    import math

    _, wz = folgen.befehl(Ziel(180.0, 4.0))
    assert wz == pytest.approx(math.radians(folgen.MAX_DREHRATE_GRAD))
    _, wz = folgen.befehl(Ziel(-180.0, 4.0))
    assert wz == pytest.approx(-math.radians(folgen.MAX_DREHRATE_GRAD))


# ------------------------------------------------------------------ Finder


class _Spot:
    def __init__(self, tags=(), leute=(), frei=5.0, pose=(0.0, 0.0, 0.0),
                 faehigkeiten=Capability.LOCOMOTION, kopfraum=None, kartenlage=None,
                 neigt=False, nick=0.0):
        self._tags, self._leute = list(tags), list(leute)
        self._frei, self._pose = frei, pose
        self._kartenlage, self._nick = kartenlage, nick
        self.kommandos = []
        self.backend = SimpleNamespace(
            capabilities=lambda: faehigkeiten,
            images=lambda quellen: kopfraum,
            neigt_beim_gehen=neigt,
        )

    def tags(self, id=None):
        return [t for t in self._tags if id is None or t.id == id]

    def people(self):
        return list(self._leute)

    def obstacles(self):
        return SimpleNamespace(free_distance=lambda x, y, grad: self._frei)

    @property
    def state(self):
        return SimpleNamespace(pose=self._pose, pitch=self._nick)

    def map_pose(self):
        return self._kartenlage

    def walk(self, **kw):
        self.kommandos.append(kw)

    def stop(self):
        self.kommandos.append("stop")


def _tag(nummer, peilung, abstand):
    return SimpleNamespace(id=nummer, bearing=peilung, distance=abstand)


def _person(nummer, peilung, abstand, sicher=0.9):
    return SimpleNamespace(entity_id=nummer, bearing=peilung, distance=abstand,
                           likelihood=sicher)


def test_der_tag_finder_nimmt_das_naechste_und_kann_eines_verlangen():
    spot = _Spot(tags=[_tag(3, 10.0, 2.0), _tag(5, -20.0, 4.0)])
    ziel = folgen.tag_finder()(spot)
    assert (ziel.bearing, ziel.distance, ziel.name) == (10.0, 2.0, "Tag 3")
    assert folgen.tag_finder(tag_id=5)(spot).name == "Tag 5"
    assert folgen.tag_finder(tag_id=9)(spot) is None


def test_ohne_tag_findet_er_nichts():
    assert folgen.tag_finder()(_Spot()) is None


def test_der_personen_finder_nimmt_die_naechste():
    spot = _Spot(leute=[_person(7, 5.0, 1.8)])
    ziel = folgen.personen_finder()(spot)
    assert (ziel.distance, ziel.name) == (1.8, "Person 7")
    assert folgen.personen_finder(mindestsicherheit=0.95)(spot) is None
    assert folgen.personen_finder()(_Spot()) is None


# --------------------------------------------------------------- Schranken


def test_das_hindernisgitter_haelt_ihn_vor_der_wand():
    assert folgen.frei_voraus(_Spot(frei=5.0))[0] is True
    darf, grund = folgen.frei_voraus(_Spot(frei=0.3))
    assert darf is False and "frei voraus" in grund


def test_ein_unlesbares_gitter_verbietet_die_fahrt():
    """Fail-closed: eine Schranke, die bei Stoerung durchwinkt, ist keine."""
    class _Kaputt(_Spot):
        def obstacles(self):
            raise RuntimeError("Dienst weg")

    darf, grund = folgen.frei_voraus(_Kaputt())
    assert darf is False and "nicht lesbar" in grund


def test_ohne_tiefenkameras_gibt_es_die_kopfraumschranke_nicht():
    assert folgen.kopfraum_frei(_Spot())[0] is True


def test_ein_ueberhang_haelt_ihn_an(monkeypatch):
    """Das Hindernisgitter ist eine BODENkarte -- eine Tischplatte steht nicht darin."""
    from spotlab.backends.real import tiefe

    monkeypatch.setattr(tiefe, "ueberhang_aus_bildern", lambda *a, **kw: "punkte")
    monkeypatch.setattr(tiefe, "kopfraum", lambda punkte: 0.72)
    spot = _Spot(faehigkeiten=Capability.DEPTH_CAMERAS, kopfraum=["bild"])
    darf, grund = folgen.kopfraum_frei(spot)
    assert darf is False and "0.72" in grund

    monkeypatch.setattr(tiefe, "kopfraum", lambda punkte: None)
    assert folgen.kopfraum_frei(spot)[0] is True


def test_ein_unlesbares_tiefenbild_verbietet_die_fahrt(monkeypatch):
    from spotlab.backends.real import tiefe

    def kaputt(*a, **kw):
        raise RuntimeError("keine Tiefenbilder")

    monkeypatch.setattr(tiefe, "ueberhang_aus_bildern", kaputt)
    spot = _Spot(faehigkeiten=Capability.DEPTH_CAMERAS, kopfraum=["bild"])
    darf, grund = folgen.kopfraum_frei(spot)
    assert darf is False and "nicht lesbar" in grund


def _raum_mit_zone():
    from spotlab.welt.raum import Kartenbezug, Raum, Sperrzone

    return Raum("test", "", (0.0, 0.0, 0.0),
                sperrzonen=(Sperrzone("glasfront", 2.0, 0.0, 1.0, 1.0, grund="Glas"),),
                karte=Kartenbezug("flur"))


def test_ohne_raum_oder_ohne_zonen_gibt_es_die_schranke_nicht():
    from spotlab.welt.raum import Raum

    assert folgen.zone_voraus(_Spot(), None)[0] is True
    assert folgen.zone_voraus(_Spot(), Raum("leer", "", (0.0, 0.0, 0.0)))[0] is True


def test_ohne_verortung_verbietet_die_zonenschranke_die_fahrt():
    darf, grund = folgen.zone_voraus(_Spot(kartenlage=None), _raum_mit_zone())
    assert darf is False and "verortet" in grund


def test_eine_zone_voraus_haelt_ihn_an():
    spot = _Spot(kartenlage=(0.0, 0.0, 0.0))
    darf, grund = folgen.zone_voraus(spot, _raum_mit_zone(), strecke=3.0)
    assert darf is False and "glasfront" in grund and "Glas" in grund, grund
    frei = _Spot(kartenlage=(0.0, 0.0, 180.0))       # von der Zone weg
    assert folgen.zone_voraus(frei, _raum_mit_zone(), strecke=3.0)[0] is True


# ---------------------------------------------------------------- Schleife


def _laeuft_takte(anzahl):
    zaehler = {"n": 0}

    def laeuft():
        zaehler["n"] += 1
        return zaehler["n"] <= anzahl

    return laeuft


def test_ohne_ziel_steht_er_sofort():
    """Derselbe Totmann-Gedanke wie im Fahrmodus -- nicht nach einer Frist."""
    spot = _Spot()
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3))
    assert not any(isinstance(k, dict) for k in spot.kommandos), "kein einziger Fahrbefehl"
    assert spot.kommandos[-1] == "stop"


def test_mit_ziel_faehrt_er_hin():
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)])
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten and all(k["vx"] > 0 for k in fahrten)
    assert all(k["stop"] is False for k in fahrten), "laufend lenken, nicht anhalten"
    assert spot.kommandos[-1] == "stop", "am Ende haelt er immer"


def test_eine_schranke_nimmt_ihm_das_vorwaerts_nicht_das_drehen():
    spot = _Spot(tags=[_tag(3, 30.0, 3.0)], frei=0.2)      # Wand voraus
    gemeldet = []
    folgen.folge(spot, folgen.tag_finder(), melde=gemeldet.append,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten and all(k["vx"] == 0.0 and k["wz"] != 0.0 for k in fahrten)
    assert any("Stehen geblieben" in m and "frei voraus" in m for m in gemeldet)


def test_der_grund_wird_nur_beim_wechsel_gemeldet():
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)], frei=0.2)
    gemeldet = []
    folgen.folge(spot, folgen.tag_finder(), melde=gemeldet.append,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(5))
    assert len([m for m in gemeldet if "Stehen geblieben" in m]) == 1


def test_ein_finder_der_wirft_beendet_den_lauf_nicht():
    def kaputt(spot):
        raise RuntimeError("Kamera weg")

    spot = _Spot()
    folgen.folge(spot, kaputt, melde=lambda _t: None, schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(2))
    assert spot.kommandos == ["stop"]


class _Aufzeichnung:
    """Der Schreiber des Laufs, so viel davon wie `folge()` benutzt."""

    def __init__(self):
        self.ereignisse = []

    def event(self, art, **daten):
        self.ereignisse.append((art, daten))


def _uhr(schritt=3.0):
    stand = {"t": 0.0}

    def jetzt():
        stand["t"] += schritt
        return stand["t"]

    return jetzt


def test_ein_nie_gesehenes_ziel_heisst_nicht_verloren():
    """Am 16.09.2026 stand Spot 28 Sekunden da, weil `personen_finder()` auf
    diesem Geraet nie etwas liefert. "Ziel verloren" waere dabei eine falsche
    Auskunft: verloren hat er nichts, er hatte nie eines."""
    gemeldet = []
    folgen.folge(_Spot(), lambda _s: None, melde=gemeldet.append, jetzt=_uhr(),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6))
    stille = [m for m in gemeldet if "kein Ziel" in m]
    assert stille, "er sagt, dass er nichts hat"
    assert not [m for m in gemeldet if "verloren" in m], "aber nicht 'verloren'"


def test_die_stille_wird_immer_wieder_gemeldet():
    """Einmal am Anfang genuegt nicht: nach einer halben Minute ist die Zeile
    weggescrollt, und ein stehender Spot sieht aus wie ein haengendes Programm."""
    gemeldet = []
    folgen.folge(_Spot(), lambda _s: None, melde=gemeldet.append,
                 jetzt=_uhr(folgen.STILLE_TAKT_S), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(12))
    stille = [m for m in gemeldet if "kein Ziel" in m]
    assert len(stille) >= 2, "sie wird wiederholt"
    assert any(m != stille[0] for m in stille[1:]), "und traegt die verstrichene Zeit"


def test_nach_einem_echten_verlust_heisst_es_verloren_und_die_rueckkehr_auch():
    plan = iter([Ziel(0.0, 3.0, "Tag 5"), None, None, None, None, None])

    def finde(_spot):
        return next(plan, Ziel(0.0, 3.0, "Tag 5"))

    gemeldet = []
    folgen.folge(_Spot(), finde, melde=gemeldet.append, jetzt=_uhr(),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(7))
    assert [m for m in gemeldet if "verloren" in m], "hier war wirklich eines da"
    assert any("wieder da" in m for m in gemeldet)


def test_die_stille_steht_auch_in_der_aufzeichnung():
    """Heute liess sich nur deshalb klaeren, was los war, weil die Aufzeichnung
    135 gleiche Zeilen enthielt -- die musste man erst zaehlen. Ein Ereignis
    sagt es in einer Zeile."""
    spot = _Spot()
    spot.recorder = _Aufzeichnung()
    folgen.folge(spot, lambda _s: None, melde=lambda _t: None, jetzt=_uhr(),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6))
    ohne_ziel = [d for art, d in spot.recorder.ereignisse if art == "kein_ziel"]
    assert ohne_ziel, "die Stille steht im Lauf"
    assert ohne_ziel[0]["je_gesehen"] is False
    assert ohne_ziel[0]["seit_s"] >= folgen.VERLOREN_S


def test_die_stille_kommt_beim_ECHTEN_schreiber_an(tmp_path):
    """Am 16.09.2026 stand `kein_ziel` in KEINEM Lauf, obwohl der Code lief: die
    Aufzeichnung fuehrt eine Erlaubnisliste (`record/events.py`), und die Art war
    nicht darin. `event()` warf, und der Auffangblock verschluckte es.

    Die Attrappe oben nahm jede Art an -- sie war grosszuegiger als die Sache
    selbst und konnte den Fehler deshalb nicht sehen. Dieser Test nimmt den
    echten Schreiber.
    """
    import json

    from spotlab.record.run import RunRecorder

    spot = _Spot()
    spot.recorder = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    gemeldet = []
    folgen.folge(spot, lambda _s: None, melde=gemeldet.append, jetzt=_uhr(),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6))

    zeilen = [json.loads(z) for z in
              (spot.recorder.dir / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
              if z.strip()]
    ohne_ziel = [z for z in zeilen if z["art"] == "kein_ziel"]
    assert ohne_ziel, "die Stille steht wirklich im Lauf, nicht nur in der Attrappe"
    assert ohne_ziel[0]["daten"]["je_gesehen"] is False
    assert not [m for m in gemeldet if "nicht aufzeichnen" in m], "und zwar ohne Klage"


def test_ein_schreiber_der_wirft_haelt_den_roboter_nicht_an_und_sagt_es(tmp_path):
    """Beides zusammen. Anhalten waere schlimmer als der fehlende Eintrag -- aber
    STILL scheitern ist genau der Fehler, den dieser Weg beheben soll."""
    class _Kaputt:
        def event(self, art, **daten):
            raise RuntimeError("Platte voll")

    spot = _Spot()
    spot.recorder = _Kaputt()
    gemeldet = []
    folgen.folge(spot, lambda _s: None, melde=gemeldet.append,
                 jetzt=_uhr(folgen.STILLE_TAKT_S), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(12))
    assert spot.kommandos == ["stop"], "der Lauf geht weiter"
    klagen = [m for m in gemeldet if "nicht aufzeichnen" in m]
    assert len(klagen) == 1, "einmal gesagt, nicht bei jeder Stille"
    assert "Platte voll" in klagen[0]


def test_ohne_aufzeichnung_laeuft_es_auch():
    """`folge()` laeuft auch aus einem Skript ohne Recorder."""
    spot = _Spot()
    folgen.folge(spot, lambda _s: None, melde=lambda _t: None, jetzt=_uhr(),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6))
    assert spot.kommandos == ["stop"]


def test_der_hinweis_des_finders_steht_genau_einmal_dabei():
    def finde(_spot):
        return None

    finde.hinweis = "Dieser Finder braucht ein blaues Tag."
    gemeldet = []
    folgen.folge(_Spot(), finde, melde=gemeldet.append,
                 jetzt=_uhr(folgen.STILLE_TAKT_S), schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(12))
    assert len([m for m in gemeldet if "blaues Tag" in m]) == 1, "einmal, nicht bei jeder Stille"


def test_der_personen_finder_nennt_den_befund_vom_geraet():
    """Er bleibt im Code und ist richtig -- er findet auf DIESEM Roboter nur
    nichts. Wer ihn waehlt, soll das erfahren, ohne die Abnahme zu lesen."""
    hinweis = folgen.personen_finder().hinweis
    assert "A34" in hinweis, "mit dem Beleg, nicht als Behauptung"
    assert "tag_finder" in hinweis or "gesicht_finder" in hinweis, "und mit einem Ausweg"


def test_zuerst_reicht_die_hinweise_seiner_finder_weiter():
    """Sonst verschwindet der Hinweis genau dann, wenn man staffelt."""
    def ohne(_spot):
        return None

    mit = folgen.personen_finder()
    staffel = folgen.zuerst(ohne, mit)
    assert mit.hinweis in getattr(staffel, "hinweis", "")


def test_die_stoppdatei_beendet_den_lauf(tmp_path):
    (tmp_path / STOPP_DATEI).write_text("", encoding="utf-8")
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)])
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, lauf_dir=tmp_path)
    assert spot.kommandos == ["stop"]


def test_ohne_lauf_verzeichnis_und_ohne_laeuft_ist_es_ein_fehler():
    with pytest.raises(ValueError, match="lauf_dir"):
        folgen.folge(_Spot(), folgen.tag_finder())


def test_der_kopfraum_wird_nicht_in_jedem_takt_geholt(monkeypatch):
    """Zwei Tiefenbilder ueber WLAN kosten mehr Zeit als ein Takt."""
    from spotlab.backends.real import tiefe

    abrufe = []
    monkeypatch.setattr(tiefe, "ueberhang_aus_bildern",
                        lambda *a, **kw: abrufe.append(1) or "punkte")
    monkeypatch.setattr(tiefe, "kopfraum", lambda punkte: None)
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)], faehigkeiten=Capability.DEPTH_CAMERAS,
                 kopfraum=["bild"])
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6),
                 jetzt=lambda: 0.0, kopfraum_takt_s=1.0)
    assert len(abrufe) == 1, "einmal geprueft, dann gilt es weiter"


def test_das_programm_liegt_im_projekt_beispiele(tmp_path):
    from spotlab.workshop.beispiele import bereitstellen

    bereitstellen(tmp_path)
    assert folgen.skript_in(tmp_path).is_file()


# ------------------------------------------------------- Gesicht und Staffel


def test_zuerst_nimmt_den_ersten_der_etwas_findet():
    """Damit lassen sich Strategien staffeln statt zu waehlen: das Gesicht,
    solange es sichtbar ist, und darunter das Tag."""
    keiner = lambda spot: None                                    # noqa: E731
    eines = lambda spot: Ziel(1.0, 3.0, "A")                      # noqa: E731
    anderes = lambda spot: Ziel(2.0, 4.0, "B")                    # noqa: E731

    assert folgen.zuerst(keiner, eines, anderes)(None).name == "A"
    assert folgen.zuerst(keiner, keiner)(None) is None
    assert folgen.zuerst()(None) is None


def test_der_gesichtsfinder_findet_nichts_ohne_die_noetigen_kameras():
    """Fehlt eine Quelle, gibt es kein Panorama und keine Entfernung -- und
    damit kein Ziel. Kein geratener Abstand: daran haengt der Mindestabstand."""
    class _OhneKameras(_Spot):
        def __init__(self):
            super().__init__()
            self.backend = SimpleNamespace(images=lambda quellen, **kw: [])

    assert folgen.gesicht_finder()(_OhneKameras()) is None


def test_ein_werfender_gesichtsfinder_beendet_den_lauf_nicht():
    class _Kaputt(_Spot):
        def __init__(self):
            super().__init__()

            def wirft(quellen, **kw):
                raise RuntimeError("Kamera weg")

            self.backend = SimpleNamespace(images=wirft)

    spot = _Kaputt()
    folgen.folge(spot, folgen.gesicht_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2))
    assert spot.kommandos == ["stop"]


def test_ein_ausfallender_finder_haelt_die_staffel_nicht_auf(monkeypatch):
    """Fehlt OpenCV oder das Gesichtsmodell, soll das Tag weiter funktionieren."""
    from spotlab import protokoll

    notizen = []
    monkeypatch.setattr(protokoll, "notiere", notizen.append)

    def wirft(spot):
        raise RuntimeError("OpenCV fehlt")

    staffel = folgen.zuerst(wirft, lambda spot: Ziel(0.0, 3.0, "Tag 3"))
    assert staffel(None).name == "Tag 3"
    assert staffel(None).name == "Tag 3"
    assert len(notizen) == 1, "der Grund steht einmal im Protokoll, nicht bei jedem Takt"
    assert "OpenCV fehlt" in notizen[0]


# ================== S1.15 Nickwinkel: hoeher schauen waehrend der Fahrt
#
# Ohne Neigung reicht das Bild bei 1.5 m bis 1.20 m Hoehe, bei 3 m bis 1.94 m
# (gemessen am 16.09.2026 mit 150 Takten bei waagrechtem Koerper: aufrecht auf
# 1 m nur Beine im Bild, auf 2 m der Oberkoerper oben abgeschnitten). Der
# Folgemodus will aber 1.6 m halten. Fuenfzehn Grad heben die Kante bei 1.5 m
# auf 1.76 m -- und kosten den Boden dicht vor den Fuessen.


def test_die_vorgabe_hebt_die_nase():
    """Seit dem 16.09.2026 ist die Vorgabe NICHT mehr null: mit waagrechtem
    Koerper sieht Spot einen aufrecht stehenden Menschen auf Folgeabstand nie --
    in 390 Takten ueber vier Sonden kein einziges Gesicht ueber 1.20 m bei
    1.5 m. Die beiden Sonden, in denen er jeden Takt eines fand, hatten die Nase
    25 Grad oben. Genau das baut die Vorgabe nach, geklemmt unter MAX."""
    assert 0.0 < folgen.BLICK_GRAD <= folgen.MAX_BLICK_GRAD
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)], neigt=True)
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten and all(k["nick_grad"] == -folgen.BLICK_GRAD for k in fahrten), \
        "ohne Angabe faehrt er mit der Vorgabe, Nase hoch ist negativ"


def test_mit_blick_grad_null_bleibt_der_fahrbefehl_flach():
    """Der alte Weg bleibt waehlbar -- wer den Boden vor den Fuessen braucht,
    sagt blick_grad=0 und bekommt nick 0 und im Wunschabstand einen Stopp."""
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)], neigt=True)
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2), blick_grad=0.0)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten and all(k["nick_grad"] == 0.0 for k in fahrten)

    still = _Spot(tags=[_tag(3, 0.0, folgen.WUNSCH_ABSTAND_M)], neigt=True)
    folgen.folge(still, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2), blick_grad=0.0)
    assert still.kommandos == ["stop"], "kein Fahrbefehl, wenn nichts zu tun ist"


def test_die_neigung_geht_mit_jedem_fahrbefehl_mit():
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)], neigt=True)
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2), blick_grad=12.0)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten and all(k["nick_grad"] == -12.0 for k in fahrten), \
        "Projektkonvention: Nase hoch ist NEGATIV"


def test_im_wunschabstand_haelt_er_die_nase_oben():
    """Sonst legt Spot sie ab, verliert das Gesicht und pendelt zwischen Suchen
    und Fahren."""
    spot = _Spot(tags=[_tag(3, 0.0, folgen.WUNSCH_ABSTAND_M)], neigt=True)
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2), blick_grad=12.0)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten, "auch bei Tempo null geht ein Kommando raus"
    assert all(k["vx"] == 0.0 and k["nick_grad"] == -12.0 for k in fahrten)


def test_ein_backend_das_sich_nicht_neigt_sagt_es_und_faehrt_flach():
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)], neigt=False)
    gemeldet = []
    folgen.folge(spot, folgen.tag_finder(), melde=gemeldet.append,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2), blick_grad=12.0)
    assert any("neigt sich beim Gehen nicht" in m for m in gemeldet)
    assert all(k["nick_grad"] == 0.0 for k in spot.kommandos if isinstance(k, dict))


@pytest.mark.parametrize("gewuenscht, erwartet", [(0.0, 0.0), (10.0, -10.0),
                                                  (99.0, -folgen.MAX_BLICK_GRAD),
                                                  (-5.0, 0.0)])
def test_der_blickwinkel_wird_geklemmt(gewuenscht, erwartet):
    """Nach unten gibt es nichts zu gewinnen, und nach oben ist bei 20 Grad Schluss."""
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)], neigt=True)
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(2), blick_grad=gewuenscht)
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten and all(k["nick_grad"] == erwartet for k in fahrten)


def test_der_gemessene_nick_kommt_aus_dem_zustand():
    import math

    assert folgen._nick(_Spot(nick=math.radians(-12.0))) == pytest.approx(math.radians(-12.0))

    class _Ohne:
        @property
        def state(self):
            raise RuntimeError("kein Zustand")

    assert folgen._nick(_Ohne()) == 0.0


# ------------------------------------------------- Was der Finder gesehen hat
#
# Am 16.09.2026 stand Spot 43 Sekunden vor einem Menschen und folgte nicht,
# waehrend derselbe Erkenner im Fahren-Reiter Kaesten auf dasselbe Gesicht
# setzte. Aus dem Lauf war nicht zu entnehmen, WORAN es lag: kein Kasten vom
# Erkenner, oder alle von der Tiefen-Gegenprobe verworfen? `finde` gibt in
# beiden Faellen None zurueck. Ein Nullergebnis ohne Begruendung ist keine
# Messung -- also sagt der Finder jetzt, was er gesehen hat.


class _Befund:
    """So viel von `gesicht.Befund`, wie die Zusammenfassung liest."""

    def __init__(self, genommen=False, grund=None, distance=2.0):
        self.genommen, self.grund, self.distance = genommen, grund, distance


def test_ohne_kasten_sagt_der_befund_dass_der_erkenner_nichts_setzte():
    assert "kein Kasten" in folgen._gesichtsbefund([])


def test_verworfene_kaesten_stehen_mit_grund_und_anzahl_da():
    """Die Zeile, die heute gefehlt hat."""
    text = folgen._gesichtsbefund([
        _Befund(grund="zu tief"), _Befund(grund="zu tief"),
        _Befund(grund="keine tiefenpunkte"),
    ])
    assert "3" in text and "verworfen" in text
    assert "2× zu tief" in text and "1× keine tiefenpunkte" in text


def test_ein_genommener_kasten_steht_auch_im_befund():
    text = folgen._gesichtsbefund([_Befund(genommen=True), _Befund(grund="zu hoch")])
    assert "1 genommen" in text


def test_der_gesichtsfinder_traegt_einen_befund_und_nennt_fehlende_bilder():
    class _OhneKameras(_Spot):
        def __init__(self):
            super().__init__()
            self.backend = SimpleNamespace(images=lambda quellen, **kw: [])

    finder = folgen.gesicht_finder()
    assert finder(_OhneKameras()) is None
    assert "Bilder" in finder.befund(), "auch das ist eine Auskunft"


def test_die_stille_traegt_den_befund_des_finders(tmp_path):
    """In der Meldung UND im Lauf -- sonst muss man wieder danebenstehen."""
    import json

    from spotlab.record.run import RunRecorder

    def finde(_spot):
        return None

    finde.befund = lambda: "3 Kästen, alle verworfen (3× zu tief)"

    spot = _Spot()
    spot.recorder = RunRecorder(tmp_path / "runs", None, backend="dryrun")
    gemeldet = []
    folgen.folge(spot, finde, melde=gemeldet.append, jetzt=_uhr(),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6))

    assert any("zu tief" in m for m in gemeldet), "er sagt es beim Warten"
    zeilen = [json.loads(z) for z in
              (spot.recorder.dir / "ereignisse.jsonl").read_text(encoding="utf-8").splitlines()
              if z.strip()]
    ohne_ziel = [z for z in zeilen if z["art"] == "kein_ziel"]
    assert ohne_ziel and "zu tief" in ohne_ziel[0]["daten"]["befund"]


def test_ein_werfender_befund_haelt_die_schleife_nicht_an():
    """Eine Auskunft ueber den Zustand darf den Zustand nicht veraendern."""
    def finde(_spot):
        return None

    def kaputt():
        raise RuntimeError("Zaehler kaputt")

    finde.befund = kaputt
    spot = _Spot()
    folgen.folge(spot, finde, melde=lambda _t: None, jetzt=_uhr(),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6))
    assert spot.kommandos == ["stop"]


def test_zuerst_reicht_auch_die_befunde_weiter():
    """Bei der Staffel ist die Frage erst recht offen: welcher der beiden hat
    nichts gesehen, und warum?"""
    def eins(_spot):
        return None

    def zwei(_spot):
        return None

    eins.befund = lambda: "kein Kasten vom Erkenner"
    zwei.befund = lambda: "kein Tag sichtbar"
    text = folgen.zuerst(eins, zwei).befund()
    assert "kein Kasten vom Erkenner" in text and "kein Tag sichtbar" in text


# ------------------------------------------------- Farbe statt Grau + Aufhellung
#
# Gemessen am 16.09.2026, dasselbe Bild durch beide Wege, 390 Takte: Farbe ohne
# Aufhellung fand JEDES echte Gesicht, das Grau mit Aufhellung fand (D ohne B: 0)
# -- aber sieben Riesenkaesten weniger (Phantome auf Beinen und einem
# Regalbrett, 0.60-0.78). Dieser Spot liefert die Frontbilder in Farbe; aeltere
# Spots fallen ueber `images(farbe=True)` von selbst auf Grau zurueck, und dort
# greift die Aufhellung weiter.


def test_die_gesichtsaufnahme_bittet_fuer_die_kameras_um_farbe_nicht_fuer_die_tiefe():
    """Zwei Anfragen, keine. Ein RGB-Wunsch fuer ein TIEFENBILD wird vom Roboter
    abgewiesen -- und `images()` merkt sich das als 'keine Farbe moeglich' fuer
    die ganze Sitzung. Dann waere die Farbe still weg, ohne dass es jemand sieht."""
    gefragt = []

    class _Backend:
        def images(self, quellen, **kw):
            gefragt.append((tuple(quellen), dict(kw)))
            return []

    spot = _Spot()
    spot.backend = _Backend()
    assert folgen.gesichtsaufnahme(spot, {}) is None, "ohne Bilder keine Aufnahme"

    mit_farbe = [q for q, kw in gefragt if kw.get("farbe")]
    ohne_farbe = [q for q, kw in gefragt if not kw.get("farbe")]
    assert mit_farbe and set(mit_farbe[0]) == set(folgen.GESICHT_QUELLEN)
    assert ohne_farbe and set(ohne_farbe[0]) == set(folgen.TIEFE_QUELLEN)
    assert not any(set(q) & set(folgen.TIEFE_QUELLEN) for q in mit_farbe), \
        "die Tiefe NIE in Farbe erbitten"


# ---------------------------------- Suchhaltung und Uebersteuern (16.09.2026)
#
# Lauf 20260916T122739Z: 94 Fahrbefehle, wz pendelt zwischen -0.79 und +0.79
# rad/s mit 13 Drehsinn-Wechseln, vx fast immer null. Mit dem Gesichtsfinder
# dauert ein Takt 0.45-0.9 s (vier Bilder plus YuNet); bei 45 Grad/s dreht Spot
# je Takt 20-40 Grad -- mehr als die Peilung selbst -- und schiesst ueber die
# Nase hinaus. Die Laeufe danach: null Fahrbefehle, Nick null. Ohne Ziel gab es
# keinen Fahrbefehl, ohne Fahrbefehl keine Neigung, ohne Neigung kein Ziel.


def test_bei_langsamem_takt_dreht_er_je_takt_hoechstens_die_halbe_peilung():
    """Wer 0.6 s lang nicht hinschaut, darf in der Zeit nicht weiter drehen, als
    das Ziel entfernt ist -- sonst liegt es danach auf der anderen Seite."""
    import math

    _, wz = folgen.befehl(Ziel(20.0, 3.0), takt_s=0.6)
    assert abs(wz) <= math.radians(0.5 * 20.0 / 0.6) + 1e-9
    assert wz > 0.0, "die Richtung bleibt"


def test_bei_schnellem_takt_bleibt_die_drehrate_wie_bisher():
    """Das Tag liefert alle 0.2 s -- dort war nichts kaputt, dort aendert sich nichts."""
    import math

    _, schnell = folgen.befehl(Ziel(20.0, 3.0), takt_s=0.2)
    _, ohne = folgen.befehl(Ziel(20.0, 3.0))
    assert schnell == pytest.approx(ohne)
    _, gross = folgen.befehl(Ziel(180.0, 3.0), takt_s=0.2)
    assert gross == pytest.approx(math.radians(folgen.MAX_DREHRATE_GRAD)), "der Deckel bleibt"


def test_ohne_ziel_haelt_er_die_nase_oben_und_steht():
    """Die Suchhaltung: die Neigung muss VOR dem ersten Ziel da sein, sonst sieht
    er mit flacher Nase keinen aufrecht stehenden Menschen und findet nie eines."""
    spot = _Spot(neigt=True)
    folgen.folge(spot, lambda _s: None, melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten, "auch ohne Ziel geht ein Haltungsbefehl raus"
    assert all(k["vx"] == 0.0 and k["wz"] == 0.0 for k in fahrten), "aber er faehrt nicht"
    assert all(k["nick_grad"] == -folgen.BLICK_GRAD for k in fahrten)
    assert spot.kommandos[-1] == "stop", "am Ende haelt er immer"


def test_beim_verlieren_haelt_er_sofort_an_und_bleibt_geneigt():
    plan = iter([Ziel(0.0, 3.0, "Tag 5"), Ziel(0.0, 3.0, "Tag 5"), None, None, None])

    def finde(_spot):
        return next(plan, None)

    spot = _Spot(neigt=True)
    # Ohne Nachlauf: hier geht es um den Stopp beim Verlust und die Haltung danach.
    folgen.folge(spot, finde, melde=lambda _t: None, schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(5), nachlauf_s=0.0)
    k = spot.kommandos
    erste_null = next(i for i, c in enumerate(k) if isinstance(c, dict) and c["vx"] == 0.0)
    assert "stop" in k[:erste_null + 1], "beim Verlust erst der Stopp"
    danach = [c for c in k[erste_null:] if isinstance(c, dict)]
    assert danach and all(c["vx"] == 0.0 and c["nick_grad"] == -folgen.BLICK_GRAD for c in danach)


def test_ohne_neigung_gibt_es_ohne_ziel_keinen_befehl():
    """Der flache Weg bleibt, wie er war: ohne Ziel kein einziger Fahrbefehl."""
    spot = _Spot(neigt=True)
    folgen.folge(spot, lambda _s: None, melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3), blick_grad=0.0)
    assert spot.kommandos == ["stop"]


# ------------------------------------------------------------ Nachlauf (16.09.2026)
#
# Der Erkenner trifft neun von zehn Takten -- und der zehnte hielt Spot sofort
# an. Ein Ziel, das vor unter einer Sekunde noch da war, gilt weiter: der
# Regler faehrt aus dem LETZTEN Ziel weiter, mit allen Schranken. Eine Sekunde
# bei 0.5 m/s sind 50 cm blind; das Fahrkommando selbst verfaellt ohnehin nach
# rund einer Sekunde. Entscheidung des Menschen am 16.09.2026.


def _uhr_schritte(*schritte):
    """Eine Uhr, die je Aufruf den naechsten Schritt weitergeht (dann den letzten)."""
    stand = {"t": 0.0, "i": 0}

    def jetzt():
        s = schritte[min(stand["i"], len(schritte) - 1)]
        stand["i"] += 1
        stand["t"] += s
        return stand["t"]

    return jetzt


def test_ein_kurzer_aussetzer_haelt_ihn_nicht_an():
    """Ziel, dann drei Takte nichts innerhalb einer Sekunde: er faehrt weiter."""
    plan = iter([Ziel(0.0, 3.0, "Gesicht"), None, None, None])

    def finde(_spot):
        return next(plan, None)

    spot = _Spot()
    folgen.folge(spot, finde, melde=lambda _t: None, jetzt=_uhr_schritte(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(4))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert len(fahrten) >= 3, "auch in den Aussetzer-Takten geht ein Fahrbefehl raus"
    assert all(k["vx"] > 0.0 for k in fahrten), "aus dem letzten Ziel, nicht Stillstand"
    assert "stop" not in spot.kommandos[:-1], "kein Stopp zwischendurch"


def test_nach_dem_nachlauf_haelt_er_an():
    plan = iter([Ziel(0.0, 3.0, "Gesicht"), None, None, None, None])

    def finde(_spot):
        return next(plan, None)

    spot = _Spot()
    # Jeder Takt kostet 0.6 s: der erste Aussetzer liegt im Nachlauf, der zweite nicht mehr.
    folgen.folge(spot, finde, melde=lambda _t: None, jetzt=_uhr_schritte(0.6),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(5))
    assert "stop" in spot.kommandos[:-1], "nach NACHLAUF_S haelt er an"
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert 1 <= len(fahrten) <= 3, "hoechstens einen Nachlauf-Takt lang weitergefahren"


def test_im_nachlauf_gelten_die_schranken_weiter():
    """Blind fahren heisst nicht ungeprueft fahren: eine Wand im Nachlauf stoppt."""
    plan = iter([Ziel(0.0, 3.0, "Gesicht"), None, None])

    def finde(_spot):
        return next(plan, None)

    spot = _Spot(frei=5.0)
    frei = {"m": 5.0}
    spot.obstacles = lambda: SimpleNamespace(free_distance=lambda x, y, g: frei["m"])
    gesagt = []

    def melde(text):
        gesagt.append(text)

    # Nach dem ersten Takt steht ploetzlich etwas im Weg.
    original = finde

    def finde_und_wand(s):
        z = original(s)
        if z is None:
            frei["m"] = 0.2
        return z

    folgen.folge(spot, finde_und_wand, melde=melde, jetzt=_uhr_schritte(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten[0]["vx"] > 0.0
    assert all(k["vx"] == 0.0 for k in fahrten[1:]), "im Nachlauf: Wand -> kein Vorwaerts"
    assert any("Stehen geblieben" in m for m in gesagt)


def test_der_nachlauf_verlaengert_sich_nicht_selbst():
    """Ein gehaltenes Ziel zaehlt nicht als gesehen -- sonst hielte er ewig."""
    plan = iter([Ziel(0.0, 3.0, "Gesicht")] + [None] * 10)

    def finde(_spot):
        return next(plan, None)

    spot = _Spot()
    folgen.folge(spot, finde, melde=lambda _t: None, jetzt=_uhr_schritte(0.3),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(11))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert len(fahrten) < 8, "irgendwann ist der Nachlauf um"
    assert spot.kommandos[-1] == "stop"


# ------------------------------------------ Nur den Rest des Takts schlafen
#
# Gemessen am 16.09.2026, ein Gesichts-Takt: Bildabrufe ~100 ms, YuNet 85 ms,
# beurteile 107 ms, RPCs 50-150 ms -- und dann schlief die Schleife UNBEDINGT
# noch 200 ms obendrauf. Beim Tag (0.05 s Arbeit) ist der Schlaf das Taktmass;
# beim Gesicht war er reine Blindzeit. Die Tiefe (4 ms) war es nie.


def test_bei_langsamer_arbeit_schlaeft_er_nicht_mehr_obendrauf():
    """Der Finder braucht 0.5 s: laenger als der Takt. Dann wird nicht geschlafen."""
    uhr = {"t": 0.0}

    def jetzt():
        return uhr["t"]

    def langsam(_spot):
        uhr["t"] += 0.5
        return Ziel(0.0, 3.0, "Gesicht")

    geschlafen = []
    folgen.folge(_Spot(), langsam, melde=lambda _t: None, jetzt=jetzt,
                 schlaf=geschlafen.append, laeuft=_laeuft_takte(3), takt_s=0.2)
    assert geschlafen and all(s <= 1e-9 for s in geschlafen), geschlafen


def test_bei_schneller_arbeit_bleibt_der_takt_das_mass():
    """Der Tag antwortet sofort: dann schlaeft er wie bisher bis zum Taktende."""
    uhr = {"t": 0.0}

    def jetzt():
        return uhr["t"]

    def schnell(_spot):
        uhr["t"] += 0.02
        return Ziel(0.0, 3.0, "Tag 3")

    geschlafen = []
    folgen.folge(_Spot(), schnell, melde=lambda _t: None, jetzt=jetzt,
                 schlaf=geschlafen.append, laeuft=_laeuft_takte(3), takt_s=0.2)
    assert geschlafen and all(0.1 <= s <= 0.2 for s in geschlafen), geschlafen


# ------------------------------------ Die Nase folgt dem Gesicht (16.09.2026)
#
# Feste Zahlen (15 Grad, 1.6 m) passen fuer EINEN Menschen. Gemessen: bei 15
# Grad und 1.6 m genau voraus liegt ein 1.65 m hohes Gesicht in der Naht-Kerbe
# (Grenze 1.46 m) und ist abgeschnitten -- Takt 110 der Reichweiten-Sonde. Die
# Regel: erst so nah wie moeglich, dann so hoch wie moeglich schauen, und nur
# wenn beides ausgereizt ist, nicht naeher (Wunsch des Menschen). Der Kasten
# traegt dafuer seine Oberkante als koerperfesten Hoehenwinkel (`bild_oben`).


def _gesicht(oben, abstand=3.0, peilung=0.0):
    return Ziel(peilung, abstand, "Gesicht", bild_oben=oben)


def _nicks(spot):
    return [k["nick_grad"] for k in spot.kommandos if isinstance(k, dict)]


def test_ein_hoher_kasten_hebt_die_nase_schrittweise_bis_zum_maximum():
    spot = _Spot(neigt=True)
    folgen.folge(spot, lambda _s: _gesicht(25.0), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(5))
    assert _nicks(spot) == [-18.0, -20.0, -20.0, -20.0, -20.0], _nicks(spot)


def test_ein_tiefer_kasten_senkt_die_nase_bis_zur_untergrenze():
    """Weit weg: die Nase kommt runter, und die Hindernisschranke bekommt den
    Boden zurueck -- aber nie ganz flach, sonst geht das Gesicht beim Naeherkommen
    sofort wieder verloren."""
    spot = _Spot(neigt=True)
    folgen.folge(spot, lambda _s: _gesicht(-20.0), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(4))
    assert _nicks(spot) == [-12.0, -10.0, -10.0, -10.0], _nicks(spot)
    assert folgen.NICK_MIN_GRAD == 10.0


def test_im_totband_bleibt_die_nase_ruhig():
    spot = _Spot(neigt=True)
    folgen.folge(spot, lambda _s: _gesicht(folgen.SOLL_OBEN_GRAD + 1.0), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3))
    assert _nicks(spot) == [-15.0, -15.0, -15.0]


def test_am_maximum_und_immer_noch_zu_hoch_kommt_er_nicht_naeher_dreht_aber_mit():
    """Das 'gerade noch so': so nah, wie er noch sehen kann -- nicht naeher."""
    spot = _Spot(neigt=True)
    folgen.folge(spot, lambda _s: _gesicht(30.0, abstand=3.0, peilung=20.0),
                 melde=lambda _t: None, schlaf=lambda _s: None, laeuft=_laeuft_takte(5))
    fahrten = [k for k in spot.kommandos if isinstance(k, dict)]
    assert fahrten[0]["vx"] > 0.0, "solange die Nase noch hoeher kann, faehrt er heran"
    assert fahrten[-1]["nick_grad"] == -folgen.MAX_BLICK_GRAD
    assert fahrten[-1]["vx"] == 0.0, "am Anschlag: nicht naeher"
    assert fahrten[-1]["wz"] != 0.0, "aber weiter mitdrehen"


def test_ein_tag_ziel_laesst_die_neigung_in_ruhe():
    spot = _Spot(tags=[_tag(3, 0.0, 3.0)], neigt=True)
    folgen.folge(spot, folgen.tag_finder(), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3))
    assert _nicks(spot) == [-15.0, -15.0, -15.0]


def test_ohne_ziel_bleibt_die_zuletzt_geregelte_neigung_stehen():
    """Suchhaltung dort, wo er das Gesicht zuletzt sah -- nicht zurueck auf 15."""
    plan = iter([_gesicht(25.0), _gesicht(25.0), None, None, None])

    def finde(_spot):
        return next(plan, None)

    spot = _Spot(neigt=True)
    folgen.folge(spot, finde, melde=lambda _t: None, schlaf=lambda _s: None,
                 laeuft=_laeuft_takte(5), nachlauf_s=0.0)
    nicks = _nicks(spot)
    assert nicks[:2] == [-18.0, -20.0]
    assert all(n == -20.0 for n in nicks[2:]) and len(nicks) > 2


def test_im_nachlauf_wird_nicht_weitergeregelt():
    """Ein gehaltenes Ziel ist kein gesehenes: die Nase regelt nur auf echte Kaesten."""
    plan = iter([_gesicht(25.0), None, None])

    def finde(_spot):
        return next(plan, None)

    spot = _Spot(neigt=True)
    folgen.folge(spot, finde, melde=lambda _t: None, jetzt=_uhr_schritte(0.05),
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3))
    assert _nicks(spot) == [-18.0, -18.0, -18.0], _nicks(spot)


def test_flach_bleibt_flach():
    """blick_grad=0 ist der alte Weg: keine Regelung, auch bei hohem Kasten."""
    spot = _Spot(neigt=True)
    folgen.folge(spot, lambda _s: _gesicht(25.0), melde=lambda _t: None,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(3), blick_grad=0.0)
    assert _nicks(spot) == [0.0, 0.0, 0.0]


def test_der_gesichtsfinder_traegt_die_kastenoberkante_ins_ziel():
    """Aus dem Befund (Kasten x, y, b, h) und der Panorama-Geometrie: der
    Hoehenwinkel der OBERKANTE, koerperfest -- das ist, was oben rauslaeuft."""
    from spotlab.backends.real.gesicht import Befund

    class _Pano:
        def winkel(self, spalte, zeile):
            return 5.0, 30.0 - zeile / 10.0        # Zeile 0 = +30 Grad, Zeile 100 = +20

    kopf = Befund(5.0, 12.0, 0.9, (100.0, 100.0, 40.0, 40.0), distance=2.0, height=1.6,
                  genommen=True)
    ziel = folgen._ziel_aus_befund(kopf, _Pano())
    assert ziel.bearing == 5.0 and ziel.distance == 2.0
    assert ziel.bild_oben == pytest.approx(20.0), "Oberkante y=100 -> +20 Grad"
    assert "1.60 m" in ziel.name
