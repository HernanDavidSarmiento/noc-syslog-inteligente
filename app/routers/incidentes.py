"""Gestión de incidentes: crear, asignar, dar seguimiento y cerrar.

Las reglas de negocio (transiciones de estado, responsable obligatorio, notas de
cierre) se validan AQUÍ, en el backend: la interfaz solo las facilita.
Cada cambio queda en la tabla auditoria (solo inserción).
"""
import json
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.auditoria import registrar
from app.database import db_session
from app.schemas_incidentes import (EstadoIncidente, IncidenteActualizar,
                                    IncidenteCrear, VincularEventos)

router = APIRouter(prefix="/api/incidentes", tags=["Incidentes"])

# Estados a los que se puede pasar desde cada estado. 'cerrado' es final.
TRANSICIONES = {
    "abierto": {"asignado", "en_progreso", "cerrado"},
    "asignado": {"en_progreso", "resuelto", "cerrado"},
    "en_progreso": {"resuelto", "cerrado"},
    "resuelto": {"en_progreso", "cerrado"},
    "cerrado": set(),
}
# Estos estados requieren un responsable humano asignado.
EXIGEN_RESPONSABLE = {"asignado", "en_progreso", "resuelto"}

SELECT_INCIDENTE = (
    "SELECT i.id, i.titulo, i.descripcion, i.severidad, i.estado, i.asignado_a, "
    "i.dispositivo_id, d.nombre AS dispositivo, i.fecha_creacion, i.fecha_cierre, "
    "i.notas_cierre, "
    "(SELECT COUNT(*) FROM incidente_eventos ie WHERE ie.incidente_id = i.id) AS eventos "
    "FROM incidentes i LEFT JOIN dispositivos d ON d.id = i.dispositivo_id")


def _obtener(conn: sqlite3.Connection, inc_id: int) -> sqlite3.Row:
    fila = conn.execute(SELECT_INCIDENTE + " WHERE i.id = ?", (inc_id,)).fetchone()
    if fila is None:
        raise HTTPException(404, "Incidente no encontrado")
    return fila


def _validar_eventos(conn: sqlite3.Connection, ids: list[int]) -> list[sqlite3.Row]:
    unicos = sorted(set(ids))
    if not unicos:
        return []
    marcas = ",".join("?" * len(unicos))   # solo signos "?", nunca texto del usuario
    filas = conn.execute(
        f"SELECT id, dispositivo_id FROM eventos WHERE id IN ({marcas})", unicos).fetchall()
    if len(filas) != len(unicos):
        raise HTTPException(404, "Alguno de los eventos no existe")
    return filas


@router.get("")
def listar(estado: Optional[EstadoIncidente] = None,
           dispositivo_id: Optional[int] = None,
           severidad_max: Optional[int] = Query(None, ge=0, le=7)):
    sql = SELECT_INCIDENTE + " WHERE 1=1"
    params: list = []
    if estado:
        sql += " AND i.estado = ?"
        params.append(estado)
    if dispositivo_id is not None:
        sql += " AND i.dispositivo_id = ?"
        params.append(dispositivo_id)
    if severidad_max is not None:
        sql += " AND i.severidad <= ?"
        params.append(severidad_max)
    # Primero los no cerrados, del más grave al menos grave, luego los más nuevos.
    sql += (" ORDER BY CASE i.estado WHEN 'cerrado' THEN 1 ELSE 0 END, "
            "i.severidad ASC, i.id DESC")
    with db_session() as conn:
        return [dict(f) for f in conn.execute(sql, params).fetchall()]


@router.get("/{inc_id}")
def consultar(inc_id: int):
    """Detalle: datos, eventos vinculados e historial tomado de la auditoría."""
    with db_session() as conn:
        inc = dict(_obtener(conn, inc_id))
        inc["eventos_vinculados"] = [dict(f) for f in conn.execute(
            "SELECT e.id, e.fecha_evento, e.severidad, e.mensaje, e.origen, "
            "e.sospechoso, e.host_origen FROM eventos e "
            "JOIN incidente_eventos ie ON ie.evento_id = e.id "
            "WHERE ie.incidente_id = ? ORDER BY e.fecha_evento DESC LIMIT 100",
            (inc_id,)).fetchall()]
        inc["historial"] = [dict(f) for f in conn.execute(
            "SELECT fecha, actor, tipo_actor, accion, detalle FROM auditoria "
            "WHERE entidad = 'incidente' AND entidad_id = ? ORDER BY id",
            (inc_id,)).fetchall()]
    return inc


