import io,json
import ssl
from urllib.error import URLError
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import UserError
from updater import Updater,release_info,version_tuple,github_url,REPOSITORY
from app import LocalApp
from updater import request_github


def release(tag='v2.1.0',size=2048):
    return {'tag_name':tag,'draft':False,'prerelease':False,'assets':[{'name':'PhDex.exe','state':'uploaded','size':size,'browser_download_url':'https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/PhDex.exe'}]}


class UpdateTests(unittest.TestCase):
    def test_network_errors_distinguish_missing_resources_and_certificates(self):
        for reason,message in ((FileNotFoundError('missing'),'recurso'),(ssl.SSLCertVerificationError('invalid'),'certificado'),(OSError('offline'),'conectar')):
            with patch('updater.build_opener') as opener:
                opener.return_value.open.side_effect=URLError(reason)
                with self.assertRaisesRegex(UserError,message):request_github('https://api.github.com/repos/RpastranaE/PhDex/releases/latest')

    def test_build_preserves_runtime_tls_resource(self):
        import build_exe
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);policy=folder/'codex-rejected-cas.pem';policy.write_text('synthetic fixture')
            with patch('ssl.__file__',str(folder/'ssl.py')),patch('build_exe.subprocess.run') as run:
                build_exe.main()
            command=run.call_args.args[0]
            self.assertIn(str(policy)+__import__('os').pathsep+'.',command)
            self.assertEqual(command[-1],str(build_exe.ROOT/'app.py'))
    def test_release_version_comparison_no_downgrade_and_invalid_payloads(self):
        self.assertTrue(release_info(release(),'2.0.0')['available'])
        self.assertFalse(release_info(release(),'2.1.0')['available'])
        self.assertFalse(release_info(release(),'2.2.0')['available'])
        self.assertGreater(version_tuple('v2.10.0'),version_tuple('2.9.0'))
        for value in ('main','2.1','v2.2.0-beta','2.1.0.exe'):
            with self.assertRaises(UserError):version_tuple(value)
        for payload in ({'draft':True},release('v2.2.0-beta'),{**release(),'assets':[]},{**release(),'prerelease':True}):
            with self.assertRaises(UserError):release_info(payload)
        payload=release();payload['assets'][0]['browser_download_url']='https://example.com/PhDex.exe'
        with self.assertRaises(UserError):release_info(payload)

    def test_github_download_redirects_remain_https_and_on_known_hosts(self):
        for url in ('http://github.com/file','https://github.com.evil.test/file','https://user:pass@github.com/file','https://api.github.com:444/file','file:///tmp/file'):
            with self.assertRaises(UserError):github_url(url)
        self.assertEqual(github_url('https://release-assets.githubusercontent.com/path?token=signed'),'https://release-assets.githubusercontent.com/path?token=signed')

    def test_download_complete_size_format_and_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            updater=Updater(tmp,current='2.0.0');payload=release();binary=b'MZ'+b'x'*2046
            with patch('updater.request_github',side_effect=[io.BytesIO(json.dumps(payload).encode()),io.BytesIO(binary)]):
                stage,info=updater.download()
            self.assertEqual(stage.read_bytes(),binary)
            self.assertEqual(info['latest'],'2.1.0')
            for data in (binary[:-1],binary+b'x',b'XX'+binary[2:]):
                with patch('updater.request_github',side_effect=[io.BytesIO(json.dumps(payload).encode()),io.BytesIO(data)]):
                    with self.assertRaises(UserError):updater.download()
            self.assertEqual(list(updater.directory.glob('*/PhDex.exe')),[stage])
            with patch('updater.request_github',return_value=io.BytesIO(b'bad json')):
                with self.assertRaises(UserError):updater.check()

    def test_automatic_setting_survives_restart_and_corrupt_file_disables_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            updater=Updater(tmp)
            self.assertTrue(updater.automatic())
            updater.set_automatic(False)
            self.assertFalse(Updater(tmp).automatic())
            with self.assertRaises(UserError):updater.set_automatic('true')
            (Path(tmp)/'actualizador.json').write_text('broken')
            self.assertFalse(updater.automatic())

    def test_install_guard_source_confirmation_busy_and_multiple_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=LocalApp(tmp)
            with self.assertRaises(UserError):app.start_update(False)
            with self.assertRaises(UserError):app.start_update(True)
            with patch('app.sys.frozen',True,create=True):
                app.jobs['copy']={'state':'running'}
                with self.assertRaises(UserError):app.start_update(True)
                app.jobs.clear();app.clients={'one','two'}
                with self.assertRaises(UserError):app.start_update(True)

if __name__=='__main__':unittest.main()
