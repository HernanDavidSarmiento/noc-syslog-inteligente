"""Fase 4: creación, asignación, seguimiento y cierre de incidentes (reglas en el backend)."""


def _crear(client, **extra):
    r = client.post("/api/incidentes", json={"titulo": "Fallas de login repetidas", "severidad": 3, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_ciclo_completo_hasta_el_cierre(client, auditoria_de):
    inc = _crear(client)
    assert inc["estado"] == "abierto"

    r = client.patch(f"/api/incidentes/{inc['id']}", json={"asignado_a": "Ana Pérez"})
    assert r.json()["estado"] == "asignado"                       # asignar abre el seguimiento

    for nuevo in ("en_progreso", "resuelto"):
        assert client.patch(f"/api/incidentes/{inc['id']}", json={"estado": nuevo}).json()["estado"] == nuevo

    r = client.patch(f"/api/incidentes/{inc['id']}", json={"estado": "cerrado", "notas_cierre": "Se bloqueó la IP origen"})
    assert r.status_code == 200 and r.json()["estado"] == "cerrado" and r.json()["fecha_cierre"]

    detalle = client.get(f"/api/incidentes/{inc['id']}").json()
    assert [h["accion"] for h in detalle["historial"]][0] == "crear_incidente"
    assert auditoria_de("cerrar_incidente", inc["id"])


def test_no_se_pasa_a_en_progreso_sin_responsable(client):
    inc = _crear(client)
    r = client.patch(f"/api/incidentes/{inc['id']}", json={"estado": "en_progreso"})
    assert r.status_code == 422 and "responsable" in r.text


def test_cierre_exige_notas(client):
    inc = _crear(client)
    r = client.patch(f"/api/incidentes/{inc['id']}", json={"estado": "cerrado"})
    assert r.status_code == 422 and "notas" in r.text.lower()


def test_transicion_no_permitida(client):
    inc = _crear(client)
    r = client.patch(f"/api/incidentes/{inc['id']}", json={"estado": "resuelto"})
    assert r.status_code == 409


def test_incidente_cerrado_no_se_modifica(client):
    inc = _crear(client)
    client.patch(f"/api/incidentes/{inc['id']}", json={"estado": "cerrado", "notas_cierre": "Falsa alarma"})
    assert client.patch(f"/api/incidentes/{inc['id']}", json={"titulo": "Otro título"}).status_code == 409


def test_incidente_desde_evento_toma_el_equipo(client):
    evento = client.get("/api/eventos", params={"severidad_max": 2}).json()[0]
    inc = _crear(client, evento_ids=[evento["id"]])
    assert inc["dispositivo_id"] == evento["dispositivo_id"] and inc["eventos"] == 1


def test_evento_inexistente_es_404(client):
    r = client.post("/api/incidentes", json={"titulo": "Prueba", "severidad": 4, "evento_ids": [999999]})
    assert r.status_code == 404


def test_severidad_de_incidente_en_rango(client):
    assert client.post("/api/incidentes", json={"titulo": "Prueba", "severidad": 8}).status_code == 422
