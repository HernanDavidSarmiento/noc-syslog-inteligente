"""Fase 5: consola simulada de solo lectura con lista permitida."""
import pytest

from app.consola import responder

CISCO = {"nombre": "SIM-CISCO-CORE-01", "ip": "192.0.2.10", "marca": "Cisco", "modelo": "Catalyst 9300", "version": "IOS-XE 17.9"}
FORTI = {"nombre": "SIM-FGT-FW-01", "ip": "198.51.100.1", "marca": "Fortinet", "modelo": "FortiGate 100F", "version": "FortiOS 7.4"}
HUAWEI = {"nombre": "SIM-HUAWEI-SW-01", "ip": "203.0.113.20", "marca": "Huawei", "modelo": "S5735-L", "version": "VRP V200R021"}
EVENTOS = [{"fecha_evento": "2026-10-09T08:15:02Z", "severidad": 3, "mensaje": "login fallido <b>x</b>"}]


@pytest.mark.parametrize("disp, cmd", [
    (CISCO, "show version"), (CISCO, "SHOW   CLOCK"), (CISCO, "show logging"),
    (FORTI, "get system status"), (FORTI, "execute log display"),
    (HUAWEI, "display version"), (HUAWEI, "display logbuffer"),
])
def test_comandos_permitidos_responden(disp, cmd):
    r = responder(disp, cmd, EVENTOS)
    assert r["permitido"] is True and r["salida"]


@pytest.mark.parametrize("disp, cmd, categoria", [
    (CISCO, "configure terminal", "modificacion"),
    (CISCO, "conf t", "modificacion"),
    (CISCO, "reload", "destructivo"),
    (CISCO, "write erase", "destructivo"),
    (CISCO, "show running-config", "sensible"),
    (CISCO, "ping 192.0.2.1", "acceso"),
    (CISCO, "enable", "acceso"),
    (FORTI, "execute reboot", "destructivo"),
    (FORTI, "config system global", "modificacion"),
    (FORTI, "show full-configuration", "sensible"),
    (HUAWEI, "system-view", "modificacion"),
    (HUAWEI, "reboot", "destructivo"),
    (HUAWEI, "display current-configuration", "sensible"),
])
def test_comandos_peligrosos_se_bloquean_con_su_categoria(disp, cmd, categoria):
    r = responder(disp, cmd, EVENTOS)
    assert r["permitido"] is False and r["categoria"] == categoria


@pytest.mark.parametrize("cmd", [
    "show version; reload", "show version && reload", "show version | include x",
    "show version\nreload", "show version `reboot`", "show version $(reload)", "show version > flash:x",
])
def test_encadenado_y_metacaracteres_se_bloquean(cmd):
    r = responder(CISCO, cmd, EVENTOS)
    assert r["permitido"] is False and r["categoria"] == "encadenado"


def test_comando_de_otra_marca_no_esta_permitido():
    r = responder(FORTI, "show version", EVENTOS)
    assert r["permitido"] is False and r["categoria"] == "no_permitido"


def test_comando_desconocido_se_bloquea_por_defecto():
    assert responder(CISCO, "comando-inventado --ahora", EVENTOS)["categoria"] == "no_permitido"


def test_comando_demasiado_largo():
    assert responder(CISCO, "show version " + "A" * 200, EVENTOS)["categoria"] == "longitud"


def test_show_logging_muestra_el_log_como_texto_plano():
    r = responder(CISCO, "show logging", EVENTOS)
    assert "<b>x</b>" in r["salida"]            # sin escapar ni interpretar: es un dato


# ----------------------------------------------------------------------------- por la API (el backend decide)
def _id(client, nombre):
    return next(d["id"] for d in client.get("/api/dispositivos").json() if d["nombre"] == nombre)


def test_api_audita_comandos_permitidos_y_bloqueados(client, auditoria_de):
    disp_id = _id(client, "SIM-CISCO-CORE-01")
    ok = client.post("/api/consola/ejecutar", json={"dispositivo_id": disp_id, "comando": "show version"}).json()
    mal = client.post("/api/consola/ejecutar", json={"dispositivo_id": disp_id, "comando": "reload"}).json()
    assert ok["permitido"] and not mal["permitido"]
    assert auditoria_de("consola_comando_permitido", disp_id)
    assert "destructivo" in auditoria_de("consola_comando_bloqueado", disp_id)[0]["detalle"]


def test_api_bloquea_encadenado_aunque_no_pase_por_la_pantalla(client):
    disp_id = _id(client, "SIM-CISCO-CORE-01")
    r = client.post("/api/consola/ejecutar", json={"dispositivo_id": disp_id, "comando": "show version\nreload"})
    assert r.status_code == 200 and r.json()["categoria"] == "encadenado"


def test_api_equipo_inexistente_e_inactivo(client, crear_disp):
    assert client.post("/api/consola/ejecutar", json={"dispositivo_id": 999999, "comando": "help"}).status_code == 404
    inactivo = crear_disp(estado="inactivo")
    assert client.post("/api/consola/ejecutar", json={"dispositivo_id": inactivo["id"], "comando": "help"}).status_code == 409
