"""A small, dependency-free LAN video library. Run with Python 3.11+."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote, quote
import argparse
import importlib.util
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get('VIDEO_SAVER_DATA_DIR', ROOT)).resolve()
DATA_ROOT.mkdir(parents=True, exist_ok=True)
DATA = DATA_ROOT / 'library'
DATA.mkdir(exist_ok=True)
DB = DATA_ROOT / 'library.sqlite3'
MAX_SIZE = 8 * 1024 ** 3
VIDEO_EXTS = {'.mp4', '.webm', '.mkv', '.mov', '.m4v', '.avi', '.mpeg', '.mpg', '.3gp', '.ts', '.ogv'}
CSRF = secrets.token_urlsafe(32)
POOL = ThreadPoolExecutor(max_workers=2)
SLOTS = threading.BoundedSemaphore(20)
YTDLP = [sys.executable, '-m', 'yt_dlp'] if importlib.util.find_spec('yt_dlp') else ([shutil.which('yt-dlp')] if shutil.which('yt-dlp') else None)
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    return db


def initialize():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, title TEXT, status TEXT, progress REAL DEFAULT 0, detail TEXT DEFAULT "", file TEXT, size INTEGER DEFAULT 0, created REAL)')
        db.execute("UPDATE jobs SET status='failed', detail='The server stopped before this transfer finished. Please try again.' WHERE status IN ('queued','downloading','uploading')")


def update(job_id, **fields):
    with connect() as db:
        db.execute('UPDATE jobs SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', [*fields.values(), job_id])


def new_job(title, status):
    job_id = uuid.uuid4().hex
    with connect() as db:
        db.execute('INSERT INTO jobs(id,title,status,created) VALUES(?,?,?,?)', (job_id, title, status, time.time()))
    return job_id


def local_addresses():
    addresses = set()
    primary = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('192.0.2.1', 80))
            primary = s.getsockname()[0]
            addresses.add(primary)
    except OSError:
        pass
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    valid = sorted(a for a in addresses if ipaddress.ip_address(a).is_private and not a.startswith(('127.', '169.254.')))
    if primary in valid:
        valid.remove(primary)
        valid.insert(0, primary)
    return valid


def download(job_id, url, quality):
    folder = DATA / job_id
    folder.mkdir(exist_ok=True)
    update(job_id, status='downloading', detail='Finding video…')
    formats = {'best': 'bv*+ba/b', '1080': 'bv*[height<=?1080]+ba/b[height<=?1080]', '720': 'bv*[height<=?720]+ba/b[height<=?720]'}
    command = [*YTDLP, '--ignore-config', '--no-plugin-dirs', '--no-playlist', '--no-cache-dir',
               '--windows-filenames', '--no-colors', '--newline', '--progress', '--socket-timeout', '30',
               '--retries', '3', '--max-filesize', '8G', '--max-downloads', '1',
               '-f', formats[quality], '--merge-output-format', 'mp4', '--remux-video', 'mp4',
               '--progress-template', 'download:PROGRESS:%(progress._percent_str)s',
               '--print', 'after_move:FILE:%(filepath)s', '-o', str(folder / '%(title).160B.%(ext)s')]
    if shutil.which('node'):
        command += ['--js-runtimes', 'node:' + shutil.which('node')]
    if shutil.which('ffmpeg'):
        command += ['--ffmpeg-location', shutil.which('ffmpeg')]
    command += ['--', url]
    errors = []
    process = None
    timer = None
    final = None
    expired = threading.Event()
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace', creationflags=FLAGS)
        def timeout():
            expired.set()
            process.kill()
        timer = threading.Timer(3600, timeout)
        timer.daemon = True
        timer.start()
        for raw in process.stdout:
            line = raw.strip()
            if line.startswith('PROGRESS:'):
                match = re.search(r'([\d.]+)%', line)
                if match:
                    update(job_id, progress=float(match[1]), detail='Downloading video…')
            elif line.startswith('FILE:'):
                final = Path(line[5:]).resolve()
            elif 'ERROR:' in line:
                errors.append(line.split('ERROR:', 1)[1].strip()[:500])
            elif '[Merger]' in line or '[VideoRemuxer]' in line:
                update(job_id, detail='Preparing your video…')
        code = process.wait()
        if expired.is_set():
            raise ValueError('Download took longer than one hour. Try a shorter video.')
        if final and final.is_file() and final.is_relative_to(folder.resolve()) and final.suffix.lower() in VIDEO_EXTS:
            update(job_id, title=final.stem, status='complete', progress=100,
                   detail='Ready to watch or download', file=final.relative_to(DATA).as_posix(), size=final.stat().st_size)
        else:
            raise ValueError(errors[-1] if errors else ('This link could not be saved. Try a direct video link or another supported site. (Exit %s)' % code))
    except Exception as exc:
        update(job_id, status='failed', detail=str(exc)[:500])
    finally:
        if timer:
            timer.cancel()
        if process and process.poll() is None:
            process.kill()
        SLOTS.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'VideoSaver/1.0'

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        super().end_headers()

    def json(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        address = ipaddress.ip_address(self.client_address[0])
        if not (address.is_private or address.is_loopback):
            self.json({'error': 'This app is available on the local network only.'}, 403)
            return False
        # Reject unexpected Host values to prevent browser DNS rebinding into this LAN app.
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
        except ValueError:
            self.json({'error': 'Invalid host address.'}, 400)
            return False
        if host not in {'localhost', '127.0.0.1', socket.gethostname().lower(), *local_addresses()}:
            self.json({'error': 'Open this app using its local network address.'}, 403)
            return False
        return True

    def do_GET(self):
        try:
            self.get()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def get(self):
        if not self.allowed():
            return
        path = urlsplit(self.path).path
        if path == '/api/state':
            with connect() as db:
                jobs = [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY created DESC')]
            for job in jobs:
                if job['file']:
                    job['url'] = '/files/' + quote(job['file'])
                    job['download_url'] = job['url'] + '?download=1'
            addresses = ['127.0.0.1'] if self.server.server_address[0] == '127.0.0.1' else local_addresses()
            self.json({'app': 'video-saver', 'version': '1.0.0', 'jobs': jobs, 'csrf': CSRF, 'downloader': bool(YTDLP),
                       'links': ['http://%s:%s' % (a, self.server.server_port) for a in addresses],
                       'free': shutil.disk_usage(DATA).free, 'max_size': MAX_SIZE})
        elif path in ('/', '/app.js', '/style.css', '/favicon.svg'):
            name = 'index.html' if path == '/' else path[1:]
            self.serve_file(ROOT / name)
        elif path.startswith('/files/'):
            filename = unquote(path[len('/files/'):])
            with connect() as db:
                found = db.execute("SELECT file FROM jobs WHERE file=? AND status='complete'", (filename,)).fetchone()
            candidate = (DATA / filename).resolve()
            if not found or not candidate.is_relative_to(DATA.resolve()) or not candidate.is_file():
                self.json({'error': 'Video not found.'}, 404)
            else:
                self.serve_file(candidate, 'download=1' in urlsplit(self.path).query)
        else:
            self.json({'error': 'Not found'}, 404)

    def serve_file(self, path, attachment=False):
        size = path.stat().st_size
        start, end = 0, size - 1
        partial = False
        if self.headers.get('Range'):
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers['Range'])
            if not match or (not match[1] and not match[2]):
                self.send_error(416)
                return
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]), end) if match[2] else end
            else:
                start = max(0, size - int(match[2]))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%s' % size)
                self.end_headers()
                return
            partial = True
        self.send_response(206 if partial else 200)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(max(0, end - start + 1)))
        self.send_header('Accept-Ranges', 'bytes')
        if partial:
            self.send_header('Content-Range', 'bytes %s-%s/%s' % (start, end, size))
        if attachment:
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(path.name))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        with path.open('rb') as stream:
            stream.seek(start)
            left = end - start + 1
            while left > 0:
                block = stream.read(min(1024 * 1024, left))
                if not block:
                    break
                self.wfile.write(block)
                left -= len(block)

    def do_POST(self):
        if not self.allowed():
            return
        if not secrets.compare_digest(self.headers.get('X-App-Key', '').encode('utf-8'), CSRF.encode('utf-8')):
            self.json({'error': 'Refresh this page and try again.'}, 403)
            return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if length < 0 or self.headers.get('Transfer-Encoding'):
                raise ValueError('A known file size is required.')
            self.connection.settimeout(120)
            path = urlsplit(self.path).path
            if path == '/api/download':
                if not YTDLP:
                    raise ValueError('yt-dlp is not installed on the host computer.')
                if length > 16384:
                    raise ValueError('The link is too long.')
                request = json.loads(self.rfile.read(length))
                url = request.get('url', '').strip()
                parsed = urlsplit(url)
                if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError('Paste a valid http or https video link.')
                quality = request.get('quality', '1080')
                if quality not in ('best', '1080', '720'):
                    raise ValueError('Choose a valid quality.')
                if not SLOTS.acquire(blocking=False):
                    self.json({'error': 'The queue is full. Try again after a download finishes.'}, 429)
                    return
                job_id = None
                try:
                    job_id = new_job(parsed.hostname, 'queued')
                    POOL.submit(download, job_id, url, quality)
                except Exception:
                    SLOTS.release()
                    if job_id:
                        update(job_id, status='failed', detail='Could not start the download.')
                    raise
                self.json({'id': job_id}, 202)
            elif path == '/api/upload':
                self.upload(length)
            else:
                self.json({'error': 'Not found'}, 404)
        except (ValueError, TypeError, AttributeError) as exc:
            self.json({'error': str(exc)}, 400)
        except (OSError, sqlite3.Error) as exc:
            try:
                self.json({'error': 'Transfer failed: ' + str(exc)}, 500)
            except OSError:
                pass

    def upload(self, length):
        name = Path(unquote(self.headers.get('X-File-Name', 'video.mp4')).replace('\\', '/')).name
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')
        if Path(name).suffix.lower() not in VIDEO_EXTS:
            raise ValueError('Choose a video file such as MP4, MOV, MKV or WebM.')
        if not 0 < length <= MAX_SIZE:
            raise ValueError('Choose a video between 1 byte and 8 GB.')
        if shutil.disk_usage(DATA).free < length + 100 * 1024 ** 2:
            raise ValueError('There is not enough free space on the host computer.')
        stem = Path(name).stem[:100]
        if stem.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}:
            stem = '_' + stem
        name = stem + Path(name).suffix.lower()
        job_id = new_job(name, 'uploading')
        folder = DATA / job_id
        folder.mkdir()
        target = folder / name
        temporary = folder / 'upload.part'
        try:
            remaining = length
            last = 0
            with temporary.open('wb') as stream:
                while remaining:
                    block = self.rfile.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError('The upload was interrupted. Try again.')
                    stream.write(block)
                    remaining -= len(block)
                    if time.monotonic() - last > 0.7:
                        update(job_id, progress=100 * (length - remaining) / length)
                        last = time.monotonic()
            temporary.rename(target)
            update(job_id, title=target.stem, status='complete', progress=100, detail='Ready to watch or download',
                   file=target.relative_to(DATA).as_posix(), size=length)
            self.json({'id': job_id}, 201)
        except Exception:
            update(job_id, status='failed', detail='Upload interrupted. Please try again.')
            temporary.unlink(missing_ok=True)
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--local-only', action='store_true', help='Only accept connections from this computer.')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    try:
        server = ThreadingHTTPServer(('127.0.0.1' if args.local_only else '0.0.0.0', args.port), Handler)
    except OSError as exc:
        parser.exit(1, f'Could not start Video Saver on port {args.port}: {exc}\nTry another port with --port 8788.\n')
    initialize()
    print('Video Saver is running. Keep this computer awake.', flush=True)
    print('This computer: http://localhost:%s' % args.port, flush=True)
    for address in ([] if args.local_only else local_addresses()):
        print('Network link: http://%s:%s' % (address, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
