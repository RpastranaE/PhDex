# PhDex

Gestor de archivos de investigación para Windows. Permite seleccionar un lote de archivos, asignar plantillas o destinos favoritos, revisar sus nombres y exportar copias. Incluye auditoría de estructura y nombres e historial con borrado confirmado.

## Descargar y abrir

1. En este repositorio privado, elige **Code → Download ZIP** y extrae el contenido en una carpeta propia (por ejemplo `D:\Gestor de archivos`).
2. Necesitas Python 3.12 o posterior. La aplicación utiliza la biblioteca estándar: no necesita instalar paquetes para funcionar.
3. Abre **Abrir PhDex.cmd**. Si Python no está disponible, el acceso indicará cómo instalarlo.
4. La carpeta de trabajo predeterminada es `D:\Doctorado`. Para usar otra, ejecuta `python app.py --doctorado "C:\Mi carpeta"`.

La guía detallada se encuentra en **GUIA_RAPIDA.html** y en **Ayuda** dentro de la aplicación.

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

Al descargar en un equipo nuevo se crea una biblioteca vacía. Al actualizar una instalación existente, conserva `datos_app/` y haz antes una copia de la instalación completa. No extraigas una versión sobre archivos de investigación.

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
