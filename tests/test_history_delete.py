import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Engine, UserError


class HistoryDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=self.root/'source.txt';self.source.write_text('original')
        self.output=self.root/'out.txt';self.output.write_text('exportado')
        self.engine=Engine(self.root/'state')
        with self.engine.db() as db:
            for n,status in enumerate(('completado','error','en_curso')):
                db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)',
                    (f'{n:032x}','batch','2026-10-21',status,str(self.source),str(self.output),'',json.dumps({}),'test'))

    def tearDown(self):self.temp.cleanup()

    def test_deletes_selected_records_only_and_preserves_files(self):
        self.assertEqual(self.engine.delete_history(['0'*32,'1'.zfill(32),'0'*32],True),{'deleted':2})
        self.assertEqual(len(self.engine.history()),1)
        self.assertEqual(self.source.read_text(),'original');self.assertEqual(self.output.read_text(),'exportado')

    def test_confirmation_validation_and_active_records_are_atomic(self):
        for ids,confirmed in ((['0'*32],False),([],True),(['bad'],True),(['0'*32,'9'*32],True),(['0'*32,'2'.zfill(32)],True)):
            with self.assertRaises(UserError):self.engine.delete_history(ids,confirmed)
            self.assertEqual(len(self.engine.history()),3)
