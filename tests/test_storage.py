from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import storage


class StorageTests(unittest.TestCase):
    def test_documents_location_independent_of_executable(self):
        with patch.object(storage,'documents_dir',return_value=Path('C:/Test/Documents')):
            self.assertEqual(storage.default_data_dir(),Path('C:/Test/Documents/PhDex/datos_app'))

    def test_migration_copies_consistent_state_without_changing_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old';old.mkdir();new=root/'Documents/PhDex/datos_app'
            with closing(sqlite3.connect(old/'registro.sqlite3')) as db:
                with db:
                    db.execute('CREATE TABLE test (value TEXT)');db.execute("INSERT INTO test VALUES ('conservado')")
            (old/'plantillas_favoritos.json').write_text('{"test":1}')
            self.assertTrue(storage.migrate_legacy_data(new,old))
            with closing(sqlite3.connect(new/'registro.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT value FROM test').fetchone()[0],'conservado')
            self.assertEqual((new/'plantillas_favoritos.json').read_text(),'{"test":1}')
            self.assertTrue((old/'registro.sqlite3').exists())
            (new/'plantillas_favoritos.json').write_text('{"test":2}')
            self.assertFalse(storage.migrate_legacy_data(new,old))
            self.assertEqual((new/'plantillas_favoritos.json').read_text(),'{"test":2}')

    def test_absent_legacy_does_not_create_data_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertFalse(storage.migrate_legacy_data(root/'new',root/'missing'))
            self.assertFalse((root/'new').exists())
