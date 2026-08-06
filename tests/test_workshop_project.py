import pytest

from spotlab.workshop.project import create_project


def test_projekt_hat_alle_teile(tmp_path):
    ordner = create_project("mein-spot", tmp_path)
    assert (ordner / "hallo_spot.py").exists()
    assert (ordner / "README.md").exists()
    assert (ordner / ".vscode" / "settings.json").exists()
    assert (ordner / "runs").is_dir()


def test_vorlage_ist_lauffaehiges_python(tmp_path):
    quelle = (create_project("p", tmp_path) / "hallo_spot.py").read_text(encoding="utf-8")
    compile(quelle, "hallo_spot.py", "exec")
    assert "spotlab.connect()" in quelle
    assert "power_on()" in quelle


def test_vorlage_laeuft_im_trockenlauf_durch(tmp_path, monkeypatch):
    """Das generierte README empfiehlt --dryrun zum Üben ohne Roboter.

    Also MUSS die Vorlage in diesem Modus durchlaufen. Vorher stürzte sie an
    spot.camera() ab, weil der Trockenlauf keine Kameras hat.
    """
    ordner = create_project("p", tmp_path)
    monkeypatch.setenv("SPOTLAB_BACKEND", "dryrun")
    monkeypatch.chdir(ordner)
    quelle = (ordner / "hallo_spot.py").read_text(encoding="utf-8")
    exec(compile(quelle, "hallo_spot.py", "exec"), {"__name__": "__main__"})


def test_bestehender_ordner_wird_nicht_ueberschrieben(tmp_path):
    create_project("p", tmp_path)
    with pytest.raises(FileExistsError):
        create_project("p", tmp_path)


def test_name_wird_entschaerft(tmp_path):
    ordner = create_project("Mein Spot/Projekt", tmp_path)
    assert ordner.parent == tmp_path
    assert "/" not in ordner.name
