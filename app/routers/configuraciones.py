"""Generador de configuraciones Syslog. Solo genera texto: no toca ningún equipo."""
import json
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auditoria import registrar
from app.config_syslog import generar
from app.database import db_session
from app.schemas import validar_ip

router = APIRouter(prefix="/api/configuraciones", tags=["Configuraciones Syslog"])

Facility = Literal["local0", "local1", "local2", "local3",
                   "local4", "local5", "local6", "local7"]


class ConfigSyslogSolicitud(BaseModel):
    marca: Literal["Cisco", "Fortinet", "Huawei"]
    colector_ip: str
    puerto: int = Field(default=514, ge=1, le=65535)
    protocolo: Literal["udp", "tcp"] = "udp"
    severidad_max: int = Field(default=6, ge=0, le=7,
                               description="Se envían severidades de 0 hasta este valor")
    facility: Facility = "local6"
    ntp_ip: Optional[str] = None
    dispositivo_id: Optional[int] = Field(default=None, ge=1)

    @field_validator("colector_ip")
    @classmethod
    def _colector(cls, v: str) -> str:
        return validar_ip(v)          # rechaza IPs públicas

    @field_validator("ntp_ip")
    @classmethod
    def _ntp(cls, v: Optional[str]) -> Optional[str]:
        return validar_ip(v) if v else None


@router.post("/syslog")
def generar_syslog(datos: ConfigSyslogSolicitud):
    nombre = ip_equipo = None
    with db_session() as conn:
        if datos.dispositivo_id is not None:
            d = conn.execute("SELECT nombre, ip, marca FROM dispositivos WHERE id = ?",
                             (datos.dispositivo_id,)).fetchone()
            if d is None:
                raise HTTPException(404, "Dispositivo no encontrado")
            if d["marca"] != datos.marca:
                raise HTTPException(422, f"La marca elegida no coincide con la del equipo ({d['marca']})")
            nombre, ip_equipo = d["nombre"], d["ip"]

        resultado = generar(datos.marca, datos.colector_ip, datos.puerto, datos.protocolo,
                            datos.severidad_max, datos.facility, datos.ntp_ip, nombre, ip_equipo)
        registrar(conn, "generar_configuracion", "dispositivo", datos.dispositivo_id,
                  json.dumps({"marca": datos.marca, "colector": datos.colector_ip,
                              "severidad_max": datos.severidad_max,
                              "facility": datos.facility, "protocolo": datos.protocolo}))
    return {"marca": datos.marca, "equipo": nombre, **resultado}