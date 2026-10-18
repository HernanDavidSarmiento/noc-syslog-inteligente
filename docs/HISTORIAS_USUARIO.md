# Requisitos e historias de usuario — NOC Syslog Inteligente v0.2.0

Roles: **Operador NOC**, **Administrador de red**, **Supervisor** y **Agente de IA** (actor restringido).

| ID | Historia | Criterios de aceptación | Evidencia |
|---|---|---|---|
| HU-01 | Como **administrador** quiero registrar y editar equipos (nombre, IP, marca, modelo, versión, ubicación, estado) para tener un inventario confiable. | Se crea, edita y elimina; no acepta IP pública ni nombre duplicado; cada cambio queda auditado con el antes y el después. | `test_inventario.py`, **E04** |
| HU-02 | Como **operador** quiero recibir o importar mensajes Syslog, claramente identificados como simulados o reales, para ver qué pasa en la red. | Se interpreta RFC 3164 y RFC 5424; el origen queda como SIMULADO o REAL; los mensajes inválidos se rechazan. | `test_syslog.py`, **E06** |
| HU-03 | Como **operador** quiero que cada evento se clasifique por equipo, fabricante, fecha, facility y severidad (0 a 7) para priorizar. | `PRI` se descompone en facility y severidad; las 8 severidades se clasifican bien. | `test_las_ocho_severidades...` |
| HU-04 | Como **operador** quiero un dashboard con el estado de los equipos, eventos recientes, críticos e incidentes para tener una visión rápida. | Muestra tarjetas, estado por equipo, gráfico por severidad y tablas; se actualiza solo. | **E05** |
| HU-05 | Como **operador** quiero filtrar eventos por fecha, marca, equipo y severidad para encontrar lo relevante. | Los filtros se combinan; «críticos» muestra severidades 0 a 2. | `test_filtro_...`, **E07** |
| HU-06 | Como **operador** quiero crear, asignar, seguir y cerrar incidentes para gestionar la respuesta. | Estados y transiciones válidos; responsable obligatorio; notas de cierre obligatorias; historial desde la auditoría. | `test_incidentes.py`, **E08** |
| HU-07 | Como **administrador** quiero generar configuraciones Syslog comentadas para Cisco, Fortinet y Huawei para configurar equipos sin errores. | Incluye colector, severidad, facility, NTP y verificación; no contiene secretos; rechaza IP pública. | `test_configuraciones.py`, **E09** |
| HU-08 | Como **operador** quiero una consola simulada de solo lectura para consultar un equipo sin riesgo de modificarlo. | Solo responden comandos permitidos; los peligrosos se bloquean con su motivo; todo queda auditado. | `test_consola.py`, **E10** |
| HU-09 | Como **supervisor** quiero que el sistema trate los logs como datos no confiables para que un log malicioso no controle nada. | Un log con una orden para una IA se guarda como texto, queda marcado y nunca se ejecuta; la web no ejecuta HTML. | `test_log_malicioso...`, **E11** |
| HU-10 | Como **supervisor** quiero que toda acción propuesta pase por revisión y aprobación humana para evitar cambios no autorizados. | Quien propone no aprueba; un agente de IA no aprueba; sin aprobación no se ejecuta. | `test_acciones.py`, **E11** |
| HU-11 | Como **auditor** quiero un registro que nadie pueda alterar para reconstruir lo ocurrido. | `UPDATE` y `DELETE` sobre la auditoría abortan; se registran también los intentos denegados. | `test_seguridad.py` |
| HU-12 | Como **operador** quiero que el sistema controle tormentas y duplicados para no saturarme. | Duplicados se cuentan; el exceso de eventos por minuto se descarta y se avisa una sola vez. | `test_control_de_tormentas...` |
| HU-13 | Como **agente de IA** (actor restringido) puedo proponer acciones del catálogo para ayudar al NOC, sin poder ejecutarlas ni aprobarlas. | Solo acciones del catálogo con parámetros válidos; límite de propuestas pendientes. | `test_acciones.py` |

## Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-01 | Sin secretos ni IPs reales en el código; datos de ejemplo etiquetados como SIMULADOS. |
| RNF-02 | Instalación reproducible desde cero con `requirements.txt` y el README. |
| RNF-03 | Cabeceras de seguridad y política de contenido (CSP) en la web. |
| RNF-04 | Pruebas automáticas ejecutables con `python -m pytest`. |
| RNF-05 | El servicio escucha solo en `127.0.0.1` por defecto. |
