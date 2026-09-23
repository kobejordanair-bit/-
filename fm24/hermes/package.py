"""Build a self-contained installer without workbooks, private paths or credentials."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile


def package(destination):
    here = Path(__file__).resolve().parent
    site = here.parent
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(prefix='fm24-hermes-package-') as temp:
        stage = Path(temp)
        skill = stage / 'fm24-screenshot-flow'
        shutil.copytree(here / 'skill', skill)
        runtime = skill / 'runtime'; runtime.mkdir()
        for pattern in ('*.py', '*.js', '*.css'):
            for source in site.glob(pattern):
                if not source.name.startswith('test_'):
                    shutil.copyfile(source, runtime / source.name)
        shutil.copyfile(site / 'template.html', runtime / 'template.html')
        (runtime / 'hermes').mkdir()
        shutil.copyfile(here / 'pipeline.py', runtime / 'hermes' / 'pipeline.py')
        shutil.copytree(here / 'engine', runtime / 'hermes' / 'engine', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(here / 'tests', runtime / 'hermes' / 'tests', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile(here / 'install.py', stage / 'install.py')
        shutil.copyfile(here / 'README.md', stage / 'README.md')
        if (here / 'VALIDATION.md').is_file():
            shutil.copyfile(here / 'VALIDATION.md', stage / 'VALIDATION.md')
        (skill / 'requirements.txt').write_text('openpyxl==3.1.5\nopencc-python-reimplemented==0.1.7\nPillow==12.3.0\n', encoding='utf-8')
        files = sorted(p for p in stage.rglob('*') if p.is_file())
        hashes = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        (stage / 'SHA256SUMS.json').write_text(json.dumps(hashes, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(stage).as_posix())
    return dict(file=str(destination.resolve()), sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), files=len(hashes) + 1)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('output', type=Path)
    print(json.dumps(package(p.parse_args().output), indent=2))
