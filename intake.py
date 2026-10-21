"""Explicit filename suggestions, user rules and safe inbox imports. No content hashes."""
from datetime import date
import json
import os
from pathlib import Path
import re
import threading
import uuid
from core import UserError, extension, KINDS, fingerprint, Engine
from workflow import safe_path, FILE


MATCHES=('contains','not_contains','extension','starts_with','ends_with')


def rule_conditions(rule):
    return rule.get('conditions',[{'match':rule.get('match'),'pattern':rule.get('pattern','')}])


def rule_matches(rule,name):
    name=name.casefold()
    results=[]
    for condition in rule_conditions(rule):
        pattern=condition['pattern'].casefold()
        kind=condition['match']
        results.append({'contains':lambda:pattern in name,'not_contains':lambda:pattern not in name,
                        'extension':lambda:name.endswith('.'+pattern.lstrip('.')),
                        'starts_with':lambda:name.startswith(pattern),'ends_with':lambda:name.endswith(pattern)}[kind]())
    return bool(results) and (any(results) if rule.get('combine','all')=='any' else all(results))


def recognize(name):
    stem = name[:-len(extension(Path(name)))] if extension(Path(name)) else name
    result, notes = {}, []
    ids = set(re.findall(r'(?<![A-Z0-9-])(?:LIMS-\d{4}-\d+|[A-Z]{2,12}-[1-9]\d*)(?![A-Z0-9-])', stem.upper()))
    # A canonical name has an explicit principal ID; MUE tokens may be relations.
    canonical = FILE.fullmatch(stem)
    principal = canonical[2] if canonical else next(iter(ids)) if len(ids) == 1 else None
    if principal:
        result.update(owner_code=principal, owner_kind=next((k for k, v in KINDS.items() if v and principal.startswith(v+'-')), 'other'))
    elif ids:
        notes.append('Varios IDs: elige el registro principal.')
    days = set(re.findall(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', stem))
    if len(days) == 1:
        try:
            result['date'] = date.fromisoformat(next(iter(days))).isoformat()
        except ValueError:
            notes.append('La fecha del nombre no es válida.')
    elif days:
        notes.append('Varias fechas: elige la correcta.')
    techniques = set(re.findall(r'(?<![A-Z0-9])(?:DRX|XRD|FTIR(?:-ATR)?|RAMAN|SEM|TEM|DSC|TGA|UV-VIS|RMN)(?![A-Z0-9])', stem.upper()))
    if len(techniques) == 1:
        result['technique'] = next(iter(techniques))
    # Preserve complete valid names as-is instead of guessing how their description splits.
    if canonical and result.get('date'):
        try:
            from core import metadata
            metadata({'category':'export', 'quick_name':stem}, Path(name))
            result['quick_name'] = stem
            notes.append('Nombre completo reconocido; se conservará al aceptar. Vacía el nombre manual si quieres reconstruirlo con los campos.')
        except UserError:
            pass
    return {'meta':result, 'notes':notes}


class Intake:
    def __init__(self, data_dir, doctorado, library, engine):
        self.path = Path(data_dir)/'entrada_reglas.json'
        self.root, self.library, self.engine = Path(doctorado), library, engine
        self.lock = threading.RLock()

    def read(self):
        with self.lock:
            if self.path.exists():
                try:
                    data = json.loads(self.path.read_text(encoding='utf-8'))
                    if not isinstance(data, dict) or not isinstance(data.get('rules'), list) or not isinstance(data.get('revision'), int):
                        raise ValueError()
                    return data
                except (ValueError, OSError):
                    raise UserError('No se puede leer la configuración de entrada y reglas. Se conserva el archivo.')
            inbox = next((self.root/n for n in ('Entrada','00_Entrada') if (self.root/n).is_dir()), self.root/'Entrada')
            return {'revision':0, 'inbox':str(inbox), 'rules':[]}

    def change(self, request):
        with self.lock:
            data = self.read()
            if request.get('revision') != data['revision']:
                raise UserError('La configuración cambió en otra pestaña. Actualiza antes de guardar.')
            if 'inbox' in request:
                folder = safe_path(request['inbox']).resolve()
                if not folder.is_dir():
                    raise UserError('Selecciona una carpeta de entrada existente.')
                if any(p.name == 'sources' and (p.parent/'AGENTS.md').exists() for p in (folder,*folder.parents)):
                    raise UserError('Los documentos sincronizados de sources son de solo lectura.')
                data['inbox'] = str(folder)
            else:
                record_id = request.get('id')
                old = next((r for r in data['rules'] if r['id'] == record_id), None)
                if record_id and not old:
                    raise UserError('La regla ya no existe.')
                if request.get('delete'):
                    if not old: raise UserError('Elige una regla.')
                    data['rules'].remove(old)
                else:
                    value = request.get('value', {})
                    label = str(value.get('label','')).strip()
                    conditions=rule_conditions(value)
                    combine=value.get('combine','all')
                    if not label or len(label)>80 or combine not in ('all','any') or not isinstance(conditions,list) or not 1<=len(conditions)<=20:
                        raise UserError('Completa el nombre y añade entre 1 y 20 condiciones. Elige Todas o Cualquiera.')
                    cleaned=[]
                    for condition in conditions:
                        if not isinstance(condition,dict):raise UserError('Condición no válida.')
                        pattern=str(condition.get('pattern','')).strip()
                        kind=condition.get('match')
                        if not pattern or len(pattern)>120 or kind not in MATCHES:
                            raise UserError('Completa el tipo y el texto de cada condición (hasta 120 caracteres).')
                        if kind=='extension' and not re.fullmatch(r'\.?[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*',pattern):
                            raise UserError('Extensión no válida. Ejemplo: csv o csv.gz.')
                        cleaned.append({'match':kind,'pattern':pattern})
                    if not any(t['id']==value.get('template') for t in self.library.read()['templates']):
                        raise UserError('Elige una plantilla existente.')
                    row = {'id':record_id or uuid.uuid4().hex,'label':label,'conditions':cleaned,'combine':combine,'template':value['template']}
                    if old: data['rules'][data['rules'].index(old)] = row
                    else:
                        if len(data['rules'])>=100: raise UserError('Límite de 100 reglas.')
                        data['rules'].append(row)
            data['revision'] += 1
            temp = self.path.with_name('.entrada-'+uuid.uuid4().hex+'.tmp')
            try:
                with temp.open('x', encoding='utf-8') as stream:
                    json.dump(data,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
                os.replace(temp,self.path)
            finally:
                temp.unlink(missing_ok=True)
            return data

    def suggestions(self, name):
        result = recognize(name)
        templates = {t['id']:t for t in self.library.read()['templates']}
        matches = []
        for rule in self.read()['rules']:
            if rule_matches(rule,name) and rule['template'] in templates:
                matches.append({'rule':rule['label'], 'template':templates[rule['template']]})
        result['matches'] = matches
        return result

    def listing(self):
        folder = safe_path(self.read()['inbox']).resolve()
        rows = self.engine.list_folder(folder)
        with self.engine.db() as db:
            records = db.execute("SELECT source,destination,payload FROM actions WHERE status IN ('completado','ya_exportado') AND json_extract(payload,'$.mode')='copy' ORDER BY rowid DESC").fetchall()
        by_source = {}
        for record in records:
            by_source.setdefault(os.path.normcase(record['source']), []).append(record)
        for row in rows:
            previous = by_source.get(os.path.normcase(str(Path(row['path']).resolve())), [])
            row['exported'] = False
            if previous:
                snapshot = fingerprint(Path(row['path']))
                for record in previous:
                    stored = json.loads(record['payload']).get('snapshot',{})
                    try:
                        destination_exists = safe_path(record['destination']).exists()
                    except (UserError,OSError):
                        destination_exists = False
                    if json.dumps(snapshot,sort_keys=True)==json.dumps(stored,sort_keys=True) and destination_exists:
                        row['exported'] = True;break
            row['pending_note'] = 'Exportado según historial, tamaño y fechas' if row['exported'] else 'Pendiente'
        return {'path':str(folder),'items':rows,'note':'El estado usa historial, tamaño y fechas; no compara el contenido. Si borras el historial, vuelve a figurar pendiente.'}

    def import_file(self, name, stream, length):
        if (not isinstance(name,str) or not name or name in ('.','..') or len(name)>240
                or re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or name.endswith(('.',' '))
                or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',name,re.I)):
            raise UserError('El archivo tiene un nombre no válido en Windows.')
        if not 0 <= length <= 2*1024**3:
            raise UserError('Arrastra archivos de hasta 2 GB; para mayores usa Seleccionar archivos.')
        with self.lock:
            folder = safe_path(self.read()['inbox']).resolve()
            if not folder.is_dir(): raise UserError('Configura una carpeta de entrada accesible antes de arrastrar.')
            if any(p.name=='sources' and (p.parent/'AGENTS.md').exists() for p in (folder,*folder.parents)):
                raise UserError('La carpeta de entrada es de solo lectura.')
            destination = folder/name
            if destination.exists():
                raise UserError('Ya existe '+name+' en Entrada. Añádelo desde Revisar entrada o cambia su nombre; no se ha sobrescrito.')
            stage = folder/('.phdex-import-'+uuid.uuid4().hex+'.tmp')
            try:
                with stage.open('xb') as output:
                    remaining = length
                    while remaining:
                        chunk = stream.read(min(1024*1024,remaining))
                        if not chunk: raise UserError('La importación se interrumpió. Vuelve a arrastrar el archivo.')
                        output.write(chunk);remaining-=len(chunk)
                    output.flush();os.fsync(output.fileno())
                safe_path(folder)
                Engine.publish(stage,destination)
            finally:
                stage.unlink(missing_ok=True)
            return str(destination)
