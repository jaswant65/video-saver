"""Host-only downloader runtime settings. Never imports browser sessions."""
from pathlib import Path
import json
import os
import shutil
import math
import re
import subprocess


def runtime_arguments(root):
    config={}
    try:
        config=json.loads((Path(root)/'.local-settings.json').read_text(encoding='utf-8'))
        if not isinstance(config,dict): config={}
    except (OSError,ValueError):
        pass
    # Only host-local configuration may choose an executable; no LAN API does.
    for kind in ('node','deno'):
        configured=os.environ.get('VIDEO_SAVER_'+kind.upper()) or config.get(kind)
        if isinstance(configured,str) and configured.strip() and Path(configured).is_file():
            return ['--no-js-runtimes','--js-runtimes',kind+':'+str(Path(configured).resolve())]
    for kind in ('node','deno'):
        found=shutil.which(kind)
        if found:
            return ['--no-js-runtimes','--js-runtimes',kind+':'+found]
    return []


def explain_download_error(message):
    text=str(message)
    lower=text.lower()
    if 'sign in to confirm' in lower or 'not a bot' in lower:
        return ('YouTube blocked this request with a sign-in or bot-verification check. '
                'This video was not saved. An explicitly authorized YouTube session may be needed if the restriction persists.')
    if 'javascript runtime' in lower or 'challenge solving failed' in lower:
        return 'YouTube download support needs attention on the host computer. Check the JavaScript runtime setup.'
    return text[:500]


def completed_video(folder, reported, code, extensions):
    """Accept a finished file only after validating its bounded path and media."""
    folder=Path(folder).resolve()
    if code not in (0,101): return None
    candidates=[]
    if reported:
        path=Path(reported).resolve()
        if path.is_relative_to(folder) and path.is_file() and path.suffix.lower() in extensions:
            candidates=[path]
    if not candidates:
        candidates=[p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in extensions
                    and not re.search(r'\.f\d+(?:[.-]|$)',p.stem) and not p.stem.endswith('.temp')]
    if len(candidates)!=1: return None
    path=candidates[0]
    if not path.resolve().is_relative_to(folder): return None
    probe=shutil.which('ffprobe')
    if not probe: return path if reported and Path(reported).resolve()==path else None
    try:
        result=subprocess.run([probe,'-v','error','-show_entries','format=duration:stream=codec_type','-of','json',str(path)],
                              capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        info=json.loads(result.stdout); duration=float(info['format']['duration'])
        if result.returncode==0 and math.isfinite(duration) and duration>0 and any(s.get('codec_type')=='video' for s in info['streams']):
            return path
    except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired): pass
    return None
