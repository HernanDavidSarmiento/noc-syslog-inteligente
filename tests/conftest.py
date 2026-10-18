"""Configuración de las pruebas.

Las pruebas usan una base de datos TEMPORAL (nunca tocan data/noc_syslog.db) y datos
SIMULADOS: IPs de documentación (RFC 5737) y nombres que empiezan por SIM- o TEST-.
La variable de entorno debe fijarse ANTES de importar la aplicación.
"""
import itertools
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="noc_test_"))
os.environ["NOC_DB_PATH"] = str(_TMP / "test.db")

import pytest                                   # noqa: E402
from fastapi.testclient import TestClient       # noqa: E402

_contador = itertools.count(1)


@pytest.fixture(scope="session")
def client():
    from app.main import app
    from scripts.init_db import sembrar_datos
    with TestClient(app) as c:                   # el 'lifespan' crea el esquema
        sembrar_datos()                          # 3 equipos y 5 eventos SIMULADOS
        yield c


@pytest.fixture()
def conn(client):
    from app.database import get_connection
    c = get_connection()
    yield c
    c.close()


@pytest.fixture()
def crear_disp(client):
    """Fábrica de dispositivos únicos: crear_disp(marca='Cisco', estado='activo')."""
    def _crear(marca="Cisco", estado="activo", nombre=None):
        n = next(_contador)
        cuerpo = {"nombre": nombre or f"TEST-DEV-{n:03d}", "ip": f"198.51.100.{n}", "marca": marca,
                  "modelo": "Modelo-Test", "version": "1.0", "ubicacion": "Laboratorio SIMULADO",
                  "estado": estado}
        r = client.post("/api/dispositivos", json=cuerpo)
        assert r.status_code == 201, r.text
        return r.json()
    return _crear


@pytest.fixture()
def auditoria_de(conn):
    """auditoria_de('accion_x') -> filas de auditoría con esa acción (más recientes primero)."""
    def _consulta(accion, entidad_id=None):
        sql, params = "SELECT * FROM auditoria WHERE accion = ?", [accion]
        if entidad_id is not None:
            sql += " AND entidad_id = ?"
            params.append(entidad_id)
        return conn.execute(sql + " ORDER BY id DESC", params).fetchall()
    return _consulta
