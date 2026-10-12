"""Punto de entrada de la API de NOC Syslog Inteligente."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import ENTORNO, VERSION
from app.database import init_schema
from app.routers import dispositivos, syslog


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_schema()          # garantiza tablas y migraciones al arrancar
    yield


app = FastAPI(
    title="NOC Syslog Inteligente",
    version=VERSION,
    description="MVP v0.2.0. Todos los datos de ejemplo son SIMULADOS.",
    lifespan=lifespan,
)
app.include_router(dispositivos.router)
app.include_router(syslog.router)


@app.get("/api/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok", "version": VERSION, "entorno": ENTORNO}