"""Consola simulada de SOLO LECTURA (estilo PuTTY).

Garantías:
  * NO abre ninguna conexión ni ejecuta nada en el sistema operativo: no hay
    subprocess, eval ni exec. Las respuestas son texto generado con datos del
    inventario y de los eventos guardados.
  * LISTA PERMITIDA (allowlist): solo se atiende un comando si coincide EXACTAMENTE
    con uno permitido para la marca del equipo. Todo lo demás se bloquea.
  * Las categorías de bloqueo (sensible, destructivo, modificación, acceso) solo sirven
    para explicar el motivo; la defensa real es la allowlist.
"""
import re
from datetime import datetime, timezone

from app.syslog_parser import SEVERIDADES, sanitizar

MAX_COMANDO = 120
# Encadenado (; & |), redirección (< >), sustitución (` $), barra invertida y control.
_META = re.compile(r"[;&|<>`$\\\x00-\x1f\x7f]")
AYUDA = {"help", "?", "ayuda"}


# ---------------------------------------------------------------- respuestas simuladas
def _reloj(ctx) -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC %a %b %d %Y")


def _eventos_texto(ctx) -> str:
    """Últimos eventos del equipo, como TEXTO PLANO (los logs son datos no confiables)."""
    if not ctx["eventos"]:
        return "(sin eventos registrados para este equipo)"
    filas = []
    for e in reversed(ctx["eventos"]):
        texto = sanitizar(e["mensaje"], 200).replace("\n", " ")
        filas.append(f"{e['fecha_evento']} [{SEVERIDADES[e['severidad']]}] {texto}")
    return "\n".join(filas)


def _logging(ctx) -> str:
    return ("Syslog logging: enabled (SIMULADO)\n"
            "Últimos eventos recibidos por el NOC para este equipo:\n" + _eventos_texto(ctx))


def _ntp(ctx) -> str:
    return "Clock is synchronized, stratum 3, reference is 192.0.2.1 (simulado)"


# --- Cisco
def _cisco_version(ctx) -> str:
    d = ctx["disp"]
    return (f"Cisco IOS XE Software, Version {d['version']}   [SIMULADO]\n"
            f"Hostname: {d['nombre']}\nModel: {d['modelo']}\n"
            "System uptime is 14 days, 3 hours, 22 minutes (simulado)")


def _cisco_interfaces(ctx) -> str:
    d = ctx["disp"]
    return ("Interface              IP-Address      OK? Method Status      Protocol\n"
            f"Vlan1                  {d['ip']:<15} YES manual up          up\n"
            "GigabitEthernet1/0/1   unassigned      YES unset  up          up\n"
            "GigabitEthernet1/0/2   unassigned      YES unset  down        down\n"
            "(salida simulada)")


# --- Fortinet
def _fgt_status(ctx) -> str:
    d = ctx["disp"]
    return (f"Version: {d['modelo']} {d['version']}   [SIMULADO]\n"
            f"Hostname: {d['nombre']}\nSerial-Number: SIMULADO-0000\n"
            "Operation Mode: NAT\nVirtual domain configuration: disable")


def _fgt_perf(ctx) -> str:
    return ("CPU states: 4% user 2% system 0% nice 94% idle\n"
            "Memory: 8174180k total, 3015020k used (36.9%)\n"
            "Uptime: 14 days, 3 hours, 22 minutes (simulado)")


def _fgt_syslog_setting(ctx) -> str:
    return ("config log syslogd setting\n    set status enable\n"
            '    set server "192.0.2.50"\n    set mode udp\n    set port 514\n'
            "    set facility local6\nend\n(salida simulada)")


def _fgt_ntp(ctx) -> str:
    return "synchronized: yes, ntpsync: enabled, server: 192.0.2.1 (simulado)"


# --- Huawei
def _hw_version(ctx) -> str:
    d = ctx["disp"]
    return ("Huawei Versatile Routing Platform Software   [SIMULADO]\n"
            f"VRP (R) software, Version {d['version']}\n"
            f"HUAWEI {d['modelo']} Routing Switch uptime is 14 days, 3 hours, 22 minutes")


def _hw_ntp(ctx) -> str:
    return "clock status: synchronized, stratum: 3, reference clock ID: 192.0.2.1 (simulado)"


def _hw_info_center(ctx) -> str:
    return ("Information Center: enabled\n"
            "Log host: 192.0.2.50, port 514, facility local6, transport udp\n"
            "Channel 2 (loghost): level informational\n(salida simulada)")


def _hw_interfaces(ctx) -> str:
    d = ctx["disp"]
    return ("Interface                 IP Address/Mask      Physical   Protocol\n"
            f"Vlanif1                   {d['ip']}/24   up         up\n"
            "GigabitEthernet0/0/1      unassigned           up         up\n(salida simulada)")


