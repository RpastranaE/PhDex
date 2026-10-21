"""Exercise the actual EXE in an isolated folder, without an external Python runtime."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import uuid


def check_executable(executable):
    with tempfile.TemporaryDirectory(prefix='phdex-exe-') as temp:
        root=Path(temp).resolve()
        portable=root/'portable';portable.mkdir()
        exe=portable/'PhDex.exe';shutil.copy2(executable,exe)
        doctorado=root/'Doctorado'
        inbox=doctorado/'00_Entrada';inbox.mkdir(parents=True)
        output=doctorado/'02_Experimentos'/'Prueba';output.mkdir(parents=True)
        source=inbox/'ensayo.csv';source.write_bytes(b'x,y\n1,2\n')
        env={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH')}
        data_dir=root/'Documents'/'PhDex'/'datos_app'

        def start():
            ready=root/(uuid.uuid4().hex+'.json')
            process=subprocess.Popen([str(exe),'--no-browser','--doctorado',str(doctorado),
                '--data-dir',str(data_dir),
                '--connection-file',str(ready)],cwd=root,env=env,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            deadline=time.monotonic()+60
            while not ready.exists():
                if process.poll() is not None:raise AssertionError('El EXE terminó antes de iniciar el servidor.')
                if time.monotonic()>deadline:
                    process.terminate();process.wait(timeout=10)
                    raise AssertionError('El EXE no inició en 60 segundos.')
                time.sleep(.1)
            info=json.loads(ready.read_text(encoding='utf-8'))

            def request(path,body=None):
                data=None if body is None else json.dumps(body).encode()
                req=Request('http://127.0.0.1:'+str(info['port'])+path,data=data,
                    headers={'X-App-Key':info['key'],'Content-Type':'application/json'})
                try:
                    with urlopen(req,timeout=20) as response:
                        content=response.read()
                        return json.loads(content) if 'application/json' in response.headers.get('Content-Type','') else content
                except HTTPError as error:
                    raise AssertionError(path+': '+error.read().decode('utf-8')) from error
            return process,request

        def stop(process,request):
            if process.poll() is None:
                try:request('/api/shutdown',{})
                finally:
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.terminate();process.wait(timeout=10)

        process,request=start()
        try:
            assert b'PhDex' in request('/')
            assert len(request('/app.js'))>1000
            assert request('/phdex.ico')[:4]==b'\x00\x00\x01\x00'
            assert request('/phdex-icon.png').startswith(b'\x89PNG')
            assert request('/api/convention')['text']
            state=request('/api/state')
            assert Path(state['history_path'])==data_dir.resolve()/'registro.sqlite3'
            request('/api/library',{'revision':0,'group':'favorites','value':{'label':'Prueba','output':str(output)}})
            item={'path':str(source),'output':str(output),'meta':{'category':'record',
                'owner_kind':'experiment','owner_code':'EXP-12','date':'2026-10-21','content':'Ensayo'}}
            plan=request('/api/preview',{'mode':'copy','items':[item]})
            assert plan['valid'],plan
            job=request('/api/execute',{'plan_id':plan['id']})
            deadline=time.monotonic()+30
            while True:
                result=request('/api/job/'+job['job'])
                if result['state']!='running':break
                assert time.monotonic()<deadline
                time.sleep(.1)
            assert result['state']=='done',result
            target=output/'2026-10-21_EXP-12_Ensayo.csv'
            assert source.read_bytes()==target.read_bytes()
            assert not request('/api/preview',{'mode':'copy','items':[item]})['valid']
            rows=request('/api/history')['rows'];assert len(rows)==1
            assert request('/api/history/delete',{'ids':[rows[0]['id']],'confirmed':True})['deleted']==1
            assert source.exists() and target.exists()
        finally:stop(process,request)
        process,request=start()
        try:
            assert len(request('/api/library')['favorites'])==1
            assert not request('/api/history')['rows']
            assert source.exists() and target.exists()
        finally:stop(process,request)
    print('EXE comprobado: recursos, datos persistentes, copia, colisiones, historial y reinicio.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('executable',type=Path)
    check_executable(parser.parse_args().executable.resolve())
