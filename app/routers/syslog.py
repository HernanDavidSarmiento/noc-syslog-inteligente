"""Endpoints de importación y consulta de eventos Syslog."""
import json
from datetime import date, timedelta
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, StringConstraints

from app.auditoria import registrar
from app.database import db_session
from app.schemas import Marca
from app.syslog_engine import procesar_mensaje
from app.syslog_parser import FACILITIES, SEVERIDADES

router = APIRouter(prefix="/api", tags=["Syslog y eventos"])

Linea = Annotated[str, StringConstraints(max_length=2048)]


class ImportarSolicitud(BaseModel):
    mensajes: list[Linea] = Field(min_length=1, max_length=500)
    origen: Literal["SIMULADO", "REAL"] = "SIMULADO"


@router.post("/syslog/importar")
def importar(datos: ImportarSolicitud):
    """Importa mensajes Syslog (uno por elemento). Pasan por las mismas validaciones."""
    resumen = {"almacenado": 0, "duplicado": 0, "limitado": 0, "rechazado": 0}
    detalles = []
    with db_session() as conn:
        for i, linea in enumerate(datos.mensajes, start=1):
            r = procesar_mensaje(conn, linea, origen=datos.origen)
            resumen[r["resultado"]] += 1
            if r["resultado"] != "almacenado":
                detalles.append({"linea": i, **r})
        registrar(conn, "importar_syslog", "evento", None,
                  json.dumps({"origen": datos.origen, **resumen}))
    return {"resumen": resumen, "detalles": detalles[:50]}


@router.get("/eventos")
def listar_eventos(
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    marca: Optional[Marca] = None,
    dispositivo_id: Optional[int] = None,
    severidad: Optional[int] = Query(None, ge=0, le=7, description="Severidad exacta"),
    severidad_max: Optional[int] = Query(
        None, ge=0, le=7, description="Severidad menor o igual (0 = más grave)"),
    facility: Optional[int] = Query(None, ge=0, le=23),
    sospechoso: Optional[bool] = None,
    limite: int = Query(100, ge=1, le=500),
    desplazamiento: int = Query(0, ge=0),
):
    """Lista eventos con filtros por fecha, marca, equipo, severidad y facility."""
    sql = ("SELECT e.id, e.fecha_evento, e.fecha_recepcion, e.facility, e.severidad, "
           "e.host_origen, e.mensaje, e.origen, e.sospechoso, e.motivo_sospecha, "
           "e.repeticiones, e.marca, e.dispositivo_id, d.nombre AS dispositivo "
           "FROM eventos e LEFT JOIN dispositivos d ON d.id = e.dispositivo_id WHERE 1=1")
    params: list = []
    if desde:
        sql += " AND e.fecha_evento >= ?"
        params.append(desde.isoformat())
    if hasta:
        sql += " AND e.fecha_evento < ?"
        params.append((hasta + timedelta(days=1)).isoformat())
    if marca:
        sql += " AND e.marca = ?"
        params.append(marca)
    if dispositivo_id is not None:
        sql += " AND e.dispositivo_id = ?"
        params.append(dispositivo_id)
    if severidad is not None:
        sql += " AND e.severidad = ?"
        params.append(severidad)
    if severidad_max is not None:
        sql += " AND e.severidad <= ?"
        params.append(severidad_max)
    if facility is not None:
        sql += " AND e.facility = ?"
        params.append(facility)
    if sospechoso is not None:
        sql += " AND e.sospechoso = ?"
        params.append(int(sospechoso))
    sql += " ORDER BY e.fecha_evento DESC, e.id DESC LIMIT ? OFFSET ?"
    params += [limite, desplazamiento]

    with db_session() as conn:
        filas = [dict(f) for f in conn.execute(sql, params).fetchall()]
    for f in filas:
        f["severidad_nombre"] = SEVERIDADES[f["severidad"]]
        f["facility_nombre"] = FACILITIES[f["facility"]]
    return filas


@router.get("/eventos/resumen")
def resumen():
    """Totales para el dashboard: por severidad, por marca, críticos y sospechosos."""
    with db_session() as conn:
        total = conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
        por_sev = {f["severidad"]: f["n"] for f in conn.execute(
            "SELECT severidad, COUNT(*) AS n FROM eventos GROUP BY severidad")}
        por_marca = {(f["marca"] or "Sin dispositivo"): f["n"] for f in conn.execute(
            "SELECT marca, COUNT(*) AS n FROM eventos GROUP BY marca")}
        sospechosos = conn.execute(
            "SELECT COUNT(*) FROM eventos WHERE sospechoso = 1").fetchone()[0]
    return {
        "total": total,
        "criticos": sum(n for s, n in por_sev.items() if s <= 2),  # severidades 0-2
        "sospechosos": sospechosos,
        "por_severidad": [{"severidad": s, "nombre": SEVERIDADES[s],
                           "cantidad": por_sev.get(s, 0)} for s in range(8)],
        "por_marca": por_marca,
    }