"""Aplicación local de archivos del doctorado. Solo biblioteca estándar de Python."""
from __future__ import annotations

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import traceback
from urllib.parse import urlsplit
import uuid
import webbrowser

from core import CATEGORIES, Engine, UserError, metadata, absolute
from workflow import structure, recommend, audit, safe_path, ROOTS
from folders import SessionFolders
from library import Library
from storage import default_data_dir, migrate_legacy_data
from intake import Intake
from updater import Updater, VERSION, RELEASES_URL, launch_replacement

ROOT = Path(__file__).resolve().parent


def pick_paths(kind, initial=""):
    if os.name != "nt":
        raise UserError("El selector nativo está disponible en Windows. Puedes pegar una ruta absoluta.")
    if kind not in ("files", "folder"):
        raise UserError("Selector desconocido.")
    config = base64.b64encode(json.dumps({"kind": kind, "initial": str(initial)}).encode()).decode()
    # Los valores del usuario se decodifican como datos JSON, nunca como comandos.
    script = r"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$cfg = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__CONFIG__')) | ConvertFrom-Json
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.Text = 'Doctorado · Selección de archivos'
$owner.StartPosition = [Windows.Forms.FormStartPosition]::CenterScreen
$owner.Size = New-Object Drawing.Size(1, 1)
$owner.Opacity = 0
# Un propietario mostrado y activado mantiene el diálogo por delante de otras
# ventanas. TopMost en un Form que nunca se mostró no establece esa propiedad.
$owner.Show()
$owner.Activate()
$owner.BringToFront()
[Windows.Forms.Application]::DoEvents()
try {
if ($cfg.kind -eq 'folder') {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Selecciona una carpeta para Doctorado · Archivos'
    $dialog.ShowNewFolderButton = $false
    if ([IO.Directory]::Exists($cfg.initial)) { $dialog.SelectedPath = $cfg.initial }
    if ($dialog.ShowDialog($owner) -eq [Windows.Forms.DialogResult]::OK) {
        ConvertTo-Json -Compress -InputObject @($dialog.SelectedPath)
    } else { '[]' }
} else {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Selecciona archivos para Doctorado · Archivos'
    $dialog.Multiselect = $cfg.kind -eq 'files'
    if ([IO.Directory]::Exists($cfg.initial)) { $dialog.InitialDirectory = $cfg.initial }
    if ($dialog.ShowDialog($owner) -eq [Windows.Forms.DialogResult]::OK) {
        ConvertTo-Json -Compress -InputObject @($dialog.FileNames)
    } else { '[]' }
}
} finally {
    if ($null -ne $dialog) { $dialog.Dispose() }
    $owner.Close()
    $owner.Dispose()
}
""".replace("__CONFIG__", config)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-EncodedCommand", encoded], capture_output=True, timeout=600, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise UserError("Se ha agotado el tiempo del selector. Puedes volver a abrirlo.")
    if result.returncode:
        raise UserError("No se pudo abrir el selector de Windows. Pega la ruta en el campo de entrada.")
    try:
        value = json.loads(result.stdout.decode("utf-8-sig").strip())
        return value if isinstance(value, list) else [value]
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise UserError("El selector no devolvió una ruta válida.")


class LocalApp:
    def __init__(self, data_dir, doctorado=Path('D:/Doctorado')):
        self.doctorado = Path(doctorado)
        self.engine = Engine(data_dir)
        self.engine.doctorado = self.doctorado
        self.folders = SessionFolders(self.doctorado)
        self.library = Library(data_dir)
        self.intake = Intake(data_dir, self.doctorado, self.library, self.engine)
        self.updater = Updater(data_dir)
        self.key = secrets.token_urlsafe(32)
        self.jobs = {}
        self.jobs_lock = threading.Lock()
        self.prefs_file = Path(data_dir) / "preferencias.json"
        self.server = None
        self.clients = set()
        self.empty_since = time.monotonic()
        self.had_client = False
        self.closing = False
        self.lifecycle_stop = threading.Event()

    def connect_client(self, client_id):
        with self.jobs_lock:
            if self.closing:
                raise UserError('La sesión está cerrándose. Vuelve a abrir la aplicación.')
            self.clients.add(client_id)
            self.had_client = True

    def disconnect_client(self, client_id):
        with self.jobs_lock:
            self.clients.discard(client_id)
            if not self.clients:
                self.empty_since = time.monotonic()

    def close_if_unused(self, current=None):
        """Recargas y varias pestañas comparten un cierre diferido; los lotes terminan."""
        current = time.monotonic() if current is None else current
        with self.jobs_lock:
            grace = 5 if self.had_client else 120
            if (self.closing or self.clients or current - self.empty_since < grace
                    or any(j['state'] == 'running' for j in self.jobs.values())):
                return False
            self.closing = True
            return True

    def watch_lifecycle(self):
        while not self.lifecycle_stop.wait(0.5):
            if self.close_if_unused():
                self.server.shutdown()
                return

    def prefs(self):
        try:
            return json.loads(self.prefs_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def preview(self, request):
        plan = self.engine.preview(request)
        # Solo preferencias de la interfaz; no se guarda una lista de entradas pendientes.
        preferences = {"output": request.get("output", ""), "meta": request.get("defaults", {})}
        self.prefs_file.write_text(json.dumps(preferences, ensure_ascii=False), encoding="utf-8")
        return plan

    def start_job(self, plan_id):
        with self.jobs_lock:
            if self.closing:
                raise UserError('La sesión está cerrándose. Vuelve a abrir la aplicación.')
            if any(j["state"] == "running" for j in self.jobs.values()):
                raise UserError("Ya hay un lote en curso. Espera a que termine.")
            job_id = uuid.uuid4().hex
            job = {"state": "running"}
            self.jobs[job_id] = job
        def run():
            try:
                result = self.engine.execute(plan_id)
                with self.jobs_lock:
                    job.update({"state": "done", "result": result})
            except Exception as exc:
                with self.jobs_lock:
                    job.update({"state": "error", "error": str(exc)})
        threading.Thread(target=run, daemon=True).start()
        return {"job": job_id}

    def start_update(self, confirmed):
        if confirmed is not True:
            raise UserError('Confirma la actualización y el reinicio de PhDex.')
        if not getattr(sys,'frozen',False):
            raise UserError('La actualización integrada se usa desde PhDex.exe. Esta sesión ejecuta el código fuente.')
        with self.jobs_lock:
            if self.closing or any(j['state']=='running' for j in self.jobs.values()):
                raise UserError('Espera a que termine la operación en curso.')
            if len(self.clients)>1:
                raise UserError('Cierra las otras pestañas de PhDex antes de actualizar.')
            job_id=uuid.uuid4().hex
            job={'state':'running','message':'Descargando la nueva versión…'}
            self.jobs[job_id]=job
        def run():
            try:
                stage,info=self.updater.download()
                job['message']='Preparando copia de seguridad y reinicio…'
                launch_replacement(stage,Path(sys.executable),self.engine.data_dir,self.doctorado,os.getpid())
                with self.jobs_lock:
                    self.closing=True
                    job.update(state='done',result={'version':info['latest'],'restarting':True})
                # Give the browser a short chance to show the restart message.
                time.sleep(2)
                self.server.shutdown()
            except Exception as exc:
                with self.jobs_lock:job.update(state='error',error=str(exc))
        threading.Thread(target=run,daemon=True).start()
        return {'job':job_id}


class Handler(BaseHTTPRequestHandler):
    server_version = "PhDex/2.1.2"

    @property
    def app(self):
        return self.server.app

    def log_message(self, format, *args):
        # No se escriben rutas de archivos ni claves de sesión en la consola.
        pass

    def headers_common(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")

    def response(self, status, data, content_type="application/json; charset=utf-8", filename=None):
        raw = data if isinstance(data, bytes) else (json.dumps(data, ensure_ascii=False).encode() if content_type.startswith("application/json") else str(data).encode())
        self.send_response(status)
        self.headers_common()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(raw)

    def valid_origin(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            return False
        origin = self.headers.get("Origin")
        return not origin or origin in {"http://" + h for h in hosts}

    def authenticated(self):
        return self.valid_origin() and secrets.compare_digest(self.headers.get("X-App-Key", ""), self.app.key)

    def do_GET(self):
        if not self.valid_origin():
            return self.response(403, {"error": "Origen no permitido."})
        path = urlsplit(self.path).path
        assets = {"/phdex.ico": ("phdex.ico", "image/x-icon"), "/phdex-icon.png": ("phdex-icon.png", "image/png"), "/metadata-model.js": ("metadata-model.js", "text/javascript; charset=utf-8"), "/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
        if path in assets:
            name, mime = assets[path]
            return self.response(200, (ROOT / "web" / name).read_bytes(), mime)
        if not self.authenticated():
            return self.response(403, {"error": "Abre la aplicación desde Abrir Doctorado Archivos.cmd para iniciar una sesión local."})
        try:
            if path == '/api/lifecycle':
                # Una conexión por pestaña. Su cierre se detecta también con la
                # pestaña en segundo plano, sin depender de temporizadores JS.
                client_id = uuid.uuid4().hex
                self.app.connect_client(client_id)
                try:
                    self.send_response(200)
                    self.headers_common()
                    self.send_header('Content-Type', 'text/event-stream')
                    self.end_headers()
                    while not self.app.lifecycle_stop.is_set():
                        self.wfile.write(b': connected\n\n')
                        self.wfile.flush()
                        if self.app.lifecycle_stop.wait(1):
                            break
                except (OSError, ConnectionError):
                    pass
                finally:
                    self.app.disconnect_client(client_id)
                return
            if path == "/api/state":
                return self.response(200, {"categories": CATEGORIES,
                                          "preferences": self.app.prefs(), "history_path": str(self.app.engine.dbpath), "native_picker": os.name == "nt", "doctorado": str(self.app.doctorado), "folder_roots":{p:str(self.app.doctorado / n) for p,n in ROOTS.items()}})
            if path == "/api/library":
                return self.response(200, self.app.library.read())
            if path == '/api/intake':
                return self.response(200, self.app.intake.read())
            if path == '/api/version':
                return self.response(200, {'version':VERSION,'packaged':bool(getattr(sys,'frozen',False)), 'releases_url':RELEASES_URL,'automatic':self.app.updater.automatic()})
            if path == "/api/structure":
                return self.response(200, structure(self.app.doctorado))
            if path == "/api/history":
                return self.response(200, {"rows": self.app.engine.history()})
            if path == "/api/history.csv":
                return self.response(200, self.app.engine.csv_text(), "text/csv; charset=utf-8", "Registro_Doctorado.csv")
            if path == "/api/convention":
                return self.response(200, {"text": (ROOT / "referencias" / "Convencion_original.txt").read_text(encoding="utf-8")})
            if path.startswith("/api/job/"):
                with self.app.jobs_lock:
                    job = self.app.jobs.get(path.rsplit("/", 1)[-1])
                    result = dict(job) if job else None
                return self.response(200 if result else 404, result or {"error": "Lote no encontrado."})
            return self.response(404, {"error": "No encontrado."})
        except (OSError, ValueError) as exc:
            return self.response(400, {"error": str(exc)})

    def do_POST(self):
        if not self.authenticated():
            return self.response(403, {"error": "Sesión local no válida."})
        if urlsplit(self.path).path == '/api/import':
            try:
                if self.headers.get('Content-Type') != 'application/octet-stream':
                    raise UserError('Selecciona archivos para arrastrar.')
                name = base64.b64decode(self.headers.get('X-File-Name',''),validate=True).decode('utf-8')
                length = int(self.headers.get('Content-Length','-1'))
                self.connection.settimeout(120)
                with self.app.jobs_lock:
                    if self.app.closing or any(j['state']=='running' for j in self.app.jobs.values()):
                        raise UserError('Espera a que termine la exportación antes de importar.')
                    imported = self.app.intake.import_file(name,self.rfile,length)
                return self.response(200, {'path':imported})
            except (OSError, ValueError, UserError) as exc:
                self.close_connection = True
                return self.response(400, {'error':str(exc)})
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.response(415, {"error": "Se requiere JSON."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 12 * 1024 * 1024:
                raise UserError("Petición demasiado grande o vacía.")
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise UserError("Petición no válida.")
            path = urlsplit(self.path).path
            if path == '/api/updates/check':
                return self.response(200,self.app.updater.check())
            if path == '/api/updates/install':
                return self.response(200,self.app.start_update(request.get('confirmed')))
            if path == '/api/updates/settings':
                return self.response(200,self.app.updater.set_automatic(request.get('automatic')))
            if path == '/api/intake':
                return self.response(200,self.app.intake.change(request))
            if path == '/api/inbox':
                return self.response(200,self.app.intake.listing())
            if path == '/api/names':
                entries=request.get('items',[])
                if not isinstance(entries,list) or len(entries)>500:
                    raise UserError('Límite de 500 archivos.')
                rows=[]
                for entry in entries:
                    try:
                        source=safe_path(entry.get('path'))
                        if not source.exists(): raise UserError('El archivo ya no está disponible.')
                        name=metadata(entry.get('meta',{}),source)['exported_name']
                        rows.append({'key':entry.get('key'),'name':name,'error':''})
                    except (UserError,OSError) as exc:
                        rows.append({'key':entry.get('key'),'name':'','error':str(exc)})
                return self.response(200,{'items':rows})
            if path == '/api/open-destinations':
                paths=request.get('paths',[])
                if not isinstance(paths,list) or not 1<=len(paths)<=20:
                    raise UserError('Selecciona entre 1 y 20 destinos.')
                allowed=set()
                with self.app.engine.db() as db:
                    rows=db.execute("SELECT destination FROM actions WHERE status IN ('completado','ya_exportado','sin_cambio')").fetchall()
                for row in rows:
                    allowed.add(os.path.normcase(str(Path(row['destination']).parent.resolve())))
                targets=[]
                for raw in dict.fromkeys(paths):
                    folder=safe_path(raw).resolve()
                    if not folder.is_dir() or os.path.normcase(str(folder)) not in allowed:
                        raise UserError('Solo se pueden abrir carpetas con exportaciones registradas.')
                    targets.append(folder)
                if os.name!='nt': raise UserError('Abrir carpetas está disponible en Windows.')
                opened=[]
                for folder in targets:
                    try:
                        os.startfile(str(folder));opened.append(str(folder))
                    except OSError as exc:
                        return self.response(200,{'opened':opened,'error':'No se pudo abrir '+str(folder)+': '+str(exc)})
                return self.response(200,{'opened':opened})
            if path == "/api/library":
                return self.response(200, self.app.library.change(request))
            if path == "/api/inspect":
                inspected=self.app.engine.inspect(request.get('paths',[]))
                for item in inspected:
                    item['suggestions']=self.app.intake.suggestions(item['name']) if item['kind']=='file' else {'meta':{},'notes':[],'matches':[]}
                return self.response(200, {"items": inspected})
            if path == '/api/history/delete':
                with self.app.jobs_lock:
                    if self.app.closing or any(j['state'] == 'running' for j in self.app.jobs.values()):
                        raise UserError('Espera a que termine la exportación antes de borrar historial.')
                    result = self.app.engine.delete_history(request.get('ids'), request.get('confirmed'))
                return self.response(200, result)
            if path == "/api/recommend":
                return self.response(200, recommend(self.app.doctorado, request.get('meta', {}), request.get('source', ''), request.get('description', '')))
            if path == '/api/folders':
                return self.response(200, self.app.folders.list(request.get('meta', {}), request.get('parent')))
            if path in ('/api/folders/create', '/api/folders/delete'):
                with self.app.jobs_lock:
                    if self.app.closing or any(j['state']=='running' for j in self.app.jobs.values()):
                        raise UserError('Espera a que termine el lote antes de cambiar carpetas.')
                    with self.app.engine.lock:
                        if path.endswith('/create'):
                            result = self.app.folders.create(request.get('meta', {}), request.get('name'), request.get('parent'))
                        else:
                            result = self.app.folders.delete(request.get('token'))
                            self.app.engine.plans.clear()
                return self.response(200, result)
            if path == "/api/audit":
                return self.response(200, audit(self.app.doctorado))
            if path == "/api/list":
                return self.response(200, {"items": self.app.engine.list_folder(request.get("path"))})
            if path == '/api/browse':
                folder = safe_path(request.get('path') or self.app.doctorado)
                if folder.is_file():
                    folder = folder.parent
                rows = self.app.engine.list_folder(folder)
                return self.response(200, {'path':str(folder), 'parent':str(folder.parent),
                    'folders':[r for r in rows if r['kind']=='folder']})
            if path == "/api/pick":
                return self.response(200, {"paths": pick_paths(request.get("kind"), request.get("initial", ""))})
            if path == "/api/preview":
                return self.response(200, self.app.preview(request))
            if path == "/api/execute":
                return self.response(200, self.app.start_job(request.get("plan_id")))
            if path == '/api/validate':
                entries = request.get('items', [])
                if not isinstance(entries, list) or not 1 <= len(entries) <= 500:
                    raise UserError('Selecciona entre 1 y 500 entradas.')
                rows = []
                for item in entries:
                    try:
                        metadata(item.get('meta', {}), absolute(item.get('path')))
                        rows.append({'key': item.get('key'), 'error': ''})
                    except (UserError, OSError) as exc:
                        rows.append({'key': item.get('key'), 'error': str(exc)})
                return self.response(200, {'items': rows, 'valid': all(not r['error'] for r in rows)})
            if path == "/api/shutdown":
                with self.app.jobs_lock:
                    if any(j["state"] == "running" for j in self.app.jobs.values()):
                        raise UserError("Espera a que termine el lote antes de cerrar.")
                    self.app.closing = True
                self.response(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self.response(404, {"error": "No encontrado."})
        except (UserError, OSError, ValueError, KeyError) as exc:
            return self.response(400, {"error": str(exc)})
        except Exception:
            (self.app.engine.data_dir / "ultimo_error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            return self.response(500, {"error": "No se pudo completar la operación. Consulta ultimo_error.txt en la carpeta de datos de la app."})


def main():
    parser = argparse.ArgumentParser(description="PhDex — Gestión de archivos")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--connection-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--doctorado", type=Path, default=Path('D:/Doctorado'))
    args = parser.parse_args()
    data_dir = args.data_dir.resolve() if args.data_dir else default_data_dir()
    if args.data_dir is None:
        legacy_root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ROOT
        migrate_legacy_data(data_dir, legacy_root/'datos_app')
    app = LocalApp(data_dir, args.doctorado.resolve())
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.app = app
    app.server = server
    threading.Thread(target=app.watch_lifecycle, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/#{app.key}"
    if sys.stdout:
        print("PhDex listo. Abre esta dirección en tu navegador:", flush=True)
        print(url, flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        if args.connection_file:
            # Explicit diagnostic output for the packaged smoke test only.
            # Never overwrite existing files, never create this in normal use.
            with args.connection_file.open('x', encoding='utf-8') as stream:
                json.dump({'url': url, 'port': server.server_port, 'key': app.key}, stream)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.lifecycle_stop.set()
        server.server_close()


if __name__ == "__main__":
    try:
        if len(sys.argv)==3 and sys.argv[1]=='--apply-update':
            from updater import apply_update
            raise SystemExit(apply_update(sys.argv[2]))
        else:
            main()
    except Exception:
        error_dir = default_data_dir().parent
        error_dir.mkdir(parents=True, exist_ok=True)
        error_path = error_dir / "error_inicio.txt"
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
        if sys.stderr:
            traceback.print_exc()
        if getattr(sys, 'frozen', False) and '--no-browser' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                'No se ha podido abrir PhDex. Consulta el detalle en:\n'+str(error_path), 'PhDex', 0x10)
        raise SystemExit(1)
