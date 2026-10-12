"""Registro en la tabla auditoria (solo inserción, protegida por triggers)."""
import sqlite3
from typing import Optional

# Autenticación queda fuera del alcance del MVP: todas las acciones se
# atribuyen a un operador humano local.
OPERADOR_LOCAL = "operador_local"


def registrar(conn: sqlite3.Connection, accion: str, entidad: str,
              entidad_id: Optional[int], detalle: str,
              actor: str = OPERADOR_LOCAL, tipo_actor: str = "humano") -> None:
    """Inserta un registro de auditoría dentro de la transacción actual."""
    conn.execute(
        "INSERT INTO auditoria (actor, tipo_actor, accion, entidad, entidad_id, detalle) "
        "VALUES (?,?,?,?,?,?)",
        (actor, tipo_actor, accion, entidad, entidad_id, detalle))