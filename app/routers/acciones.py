"""Acciones propuestas: flujo con validación, revisión humana, aprobación, ejecución y verificación.

Las denegaciones NO lanzan HTTPException: se registran en auditoría y se devuelven como
JSON con su código, para que el intento quede guardado (una excepción haría rollback).
"""
import json
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from app.acciones import (CATALOGO, ESTADOS_PENDIENTES, MAX_PENDIENTES_POR_PROPONENTE,
                          revisor_valido)
from app.auditoria import registrar
from app.database import db_session
from app.seguridad_logs import detectar_sospechoso
from app.syslog_parser import sanitizar

router = APIRouter(prefix="/api/acciones", tags=["Acciones propuestas (defensa IA)"])

ESTADOS = ("propuesta", "en_revision", "aprobada", "rechazada", "ejecutada", "verificada", "fallida")
COLUMNAS = ("id, evento_id, incidente_id, propuesto_por, accion, parametros, estado, motivo, "
            "revisado_por, fecha_propuesta, fecha_revision, fecha_ejecucion, resultado")


class AccionProponer(BaseModel):
    accion: str = Field(min_length=1, max_length=64)
    parametros: dict = Field(default_factory=dict)
    propuesto_por: str = Field(min_length=2, max_length=64)
    tipo_actor: Literal["agente_ia", "humano", "sistema"] = "agente_ia"
    evento_id: Optional[int] = Field(default=None, ge=1)
    motivo: Optional[str] = Field(default=None, max_length=500)


class Revision(BaseModel):
    revisado_por: str = Field(min_length=2, max_length=64)


class Decision(BaseModel):
    decision: Literal["aprobar", "rechazar"]
    revisado_por: str = Field(min_length=2, max_length=64)
    comentario: Optional[str] = Field(default=None, max_length=500)


def _fila(conn: sqlite3.Connection, acc_id: int) -> sqlite3.Row:
    f = conn.execute(f"SELECT {COLUMNAS} FROM acciones_propuestas WHERE id = ?", (acc_id,)).fetchone()
    if f is None:
        raise HTTPException(404, "Acción no encontrada")
    return f


def _salida(f: sqlite3.Row) -> dict:
    d = dict(f)
    d["parametros"] = json.loads(d["parametros"]) if d["parametros"] else {}
    return d


def _denegar(conn, codigo: int, mensaje: str, accion_audit: str, entidad_id: Optional[int],
             detalle: dict, actor: str, tipo_actor: str) -> JSONResponse:
    """Registra el intento denegado en auditoría y devuelve la respuesta de error."""
    registrar(conn, accion_audit, "accion", entidad_id,
              json.dumps(detalle, ensure_ascii=False), actor=actor, tipo_actor=tipo_actor)
    return JSONResponse(status_code=codigo, content={"detail": mensaje})


# ----------------------------------------------------------------------------- consulta
@router.get("/catalogo")
def catalogo():
    """Acciones permitidas, con ejemplo de parámetros."""
    return [{"accion": k, "descripcion": v["descripcion"], "riesgo": v["riesgo"],
             "ejemplo": v["ejemplo"]} for k, v in CATALOGO.items()]


@router.get("")
def listar(estado: Optional[str] = Query(None)):
    if estado is not None and estado not in ESTADOS:
        raise HTTPException(422, "Estado inválido")
    sql = f"SELECT {COLUMNAS} FROM acciones_propuestas"
    params: list = []
    if estado:
        sql += " WHERE estado = ?"
        params.append(estado)
    sql += " ORDER BY id DESC LIMIT 200"
    with db_session() as conn:
        return [_salida(f) for f in conn.execute(sql, params).fetchall()]


@router.get("/{acc_id}")
def consultar(acc_id: int):
    with db_session() as conn:
        acc = _salida(_fila(conn, acc_id))
        acc["historial"] = [dict(f) for f in conn.execute(
            "SELECT fecha, actor, tipo_actor, accion, detalle FROM auditoria "
            "WHERE entidad = 'accion' AND entidad_id = ? ORDER BY id", (acc_id,)).fetchall()]
    return acc


