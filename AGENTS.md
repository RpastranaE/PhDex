# PhDex: mantenimiento

- Repositorio autorizado por el usuario: `https://github.com/RpastranaE/PhDex`, siempre privado.
- El usuario ha solicitado que los futuros cambios de PhDex se publiquen en este mismo repositorio al terminar. Tras cada mejora, verificar, conservar una copia de seguridad, actualizar documentación y publicar la versión revisada. Si el acceso falla, comunicarlo; no afirmar que se ha actualizado.
- Inspeccionar la instalación existente antes de modificar. No borrar ni mover datos originales. El borrado del historial solo afecta a filas SQLite elegidas y exige confirmación en la interfaz.
- No publicar `datos_app/`, bases de datos, preferencias, favoritos/plantillas personales, catálogos, logs, carpetas de pruebas con resultados reales, copias de seguridad, credenciales ni documentos de investigación. Publicar únicamente código, pruebas sintéticas, documentación e iconos.
- Conservar la funcionalidad y pruebas de colisiones, RAW, rutas sin enlaces, historial y copias. No añadir hashes, informes, Notion ni sincronización automática de datos.
- Antes de subir, comprobar la visibilidad privada y revisar los archivos incluidos. No cambiar ni sobrescribir datos del usuario durante una actualización.

- Distribución principal: PhDex.exe (Windows x64). Tras cambios funcionales, compilar con build_exe.py y ejecutar smoke_exe.py; publicar el ejecutable en Releases. No incluir build/, dist/ ni datos de usuario en el árbol de código.
- El estado del usuario está en Documentos/PhDex/datos_app. Nunca reemplazarlo al actualizar. La migración de datos_app antiguo solo copia a un destino inexistente.
