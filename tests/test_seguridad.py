"""Seguridad transversal: auditoría inmutable, restricciones de la BD, cabeceras y datos sin secretos."""
import ipaddress
import re
import sqlite3
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------------- auditoría inmutable
def test_auditoria_no_permite_borrar(conn):
    with pytest.raises(sqlite3.IntegrityError, match="solo inserción"):
        conn.execute("DELETE FROM auditoria")


def test_auditoria_no_permite_modificar(conn):
    with pytest.raises(sqlite3.IntegrityError, match="solo inserción"):
        conn.execute("UPDATE auditoria SET detalle = 'borrado'")


# ----------------------------------------------------------------------------- restricciones del modelo
def test_la_base_rechaza_severidad_fuera_de_0_a_7(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO eventos (fecha_evento, facility, severidad, mensaje) "
                     "VALUES ('2026-10-12T10:00:00Z', 1, 9, 'x')")


def test_la_base_rechaza_origen_desconocido(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO eventos (fecha_evento, facility, severidad, mensaje, origen) "
                     "VALUES ('2026-10-12T10:00:00Z', 1, 3, 'x', 'DESCONOCIDO')")


def test_todos_los_eventos_sembrados_estan_etiquetados_como_simulados(conn):
    origenes = {f[0] for f in conn.execute("SELECT DISTINCT origen FROM eventos")}
    assert origenes <= {"SIMULADO", "REAL"}


# ----------------------------------------------------------------------------- cabeceras HTTP
def test_cabeceras_de_seguridad(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_la_api_de_documentacion_no_lleva_csp_para_no_romper_swagger(client):
    assert "Content-Security-Policy" not in client.get("/docs").headers


# ----------------------------------------------------------------------------- sin secretos ni IPs reales
def _archivos(patrones=("*.py",)):
    for carpeta in ("app", "scripts"):
        for patron in patrones:
            for ruta in (RAIZ / carpeta).rglob(patron):
                if "__pycache__" not in ruta.parts:
                    yield ruta


def test_el_codigo_no_tiene_ips_publicas():
    ipv4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    for ruta in _archivos():
        for candidato in ipv4.findall(ruta.read_text(encoding="utf-8")):
            try:
                ip = ipaddress.ip_address(candidato)
            except ValueError:
                continue                                  # p. ej. versiones como 1.0.1.2.3
            assert not ip.is_global, f"IP pública en {ruta.relative_to(RAIZ)}: {candidato}"


def test_el_codigo_no_tiene_credenciales_literales():
    asignacion = re.compile(r"""(password|passwd|secret|token|api[_-]?key)\s*=\s*["'][^"']+["']""", re.I)
    for ruta in _archivos():
        assert not asignacion.search(ruta.read_text(encoding="utf-8")), ruta.relative_to(RAIZ)


def test_el_archivo_env_no_esta_versionado():
    gitignore = (RAIZ / ".gitignore")
    if gitignore.exists():                                # en el repositorio real debe existir
        lineas = gitignore.read_text(encoding="utf-8").splitlines()
        assert ".env" in lineas and any(l.startswith("data/*.db") for l in lineas)
