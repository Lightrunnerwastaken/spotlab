"""Die Erkennermodelle aus dem Schueler-ZIP dorthin legen, wo spotlab sucht.

Laeuft am Ende von `einrichten.cmd`, in der eigenen `.venv`. Kopiert wird nur,
was fehlt oder anders ist -- ein alter git-lfs-Zeiger (132 Byte) wird ersetzt,
eine gleiche Datei bleibt stehen. Danach fragt es spotlab selbst, ob Gesicht,
Koerper und Hand ihre Modelle finden.
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

LIZENZ = 'LIZENZEN.txt'


def _summe(pfad):
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def einrichten(quelle, ziel):
    """Kopiert die Modelle von `quelle` nach `ziel`; gibt die Namen der kopierten zurueck."""
    quelle, ziel = Path(quelle), Path(ziel)
    dateien = sorted(quelle.glob('*.onnx')) if quelle.is_dir() else []
    if not dateien:
        raise FileNotFoundError(f'Keine Modelle im Ordner {quelle} -- ist das ZIP vollstaendig entpackt?')
    ziel.mkdir(parents=True, exist_ok=True)
    kopiert = []
    for datei in dateien:
        vorhanden = ziel/datei.name
        if vorhanden.is_file() and _summe(vorhanden) == _summe(datei):
            continue
        shutil.copyfile(datei, vorhanden)
        kopiert.append(datei.name)
    if (quelle/LIZENZ).is_file():
        shutil.copyfile(quelle/LIZENZ, ziel/LIZENZ)
    return kopiert


def main(argv=None):
    from spotlab.backends.real import gesicht, gesten, koerper

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quelle', type=Path, default=Path(__file__).resolve().parent/'modelle')
    parser.add_argument('--ziel', type=Path, default=gesicht.MODELL_ORDNER)
    args = parser.parse_args(argv)
    kopiert = einrichten(args.quelle, args.ziel)
    print(f'Modelle in {args.ziel}: {len(kopiert)} neu abgelegt.' if kopiert
          else f'Modelle in {args.ziel}: schon vorhanden.')
    fehlend = []
    for name, suche in (('Gesicht', lambda: gesicht.modellpfad(umgebung={}, pfad=args.ziel/gesicht.MODELL_DATEI)),
                        ('Koerper', lambda: koerper.modellpfade(args.ziel, umgebung={})),
                        ('Hand', lambda: gesten.modellpfade(args.ziel, umgebung={}))):
        try:
            suche()
        except Exception as fehler:     # noqa: BLE001 -- jede Meldung soll sichtbar werden
            fehlend.append(f'{name}: {fehler}')
    for zeile in fehlend:
        print(zeile)
    if fehlend:
        return 1
    print('Gesicht, Koerper und Hand finden ihre Modelle.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
