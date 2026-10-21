"""Descubrimiento de destinos y auditoría de solo lectura de Doctorado."""
from pathlib import Path
from datetime import date
import os
import re

from core import UserError, absolute, code, extension, is_link, slug, under

ROOTS = {
    'PRY': '01_Proyectos', 'EXP': '02_Experimentos', 'MUE': '03_Muestras',
    'CAR': '04_Caracterizaciones', 'RES': '05_Resultados', 'HIP': '06_Ideas_Hipotesis',
    'ART': '07_Literatura', 'TAR': '08_Tareas', 'REU': '09_Reuniones',
    'PRO': '10_Protocolos', 'PUB': '11_Publicaciones', 'TEC': '12_Tecnicas',
    'LIMS': '13_Solicitudes_LIMS',
}
TEMPLATES = dict(zip(ROOTS, ['Proyecto', 'Experimento', 'Muestra', 'Caracterizacion',
    'Resultado', 'Idea', 'Articulo', 'Tarea', 'Reunion', 'Protocolo', 'Publicacion', 'Tecnica', 'LIMS']))
EXPECTED = list(ROOTS.values()) + ['14_Tesis', '90_Plantillas', '99_Gestion']
RECORD = re.compile(r'([A-Z][A-Z0-9]{1,11}-[1-9][0-9]*|LIMS-[0-9]{4}-[0-9]+)__([A-Za-z0-9][A-Za-z0-9_-]*)')
FILE = re.compile(r'(\d{4}-\d{2}-\d{2})_([A-Z][A-Z0-9]{1,11}-[1-9][0-9]*|LIMS-[0-9]{4}-[0-9]+)_([A-Za-z0-9][A-Za-z0-9_-]*)')


def safe_path(path):
    path = absolute(path)
    for ancestor in [path, *path.parents]:
        if is_link(ancestor):
            raise UserError('La ruta atraviesa un enlace o unión. Elige la ubicación real.')
    return path


def structure(root):
    root = safe_path(root)
    if not root.is_dir():
        raise UserError('No se puede acceder a la carpeta Doctorado.')
    entries = [str(root / n) for n in ('Entrada', '00_Entrada') if (root / n).is_dir() and not is_link(root / n)]
    return {'root': str(root), 'inboxes': entries, 'records': records(root),
            'sync': 'La copia local no confirma la subida a Drive. Revisa el estado del cliente de Drive; descarga antes los archivos disponibles solo en la nube. Los RAW también consumen cuota si se sincronizan.'}


def records(root):
    result = []
    for prefix, name in ROOTS.items():
        parent = safe_path(root / name)
        if not parent.is_dir():
            continue
        for p in sorted(parent.iterdir(), key=lambda p: p.name.casefold()):
            match = RECORD.fullmatch(p.name)
            if p.is_dir() and not is_link(p) and match:
                result.append({'code': match[1], 'path': str(p), 'name': p.name, 'parent': name})
    return result


def folder_name(value):
    raw = str(value or '').strip()
    if re.search(r'[\\/:*?"<>|]', raw):
        raise UserError('Escribe solo el nombre de la carpeta, por ejemplo DRX.')
    name = slug(raw)
    if not name or len(name) > 150 or re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]', name, re.I):
        raise UserError('Escribe un nombre de carpeta válido, por ejemplo DRX.')
    return name


