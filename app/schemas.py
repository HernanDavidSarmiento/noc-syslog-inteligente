"""Esquemas de validación (Pydantic). Todo dato de entrada se valida aquí."""
import ipaddress
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

Marca = Literal["Cisco", "Fortinet", "Huawei", "Otro"]
Estado = Literal["activo", "inactivo", "mantenimiento"]


def validar_ip(valor: str) -> str:
    """Acepta solo IPs bien formadas que NO sean públicas.

    Política del proyecto: sin IPs reales de producción. Se permiten rangos
    privados (RFC 1918) y de documentación (RFC 5737).
    """
    try:
        ip = ipaddress.ip_address(valor.strip())
    except ValueError:
        raise ValueError("IP inválida")
    if ip.is_global:
        raise ValueError(
            "IP pública no permitida: usa rangos privados o de documentación "
            "(192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24)")
    return str(ip)


class DispositivoCampos(BaseModel):
    nombre: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    ip: str
    marca: Marca
    modelo: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    ubicacion: str = Field(min_length=1, max_length=128)
    estado: Estado = "activo"


class DispositivoCrear(DispositivoCampos):
    @field_validator("ip")
    @classmethod
    def _ip(cls, v: str) -> str:
        return validar_ip(v)


class DispositivoActualizar(BaseModel):
    """Todos los campos son opcionales: solo se modifican los enviados."""
    nombre: Optional[str] = Field(default=None, min_length=3, max_length=64,
                                  pattern=r"^[A-Za-z0-9_.-]+$")
    ip: Optional[str] = None
    marca: Optional[Marca] = None
    modelo: Optional[str] = Field(default=None, min_length=1, max_length=64)
    version: Optional[str] = Field(default=None, min_length=1, max_length=64)
    ubicacion: Optional[str] = Field(default=None, min_length=1, max_length=128)
    estado: Optional[Estado] = None

    @field_validator("ip")
    @classmethod
    def _ip(cls, v: Optional[str]) -> Optional[str]:
        return validar_ip(v) if v is not None else v


class DispositivoSalida(DispositivoCampos):
    id: int
    fecha_actualizacion: str