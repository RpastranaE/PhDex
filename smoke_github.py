"""Check GitHub HTTPS from the packaged EXE, using only temporary application data."""
from pathlib import Path
import json,subprocess,tempfile,time,os,sys
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from updater import VERSION


def check_github(executable):
    with tempfile.TemporaryDirectory(prefix='phdex-https-') as tmp:
        root=Path(tmp).resolve();ready=root/'ready.json'
        process=subprocess.Popen([str(executable),'--no-browser','--data-dir',str(root/'state'),'--connection-file',str(ready)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def request(path):
            req=Request('http://127.0.0.1:'+str(info['port'])+path,data=b'{}',headers={'X-App-Key':info['key'],'Content-Type':'application/json'})
            try:
                with urlopen(req,timeout=45) as response:return json.loads(response.read())
            except HTTPError as error:raise AssertionError(error.read().decode('utf-8')) from error
        try:
            deadline=time.monotonic()+60
            while not ready.exists():
                if process.poll() is not None or time.monotonic()>deadline:raise AssertionError('No se pudo iniciar el EXE de prueba.')
                time.sleep(.1)
            info=json.loads(ready.read_text())
            result=request('/api/updates/check')
            assert result['current']==VERSION,result
            assert result['latest'] and result['download_url'].startswith('https://github.com/RpastranaE/PhDex/'),result
            print('HTTPS desde EXE: correcto. Instalada '+VERSION+'; GitHub '+result['latest']+'.')
            request('/api/shutdown')
        finally:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)


if __name__=='__main__':check_github(Path(sys.argv[1]).resolve())
