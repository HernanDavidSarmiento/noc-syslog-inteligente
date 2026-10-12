"""CRUD del inventario de dispositivos. Cada cambio queda auditado."""
import json
import sqlite3
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from app.auditoria import registrar
from app.database import db_session
from app.schemas import (DispositivoActualizar, DispositivoCrear,
                         DispositivoSalida, Estado, Marca)

router = APIRouter(prefix="/api/dispositivos", tags=["Inventario"])

COLUMNAS = ("id, nombre, ip, marca, modelo, version, ubicacion, "
            "estado, fecha_actualizacion")


def _obtener(conn: sqlite3.Connection, disp_id: int) -> sqlite3.Row:
    fila = conn.execute(
        f"SELECT {COLUMNAS} FROM dispositivos WHERE id = ?", (disp_id,)).fetchone()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispositivo no encontrado")
    return fila


@router.get("", response_model=list[DispositivoSalida])
def listar(marca: Optional[Marca] = None, estado: Optional[Estado] = None):
    """Lista dispositivos; filtra opcionalmente por marca y estado."""
    sql = f"SELECT {COLUMNAS} FROM dispositivos WHERE 1=1"
    params: list = []
    if marca:
        sql += " AND marca = ?"
        params.append(marca)
    if estado:
        sql += " AND estado = ?"
        params.append(estado)
    sql += " ORDER BY nombre"
    with db_session() as conn:
        return [dict(f) for f in conn.execute(sql, params).fetchall()]


@router.get("/{disp_id}", response_model=DispositivoSalida)
def consultar(disp_id: int):
    with db_session() as conn:
        return dict(_obtener(conn, disp_id))


@router.post("", response_model=DispositivoSalida, status_code=status.HTTP_201_CREATED)
def crear(datos: DispositivoCrear):
    with db_session() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO dispositivos (nombre, ip, marca, modelo, version, ubicacion, estado) "
                "VALUES (?,?,?,?,?,?,?)",
                (datos.nombre, datos.ip, datos.marca, datos.modelo,
                 datos.version, datos.ubicacion, datos.estado))
        except sqlite3.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Ya existe un dispositivo con ese nombre")
        nuevo_id = cur.lastrowid
        registrar(conn, "crear_dispositivo", "dispositivo", nuevo_id,
                  json.dumps(datos.model_dump(), ensure_ascii=False))
        return dict(_obtener(conn, nuevo_id))


@router.patch("/{disp_id}", response_model=DispositivoSalida)
def actualizar(disp_id: int, datos: DispositivoActualizar):
    """Edita solo los campos enviados y guarda el antes/después en auditoría."""
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    if not cambios:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se envió ningún cambio")
    with db_session() as conn:
        actual = dict(_obtener(conn, disp_id))
        # Los nombres de columna salen de los campos del esquema (lista cerrada),
        # nunca del usuario; los VALORES van siempre como parámetros (?).
        sets = ", ".join(f"{col} = ?" for col in cambios)
        try:
            conn.execute(
                f"UPDATE dispositivos SET {sets}, fecha_actualizacion = datetime('now') "
                "WHERE id = ?", (*cambios.values(), disp_id))
        except sqlite3.IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Ya existe un dispositivo con ese nombre")
        diff = {c: {"antes": actual[c], "despues": v} for c, v in cambios.items()}
        registrar(conn, "editar_dispositivo", "dispositivo", disp_id,
                  json.dumps(diff, ensure_ascii=False))
        return dict(_obtener(conn, disp_id))


@router.delete("/{disp_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(disp_id: int):
    """Elimina el equipo. Sus eventos se conservan (dispositivo_id pasa a NULL)."""
    with db_session() as conn:
        actual = dict(_obtener(conn, disp_id))
        conn.execute("DELETE FROM dispositivos WHERE id = ?", (disp_id,))
        registrar(conn, "eliminar_dispositivo", "dispositivo", disp_id,
                  json.dumps(actual, ensure_ascii=False))