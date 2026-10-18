"""Parser de mensajes Syslog (RFC 3164 y RFC 5424).

REGLA DE ORO: el mensaje es un DATO NO CONFIABLE. Aquí solo se extrae y se
sanea texto; nada se evalúa, se ejecuta ni se interpreta como instrucción.
"""
import re
from datetime import datetime, timezone
from typing import Optional

SEVERIDADES = ["Emergency", "Alert", "Critical", "Error",
               "Warning", "Notice", "Informational", "Debug"]
FACILITIES = ["kern", "user", "mail", "daemon", "auth", "syslog", "lpr", "news",
              "uucp", "cron", "authpriv", "ftp", "ntp", "audit", "alert", "clock",
              "local0", "local1", "local2", "local3",
              "local4", "local5", "local6", "local7"]

MAX_MENSAJE = 1024
FORMATO_FECHA = "%Y-%m-%dT%H:%M:%SZ"

# Caracteres de control (salvo tabulación y salto de línea) se eliminan.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

_RFC5424 = re.compile(
    r"^<(?P<pri>\d{1,3})>(?P<ver>\d{1,2}) (?P<ts>\S+) (?P<host>\S+) "
    r"(?P<app>\S+) (?P<procid>\S+) (?P<msgid>\S+) "
    r"(?P<sd>-|(?:\[[^\]]*\])+)(?: (?P<msg>.*))?$", re.DOTALL)
_RFC3164 = re.compile(
    r"^<(?P<pri>\d{1,3})>(?P<ts>[A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2}) "
    r"(?P<host>\S+) (?P<msg>.*)$", re.DOTALL)
_SOLO_PRI = re.compile(r"^<(?P<pri>\d{1,3})>\s*(?P<msg>.*)$", re.DOTALL)


def sanitizar(texto: str, maximo: int = MAX_MENSAJE) -> str:
    """Quita caracteres de control y limita la longitud."""
    return _CONTROL.sub("", texto).strip()[:maximo]


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime(FORMATO_FECHA)


def _fecha_5424(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime(FORMATO_FECHA)
    except ValueError:
        return _ahora()


def _fecha_3164(ts: str) -> str:
    # RFC 3164 no trae año ni zona horaria: se asume el año actual y UTC.
    try:
        anio = datetime.now(timezone.utc).year
        return datetime.strptime(f"{anio} {ts}", "%Y %b %d %H:%M:%S").strftime(FORMATO_FECHA)
    except ValueError:
        return _ahora()


def parse_mensaje(crudo: str) -> dict:
    """Interpreta un mensaje Syslog. Lanza ValueError si no es válido."""
    texto = crudo.strip()
    host: Optional[str] = None

    m = _RFC5424.match(texto)
    if m:
        formato = "RFC5424"
        fecha = _fecha_5424(m.group("ts"))
        host = None if m.group("host") == "-" else m.group("host")
    else:
        m = _RFC3164.match(texto)
        if m:
            formato = "RFC3164"
            fecha = _fecha_3164(m.group("ts"))
            host = m.group("host")
        else:
            m = _SOLO_PRI.match(texto)
            if not m:
                raise ValueError("Mensaje sin PRI válido (se espera <0-191>)")
            formato = "PRI"
            fecha = _ahora()

    pri = int(m.group("pri"))
    if pri > 191:
        raise ValueError("PRI fuera de rango (0-191)")

    mensaje = sanitizar(m.group("msg") or "")
    if not mensaje:
        raise ValueError("Mensaje vacío")

    facility, severidad = pri // 8, pri % 8
    return {
        "facility": facility, "facility_nombre": FACILITIES[facility],
        "severidad": severidad, "severidad_nombre": SEVERIDADES[severidad],
        "fecha_evento": fecha,
        "host": sanitizar(host, 64) if host else None,
        "mensaje": mensaje, "formato": formato,
    }