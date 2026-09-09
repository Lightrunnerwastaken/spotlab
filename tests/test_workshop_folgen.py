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
                 faehigkeiten=Capability.LOCOMOTION, kopfraum=None, kartenlage=None):
        self._tags, self._leute = list(tags), list(leute)
        self._frei, self._pose = frei, pose
        self._kartenlage = kartenlage
        self.kommandos = []
        self.backend = SimpleNamespace(
            capabilities=lambda: faehigkeiten,
            images=lambda quellen: kopfraum,
        )

    def tags(self, id=None):
        return [t for t in self._tags if id is None or t.id == id]

    def people(self):
        return list(self._leute)

    def obstacles(self):
        return SimpleNamespace(free_distance=lambda x, y, grad: self._frei)

    @property
    def state(self):
        return SimpleNamespace(pose=self._pose)

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


def test_das_verlieren_wird_einmal_gesagt_und_die_rueckkehr_auch():
    zeit = {"t": 0.0}

    def jetzt():
        zeit["t"] += 3.0
        return zeit["t"]

    spot = _Spot()
    gemeldet = []
    folgen.folge(spot, lambda s: None, melde=gemeldet.append, jetzt=jetzt,
                 schlaf=lambda _s: None, laeuft=_laeuft_takte(6))
    assert len([m for m in gemeldet if "verloren" in m]) == 1


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
