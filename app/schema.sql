-- =====================================================================
-- NOC Syslog Inteligente v0.2.0 - Modelo de datos (SQLite)
-- Regla de oro: el contenido de los logs es DATO NO CONFIABLE.
-- =====================================================================
PRAGMA foreign_keys = ON;

-- 1. Inventario de equipos (editable)
CREATE TABLE IF NOT EXISTS dispositivos (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre               TEXT    NOT NULL UNIQUE,
    ip                   TEXT    NOT NULL,
    marca                TEXT    NOT NULL CHECK (marca IN ('Cisco','Fortinet','Huawei','Otro')),
    modelo               TEXT    NOT NULL,
    version              TEXT    NOT NULL,
    ubicacion            TEXT    NOT NULL,
    estado               TEXT    NOT NULL DEFAULT 'activo'
                                 CHECK (estado IN ('activo','inactivo','mantenimiento')),
    fecha_actualizacion  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 2. Eventos Syslog (facility 0-23, severidad 0-7)
CREATE TABLE IF NOT EXISTS eventos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo_id   INTEGER REFERENCES dispositivos(id) ON DELETE SET NULL,
    marca            TEXT,
    fecha_evento     TEXT    NOT NULL,
    fecha_recepcion  TEXT    NOT NULL DEFAULT (datetime('now')),
    facility         INTEGER NOT NULL CHECK (facility BETWEEN 0 AND 23),
    severidad        INTEGER NOT NULL CHECK (severidad BETWEEN 0 AND 7),
    host_origen      TEXT,
    mensaje          TEXT    NOT NULL,
    mensaje_hash     TEXT,
    origen           TEXT    NOT NULL DEFAULT 'SIMULADO'
                             CHECK (origen IN ('SIMULADO','REAL')),
    sospechoso       INTEGER NOT NULL DEFAULT 0 CHECK (sospechoso IN (0,1)),
    motivo_sospecha  TEXT
);

CREATE INDEX IF NOT EXISTS idx_eventos_fecha     ON eventos(fecha_evento);
CREATE INDEX IF NOT EXISTS idx_eventos_severidad ON eventos(severidad);
CREATE INDEX IF NOT EXISTS idx_eventos_disp      ON eventos(dispositivo_id);
CREATE INDEX IF NOT EXISTS idx_eventos_hash      ON eventos(mensaje_hash);

-- 3. Incidentes
CREATE TABLE IF NOT EXISTS incidentes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo           TEXT    NOT NULL,
    descripcion      TEXT,
    severidad        INTEGER NOT NULL CHECK (severidad BETWEEN 0 AND 7),
    estado           TEXT    NOT NULL DEFAULT 'abierto'
                             CHECK (estado IN ('abierto','asignado','en_progreso','resuelto','cerrado')),
    asignado_a       TEXT,
    dispositivo_id   INTEGER REFERENCES dispositivos(id) ON DELETE SET NULL,
    fecha_creacion   TEXT    NOT NULL DEFAULT (datetime('now')),
    fecha_cierre     TEXT,
    notas_cierre     TEXT
);

CREATE TABLE IF NOT EXISTS incidente_eventos (
    incidente_id INTEGER NOT NULL REFERENCES incidentes(id) ON DELETE CASCADE,
    evento_id    INTEGER NOT NULL REFERENCES eventos(id)    ON DELETE CASCADE,
    PRIMARY KEY (incidente_id, evento_id)
);

-- 4. Acciones propuestas (flujo estricto con revisión humana)
CREATE TABLE IF NOT EXISTS acciones_propuestas (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_id         INTEGER REFERENCES eventos(id)    ON DELETE SET NULL,
    incidente_id      INTEGER REFERENCES incidentes(id) ON DELETE SET NULL,
    propuesto_por     TEXT    NOT NULL,
    accion            TEXT    NOT NULL,
    parametros        TEXT,
    estado            TEXT    NOT NULL DEFAULT 'propuesta'
                              CHECK (estado IN ('propuesta','en_revision','aprobada',
                                                'rechazada','ejecutada','verificada','fallida')),
    revisado_por      TEXT,
    fecha_propuesta   TEXT    NOT NULL DEFAULT (datetime('now')),
    fecha_revision    TEXT,
    fecha_ejecucion   TEXT,
    resultado         TEXT
);

-- 5. Auditoría (solo inserción: UPDATE y DELETE bloqueados por triggers)
CREATE TABLE IF NOT EXISTS auditoria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha       TEXT NOT NULL DEFAULT (datetime('now')),
    actor       TEXT NOT NULL,
    tipo_actor  TEXT NOT NULL CHECK (tipo_actor IN ('humano','sistema','agente_ia')),
    accion      TEXT NOT NULL,
    entidad     TEXT,
    entidad_id  INTEGER,
    detalle     TEXT
);

CREATE TRIGGER IF NOT EXISTS auditoria_no_update
BEFORE UPDATE ON auditoria
BEGIN
    SELECT RAISE(ABORT, 'auditoria es de solo inserción');
END;

CREATE TRIGGER IF NOT EXISTS auditoria_no_delete
BEFORE DELETE ON auditoria
BEGIN
    SELECT RAISE(ABORT, 'auditoria es de solo inserción');
END;