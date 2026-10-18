"""Esquemas de validación para incidentes."""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

EstadoIncidente = Literal["abierto", "asignado", "en_progreso", "resuelto", "cerrado"]


class IncidenteCrear(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    titulo: str = Field(min_length=3, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=2000)
    severidad: int = Field(ge=0, le=7)
    dispositivo_id: Optional[int] = Field(default=None, ge=1)
    asignado_a: Optional[str] = Field(default=None, min_length=2, max_length=64)
    evento_ids: list[int] = Field(default_factory=list, max_length=100)


class IncidenteActualizar(BaseModel):
    """Todos los campos son opcionales: solo se modifican los enviados."""
    model_config = ConfigDict(str_strip_whitespace=True)
    titulo: Optional[str] = Field(default=None, min_length=3, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=2000)
    severidad: Optional[int] = Field(default=None, ge=0, le=7)
    estado: Optional[EstadoIncidente] = None
    asignado_a: Optional[str] = Field(default=None, min_length=2, max_length=64)
    notas_cierre: Optional[str] = Field(default=None, max_length=2000)


class VincularEventos(BaseModel):
    evento_ids: list[int] = Field(min_length=1, max_length=100)