def recommend(root, meta, source, description=''):
    root = safe_path(root)
    owner = code(meta.get('owner_code'), meta.get('owner_kind', 'other'))
    prefix = owner.split('-')[0]
    if prefix not in ROOTS:
        raise UserError('Este prefijo no tiene un destino definido en la guía local. Elige la carpeta manualmente.')
    parent = safe_path(root / ROOTS[prefix])
    if not parent.is_dir():
        raise UserError('Falta la carpeta principal; revisa la auditoría antes de continuar.')
    if str(description).strip():
        name = folder_name(description)
        # Reutilizar la carpeta real, incluso si se escribió con otra combinación
        # de mayúsculas. No añadir IDs ni subcarpetas de plantilla.
        matches = [p for p in parent.iterdir() if p.name.casefold() == name.casefold()]
        target = matches[0] if matches else parent / name
        safe_path(target)
        if target.exists() and not target.is_dir():
            raise UserError('Ya existe un archivo con ese nombre. Elige otro nombre de carpeta.')
        validate_destination(root, target, {'owner_code':owner})
        return {'output': str(target), 'new_folder': not target.exists(),
                'new_record': False, 'record': str(target)}
    matches = [r for r in records(root) if r['code'] == owner]
    if len(matches) > 1:
        raise UserError('Hay varias carpetas con este ID. Resuelve la duplicidad o elige explícitamente el destino.')
    if matches:
        record = Path(matches[0]['path'])
        if not under(record, parent):
            raise UserError('El ID está en una carpeta principal incorrecta. Revisa la auditoría.')
    else:
        raise UserError('Escribe el nombre de la carpeta, por ejemplo DRX. Se reutilizará si existe y se creará al exportar si falta.')
    category = meta.get('category')
    mapping = {
        'CAR': {'raw_original': '01_RAW', 'raw_copy': '02_Exportaciones', 'export': '02_Exportaciones', 'processed': '03_Procesamiento', 'report': '04_Informe_equipo'},
        'RES': {'processed': '01_Analisis', 'origin': '02_Origin', 'table': '05_Tablas', 'report': '06_Interpretacion'},
        'EXP': {'record': '02_Registro', 'raw_original': '03_Datos_propios', 'raw_copy': '03_Datos_propios', 'export': '03_Datos_propios', 'processed': '03_Datos_propios'},
        'MUE': {'photo': '01_Fotos'}, 'LIMS': {'report': '01_Justificante'},
    }
    sub = mapping.get(prefix, {}).get(category, '')
    if prefix == 'RES' and category == 'figure':
        sub = '04_Figuras_exportadas' if extension(Path(source)).lower() in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.pdf') else '03_Figuras_editables'
    if not sub:
        raise UserError('Este tipo de archivo necesita un destino elegido manualmente dentro del registro.')
    template = root / '90_Plantillas' / TEMPLATES[prefix] / sub
    if not template.is_dir() and not (record / sub).is_dir():
        raise UserError('La subcarpeta no aparece en la plantilla local. Elige su destino manualmente.')
    return {'output': str(safe_path(record / sub)), 'new_record': not record.exists(), 'record': str(record)}


def validate_destination(root, output, meta):
    """Admitir agrupaciones como CAR/DRX conservando la categoría principal."""
    root, output = safe_path(root), safe_path(output)
    if not under(output, root):
        return  # Se permite almacenamiento institucional externo elegido expresamente.
    relative = output.relative_to(root)
    if len(relative.parts) < 2:
        raise UserError('Indica una subcarpeta, por ejemplo DRX dentro de 04_Caracterizaciones. Puedes escribir su nombre para preparar el destino.')
    owner = meta['owner_code']
    expected = ROOTS.get(owner.split('-')[0])
    if relative.parts[0] == '14_Tesis':
        return  # La guía define capítulos/compilación, sin carpeta de registro obligatoria.
    match = RECORD.fullmatch(relative.parts[1])
    if not expected or relative.parts[0] != expected:
        raise UserError('El destino debe corresponder al tipo de registro: CAR en 04_Caracterizaciones, EXP en 02_Experimentos, MUE en 03_Muestras, etc.')
    if not match:
        return  # Nombre descriptivo, por ejemplo DRX, compartido por varios IDs.
    if match[1] != owner:
        raise UserError('Esta carpeta lleva el ID de otro registro. Elige una carpeta descriptiva como DRX o la del ID correcto.')
    record = root / relative.parts[0] / relative.parts[1]
    matches = [Path(r['path']) for r in records(root) if r['code'] == owner]
    if any(p != record for p in matches):
        raise UserError('Ya existe otra carpeta para este ID. Reutilízala y evita duplicar el registro.')


