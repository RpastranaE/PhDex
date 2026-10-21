"""Nombres y operaciones locales. No requiere bibliotecas externas."""
from __future__ import annotations

import csv
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import threading
import unicodedata
import uuid
from datetime import date, datetime, timezone


KINDS = {"experiment": "EXP", "sample": "MUE", "characterization": "CAR", "result": "RES", "other": ""}
CATEGORIES = {
    "raw_original": {"label": "RAW original · conservar nombres", "owner": "characterization", "hint": "CAR / 01_RAW · adquisición completa y nombres originales"},
    "raw_copy": {"label": "RAW independiente · copia renombrada", "owner": "characterization", "hint": "Copia de trabajo; nunca sustituye el RAW original"},
    "export": {"label": "Exportación del equipo", "owner": "characterization", "hint": "CAR / 02_Exportaciones"},
    "processed": {"label": "Datos procesados / Excel", "owner": "characterization", "hint": "CAR / 03_Procesamiento; RES si sustenta un hallazgo"},
    "origin": {"label": "Proyecto de Origin / análisis", "owner": "result", "hint": "RES / 02_Origin; conserva las versiones de ajustes relevantes"},
    "figure": {"label": "Figura editable o exportada", "owner": "result", "hint": "RES · figura maestra y sus exportaciones"},
    "table": {"label": "Tabla de resultados", "owner": "result", "hint": "RES · tabla que sustenta el resultado"},
    "report": {"label": "Informe / justificante", "owner": "characterization", "hint": "CAR para informe del equipo; LIMS para justificante"},
    "photo": {"label": "Fotografía de muestra", "owner": "sample", "hint": "MUE · documentación y fotografías de la muestra"},
    "record": {"label": "Registro / documento experimental", "owner": "experiment", "hint": "EXP · diseño, registro y conclusiones"},
    "other": {"label": "Otro documento o archivo", "owner": "other", "hint": "Elige el ID real del registro al que pertenece"},
}
COMPOUND_EXTENSIONS = (".wiff.scan", ".tar.gz", ".tar.bz2", ".tar.xz", ".csv.gz", ".nii.gz")


class UserError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_- ")


def code(value, kind="other", required=True):
    value = str(value or "").strip().upper()
    if not value and not required:
        return ""
    pattern = r"[A-Z][A-Z0-9]{1,11}-[1-9][0-9]*"
    if not re.fullmatch(pattern, value) and not re.fullmatch(r"LIMS-[0-9]{4}-[0-9]+", value):
        raise UserError("Escribe un ID sin ceros añadidos (por ejemplo, CAR-27).")
    prefix = KINDS.get(kind)
    if prefix is None:
        raise UserError("Tipo de registro desconocido.")
    if prefix and not value.startswith(prefix + "-"):
        raise UserError(f"El registro seleccionado necesita un ID {prefix}-…")
    return value


def codes(value, kind):
    values = value if isinstance(value, list) else re.split(r"[,;\s]+", str(value or ""))
    return list(dict.fromkeys(code(v, kind) for v in values if str(v).strip()))


def extension(path: Path):
    for ext in COMPOUND_EXTENSIONS:
        if path.name.lower().endswith(ext):
            return path.name[-len(ext):]
    return path.suffix


