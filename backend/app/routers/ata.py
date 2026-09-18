"""Endpoints de Ata/Relatório e Encaminhamentos da reunião."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import schemas
from ..config import settings
from ..database import AtaReuniao, Encaminhamento, LogEvento, Reuniao, StatusReuniao, get_db
from ..services import ata as ata_service
from ..services import docx_ata_export, encaminhamentos as encaminhamentos_service

router = APIRouter(prefix="/api/meetings", tags=["ata"])


def _obter_reuniao_ou_404(reuniao_id: str, db: Session) -> Reuniao:
    reuniao = db.get(Reuniao, reuniao_id)
    if reuniao is None:
        raise HTTPException(status_code=404, detail="Reunião não encontrada.")
    return reuniao


def _obter_ata_ou_404(reuniao_id: str, db: Session) -> AtaReuniao:
    ata = db.query(AtaReuniao).filter(AtaReuniao.reuniao_id == reuniao_id).first()
    if ata is None:
        raise HTTPException(status_code=404, detail="A ata ainda não foi gerada para esta reunião.")
    return ata


def _listar_encaminhamentos(reuniao_id: str, db: Session) -> list[Encaminhamento]:
    return (
        db.query(Encaminhamento)
        .filter(Encaminhamento.reuniao_id == reuniao_id)
        .order_by(Encaminhamento.criado_em)
        .all()
    )


def _montar_ata_out(ata: AtaReuniao, encaminhamentos: list[Encaminhamento]) -> schemas.AtaOut:
    return schemas.AtaOut(
        id=ata.id,
        objetivo=ata.objetivo,
        assuntos_tratados=ata.assuntos_tratados,
        decisoes=ata.decisoes,
        pendencias=ata.pendencias,
        gerada_por_ia=ata.gerada_por_ia,
        gerada_em=ata.gerada_em,
        atualizada_em=ata.atualizada_em,
        encaminhamentos=encaminhamentos,
    )


@router.post("/{reuniao_id}/ata/gerar", response_model=schemas.AtaOut)
def gerar_ata(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    if reuniao.status != StatusReuniao.CONCLUIDA.value:
        raise HTTPException(status_code=400, detail="A transcrição precisa estar concluída antes de gerar a ata.")

    ata = db.query(AtaReuniao).filter(AtaReuniao.reuniao_id == reuniao.id).first()
    if ata is None:
        ata = AtaReuniao(reuniao_id=reuniao.id)
        db.add(ata)
        db.flush()

    # Encaminhamentos automáticos: adiciona apenas candidatos ainda não
    # registrados (não duplica ao gerar de novo) e nunca remove edições
    # manuais do usuário.
    existentes = {
        (e.segmento_id, e.descricao)
        for e in db.query(Encaminhamento).filter(Encaminhamento.reuniao_id == reuniao.id).all()
    }
    nomes_participantes = sorted({s.falante for s in reuniao.segmentos if s.falante})
    candidatos = encaminhamentos_service.extrair_candidatos(reuniao.segmentos, nomes_participantes)
    for c in candidatos:
        if (c.segmento_id, c.descricao) in existentes:
            continue
        db.add(Encaminhamento(
            reuniao_id=reuniao.id,
            segmento_id=c.segmento_id,
            descricao=c.descricao,
            responsavel=c.responsavel,
            prazo=c.prazo,
            status="Pendente",
            origem="automatica",
        ))

    if settings.ollama_habilitado:
        rascunho = ata_service.gerar_rascunho_ia(reuniao.segmentos)
        if rascunho:
            if not ata.assuntos_tratados:
                ata.assuntos_tratados = rascunho["assuntos_tratados"]
            if not ata.decisoes:
                ata.decisoes = rascunho["decisoes"]
            if not ata.pendencias:
                ata.pendencias = rascunho["pendencias"]
            ata.gerada_por_ia = True
            db.add(LogEvento(reuniao_id=reuniao.id, tipo="ata", descricao="Rascunho de ata gerado por IA local (Ollama)."))
        else:
            db.add(LogEvento(reuniao_id=reuniao.id, tipo="ata_ia_indisponivel", descricao="Rascunho por IA local solicitado mas indisponível; seções narrativas seguem em branco."))

    ata.atualizada_em = datetime.utcnow()
    db.add(LogEvento(reuniao_id=reuniao.id, tipo="ata", descricao=f"Ata gerada/atualizada ({len(candidatos)} encaminhamentos candidatos)."))
    db.commit()
    db.refresh(ata)
    return _montar_ata_out(ata, _listar_encaminhamentos(reuniao.id, db))


@router.get("/{reuniao_id}/ata", response_model=schemas.AtaOut)
def obter_ata(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    ata = _obter_ata_ou_404(reuniao.id, db)
    return _montar_ata_out(ata, _listar_encaminhamentos(reuniao.id, db))


@router.put("/{reuniao_id}/ata", response_model=schemas.AtaOut)
def atualizar_ata(reuniao_id: str, dados: schemas.AtaAtualizar, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    ata = _obter_ata_ou_404(reuniao.id, db)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(ata, campo, valor)
    ata.atualizada_em = datetime.utcnow()
    db.commit()
    db.refresh(ata)
    return _montar_ata_out(ata, _listar_encaminhamentos(reuniao.id, db))


@router.get("/{reuniao_id}/exportar/ata-docx")
def exportar_ata_docx(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    ata = _obter_ata_ou_404(reuniao.id, db)
    encaminhamentos = _listar_encaminhamentos(reuniao.id, db)
    buffer = docx_ata_export.gerar_docx_ata(reuniao, ata, encaminhamentos)
    nome_arquivo = f"ata_{reuniao.titulo.replace(' ', '_')}.docx"
    db.add(LogEvento(reuniao_id=reuniao.id, tipo="exportacao", descricao="Exportação da ata em DOCX"))
    db.commit()
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


# --- Encaminhamentos ---------------------------------------------------------

@router.get("/{reuniao_id}/encaminhamentos", response_model=list[schemas.EncaminhamentoOut])
def listar_encaminhamentos(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    return _listar_encaminhamentos(reuniao.id, db)


@router.post("/{reuniao_id}/encaminhamentos", response_model=schemas.EncaminhamentoOut)
def criar_encaminhamento(reuniao_id: str, dados: schemas.EncaminhamentoCriar, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    novo = Encaminhamento(
        reuniao_id=reuniao.id,
        descricao=dados.descricao,
        responsavel=dados.responsavel or None,
        prazo=dados.prazo or None,
        status=dados.status,
        origem="manual",
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


def _obter_encaminhamento_ou_404(reuniao_id: str, encaminhamento_id: str, db: Session) -> Encaminhamento:
    enc = db.get(Encaminhamento, encaminhamento_id)
    if enc is None or enc.reuniao_id != reuniao_id:
        raise HTTPException(status_code=404, detail="Encaminhamento não encontrado.")
    return enc


@router.put("/{reuniao_id}/encaminhamentos/{encaminhamento_id}", response_model=schemas.EncaminhamentoOut)
def atualizar_encaminhamento(reuniao_id: str, encaminhamento_id: str, dados: schemas.EncaminhamentoAtualizar, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    enc = _obter_encaminhamento_ou_404(reuniao.id, encaminhamento_id, db)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(enc, campo, valor or None if campo in ("responsavel", "prazo") else valor)
    db.commit()
    db.refresh(enc)
    return enc


@router.delete("/{reuniao_id}/encaminhamentos/{encaminhamento_id}")
def excluir_encaminhamento(reuniao_id: str, encaminhamento_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    enc = _obter_encaminhamento_ou_404(reuniao.id, encaminhamento_id, db)
    db.delete(enc)
    db.commit()
    return {"detail": "Encaminhamento excluído."}