def audit(root, limit=20000):
    root = safe_path(root)
    if not root.is_dir():
        raise UserError('No se puede acceder a Doctorado.')
    findings, count, truncated = [], 0, False
    def add(kind, path, message):
        findings.append({'kind': kind, 'path': str(path), 'message': message})
    for name in EXPECTED:
        if not (root / name).is_dir():
            add('estructura', root / name, 'Falta la carpeta principal; no se ha creado.')
    if not any((root / n).is_dir() for n in ('Entrada', '00_Entrada')):
        add('estructura', root, 'No existe Entrada ni 00_Entrada.')
    if all((root / n).is_dir() for n in ('Entrada', '00_Entrada')):
        add('entrada', root, 'Existen dos bandejas. El selector permite revisar ambas sin fusionarlas.')
    seen = {}
    def onerror(error):
        add('acceso', error.filename or root, str(error))
    for current, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        path = Path(current)
        rel = path.relative_to(root)
        for d in list(dirs):
            if is_link(path / d):
                dirs.remove(d)
                add('acceso', path / d, 'Enlace o unión omitido.')
        if path == root:
            dirs[:] = [d for d in dirs if d not in ('90_Plantillas', '99_Gestion', 'Entrada', '00_Entrada')]
        # Los nombres internos de paquetes RAW se conservan por la excepción de la guía.
        if path.name == '01_RAW':
            dirs[:] = []
            continue
        if len(rel.parts) == 1 and path.name in ROOTS.values():
            for d in dirs:
                p = path / d
                m = RECORD.fullmatch(d)
                if not m:
                    if not slug(d) or slug(d) != d:
                        add('carpeta', p, 'Usa un nombre breve sin tildes ni caracteres especiales, por ejemplo DRX.')
                    continue
                owner = m[1]
                if owner in seen:
                    add('duplicado', p, 'ID repetido: ' + str(seen[owner]))
                seen[owner] = p
                expected = ROOTS.get(owner.split('-')[0])
                if expected != path.name:
                    add('estructura', p, 'El prefijo del ID no corresponde a esta carpeta principal.')
                template = root / '90_Plantillas' / TEMPLATES.get(owner.split('-')[0], '')
                if template.is_dir() and template != root / '90_Plantillas':
                    for child in template.iterdir():
                        if child.is_dir() and not (p / child.name).is_dir():
                            add('estructura', p / child.name, 'Falta una subcarpeta de la plantilla; créala solo si la necesitas.')
        for f in files:
            count += 1
            if count > limit:
                truncated = True
                break
            p = path / f
            if f in ('REFERENCIAS.txt', 'LEEME_Doctorado.txt'):
                continue
            if is_link(p):
                add('acceso', p, 'Archivo enlazado omitido.')
                continue
            ext = extension(p)
            stem = f[:-len(ext)] if ext else f
            m = FILE.fullmatch(stem)
            valid = bool(m)
            if valid:
                try:
                    date.fromisoformat(m[1])
                except ValueError:
                    valid = False
            if not valid or re.search(r'(?:^|_)(?:r|v)(?:0|0{2,}|[1-9])(?:_|$)', stem) or re.search(r'final_final|copia_nueva', stem, re.I):
                add('nombre', p, 'Revisar fecha, ID y contenido: AAAA-MM-DD_ID_Contenido[_rNN][_vNN].ext.')
            elif len(rel.parts) == 1 and path.name in ROOTS.values():
                add('ubicacion', p, 'Archivo suelto en carpeta principal; elige una subcarpeta descriptiva, por ejemplo DRX.')
            elif len(rel.parts) >= 2:
                record = RECORD.fullmatch(rel.parts[1])
                if record and record[1] != m[2]:
                    add('ubicacion', p, 'El ID del archivo no coincide con el registro de la carpeta.')
        if truncated:
            break
    return {'root': str(root), 'findings': findings, 'scanned': min(count, limit), 'truncated': truncated,
            'note': 'Solo lectura. Excluye Entrada, plantillas, gestión y nombres internos de RAW; no verifica contenido ni sincronización.'}