def is_link(path: Path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def absolute(value):
    p = Path(str(value or "").strip().strip('"')).expanduser()
    if not p.is_absolute():
        raise UserError("Introduce una ruta absoluta de Windows o utiliza el selector.")
    return p


def under(path: Path, root: Path):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def tree_files(path: Path):
    if is_link(path):
        raise UserError("No se admiten enlaces simbólicos ni uniones de carpetas.")
    if path.is_file():
        yield path, Path(path.name)
        return
    if not path.is_dir():
        raise UserError("La entrada no es un archivo o una carpeta accesible.")
    def fail(error):
        raise error
    for root, dirs, files in os.walk(path, followlinks=False, onerror=fail):
        root = Path(root)
        for name in dirs:
            if is_link(root / name):
                raise UserError("El paquete contiene una carpeta enlazada. Selecciona los datos originales.")
        for name in sorted(files):
            child = root / name
            if is_link(child) or not child.is_file():
                raise UserError("El paquete contiene un enlace o un archivo especial.")
            yield child, child.relative_to(path)


def fingerprint(path: Path):
    rows = []
    total = 0
    for child, rel in tree_files(path):
        s = child.stat()
        rows.append((str(rel), s.st_size, s.st_mtime_ns, s.st_ino))
        total += s.st_size
    if path.is_dir():
        # Incluye directorios vacíos y sus fechas, además de todos los archivos.
        for root, dirs, _ in os.walk(path):
            for name in sorted(dirs):
                p = Path(root) / name
                s = p.stat()
                rows.append((str(p.relative_to(path)) + "/", 0, s.st_mtime_ns, s.st_ino))
    return {"signature": sorted(rows), "bytes": total, "files": sum(not r[0].endswith("/") for r in rows)}


def metadata(meta, source: Path):
    if not isinstance(meta, dict):
        raise UserError("Faltan los metadatos del archivo.")
    quick_name = str(meta.get('quick_name', '')).strip()
    if quick_name:
        if source.is_dir() or str(meta.get('category', '')).startswith('raw_'):
            raise UserError('RAW y paquetes conservan sus reglas; vacía el nombre manual.')
        from workflow import FILE
        match = FILE.fullmatch(quick_name)
        if (not match or len(quick_name + extension(source)) > 240
                or re.search(r'(?:^|_)(?:r|v)(?:0|0{2,}|[1-9])(?:_|$)', quick_name)):
            raise UserError('Nombre manual: usa AAAA-MM-DD_ID_Descripcion sin extensión, espacios ni rutas.')
        # La auditoría y el historial deben registrar el ID y la fecha reales del nombre.
        meta = {**meta, 'date': match[1], 'owner_code': match[2],
                'owner_kind': next((k for k, v in KINDS.items() if v and match[2].startswith(v+'-')), 'other'),
                'content': match[3], 'technique': '', 'samples': [], 'replicate': 0, 'version': 0}
    category = str(meta.get("category", "export"))
    if category not in CATEGORIES:
        raise UserError("Elige un tipo de archivo.")
    kind = str(meta.get("owner_kind", CATEGORIES[category]["owner"]))
    owner = code(meta.get("owner_code"), kind)
    try:
        day = date.fromisoformat(str(meta.get("date", ""))).isoformat()
    except ValueError:
        raise UserError("Introduce una fecha válida: adquisición, emisión o creación, según el archivo.")
    sample_codes = codes(meta.get("samples", []), "sample")
    experiment_codes = codes(meta.get("experiments", []), "experiment")
    characterization_codes = codes(meta.get("characterizations", []), "characterization")
    technique = slug(meta.get("technique", ""))
    technique = technique.replace("_", "-")
    try:
        replicate = int(meta.get("replicate", 0) or 0)
        version = int(meta.get("version", 0) or 0)
    except (ValueError, TypeError):
        raise UserError("Réplica y versión deben ser números enteros.")
    if not (0 <= replicate <= 999 and 0 <= version <= 999):
        raise UserError("Réplica y versión deben estar entre 0 y 999; 0 significa sin sufijo.")
    if category.startswith("raw_") and version:
        raise UserError("Un RAW no lleva versión de análisis. Usa réplica para adquisiciones distintas.")
    if category.startswith("raw_") and kind not in ("characterization", "experiment"):
        raise UserError("Los RAW se asocian a CAR; usa EXP solo para datos propios del experimento.")
    ext = extension(source) if source.is_file() else ""
    original_stem = source.name[:-len(ext)] if ext else source.name
    content = slug(meta.get("content") or original_stem)
    if not content and category != "raw_original":
        raise UserError("Escribe una descripción breve en Contenido.")
    result = {"category": category, "owner_kind": kind, "owner_code": owner, "date": day,
              "samples": sample_codes, "experiments": experiment_codes,
              "characterizations": characterization_codes, "technique": technique,
              "content": content, "replicate": replicate, "version": version,
              "independent_raw": meta.get("independent_raw") is True,
              "note": str(meta.get("note", ""))[:4000]}
    if category == "raw_original":
        result["exported_name"] = source.name
    elif source.is_dir():
        if category == "raw_copy":
            raise UserError("Para un paquete instrumental elige RAW original y conserva toda su estructura.")
        result["exported_name"] = owner + "__" + content
    else:
        if category == "raw_copy":
            if not result["independent_raw"]:
                raise UserError("Confirma que la copia RAW es un archivo independiente.")
            if source.name.lower() in {"fid", "ser", "acqus", "acqu2s", "procpar"} or source.name.lower().endswith(".wiff.scan") or (source.name.lower().endswith(".wiff") and source.with_name(source.name + ".scan").exists()):
                raise UserError("Este archivo parece parte de una adquisición. Usa RAW original y selecciona el paquete completo.")
        tokens = [day, owner]
        if len(sample_codes) == 1 and sample_codes[0] != owner:
            tokens.append(sample_codes[0])
        if technique:
            tokens.append(technique)
        tokens.append(content)
        if replicate:
            tokens.append(f"r{replicate:02d}")
        if version:
            tokens.append(f"v{version:02d}")
        result["exported_name"] = "_".join(tokens) + ext
    if len(result["exported_name"]) > 240:
        raise UserError("El nombre es demasiado largo. Acorta Contenido o Técnica.")
    return result


CSV_FIELDS = ["fecha_utc", "operacion", "estado", "nombre_original", "ruta_original", "nombre_exportado", "ruta_exportada",
              "tipo", "id_principal", "muestras", "experimentos", "caracterizaciones", "tecnica", "fecha_archivo",
              "replica", "version", "bytes", "sha256", "url_notion", "observacion", "error", "lote", "id_operacion"]


class Engine:
    def __init__(self, data_dir: Path, catalog_path=None):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.doctorado = Path('D:/Doctorado')
        self.lock = threading.RLock()
        self.plans = {}
        self.dbpath = self.data_dir / "registro.sqlite3"
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, batch TEXT, time TEXT, status TEXT, source TEXT, destination TEXT, digest TEXT, payload TEXT, error TEXT)")
            # No se reejecuta una operación incompleta a ciegas tras reiniciar.
            db.execute("UPDATE actions SET status='revisar', error='La aplicación se cerró durante la operación. Comprueba la salida antes de volver a intentarlo.' WHERE status='en_curso'")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.dbpath, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def inspect(self, paths):
        if not isinstance(paths, list) or len(paths) > 500:
            raise UserError("Añade como máximo 500 entradas por lote.")
        items = []
        for raw in dict.fromkeys(paths):
            p = absolute(raw)
            if not p.exists():
                raise UserError(f"No existe: {p}")
            if is_link(p):
                raise UserError("Selecciona el archivo original, no un enlace.")
            s = fingerprint(p)
            items.append({"key": uuid.uuid4().hex, "path": str(p.resolve()), "name": p.name,
                          "kind": "folder" if p.is_dir() else "file", "bytes": s["bytes"], "files": s["files"]})
        return items

    def list_folder(self, raw):
        p = absolute(raw)
        if not p.is_dir() or is_link(p):
            raise UserError("Elige una carpeta de entrada accesible.")
        rows = []
        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.casefold())):
            if is_link(child):
                continue
            rows.append({"path": str(child), "name": child.name, "kind": "folder" if child.is_dir() else "file",
                         "bytes": child.stat().st_size if child.is_file() else None})
            if len(rows) > 2000:
                raise UserError("Hay más de 2.000 entradas. Elige una subcarpeta o añade archivos concretos.")
        return rows

    def preview(self, request):
        with self.lock:
            mode = request.get("mode", "copy")
            if mode not in ("copy", "rename"):
                raise UserError("Elige exportar copia o renombrar en origen.")
            items = request.get("items", [])
            if not items or len(items) > 500:
                raise UserError("Selecciona entre 1 y 500 entradas.")
            out = absolute(request.get("output")) if mode == "copy" and request.get("output") else None
            if out and out.exists() and (not out.is_dir() or is_link(out)):
                raise UserError("La salida debe ser una carpeta, sin enlaces ni uniones.")
            if out:
                existing_parent = out
                while not existing_parent.exists() and existing_parent.parent != existing_parent:
                    existing_parent = existing_parent.parent
                if not existing_parent.is_dir():
                    raise UserError("No se puede acceder a la carpeta de salida.")
                if any(is_link(a) for a in [out, *out.parents] if a.exists()):
                    raise UserError("La ruta de salida atraviesa un enlace de carpeta. Elige su ubicación real.")
            batch = uuid.uuid4().hex
            rows, sources, destinations = [], set(), {}
            for item in items:
                row = {"key": item.get("key", uuid.uuid4().hex), "source": str(item.get("path", "")), "error": "", "warnings": [], "mode": mode}
                try:
                    src = absolute(item.get("path"))
                    from workflow import safe_path
                    safe_path(src)
                    if not src.exists():
                        raise UserError("El archivo ya no existe.")
                    # Nunca alterar el espejo de documentos sincronizados del proyecto.
                    if mode == "rename" and any(a.name == "sources" and (a.parent / "AGENTS.md").exists() for a in src.parents):
                        raise UserError("Los archivos sincronizados de sources son de solo lectura.")
                    source_key = os.path.normcase(str(src.resolve()))
                    if source_key in sources:
                        raise UserError("La misma entrada aparece dos veces en el lote.")
                    sources.add(source_key)
                    meta = metadata(item.get("meta", {}), src)
                    if mode == "rename" and (meta["category"].startswith("raw_") or src.is_dir()):
                        raise UserError("RAW y carpetas completas se exportan como copia; el original se conserva.")
                    row_out = absolute(item.get("output") or request.get("output")) if mode == "copy" else src.parent
                    safe_path(row_out)
                    if mode == 'copy':
                        from workflow import validate_destination
                        validate_destination(self.doctorado, row_out, meta)
                    if row_out.exists() and not row_out.is_dir():
                        raise UserError("El destino debe ser una carpeta.")
                    if mode == "copy" and any(a.name == "sources" and (a.parent / "AGENTS.md").exists() for a in [row_out, *row_out.parents]):
                        raise UserError("Los documentos sincronizados de sources son de solo lectura.")
                    dest = row_out / meta["exported_name"]
                    if src.is_dir() and under(dest, src):
                        raise UserError("La salida no puede estar dentro del paquete de entrada.")
                    if mode == "copy" and src.resolve() == dest.resolve():
                        raise UserError("Entrada y salida son la misma ruta. Elige otra carpeta para la copia.")
                    if len(str(dest)) > 245:
                        raise UserError("Ruta de salida demasiado larga para una operación fiable en Windows. Acórtala.")
                    dest_key = os.path.normcase(str(dest.resolve()))
                    row.update({"source": str(src.resolve()), "original_name": src.name, "destination": str(dest),
                                "name": meta["exported_name"], "is_directory": src.is_dir(), "meta": meta,
                                "snapshot": fingerprint(src), "notion_url": ""})
                    if len(meta["samples"]) > 1:
                        row["warnings"].append("Varias muestras: se registran todas, sin alargar el nombre con sus IDs.")
                    if src.is_dir():
                        row["warnings"].append("Se copia el paquete completo; sus nombres internos se conservan.")
                    if meta["category"] == "raw_original":
                        row["warnings"].append("RAW original: conserva el nombre generado por el instrumento.")
                    row["warnings"].append("Copia local: comprueba en Drive cuándo termina la sincronización; no se confirma desde esta app.")
                    if mode == "copy" and not row_out.exists():
                        row["warnings"].append("Se creará la carpeta de salida indicada.")
                    if dest_key in destinations:
                        row["error"] = "Dos entradas producirían la misma ruta. Cambia Contenido, réplica o versión."
                        destinations[dest_key]["error"] = row["error"]
                    destinations[dest_key] = row
                    if dest.exists() and src.resolve() != dest.resolve():
                        raise UserError("La salida ya existe. No se sobrescribe ni se presume que sea idéntica: cambia descripción, réplica, versión o carpeta.")
                except (OSError, UserError) as exc:
                    row["error"] = str(exc)
                rows.append(row)
            # No admitir fuentes anidadas o destinos que pisen otra entrada del lote.
            for a in rows:
                if "destination" not in a:
                    continue
                for b in rows:
                    if a is b:
                        continue
                    if "source" in b and (os.path.normcase(a["destination"]) == os.path.normcase(b["source"]) or (b.get("is_directory") and under(Path(a["destination"]), Path(b["source"])))):
                        a["error"] = "La salida coincide con otra entrada del lote o está dentro de ella."
                    if a.get("is_directory") and "source" in b and under(Path(b["source"]), Path(a["source"])):
                        a["error"] = b["error"] = "No selecciones a la vez un paquete y los archivos que contiene."
            plan = {"id": batch, "created": now(), "mode": mode, "output": str(out) if out else "", "items": rows,
                    "valid": all(not row["error"] for row in rows), "used": False}
            self.plans[batch] = plan
            # Los planes son efímeros; el historial no.
            if len(self.plans) > 100:
                self.plans.pop(next(iter(self.plans)))
            return plan

    def _record(self, action_id, batch, row, status, digest="", error=""):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO actions VALUES (?,?,?,?,?,?,?,?,?)", (action_id, batch, now(), status, row["source"], row.get("destination", ""), digest, json.dumps(row, ensure_ascii=False), error))

    @staticmethod
    def publish(stage: Path, dest: Path):
        if dest.exists():
            raise UserError("La salida apareció durante la operación. No se ha sobrescrito.")
        if os.name == "nt":
            # En Windows rename falla si el destino ya existe.
            os.rename(stage, dest)
        elif stage.is_file():
            os.link(stage, dest)
            stage.unlink()
        else:
            # La aplicación se distribuye para Windows. En otros sistemas no se
            # publica una carpeta con una primitiva que pueda reemplazar otra.
            raise UserError("La exportación de carpetas está disponible en Windows.")

    def _copy(self, src, dest, expected):
        from workflow import safe_path
        safe_path(src)
        safe_path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        stage = dest.parent / (".doctorado-" + uuid.uuid4().hex + ".part")
        try:
            if src.is_dir():
                stage.mkdir()
                for root, dirs, _ in os.walk(src, followlinks=False):
                    for name in dirs:
                        p = Path(root) / name
                        if is_link(p):
                            raise UserError("El paquete cambió e incluye un enlace.")
                        (stage / p.relative_to(src)).mkdir(parents=True, exist_ok=True)
                for p, rel in tree_files(src):
                    target = stage / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with p.open("rb") as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
                        output.flush()
                        os.fsync(output.fileno())
                    shutil.copystat(p, target)
            else:
                with src.open("rb") as source, stage.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                shutil.copystat(src, stage)
            if fingerprint(src) != expected:
                raise UserError("La entrada cambió mientras se copiaba. Espera a que termine de guardarse y revisa otra vez.")
            if fingerprint(stage)["bytes"] != expected["bytes"]:
                raise UserError("El tamaño de la copia no coincide. No se ha publicado.")
            safe_path(dest)
            self.publish(stage, dest)
            return ""
        finally:
            # Solo se elimina el temporal creado por esta operación.
            if stage.exists():
                if stage.is_dir():
                    shutil.rmtree(stage)
                else:
                    stage.unlink()

    def execute(self, plan_id):
        with self.lock:
            plan = self.plans.get(plan_id)
            if not plan or not plan["valid"]:
                raise UserError("Revisa el lote antes de ejecutarlo.")
            if plan["used"]:
                raise UserError("Este lote ya se ejecutó. Consulta el historial o prepara una nueva revisión.")
            plan["used"] = True
            results = []
            for row in plan["items"]:
                action_id = uuid.uuid4().hex
                status, digest, error = "error", "", ""
                try:
                    self._record(action_id, plan_id, row, "en_curso")
                    src, dest = Path(row["source"]), Path(row["destination"])
                    from workflow import safe_path
                    safe_path(src)
                    safe_path(dest)
                    if plan['mode'] == 'copy':
                        from workflow import validate_destination
                        validate_destination(self.doctorado, dest.parent, row['meta'])
                    if fingerprint(src) != row["snapshot"]:
                        raise UserError("La entrada cambió desde la vista previa. Vuelve a revisarla.")
                    if plan["mode"] == "rename":
                        if src == dest:
                            status = "sin_cambio"
                        else:
                            self.publish(src, dest)
                            status = "completado"
                    else:
                        digest = self._copy(src, dest, row["snapshot"])
                        status = "completado"
                except (OSError, UserError) as exc:
                    error = str(exc)
                self._record(action_id, plan_id, row, status, digest, error)
                results.append({"id": action_id, "source": row["source"], "destination": row["destination"], "name": row["name"], "status": status, "error": error, "sha256": digest})
            return {"batch": plan_id, "results": results, "manifest": "", "manifest_error": ""}

    def delete_history(self, ids, confirmed=False):
        if confirmed is not True:
            raise UserError('Confirma el borrado de las entradas del historial.')
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 5000
                or any(not isinstance(v, str) or not re.fullmatch(r'[a-f0-9]{32}', v) for v in ids)):
            raise UserError('Selecciona entre 1 y 5.000 entradas válidas.')
        selected = set(ids)
        with self.lock, self.db() as db:
            # Transaction covers validation and deletion; no filesystem operations.
            db.execute('BEGIN IMMEDIATE')
            existing = {r['id']: r['status'] for r in db.execute('SELECT id,status FROM actions')}
            if not selected.issubset(existing):
                raise UserError('El historial ha cambiado. Actualiza la lista y vuelve a seleccionar.')
            if any(existing[i] == 'en_curso' for i in selected):
                raise UserError('No se pueden borrar operaciones en curso.')
            db.executemany('DELETE FROM actions WHERE id=?', [(i,) for i in selected])
        return {'deleted': len(selected)}

    def history(self, batch=None, limit=5000):
        with self.db() as db:
            if batch:
                rows = db.execute("SELECT * FROM actions WHERE batch=? ORDER BY rowid", (batch,)).fetchall()
            elif limit:
                rows = db.execute("SELECT * FROM actions ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM actions ORDER BY rowid DESC").fetchall()
        result = []
        for r in rows:
            data = dict(r)
            payload = json.loads(data.pop("payload"))
            data.update({"meta": payload.get("meta", {}), "original_name": payload.get("original_name", ""),
                         "name": payload.get("name", ""), "mode": payload.get("mode", ""),
                         "bytes": payload.get("snapshot", {}).get("bytes", 0), "notion_url": payload.get("notion_url", "")})
            result.append(data)
        return result

    @staticmethod
    def write_csv(handle, rows):
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, delimiter=";")
        writer.writeheader()
        def cell(value):
            value = "" if value is None else str(value)
            return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
        for r in rows:
            m = r["meta"]
            values = [r["time"], r["mode"], r["status"], r["original_name"], r["source"], r["name"], r["destination"],
                      m.get("category"), m.get("owner_code"), ",".join(m.get("samples", [])), ",".join(m.get("experiments", [])),
                      ",".join(m.get("characterizations", [])), m.get("technique"), m.get("date"), m.get("replicate"), m.get("version"),
                      r["bytes"], r["digest"], r.get("notion_url"), m.get("note"), r["error"], r["batch"], r["id"]]
            writer.writerow(dict(zip(CSV_FIELDS, map(cell, values))))

    def csv_text(self):
        out = io.StringIO(newline="")
        self.write_csv(out, self.history(limit=None))
        return "\ufeff" + out.getvalue()

