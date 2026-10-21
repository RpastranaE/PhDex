# Comprobación — 21 de octubre de 2026

## Selector de carpetas y gestión limitada a la sesión

Comprobación actual: **49 pruebas Python y 5 pruebas JavaScript correctas**. Se han probado selección y creación explícita de carpetas, nombres existentes sin adquisición de permiso de borrado, rechazo de carpetas ajenas o de sesiones anteriores, identidad de carpetas reemplazadas, protección de contenido y subcarpetas, límites de categoría, bloqueo durante copias e invalidación de planes tras eliminar.

Prueba de interfaz sobre una estructura ficticia: hacer clic en el campo mostró DRX y FTIR existentes, sin controles de borrado. Se creó DRX_prueba_sesion con + Añadir carpeta y Crear carpeta, se seleccionó al momento y se eliminó estando vacía. DRX y FTIR permanecieron intactas. Se creó después DRX_nueva y se exportó un archivo ficticio; al volver a abrir la lista, Eliminar quedó desactivado porque contenía datos. Una recarga mantuvo la sesión y esa protección. Se verificó que no hay botón Preparar destinos y que no se crea una carpeta nueva solo por escribir un nombre.

Las pruebas usaron únicamente carpetas de QA en el espacio de trabajo. No se crearon ni eliminaron carpetas de datos en D:\Doctorado. El borrado de la app usa exclusivamente rmdir, sin recursión, y exige una identidad registrada en memoria por el botón de creación de esta sesión. Al reiniciar se pierde ese permiso, no la carpeta.

## Carpetas descriptivas como DRX

Comprobación vigente: **41 pruebas Python y 5 pruebas JavaScript correctas**. La app permite una carpeta compartida como `04_Caracterizaciones/DRX` sin exigir `ID__Descripcion` ni añadir subcarpetas de plantilla. Se conserva la compatibilidad con las carpetas anteriores por ID.

Pruebas añadidas: reutilización de DRX con diferente combinación de mayúsculas, varios CAR en la misma carpeta, rechazo de rutas o nombres de dispositivos en el campo de nombre, conflicto con un archivo del mismo nombre y auditoría sin avisos falsos por una carpeta DRX. Se mantienen las pruebas de no sobrescritura y de cambios en el destino tras la revisión.

Prueba de interfaz: un archivo ficticio CAR-900, nombre de carpeta DRX y Siguiente, sin pulsar Preparar destinos. La revisión mostró directamente `04_Caracterizaciones/DRX/2026-10-21_CAR-900_Medicion.txt`; la exportación terminó correctamente. La carpeta DRX y un archivo anterior ya existían antes de la prueba y se conservaron. Las pruebas se realizaron en una estructura aislada, sin modificar D:\Doctorado.

Las 21 pruebas de la versión original pasaban antes de los cambios.
La revisión amplía la cobertura a 37 pruebas correctas en Windows, sobre datos sintéticos temporales. También se ha comprobado la sintaxis JavaScript.

Cierre automático: se comprueba la conexión autenticada de la pestaña, su desconexión, la tolerancia a recargas, varias pestañas y la espera de un lote activo. Prueba real adicional en el navegador: abrir, recargar y cerrar la pestaña. El proceso local terminó por sí solo con código 0 después del cierre, sin utilizar el botón de salida. La detección no depende de temporizadores del navegador en segundo plano. Se deja un margen de cinco segundos tras perder la última conexión; un inicio sin ninguna conexión se apaga a los dos minutos.

Se prueban nombres y extensiones, RAW y paquetes completos, colisiones antes y después de revisar, cambios en la fuente, destinos por archivo, errores de copia, conservación del original, historial compatible, sesiones locales, consulta de ambas entradas, propuestas sin crear carpetas, reutilización por ID, duplicados, auditoría de solo lectura, fechas imposibles, excepciones RAW, destinos manuales incorrectos y aparición de un registro alternativo después de revisar. Una prueba bloquea cualquier uso de SHA-256 durante el flujo de copia.

Prueba visual en el navegador del ordenador: selección desde una bandeja aislada, ID CAR-27 ficticio, propuesta de carpeta de registro, vista previa y exportación de un CSV sintético. Resultado: una entrada correcta, original conservado y ausencia de informes por lote.

Auditoría de solo lectura sobre D:\Doctorado: un archivo suelto y un CSV antiguo en 04_Caracterizaciones. No se han movido, renombrado ni eliminado. La estructura actual usa 00_Entrada; no se ha creado otra bandeja.

Limitaciones: el estado final de sincronización de Drive no es accesible desde la app; no se ha probado una adquisición real ni automatizado los diálogos nativos de Windows. La selección de bandeja y la exportación sí se han probado en la interfaz. Las dependencias internas de formatos propietarios deben preservarse con RAW original y paquete completo.


## Asistente por pasos y asignación manual

37 pruebas automáticas: se han retirado las pruebas de importación del catálogo y añadido comprobaciones de que sus rutas ya no existen, el estado no lo incluye, la asignación manual funciona sin leer un catálogo, la validación de datos por paso no crea archivos y el navegador integrado devuelve carpetas y rutas sin modificar datos.

