"""Persistent user data in Windows Documents, independent of EXE placement."""
import os
from pathlib import Path
import shutil
import sqlite3
import uuid
from contextlib import closing

FILES=('registro.sqlite3','preferencias.json','plantillas_favoritos.json','entrada_reglas.json','actualizador.json')


def documents_dir():
    if os.name=='nt':
        # Honor the user's redirected Documents folder, including OneDrive.
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                value=winreg.QueryValueEx(key,'Personal')[0]
            folder=Path(os.path.expandvars(value))
            if folder.is_absolute():return folder
        except OSError:
            pass
    return Path.home()/'Documents'


def default_data_dir():
    return documents_dir()/'PhDex'/'datos_app'


def migrate_legacy_data(destination,legacy):
    """Copy a previous installation once, without merging or deleting its files."""
    destination,legacy=Path(destination),Path(legacy)
    if destination.exists() or not legacy.is_dir() or destination.resolve()==legacy.resolve():
        return False
    present=[name for name in FILES if (legacy/name).is_file()]
    if not present:return False
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=destination.parent/('.migracion-'+uuid.uuid4().hex)
    stage.mkdir()
    try:
        for name in present:
            source=legacy/name
            if source.is_symlink():raise ValueError('No se migran enlaces de datos personales.')
            if name.endswith('.sqlite3'):
                with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                    with closing(sqlite3.connect(stage/name)) as target:db.backup(target)
            else:
                shutil.copy2(source,stage/name)
        if destination.exists():return False
        # Windows refuses to replace an existing directory. Only publish a new one.
        stage.rename(destination)
        return True
    finally:
        # The staging folder contains only copies made by this function.
        if stage.exists():
            for name in FILES:
                copied=stage/name
                if copied.is_file():copied.unlink()
            stage.rmdir()
