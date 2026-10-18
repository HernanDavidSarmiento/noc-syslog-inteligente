"""Detección heurística de texto que intenta dar órdenes a una IA o a un operador.

IMPORTANTE: esto es una ALERTA, no la defensa principal. La defensa real es que
los logs NUNCA se ejecutan ni se pasan como instrucciones; cualquier acción
requiere propuesta, revisión humana y aprobación.
"""
import re
from typing import Optional

PATRONES = [
    ("ignorar instrucciones previas", re.compile(
        r"ignor(e|a|ar)\s+(all\s+|todas\s+)?(the\s+|las\s+)?"
        r"(previous|prior|above|anteriores|previas)\s+(instructions?|instrucciones)", re.I)),
    ("referencia al prompt del sistema", re.compile(
        r"(system|developer|sistema)\s+(prompt|message|mensaje)", re.I)),
    ("intento de cambio de rol", re.compile(
        r"(you are now|act as|ahora eres|actúa como)", re.I)),
    ("orden de ejecución destructiva", re.compile(
        r"\b(run|execute|ejecuta(r)?)\b.{0,60}\b(delete|drop|erase|format|shutdown|"
        r"reload|rm\s+-rf|write\s+erase|no\s+logging|borra(r)?|elimina(r)?)\b",
        re.I | re.S)),
    ("borrado masivo", re.compile(
        r"\b(delete|borra(r)?|elimina(r)?)\s+(all|todo|todas|todos)\b", re.I)),
]


def detectar_sospechoso(texto: str) -> tuple[bool, Optional[str]]:
    """Devuelve (es_sospechoso, motivo). El motivo es texto propio, no del log."""
    hallazgos = [nombre for nombre, patron in PATRONES if patron.search(texto)]
    if not hallazgos:
        return False, None
    return True, "Posible prompt injection: " + "; ".join(hallazgos)