# ----------------------------------------------------------------------------- 1) validación y propuesta
@router.post("", status_code=201)
def proponer(datos: AccionProponer):
    actor, tipo = datos.propuesto_por, datos.tipo_actor
    with db_session() as conn:
        # Validación 1: la acción debe estar en el catálogo (lista permitida).
        if datos.accion not in CATALOGO:
            return _denegar(conn, 422, f"Acción no permitida: {sanitizar(datos.accion, 64)}",
                            "accion_rechazada_no_permitida", None,
                            {"accion": sanitizar(datos.accion, 64)}, actor, tipo)
        # Validación 2: parámetros con esquema estricto (sin campos extra).
        try:
            params = CATALOGO[datos.accion]["modelo"](**datos.parametros).model_dump()
        except (ValidationError, TypeError):
            return _denegar(conn, 422, "Parámetros inválidos para esa acción",
                            "accion_rechazada_parametros", None,
                            {"accion": datos.accion}, actor, tipo)
        # Validación 3: los textos libres son datos no confiables; se escanean.
        for campo, texto in (("motivo", datos.motivo), ("titulo", params.get("titulo"))):
            if texto:
                sospechoso, motivo_s = detectar_sospechoso(texto)
                if sospechoso:
                    return _denegar(conn, 422, f"Contenido sospechoso en '{campo}': se rechaza la propuesta",
                                    "accion_rechazada_contenido_sospechoso", None,
                                    {"accion": datos.accion, "campo": campo, "motivo": motivo_s},
                                    actor, tipo)
        # Validación 4: los objetos referenciados deben existir.
        if params.get("dispositivo_id") is not None:
            if conn.execute("SELECT 1 FROM dispositivos WHERE id = ?",
                            (params["dispositivo_id"],)).fetchone() is None:
                raise HTTPException(404, "Dispositivo no encontrado")
        if datos.evento_id is not None:
            if conn.execute("SELECT 1 FROM eventos WHERE id = ?", (datos.evento_id,)).fetchone() is None:
                raise HTTPException(404, "Evento no encontrado")
        # Control de volumen: un proponente no puede acumular propuestas sin revisar.
        pendientes = conn.execute(
            "SELECT COUNT(*) FROM acciones_propuestas WHERE propuesto_por = ? "
            "AND estado IN ('propuesta','en_revision')", (actor,)).fetchone()[0]
        if pendientes >= MAX_PENDIENTES_POR_PROPONENTE:
            return _denegar(conn, 429,
                            f"Demasiadas propuestas sin revisar ({MAX_PENDIENTES_POR_PROPONENTE} máximo)",
                            "propuestas_limitadas", None, {"pendientes": pendientes}, actor, tipo)
        # Propuesta registrada: queda esperando revisión humana.
        cur = conn.execute(
            "INSERT INTO acciones_propuestas (evento_id, propuesto_por, accion, parametros, motivo) "
            "VALUES (?,?,?,?,?)",
            (datos.evento_id, actor, datos.accion, json.dumps(params, ensure_ascii=False),
             sanitizar(datos.motivo, 500) if datos.motivo else None))
        acc_id = cur.lastrowid
        registrar(conn, "proponer_accion", "accion", acc_id,
                  json.dumps({"accion": datos.accion, "parametros": params}, ensure_ascii=False),
                  actor=actor, tipo_actor=tipo)
        return JSONResponse(status_code=201, content=_salida(_fila(conn, acc_id)))


# ----------------------------------------------------------------------------- 2) revisión humana
@router.post("/{acc_id}/revisar")
def revisar(acc_id: int, datos: Revision):
    with db_session() as conn:
        acc = _fila(conn, acc_id)
        error = revisor_valido(datos.revisado_por, acc["propuesto_por"])
        if error:
            return _denegar(conn, 403, error, "revision_denegada", acc_id,
                            {"revisor": datos.revisado_por}, datos.revisado_por, "humano")
        if acc["estado"] != "propuesta":
            raise HTTPException(409, f"Solo se revisa una acción en 'propuesta' (está en '{acc['estado']}')")
        conn.execute("UPDATE acciones_propuestas SET estado='en_revision', revisado_por=?, "
                     "fecha_revision=datetime('now') WHERE id=?", (datos.revisado_por, acc_id))
        registrar(conn, "iniciar_revision", "accion", acc_id, "{}",
                  actor=datos.revisado_por, tipo_actor="humano")
        return _salida(_fila(conn, acc_id))


# ----------------------------------------------------------------------------- 3) aprobación
@router.post("/{acc_id}/decidir")
def decidir(acc_id: int, datos: Decision):
    with db_session() as conn:
        acc = _fila(conn, acc_id)
        error = revisor_valido(datos.revisado_por, acc["propuesto_por"])
        if error:
            return _denegar(conn, 403, error, "aprobacion_denegada", acc_id,
                            {"revisor": datos.revisado_por, "decision": datos.decision},
                            datos.revisado_por, "humano")
        if acc["estado"] != "en_revision":
            raise HTTPException(409, f"Solo se decide una acción en 'en_revision' (está en '{acc['estado']}')")
        nuevo = "aprobada" if datos.decision == "aprobar" else "rechazada"
        conn.execute("UPDATE acciones_propuestas SET estado=?, revisado_por=?, "
                     "fecha_revision=datetime('now') WHERE id=?", (nuevo, datos.revisado_por, acc_id))
        registrar(conn, "aprobar_accion" if nuevo == "aprobada" else "rechazar_accion", "accion", acc_id,
                  json.dumps({"comentario": sanitizar(datos.comentario or "", 500)}, ensure_ascii=False),
                  actor=datos.revisado_por, tipo_actor="humano")
        return _salida(_fila(conn, acc_id))


