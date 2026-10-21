import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import Engine, UserError
from workflow import audit, recommend, structure, EXPECTED


class GuidedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.doctorado = self.root / 'Doctorado'
        for name in EXPECTED + ['00_Entrada']:
            (self.doctorado / name).mkdir(parents=True)
        for name, sub in [('Caracterizacion', '02_Exportaciones'), ('Caracterizacion', '01_RAW'), ('Resultado', '02_Origin'), ('Resultado', '04_Figuras_exportadas')]:
            (self.doctorado / '90_Plantillas' / name / sub).mkdir(parents=True, exist_ok=True)
        self.source = self.doctorado / '00_Entrada' / 'equipo.csv'
        self.source.write_bytes(b'prueba')
        catalog = self.root / 'catalog.json'
        catalog.write_text(json.dumps({'records': []}))
        self.engine = Engine(self.root / 'estado', catalog)
        self.engine.doctorado = self.doctorado
        self.meta = {'owner_code':'CAR-27', 'owner_kind':'characterization', 'category':'export', 'date':'2026-10-21'}

    def tearDown(self):
        self.temp.cleanup()

    def test_existing_inbox_and_both_inboxes(self):
        self.assertEqual(structure(self.doctorado)['inboxes'], [str(self.doctorado / '00_Entrada')])
        (self.doctorado / 'Entrada').mkdir()
        self.assertEqual(len(structure(self.doctorado)['inboxes']), 2)
        self.assertTrue(any(f['kind']=='entrada' for f in audit(self.doctorado)['findings']))

    def test_drx_reuses_existing_folder_and_its_original_case(self):
        folder=self.doctorado/'04_Caracterizaciones'/'DRX';folder.mkdir()
        result=recommend(self.doctorado,self.meta,self.source,'drx')
        self.assertEqual(result['output'],str(folder))
        self.assertFalse(result['new_folder'])
        self.assertEqual(list(folder.iterdir()),[])

    def test_two_car_records_share_drx_without_id_folders(self):
        entries=[]
        for owner in ('CAR-27','CAR-28'):
            meta={**self.meta,'owner_code':owner,'content':'Espectro'}
            result=recommend(self.doctorado,meta,self.source,'DRX')
            entries.append({'path':str(self.source),'meta':meta,'output':result['output']})
        # Un lote no admite la misma fuente dos veces, por lo que usamos otra adquisición.
        other=self.source.with_name('otro.csv');other.write_bytes(b'otra adquisicion')
        entries[1]['path']=str(other)
        plan=self.engine.preview({'items':entries})
        self.assertTrue(plan['valid'])
        self.assertFalse((self.doctorado/'04_Caracterizaciones'/'DRX').exists())
        results=self.engine.execute(plan['id'])['results']
        self.assertTrue(all(r['status']=='completado' for r in results))
        folder=self.doctorado/'04_Caracterizaciones'/'DRX'
        self.assertEqual({p.name for p in folder.iterdir()}, {'2026-10-21_CAR-27_Espectro.csv','2026-10-21_CAR-28_Espectro.csv'})
        self.assertFalse(any(f['kind'] in ('carpeta','ubicacion') and 'DRX' in f['path'] for f in audit(self.doctorado)['findings']))

    def test_folder_name_rejects_paths_devices_and_existing_file(self):
        for name in ('../DRX',r'D:\DRX','NUL','CON','..'):
            with self.subTest(name=name),self.assertRaises(UserError):
                recommend(self.doctorado,self.meta,self.source,name)
        (self.doctorado/'04_Caracterizaciones'/'DRX').write_text('original')
        with self.assertRaises(UserError):
            recommend(self.doctorado,self.meta,self.source,'DRX')

    def test_legacy_record_reused_when_folder_name_is_blank(self):
        record=self.doctorado / '04_Caracterizaciones' / 'CAR-27__Existente'
        record.mkdir()
        result=recommend(self.doctorado,self.meta,self.source)
        self.assertEqual(result['output'], str(record / '02_Exportaciones'))
        self.assertFalse(result['new_record'])
        self.assertFalse((record / '02_Exportaciones').exists())

    def test_new_record_requires_description_and_preview_does_not_create(self):
        with self.assertRaises(UserError):
            recommend(self.doctorado,self.meta,self.source)
        result=recommend(self.doctorado,self.meta,self.source,'Señal FTIR')
        self.assertEqual(Path(result['output']).name,'Senal_FTIR')
        self.assertTrue(result['new_folder'])
        plan=self.engine.preview({'mode':'copy','items':[{'path':str(self.source),'output':result['output'],'meta':self.meta}]})
        self.assertTrue(plan['valid'])
        self.assertFalse(Path(result['output']).exists())
        # Ninguna función de hash puede ejecutarse durante selección, revisión o copia.
        with patch('hashlib.sha256', side_effect=AssertionError('No calcular hashes')):
            done=self.engine.execute(plan['id'])
        self.assertEqual(done['results'][0]['status'],'completado')
        self.assertTrue(self.source.exists())
        self.assertEqual(list(Path(result['output']).glob('Registro*')),[])

    def test_duplicate_id_blocks_proposal(self):
        for description in ('Uno','Dos'):
            (self.doctorado/'04_Caracterizaciones'/('CAR-27__'+description)).mkdir()
        with self.assertRaises(UserError):
            recommend(self.doctorado,self.meta,self.source)
        self.assertTrue(any(f['kind']=='duplicado' for f in audit(self.doctorado)['findings']))

    def test_manual_destination_cannot_bypass_record_rules(self):
        for output in (self.doctorado/'04_Caracterizaciones', self.doctorado/'00_Entrada', self.doctorado/'04_Caracterizaciones'/'CAR-28__Otro'):
            with self.subTest(output=output):
                plan=self.engine.preview({'output':str(output),'items':[{'path':str(self.source),'meta':self.meta}]})
                self.assertFalse(plan['valid'])

    def test_folder_replaced_by_a_file_after_review_blocks_copy(self):
        result=recommend(self.doctorado,self.meta,self.source,'Propuesto')
        plan=self.engine.preview({'output':result['output'],'items':[{'path':str(self.source),'meta':self.meta}]})
        Path(result['output']).write_bytes(b'No reemplazar')
        done=self.engine.execute(plan['id'])
        self.assertEqual(done['results'][0]['status'],'error')
        self.assertEqual(Path(result['output']).read_bytes(),b'No reemplazar')

    def test_distinct_row_destinations_and_batch_collision(self):
        other=self.source.with_name('otro.csv');other.write_bytes(b'otro')
        def preview(outputs):
            return self.engine.preview({'mode':'copy','items':[{'path':str(p),'output':str(o),'meta':{**self.meta,'content':'Espectro'}} for p,o in zip((self.source,other),outputs)]})
        a,b=self.root/'a',self.root/'b'
        plan=preview([a,b]);self.assertTrue(plan['valid'])
        result=self.engine.execute(plan['id'])
        self.assertTrue(all(r['status']=='completado' for r in result['results']))
        self.assertFalse(preview([self.root/'c',self.root/'c'])['valid'])

    def test_four_different_records_copy_in_one_batch(self):
        cases=[('CAR-701','characterization','export','04_Caracterizaciones','Caracterizacion','02_Exportaciones'),
               ('EXP-702','experiment','record','02_Experimentos','Experimento','02_Registro'),
               ('MUE-703','sample','photo','03_Muestras','Muestra','01_Fotos'),
               ('RES-704','result','table','05_Resultados','Resultado','05_Tablas')]
        entries=[]
        for index,(owner,kind,category,parent,template,sub) in enumerate(cases):
            (self.doctorado/'90_Plantillas'/template/sub).mkdir(parents=True,exist_ok=True)
            source=self.source.with_name(f'archivo_{index}.txt');source.write_text(f'datos {index}')
            meta={**self.meta,'owner_code':owner,'owner_kind':kind,'category':category,'content':f'Contenido_{index}'}
            destination=recommend(self.doctorado,meta,source,f'Registro_{index}')['output']
            self.assertEqual(Path(destination).parts[-2],parent)
            entries.append({'path':str(source),'meta':meta,'output':destination})
        plan=self.engine.preview({'items':entries})
        self.assertTrue(plan['valid'])
        results=self.engine.execute(plan['id'])['results']
        self.assertEqual(len(results),4)
        for index,row in enumerate(results):
            self.assertEqual(row['status'],'completado')
            self.assertEqual(Path(row['destination']).read_text(),f'datos {index}')
            self.assertEqual(Path(row['source']).read_text(),f'datos {index}')

    def test_copy_failure_is_recorded_and_original_is_preserved(self):
        out=self.root/'salida'
        plan=self.engine.preview({'output':str(out),'items':[{'path':str(self.source),'meta':self.meta}]})
        with patch('core.shutil.copyfileobj',side_effect=OSError('Drive no disponible')):
            done=self.engine.execute(plan['id'])
        self.assertEqual(done['results'][0]['status'],'error')
        self.assertEqual(self.source.read_bytes(),b'prueba')
        self.assertEqual(list(out.iterdir()),[])
        self.assertIn('Drive no disponible',self.engine.history()[0]['error'])

    def test_audit_names_location_dates_raw_and_readonly(self):
        record=self.doctorado/'04_Caracterizaciones'/'CAR-27__Ensayo';raw=record/'01_RAW';raw.mkdir(parents=True)
        (raw/'nombre propio.raw').write_bytes(b'raw')
        (record/'2026-02-30_CAR-27_Espectro.csv').write_bytes(b'fecha')
        (record/'2026-10-21_CAR-28_Espectro.csv').write_bytes(b'id')
        (record/'2026-10-21_CAR-27_Espectro_r0.csv').write_bytes(b'replica')
        before={str(p):p.read_bytes() for p in self.doctorado.rglob('*') if p.is_file()}
        result=audit(self.doctorado)
        self.assertFalse(any('nombre propio' in f['path'] for f in result['findings']))
        self.assertEqual(len([f for f in result['findings'] if f['kind']=='nombre']),2)
        self.assertTrue(any(f['kind']=='ubicacion' for f in result['findings']))
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.doctorado.rglob('*') if p.is_file()})

    @unittest.skipUnless(os.name=='nt','Uniones Windows')
    def test_link_inserted_after_preview_blocks_export(self):
        import subprocess
        out=self.root/'salida';out.mkdir();real=self.root/'otra';real.mkdir()
        plan=self.engine.preview({'output':str(out),'items':[{'path':str(self.source),'meta':self.meta}]})
        out.rmdir()
        subprocess.run(['cmd','/c','mklink','/J',str(out),str(real)],check=True,capture_output=True)
        try:
            done=self.engine.execute(plan['id'])
            self.assertEqual(done['results'][0]['status'],'error')
            self.assertEqual(list(real.iterdir()),[])
        finally:
            out.rmdir()

if __name__=='__main__':
    unittest.main()
