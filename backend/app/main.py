"""Transcritor CTCE - aplicação FastAPI.

Ferramenta institucional de transcrição de reuniões com processamento
local/offline, destinada ao uso da Corregedoria Tributária de Controle
Externo (CTCE) - SEFAZ-RJ.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import meetings

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Transcritor CTCE",
    description="Transcrição automática e local de reuniões institucionais.",
    version="0.1.0-mvp",
)

app.include_router(meetings.router)


@app.get("/api/saude")
def saude():
    return {"status": "ok"}


# Servir o frontend estático por último: um Mount em "/" é um prefixo
# catch-all e, se registrado antes, intercepta qualquer rota definida depois.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
