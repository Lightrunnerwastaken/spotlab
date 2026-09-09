import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_reference_covers_public_facade():
    tree = ast.parse((ROOT / 'src/spotlab/api/spot.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    reference = (ROOT / 'docs/API.md').read_text(encoding='utf-8')
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
            assert '`' + node.name in reference


@pytest.mark.parametrize('name', ['zustand_lesen', 'umgebung_lesen', 'licht_und_ton',
                                  'koerper_ausrichten', 'tiefenbild_lesen', 'punktwolke_speichern',
                                  'localgrids_lesen'])
def test_new_examples_without_robot(name, tmp_path):
    env = dict(os.environ, SPOTLAB_BACKEND='dryrun', SPOTLAB_NUR_TROCKEN='1',
               PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1')
    source = ROOT / 'src/spotlab/workshop/beispiele' / (name + '.py')
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())
    result = subprocess.run([sys.executable, str(target)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert list((tmp_path / 'runs').glob('*/lauf.json'))
