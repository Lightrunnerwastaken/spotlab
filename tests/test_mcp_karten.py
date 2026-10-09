"""Die Karten- und Merkort-Werkzeuge des MCP-Servers (Agenten am Spot, Teil 2).

Die Zentrale ist dieselbe Attrappe wie in `test_mcp_fahren.py`: sie liest `agent_befehl.json`
und schreibt den Stand ins Lagebild."""

from pathlib import Path

import pytest
from test_mcp_fahren import wurzel, zentrale_mit  # noqa: F401  (Fixtures)

from spotlab.mcp import fahren, karten
from spotlab.record import agent as agentdatei

KATAKOMBEN = Path(r"D:\Users\janis\Documents\Spot Projects\maps\map_catacombs_01")


def _mitschreiben(liste, zustand="erledigt", grund="", **felder):
    """Eine Antwort der Attrappe, die jeden gelesenen Befehl als (art, werte) festhält."""

    def antwort(befehl, seit_s):
        if not liste or liste[-1][0] != befehl.nummer:
            liste.append((befehl.nummer, befehl.art, dict(befehl.werte)))
        return (zustand, grund, felder) if felder else (zustand, grund)

    return antwort


@pytest.mark.parametrize("werkzeug, argumente", [
    ("karte_laden", {"name": "flur"}), ("aufnahme_starten", {}), ("aufnahme_beenden", {}),
    ("wegpunkt_setzen", {"name": "Tür"}), ("zum_wegpunkt", {"name": "Tür", "warum": "hin"}),
])
def test_im_uebungsraum_sagen_die_kartenwerkzeuge_was_dort_geht(zentrale_mit, werkzeug,  # noqa: F811
                                                                 argumente):
    befehle = []
    zentrale_mit(_mitschreiben(befehle), backend="mujoco")
    antwort = getattr(karten, werkzeug)(**argumente)
    assert "merkort_setzen" in antwort["fehler"] and "zum_merkort" in antwort["fehler"], antwort
    assert befehle == [], "kein Befehl geht an die Zentrale"


def test_ohne_zentrale_sagt_ein_kartenwerkzeug_wie_man_eine_startet(wurzel):  # noqa: F811
    assert "zentrale_starten" in karten.karte_laden("flur")["fehler"]


def test_karte_laden_wartet_aufs_ende_und_nennt_den_stand(zentrale_mit):  # noqa: F811
    def antwort(befehl, seit_s):
        if seit_s < 0.4:
            return "unterwegs", ""
        return "erledigt", "Karte geladen", {"karte": {"zustand": "sucht_tag", "name": "flur",
                                                       "grund": "", "gespeichert_als": None}}

    zentrale = zentrale_mit(antwort, backend="real")
    ergebnis = karten.karte_laden("flur")
    assert ergebnis["zustand"] == "erledigt", ergebnis
    assert ergebnis["karte"]["zustand"] == "sucht_tag" and "AprilTag" in ergebnis["hinweis"]
    befehl = agentdatei.lies_befehl(zentrale.lauf)
    assert (befehl.art, befehl.werte) == ("karte_laden", {"name": "flur"})


def test_aufnahme_beenden_nennt_den_freien_namen(zentrale_mit):  # noqa: F811
    zentrale_mit(_mitschreiben([], grund="gespeichert als ‹flur-2›",
                               karte={"zustand": "keine", "name": None, "grund": "",
                                      "gespeichert_als": "flur-2"}), backend="real")
    antwort = karten.aufnahme_beenden()
    assert antwort["karte"]["gespeichert_als"] == "flur-2", antwort


def test_ohne_namen_sagt_jedes_werkzeug_was_fehlt(zentrale_mit):  # noqa: F811
    zentrale_mit(_mitschreiben([]), backend="real")
    assert "welcher Wegpunkt" in karten.zum_wegpunkt("  ", warum="hin")["fehler"]
    assert "welche Karte" in karten.karte_laden("")["fehler"]
    assert "warum" in karten.zum_wegpunkt("Küche", warum="")["fehler"]


def test_merkortbefehle_gehen_mit_namen_und_ort_an_die_zentrale(zentrale_mit):  # noqa: F811
    befehle = []
    zentrale_mit(_mitschreiben(befehle), backend="sim")
    assert karten.merkort_setzen("Tür")["zustand"] == "erledigt"
    karten.merkort_setzen("Tisch", x=1, y=2)
    karten.merkort_loeschen("Tisch")
    karten.zum_merkort("Tür", warum="zurück zum Anfang")
    assert [(art, werte) for _, art, werte in befehle] == [
        ("merkort_setzen", {"name": "Tür"}),
        ("merkort_setzen", {"name": "Tisch", "x": 1.0, "y": 2.0}),
        ("merkort_loeschen", {"name": "Tisch"}),
        ("zum_merkort", {"name": "Tür"}),
    ]
    assert "welcher Merkort" in karten.zum_merkort("", warum="hin")["fehler"]
    assert "x muss eine Zahl sein" in karten.merkort_setzen("Ecke", x="links", y=0)["fehler"]