# ----------------------------------------------------------------------------- 4) ejecución autorizada
def _ejecutar_simulada(conn: sqlite3.Connection, accion: str, params: dict) -> dict:
    """Aplica el efecto (simulado y reversible). Lanza ValueError si ya no es posible."""
    if accion in ("poner_dispositivo_en_mantenimiento", "reactivar_dispositivo"):
        estado = "mantenimiento" if accion == "poner_dispositivo_en_mantenimiento" else "activo"
        cur = conn.execute("UPDATE dispositivos SET estado = ?, fecha_actualizacion = datetime('now') "
                           "WHERE id = ?", (estado, params["dispositivo_id"]))
        if cur.rowcount == 0:
            raise ValueError("El dispositivo ya no existe")
        return {"mensaje": f"Dispositivo {params['dispositivo_id']} en estado '{estado}'",
                "dispositivo_id": params["dispositivo_id"], "estado_esperado": estado}
    if accion == "crear_incidente":
        cur = conn.execute("INSERT INTO incidentes (titulo, descripcion, severidad, dispositivo_id) "
                           "VALUES (?,?,?,?)",
                           (params["titulo"], "Creado por una acción propuesta y aprobada por una persona",
                            params["severidad"], params.get("dispositivo_id")))
        return {"mensaje": f"Incidente {cur.lastrowid} creado", "incidente_id": cur.lastrowid}
    raise ValueError("Acción fuera del catálogo")


@router.post("/{acc_id}/ejecutar")
def ejecutar(acc_id: int):
    with db_session() as conn:
        acc = _fila(conn, acc_id)
        # Solo se ejecuta lo que una persona aprobó.
        if acc["estado"] != "aprobada":
            return _denegar(conn, 409,
                            f"Solo se ejecuta una acción 'aprobada' (está en '{acc['estado']}')",
                            "ejecucion_denegada", acc_id, {"estado": acc["estado"]}, "sistema", "sistema")
        params = json.loads(acc["parametros"])
        try:
            resultado = _ejecutar_simulada(conn, acc["accion"], params)
            nuevo = "ejecutada"
        except ValueError as e:
            resultado, nuevo = {"error": str(e)}, "fallida"
        conn.execute("UPDATE acciones_propuestas SET estado=?, fecha_ejecucion=datetime('now'), "
                     "resultado=? WHERE id=?", (nuevo, json.dumps(resultado, ensure_ascii=False), acc_id))
        registrar(conn, "ejecutar_accion" if nuevo == "ejecutada" else "ejecucion_fallida",
                  "accion", acc_id,
                  json.dumps({"autorizada_por": acc["revisado_por"], **resultado}, ensure_ascii=False),
                  actor="sistema", tipo_actor="sistema")
        return _salida(_fila(conn, acc_id))


# ----------------------------------------------------------------------------- 5) verificación
@router.post("/{acc_id}/verificar")
def verificar(acc_id: int):
    with db_session() as conn:
        acc = _fila(conn, acc_id)
        if acc["estado"] != "ejecutada":
            return _denegar(conn, 409,
                            f"Solo se verifica una acción 'ejecutada' (está en '{acc['estado']}')",
                            "verificacion_denegada", acc_id, {"estado": acc["estado"]}, "sistema", "sistema")
        res = json.loads(acc["resultado"])
        if "estado_esperado" in res:
            f = conn.execute("SELECT estado FROM dispositivos WHERE id = ?", (res["dispositivo_id"],)).fetchone()
            ok = f is not None and f["estado"] == res["estado_esperado"]
        else:
            ok = conn.execute("SELECT 1 FROM incidentes WHERE id = ?", (res.get("incidente_id"),)).fetchone() is not None
        nuevo = "verificada" if ok else "fallida"
        res["verificacion"] = "ok" if ok else "el efecto esperado no se observa"
        conn.execute("UPDATE acciones_propuestas SET estado=?, resultado=? WHERE id=?",
                     (nuevo, json.dumps(res, ensure_ascii=False), acc_id))
        registrar(conn, "verificar_accion", "accion", acc_id,
                  json.dumps({"resultado": res["verificacion"]}, ensure_ascii=False),
                  actor="sistema", tipo_actor="sistema")
        return _salida(_fila(conn, acc_id))
