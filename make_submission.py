"""Build the two CS239 submission archives into dist/.

    python make_submission.py --name <name> --uid <uid> [--app financial-advisor]

{name}-{appName}-{uid}-requirements.tar.gz   {appName}/ app.md, policy.md, tools.md, agents/, episodes/
{name}-{appName}-{uid}-whole.tar.gz          src/ (README.md, code, data, docs, traces) and tests/

Regenerates the agent files from app.py and runs the tests first; stops if any test fails.
"""
import argparse
import io
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP = {'__pycache__', '.venv', 'charts', 'dist'}
# The demo video is submitted separately, never inside an archive.
MEDIA = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.wmv'}


def add_tree(tar: tarfile.TarFile, source: Path, arcname: str, skip_files=()):
    for path in sorted(source.rglob('*')):
        rel = path.relative_to(source)
        if (path.is_file() and not SKIP.intersection(rel.parts) and path.name not in skip_files
                and path.suffix.lower() not in MEDIA):
            tar.add(path, f'{arcname}/{rel.as_posix()}')


def add_bytes(tar: tarfile.TarFile, arcname: str, data: bytes):
    info = tarfile.TarInfo(arcname)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', required=True, help='Your name as the course asks for it (no spaces)')
    parser.add_argument('--uid', required=True, help='Your UID')
    parser.add_argument('--app', default='financial-advisor', help='appName (default: financial-advisor)')
    args = parser.parse_args()
    for label, value in [('name', args.name), ('uid', args.uid), ('app', args.app)]:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
            parser.error(f'--{label} may contain only letters, digits, ".", "_" and "-"')

    subprocess.run([sys.executable, '-m', 'phase1.describe'], cwd=ROOT, check=True)
    tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', 'tests'], cwd=ROOT)
    if tests.returncode:
        parser.exit(1, 'Tests failed; no archives written.\n')

    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    stem = f'{args.name}-{args.app}-{args.uid}'

    requirements = dist / f'{stem}-requirements.tar.gz'
    with tarfile.open(requirements, 'w:gz') as tar:
        description = ROOT / 'description'
        tar.add(description / 'app.md', f'{args.app}/app.md')
        tar.add(ROOT / 'policy.md', f'{args.app}/policy.md')
        tar.add(description / 'tools.md', f'{args.app}/tools.md')
        add_tree(tar, description / 'agents', f'{args.app}/agents')
        add_tree(tar, description / 'episodes', f'{args.app}/episodes')

    whole = dist / f'{stem}-whole.tar.gz'
    with tarfile.open(whole, 'w:gz') as tar:
        for name in ('README.md', 'requirements.txt', 'requirements.md', 'policy.md', '.gitignore'):
            tar.add(ROOT / name, f'src/{name}')
        add_tree(tar, ROOT / 'phase1', 'src/phase1')
        add_tree(tar, ROOT / 'description', 'src/description')
        add_tree(tar, ROOT / 'traces', 'src/traces', skip_files={'tool_calls.jsonl'})
        # Ship the starting data, whatever live runs have changed since.
        seed = ROOT / 'data' / 'seed'
        add_tree(tar, ROOT / 'data', 'src/data',
                 skip_files={p.name for p in seed.glob('*.json')} | {'tool_calls.jsonl'})
        for path in sorted(seed.glob('*.json')):
            add_bytes(tar, f'src/data/{path.name}', path.read_bytes())
            add_bytes(tar, f'src/data/seed/{path.name}', path.read_bytes())
        add_tree(tar, ROOT / 'tests', 'tests')

    for archive in (requirements, whole):
        print(f'Wrote {archive.relative_to(ROOT)} ({archive.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
