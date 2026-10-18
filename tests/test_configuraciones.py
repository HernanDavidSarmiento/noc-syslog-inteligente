"""Fase 5: generador de configuraciones Syslog (solo texto, validado)."""
import pytest

BASE = {"colector_ip": "192.0.2.50"}


def _gen(client, **extra):
    return client.post("/api/configuraciones/syslog", json={**BASE, **extra})


def test_cisco_incluye_destino_nivel_y_comentarios(client):
    r = _gen(client, marca="Cisco", severidad_max=6)
    assert r.status_code == 200
    cfg = r.json()["configuracion"]
    assert "logging host 192.0.2.50 transport udp port 514" in cfg
    assert "logging trap informational" in cfg and "logging facility local6" in cfg
    assert cfg.count("!") > 10                                   # configuración comentada
    assert r.json()["verificacion"]


def test_fortinet_tcp_con_severidad_critica(client):
    cfg = _gen(client, marca="Fortinet", protocolo="tcp", severidad_max=2).json()["configuracion"]
    assert 'set server "192.0.2.50"' in cfg and "set mode reliable" in cfg and "set severity critical" in cfg


def test_huawei(client):
    cfg = _gen(client, marca="Huawei", facility="local3").json()["configuracion"]
    assert "info-center loghost 192.0.2.50 transport udp port 514 facility local3" in cfg


@pytest.mark.parametrize("marca", ["Cisco", "Fortinet", "Huawei"])
def test_ninguna_configuracion_contiene_secretos(client, marca):
    cfg = _gen(client, marca=marca).json()["configuracion"].lower()
    # Se revisan solo las líneas de comandos: los comentarios pueden mencionar la palabra "tokens".
    comandos = [l for l in cfg.splitlines() if l.strip() and not l.strip().startswith(("!", "#"))]
    for linea in comandos:
        for prohibido in ("password", "secret", "token", "community", "key "):
            assert prohibido not in linea, linea


def test_colector_publico_se_rechaza(client):
    assert _gen(client, marca="Cisco", colector_ip="8.8.8.8").status_code == 422


@pytest.mark.parametrize("ip", ["192.0.2.50\nreload", "192.0.2.50; reload", "192.0.2.50 reload", "$(reload)"])
def test_no_se_pueden_colar_comandos_por_la_ip(client, ip):
    assert _gen(client, marca="Cisco", colector_ip=ip).status_code == 422


def test_valores_fuera_de_lista_se_rechazan(client):
    assert _gen(client, marca="Cisco", facility="kern").status_code == 422
    assert _gen(client, marca="Cisco", protocolo="icmp").status_code == 422
    assert _gen(client, marca="Cisco", severidad_max=9).status_code == 422
    assert _gen(client, marca="Cisco", puerto=70000).status_code == 422
    assert _gen(client, marca="MikroTik").status_code == 422


def test_la_marca_debe_coincidir_con_el_equipo(client):
    cisco = next(d for d in client.get("/api/dispositivos").json() if d["nombre"] == "SIM-CISCO-CORE-01")
    assert _gen(client, marca="Huawei", dispositivo_id=cisco["id"]).status_code == 422
    r = _gen(client, marca="Cisco", dispositivo_id=cisco["id"])
    assert r.status_code == 200 and "SIM-CISCO-CORE-01" in r.json()["configuracion"]


def test_la_generacion_queda_auditada(client, auditoria_de):
    _gen(client, marca="Cisco")
    assert auditoria_de("generar_configuracion")
