import base64
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import LocalApp, Handler, ThreadingHTTPServer
from intake import recognize,rule_matches
from core import UserError


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.doc=self.root/'Doctorado';self.inbox=self.doc/'00_Entrada';self.inbox.mkdir(parents=True)
        self.output=self.doc/'04_Caracterizaciones'/'DRX';self.output.mkdir(parents=True)
        self.app=LocalApp(self.root/'state',self.doc)
        self.service=self.app.intake

    def tearDown(self):self.temp.cleanup()

    def test_multiple_conditions_all_any_and_legacy(self):
        rule={'combine':'all','conditions':[{'match':'contains','pattern':'DRX'},{'match':'extension','pattern':'csv'}]}
        self.assertTrue(rule_matches(rule,'CAR-27_drx.csv'))
        self.assertFalse(rule_matches(rule,'DRX.xlsx'))
        self.assertFalse(rule_matches(rule,'FTIR.csv'))
        rule['combine']='any'
        self.assertTrue(rule_matches(rule,'DRX.xlsx'))
        self.assertTrue(rule_matches(rule,'FTIR.csv'))
        self.assertFalse(rule_matches(rule,'FTIR.xlsx'))
        self.assertTrue(rule_matches({'match':'contains','pattern':'drx'},'DRX.csv'))
        self.assertTrue(rule_matches({'conditions':[{'match':'starts_with','pattern':'CAR-'},{'match':'ends_with','pattern':'_RAW.csv'},{'match':'not_contains','pattern':'descartar'}]},'CAR-27_DRX_RAW.csv'))

    def test_multiple_conditions_validation_and_persistence(self):
        t=self.app.library.change({'revision':0,'group':'templates','value':{'label':'DRX','output':str(self.output),'meta':{'category':'export','owner_kind':'characterization'}}})['templates'][0]
        value={'label':'DRX CSV','combine':'all','conditions':[{'match':'contains','pattern':'DRX'},{'match':'extension','pattern':'.csv'}],'template':t['id']}
        saved=self.service.change({'revision':0,'value':value})
        self.assertEqual(saved['rules'][0]['conditions'],value['conditions'])
        self.assertEqual(len(self.service.suggestions('drx.csv')['matches']),1)
        self.assertEqual(self.service.suggestions('drx.xlsx')['matches'],[])
        for override in ({'conditions':[]},{'conditions':[{'match':'unknown','pattern':'x'}]},{'combine':'invalid'},{'conditions':[{'match':'contains','pattern':''}]},{'conditions':[{'match':'contains','pattern':'x'}]*21}):
            with self.assertRaises(UserError):self.service.change({'revision':1,'value':{**value,**override}})
        self.assertEqual(self.service.read(),saved)

    def test_recognition_ambiguity_dates_and_complete_name(self):
        result=recognize('DRX CAR-27 2026-10-21.csv')['meta']
        self.assertEqual(result,{'owner_code':'CAR-27','owner_kind':'characterization','date':'2026-10-21','technique':'DRX'})
        self.assertNotIn('owner_code',recognize('CAR-27_EXP-12.csv')['meta'])
        self.assertNotIn('date',recognize('2026-02-30_CAR-2_DRX.csv')['meta'])
        self.assertNotIn('date',recognize('2026-01-01_2026-01-02.csv')['meta'])
        self.assertNotIn('technique',recognize('XDRX_JDRX.csv')['meta'])
        self.assertNotIn('technique',recognize('DRX FTIR.csv')['meta'])
        self.assertEqual(recognize('2026-10-21_CAR-27_MUE-8_DRX_Datos_r02_v01.csv.gz')['meta']['quick_name'],'2026-10-21_CAR-27_MUE-8_DRX_Datos_r02_v01')
        self.assertNotIn('quick_name',recognize('2026-10-21_CAR-27_Datos_r0.csv')['meta'])

    def test_rules_persist_conflicts_and_removed_template(self):
        t=self.app.library.change({'revision':0,'group':'templates','value':{'label':'DRX','output':str(self.output),'meta':{'category':'export','owner_kind':'characterization','technique':'DRX'}}})['templates'][0]
        for n,(match,pattern) in enumerate([('contains','DRX'),('extension','.csv.gz')]):
            data=self.service.change({'revision':n,'value':{'label':str(n),'match':match,'pattern':pattern,'template':t['id']}})
        self.assertEqual(len(self.service.suggestions('drx.csv.gz')['matches']),2)
        with self.assertRaises(UserError):self.service.change({'revision':0,'inbox':str(self.inbox)})
        self.app.library.change({'revision':1,'group':'templates','id':t['id'],'delete':True})
        self.assertEqual(self.service.suggestions('DRX.csv.gz')['matches'],[])
        self.assertEqual(self.service.read(),data)
        self.assertEqual(list(self.output.iterdir()),[])

    def test_inbox_change_import_collision_invalid_and_truncation(self):
        other=self.root/'Otra entrada';other.mkdir()
        self.service.change({'revision':0,'inbox':str(other)})
        path=Path(self.service.import_file('á.csv',io.BytesIO(b'123'),3))
        self.assertEqual(path,other/'á.csv');self.assertEqual(path.read_bytes(),b'123')
        for name in ('../x.csv','x/archivo','NUL.txt','x.csv:ads','trailing.',''):
            with self.assertRaises(UserError):self.service.import_file(name,io.BytesIO(),0)
        with self.assertRaises(UserError):self.service.import_file('á.csv',io.BytesIO(b'456'),3)
        with self.assertRaises(UserError):self.service.import_file('cortado.csv',io.BytesIO(b'x'),2)
        self.assertEqual(path.read_bytes(),b'123')
        self.assertEqual([p.name for p in other.iterdir()],['á.csv'])
        self.assertEqual(self.service.read()['inbox'],str(other))

    def test_pending_changed_deleted_output_and_deleted_history(self):
        source=self.inbox/'datos.csv';source.write_bytes(b'abc')
        self.assertFalse(self.service.listing()['items'][0]['exported'])
        plan=self.app.engine.preview({'mode':'copy','items':[{'path':str(source),'output':str(self.output),'meta':{'category':'export','owner_kind':'characterization','owner_code':'CAR-27','date':'2026-10-21','content':'Datos'}}]})
        result=self.app.engine.execute(plan['id'])
        self.assertTrue(self.service.listing()['items'][0]['exported'])
        stat=source.stat();source.write_bytes(b'abcdef')
        self.assertFalse(self.service.listing()['items'][0]['exported'])
        source.write_bytes(b'abc');os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        self.assertTrue(self.service.listing()['items'][0]['exported'])
        Path(result['results'][0]['destination']).unlink()
        self.assertFalse(self.service.listing()['items'][0]['exported'])
        self.app.engine.delete_history([result['results'][0]['id']],True)
        self.assertFalse(self.service.listing()['items'][0]['exported'])

    def test_server_import_names_and_open_destinations(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.app=self.app
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def req(path,body,headers=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
            h={'X-App-Key':self.app.key,'Content-Type':'application/json'};h.update(headers or {})
            conn.request('POST',path,body,h);r=conn.getresponse();data=json.loads(r.read());status=r.status;conn.close();return status,data
        try:
            hdr={'Content-Type':'application/octet-stream','X-File-Name':base64.b64encode('DRX CAR-27.csv'.encode()).decode()}
            self.assertEqual(req('/api/import',b'x',{**hdr,'X-App-Key':'invalid'})[0],403)
            status,data=req('/api/import',b'x',hdr);self.assertEqual(status,200,data)
            self.assertEqual(req('/api/import',b'other',hdr)[0],400)
            source=Path(data['path']);self.assertEqual(source.read_bytes(),b'x')
            inspected=req('/api/inspect',json.dumps({'paths':[str(source)]}))[1]['items'][0]
            self.assertEqual(inspected['suggestions']['meta']['owner_code'],'CAR-27')
            meta={'category':'export','owner_kind':'characterization','owner_code':'CAR-27','date':'2026-10-21','content':'Datos'}
            status,preview=req('/api/names',json.dumps({'items':[{'key':'one','path':str(source),'meta':meta}]}))
            self.assertEqual(preview['items'][0]['name'],'2026-10-21_CAR-27_Datos.csv')
            self.assertFalse(list(self.output.iterdir()))
            self.assertEqual(req('/api/open-destinations',json.dumps({'paths':[str(self.output)]}))[0],400)
            plan=self.app.engine.preview({'mode':'copy','items':[{'path':str(source),'output':str(self.output),'meta':meta}]})
            self.app.engine.execute(plan['id'])
            with patch('app.os.startfile',create=True) as opener:
                status,data=req('/api/open-destinations',json.dumps({'paths':[str(self.output),str(self.output)]}))
                self.assertEqual(status,200,data);opener.assert_called_once_with(str(self.output))
                self.assertEqual(len(data['opened']),1)
            self.assertEqual(source.read_bytes(),b'x')
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
