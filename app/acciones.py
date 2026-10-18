"""Reglas del flujo de acciones propuestas (política de defensa frente a agentes de IA).

Flujo obligatorio:
  Evento detectado -> Validación -> Propuesta -> Revisión humana -> Aprobación ->
  Ejecución autorizada -> Verificación -> Auditoría

Principios:
  * Lista PERMITIDA de acciones: lo que no está en el catálogo se rechaza.
  * Parámetros validados con esquemas estrictos (sin campos extra, solo tipos simples).
  * Los textos libres (motivo, título) son datos NO confiables: se escanean y se rechazan
    si parecen una orden dirigida a una IA; nunca se ejecutan.
  * Separación de funciones: quien propone no puede aprobar; un agente de IA o el
    sistema nunca pueden revisar ni aprobar.
  * Solo una acción APROBADA puede ejecutarse, y la ejecución es simulada y reversible.
  * Cada paso (también los intentos denegados) queda en la auditoría de solo inserción.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ParamsDispositivo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dispositivo_id: int = Field(ge=1)


class ParamsIncidente(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    titulo: str = Field(min_length=3, max_length=120)
    severidad: int = Field(ge=0, le=7)
    dispositivo_id: Optional[int] = Field(default=None, ge=1)


# Catálogo de acciones permitidas. Cualquier otra se rechaza.
CATALOGO = {
    "poner_dispositivo_en_mantenimiento": {
        "descripcion": "Cambia el estado de un equipo del inventario a 'mantenimiento' (reversible).",
        "riesgo": "bajo", "modelo": ParamsDispositivo,
        "ejemplo": {"dispositivo_id": 1}},
    "reactivar_dispositivo": {
        "descripcion": "Devuelve un equipo del inventario al estado 'activo' (reversible).",
        "riesgo": "bajo", "modelo": ParamsDispositivo,
        "ejemplo": {"dispositivo_id": 1}},
    "crear_incidente": {
        "descripcion": "Abre un incidente para seguimiento humano.",
        "riesgo": "bajo", "modelo": ParamsIncidente,
        "ejemplo": {"titulo": "Revisar fallas de login", "severidad": 3, "dispositivo_id": 1}},
}

# Quién propone puede ser un agente de IA, el sistema o una persona.
# Estos nombres están reservados: nunca pueden revisar ni aprobar.
REVISORES_PROHIBIDOS = {"agente_ia", "sistema", "motor_syslog"}
MAX_PENDIENTES_POR_PROPONENTE = 5

ESTADOS_PENDIENTES = ("propuesta", "en_revision")


def revisor_valido(revisor: str, propuesto_por: str) -> Optional[str]:
    """Devuelve un mensaje de error si el revisor no puede revisar, o None si puede."""
    r = revisor.strip().lower()
    if r in REVISORES_PROHIBIDOS or r.startswith(("agente", "ia_", "bot")):
        return "Solo una persona puede revisar y aprobar acciones (no un agente de IA ni el sistema)"
    if r == propuesto_por.strip().lower():
        return "Separación de funciones: quien propone la acción no puede aprobarla"
    return None
