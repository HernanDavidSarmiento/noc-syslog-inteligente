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
    """Sesión transaccional: commit si todo sale bien, rollback si hay error.

    Se usa un solo bloque por petición, de modo que el cambio de datos y su
    registro de auditoría se guardan juntos o no se guardan.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    """Crea las tablas si no existen (idempotente)."""
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))