"""Consola simulada de solo lectura. Cada comando queda en auditoría."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.auditoria import registrar
from app.consola import responder
from app.database import db_session

router = APIRouter(prefix="/api/consola", tags=["Consola simulada"])


class ComandoSolicitud(BaseModel):
    dispositivo_id: int = Field(ge=1)
    comando: str = Field(min_length=1, max_length=256)


@router.post("/ejecutar")
def ejecutar(datos: ComandoSolicitud):
    """Evalúa un comando. Un comando bloqueado NO es un error HTTP: es un resultado."""
    with db_session() as conn:
        disp = conn.execute(
            "SELECT id, nombre, ip, marca, modelo, version, estado "
            "FROM dispositivos WHERE id = ?", (datos.dispositivo_id,)).fetchone()
        if disp is None:
            raise HTTPException(404, "Dispositivo no encontrado")
        if disp["estado"] == "inactivo":
            raise HTTPException(409, "Dispositivo inactivo: la consola simulada no tiene sesión")

        eventos = [dict(f) for f in conn.execute(
            "SELECT fecha_evento, severidad, mensaje FROM eventos WHERE dispositivo_id = ? "
            "ORDER BY fecha_evento DESC, id DESC LIMIT 10", (disp["id"],)).fetchall()]

        r = responder(dict(disp), datos.comando, eventos)
        registrar(conn,
                  "consola_comando_permitido" if r["permitido"] else "consola_comando_bloqueado",
                  "dispositivo", disp["id"],
                  json.dumps({"comando": r["comando"], "categoria": r["categoria"]},
                             ensure_ascii=False))
        return r