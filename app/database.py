"""Acceso a SQLite: conexión, sesión transaccional y creación del esquema."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.config import DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Devuelve una conexión con filas accesibles por nombre y FKs activas."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session():
    """Sesión transaccional: commit si todo sale bien, rollback si hay error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrar(conn: sqlite3.Connection) -> None:
    """Migraciones simples e idempotentes sobre una BD ya existente."""
    columnas = {f["name"] for f in conn.execute("PRAGMA table_info(eventos)")}
    if "repeticiones" not in columnas:
        # Fase 3: contador de mensajes idénticos deduplicados
        conn.execute(
            "ALTER TABLE eventos ADD COLUMN repeticiones INTEGER NOT NULL DEFAULT 1")


def init_schema() -> None:
    """Crea las tablas si no existen y aplica migraciones (idempotente)."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrar(conn)