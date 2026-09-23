"""`record/atomar.py`: eine kleine Datei ersetzen, die jemand gerade liest.

Das Versprechen steht im Modul: kurz wiederholen, dann aufgeben -- und NIE
werfen. Ein Fahrbefehl oder ein Bild darf weder die GUI noch den Lauf anhalten.
"""

import threading

from spotlab.record import ansicht, atomar

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 20_000 + b"\xff\xd9"


def test_jedes_ziel_hat_seine_eigene_tempdatei(tmp_path, monkeypatch):
    """Beta-Prüfung 23.09.2026 (p12): die Temp-Datei hiess `ziel.with_suffix(".tmp")`
    -- für `ansicht.jpg` (Blick, MuJoCo) UND `ansicht.json` (Schalter der GUI)
    also beide `ansicht.tmp`. Zwei Schreiber, eine Datei."""
    quellen = []
    echt = atomar._ersetze

    def merke(quelle, ziel):
        quellen.append((str(quelle), str(ziel)))
        return echt(quelle, ziel)

    monkeypatch.setattr(atomar, "_ersetze", merke)
    assert atomar.schreibe_atomar(tmp_path / "ansicht.jpg", JPEG)
    assert atomar.schreibe_atomar(tmp_path / "ansicht.json", "{}")
    assert atomar.schreibe_atomar(tmp_path / "ansicht.json", "{}")
    (jpg, _), (json1, _), (json2, _) = quellen
    assert len({jpg, json1, json2}) == 3, "keine Temp-Datei zweimal"
    assert "ansicht.jpg" in jpg and "ansicht.json" in json1
    assert not list(tmp_path.glob("*.tmp")), "nichts bleibt liegen"


def test_gleichzeitige_schreiber_vertauschen_nichts_und_werfen_nie(tmp_path):
    """Zwei Fäden wie im Lauf: der Blick schreibt ansicht.jpg, die GUI den
    Schalter, beide lesen zurück. Vorher (p12, 2000 Runden): über 800
    Ausnahmen je Schreiber und über 200 vertauschte Inhalte."""
    fehler, vertauscht = [], []
    ende = threading.Event()

    def bild():
        while not ende.is_set():
            try:
                atomar.schreibe_atomar(tmp_path / "ansicht.jpg", JPEG)
                if (tmp_path / "ansicht.jpg").read_bytes()[:1] == b"{":
                    vertauscht.append("jpg")
            except OSError:
                pass                                   # nur das LESEN darf kollidieren
            except Exception as e:                     # noqa: BLE001 - der Test zaehlt alles
                fehler.append(repr(e))

    def schalter():
        try:
            for i in range(300):
                try:
                    ansicht.schreibe(tmp_path, gesicht=bool(i % 2))
                except Exception as e:                 # noqa: BLE001
                    fehler.append(repr(e))
                try:
                    if (tmp_path / "ansicht.json").read_bytes()[:2] == JPEG[:2]:
                        vertauscht.append("json")
                except OSError:
                    pass
        finally:
            ende.set()

    faeden = [threading.Thread(target=bild), threading.Thread(target=schalter)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join(timeout=120)
    assert fehler == []
    assert vertauscht == []
    assert not list(tmp_path.glob("*.tmp")), "nichts bleibt liegen"


def test_derselbe_ziel_aus_zwei_faeden_wirft_nicht(tmp_path):
    fehler = []

    def schreiber(nummer):
        for i in range(200):
            try:
                atomar.schreibe_atomar(tmp_path / "fahrt.json", f'{{"n": {nummer}, "i": {i}}}')
            except Exception as e:                     # noqa: BLE001
                fehler.append(repr(e))

    faeden = [threading.Thread(target=schreiber, args=(n,)) for n in range(2)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join(timeout=120)
    assert fehler == []
    assert (tmp_path / "fahrt.json").read_text(encoding="utf-8").startswith('{"n": ')


def test_ein_fehlender_ordner_wirft_nicht(tmp_path):
    """Der Lauf ist schon aufgeräumt, die GUI schreibt noch einen Schalter:
    False, keine Ausnahme."""
    assert atomar.schreibe_atomar(tmp_path / "weg" / "ansicht.json", "{}") is False
    ansicht.schreibe(tmp_path / "weg", gesicht=True)            # wirft nicht
