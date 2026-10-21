"""Build the standalone Windows EXE from explicitly selected application assets."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    if os.name != 'nt':
        raise SystemExit('El ejecutable de Windows se debe compilar en Windows.')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile',
        '--windowed', '--noupx', '--name', 'PhDex', '--icon', str(ROOT/'PhDex.ico'),
        '--version-file', str(ROOT/'windows_version.txt'),
        '--additional-hooks-dir', str(ROOT/'build_hooks'),
        '--distpath', str(ROOT/'dist'), '--workpath', str(ROOT/'build'),
        '--specpath', str(ROOT/'build'),
        '--add-data', str(ROOT/'web')+os.pathsep+'web',
        '--add-data', str(ROOT/'referencias')+os.pathsep+'referencias',
        str(ROOT/'app.py')]
    # Some bundled Python runtimes load this trust-policy resource in SSLContext.
    # Preserve it in the frozen layout; never bypass TLS verification.
    import ssl
    trust_policy=Path(ssl.__file__).with_name('codex-rejected-cas.pem')
    if trust_policy.is_file():
        command[-1:-1]=['--add-data',str(trust_policy)+os.pathsep+'.']
    # The build includes no databases, preferences, library, logs or scientific data.
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
