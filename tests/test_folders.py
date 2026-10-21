from pathlib import Path
import tempfile
import unittest

from core import UserError
from folders import SessionFolders


class SessionFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'Doctorado'
        self.parent=self.root/'04_Caracterizaciones';self.parent.mkdir(parents=True)
        self.previous=self.parent/'DRX';self.previous.mkdir()
        self.manager=SessionFolders(self.root)
        self.meta={'owner_kind':'characterization','owner_code':'CAR-27'}

    def tearDown(self):
        self.temp.cleanup()

    def test_existing_folder_never_acquires_deletion_permission(self):
        result=self.manager.create(self.meta,'drx')
        self.assertFalse(result['created'])
        self.assertEqual(result['path'],str(self.previous))
        folder=result['folders'][0]
        self.assertIsNone(folder['token']);self.assertFalse(folder['can_delete'])
        with self.assertRaises(UserError):
            self.manager.delete(str(self.previous))
        self.assertTrue(self.previous.exists())

    def test_explicit_creation_and_empty_removal_in_same_session(self):
        result=self.manager.create(self.meta,'FTIR')
        target=Path(result['path']);self.assertTrue(target.is_dir())
        row=next(r for r in result['folders'] if r['name']=='FTIR')
        self.assertTrue(row['can_delete'])
        deleted=self.manager.delete(row['token'])
        self.assertEqual(deleted['deleted'],str(target));self.assertFalse(target.exists())
        self.assertTrue(self.previous.exists())

    def test_new_session_cannot_remove_previous_session_folder(self):
        result=self.manager.create(self.meta,'FTIR')
        token=next(r['token'] for r in result['folders'] if r['name']=='FTIR')
        other=SessionFolders(self.root)
        self.assertFalse(next(r for r in other.list(self.meta)['folders'] if r['name']=='FTIR')['created_in_session'])
        with self.assertRaises(UserError):other.delete(token)
        self.assertTrue(Path(result['path']).exists())

    def test_files_or_subfolders_block_removal_without_deleting_contents(self):
        for name,is_dir in (('Con_archivo',False),('Con_subcarpeta',True)):
            with self.subTest(name=name):
                result=self.manager.create(self.meta,name)
                target=Path(result['path']);child=target/'dato'
                if is_dir:child.mkdir()
                else:child.write_text('NO TOCAR')
                row=next(r for r in self.manager.list(self.meta)['folders'] if r['name']==name)
                self.assertTrue(row['created_in_session']);self.assertFalse(row['can_delete'])
                with self.assertRaises(UserError):self.manager.delete(row['token'])
                self.assertTrue(child.exists())

    def test_replaced_folder_is_not_deleted(self):
        result=self.manager.create(self.meta,'Temporal')
        target=Path(result['path'])
        token=next(r['token'] for r in result['folders'] if r['name']=='Temporal')
        target.rename(self.parent/'Original_movida')
        target.mkdir()
        with self.assertRaises(UserError):self.manager.delete(token)
        self.assertTrue(target.exists())

    def test_category_boundary_and_unsafe_names_are_rejected(self):
        for name in ('../Otra','NUL',r'D:\Otra','DRX/Subcarpeta'):
            with self.subTest(name=name),self.assertRaises(UserError):self.manager.create(self.meta,name)
        with self.assertRaises(UserError):self.manager.create(self.meta,'Otra',self.root)
        self.assertEqual([p.name for p in self.parent.iterdir()],['DRX'])

    def test_multiple_new_folders_remain_session_owned(self):
        self.manager.create(self.meta,'Uno');self.manager.create(self.meta,'Dos')
        rows=[r for r in self.manager.list(self.meta)['folders'] if r['created_in_session']]
        self.assertEqual({r['name'] for r in rows},{'Uno','Dos'})

if __name__=='__main__':unittest.main()
