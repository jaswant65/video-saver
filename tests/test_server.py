"""Exercise the real HTTP server using isolated, generated data (no user library)."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, ProxyHandler
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='video-saver-test-')
        cls.data_root = Path(cls.temp.name)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            cls.port = probe.getsockname()[1]
        cls.base = f'http://127.0.0.1:{cls.port}'
        cls.opener = build_opener(ProxyHandler({}))
        cls.log = (cls.data_root / 'test-server.log').open('w', encoding='utf-8')
        cls.start_server()

    @classmethod
    def start_server(cls):
        environment = {**os.environ, 'VIDEO_SAVER_DATA_DIR': str(cls.data_root)}
        cls.process = subprocess.Popen(
            [sys.executable, str(ROOT / 'server.py'), '--port', str(cls.port), '--local-only'],
            env=environment, stdout=cls.log, stderr=cls.log,
        )
        for attempt in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError('Test server exited; inspect temporary test logs.')
            try:
                cls.state = cls.request_json('/api/state')
                return
            except OSError:
                time.sleep(0.05)
        cls.stop_server()
        raise RuntimeError('Test server did not become ready.')

    @classmethod
    def stop_server(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.stop_server()
        cls.log.close()
        cls.temp.cleanup()

    @classmethod
    def request(cls, path, data=None, headers=None, method=None):
        return cls.opener.open(Request(cls.base + path, data=data, headers=headers or {}, method=method), timeout=10)

    @classmethod
    def request_json(cls, path, **kwargs):
        with cls.request(path, **kwargs) as response:
            return json.load(response)

    def upload(self, name='generated clip.mp4', content=None):
        payload = content if content is not None else b'generated file-transfer fixture\x00' + bytes(range(256)) * 8
        state = self.request_json('/api/state')
        result = self.request_json('/api/upload', data=payload,
                                   headers={'X-App-Key': state['csrf'], 'X-File-Name': quote(name)})
        jobs = self.request_json('/api/state')['jobs']
        return next(job for job in jobs if job['id'] == result['id']), payload

    def assert_status(self, expected, path, **kwargs):
        with self.assertRaises(HTTPError) as caught:
            self.request(path, **kwargs)
        self.assertEqual(caught.exception.code, expected)
        caught.exception.close()

    def test_static_page_and_assets(self):
        for path in ('/', '/app.js', '/style.css', '/favicon.svg'):
            with self.subTest(path=path), self.request(path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])

    def test_state_is_local_and_no_cache(self):
        with self.request('/api/state') as response:
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            state = json.load(response)
        self.assertEqual(state['app'], 'video-saver')
        self.assertEqual(state['version'], '1.0.0')
        self.assertEqual(state['links'], [self.base])
        self.assertGreater(len(state['csrf']), 20)

    def test_upload_library_download_and_seeking(self):
        job, payload = self.upload()
        self.assertEqual(job['status'], 'complete')
        self.assertEqual(job['size'], len(payload))
        with self.request(job['download_url']) as response:
            self.assertEqual(response.read(), payload)
            self.assertIn('attachment;', response.headers['Content-Disposition'])
        for range_value, expected in [('bytes=0-99', payload[:100]), ('bytes=100-', payload[100:]), ('bytes=-50', payload[-50:])]:
            with self.subTest(range=range_value), self.request(job['url'], headers={'Range': range_value}) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), expected)
                self.assertIn('bytes ', response.headers['Content-Range'])
        self.assert_status(416, job['url'], headers={'Range': f'bytes={len(payload)}-'})
        self.assert_status(416, job['url'], headers={'Range': 'bytes=-'})

    def test_filename_stays_in_generated_item_directory(self):
        job, _ = self.upload('../../outside.mp4')
        file = (self.data_root / 'library' / job['file']).resolve()
        self.assertEqual(file.parent.name, job['id'])
        self.assertTrue(file.is_relative_to((self.data_root / 'library').resolve()))
        self.assertEqual(file.name, 'outside.mp4')

    def test_reserved_windows_filename_is_portable(self):
        job, _ = self.upload('CON.mp4')
        self.assertTrue(job['file'].endswith('/_CON.mp4'))

    def test_private_files_are_not_exposed(self):
        for path in ('/library.sqlite3', '/server.py', '/.env', '/files/../server.py', '/files/%2e%2e/library.sqlite3'):
            with self.subTest(path=path):
                self.assert_status(404, path)

    def test_mutations_need_correct_token(self):
        for token in ('', 'wrong-key', '\u00e9'):
            with self.subTest(token=token):
                self.assert_status(403, '/api/upload', data=b'test',
                                   headers={'X-App-Key': token, 'X-File-Name': 'test.mp4'})

    def test_host_validation(self):
        self.assert_status(403, '/api/state', headers={'Host': 'untrusted.example'})
        self.assert_status(400, '/api/state', headers={'Host': '['})

    def test_invalid_uploads_are_rejected(self):
        token = self.request_json('/api/state')['csrf']
        for name, payload, extra in [('script.html', b'x', {}), ('empty.mp4', b'', {}),
                                      ('huge.mp4', b'x', {'Content-Length': str(8 * 1024 ** 3 + 1)})]:
            with self.subTest(name=name):
                self.assert_status(400, '/api/upload', data=payload,
                                   headers={'X-App-Key': token, 'X-File-Name': name, **extra})

    def test_invalid_link_payload_does_not_crash_server(self):
        token = self.request_json('/api/state')['csrf']
        for payload in (b'not json', b'[]', b'{"url":"file:///private/file.mp4"}'):
            with self.subTest(payload=payload):
                self.assert_status(400, '/api/download', data=payload, headers={'X-App-Key': token})
        self.assertEqual(self.request_json('/api/state')['app'], 'video-saver')

    def test_z_restart_preserves_finished_library(self):
        job, payload = self.upload('restart.mp4')
        old_csrf = self.request_json('/api/state')['csrf']
        self.stop_server()
        self.start_server()
        state = self.request_json('/api/state')
        self.assertNotEqual(state['csrf'], old_csrf)
        restored = next(item for item in state['jobs'] if item['id'] == job['id'])
        self.assertEqual(restored['status'], 'complete')
        with self.request(restored['url']) as response:
            self.assertEqual(response.read(), payload)

    @unittest.skipUnless(os.environ.get('VIDEO_SAVER_DOWNLOAD_SMOKE') == '1' and shutil.which('ffmpeg'),
                         'Optional: set VIDEO_SAVER_DOWNLOAD_SMOKE=1 with yt-dlp and FFmpeg installed.')
    def test_real_downloader_against_generated_local_video(self):
        self.assertTrue(self.request_json('/api/state')['downloader'], 'Install yt-dlp to run this optional check.')
        sample = self.data_root / 'generated-smoke.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
                        'color=c=green:s=320x180:r=12:d=1', '-f', 'lavfi', '-i', 'anullsrc', '-t', '1',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', '-y', str(sample)], check=True)
        job, _ = self.upload('generated-smoke.mp4', sample.read_bytes())
        state = self.request_json('/api/state')
        result = self.request_json('/api/download', data=json.dumps({'url': self.base + job['url'], 'quality': '1080'}).encode(),
                                   headers={'X-App-Key': state['csrf'], 'Content-Type': 'application/json'})
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            downloaded = next(j for j in self.request_json('/api/state')['jobs'] if j['id'] == result['id'])
            if downloaded['status'] in ('complete', 'failed'):
                break
            time.sleep(0.2)
        self.assertEqual(downloaded['status'], 'complete', downloaded['detail'])
        with self.request(downloaded['url']) as response:
            self.assertTrue(response.read())


if __name__ == '__main__':
    unittest.main()
