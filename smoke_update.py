"""Test the actual Windows replacement helper with an isolated EXE and persisted state."""
from pathlib import Path
import json,os,shutil,subprocess,sys,tempfile,time
from urllib.request import Request,urlopen
from updater import launch_replacement
from unittest.mock import patch


def check_update(executable):
    with tempfile.TemporaryDirectory(prefix='phdex-update-') as tmp:
        root=Path(tmp).resolve()/"Carpeta con espacios y ' comilla";root.mkdir()
        target=root/'PhDex.exe';shutil.copy2(executable,target)
        staging=root/'descarga';staging.mkdir();stage=staging/'PhDex.exe';shutil.copy2(executable,stage)
        data=root/'Documentos'/'PhDex'/'datos_app';data.mkdir(parents=True)
        marker=data/'personal.txt';marker.write_text('conservar',encoding='utf-8')
        doc=root/'Doctorado';doc.mkdir();(doc/'00_Entrada').mkdir()
        first=root/'primero.json';second=root/'segundo.json'
        env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
        args=['--no-browser','--doctorado',str(doc),'--data-dir',str(data),'--connection-file',str(first)]
        original=subprocess.Popen([str(target),*args],env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def ready(path):
            deadline=time.monotonic()+60
            while not path.exists():
                if time.monotonic()>deadline:raise AssertionError('El proceso no inició: '+str(path))
                time.sleep(.1)
            return json.loads(path.read_text(encoding='utf-8'))
        def request(info,path,body=None):
            req=Request('http://127.0.0.1:'+str(info['port'])+path,data=None if body is None else json.dumps(body).encode(),headers={'X-App-Key':info['key'],'Content-Type':'application/json'})
            with urlopen(req,timeout=10) as response:return json.loads(response.read())
        helper=None;new_info=None
        try:
            old_info=ready(first)
            request(old_info,'/api/updates/settings',{'automatic':False})
            new_args=args[:-1]+[str(second)]
            # The onefile launcher is the process ID returned by Popen; the app child exits with it.
            with patch('updater.sys.frozen',True,create=True),patch('updater.sys.executable',str(Path(executable).resolve())):
                helper=launch_replacement(stage,target,data,doc,original.pid,extra_args=new_args)
            request(old_info,'/api/shutdown',{})
            original.wait(timeout=30)
            new_info=ready(second)
            assert request(new_info,'/api/version')['version']=='2.1.0'
            assert request(new_info,'/api/version')['automatic'] is False
            assert marker.read_text(encoding='utf-8')=='conservar'
            backups=list(root.glob('PhDex.exe.respaldo-*.exe'));assert len(backups)==1
            assert backups[0].read_bytes()==target.read_bytes()==stage.read_bytes()
            helper.wait(timeout=25);assert helper.returncode==0
            assert not list(staging.glob('error_actualizacion.txt'))
            request(new_info,'/api/shutdown',{});new_info=None
            time.sleep(2)
        finally:
            if new_info:
                try:request(new_info,'/api/shutdown',{})
                except OSError:pass
            if original.poll() is None:
                try:request(ready(first),'/api/shutdown',{})
                except OSError:original.terminate()
                original.wait(timeout=15)
            if helper and helper.poll() is None:helper.terminate();helper.wait(timeout=10)


if __name__=='__main__':
    check_update(Path(sys.argv[1]).resolve())
    print('Actualizador comprobado: reemplazo, respaldo, reinicio y datos conservados.')
