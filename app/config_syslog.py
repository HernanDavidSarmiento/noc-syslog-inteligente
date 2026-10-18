"""Generador de configuraciones Syslog comentadas (Cisco, Fortinet, Huawei).

Solo produce TEXTO. Nunca se conecta ni aplica nada en un equipo: es una propuesta
que un responsable revisa y aplica a mano (flujo: propuesta -> revisión humana ->
aprobación -> ejecución autorizada).

Todos los valores que entran a la plantilla llegan ya validados (IP no pública,
listas cerradas, puerto numérico), por eso no es posible colar líneas de comandos
adicionales en la configuración generada.
"""
import ipaddress
import re
from datetime import datetime, timezone
from typing import Optional

from app.syslog_parser import SEVERIDADES

# Nombre del nivel de severidad según cada fabricante (índice = severidad 0..7).
NIVELES = {
    "Cisco":    ["emergencies", "alerts", "critical", "errors",
                 "warnings", "notifications", "informational", "debugging"],
    "Fortinet": ["emergency", "alert", "critical", "error",
                 "warning", "notification", "information", "debug"],
    "Huawei":   ["emergencies", "alert", "critical", "error",
                 "warning", "notification", "informational", "debugging"],
}


def _cabecera(c: str, titulo: str, p: dict) -> list[str]:
    """Encabezado común. 'c' es el símbolo de comentario del fabricante."""
    equipo = (f"{p['nombre']} ({p['ip_equipo']})" if p["nombre"]
              else "(genérico, sin equipo seleccionado)")
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    borde = c + " " + "=" * 68
    sev = p["severidad_max"]
    return [
        borde,
        f"{c} NOC Syslog Inteligente v0.2.0 - {titulo}",
        f"{c} Equipo: {equipo}   [DATOS SIMULADOS]",
        f"{c} Generada: {ahora}",
        f"{c} Colector: {p['colector']} puerto {p['puerto']}/{p['protocolo']}",
        f"{c} Envía severidades 0 a {sev} ({SEVERIDADES[0]} ... {SEVERIDADES[sev]}), "
        f"facility {p['facility']}",
        f"{c} PROPUESTA: revísala y aplícala tú, de forma manual y autorizada.",
        f"{c} No contiene contraseñas, tokens ni claves.",
        borde,
    ]


def _cisco(p: dict):
    c = "!"
    nivel = NIVELES["Cisco"][p["severidad_max"]]
    t = _cabecera(c, "Syslog para Cisco IOS / IOS-XE", p)
    t += [c, f"{c} --- 1. Hora confiable (NTP): sin hora sincronizada no hay correlación ---",
          "clock timezone COT -5"]
    if p["ntp"]:
        t.append(f"ntp server {p['ntp']}")
    else:
        t.append(f"{c} (no se indicó servidor NTP: configúralo antes de producción)")
    t += [
        "service timestamps log datetime msec show-timezone",
        c, f"{c} --- 2. Destino de los logs (colector NOC) ---",
        f"{c} Fuente autorizada: el colector identifica al equipo por su IP de origen",
        f"{c} y descarta todo lo que no esté en el inventario.",
        f"logging host {p['colector']} transport {p['protocolo']} port {p['puerto']}",
        f"{c} Envía los mensajes de severidad 0 a {p['severidad_max']} ({nivel} o más grave)",
        f"logging trap {nivel}",
        f"logging facility {p['facility']}",
        f"{c} IP de origen estable: usa una Loopback (ajusta el nombre a tu equipo)",
        "logging source-interface Loopback0",
        "logging on",
        c, f"{c} --- 3. Copia local y control de volumen ---",
        "logging buffered 16384 informational",
        f"{c} Opcional (confirma la sintaxis en tu versión): limita mensajes por segundo",
        f"{c} logging rate-limit all 100 except errors",
        c, f"{c} --- 4. Transporte seguro ---",
        f"{c} UDP no cifra ni garantiza entrega. Si tu versión lo soporta, usa TLS (RFC 5425).",
        f"{c} Consulta: Cisco, System Management Configuration Guide > System Message Logging.",
        c, f"{c} Guarda con 'write memory' solo después de verificar.",
    ]
    ver = [
        {"comando": "show logging",
         "esperado": f"Aparece el destino {p['colector']} con transport {p['protocolo']} "
                     f"port {p['puerto']} y el nivel {nivel}"},
    ]
    if p["ntp"]:
        ver.append({"comando": "show ntp status",
                    "esperado": "Debe decir 'Clock is synchronized'"})
    ver.append({"comando": "configure terminal  y luego  end",
                "esperado": ("Genera %SYS-5-CONFIG_I (severidad 5): debe llegar al NOC"
                             if p["severidad_max"] >= 5 else
                             f"Con severidad máxima {p['severidad_max']} ese aviso (5) no se envía; "
                             "usa un evento de severidad menor o igual")})
    return t, ver