Prueba de interfaz en el ordenador: navegación del selector integrado (subir y entrar en una carpeta), selección de un CSV ficticio, cuatro pantallas sucesivas, bloqueo de avance con ID vacío, asignación manual de CAR-27, reutilización de su carpeta existente, revisión final en su propio paso y exportación correcta. El original ficticio sigue intacto. Los botones Explorar otra carpeta, Copiar una carpeta entera y Elegir carpeta de salida usan el selector integrado, por lo que no generan una ventana externa que pueda quedar detrás.

El selector nativo de archivos sigue disponible; se ha mejorado su propietario para mostrarlo y activarlo antes de abrirlo. Durante la prueba de escritorio el usuario confirmó que apareció el diálogo nativo de carpetas. La solución final para los botones de carpetas es el selector integrado, comprobado de extremo a extremo. No se ha automatizado la interacción con el selector nativo de archivos ni con Firefox.


## Edición directa por archivo

La comprobación actual suma **38 pruebas Python y 5 pruebas JavaScript correctas**. Las pruebas nuevas cubren metadatos independientes, aplicación conjunta limitada a campos explícitos, conservación del registro elegido y confirmación individual de RAW. Una prueba de operaciones copia CAR, EXP, MUE y RES en un solo lote a cuatro destinos distintos, conservando las fuentes.

Prueba de interfaz: se añadieron cuatro archivos ficticios simultáneamente. Se asignaron directamente en sus filas MUE-703, CAR-701, EXP-702 y RES-704, cada uno con un tipo y contenido distinto. La edición conjunta cambió solo la fecha de CAR y EXP; MUE y RES conservaron su fecha, contenido y registro. Después se escribieron cuatro descripciones individuales, se propusieron cuatro destinos, se revisó y se exportó el lote: cuatro entradas completadas. No se utilizaron ventanas de edición por archivo. La captura Edicion_por_archivo.png muestra el editor directo.


## Modo rápido y biblioteca (1.7)
55 pruebas Python y 5 JavaScript. Biblioteca persistente, edición, borrado de accesos sin borrar carpetas, revisiones concurrentes, extensión compuesta, nombres manuales y rechazo de rutas/fechas inválidas. Navegador: creación de plantilla DRX y favorito Ensayos, recarga persistente, selección por archivo CAR/EXP y copia correcta de dos archivos ficticios con originales intactos. Selector de carpeta en la misma ventana conserva el formulario al regresar. Pruebas aisladas de D:/Doctorado; sin comprobar subida a Drive.


## PhDex (1.8)
Renovación visual y de textos. Sin cambios en el motor de copia ni en la biblioteca guardada. Revisión de formulario de plantillas, navegación y lote rápido en navegador.


## PhDex 2.0: EXE y Documentos
61 pruebas Python y 5 JavaScript. Ejecutable Windows x64 con icono y versión integrados, sin consola. Prueba real del EXE con Python externo no configurado: recursos web, SQLite, biblioteca, copia, colisión, borrado confirmado y reinicio persistente. Datos predeterminados en Documentos/PhDex/datos_app; migración SQLite consistente y sin sobrescribir destinos existentes.

## Versión 2.1

71 pruebas Python y 5 JavaScript: reconocimiento conservador y ambigüedades, reglas múltiples y referencias a plantillas eliminadas, carpeta de entrada configurable, importación interrumpida/sin sobrescrituras/nombres inválidos, pendientes modificados o con salida ausente, vista de nombres y apertura restringida a destinos registrados. Prueba del ejecutable con estado temporal, copias, colisiones, pendientes y reinicio. Prueba visual del recorrido con datos sintéticos, sugerencias, vista previa e importación desde navegador. Sin exportaciones ni borrados sobre archivos reales.

Actualizador: comparación de versiones sin regresiones, rechazo de publicaciones preliminares o assets ajenos, descargas truncadas y tamaño/formato inválidos, limitación a HTTPS GitHub, bloqueo con copias en curso o varias pestañas, preferencias persistentes y prueba del ayudante integrado con respaldo, reemplazo y reinicio sobre una instalación aislada. No requiere PowerShell ni altera políticas de Windows.

## Versión 2.1.1

75 pruebas Python y 5 JavaScript correctas. Nuevas regresiones: recurso TLS del runtime incluido al compilar, clasificación de errores de certificados/recursos/red, combinación Y/O de condiciones, validación de límites y persistencia sin modificar reglas ante errores. Se prueba la conexión HTTPS real a GitHub desde el EXE, además de copias, colisiones, respaldo y reinicio del actualizador.

## Versión 2.1.2

Corrección de altura del formulario de reglas: cabecera y botones fuera del área desplazable. Comprobación visual a 1280×600 y 800×500 con 20 condiciones: Guardar permanece dentro de la ventana. Cancelar descarta las modificaciones de prueba. Se mantienen las pruebas del ejecutable y del actualizador.
