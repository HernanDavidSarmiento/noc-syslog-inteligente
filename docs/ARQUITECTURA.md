# Arquitectura — NOC Syslog Inteligente v0.2.0

## 1. Visión general

```mermaid
flowchart LR
    subgraph Equipos["Equipos de red (SIMULADOS)"]
        C[Cisco] ~~~ F[Fortinet] ~~~ H[Huawei]
    end
    Equipos -- "Syslog UDP 5514" --> R[Receptor UDP<br/>scripts/receptor_syslog.py]
    Equipos -. "Importación HTTP" .-> API
    R --> M[Motor de ingesta<br/>parser, fuentes, duplicados, tormentas]
    API --> M
    M --> DB[(SQLite)]
    subgraph API["API FastAPI"]
        I[Inventario] --- E[Eventos] --- N[Incidentes] --- G[Configuraciones] --- K[Consola simulada] --- A[Acciones propuestas]
    end
    API <--> DB
    WEB[Interfaz web<br/>HTML, CSS, JS] <--> API
    OP([Operador / Revisor humano]) <--> WEB
```

## 2. Componentes

| Componente | Archivos | Responsabilidad |
|---|---|---|
| Configuración | `app/config.py`, `.env.example` | Variables de entorno; sin secretos en el código. |
| Base de datos | `app/database.py`, `app/schema.sql` | Conexión, transacciones y esquema con restricciones. |
| Ingesta Syslog | `syslog_parser.py`, `syslog_engine.py`, `seguridad_logs.py`, `scripts/receptor_syslog.py` | Parseo RFC 3164 y 5424, clasificación, fuentes autorizadas, duplicados y tormentas. |
| API | `app/routers/*.py` | Inventario, eventos, incidentes, configuraciones, consola, acciones y panel. |
| Reglas de acciones | `app/acciones.py` | Catálogo, esquemas estrictos y separación de funciones. |
| Auditoría | `app/auditoria.py` | Inserción en la tabla de solo inserción. |
| Interfaz web | `app/static/*` | Dashboard, eventos, incidentes, inventario, configuraciones, consola y defensa IA. |
| Pruebas | `tests/` | Pruebas automáticas con base de datos temporal. |

## 3. Modelo de datos

```mermaid
erDiagram
    DISPOSITIVOS ||--o{ EVENTOS : genera
    DISPOSITIVOS ||--o{ INCIDENTES : afecta
    INCIDENTES ||--o{ INCIDENTE_EVENTOS : agrupa
    EVENTOS ||--o{ INCIDENTE_EVENTOS : "pertenece a"
    EVENTOS ||--o{ ACCIONES_PROPUESTAS : origina
    INCIDENTES ||--o{ ACCIONES_PROPUESTAS : "se relaciona con"

    DISPOSITIVOS {
        int id PK
        text nombre UK
        text ip
        text marca
        text modelo
        text version
        text ubicacion
        text estado
        text fecha_actualizacion
    }
    EVENTOS {
        int id PK
        int dispositivo_id FK
        text marca
        text fecha_evento
        int facility "0 a 23"
        int severidad "0 a 7"
        text mensaje "dato no confiable"
        text origen "SIMULADO o REAL"
        int sospechoso
        int repeticiones
    }
    INCIDENTES {
        int id PK
        text titulo
        int severidad
        text estado
        text asignado_a
        int dispositivo_id FK
        text notas_cierre
    }
    ACCIONES_PROPUESTAS {
        int id PK
        int evento_id FK
        text propuesto_por
        text accion
        text parametros
        text estado
        text revisado_por
        text motivo "dato no confiable"
    }
    AUDITORIA {
        int id PK
        text actor
        text tipo_actor "humano, sistema o agente_ia"
        text accion
        text entidad
        int entidad_id
        text detalle
    }
```

`AUDITORIA` no tiene relaciones: es de solo inserción y los *triggers* bloquean `UPDATE` y `DELETE`.

## 4. Estados de una acción propuesta

```mermaid
stateDiagram-v2
    [*] --> propuesta
    propuesta --> en_revision: revisa una persona
    en_revision --> aprobada: aprueba (otra persona)
    en_revision --> rechazada: rechaza
    aprobada --> ejecutada: ejecución autorizada
    aprobada --> fallida: el objeto ya no existe
    ejecutada --> verificada: efecto comprobado
    ejecutada --> fallida: efecto no observado
    rechazada --> [*]
    verificada --> [*]
    fallida --> [*]
```

## 5. Secuencia: un log malicioso y una acción propuesta

```mermaid
sequenceDiagram
    participant EQ as Equipo
    participant MI as Motor de ingesta
    participant AG as Agente de IA
    participant API as API de acciones
    participant HU as Revisor humano
    participant AU as Auditoría
    EQ->>MI: Syslog con texto "IGNORE PREVIOUS INSTRUCTIONS..."
    MI->>MI: valida fuente, guarda como texto y marca sospechoso
    MI->>AU: log_sospechoso_detectado
    AG->>API: propone acción (catálogo y parámetros)
    API->>AU: proponer_accion (nada cambia)
    HU->>API: revisa y aprueba (distinto de quien propuso)
    API->>AU: aprobar_accion
    API->>API: ejecuta (simulado) y verifica
    API->>AU: ejecutar_accion y verificar_accion
```

## 6. Endpoints principales

| Grupo | Endpoints |
|---|---|
| Inventario | `GET/POST /api/dispositivos`, `GET/PATCH/DELETE /api/dispositivos/{id}` |
| Syslog y eventos | `POST /api/syslog/importar`, `GET /api/eventos`, `GET /api/eventos/resumen` |
| Panel | `GET /api/dashboard` |
| Incidentes | `GET/POST /api/incidentes`, `GET/PATCH /api/incidentes/{id}`, `POST /api/incidentes/{id}/eventos` |
| Configuraciones | `POST /api/configuraciones/syslog` |
| Consola simulada | `POST /api/consola/ejecutar` |
| Acciones | `GET /api/acciones/catalogo`, `GET/POST /api/acciones`, `GET /api/acciones/{id}`, `POST /api/acciones/{id}/revisar`, `/decidir`, `/ejecutar`, `/verificar` |
| Sistema | `GET /api/salud`, documentación en `/docs` |

## 7. Decisiones de diseño

- **SQLite** y **FastAPI**: sencillos de instalar y de explicar; suficientes para el MVP.
- **Frontend sin frameworks**: HTML, CSS y JavaScript, con `textContent` para todo dato externo.
- **Reglas en el backend**: la interfaz solo las hace visibles; la API las aplica siempre.
- **Denegaciones auditadas**: un intento rechazado también deja huella.
