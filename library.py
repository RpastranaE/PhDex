"""Biblioteca local de favoritos y plantillas; independiente de los lotes."""
import json
import os
from pathlib import Path
import threading
import uuid
from core import CATEGORIES, KINDS, UserError
from workflow import safe_path


class Library:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'plantillas_favoritos.json'
        self.lock = threading.RLock()

    def read(self):
        with self.lock:
            if not self.path.exists():
                return {'revision': 0, 'favorites': [], 'templates': []}
            try:
                value = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(value, dict) or not all(k in value for k in ('revision', 'favorites', 'templates')):
                    raise ValueError()
                return value
            except (ValueError, OSError):
                raise UserError('No se puede leer la biblioteca. Se conserva el archivo; no se reemplazará.')

    def change(self, request):
        with self.lock:
            data = self.read()
            if request.get('revision') != data['revision']:
                raise UserError('La biblioteca cambió en otra pestaña. Vuelve a abrir Plantillas y favoritos.')
            group = request.get('group')
            if group not in ('favorites', 'templates'):
                raise UserError('Elige favorito o plantilla.')
            record_id = request.get('id')
            old = next((r for r in data[group] if r['id'] == record_id), None)
            if record_id and not old:
                raise UserError('Este elemento ya no existe. Actualiza la biblioteca.')
            if request.get('delete'):
                if not old:
                    raise UserError('Elige un elemento para eliminar.')
                data[group].remove(old)
            else:
                value = request.get('value', {})
                label = str(value.get('label', '')).strip()
                if not label or len(label) > 80:
                    raise UserError('Escribe un nombre de entre 1 y 80 caracteres.')
                if any(r['label'].casefold() == label.casefold() and r is not old for r in data[group]):
                    raise UserError('Ya existe un elemento con ese nombre.')
                folder = safe_path(value.get('output'))
                if not folder.is_dir():
                    raise UserError('Elige una carpeta existente. Guardar no crea carpetas.')
                row = {'id': record_id or uuid.uuid4().hex, 'label': label, 'output': str(folder)}
                if group == 'templates':
                    meta = value.get('meta', {})
                    category, kind = meta.get('category'), meta.get('owner_kind')
                    if category not in CATEGORIES or kind not in KINDS:
                        raise UserError('Elige tipo de archivo y registro para la plantilla.')
                    row['meta'] = {'category': category, 'owner_kind': kind}
                    for field in ('technique', 'content'):
                        row['meta'][field] = str(meta.get(field, ''))[:150]
                    for field in ('replicate', 'version'):
                        val = int(meta.get(field, 0) or 0)
                        if not 0 <= val <= 999 or (field == 'version' and category.startswith('raw_') and val):
                            raise UserError('Réplica y versión: 0 a 999. RAW no admite versión.')
                        row['meta'][field] = val
                if old:
                    data[group][data[group].index(old)] = row
                else:
                    if len(data[group]) >= 100:
                        raise UserError('Límite de 100 elementos por sección.')
                    data[group].append(row)
            data['revision'] += 1
            temp = self.path.with_suffix('.tmp')
            with temp.open('w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
            return data
