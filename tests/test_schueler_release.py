import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'tools/schueler_release.py'
if not SOURCE.exists():
    SOURCE = Path(__file__).with_name('schueler_release.py')
spec = importlib.util.spec_from_file_location('schueler_release', SOURCE)
release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = release
spec.loader.exec_module(release)


def test_research_modules_are_excluded():
    assert not release.MODULES & {'gates', 'sdk_real', 'explorer', 'mapping', 'planning', 'metrics', 'schritt'}


@pytest.mark.parametrize('source', ['from spotsim.gates import GATES',
                                   'from spotsim import explorer', 'import spotsim.sdk_real'])
def test_unknown_dependency_aborts(source):
    with pytest.raises(ValueError, match='outside allowlist'):
        release.validate_imports(source)


def test_nested_runtime_imports_are_allowed():
    release.validate_imports('def f():\n    from spotsim.local_grid import local_grid_proto')


def test_model_closure_excludes_unused_arm(tmp_path):
    (tmp_path/'LICENSE').write_text('License', encoding='utf-8')
    (tmp_path/'scene.xml').write_text('<mujoco><include file="spot.xml"/></mujoco>', encoding='utf-8')
    (tmp_path/'spot.xml').write_text('<mujoco><compiler meshdir="assets"/><asset><mesh file="leg.obj"/></asset></mujoco>', encoding='utf-8')
    (tmp_path/'assets').mkdir()
    (tmp_path/'assets/leg.obj').write_text('mesh', encoding='utf-8')
    (tmp_path/'assets/arm.obj').write_text('unused', encoding='utf-8')
    assert release.model_files(tmp_path) == ['LICENSE', 'assets/leg.obj', 'scene.xml', 'spot.xml']


def test_asset_path_cannot_escape(tmp_path):
    (tmp_path/'scene.xml').write_text('<mujoco><include file="../private.xml"/></mujoco>', encoding='utf-8')
    (tmp_path/'spot.xml').write_text('<mujoco/>', encoding='utf-8')
    with pytest.raises(ValueError):
        release.model_files(tmp_path)


def test_release_launcher_uses_own_environment(tmp_path):
    shell = shutil.which('powershell')
    if shell is None:
        pytest.skip('PowerShell not installed')
    launcher = ROOT/'starten.ps1'
    if not launcher.exists():
        launcher = Path(__file__).with_name('starten.ps1')
    shutil.copyfile(launcher, tmp_path/'starten.ps1')
    (tmp_path/'release.json').write_text('{}', encoding='utf-8')
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', str(tmp_path/'starten.ps1'), '-NurPruefen'],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'einrichten.ps1' in result.stdout
