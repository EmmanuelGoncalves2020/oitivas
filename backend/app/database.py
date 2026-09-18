"""Camada de persistência (SQLite/SQLAlchemy) do Transcritor CTCE."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import settings


def _uuid() -> str:
    return str(uuid.uuid4())


class StatusReuniao(str, enum.Enum):
    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    CONCLUIDA = "concluida"
    ERRO = "erro"
    CANCELADA = "cancelada"


engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Reuniao(Base):
    __tablename__ = "reunioes"

    id = Column(String, primary_key=True, default=_uuid)
    titulo = Column(String, nullable=False)
    nome_arquivo_original = Column(String, nullable=False)
    formato = Column(String, nullable=False)
    tamanho_bytes = Column(Integer, nullable=False)
    duracao_segundos = Column(Float, nullable=True)

    status = Column(String, default=StatusReuniao.PENDENTE.value, nullable=False)
    etapa_atual = Column(String, nullable=True)
    progresso_percentual = Column(Integer, default=0)
    mensagem_erro = Column(Text, nullable=True)

    idioma = Column(String, default="pt")
    modelo_whisper = Column(String, nullable=True)
    diarizacao_solicitada = Column(Boolean, default=False)
    diarizacao_disponivel = Column(Boolean, default=False)

    caminho_audio_original = Column(String, nullable=True)
    caminho_audio_extraido = Column(String, nullable=True)
    excluir_audio_apos_processar = Column(Boolean, default=False)
    audio_excluido = Column(Boolean, default=False)

    usuario_responsavel = Column(String, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)
    processamento_iniciado_em = Column(DateTime, nullable=True)
    processamento_concluido_em = Column(DateTime, nullable=True)
    audio_excluido_em = Column(DateTime, nullable=True)
    tempo_processamento_segundos = Column(Float, nullable=True)

    segmentos = relationship(
        "Segmento", back_populates="reuniao", cascade="all, delete-orphan",
        order_by="Segmento.ordem",
    )


class Participante(Base):
    """Quadro de participantes de uma reunião. Nomear um participante aqui
    (ex.: "Participante 1" -> "Emmanuel") propaga automaticamente para todos
    os segmentos vinculados a ele - não depende de comparação de texto, então
    nunca "perde" a associação por causa de um pequeno erro de digitação."""

    __tablename__ = "participantes"

    id = Column(String, primary_key=True, default=_uuid)
    reuniao_id = Column(String, ForeignKey("reunioes.id"), nullable=False)
    ordem = Column(Integer, nullable=False)
    nome = Column(String, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Segmento(Base):
    __tablename__ = "segmentos"

    id = Column(String, primary_key=True, default=_uuid)
    reuniao_id = Column(String, ForeignKey("reunioes.id"), nullable=False)
    ordem = Column(Integer, nullable=False)

    inicio_segundos = Column(Float, nullable=False)
    fim_segundos = Column(Float, nullable=False)

    participante_id = Column(String, ForeignKey("participantes.id"), nullable=True)
    falante = Column(String, nullable=True)  # nome denormalizado, mantido em sincronia com participante.nome
    texto = Column(Text, nullable=False)

    confianca_media = Column(Float, nullable=True)
    baixa_confianca = Column(Boolean, default=False)

    editado_manualmente = Column(Boolean, default=False)

    reuniao = relationship("Reuniao", back_populates="segmentos")


class AtaReuniao(Base):
    __tablename__ = "atas"

    id = Column(String, primary_key=True, default=_uuid)
    reuniao_id = Column(String, ForeignKey("reunioes.id"), nullable=False, unique=True)

    objetivo = Column(Text, nullable=True)
    assuntos_tratados = Column(Text, nullable=True)
    decisoes = Column(Text, nullable=True)
    pendencias = Column(Text, nullable=True)

    gerada_por_ia = Column(Boolean, default=False)
    gerada_em = Column(DateTime, default=datetime.utcnow)
    atualizada_em = Column(DateTime, nullable=True)


class Encaminhamento(Base):
    __tablename__ = "encaminhamentos"

    id = Column(String, primary_key=True, default=_uuid)
    reuniao_id = Column(String, ForeignKey("reunioes.id"), nullable=False)
    segmento_id = Column(String, ForeignKey("segmentos.id"), nullable=True)

    descricao = Column(Text, nullable=False)
    responsavel = Column(String, nullable=True)  # None -> exibido como "Não identificado"
    prazo = Column(String, nullable=True)  # None -> exibido como "Não identificado"
    status = Column(String, default="Pendente")
    origem = Column(String, default="automatica")  # "automatica" (heurística) ou "manual"

    criado_em = Column(DateTime, default=datetime.utcnow)


class TermoDicionario(Base):
    __tablename__ = "dicionario_termos"

    id = Column(String, primary_key=True, default=_uuid)
    termo = Column(String, nullable=False, unique=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class LogEvento(Base):
    __tablename__ = "logs_eventos"

    id = Column(String, primary_key=True, default=_uuid)
    reuniao_id = Column(String, ForeignKey("reunioes.id"), nullable=True)
    tipo = Column(String, nullable=False)  # upload, processamento, exportacao, exclusao, erro
    descricao = Column(Text, nullable=True)
    usuario = Column(String, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
