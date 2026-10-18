"""Datos agregados para el dashboard: dispositivos, eventos e incidentes."""
from fastapi import APIRouter

from app.database import db_session
from app.syslog_parser import FACILITIES, SEVERIDADES

router = APIRouter(prefix="/api", tags=["Dashboard"])

SELECT_EVENTOS = (
    "SELECT e.id, e.fecha_evento, e.facility, e.severidad, e.mensaje, e.origen, "
    "e.sospechoso, e.motivo_sospecha, e.repeticiones, e.marca, e.dispositivo_id, "
    "d.nombre AS dispositivo "
    "FROM eventos e LEFT JOIN dispositivos d ON d.id = e.dispositivo_id")

SQL_DISPOSITIVOS = (
    "SELECT d.id, d.nombre, d.ip, d.marca, d.estado, "
    "(SELECT COUNT(*) FROM eventos e WHERE e.dispositivo_id = d.id) AS eventos, "
    "(SELECT COUNT(*) FROM eventos e WHERE e.dispositivo_id = d.id "
    "   AND e.severidad <= 2) AS criticos, "
    "(SELECT MAX(e.fecha_evento) FROM eventos e WHERE e.dispositivo_id = d.id) AS ultimo_evento, "
    "(SELECT COUNT(*) FROM incidentes i WHERE i.dispositivo_id = d.id "
    "   AND i.estado != 'cerrado') AS incidentes_abiertos "
    "FROM dispositivos d ORDER BY d.nombre")


def _con_nombres(filas) -> list[dict]:
    salida = []
    for f in filas:
        d = dict(f)
        d["severidad_nombre"] = SEVERIDADES[d["severidad"]]
        d["facility_nombre"] = FACILITIES[d["facility"]]
        salida.append(d)
    return salida


@router.get("/dashboard")
def dashboard():
    with db_session() as conn:
        # --- Dispositivos ---
        dispositivos = [dict(f) for f in conn.execute(SQL_DISPOSITIVOS).fetchall()]
        por_estado_disp = {"activo": 0, "inactivo": 0, "mantenimiento": 0}
        for d in dispositivos:
            por_estado_disp[d["estado"]] += 1

        # --- Eventos ---
        total = conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
        por_sev = {f["severidad"]: f["n"] for f in conn.execute(
            "SELECT severidad, COUNT(*) AS n FROM eventos GROUP BY severidad")}
        sospechosos = conn.execute(
            "SELECT COUNT(*) FROM eventos WHERE sospechoso = 1").fetchone()[0]
        recientes = _con_nombres(conn.execute(
            SELECT_EVENTOS + " ORDER BY e.fecha_evento DESC, e.id DESC LIMIT 10").fetchall())
        criticos = _con_nombres(conn.execute(
            SELECT_EVENTOS + " WHERE e.severidad <= 2 "
            "ORDER BY e.fecha_evento DESC, e.id DESC LIMIT 10").fetchall())

        # --- Incidentes ---
        estados = {e: 0 for e in ("abierto", "asignado", "en_progreso", "resuelto", "cerrado")}
        for f in conn.execute("SELECT estado, COUNT(*) AS n FROM incidentes GROUP BY estado"):
            estados[f["estado"]] = f["n"]
        pendientes = [dict(f) for f in conn.execute(
            "SELECT i.id, i.titulo, i.severidad, i.estado, i.asignado_a, "
            "d.nombre AS dispositivo, i.fecha_creacion "
            "FROM incidentes i LEFT JOIN dispositivos d ON d.id = i.dispositivo_id "
            "WHERE i.estado != 'cerrado' ORDER BY i.severidad ASC, i.id DESC LIMIT 8")]

    return {
        "dispositivos": {"total": len(dispositivos), "por_estado": por_estado_disp,
                         "lista": dispositivos},
        "eventos": {
            "total": total,
            "criticos": sum(n for s, n in por_sev.items() if s <= 2),
            "sospechosos": sospechosos,
            "por_severidad": [{"severidad": s, "nombre": SEVERIDADES[s],
                               "cantidad": por_sev.get(s, 0)} for s in range(8)],
            "recientes": recientes,
            "criticos_recientes": criticos,
        },
        "incidentes": {
            "sin_cerrar": sum(n for e, n in estados.items() if e != "cerrado"),
            "por_estado": estados,
            "lista": pendientes,
        },
    }