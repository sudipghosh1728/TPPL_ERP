"""Build the pinned corporate site and ERP into one static deployment output.

No database access, initialization, demo seeding or private environment copying.
"""
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
SITE = ROOT / 'TPPL'
OUTPUT = ROOT / 'web-dist'

def build():
    if not (SITE / 'package.json').is_file():
        raise SystemExit('Corporate source missing. Run git submodule update --init TPPL.')
    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm:
        raise SystemExit('Node/npm is required to build the corporate website.')
    subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd=SITE, check=True)
    subprocess.run([npm, 'run', 'build'], cwd=SITE, check=True)
    # The output is disposable and confined to this explicit repository path.
    resolved = OUTPUT.resolve()
    if resolved.parent != ROOT or resolved.name != 'web-dist':
        raise SystemExit('Unexpected build output path.')
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    shutil.copytree(SITE / 'dist', OUTPUT)
    for source in (ROOT / 'public').iterdir():
        if source.name == 'website':
            continue
        destination = OUTPUT / ('erp.html' if source.name == 'index.html' else source.name)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)
    for file in ('index.html', 'login.html', 'erp.html', 'projects.js'):
        if not (OUTPUT / file).is_file():
            raise SystemExit('Missing deployment asset: ' + file)
    print('Combined website and ERP built in web-dist. No database records changed.')

if __name__ == '__main__':
    build()
