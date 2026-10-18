"""Punto de entrada de la API de NOC Syslog Inteligente."""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import ENTORNO, VERSION
from app.database import init_schema
from app.routers import (acciones, configuraciones, consola, dashboard, dispositivos, incidentes, syslog)

STATIC_DIR = Path(__file__).parent / "static"
# Política de seguridad de contenido: solo scripts y estilos del propio origen.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
# Swagger (/docs) carga scripts externos y en línea, por eso se excluye de la CSP.
RUTAS_SIN_CSP = ("/docs", "/redoc", "/openapi.json")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_schema()
    yield

app = FastAPI(title="NOC Syslog Inteligente", version=VERSION,
              description="MVP v0.2.0. Todos los datos de ejemplo son SIMULADOS.", lifespan=lifespan)

@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith(RUTAS_SIN_CSP):
        respuesta.headers["Content-Security-Policy"] = CSP
    return respuesta

app.include_router(dispositivos.router)
app.include_router(syslog.router)
app.include_router(incidentes.router)
app.include_router(dashboard.router)
app.include_router(configuraciones.router)
app.include_router(consola.router)
app.include_router(acciones.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok", "version": VERSION, "entorno": ENTORNO}
