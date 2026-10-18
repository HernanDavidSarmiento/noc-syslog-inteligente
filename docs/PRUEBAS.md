# Plan y registro de pruebas — v0.2.0

Todos los datos son **SIMULADOS** (IPs de documentación RFC 5737; equipos `SIM-` y `TEST-`).

## 1. Pruebas automáticas

```powershell
pip install -r requirements-dev.txt
python -m pytest -v
```

Usan una base de datos temporal y no tocan `data/noc_syslog.db`.

| Archivo | Cubre |
|---|---|
| `tests/test_syslog.py` | Parseo RFC 3164 y 5424, severidades 0 a 7, fuentes autorizadas, duplicados, tormentas, logs maliciosos y con HTML, filtros. |
| `tests/test_inventario.py` | CRUD, validación de IP y nombre, conflictos, auditoría del antes y el después. |
| `tests/test_incidentes.py` | Ciclo completo, transiciones, responsable y notas de cierre obligatorios. |
| `tests/test_consola.py` | Allowlist, categorías de bloqueo, encadenado, auditoría de comandos permitidos y bloqueados. |
| `tests/test_configuraciones.py` | Plantillas por marca, sin secretos, rechazo de IP pública e inyección. |
| `tests/test_acciones.py` | Flujo completo, separación de funciones, agente que no aprueba, sin ejecución sin aprobación, límites. |
| `tests/test_seguridad.py` | Auditoría inmutable, restricciones de la BD, cabeceras, sin IPs públicas ni credenciales. |

**Resultado obtenido:** _(pega aquí la última línea de pytest, por ejemplo «N passed»)_

## 2. Pruebas manuales

| ID | Requisito | Procedimiento | Resultado esperado | Obtenido | Evidencia |
|---|---|---|---|---|---|
| F2-4 | HU-01 | `POST /api/dispositivos` con un equipo nuevo | `201` con `id` | ☐ | Swagger |
| F2-5 | HU-01 | Repetir el mismo `POST` | `409` nombre duplicado | ☐ | Swagger |
| F2-6 | HU-01 | `POST` con `"ip": "8.8.8.8"` | `422` IP pública no permitida | ☐ | Swagger |
| F2-7 | HU-01 | `PATCH` con `{"estado":"mantenimiento"}` | `200` con el estado nuevo | ☐ | Swagger |
| F3-2 | HU-02 | Emisor simulado con el receptor activo | 5 almacenados, 3 duplicados, 2 rechazados | ☐ | **E06** |
| F3-4 | HU-03/05 | `GET /api/eventos?severidad_max=2` | Solo severidades 0 a 2 | ☐ | Swagger |
| F3-9 | HU-12 | Emisor con `--tormenta` | Unos 60 almacenados y el resto limitados | ☐ | Terminal |
| F4-3 | HU-05 | Eventos → «Críticos (0 a 2)» | Solo severidades 0, 1 y 2 | ☐ | **E07** |
| F4-9 | HU-06 | Cerrar un incidente con notas | Estado `cerrado` | ☐ | **E08** |
| F4-12 | HU-06 | `PATCH` a `en_progreso` sin responsable | `422` | ☐ | Swagger |
| F4-13 | HU-09 | Importar un log con HTML | Se ve como texto, sin ejecutar | ☐ | Captura |
| F5-1/2/3 | HU-07 | Generar las tres configuraciones | Comentadas, con el colector y el nivel | ☐ | **E09** |
| F5-10 | HU-08 | `configure terminal` en la consola | Bloqueado (modificación) | ☐ | **E10** |
| F5-15 | HU-08 | Comando encadenado por Swagger | `permitido: false` | ☐ | Swagger |
| F6-1 | HU-13 | Defensa IA: proponer una acción | Estado `propuesta`; el equipo no cambia | ☐ | **E11** |
| F6-2 | HU-10 | Aprobar con el mismo nombre que propuso | Error de separación de funciones | ☐ | **E11** |
| F6-3 | HU-10 | Revisión → Aprobar → Ejecutar → Verificar | Estado `verificada` | ☐ | **E11** |
| F6-4 | HU-10 | Proponer `ejecutar_comando` | `422` acción no permitida | ☐ | Swagger |
| F6-5 | HU-11 | Consultar la auditoría | Pasos y denegaciones registrados | ☐ | Terminal |

## 3. Defectos encontrados y corregidos

| Fecha | Defecto | Corrección |
|---|---|---|
| _(completa)_ | _(por ejemplo: nombre de archivo mal escrito)_ | _(acción tomada)_ |
