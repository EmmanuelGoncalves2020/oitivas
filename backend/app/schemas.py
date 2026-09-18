"""Schemas Pydantic (request/response) do Transcritor CTCE."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SegmentoOut(BaseModel):
    id: str
    ordem: int
    inicio_segundos: float
    fim_segundos: float
    falante: Optional[str] = None
    texto: str
    baixa_confianca: bool
    editado_manualmente: bool

    class Config:
        from_attributes = True


class ReuniaoResumo(BaseModel):
    id: str
    titulo: str
    nome_arquivo_original: str
    formato: str
    tamanho_bytes: int
    duracao_segundos: Optional[float] = None
    status: str
    etapa_atual: Optional[str] = None
    progresso_percentual: int
    criado_em: datetime
    processamento_concluido_em: Optional[datetime] = None
    tempo_processamento_segundos: Optional[float] = None

    class Config:
        from_attributes = True


class ReuniaoDetalhe(ReuniaoResumo):
    idioma: str
    modelo_whisper: Optional[str] = None
    diarizacao_solicitada: bool
    diarizacao_disponivel: bool
    mensagem_erro: Optional[str] = None
    audio_excluido: bool
    segmentos: list[SegmentoOut] = []

    class Config:
        from_attributes = True


class StatusProcessamento(BaseModel):
    id: str
    status: str
    etapa_atual: Optional[str] = None
    progresso_percentual: int
    mensagem_erro: Optional[str] = None
    quantidade_segmentos: int = 0


class SegmentoUpdate(BaseModel):
    texto: Optional[str] = None
    falante: Optional[str] = None
    inicio_segundos: Optional[float] = None
    fim_segundos: Optional[float] = None


class SegmentoCriar(BaseModel):
    inicio_segundos: float
    fim_segundos: float
    falante: Optional[str] = None
    texto: str
    apos_ordem: Optional[int] = None


class SegmentoDividir(BaseModel):
    posicao_caractere: int


class SegmentosMesclar(BaseModel):
    segmento_id_a: str
    segmento_id_b: str


class RenomearParticipante(BaseModel):
    nome_atual: str
    nome_novo: str


class TermoOut(BaseModel):
    id: str
    termo: str
    criado_em: datetime

    class Config:
        from_attributes = True


class TermoCriar(BaseModel):
    termo: str


class Capacidades(BaseModel):
    diarizacao_disponivel: bool
    rascunho_ia_disponivel: bool


class EncaminhamentoOut(BaseModel):
    id: str
    descricao: str
    responsavel: Optional[str] = None
    prazo: Optional[str] = None
    status: str
    origem: str
    segmento_id: Optional[str] = None
    criado_em: datetime

    class Config:
        from_attributes = True


class EncaminhamentoCriar(BaseModel):
    descricao: str
    responsavel: Optional[str] = None
    prazo: Optional[str] = None
    status: str = "Pendente"


class EncaminhamentoAtualizar(BaseModel):
    descricao: Optional[str] = None
    responsavel: Optional[str] = None
    prazo: Optional[str] = None
    status: Optional[str] = None


class AtaOut(BaseModel):
    id: str
    objetivo: Optional[str] = None
    assuntos_tratados: Optional[str] = None
    decisoes: Optional[str] = None
    pendencias: Optional[str] = None
    gerada_por_ia: bool
    gerada_em: datetime
    atualizada_em: Optional[datetime] = None
    encaminhamentos: list[EncaminhamentoOut] = []

    class Config:
        from_attributes = True


class AtaAtualizar(BaseModel):
    objetivo: Optional[str] = None
    assuntos_tratados: Optional[str] = None
    decisoes: Optional[str] = None
    pendencias: Optional[str] = None
