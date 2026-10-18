# NOC Syslog Inteligente — v0.2.0 (MVP, Corte 2)

Proyecto individual de **Administración y Gestión de Redes** (periodo 2026-2).
Docente: Ing. John Harold Pérez Calderón · Autor: _(tu nombre completo)_

Plataforma de NOC que recibe mensajes **Syslog**, mantiene un inventario de equipos, gestiona incidentes y aplica una
**política de defensa frente a acciones de agentes de IA**: los logs son datos no confiables y ninguna acción tiene
efecto sin revisión y aprobación humana.

> ⚠️ **Todos los datos de ejemplo son SIMULADOS.** El proyecto no contiene contraseñas, tokens ni IPs de producción
> (solo rangos de documentación RFC 5737). No se conecta a ningún equipo real.

## Funcionalidades del MVP

| # | Funcionalidad | Dónde verla |
|---|---|---|
| 1 | Inventario editable (nombre, IP, marca, modelo, versión, ubicación, estado, fecha de actualización) | Pestaña **Inventario** |
| 2 | Recepción por UDP e importación de Syslog (RFC 3164 y 5424), con origen SIMULADO o REAL | `scripts/receptor_syslog.py`, `POST /api/syslog/importar` |
| 3 | Clasificación por equipo, fabricante, fecha, facility y severidad (0 a 7) | Pestaña **Eventos** |
| 4 | Dashboard con estado de equipos, eventos recientes, críticos e incidentes | Pestaña **Dashboard** |
| 5 | Filtros por fecha, marca, equipo y severidad | Pestaña **Eventos** |
| 6 | Incidentes: crear, asignar, seguir y cerrar | Pestaña **Incidentes** |
| 7 | Generador de configuraciones Syslog comentadas para Cisco, Fortinet y Huawei | Pestaña **Configuraciones** |
| 8 | Consola tipo PuTTY simulada, de solo lectura, con comandos permitidos y bloqueados | Pestaña **Consola** |
| 9 | Política de defensa frente a agentes de IA y flujo de acciones con aprobación humana | Pestaña **Defensa IA**, [`docs/POLITICA_DEFENSA_IA.md`](docs/POLITICA_DEFENSA_IA.md) |

## Requisitos

- Python **3.12** (3.13 también debería funcionar; se desaconseja una versión muy reciente: algunas librerías aún no publican instaladores).
- Git.

## Instalación desde cero

**Windows (PowerShell):**

```powershell
git clone <URL_DEL_REPOSITORIO>
cd noc-syslog-inteligente
py -3.12 -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m scripts.init_db
uvicorn app.main:app --reload
```

**Linux / macOS:**

```bash
git clone <URL_DEL_REPOSITORIO>
cd noc-syslog-inteligente
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m scripts.init_db
uvicorn app.main:app --reload
```

Abre **http://127.0.0.1:8000/** (interfaz web) o **http://127.0.0.1:8000/docs** (documentación interactiva de la API).

> Reemplaza `<URL_DEL_REPOSITORIO>` por la URL real. No dejes los símbolos `<` `>`.

## Generar tráfico Syslog simulado

Con la API encendida, abre dos terminales más (con el entorno virtual activado):

```powershell
python -m scripts.receptor_syslog                 # escucha UDP en 127.0.0.1:5514
python -m scripts.enviar_syslog_simulado          # envía mensajes simulados
python -m scripts.enviar_syslog_simulado --tormenta   # prueba del control de tormentas
```

El puerto estándar de Syslog es UDP/514, pero exige privilegios elevados; en desarrollo se usa el **5514**.

## Pruebas automáticas

```powershell
pip install -r requirements-dev.txt
python -m pytest -v
```

Usan una base de datos temporal y no tocan `data/noc_syslog.db`. Detalle en [`docs/PRUEBAS.md`](docs/PRUEBAS.md).

## Configuración

Variables de entorno (copia `.env.example` como `.env`; **nunca** subas `.env` a Git):

| Variable | Valor por defecto | Uso |
|---|---|---|
| `NOC_DB_PATH` | `data/noc_syslog.db` | Ruta de la base de datos SQLite |
| `NOC_SYSLOG_UDP_PORT` | `5514` | Puerto UDP del receptor |
| `NOC_SYSLOG_BIND_HOST` | `127.0.0.1` | Interfaz donde escucha (solo local por defecto) |
| `NOC_SYSLOG_MAX_POR_MINUTO` | `60` | Límite de eventos por equipo y por minuto |
| `NOC_SYSLOG_VENTANA_DEDUP` | `60` | Segundos en los que un mensaje idéntico cuenta como repetido |

## Estructura

```
noc-syslog-inteligente/
├── app/
│   ├── main.py, config.py, database.py, schema.sql, auditoria.py
│   ├── syslog_parser.py, syslog_engine.py, seguridad_logs.py
│   ├── acciones.py, config_syslog.py, consola.py
│   ├── schemas.py, schemas_incidentes.py
│   ├── routers/        (inventario, syslog, incidentes, panel, configuraciones, consola, acciones)
│   └── static/         (index.html, estilos.css, app.js, herramientas.js, defensa.js, defensa.css)
├── scripts/            (init_db, receptor_syslog, enviar_syslog_simulado)
├── tests/              (pruebas automáticas)
├── docs/               (política, historias de usuario, arquitectura, pruebas, capturas)
├── requirements.txt, requirements-dev.txt, pytest.ini
└── .env.example, .gitignore
```

## Seguridad (resumen)

- **Logs = datos no confiables:** se guardan y se muestran como texto; nunca se ejecutan ni se usan como instrucciones.
- **Flujo obligatorio:** evento detectado → validación → propuesta → revisión humana → aprobación → ejecución
  autorizada → verificación → auditoría.
- **Listas permitidas:** fuentes Syslog (inventario), acciones (catálogo) y comandos de consola.
- **Control de volumen:** deduplicación y límite de eventos por minuto; límite de propuestas pendientes.
- **Auditoría de solo inserción:** `UPDATE` y `DELETE` bloqueados por *triggers*, incluidos los intentos denegados.
- **Web:** `textContent` para todo dato externo y cabecera CSP `script-src 'self'`.

Más detalle en [`docs/POLITICA_DEFENSA_IA.md`](docs/POLITICA_DEFENSA_IA.md).

## Limitaciones conocidas (se abordan en el Corte 3)

- Sin autenticación ni roles: el revisor y el tipo de actor se declaran en pantalla.
- Syslog sobre UDP no autentica ni cifra; falta TLS (RFC 5425).
- La detección de texto sospechoso es heurística y solo sirve como alerta.
- La consola y las acciones son simuladas; no se conectan a equipos reales.
- Las plantillas de configuración deben confirmarse con la documentación de cada fabricante y versión.

## Control de versiones

| Etiqueta | Contenido |
|---|---|
| `v0.1.0` | Versión alfa: estructura, esquema SQLite y datos simulados |
| `v0.2.0` | Corte 2: MVP completo |

Rama principal: `main`. Desarrollo en `desarrollo`, integrado mediante *Pull Request*.

## Documentación

- [Política de defensa frente a agentes de IA](docs/POLITICA_DEFENSA_IA.md)
- [Requisitos e historias de usuario](docs/HISTORIAS_USUARIO.md)
- [Arquitectura y diagramas](docs/ARQUITECTURA.md)
- [Plan y registro de pruebas](docs/PRUEBAS.md)