# ---------------------------------------------------------------- lista PERMITIDA
PERMITIDOS = {
    "Cisco": {
        "show version": _cisco_version,
        "show clock": _reloj,
        "show logging": _logging,
        "show ntp status": _ntp,
        "show ip interface brief": _cisco_interfaces,
    },
    "Fortinet": {
        "get system status": _fgt_status,
        "get system performance status": _fgt_perf,
        "show log syslogd setting": _fgt_syslog_setting,
        "diagnose sys ntp status": _fgt_ntp,
        "execute log display": _logging,
    },
    "Huawei": {
        "display version": _hw_version,
        "display clock": _reloj,
        "display logbuffer": _logging,
        "display ntp-service status": _hw_ntp,
        "display ip interface brief": _hw_interfaces,
        "display info-center": _hw_info_center,
    },
    "Otro": {
        "show version": _cisco_version,
        "show clock": _reloj,
        "show logging": _logging,
    },
}

# ---------------------------------------------------------------- categorías de BLOQUEO
# Se evalúan solo cuando el comando NO está en la lista permitida.
BLOQUEOS = [
    ("sensible", re.compile(
        r"^(show|display|get)\s+(running-config|startup-config|current-configuration|"
        r"saved-configuration|full-configuration|tech-support)\b", re.I),
     "Puede exponer credenciales, claves o secretos"),
    ("destructivo", re.compile(
        r"^(reload|reboot|restart|halt|erase|format|factory-reset|reset)\b|"
        r"^write\s+erase\b|"
        r"^execute\s+(reboot|shutdown|factory-reset|formatlogdisk|restore|backup)\b", re.I),
     "Reinicia, borra o restaura el equipo"),
    ("modificacion", re.compile(
        r"^(conf(ig(ure)?)?|system-view|edit|set|unset|append|delete|no|undo|copy|write|"
        r"save|commit|interface|username|password|ip|logging|info-center|ntp|"
        r"ntp-service|clock|shutdown)\b", re.I),
     "Modifica la configuración del equipo"),
    ("acceso", re.compile(
        r"^(enable|su|sudo|ssh|telnet|ftp|tftp|scp|sftp|ping|traceroute|tracert)\b", re.I),
     "Eleva privilegios o abre conexiones hacia otros sistemas"),
]


def _visible(crudo: str) -> str:
    """Versión del comando apta para mostrar y registrar."""
    return sanitizar(crudo, 200).replace("\n", "⏎").replace("\r", "").replace("\t", " ")


def _ayuda(marca: str) -> str:
    lista = "\n".join(f"  {c}" for c in PERMITIDOS.get(marca, PERMITIDOS["Otro"]))
    return (f"Consola SIMULADA de solo lectura. Comandos permitidos en {marca}:\n{lista}\n"
            "  clear   (limpia la pantalla)\n"
            "Todo lo demás se bloquea y queda registrado en auditoría.")


def _bloqueado(base: dict, categoria: str, motivo: str) -> dict:
    return {**base, "permitido": False, "categoria": categoria, "motivo": motivo,
            "salida": (f"% Comando BLOQUEADO ({categoria}): {motivo}.\n"
                       "% La consola es de solo lectura. Los cambios exigen propuesta, "
                       "revisión humana y aprobación.")}


def responder(disp: dict, crudo: str, eventos: list) -> dict:
    """Evalúa un comando y devuelve {permitido, categoria, motivo, salida, comando}."""
    marca = disp["marca"]
    base = {"comando": _visible(crudo)}

    # 1) Controles sobre el texto ORIGINAL (antes de normalizar espacios y saltos).
    if len(crudo) > MAX_COMANDO:
        return _bloqueado(base, "longitud", f"Supera {MAX_COMANDO} caracteres")
    if _META.search(crudo):
        return _bloqueado(base, "encadenado",
                          "Contiene caracteres de encadenado, redirección o control")

    norm = " ".join(crudo.split()).lower()
    if not norm:
        return _bloqueado(base, "vacio", "Comando vacío")
    if norm in AYUDA:
        return {**base, "permitido": True, "categoria": "ayuda", "motivo": None,
                "salida": _ayuda(marca)}

    # 2) LISTA PERMITIDA: coincidencia exacta con un comando de la marca.
    permitidos = PERMITIDOS.get(marca, PERMITIDOS["Otro"])
    if norm in permitidos:
        salida = permitidos[norm]({"disp": disp, "eventos": eventos})
        return {**base, "permitido": True, "categoria": "permitido", "motivo": None,
                "salida": salida}

    # 3) No permitido: se clasifica solo para explicar el motivo.
    for categoria, patron, motivo in BLOQUEOS:
        if patron.search(norm):
            return _bloqueado(base, categoria, motivo)
    return _bloqueado(base, "no_permitido",
                      f"No está en la lista de comandos permitidos para {marca}")