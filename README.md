# PhDex

Gestor de archivos de investigación para Windows. Permite seleccionar un lote de archivos, asignar plantillas o destinos favoritos, revisar sus nombres y exportar copias. Incluye auditoría de estructura y nombres e historial con borrado confirmado.

## Descargar y abrir

1. Abre **Releases** en este repositorio privado y descarga **PhDex.exe** de la última versión (o el ZIP portátil).
2. Guarda el ejecutable en una carpeta propia y haz doble clic. Lleva Python y los recursos incluidos: no necesitas instalar Python ni ejecutar un CMD.
3. La interfaz se abre en el navegador. Al cerrar la última pestaña, PhDex termina cuando acaba cualquier copia pendiente.

La carpeta de trabajo predeterminada es `D:\Doctorado`. Para otra ubicación: `PhDex.exe --doctorado "C:\Mi carpeta"`.

El historial, plantillas, favoritos y preferencias se guardan en **Documentos\PhDex\datos_app**, en el perfil de Windows donde se ejecuta. Se respeta la ubicación de Documentos configurada en Windows, incluso si está redirigida a OneDrive. Puedes mover o actualizar el ejecutable sin mover estos datos.

En la primera apertura, si no hay datos en Documentos y existe un `datos_app` junto al ejecutable, se copia el historial y la configuración de esa instalación. La copia anterior se conserva. Si ya hay datos en Documentos, no se sustituyen ni se mezclan automáticamente.

La guía está en **GUIA_RAPIDA.html** y en **Ayuda** dentro de la aplicación. El código fuente se puede descargar desde Code → Download ZIP; para ejecutarlo como código fuente sí necesitas Python 3.12 o posterior.

## Uso habitual

- Selecciona los archivos de Entrada y pulsa Siguiente.
- Para cada archivo, elige una plantilla o un destino y completa el ID y la descripción.
- Revisa los nombres y rutas; confirma Exportar lote.
- Crea y edita plantillas en **Plantillas y favoritos**.
- Para borrar historial, marca las entradas y confirma **Borrar seleccionadas**. Esta acción solo elimina registros; no toca archivos.

Se conservan los originales al exportar. Las colisiones bloquean la copia. La sincronización de Drive se comprueba en su cliente.

## Icono

Los archivos **PhDex.png** y **PhDex.ico** están en la raíz. El ICO incluye tamaños desde 16 hasta 256 píxeles. La web usa el mismo diseño sin texto. El icono se generó para PhDex y se convirtió a PNG/ICO.

## Qué contiene esta copia

Código, pruebas, guía, referencia de nombres e iconos. **No incluye** archivos del doctorado, historial SQLite, preferencias personales, favoritos o plantillas guardadas, catálogos ni credenciales. Estos datos permanecen en el ordenador y necesitan su propia copia de seguridad.

Al ejecutar en un equipo nuevo se crea una biblioteca vacía en Documentos. Guarda una copia de Documentos\PhDex para recuperar tu configuración personal; GitHub contiene la aplicación, no estos datos. No extraigas versiones sobre archivos de investigación.

## Pruebas

```text
python -m unittest discover -s tests -v
node --test tests/test_metadata_model.cjs
node --check web/app.js
```

Node se utiliza únicamente para comprobar JavaScript, no para ejecutar la aplicación.

## Mantenimiento

Repositorio de referencia: https://github.com/RpastranaE/PhDex (privado).
Las futuras mejoras deben publicarse aquí después de verificarlas. Esto es una instrucción de mantenimiento; la aplicación no vigila cambios ni sube datos automáticamente.


## Compilar el ejecutable (Windows x64)

```text
python -m pip install -r requirements-build.txt
python build_exe.py
python smoke_exe.py dist/PhDex.exe
```

El resultado es `dist/PhDex.exe`, con el icono y los recursos incluidos. La prueba del ejecutable utiliza datos ficticios y una carpeta temporal. La compilación automática también está disponible en GitHub Actions. El ejecutable se distribuye sin firma digital.
