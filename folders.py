"""Carpetas elegibles y creación explícita con borrado vacío limitado a la sesión."""
from pathlib import Path
import threading
import uuid

from core import UserError, code, under
from workflow import ROOTS, safe_path, folder_name


def identity(path):
    info = path.stat()
    return (info.st_dev, info.st_ino, getattr(info, 'st_birthtime_ns', info.st_ctime_ns))


class SessionFolders:
    def __init__(self, root):
        self.root = Path(root)
        self.created = {}
        self.lock = threading.RLock()

    def parent(self, meta, selected=None):
        owner = code(meta.get('owner_code'), meta.get('owner_kind', 'other'))
        name = ROOTS.get(owner.split('-')[0])
        if not name:
            raise UserError('Este registro necesita una ruta de salida elegida manualmente.')
        category = safe_path(self.root / name)
        target = safe_path(selected) if selected else category
        if not under(target, category):
            raise UserError('Elige una carpeta base dentro de ' + str(category))
        if not target.is_dir():
            raise UserError('La carpeta base no existe o no está disponible.')
        return target

    def _owned(self, path):
        for token, entry in self.created.items():
            if (entry['path'] == path and entry['identity'] == identity(path)
                    and entry['parent_identity'] == identity(path.parent)):
                return token
        return None

    def list(self, meta, parent=None):
        with self.lock:
            base = self.parent(meta, parent)
            rows = []
            for child in sorted(base.iterdir(), key=lambda p:p.name.casefold()):
                try:
                    safe_path(child)
                    if not child.is_dir():
                        continue
                    token = self._owned(child)
                    empty = next(child.iterdir(), None) is None
                    rows.append({'name': child.name, 'path':str(child), 'token':token,
                                 'created_in_session':bool(token), 'can_delete':bool(token and empty)})
                except (OSError, UserError):
                    continue
            return {'parent':str(base), 'folders':rows}

    def create(self, meta, name, parent=None):
        with self.lock:
            base = self.parent(meta, parent)
            normalized = folder_name(name)
            matches = [p for p in base.iterdir() if p.name.casefold() == normalized.casefold()]
            target = safe_path(matches[0] if matches else base / normalized)
            created = False
            try:
                target.mkdir()  # Exclusivo: nunca atribuirse una carpeta previa.
                created = True
                token = uuid.uuid4().hex
                self.created[token] = {'path':target, 'identity':identity(target),
                                       'parent_identity':identity(base)}
            except FileExistsError:
                safe_path(target)
                if not target.is_dir():
                    raise UserError('Ya hay un archivo con ese nombre; elige otro nombre de carpeta.')
            return {'created':created, 'name':target.name, 'path':str(target), **self.list(meta, base)}

    def delete(self, token):
        with self.lock:
            entry = self.created.get(str(token))
            if not entry:
                raise UserError('Solo se pueden eliminar carpetas creadas desde esta sesión de la app.')
            target = safe_path(entry['path'])
            if not target.is_dir() or self._owned(target) != token:
                raise UserError('La carpeta cambió desde su creación. No se ha eliminado.')
            if next(target.iterdir(), None) is not None:
                raise UserError('La carpeta contiene archivos o subcarpetas. No se elimina.')
            target.rmdir()  # Sin recursión: Windows también rechaza carpetas no vacías.
            del self.created[token]
            return {'deleted':str(target)}
