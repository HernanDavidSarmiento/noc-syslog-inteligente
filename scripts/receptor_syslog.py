"""Receptor Syslog UDP (desarrollo).  Uso:  python -m scripts.receptor_syslog

- Escucha por defecto en 127.0.0.1:5514 (UDP/514 exige privilegios elevados).
- Paquetes desde loopback se marcan SIMULADO y pueden identificarse por el
  nombre del host dentro del mensaje. Paquetes desde otras IPs se marcan REAL
  y SOLO se aceptan si la IP de origen está en el inventario.
"""
import socket
from app.config import SYSLOG_BIND_HOST, SYSLOG_UDP_PORT
from app.database import db_session, init_schema
from app.syslog_engine import procesar_mensaje

TAM_MAX = 4096
LOOPBACK = {"127.0.0.1", "::1"}


def main() -> None:
    init_schema()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SYSLOG_BIND_HOST, SYSLOG_UDP_PORT))
    print(f"Escuchando Syslog UDP en {SYSLOG_BIND_HOST}:{SYSLOG_UDP_PORT} (Ctrl+C para salir)")
    try:
        while True:
            try:
                datos, (ip, _puerto) = sock.recvfrom(TAM_MAX)
            except OSError:
                print("[descartado ] datagrama demasiado grande o error de socket")
                continue
            crudo = datos.decode("utf-8", errors="replace")
            local = ip in LOOPBACK
            try:
                with db_session() as conn:
                    r = procesar_mensaje(
                        conn, crudo,
                        origen="SIMULADO" if local else "REAL",
                        ip_origen=ip, permitir_hostname=local)
            except Exception as e:  # el receptor no debe caerse por un mensaje
                print(f"[error      ] {type(e).__name__}: {e}")
                continue
            print(f"[{r['resultado']:<11}] sev={r.get('severidad', '-')} "
                  f"host={r.get('host', '-')} {r.get('motivo', '')}")
    except KeyboardInterrupt:
        print("\nReceptor detenido.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()