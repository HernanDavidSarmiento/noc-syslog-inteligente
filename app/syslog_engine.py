"""Motor de ingesta: validación -> deduplicación -> control de tormentas -> almacenamiento.

Resultados posibles de procesar_mensaje():
  almacenado | duplicado | limitado | rechazado
"""
import hashlib
import sqlite3
import time
from typing import Optional

from app.auditoria import registrar
from app.config import SYSLOG_MAX_POR_MINUTO, SYSLOG_VENTANA_DEDUP
from app.seguridad_logs import detectar_sospechoso
from app.syslog_parser import parse_mensaje, sanitizar

ACTOR = "motor_syslog"

# Evita inundar la auditoría: un mismo aviso se registra como máximo 1 vez/minuto.
# (Contadores en memoria: se reinician al reiniciar el proceso.)
_ultimo_aviso: dict[str, float] = {}


def _avisar_una_vez(clave: str, intervalo: float = 60.0) -> bool:
    ahora = time.monotonic()
    if ahora - _ultimo_aviso.get(clave, -1e9) >= intervalo:
        _ultimo_aviso[clave] = ahora
        return True
    return False


def _resolver_dispositivo(conn: sqlite3.Connection, ip_origen: Optional[str],
                          host_msg: Optional[str], permitir_hostname: bool):
    """Lista permitida de fuentes: solo equipos del inventario.

    - Por defecto se identifica por la IP de origen del paquete.
    - El nombre declarado dentro del mensaje SOLO se acepta en pruebas locales
      (loopback) o en importaciones hechas por el operador, porque un atacante
      podría falsificarlo.
    """
    fila = None
    if ip_origen:
        fila = conn.execute(
            "SELECT id, nombre, marca, estado FROM dispositivos WHERE ip = ?",
            (ip_origen,)).fetchone()
    if fila is None and permitir_hostname and host_msg:
        fila = conn.execute(
            "SELECT id, nombre, marca, estado FROM dispositivos WHERE nombre = ?",
            (host_msg,)).fetchone()
    return fila


def procesar_mensaje(conn: sqlite3.Connection, crudo: str, origen: str = "SIMULADO",
                     ip_origen: Optional[str] = None,
                     permitir_hostname: bool = True) -> dict:
    # 1) Validación del formato
    try:
        p = parse_mensaje(crudo)
    except ValueError as e:
        return {"resultado": "rechazado", "motivo": str(e)}

    # 2) Fuente autorizada
    disp = _resolver_dispositivo(conn, ip_origen, p["host"], permitir_hostname)
    if disp is None:
        fuente = sanitizar(str(ip_origen or p["host"] or "desconocida"), 80)
        if _avisar_una_vez(f"fuente:{fuente}"):
            registrar(conn, "syslog_fuente_no_autorizada", "syslog", None,
                      f"Fuente no autorizada: {fuente}",
                      actor=ACTOR, tipo_actor="sistema")
        return {"resultado": "rechazado",
                "motivo": "Fuente no autorizada (no está en el inventario)"}
    if disp["estado"] == "inactivo":
        return {"resultado": "rechazado", "motivo": "Dispositivo inactivo"}

    # 3) Deduplicación
    h = hashlib.sha256(
        f"{disp['id']}|{p['facility']}|{p['severidad']}|{p['mensaje']}".encode("utf-8")
    ).hexdigest()
    dup = conn.execute(
        "SELECT id FROM eventos WHERE dispositivo_id = ? AND mensaje_hash = ? "
        "AND fecha_recepcion >= datetime('now', ?) ORDER BY id DESC LIMIT 1",
        (disp["id"], h, f"-{SYSLOG_VENTANA_DEDUP} seconds")).fetchone()
    if dup:
        conn.execute("UPDATE eventos SET repeticiones = repeticiones + 1 WHERE id = ?",
                     (dup["id"],))
        return {"resultado": "duplicado", "evento_id": dup["id"],
                "severidad": p["severidad"], "host": disp["nombre"]}

    # 4) Control de tormentas
    recientes = conn.execute(
        "SELECT COUNT(*) FROM eventos WHERE dispositivo_id = ? "
        "AND fecha_recepcion >= datetime('now', '-60 seconds')",
        (disp["id"],)).fetchone()[0]
    if recientes >= SYSLOG_MAX_POR_MINUTO:
        if _avisar_una_vez(f"tormenta:{disp['id']}"):
            registrar(conn, "tormenta_eventos_limitada", "dispositivo", disp["id"],
                      f"Se superó el límite de {SYSLOG_MAX_POR_MINUTO} eventos/min; "
                      "se descartan los excedentes",
                      actor=ACTOR, tipo_actor="sistema")
        return {"resultado": "limitado", "severidad": p["severidad"],
                "host": disp["nombre"],
                "motivo": f"Límite de {SYSLOG_MAX_POR_MINUTO} eventos/min por dispositivo"}

    # 5) Almacenamiento (el mensaje se guarda como TEXTO, nunca se ejecuta)
    sospechoso, motivo = detectar_sospechoso(p["mensaje"])
    cur = conn.execute(
        "INSERT INTO eventos (dispositivo_id, marca, fecha_evento, facility, severidad, "
        "host_origen, mensaje, mensaje_hash, origen, sospechoso, motivo_sospecha) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (disp["id"], disp["marca"], p["fecha_evento"], p["facility"], p["severidad"],
         p["host"] or ip_origen, p["mensaje"], h, origen, int(sospechoso), motivo))
    evento_id = cur.lastrowid
    if sospechoso:
        registrar(conn, "log_sospechoso_detectado", "evento", evento_id, motivo,
                  actor=ACTOR, tipo_actor="sistema")
    return {"resultado": "almacenado", "evento_id": evento_id,
            "severidad": p["severidad"], "host": disp["nombre"],
            "sospechoso": sospechoso}