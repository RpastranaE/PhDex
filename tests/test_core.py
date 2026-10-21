import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Engine, UserError, metadata


class FileWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doctorado-qa-")
        self.root = Path(self.temp.name)
        self.input = self.root / "entrada"
        self.output = self.root / "salida"
        self.input.mkdir()
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps({"updated_at": "2026-10-20", "records": [{"kind": "characterization", "code": "CAR-27", "title": "Ensayo ficticio", "url": "https://app.notion.com/p/11111111111111111111111111111111"}]}), encoding="utf-8")
        self.engine = Engine(self.root / "registro", self.catalog)
        self.meta = {"category": "export", "owner_kind": "characterization", "owner_code": "CAR-27", "date": "2026-10-20", "samples": "MUE-8", "technique": "FTIR-ATR", "content": "Espectro", "replicate": 1, "version": 0}

    def tearDown(self):
        self.temp.cleanup()

    def file(self, name="instrumento.csv", content=b"numero,intensidad\n1,0.5\n"):
        path = self.input / name
        path.write_bytes(content)
        return path

    def plan(self, paths, meta=None, mode="copy", output=None):
        return self.engine.preview({"mode": mode, "output": str(output or self.output), "items": [{"path": str(p), "meta": meta or self.meta} for p in paths]})

    def test_exact_naming_and_replicates(self):
        p = self.file()
        self.assertEqual(metadata(self.meta, p)["exported_name"], "2026-10-20_CAR-27_MUE-8_FTIR-ATR_Espectro_r01.csv")
        changed = {**self.meta, "owner_kind": "result", "owner_code": "RES-6", "content": "Ajuste de bandas", "samples": "", "technique": "", "replicate": 0, "version": 2}
        self.assertEqual(metadata(changed, p)["exported_name"], "2026-10-20_RES-6_Ajuste_de_bandas_v02.csv")

    def test_compound_extension_and_accents(self):
        p = self.file("máximo.csv.gz")
        m = metadata({**self.meta, "content": "Señal: carbóñ / integración", "replicate": 0}, p)
        self.assertEqual(m["exported_name"], "2026-10-20_CAR-27_MUE-8_FTIR-ATR_Senal_carbon_integracion.csv.gz")

    def test_manual_ids_no_new_numbering(self):
        p = self.file()
        for value in ("CAR-027", "CAR-0", "../CAR-27", "EXP-27"):
            with self.subTest(value=value), self.assertRaises(UserError):
                metadata({**self.meta, "owner_code": value}, p)

    def test_copy_preserves_content_and_history_without_hash_or_report(self):
        p = self.file()
        plan = self.plan([p])
        self.assertTrue(plan["valid"])
        result = self.engine.execute(plan["id"])
        row = result["results"][0]
        target = Path(row["destination"])
        self.assertEqual(row["status"], "completado")
        self.assertEqual(p.read_bytes(), target.read_bytes())
        self.assertEqual(row["sha256"], "")
        self.assertEqual(result["manifest"], "")
        self.assertEqual(len(list(self.output.iterdir())), 1)
        log = self.engine.history()[0]
        self.assertEqual(log["source"], str(p))
        self.assertEqual(log["destination"], str(target))
        self.assertEqual(log["notion_url"], "")
        exported = list(csv.DictReader(io.StringIO(self.engine.csv_text().lstrip("\ufeff")), delimiter=";"))
        self.assertEqual(exported[0]["nombre_original"], p.name)
        self.assertEqual(exported[0]["ruta_exportada"], str(target))

    def test_repeat_same_plan_and_existing_output_rejected(self):
        p = self.file()
        plan = self.plan([p])
        self.engine.execute(plan["id"])
        with self.assertRaises(UserError):
            self.engine.execute(plan["id"])
        new_plan = self.plan([p])
        self.assertFalse(new_plan["valid"])
        self.assertEqual(len(list(self.output.glob("2026*.csv"))), 1)

    def test_existing_file_never_overwritten(self):
        p = self.file()
        self.output.mkdir()
        dest = self.output / metadata(self.meta, p)["exported_name"]
        dest.write_bytes(b"NO CAMBIAR")
        plan = self.plan([p])
        self.assertFalse(plan["valid"])
        self.assertEqual(dest.read_bytes(), b"NO CAMBIAR")

    def test_destination_appearing_after_preview_is_safe(self):
        p = self.file()
        plan = self.plan([p])
        self.output.mkdir()
        target = Path(plan["items"][0]["destination"])
        target.write_bytes(b"aparecio despues")
        result = self.engine.execute(plan["id"])
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertEqual(target.read_bytes(), b"aparecio despues")
        self.assertTrue(p.exists())
        self.assertEqual(list(self.output.glob("*.part")), [])

    def test_source_changed_after_preview_does_not_export(self):
        p = self.file()
        plan = self.plan([p])
        p.write_bytes(b"nuevos datos")
        result = self.engine.execute(plan["id"])
        self.assertEqual(result["results"][0]["status"], "error")
        self.assertFalse(Path(plan["items"][0]["destination"]).exists())

    def test_collisions_within_batch(self):
        p, q = self.file("uno.csv"), self.file("dos.csv")
        plan = self.plan([p, q])
        self.assertFalse(plan["valid"])
        self.assertTrue(all(r["error"] for r in plan["items"]))

    def test_rename_requires_review_and_keeps_extension(self):
        p = self.file()
        plan = self.plan([p], mode="rename")
        target = Path(plan["items"][0]["destination"])
        result = self.engine.execute(plan["id"])
        self.assertEqual(result["results"][0]["status"], "completado")
        self.assertFalse(p.exists())
        self.assertTrue(target.exists())
        self.assertEqual(target.suffix, ".csv")
        self.assertEqual(target.parent, self.input)

    def test_raw_original_not_renamed(self):
        p = self.file("Nombre de equipo sin normalizar.RAW")
        meta = {**self.meta, "category": "raw_original", "version": 0}
        plan = self.plan([p], meta)
        self.assertEqual(plan["items"][0]["name"], p.name)
        result = self.engine.execute(plan["id"])
        self.assertTrue(p.exists())
        self.assertEqual(Path(result["results"][0]["destination"]).name, p.name)
        self.assertFalse(self.plan([p], meta, mode="rename")["valid"])

    def test_raw_copy_independence_and_companions(self):
        p = self.file("datos.wiff")
        meta = {**self.meta, "category": "raw_copy"}
        self.assertFalse(self.plan([p], meta)["valid"])
        self.assertTrue(self.plan([p], {**meta, "independent_raw": True})["valid"])
        self.file("datos.wiff.scan")
        self.assertFalse(self.plan([p], {**meta, "independent_raw": True})["valid"])

    @unittest.skipUnless(os.name == "nt", "Paquetes: publicación sin reemplazo de Windows")
    def test_instrument_directory_preserves_all_internal_names(self):
        folder = self.input / "Nombre original.d"
        (folder / "Subcarpeta de equipo").mkdir(parents=True)
        (folder / "carpeta_vacia").mkdir()
        (folder / "Subcarpeta de equipo" / "fid").write_bytes(b"DATOS RAW")
        (folder / "method.xml").write_text("metodo original")
        meta = {**self.meta, "category": "raw_original", "version": 0}
        plan = self.plan([folder], meta)
        result = self.engine.execute(plan["id"])
        target = Path(result["results"][0]["destination"])
        self.assertEqual(target.name, folder.name)
        self.assertEqual((target / "Subcarpeta de equipo" / "fid").read_bytes(), b"DATOS RAW")
        self.assertTrue((target / "carpeta_vacia").is_dir())
        self.assertTrue(folder.exists())

    def test_output_not_inside_input_package(self):
        folder = self.input / "adquisicion"
        folder.mkdir()
        (folder / "fid").write_bytes(b"x")
        plan = self.plan([folder], {**self.meta, "category": "raw_original"}, output=folder / "salida")
        self.assertFalse(plan["valid"])

    def test_manual_assignment_does_not_read_a_catalog(self):
        self.catalog.write_text('No es JSON; no debe leerse')
        plan = self.plan([self.file()], {**self.meta, 'owner_code':'CAR-919'})
        self.assertTrue(plan['valid'])
        self.assertFalse(any('Notion' in w for w in plan['items'][0]['warnings']))

    def test_many_samples_stored_not_repeated_in_name(self):
        m = metadata({**self.meta, "samples": "MUE-8,MUE-9"}, self.file())
        self.assertEqual(m["samples"], ["MUE-8", "MUE-9"])
        self.assertNotIn("MUE", m["exported_name"])

    def test_files_referenced_from_sources_are_not_renamed(self):
        (self.root / "AGENTS.md").write_text("sources solo lectura")
        source_dir = self.root / "sources"
        source_dir.mkdir()
        p = source_dir / "referencia.csv"
        p.write_text("original")
        self.assertFalse(self.plan([p], mode="rename")["valid"])

    def test_csv_formula_prefix_escaped(self):
        p = self.file("=formula.csv")
        plan = self.plan([p])
        self.engine.execute(plan["id"])
        self.assertIn("'=formula.csv", self.engine.csv_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
