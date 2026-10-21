"""Create a project-local Python environment without changing system packages."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Video Saver requires Python 3.11 or newer: https://www.python.org/downloads/')
    environment = ROOT / '.venv'
    print('Preparing the local Python environment...', flush=True)
    if not environment.is_dir():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', '--upgrade', '-r', str(ROOT / 'requirements.txt')], check=True)
    print('\nPython and the download engine are ready.')
    if not shutil.which('ffmpeg'):
        print('FFmpeg is still required for merging/remuxing downloaded videos.')
        print('Install it using the steps in README.md, then reopen your terminal.')
    if not (shutil.which('node') or shutil.which('deno')):
        print('Some video sites also need a JavaScript runtime; see README.md.')
    print('Windows: double-click Start.cmd. macOS/Linux: run ./start.sh')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit('Setup failed. Check your internet connection and Python installation.\n' + str(exc))
