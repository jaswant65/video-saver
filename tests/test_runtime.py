from pathlib import Path
from unittest.mock import patch
import json
import sys
import tempfile
import unittest
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import runtime_support


class RuntimeTests(unittest.TestCase):
    def test_host_config_wins_and_explicitly_selects_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); exe=root/'node.exe'; exe.write_bytes(b'fixture')
            (root/'.local-settings.json').write_text(json.dumps({'node':str(exe)}),encoding='utf-8')
            with patch.dict('os.environ',{},clear=True),patch('runtime_support.shutil.which',return_value='other.exe'):
                args=runtime_support.runtime_arguments(root)
            self.assertEqual(args,['--no-js-runtimes','--js-runtimes','node:'+str(exe.resolve())])

    def test_missing_configured_binary_falls_back_to_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'.local-settings.json').write_text('{"node":"missing.exe"}')
            with patch.dict('os.environ',{},clear=True),patch('runtime_support.shutil.which',side_effect=lambda name:'deno.exe' if name=='deno' else None):
                self.assertEqual(runtime_support.runtime_arguments(root),['--no-js-runtimes','--js-runtimes','deno:deno.exe'])

    def test_bad_config_does_not_break_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'.local-settings.json').write_text('not json')
            with patch.dict('os.environ',{},clear=True),patch('runtime_support.shutil.which',return_value=None):
                self.assertEqual(runtime_support.runtime_arguments(root),[])

    def test_bot_check_is_clear_without_copying_cookie_instructions(self):
        text=runtime_support.explain_download_error('ERROR: Sign in to confirm you are not a bot. Use --cookies-from-browser')
        self.assertIn('YouTube blocked',text)
        self.assertNotIn('--cookies',text)

    def test_unicode_filename_is_recovered_from_successful_stop_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); file=root/'How He’d Make a Video.mp4'; file.write_bytes(b'fixture')
            probe=types.SimpleNamespace(returncode=0,stdout='{"format":{"duration":"10"},"streams":[{"codec_type":"video"}]}')
            with patch('runtime_support.shutil.which',return_value='ffprobe.exe'),patch('runtime_support.subprocess.run',return_value=probe):
                found=runtime_support.completed_video(root,root/'How He�d Make a Video.mp4',101,{'.mp4'})
            self.assertEqual(found,file)

    def test_failed_partial_ambiguous_and_external_outputs_are_not_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'one.mp4').write_bytes(b'one')
            self.assertIsNone(runtime_support.completed_video(root,None,1,{'.mp4'}))
            (root/'two.mp4').write_bytes(b'two')
            self.assertIsNone(runtime_support.completed_video(root,None,0,{'.mp4'}))
            self.assertIsNone(runtime_support.completed_video(root,root.parent/'private.mp4',0,{'.mp4'}))

    def test_intermediate_stream_is_not_a_completed_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'video.f398.mp4').write_bytes(b'video only')
            self.assertIsNone(runtime_support.completed_video(root,None,101,{'.mp4'}))


if __name__=='__main__': unittest.main()
