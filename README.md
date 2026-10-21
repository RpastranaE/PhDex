# PhDex

Proyecto personal creado con ayuda de ChatGPT.

Gestor de archivos de investigación para Windows. Permite seleccionar un lote de archivos, asignar plantillas o destinos favoritos, revisar sus nombres y exportar copias. Incluye auditoría de estructura y nombres e historial con borrado confirmado.

## Descargar y abrir

1. Abre **Releases** en este repositorio público y descarga **PhDex.exe** de la última versión (o el ZIP portátil).
2. Guarda el ejecutable en una carpeta propia y haz doble clic. Lleva Python y los recursos incluidos: no necesitas instalar Python ni ejecutar un CMD.
3. La interfaz se abre en el navegador. Al cerrar la última pestaña, PhDex termina cuando acaba cualquier copia pendiente.

La carpeta de trabajo predeterminada es `D:\Doctorado`. Para otra ubicación: `PhDex.exe --doctorado "C:\Mi carpeta"`.

El historial, plantillas, favoritos y preferencias se guardan en **Documentos\PhDex\datos_app**, en el perfil de Windows donde se ejecuta. Se respeta la ubicación de Documentos configurada en Windows, incluso si está redirigida a OneDrive. Puedes mover o actualizar el ejecutable sin mover estos datos.

En la primera apertura, si no hay datos en Documentos y existe un `datos_app` junto al ejecutable, se copia el historial y la configuración de esa instalación. La copia anterior se conserva. Si ya hay datos en Documentos, no se sustituyen ni se mezclan automáticamente.

La guía está en **GUIA_RAPIDA.html** y en **Ayuda** dentro de la aplicación. El código fuente se puede descargar desde Code → Download ZIP; para ejecutarlo como código fuente sí necesitas Python 3.12 o posterior.

## Actualizaciones y búsqueda

Desde PhDex.exe se consulta la última Release estable en el repositorio público, sin credenciales. Por defecto se actualiza al iniciar si el lote está vacío; puedes desactivarlo en **Actualizaciones**. Si ya has empezado un lote, se ofrece el botón **Actualizar y reiniciar**. Se bloquea la instalación con varias pestañas u operaciones en curso. La descarga se completa y valida su tamaño/formato antes de cerrar la sesión. Un ayudante de Windows guarda una copia del ejecutable anterior, lo sustituye y abre la nueva versión con la misma ubicación de datos. No se instalan versiones anteriores ni preliminares. Si falla la conexión, puedes seguir trabajando; si Windows impide el reemplazo, se conserva el ejecutable y se muestra el error. Los datos de Documentos y los documentos de investigación no se sustituyen.

El buscador de **Historial** filtra nombres, IDs, descripciones y rutas mientras escribes, ignorando mayúsculas y tildes; muestra el número de resultados y un botón Limpiar. Se consultan las últimas 5.000 operaciones.

## Entrada y sugerencias (2.1)

- La carpeta de entrada se detecta al iniciar y se cambia con **Cambiar**. Se guarda por usuario en Documentos/PhDex/datos_app/entrada_reglas.json. No se crea ni reorganiza ninguna carpeta existente.
- Arrastra archivos al primer paso, o pulsa en esa zona para importarlos. Se copian a Entrada sin sobrescribir (hasta 2 GB por archivo). Si ya están en Entrada, usa **Revisar entrada**. El selector de otra ubicación permite añadir una ruta directamente. Las carpetas/adquisiciones con auxiliares se seleccionan completas.
- El reconocimiento usa solo el nombre: fechas AAAA-MM-DD, un ID sin ambigüedad y técnicas habituales (DRX/XRD, FTIR/ATR, Raman, SEM/TEM, DSC/TGA, UV-Vis, RMN). No lee contenido, no inventa IDs. Acepta o descarta las sugerencias. Un nombre completo válido se mantiene mediante Nombre manual; vacíalo para reconstruirlo con los campos.
- Crea reglas en **Reglas de clasificación**: texto literal contenido o extensión, asociados a una plantilla. Las coincidencias múltiples requieren elección. Datos reconocidos del nombre prevalecen sobre la plantilla. Las reglas se evalúan al añadir nuevos archivos.
- La ficha muestra el nombre resultante mientras editas. La revisión final comprueba además destinos y colisiones.
- **Revisar entrada** muestra pendientes y permite incluir exportados. El estado usa historial, tamaño y fechas, con salida todavía existente; no verifica contenido. Si se borra historial, se pierde esa referencia.
- Al acabar, marca uno o varios destinos y pulsa **Abrir seleccionados** (hasta 20 por pulsación). No se abren automáticamente.

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

Repositorio de referencia: https://github.com/RpastranaE/PhDex (público).
Las futuras mejoras deben publicarse aquí después de verificarlas. Esto es una instrucción de mantenimiento; la aplicación no vigila cambios ni sube datos automáticamente.


## Compilar el ejecutable (Windows x64)

```text
python -m pip install -r requirements-build.txt
python build_exe.py
python smoke_exe.py dist/PhDex.exe
```

El resultado es `dist/PhDex.exe`, con el icono y los recursos incluidos. La prueba del ejecutable utiliza datos ficticios y una carpeta temporal. La compilación automática también está disponible en GitHub Actions. El ejecutable se distribuye sin firma digital.
