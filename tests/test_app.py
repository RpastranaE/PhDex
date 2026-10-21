import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Handler, LocalApp, ThreadingHTTPServer


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doctorado-servidor-")
        self.app = LocalApp(Path(self.temp.name))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.app = self.app
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method="GET", data=None, authenticated=True, extra=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"X-App-Key": self.app.key} if authenticated else {}
        headers.update(extra or {})
        if data is not None:
            headers.setdefault("Content-Type", "application/json")
        conn.request(method, path, json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        status, body = response.status, response.read()
        conn.close()
        return status, body

    def test_library_api_persists_and_rejects_unauthenticated_changes(self):
        folder = Path(self.temp.name)/'favorito'
        folder.mkdir()
        payload = {'revision':0,'group':'favorites','value':{'label':'Destino','output':str(folder)}}
        self.assertEqual(self.request('/api/library','POST',payload,authenticated=False)[0],403)
        status, body = self.request('/api/library','POST',payload)
        self.assertEqual(status,200)
        saved=json.loads(body)
        self.assertEqual(json.loads(self.request('/api/library')[1]),saved)
        self.assertEqual(self.request('/api/library','POST',payload)[0],400)
        self.assertEqual(list(folder.iterdir()),[])

    def test_history_deletion_needs_auth_confirmation_and_idle_app(self):
        payload={'ids':['0'*32],'confirmed':True}
        self.assertEqual(self.request('/api/history/delete','POST',payload,authenticated=False)[0],403)
        self.assertEqual(self.request('/api/history/delete','POST',{'ids':['0'*32]})[0],400)
        self.app.jobs['test']={'state':'running'}
        self.assertEqual(self.request('/api/history/delete','POST',payload)[0],400)
        self.app.jobs.clear()
        self.assertEqual(self.request('/api/history/delete','POST',payload)[0],400)

    def test_session_and_cross_origin_requests(self):
        self.assertEqual(self.request("/")[0], 200)
        self.assertEqual(self.request("/api/state", authenticated=False)[0], 403)
        self.assertEqual(self.request("/api/state", extra={"Origin": "https://otro.example"})[0], 403)
        self.assertEqual(self.request("/api/state", extra={"Host": "otro.example"})[0], 403)
        self.assertEqual(self.request("/api/state")[0], 200)

    def test_post_requires_json_and_no_arbitrary_file_download(self):
        self.assertEqual(self.request("/api/inspect", "POST", {"paths": []}, extra={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("/../core.py")[0], 404)
        self.assertEqual(self.request("/api/inspect", "POST", {"paths": ["relative.csv"]})[0], 400)

    def test_catalog_update_removed_and_manual_step_validation(self):
        self.assertEqual(self.request('/api/catalog.json')[0], 404)
        self.assertEqual(self.request('/api/catalog/import', 'POST', {'kind':'sample','text':'ID,Muestra\nMUE-8,Ejemplo'})[0],404)
        self.assertNotIn('catalog',json.loads(self.request('/api/state')[1]))
        root = Path(self.temp.name)
        source = root/'ensayo.csv';source.write_text('datos')
        meta = {'category':'export','owner_kind':'characterization','owner_code':'CAR-27','date':'2026-10-21'}
        status,body=self.request('/api/validate','POST',{'items':[{'key':'a','path':str(source),'meta':meta}]})
        self.assertEqual(status,200)
        self.assertTrue(json.loads(body)['valid'])
        meta['owner_code']='CAR-027'
        status,body=self.request('/api/validate','POST',{'items':[{'key':'a','path':str(source),'meta':meta}]})
        self.assertFalse(json.loads(body)['valid'])
        self.assertEqual(list(root.glob('2026*')),[])

    def test_folder_browser_navigates_without_native_dialog_or_writes(self):
        root=Path(self.temp.name)
        (root/'subcarpeta').mkdir()
        source=root/'archivo.csv';source.write_text('original')
        status,body=self.request('/api/browse','POST',{'path':str(root)})
        result=json.loads(body)
        self.assertEqual(status,200)
        self.assertEqual([r['name'] for r in result['folders']],['subcarpeta'])
        self.assertEqual(result['parent'],str(root.parent))
        status,body=self.request('/api/browse','POST',{'path':str(root/'subcarpeta')})
        self.assertEqual(json.loads(body)['parent'],str(root))
        status,body=self.request('/api/browse','POST',{'path':str(source)})
        self.assertEqual(json.loads(body)['path'],str(root))
        self.assertEqual(self.request('/api/browse','POST',{'path':str(root/'inexistente')})[0],400)
        self.assertEqual(source.read_text(),'original')

    def test_folder_mutation_requires_session_and_blocks_active_copy(self):
        from folders import SessionFolders
        root=Path(self.temp.name)/'Doctorado'
        parent=root/'04_Caracterizaciones';parent.mkdir(parents=True)
        (parent/'DRX').mkdir()
        self.app.doctorado=root;self.app.engine.doctorado=root;self.app.folders=SessionFolders(root)
        meta={'owner_code':'CAR-27','owner_kind':'characterization'}
        payload={'meta':meta,'name':'Nueva'}
        self.assertEqual(self.request('/api/folders/create','POST',payload,authenticated=False)[0],403)
        self.assertEqual(self.request('/api/folders/delete','POST',{'token':'inventado'})[0],400)
        self.app.jobs['a']={'state':'running'}
        self.assertEqual(self.request('/api/folders/create','POST',payload)[0],400)
        self.app.jobs['a']['state']='done'
        status,body=self.request('/api/folders/create','POST',payload)
        self.assertEqual(status,200)
        row=next(r for r in json.loads(body)['folders'] if r['name']=='Nueva')
        self.app.engine.plans['viejo']={'valid':True}
        self.app.jobs['a']['state']='running'
        self.assertEqual(self.request('/api/folders/delete','POST',{'token':row['token']})[0],400)
        self.app.jobs['a']['state']='done'
        self.assertEqual(self.request('/api/folders/delete','POST',{'token':row['token']})[0],200)
        self.assertFalse(self.app.engine.plans)
        self.assertTrue((parent/'DRX').exists());self.assertFalse((parent/'Nueva').exists())

    def test_lifecycle_stream_is_authenticated_and_tracks_disconnect(self):
        self.assertEqual(self.request('/api/lifecycle', authenticated=False)[0], 403)
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        disconnected = threading.Event()
        original = self.app.disconnect_client
        def disconnect(client_id):
            original(client_id)
            disconnected.set()
        with patch.object(self.app, 'disconnect_client', side_effect=disconnect):
            conn.request('GET', '/api/lifecycle', headers={'X-App-Key': self.app.key})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.fp.readline(), b': connected\n')
            self.assertEqual(len(self.app.clients), 1)
            response.close()
            conn.close()
            self.assertTrue(disconnected.wait(4))
        self.assertFalse(self.app.clients)

    def test_reload_and_second_tab_keep_session_running(self):
        self.app.connect_client('a')
        self.app.connect_client('b')
        self.app.disconnect_client('a')
        self.assertFalse(self.app.close_if_unused(self.app.empty_since + 100))
        self.app.disconnect_client('b')
        closed_at = self.app.empty_since
        self.assertFalse(self.app.close_if_unused(closed_at + 4.9))
        self.app.connect_client('reload')
        self.assertFalse(self.app.close_if_unused(closed_at + 6))
        self.app.disconnect_client('reload')
        self.app.empty_since = 1000.0  # Exact boundary independent of monotonic clock magnitude.
        self.assertTrue(self.app.close_if_unused(self.app.empty_since + 5))
        with self.assertRaisesRegex(ValueError, 'cerrándose'):
            self.app.start_job('unused')

    def test_tab_close_waits_for_active_copy(self):
        self.app.connect_client('a')
        self.app.jobs['job'] = {'state':'running'}
        self.app.disconnect_client('a')
        elapsed = self.app.empty_since + 10
        self.assertFalse(self.app.close_if_unused(elapsed))
        self.app.jobs['job']['state'] = 'done'
        self.assertTrue(self.app.close_if_unused(elapsed))

    def test_unused_launch_exits_after_startup_grace(self):
        self.app.empty_since = 1000.0
        self.assertFalse(self.app.close_if_unused(self.app.empty_since + 119))
        self.assertTrue(self.app.close_if_unused(self.app.empty_since + 120))

    def test_preview_export_and_history_over_http(self):
        root = Path(self.temp.name)
        source = root / "original.csv"
        source.write_bytes(b"x,y\n1,2\n")
        payload = {"mode": "copy", "output": str(root / "salida"), "items": [{"path": str(source)}],
                   "defaults": {"category": "record", "owner_kind": "experiment", "owner_code": "EXP-8",
                                "date": "2026-10-20", "content": "Ensayo", "version": 1}}
        payload["items"][0]["meta"] = payload["defaults"]
        status, body = self.request("/api/preview", "POST", payload)
        self.assertEqual(status, 200)
        plan = json.loads(body)
        self.assertTrue(plan["valid"])
        status, body = self.request("/api/execute", "POST", {"plan_id": plan["id"]})
        self.assertEqual(status, 200)
        job = json.loads(body)["job"]
        # Espera acotada al trabajo real, no a un tiempo arbitrario de copia.
        for thread in threading.enumerate():
            if thread.name.endswith("(run)"):
                thread.join(timeout=5)
        status, body = self.request("/api/job/" + job)
        result = json.loads(body)
        self.assertEqual(result["state"], "done", result)
        self.assertEqual(result["result"]["results"][0]["status"], "completado")
        self.assertEqual(source.read_bytes(), (root / "salida" / "2026-10-20_EXP-8_Ensayo_v01.csv").read_bytes())
        status, body = self.request("/api/history.csv")
        self.assertEqual(status, 200)
        self.assertIn("original.csv", body.decode("utf-8-sig"))
        self.assertIn("2026-10-20_EXP-8_Ensayo_v01.csv", body.decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
