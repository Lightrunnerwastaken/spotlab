import io

import pytest

pytest.importorskip("PySide6.QtCore")

from spotlab.gui.workers import DoctorWorker, OutputReader  # noqa: E402
from spotlab.workshop.doctor import Check  # noqa: E402


class FakeProzess:
    def __init__(self, zeilen, returncode=0):
        self.stdout = io.StringIO("".join(z + "\n" for z in zeilen))
        self.returncode = returncode

    def wait(self):
        return self.returncode


def test_doctor_worker_meldet_ergebnisse(qapp, monkeypatch):
    pruefungen = [Check("Netz", True, "antwortet")]
    monkeypatch.setattr("spotlab.gui.workers.diagnose", lambda: pruefungen)

    empfangen = []
    worker = DoctorWorker()
    worker.fertig.connect(empfangen.append)
    worker.run()  # direkt aufrufen, ohne Thread zu starten

    assert empfangen == [pruefungen]


def test_doctor_worker_faengt_ausnahmen(qapp, monkeypatch):
    def kaputt():
        raise RuntimeError("Netz weg")

    monkeypatch.setattr("spotlab.gui.workers.diagnose", kaputt)

    fehler = []
    worker = DoctorWorker()
    worker.fehler.connect(fehler.append)
    worker.run()

    assert fehler and "Netz weg" in fehler[0]


def test_ausgabe_leser_gibt_zeilen_weiter(qapp):
    empfangen = []
    enden = []
    leser = OutputReader(FakeProzess(["Akku: 87 %", "Fertig."], returncode=0))
    leser.zeile.connect(empfangen.append)
    leser.ende.connect(enden.append)
    leser.run()

    assert empfangen == ["Akku: 87 %", "Fertig."]
    assert enden == [0]


def test_ausgabe_leser_ohne_pipe(qapp):
    class OhnePipe:
        stdout = None

        def wait(self):
            return 1

    enden = []
    leser = OutputReader(OhnePipe())
    leser.ende.connect(enden.append)
    leser.run()  # darf nicht werfen

    assert enden == [1]