def _fortinet(p: dict):
    c = "#"
    nivel = NIVELES["Fortinet"][p["severidad_max"]]
    modo = "udp" if p["protocolo"] == "udp" else "reliable"
    t = _cabecera(c, "Syslog para Fortinet FortiGate (FortiOS)", p)
    t += [c, f"{c} --- 1. Hora confiable (NTP) ---"]
    if p["ntp"]:
        t += ["config system ntp", "    set ntpsync enable", "    set type custom",
              "    config ntpserver", "        edit 1",
              f'            set server "{p["ntp"]}"', "        next", "    end", "end"]
    else:
        t.append(f"{c} (no se indicó servidor NTP: configúralo antes de producción)")
    t += [
        c, f"{c} --- 2. Destino de los logs (colector NOC) ---",
        f"{c} Fuente autorizada: el colector identifica al equipo por su IP de origen.",
        "config log syslogd setting",
        "    set status enable",
        f'    set server "{p["colector"]}"',
        f"    set mode {modo}",
        f"    set port {p['puerto']}",
        f"    set facility {p['facility']}",
    ]
    if p["ip_equipo"]:
        t.append(f"    {c} IP de origen (debe ser una IP del propio equipo)")
        t.append(f'    set source-ip "{p["ip_equipo"]}"')
    if modo == "reliable":
        t.append(f"    {c} Para cifrar (RFC 5425), si tu versión lo soporta: set enc-algorithm high")
    t += [
        "end",
        c, f"{c} --- 3. Qué severidades se envían ---",
        f"{c} Envía los mensajes de severidad 0 a {p['severidad_max']} ({nivel} o más grave)",
        "config log syslogd filter",
        f"    set severity {nivel}",
        "end",
        c, f"{c} Consulta: Fortinet, FortiGate CLI Reference (log syslogd setting / filter).",
    ]
    ver = [
        {"comando": "show log syslogd setting",
         "esperado": f"status enable, server {p['colector']}, mode {modo}, port {p['puerto']}"},
        {"comando": "show log syslogd filter", "esperado": f"severity {nivel}"},
        {"comando": "diagnose log test",
         "esperado": "Genera mensajes de prueba de varias severidades: deben llegar al NOC"},
        {"comando": f"execute ping {p['colector']}",
         "esperado": "Hay alcance de red hacia el colector"},
    ]
    return t, ver


def _huawei(p: dict):
    c = "#"
    nivel = NIVELES["Huawei"][p["severidad_max"]]
    t = _cabecera(c, "Syslog para Huawei VRP", p)
    t += ["system-view", c, f"{c} --- 1. Hora confiable (NTP) ---",
          "clock timezone COT minus 05:00:00"]
    if p["ntp"]:
        t.append(f"ntp-service unicast-server {p['ntp']}")
    else:
        t.append(f"{c} (no se indicó servidor NTP: configúralo antes de producción)")
    t += [
        "info-center timestamp log date",
        c, f"{c} --- 2. Destino de los logs (colector NOC) ---",
        f"{c} Fuente autorizada: el colector identifica al equipo por su IP de origen.",
        "info-center enable",
        f"info-center loghost {p['colector']} transport {p['protocolo']} "
        f"port {p['puerto']} facility {p['facility']}",
        f"{c} La sintaxis exacta puede variar según la versión de VRP: confirma con",
        f"{c} 'info-center loghost ?' antes de aplicar.",
        c, f"{c} --- 3. Qué severidades se envían ---",
        f"{c} Envía los mensajes de severidad 0 a {p['severidad_max']} ({nivel} o más grave)",
        f"info-center source default channel loghost log level {nivel}",
        "return",
        c, f"{c} Guarda con 'save' solo después de verificar (no se incluye a propósito).",
        f"{c} Consulta: Huawei, Command Reference > info-center loghost.",
    ]
    ver = [
        {"comando": "display info-center",
         "esperado": f"Information center enabled; loghost {p['colector']} puerto {p['puerto']}"},
        {"comando": "display ntp-service status",
         "esperado": "Debe indicar 'clock status: synchronized'"} if p["ntp"] else
        {"comando": "display clock", "esperado": "Hora y zona horaria correctas"},
        {"comando": "display logbuffer",
         "esperado": "Aparecen los mensajes recientes; entrar y salir de system-view genera uno"},
    ]
    return t, ver


GENERADORES = {"Cisco": _cisco, "Fortinet": _fortinet, "Huawei": _huawei}


def generar(marca: str, colector: str, puerto: int, protocolo: str,
            severidad_max: int, facility: str, ntp: Optional[str],
            nombre: Optional[str], ip_equipo: Optional[str]) -> dict:
    """Devuelve la configuración comentada y la lista de verificación."""
    # Defensa extra: aunque el nombre viene del inventario, se sanea.
    nombre_seguro = re.sub(r"[^A-Za-z0-9_.-]", "_", nombre) if nombre else None
    try:
        ip_ok = str(ipaddress.ip_address(ip_equipo)) if ip_equipo else None
    except ValueError:
        ip_ok = None
    p = {"colector": colector, "puerto": puerto, "protocolo": protocolo,
         "severidad_max": severidad_max, "facility": facility, "ntp": ntp,
         "nombre": nombre_seguro, "ip_equipo": ip_ok}
    lineas, verificacion = GENERADORES[marca](p)
    return {"configuracion": "\n".join(lineas) + "\n", "verificacion": verificacion}
