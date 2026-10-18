"""Fase 2: CRUD del inventario con validación y auditoría."""
BASE = {"nombre": "SIM-INV-001", "ip": "192.0.2.77", "marca": "Cisco", "modelo": "Catalyst 2960X",
        "version": "IOS 15.2", "ubicacion": "Piso 2 - Acceso SIMULADO", "estado": "activo"}


def test_crud_completo_con_auditoria(client, auditoria_de):
    r = client.post("/api/dispositivos", json=BASE)
    assert r.status_code == 201
    disp = r.json()
    assert client.get(f"/api/dispositivos/{disp['id']}").json()["nombre"] == "SIM-INV-001"

    r = client.patch(f"/api/dispositivos/{disp['id']}", json={"estado": "mantenimiento"})
    assert r.status_code == 200 and r.json()["estado"] == "mantenimiento"

    assert client.delete(f"/api/dispositivos/{disp['id']}").status_code == 204
    assert client.get(f"/api/dispositivos/{disp['id']}").status_code == 404

    assert auditoria_de("crear_dispositivo", disp["id"])
    editar = auditoria_de("editar_dispositivo", disp["id"])[0]
    assert '"antes": "activo"' in editar["detalle"] and '"despues": "mantenimiento"' in editar["detalle"]
    assert auditoria_de("eliminar_dispositivo", disp["id"])


def test_nombre_duplicado_devuelve_409(client):
    cuerpo = {**BASE, "nombre": "SIM-INV-DUP"}
    assert client.post("/api/dispositivos", json=cuerpo).status_code == 201
    assert client.post("/api/dispositivos", json=cuerpo).status_code == 409


def test_ip_publica_no_se_acepta(client):
    r = client.post("/api/dispositivos", json={**BASE, "nombre": "SIM-INV-PUB", "ip": "8.8.8.8"})
    assert r.status_code == 422 and "pública" in r.text


def test_ip_mal_formada_no_se_acepta(client):
    assert client.post("/api/dispositivos", json={**BASE, "nombre": "SIM-INV-BAD", "ip": "999.1.1.1"}).status_code == 422


def test_marca_y_nombre_validos(client):
    assert client.post("/api/dispositivos", json={**BASE, "nombre": "SIM-INV-MARCA", "marca": "TP-Link"}).status_code == 422
    assert client.post("/api/dispositivos", json={**BASE, "nombre": "mal nombre; DROP TABLE"}).status_code == 422


def test_listado_filtra_por_marca(client):
    cisco = client.get("/api/dispositivos", params={"marca": "Cisco"}).json()
    assert cisco and all(d["marca"] == "Cisco" for d in cisco)


def test_patch_sin_cambios_es_400(client, crear_disp):
    d = crear_disp()
    assert client.patch(f"/api/dispositivos/{d['id']}", json={}).status_code == 400


def test_intento_de_inyeccion_sql_en_filtro_no_rompe_nada(client):
    r = client.get("/api/dispositivos", params={"marca": "Cisco' OR '1'='1"})
    assert r.status_code == 422          # la marca está en una lista cerrada
