import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from library import Library
from core import Engine, metadata, UserError


class QuickTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root/'DRX';self.folder.mkdir()
        self.source = self.root/'original.csv.gz';self.source.write_bytes(b'original')
        self.lib = Library(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, **kwargs):
        return self.lib.change({'revision':self.lib.read()['revision'], 'group':'templates',
            'value':{'label':'DRX', 'output':str(self.folder), 'meta':{'category':'export', 'owner_kind':'characterization',
                'technique':'DRX', 'content':'Difractograma','owner_code':'CAR-99','date':'2000-01-01'}},**kwargs})

    def test_persistent_template_without_old_ids_or_dates(self):
        data=self.save();self.assertEqual(Library(self.root).read(), data)
        meta=data['templates'][0]['meta']
        self.assertNotIn('owner_code',meta);self.assertNotIn('date',meta)
        engine=Engine(self.root/'state')
        req={'items':[{'path':str(self.source),'output':str(self.folder),
            'meta':{**meta,'owner_code':'CAR-2','date':'2026-10-21'}}]}
        plan=engine.preview(req);self.assertTrue(plan['valid'],plan)
        engine.execute(plan['id'])
        self.assertEqual((self.folder/'2026-10-21_CAR-2_DRX_Difractograma.csv.gz').read_bytes(),b'original')
        self.assertTrue(self.source.exists())
        self.assertFalse(engine.preview(req)['valid'])
        self.assertEqual(self.lib.read(),data)

    def test_edit_delete_only_changes_library_and_rejects_stale_revision(self):
        data=self.save();row=data['templates'][0]
        with self.assertRaises(UserError):self.lib.change({'revision':0,'group':'templates','delete':True,'id':row['id']})
        self.save(id=row['id'],value={'label':'Renombrada','output':str(self.folder),'meta':row['meta']})
        self.lib.change({'revision':2,'group':'templates','delete':True,'id':row['id']})
        self.assertEqual(self.lib.read()['templates'],[]);self.assertTrue(self.folder.is_dir())

    def test_invalid_save_preserves_library(self):
        self.save();before=self.lib.path.read_bytes()
        for val in ({'label':'DRX','output':str(self.folder)}, {'label':'Nueva','output':str(self.root/'missing')}):
            with self.assertRaises(UserError):self.save(value=val)
        self.assertEqual(self.lib.path.read_bytes(),before)
        self.lib.path.write_text('broken')
        with self.assertRaises(UserError):self.lib.read()
        self.assertEqual(self.lib.path.read_text(),'broken')

    def test_direct_name_extension_date_id_and_paths(self):
        meta={'category':'export','quick_name':'2026-10-21_EXP-3_Ensayo_r01'}
        result=metadata(meta,self.source)
        self.assertEqual(result['exported_name'],'2026-10-21_EXP-3_Ensayo_r01.csv.gz')
        self.assertEqual(result['owner_code'],'EXP-3');self.assertEqual(result['owner_kind'],'experiment')
        for name in ('../escaped','2026-02-30_CAR-3_Foo','2026-10-21_CAR-03_Foo','2026-10-21_CAR-3_Foo.csv'):
            with self.assertRaises(UserError):metadata({**meta,'quick_name':name},self.source)
        with self.assertRaises(UserError):metadata({**meta,'category':'raw_copy'},self.source)

    def test_favorite_does_not_claim_or_change_folder(self):
        result=self.lib.change({'revision':0,'group':'favorites','value':{'label':'DRX','output':str(self.folder)}})
        self.assertNotIn('meta',result['favorites'][0]);self.assertEqual(list(self.folder.iterdir()),[])
