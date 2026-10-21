# PhDex

# Archivos · Doctorado

Abre **Abrir Doctorado Archivos.cmd**, en `D:\Gestor de archivos`.
La guía sencilla está en **GUIA_RAPIDA.html** y en **Guía de uso**, dentro de la app.

## Flujo en cuatro pasos

1. **Archivos:** revisa `D:\Doctorado\00_Entrada` o añade archivos de otra ubicación. Marca lo que quieres procesar y pulsa Siguiente.
2. **Datos:** cada archivo tiene sus campos editables visibles. Asigna el tipo, registro, ID, fecha y contenido directamente en su fila. Los campos adicionales se despliegan en esa misma fila. No hay valores heredados del formulario general.
3. **Destino:** haz clic en el campo para elegir una carpeta existente dentro de la ruta que muestra Buscar en. **+ Añadir carpeta** abre el nombre y **Crear carpeta** la crea y selecciona al momento. No hay botón de preparación. **Siguiente** revisa la copia de archivos.
4. **Revisar:** comprueba nombres y rutas completas. Usa Atrás para corregir errores. Solo al pulsar Exportar lote se copian los archivos.

Los botones de carpetas abren un selector dentro de la app: puedes subir un nivel, entrar en una subcarpeta o pegar una ruta. No necesitas minimizar ventanas. Elegir archivos sigue usando el selector de archivos de Windows.

**Copiar una carpeta entera** significa copiar todo su contenido como una unidad, sin renombrar los archivos interiores. Es útil para adquisiciones instrumentales con auxiliares. Para archivos sueltos, usa Elegir archivos o Revisar Entrada.

## Edición conjunta opcional

La edición por archivo es la opción principal. Ningún archivo toma los datos de otro ni los de la última sesión. La fecha inicial es hoy y réplica/versión empiezan en 0: revísalos según tus datos.

Si varios archivos comparten un dato, marca **Edición conjunta** en esas filas, abre **Aplicar datos a varios archivos (opcional)** y marca los campos que quieres copiar. Rellena sus valores y pulsa **Aplicar a las filas marcadas**. Solo cambian esos campos en esas filas; los demás permanecen intactos. Cambiar el formulario conjunto sin pulsar Aplicar no modifica los archivos.

Los destinos y los nombres de carpetas también son individuales. La salida común opcional se utiliza únicamente para archivos sin ruta propia. Si cambias de categoría, vuelve a elegir una carpeta de destino en esa fila.

## Conservación y nombres

Exportar conserva el original. No se sobrescriben salidas existentes ni se incrementan automáticamente versiones o réplicas. La regla sigue siendo `AAAA-MM-DD_ID[_MUE-ID][_Tecnica]_Contenido[_rNN][_vNN].ext`. RAW original conserva nombres y estructura del equipo; usa la adquisición completa si depende de auxiliares.

Se admiten carpetas descriptivas compartidas, como `04_Caracterizaciones/DRX`, sin prefijo de ID ni subcarpetas adicionales. Varios CAR pueden compartir DRX: el ID permanece en el nombre de cada archivo. La carpeta principal debe corresponder al registro (CAR, EXP, MUE, RES…). Se permite almacenamiento externo elegido manualmente. Las carpetas anteriores por ID se conservan y pueden seguir utilizándose; no se mueven ni fusionan datos existentes.

El historial se conserva en `datos_app/registro.sqlite3`, compatible con las operaciones anteriores. Se registran nombres, rutas, datos asignados, resultado y errores. No se calculan hashes ni se generan informes junto a los datos. Se comprueban cambios de tamaño/fecha durante la revisión y la copia, pero no se garantiza identidad binaria de contenido. Si una entrada falla, su original se conserva; las copias anteriores del lote no se revierten. Los temporales de una interrupción abrupta pueden permanecer en la salida y requieren revisión manual.

**Renombrar en origen** queda en las opciones avanzadas del paso Destino. Esa opción sí cambia el nombre original, tras confirmarlo en Revisar; no es necesaria para exportar desde Entrada. No tiene deshacer automático.

