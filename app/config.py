"""Configuración central. Lee variables de entorno; sin secretos en el código."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.getenv("NOC_DB_PATH", BASE_DIR / "data" / "noc_syslog.db"))
ENTORNO = os.getenv("NOC_ENV", "desarrollo")

# --- Syslog ---
SYSLOG_UDP_PORT = int(os.getenv("NOC_SYSLOG_UDP_PORT", "5514"))
# Por defecto solo escucha en loopback: no se expone a la red sin decidirlo.
SYSLOG_BIND_HOST = os.getenv("NOC_SYSLOG_BIND_HOST", "127.0.0.1")
# Control de tormentas: máximo de eventos almacenados por equipo y por minuto.
SYSLOG_MAX_POR_MINUTO = int(os.getenv("NOC_SYSLOG_MAX_POR_MINUTO", "60"))
# Deduplicación: ventana (segundos) en que un mensaje idéntico cuenta como repetido.
SYSLOG_VENTANA_DEDUP = int(os.getenv("NOC_SYSLOG_VENTANA_DEDUP", "60"))

VERSION = "0.2.0"