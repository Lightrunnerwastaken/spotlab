"""Das Diagnose-Protokoll: fuer das, was die Abbaupfade sonst verschlucken."""

from spotlab import protokoll


def test_ohne_ziel_wird_nichts_geschrieben(tmp_path):
    """Ein Import von spotlab soll nirgends eine Datei anlegen."""
    protokoll.setze_ziel(None)
    protokoll.notiere("egal")
    assert list(tmp_path.iterdir()) == []


def test_mit_ziel_landet_die_zeile_in_der_datei(tmp_path):
    protokoll.setze_ziel(tmp_path)
    try:
        protokoll.notiere("Lease-Rueckgabe gescheitert")
    finally:
        protokoll.setze_ziel(None)
    text = (tmp_path / protokoll.DATEINAME).read_text(encoding="utf-8")
    assert "Lease-Rueckgabe gescheitert" in text
    assert "pid=" in text


def test_die_ausnahme_kommt_mit_stapelspur(tmp_path):
    protokoll.setze_ziel(tmp_path)
    try:
        try:
            raise RuntimeError("Funk weg")
        except RuntimeError as fehler:
            protokoll.notiere("power_off gescheitert", fehler)
    finally:
        protokoll.setze_ziel(None)
    text = (tmp_path / protokoll.DATEINAME).read_text(encoding="utf-8")
    assert "RuntimeError: Funk weg" in text
    assert "Traceback" in text


def test_notieren_wirft_nie(tmp_path):
    """Es laeuft in Abbaupfaden, in denen schon etwas schiefging."""
    protokoll.setze_ziel(tmp_path / "gibtsnicht" / "\x00ungueltig")
    try:
        protokoll.notiere("darf nicht werfen")
    finally:
        protokoll.setze_ziel(None)


def test_nie_auf_stdout(capsys, tmp_path):
    """Die Ausgabe eines Laufs hat genau EINEN Leser, und der MCP-Server
    spricht ueber stdout ein Protokoll. Ein StreamHandler zerstoerte beides."""
    protokoll.setze_ziel(tmp_path)
    try:
        protokoll.notiere("still")
    finally:
        protokoll.setze_ziel(None)
    gefangen = capsys.readouterr()
    assert gefangen.out == "" and gefangen.err == ""