## Auditoría, Drive y cierre

La auditoría de estructura y nombres es de solo lectura: muestra observaciones, sin corregir ni mover archivos. Omite Entrada, gestión, plantillas y nombres internos de `01_RAW`; limita la revisión a 20.000 archivos e indica si es parcial.

Una copia local terminada no confirma la subida a Drive. Descarga antes los archivos disponibles solo en la nube y comprueba después el estado del cliente de sincronización. La app no modifica esa configuración.

Cerrar la última pestaña apaga la app tras unos segundos. Recargar mantiene la sesión. Si hay una copia activa, primero termina. Sin conexión inicial de navegador, un inicio se apaga a los dos minutos.

## Asignación manual

Ya no hay catálogo, importación ni actualización con Notion en la app. Tú asignas cada registro y sus relaciones. Los antiguos archivos de catálogo se conservan en disco para no borrar datos anteriores, pero no se leen ni se utilizan. El historial anterior también permanece intacto.

## Comprobación técnica

Requiere Python 3.12 o posterior, sin paquetes adicionales. Pruebas: `python -m unittest discover -s tests -v`. La opción `--doctorado RUTA --data-dir RUTA --no-browser` permite probar sobre archivos ficticios sin utilizar datos reales. Consulta `VERIFICACION.md` para el alcance de las pruebas.

La guía original de referencia muestra la organización por ID, pero la app admite ahora la organización por nombres descriptivos elegida por el usuario. La auditoría acepta DRX, FTIR y otros nombres de carpeta sin exigir ID__Descripcion.


## Crear y eliminar carpetas desde el selector

El listado se actualiza al abrir el campo, admite filtrar escribiendo y solo muestra subcarpetas reales, sin enlaces ni uniones. Cambiar carpeta base permite navegar dentro de la categoría correspondiente. Las rutas manuales siguen disponibles como opción avanzada.

La creación es explícita e inmediata con **Crear carpeta**. Si el nombre ya existe, se selecciona su carpeta real, sin sobrescribirla ni atribuirle permiso de borrado. Las carpetas nuevas se conservan al cerrar: no se limpian automáticamente.

Solo las creadas mediante ese botón en la sesión actual ofrecen **Eliminar**, y únicamente mientras estén vacías. No se admite borrado recursivo, de carpetas anteriores, de una carpeta reemplazada por otra o de una carpeta que contenga archivos o subcarpetas. La app vuelve a comprobarlo en el ordenador al confirmar la eliminación. Mientras se copia un lote, no se crean ni eliminan carpetas desde el selector. Borrar una carpeta invalida las revisiones pendientes y limpia las selecciones que la usaban.

La sesión corresponde al proceso de la app, compartido por sus pestañas. Recargar mantiene la sesión; cerrarla y volverla a abrir empieza otra. Los permisos de borrado son temporales y no se guardan en disco: las carpetas que permanezcan al cerrar quedan protegidas en la siguiente sesión.


Versión 1.7: modo rápido de tres pasos y página Plantillas y favoritos. La biblioteca local se guarda atómicamente en datos_app/plantillas_favoritos.json; sus revisiones evitan sobrescribir cambios de otra pestaña. No guarda IDs ni fechas de lote. Los favoritos solo seleccionan destinos existentes. El nombre manual opcional respeta fecha/ID y conserva la extensión; el historial registra el ID real.


Versión 1.8: identidad PhDex, navegación con iconos SVG, diseño neutro y formularios con ayuda contextual. Acceso Abrir PhDex.cmd; se conserva el acceso anterior.


## Versión 2.0: ejecutable
Abre PhDex.exe. Incluye el intérprete y los recursos, y utiliza la interfaz en el navegador. El historial, preferencias y biblioteca se guardan en Documentos/PhDex/datos_app. El primer arranque copia los datos antiguos adyacentes solo si el destino no existe; nunca borra ni sobrescribe el historial previo. Los accesos CMD antiguos utilizan el EXE cuando está presente. Consulta README.md para descargar y compilar.
