"""Install the isolated FM24 skill; never replace Hermes' existing import modules."""
from pathlib import Path
import argparse
import json
import hashlib
import os
import shutil
import subprocess
import sys
import venv


def install(bundle, hermes_home, registry, state, *, create_venv=True):
    bundle, hermes_home, registry, state = map(lambda x: Path(x).resolve(), (bundle, hermes_home, registry, state))
    if not hermes_home.is_dir():
        raise ValueError('HERMES_HOME_NOT_FOUND: run this on the computer/server where Hermes actually runs')
    if not registry.is_file():
        raise ValueError('ACTIVE_REGISTRY_NOT_FOUND: provide the current registry; do not guess a workbook')
    source = bundle / 'fm24-screenshot-flow'
    if not (source / 'SKILL.md').is_file():
        raise ValueError('BUNDLE_LAYOUT_INVALID')
    target = hermes_home / 'skills' / 'fm24-screenshot-flow'
    manifest = json.loads((bundle / 'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        file = (bundle / name).resolve()
        if not file.is_relative_to(bundle) or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError('BUNDLE_HASH_MISMATCH:' + name)
    if target.exists():
        for file in source.rglob('*'):
            if file.is_file():
                installed = target / file.relative_to(source)
                if not installed.is_file() or installed.read_bytes() != file.read_bytes():
                    raise ValueError('DIFFERENT_EXISTING_SKILL_PRESERVED:' + str(installed))
    else:
        shutil.copytree(source, target)
    python = Path(sys.executable)
    if create_venv:
        env = target / '.venv'
        python = env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(env)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(target / 'requirements.txt')], check=True)
    script = target / 'scripts' / 'fm24_pipeline.py'
    subprocess.run([str(python), '-m', 'unittest', 'discover', '-s', str(target / 'runtime' / 'hermes' / 'tests'), '-v'], check=True)
    if state.exists():
        config = json.loads((state / 'config.json').read_text(encoding='utf-8'))
        if Path(config['registry']).resolve() != registry:
            raise ValueError('EXISTING_STATE_POINTS_TO_DIFFERENT_REGISTRY')
        subprocess.run([str(python), str(script), 'doctor', '--config', str(state / 'config.json')], check=True)
    else:
        subprocess.run([str(python), str(script), 'configure', '--registry', str(registry), '--state', str(state)], check=True)
    info = dict(python=str(python), config=str(state / 'config.json'), installed=True,
                live_image_recognition_tested=False, public_deployment=False)
    (target / 'installation.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    return dict(skill=str(target), **info)


def main():
    p = argparse.ArgumentParser(description='Install FM24 screenshot flow on the existing Hermes host')
    p.add_argument('--hermes-home', type=Path, default=Path.home() / '.hermes')
    p.add_argument('--registry', type=Path, default=Path('/opt/data/FM24_World_Current.json'))
    p.add_argument('--state', type=Path, default=Path.home() / '.hermes' / 'fm24-flow')
    p.add_argument('--use-current-python', action='store_true', help='Use already installed compatible dependencies')
    args = p.parse_args()
    try:
        result = install(Path(__file__).resolve().parent, args.hermes_home, args.registry, args.state,
                         create_venv=not args.use_current_python)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps(dict(status='INSTALL_FAILED', error=str(exc)), ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
