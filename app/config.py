"""Configuración central. Lee variables de entorno; sin secretos en el código."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.getenv("NOC_DB_PATH", BASE_DIR / "data" / "noc_syslog.db"))
SYSLOG_UDP_PORT = int(os.getenv("NOC_SYSLOG_UDP_PORT", "5514"))
ENTORNO = os.getenv("NOC_ENV", "desarrollo")

VERSION = "0.2.0"