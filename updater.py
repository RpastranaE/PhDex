"""GitHub release updates for PhDex.exe; user documents are never replaced."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid
from core import UserError
from workflow import safe_path

VERSION = '2.1.1'
REPOSITORY = 'RpastranaE/PhDex'
RELEASES_URL = 'https://github.com/'+REPOSITORY+'/releases'
API = 'https://api.github.com/repos/'+REPOSITORY
MAX_SIZE = 100*1024*1024


def version_tuple(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',str(value))
    if not match:raise UserError('La versión publicada no tiene un formato compatible.')
    return tuple(int(n) for n in match.groups())


def github_url(url):
    parts=urlsplit(url)
    if parts.scheme!='https' or parts.username or parts.password or parts.port not in (None,443) or parts.hostname not in ('api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'):
        raise UserError('La descarga no procede de GitHub.')
    return url


class GitHubRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        github_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def request_github(url, accept='application/vnd.github+json'):
    request=Request(github_url(url),headers={'Accept':accept,'User-Agent':'PhDex/'+VERSION,'X-GitHub-Api-Version':'2022-11-28'})
    try:
        return build_opener(GitHubRedirects()).open(request,timeout=30)
    except HTTPError as error:
        if error.code in (403,429):raise UserError('GitHub ha limitado temporalmente las consultas. Inténtalo más tarde.') from None
        if error.code==404:raise UserError('No hay una versión pública disponible en GitHub.') from None
        raise UserError('GitHub no ha podido completar la consulta (HTTP '+str(error.code)+').') from None
    except (URLError,TimeoutError,OSError) as error:
        reason=getattr(error,'reason',error)
        if isinstance(reason,ssl.SSLCertVerificationError):
            raise UserError('No se ha podido validar el certificado HTTPS de GitHub. Comprueba la fecha de Windows y la conexión de red.') from None
        if isinstance(reason,FileNotFoundError):
            raise UserError('Falta un recurso de la conexión HTTPS. Descarga la última versión de PhDex desde GitHub.') from None
        raise UserError('No se ha podido conectar con GitHub. Comprueba tu conexión; puedes seguir usando PhDex.') from None


def release_info(payload,current=VERSION):
    if not isinstance(payload,dict) or payload.get('draft') or payload.get('prerelease'):
        raise UserError('La versión no es una publicación estable.')
    tag=payload.get('tag_name','');latest=version_tuple(tag)
    assets=[a for a in payload.get('assets',[]) if a.get('name')=='PhDex.exe' and a.get('state')=='uploaded']
    if len(assets)!=1:raise UserError('La publicación todavía no incluye PhDex.exe listo para descargar.')
    asset=assets[0];size=asset.get('size')
    if type(size) is not int or not 1024<=size<=MAX_SIZE:raise UserError('El tamaño del ejecutable publicado no es válido.')
    url=asset.get('browser_download_url','')
    expected='https://github.com/'+REPOSITORY+'/releases/download/'+str(tag)+'/PhDex.exe'
    if url!=expected:raise UserError('El ejecutable no pertenece a la publicación de PhDex.')
    return {'current':current,'latest':'.'.join(map(str,latest)),'available':latest>version_tuple(current),
            'release_url':RELEASES_URL+'/tag/'+str(tag),'download_url':url,'size':size}


class Updater:
    def __init__(self,data_dir,current=VERSION):
        self.directory=Path(data_dir)/'actualizaciones'
        self.current=current
        self.lock=threading.Lock()
        self.latest=None

    def automatic(self):
        config=self.directory.parent/'actualizador.json'
        if not config.exists():return True
        try:
            data=json.loads(config.read_text(encoding='utf-8'))
            return data.get('automatic') is True
        except (OSError,ValueError):return False

    def set_automatic(self,value):
        if type(value) is not bool:raise UserError('Elige si quieres actualizar al iniciar.')
        with self.lock:
            config=self.directory.parent/'actualizador.json'
            temp=config.with_name('.actualizador-'+uuid.uuid4().hex+'.tmp')
            try:
                with temp.open('x',encoding='utf-8') as stream:
                    json.dump({'automatic':value},stream);stream.flush();os.fsync(stream.fileno())
                os.replace(temp,config)
            finally:temp.unlink(missing_ok=True)
        return {'automatic':value}

    def check(self):
        with request_github(API+'/releases/latest') as response:
            raw=response.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise UserError('La respuesta de GitHub es demasiado grande.')
            try:payload=json.loads(raw)
            except ValueError:raise UserError('GitHub no ha devuelto una publicación válida.') from None
        result=release_info(payload,self.current)
        with self.lock:self.latest=result
        return result

    def download(self):
        # Recheck instead of trusting a stale browser-supplied URL/version.
        info=self.check()
        if not info['available']:raise UserError('Ya tienes la última versión disponible.')
        safe_path(self.directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        folder=self.directory/uuid.uuid4().hex;folder.mkdir()
        stage=folder/'PhDex.exe'
        try:
            with request_github(info['download_url'],'application/octet-stream') as response,stage.open('xb') as output:
                total=0
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total>info['size']:raise UserError('La descarga supera el tamaño publicado. No se instalará.')
                    output.write(chunk)
                output.flush();os.fsync(output.fileno())
            if total!=info['size']:raise UserError('La descarga está incompleta. No se instalará.')
            with stage.open('rb') as stream:
                if stream.read(2)!=b'MZ':raise UserError('La descarga no es un ejecutable de Windows.')
            return stage,info
        except Exception:
            stage.unlink(missing_ok=True)
            folder.rmdir()
            raise



def wait_process(process_id,timeout=90):
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x00100000,False,process_id)
    if not handle:
        if ctypes.get_last_error()==87:return
        raise UserError('No se puede comprobar el cierre de PhDex. Se conserva la versión actual.')
    try:
        if kernel.WaitForSingleObject(handle,int(timeout*1000))!=0:
            raise UserError('PhDex sigue abierto. No se ha sustituido el ejecutable.')
    finally:kernel.CloseHandle(handle)


def apply_update(manifest):
    import shutil
    manifest=safe_path(manifest).resolve()
    folder=manifest.parent
    config=json.loads(manifest.read_text(encoding='utf-8'))
    stage,target=safe_path(config['stage']).resolve(),safe_path(config['target']).resolve()
    if stage!=folder/'PhDex.exe' or target.suffix.lower()!='.exe' or not stage.is_file() or not target.is_file() or target.parent==folder:
        raise UserError('La actualización no tiene una ubicación válida.')
    arguments=config['args']
    if not isinstance(arguments,list) or len(arguments)>30 or not all(isinstance(a,str) and '\x00' not in a for a in arguments):
        raise UserError('Argumentos de reinicio no válidos.')
    candidate=target.with_name('.PhDex-'+uuid.uuid4().hex+'.exe')
    backup=target.with_name(target.name+'.respaldo-'+uuid.uuid4().hex+'.exe')
    replaced=False
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    (folder/'helper_listo.txt').write_text('ready',encoding='ascii')
    try:
        wait_process(int(config['pid']))
        safe_path(target)
        shutil.copy2(target,backup)
        with stage.open('rb') as source,candidate.open('xb') as output:
            shutil.copyfileobj(source,output,1024*1024);output.flush();os.fsync(output.fileno())
        for attempt in range(60):
            try:
                safe_path(target);os.replace(candidate,target);replaced=True;break
            except PermissionError:
                time.sleep(.5)
        if not replaced:raise UserError('El ejecutable sigue abierto en otra sesión o la carpeta no permite sustituirlo.')
        process=subprocess.Popen([str(target),*arguments],cwd=target.parent,creationflags=flags)
        try:
            code=process.wait(timeout=8)
            if code:raise UserError('La nueva versión no pudo iniciar.')
        except subprocess.TimeoutExpired:pass
        (folder/'actualizacion_completada.txt').write_text('PhDex actualizado. Respaldo: '+str(backup),encoding='utf-8')
        return 0
    except Exception as error:
        problem=str(error)
        if replaced:
            try:
                failed=target.with_name(target.name+'.fallida-'+uuid.uuid4().hex+'.exe')
                shutil.copy2(target,failed)
                os.replace(backup,target)
                subprocess.Popen([str(target),*arguments],cwd=target.parent,creationflags=flags)
                problem+=' Se ha restaurado la versión anterior.'
            except OSError:problem+=' La copia anterior está en '+str(backup)+'.'
        log=folder/'error_actualizacion.txt';log.write_text(problem,encoding='utf-8')
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,problem+'\nDetalle: '+str(log),'PhDex: actualización no completada',0x10)
        return 1
    finally:candidate.unlink(missing_ok=True)


def launch_replacement(stage,target,data_dir,doctorado,process_id,extra_args=None):
    """Use a separate copy of this EXE as a native helper, without PowerShell or CMD."""
    import shutil
    if os.name!='nt':raise UserError('La actualización integrada está disponible en Windows.')
    stage,target=safe_path(stage).resolve(),safe_path(target).resolve()
    if not stage.is_file() or not target.is_file() or stage==target:
        raise UserError('No se puede preparar la sustitución del ejecutable.')
    config={'stage':str(stage),'target':str(target),'pid':int(process_id),
            'args':extra_args if extra_args is not None else ['--data-dir',str(Path(data_dir).resolve()),'--doctorado',str(Path(doctorado).resolve())]}
    manifest=stage.parent/'actualizar.json'
    with manifest.open('x',encoding='utf-8') as stream:json.dump(config,stream,ensure_ascii=False)
    if getattr(sys,'frozen',False):
        helper=stage.parent/'Ayudante_PhDex.exe';shutil.copy2(sys.executable,helper)
        command=[str(helper),'--apply-update',str(manifest)]
    else:
        command=[sys.executable,str(Path(__file__).resolve().with_name('app.py')),'--apply-update',str(manifest)]
    log=stage.parent/'ayudante_windows.txt'
    with log.open('wb') as output:
        process=subprocess.Popen(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),stdout=output,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+15
    while not (stage.parent/'helper_listo.txt').exists():
        if process.poll() is not None:
            detail=log.read_bytes().decode('utf-8-sig',errors='replace')[:1000]
            raise UserError('Windows no ha permitido iniciar el actualizador. El ejecutable actual se conserva. '+detail)
        if time.monotonic()>deadline:
            process.terminate();process.wait(timeout=5)
            raise UserError('El actualizador no respondió. El ejecutable actual se conserva.')
        time.sleep(.1)
    return process
