"""Transcritor CTCE - aplicação FastAPI.

Ferramenta institucional de transcrição de reuniões com processamento
local/offline, destinada ao uso da Corregedoria Tributária de Controle
Externo (CTCE) - SEFAZ-RJ.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import schemas
from .config import settings
from .routers import ata, dicionario, meetings

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Transcritor CTCE",
    description="Transcrição automática e local de reuniões institucionais.",
    version="0.3.0-mvp-fase3",
)

app.include_router(meetings.router)
app.include_router(dicionario.router)
app.include_router(ata.router)


@app.get("/api/saude")
def saude():
    return {"status": "ok"}


@app.get("/api/sistema/capacidades", response_model=schemas.Capacidades)
def capacidades():
    """Informa ao frontend quais funcionalidades opcionais estão configuradas
    nesta instalação (ex.: diarização), para não exibir controles que não
    vão funcionar."""
    return schemas.Capacidades(
        diarizacao_disponivel=settings.diarizacao_habilitada,
        rascunho_ia_disponivel=settings.ollama_habilitado,
    )


# Servir o frontend estático por último: um Mount em "/" é um prefixo
# catch-all e, se registrado antes, intercepta qualquer rota definida depois.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
