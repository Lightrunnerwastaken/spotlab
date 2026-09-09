"""Developer: build a GUI + sim release without distributing the research repo.

Only explicit runtime modules and model-referenced assets enter the sim wheel.
Run with a build environment containing setuptools and wheel; no robot access.
"""
import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

MODULES = frozenset('puppe sensors local_grid kinematics sim interpreter posture stability '
                    'sdk_sim trot terrain_sdk terrain_step contact_metrics detect'.split())
ASSETS_PY = '''"""Robot model shipped inside the runtime wheel."""
from pathlib import Path
SPOT_DIR = str(Path(__file__).resolve().parent / "model")
def spot_scene_path():
    return str(Path(SPOT_DIR) / "scene.xml")
def spot_xml_path():
    return str(Path(SPOT_DIR) / "spot.xml")
def spot_asset_available():
    return Path(spot_scene_path()).is_file()
'''
INIT_PY = '''"""Spotlab simulation runtime, distributed separately from research tools."""
from spotsim.assets import spot_asset_available, spot_scene_path, spot_xml_path
__all__ = ["spot_asset_available", "spot_scene_path", "spot_xml_path"]
'''


def version(repo):
    tree = ast.parse((repo/'src/spotlab/__init__.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('spotlab version missing')


def validate_imports(source):
    allowed = MODULES | {'assets'}
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = ([f'spotsim.{a.name}' for a in node.names] if node.module == 'spotsim' else [node.module])
        for name in names:
            if name.startswith('spotsim.') and name.split('.')[1] not in allowed:
                raise ValueError(f'Runtime dependency outside allowlist: {name}')


def model_files(model):
    """Only the XML include closure and referenced meshes/textures, never arm assets."""
    found = {'LICENSE'}
    pending = ['scene.xml', 'spot.xml']
    while pending:
        relative = pending.pop()
        if relative in found:
            continue
        path = (model/relative).resolve()
        if not path.is_relative_to(model.resolve()):
            raise ValueError('Asset path outside model')
        tree = ET.parse(path)
        found.add(relative)
        compiler = tree.find('compiler')
        for element in tree.iter():
            name = element.get('file')
            if not name:
                continue
            prefix = ''
            if element.tag in ('mesh', 'texture') and compiler is not None:
                prefix = compiler.get('meshdir' if element.tag == 'mesh' else 'texturedir', '')
            item = (path.parent/prefix/name).resolve()
            if not item.is_relative_to(model.resolve()) or not item.is_file():
                raise ValueError(f'Missing/invalid model asset: {name}')
            rel = item.relative_to(model.resolve()).as_posix()
            if element.tag == 'include':
                pending.append(rel)
            else:
                found.add(rel)
    return sorted(found)


def runtime(research, target, release_version):
    package = target/'src/spotsim'
    package.mkdir(parents=True)
    hashes = {}
    for name in sorted(MODULES):
        path = research/f'src/spotsim/{name}.py'
        data = path.read_bytes()
        validate_imports(data.decode('utf-8'))
        (package/path.name).write_bytes(data)
        hashes[path.name] = hashlib.sha256(data).hexdigest()
    (package/'__init__.py').write_text(INIT_PY, encoding='utf-8')
    (package/'assets.py').write_text(ASSETS_PY, encoding='utf-8')
    model = research/'assets/mujoco_menagerie/boston_dynamics_spot'
    for name in model_files(model):
        destination = package/'model'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(model/name, destination)
        hashes[f'model/{name}'] = hashlib.sha256(destination.read_bytes()).hexdigest()
    (package/'provenance.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    (target/'pyproject.toml').write_text(f'''[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"
[project]
name = "spotlab-sim-runtime"
version = "{release_version}"
description = "Simulation runtime and robot model for Spotlab"
requires-python = ">=3.11,<3.15"
dependencies = ["mujoco>=3.9,<4", "numpy>=2,<3", "scipy>=1.12,<2", "bosdyn-client==5.0.1.2", "bosdyn-api==5.0.1.2"]
[tool.setuptools.packages.find]
where = ["src"]
[tool.setuptools.package-data]
spotsim = ["provenance.json", "model/*", "model/assets/*"]
''', encoding='utf-8')


def build(repo, research, output):
    release_version = version(repo)
    output.mkdir(parents=True, exist_ok=True)
    archive = output/f'spotlab-{release_version}-schueler.zip'
    if archive.exists():
        raise FileExistsError(f'Release exists; increment version or choose another output: {archive}')
    with tempfile.TemporaryDirectory(prefix='spotlab-release-') as temporary:
        work = Path(temporary)
        app = work/'app'
        (app/'src').mkdir(parents=True)
        shutil.copytree(repo/'src/spotlab', app/'src/spotlab',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'runs'))
        shutil.copyfile(repo/'pyproject.toml', app/'pyproject.toml')
        runtime(research, work/'runtime', release_version)
        bundle = work/f'spotlab-{release_version}'
        wheels = bundle/'wheels'
        wheels.mkdir(parents=True)
        for project in (app, work/'runtime'):
            subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                            '--wheel-dir', str(wheels), str(project)], check=True)
        for name in ('einrichten.ps1', 'einrichten.cmd', 'starten.ps1', 'verknuepfung.ps1', 'spotlab.ico'):
            shutil.copyfile(repo/name, bundle/name)
        shutil.copyfile(repo/'docs/INSTALLATION_SCHULE.md', bundle/'ANLEITUNG.md')
        shutil.copyfile(repo/'tools/pruefe_schueler.py', bundle/'pruefe_schueler.py')
        app_wheel = next(wheels.glob('spotlab-*.whl')).name
        sim_wheel = next(wheels.glob('spotlab_sim_runtime-*.whl')).name
        requirements = f'./wheels/{app_wheel}[gui,sim]\n./wheels/{sim_wheel}\n'
        (bundle/'schueler-requirements.txt').write_text(requirements, encoding='utf-8')
        # No dev/MCP dependencies are requested, but normal optional extras remain
        # available in package metadata for developers.
        metadata = tomllib.loads((app/'pyproject.toml').read_text(encoding='utf-8'))
        report = {'version': release_version, 'extras': ['gui', 'sim'],
                  'dependencies': metadata['project']['dependencies'],
                  'files': {p.relative_to(bundle).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in bundle.rglob('*') if p.is_file()}}
        (bundle/'release.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        with ZipFile(archive, 'w', ZIP_DEFLATED) as zipped:
            for path in bundle.rglob('*'):
                if path.is_file():
                    zipped.write(path, path.relative_to(work).as_posix())
    print(f'Release: {archive} ({archive.stat().st_size / 1024**2:.1f} MiB; dependencies downloaded during setup)')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--sim-quelle', type=Path, required=True)
    parser.add_argument('--ausgabe', type=Path, default=Path('dist'))
    args = parser.parse_args()
    build(args.repo.resolve(), args.sim_quelle.resolve(), args.ausgabe.resolve())