@router.post("", status_code=201)
def crear(datos: IncidenteCrear):
    with db_session() as conn:
        eventos = _validar_eventos(conn, datos.evento_ids)
        disp_id = datos.dispositivo_id
        if disp_id is not None:
            if conn.execute("SELECT 1 FROM dispositivos WHERE id = ?",
                            (disp_id,)).fetchone() is None:
                raise HTTPException(404, "Dispositivo no encontrado")
        else:
            # Si no se indicó equipo, se toma el del primer evento que tenga uno.
            disp_id = next((e["dispositivo_id"] for e in eventos if e["dispositivo_id"]), None)

        estado = "asignado" if datos.asignado_a else "abierto"
        cur = conn.execute(
            "INSERT INTO incidentes (titulo, descripcion, severidad, estado, asignado_a, "
            "dispositivo_id) VALUES (?,?,?,?,?,?)",
            (datos.titulo, datos.descripcion, datos.severidad, estado,
             datos.asignado_a, disp_id))
        inc_id = cur.lastrowid
        for e in eventos:
            conn.execute("INSERT OR IGNORE INTO incidente_eventos (incidente_id, evento_id) "
                         "VALUES (?,?)", (inc_id, e["id"]))
        registrar(conn, "crear_incidente", "incidente", inc_id, json.dumps({
            "titulo": datos.titulo, "severidad": datos.severidad, "estado": estado,
            "asignado_a": datos.asignado_a, "dispositivo_id": disp_id,
            "evento_ids": [e["id"] for e in eventos]}, ensure_ascii=False))
        return dict(_obtener(conn, inc_id))


@router.patch("/{inc_id}")
def actualizar(inc_id: int, datos: IncidenteActualizar):
    """Edita, asigna, cambia de estado o cierra. Valida las reglas de negocio."""
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    if not cambios:
        raise HTTPException(400, "No se envió ningún cambio")
    with db_session() as conn:
        actual = dict(_obtener(conn, inc_id))
        if actual["estado"] == "cerrado":
            raise HTTPException(409, "Un incidente cerrado no se puede modificar")

        # Asignar a alguien un incidente 'abierto' lo pasa a 'asignado'.
        if ("estado" not in cambios and "asignado_a" in cambios
                and actual["estado"] == "abierto"):
            cambios["estado"] = "asignado"
        # Pedir el mismo estado que ya tiene no es un cambio.
        if cambios.get("estado") == actual["estado"]:
            del cambios["estado"]

        nuevo = cambios.get("estado")
        if nuevo and nuevo not in TRANSICIONES[actual["estado"]]:
            raise HTTPException(409, f"Transición no permitida: {actual['estado']} -> {nuevo}")

        responsable = cambios.get("asignado_a", actual["asignado_a"])
        if nuevo in EXIGEN_RESPONSABLE and not responsable:
            raise HTTPException(422, "Asigna un responsable antes de pasar a ese estado")

        if nuevo == "cerrado":
            if not cambios.get("notas_cierre"):
                raise HTTPException(422, "Las notas de cierre son obligatorias para cerrar")
        elif "notas_cierre" in cambios:
            raise HTTPException(422, "Las notas de cierre solo se registran al cerrar")

        if not cambios:
            raise HTTPException(400, "No hay cambios respecto al estado actual")

        # Los nombres de columna salen de los campos del esquema (lista cerrada);
        # los VALORES van siempre como parámetros (?).
        sets = [f"{col} = ?" for col in cambios]
        if nuevo == "cerrado":
            sets.append("fecha_cierre = datetime('now')")
        conn.execute(f"UPDATE incidentes SET {', '.join(sets)} WHERE id = ?",
                     (*cambios.values(), inc_id))

        diff = {c: {"antes": actual[c], "despues": v} for c, v in cambios.items()}
        registrar(conn, "cerrar_incidente" if nuevo == "cerrado" else "editar_incidente",
                  "incidente", inc_id, json.dumps(diff, ensure_ascii=False))
        return dict(_obtener(conn, inc_id))


@router.post("/{inc_id}/eventos")
def vincular_eventos(inc_id: int, datos: VincularEventos):
    """Vincula más eventos a un incidente que no esté cerrado."""
    with db_session() as conn:
        inc = _obtener(conn, inc_id)
        if inc["estado"] == "cerrado":
            raise HTTPException(409, "Un incidente cerrado no se puede modificar")
        eventos = _validar_eventos(conn, datos.evento_ids)
        for e in eventos:
            conn.execute("INSERT OR IGNORE INTO incidente_eventos (incidente_id, evento_id) "
                         "VALUES (?,?)", (inc_id, e["id"]))
        registrar(conn, "vincular_eventos", "incidente", inc_id,
                  json.dumps({"evento_ids": [e["id"] for e in eventos]}))
        return dict(_obtener(conn, inc_id))