def test_der_status_nennt_die_geladene_karte(zentrale_mit):  # noqa: F811
    zentrale = zentrale_mit(lambda b, s: None, backend="real")
    zentrale.lagebild = {"karte": {"kann": True, "name": "flur", "zustand": "verortet",
                                   "grund": "", "wegpunkte": []}}
    zentrale._schreibe()
    assert fahren.zentrale_status()["karte"] == {"name": "flur", "zustand": "verortet"}


def test_ein_freier_raumname_meidet_eigene_raeume_und_vorlagen(tmp_path):
    from spotlab.welt.raum import raum_pfad, vorlagen

    raum_pfad(tmp_path, "flur").parent.mkdir(parents=True)
    raum_pfad(tmp_path, "flur").write_text("", encoding="utf-8")
    assert karten._freier_raumname(tmp_path, "flur") == "flur-2"
    assert karten._freier_raumname(tmp_path, vorlagen()[0]) == f"{vorlagen()[0]}-2"
    assert karten._freier_raumname(tmp_path, "gang") == "gang"


@pytest.mark.skipif(not KATAKOMBEN.is_dir(), reason="Katakomben-Karte fehlt auf diesem Rechner")
def test_raum_aus_karte_baut_einen_ladbaren_raum_mit_pauspapier(wurzel, monkeypatch):  # noqa: F811
    from spotlab.welt.raum import raum_laden

    monkeypatch.setattr(karten, "_kartenordner", lambda ws, karte: KATAKOMBEN)
    antwort = karten.raum_aus_karte("katakomben", name="kata")
    assert antwort["name"] == "kata", antwort
    pfad = Path(antwort["pfad"])
    assert pfad == wurzel / "raeume" / "kata.toml" and pfad.with_suffix(".pauspapier").is_file()
    assert antwort["waende"] > 10 and antwort["tags"] > 10
    assert raum_laden("kata", wurzel).name == "kata"
    assert 'raum="kata"' in antwort["hinweis"]


# ------------------------------------------------------------ Kette mit dem echten Programm


def test_die_kette_mit_einem_merkort_im_2d_uebungsraum(wurzel, monkeypatch):  # noqa: F811
    """zentrale_starten → merkort_setzen → fahre_relativ → zum_merkort → angekommen →
    zentrale_beenden mit dem echten Programm im 2D-Übungsraum „durchgang“ (Start (1, 2), Blick
    +x). Der Merkort liegt danach neben dem Raum, und ein zweiter Start kennt ihn wieder."""
    import json

    monkeypatch.setattr(fahren, "BESTAETIGUNG_S", 10.0)        # ein echter Prozess unter Last
    monkeypatch.setattr(fahren, "BEFEHL_WARTE_S", 60.0)
    start = fahren.zentrale_starten("2d", raum="durchgang")
    assert start.get("gestartet"), start
    try:
        gesetzt = karten.merkort_setzen("start")
        assert gesetzt["zustand"] == "erledigt", gesetzt
        assert fahren.fahre_relativ(1.0, 0.0, warum="ein Stück vor")["zustand"] == "angekommen"
        assert fahren.lage()["spot"]["x"] == pytest.approx(2.0, abs=0.35)
        zurueck = karten.zum_merkort("start", warum="zurück zum Anfang")
        assert zurueck["zustand"] == "angekommen", zurueck
        lage = fahren.lage()
        assert (lage["spot"]["x"], lage["spot"]["y"]) == (pytest.approx(1.0, abs=0.35),
                                                          pytest.approx(2.0, abs=0.35)), lage
    finally:
        ende = fahren.zentrale_beenden()
    assert ende["beendet"], ende
    datei = wurzel / "raeume" / "durchgang.merkorte.json"
    assert [o["name"] for o in json.loads(datei.read_text(encoding="utf-8"))] == ["start"]

    assert fahren.zentrale_starten("2d", raum="durchgang").get("gestartet")
    try:
        assert [o["name"] for o in fahren.lage()["merkorte"]] == ["start"]
    finally:
        assert fahren.zentrale_beenden()["beendet"]
