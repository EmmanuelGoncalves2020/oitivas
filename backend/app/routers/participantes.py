"""Quadro de participantes de uma reunião.

Permite nomear os participantes uma única vez logo no início da revisão
(ex.: "Participante 1" -> "Emmanuel") e propagar automaticamente esse nome
para todos os trechos da transcrição vinculados a ele - o usuário não
precisa reescrever o nome em cada segmento. A propagação é feita por
vínculo (chave estrangeira), não por comparação de texto, então não se
perde por causa de uma pequena diferença de digitação entre segmentos.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import Participante, Reuniao, Segmento, get_db

router = APIRouter(prefix="/api/meetings", tags=["participantes"])


def _obter_reuniao_ou_404(reuniao_id: str, db: Session) -> Reuniao:
    reuniao = db.get(Reuniao, reuniao_id)
    if reuniao is None:
        raise HTTPException(status_code=404, detail="Reunião não encontrada.")
    return reuniao


def _obter_participante_ou_404(reuniao_id: str, participante_id: str, db: Session) -> Participante:
    participante = db.get(Participante, participante_id)
    if participante is None or participante.reuniao_id != reuniao_id:
        raise HTTPException(status_code=404, detail="Participante não encontrado.")
    return participante


@router.get("/{reuniao_id}/participantes", response_model=list[schemas.ParticipanteOut])
def listar_participantes(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    return (
        db.query(Participante)
        .filter(Participante.reuniao_id == reuniao.id)
        .order_by(Participante.ordem)
        .all()
    )


@router.post("/{reuniao_id}/participantes", response_model=schemas.ParticipanteOut)
def criar_participante(reuniao_id: str, dados: schemas.ParticipanteCriar, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    quantidade_atual = db.query(Participante).filter(Participante.reuniao_id == reuniao.id).count()
    nova_ordem = quantidade_atual + 1
    nome = (dados.nome or "").strip() or f"Participante {nova_ordem}"

    novo = Participante(reuniao_id=reuniao.id, ordem=nova_ordem, nome=nome)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.put("/{reuniao_id}/participantes/{participante_id}", response_model=schemas.ParticipanteOut)
def renomear_participante(reuniao_id: str, participante_id: str, dados: schemas.ParticipanteAtualizar, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    participante = _obter_participante_ou_404(reuniao.id, participante_id, db)

    nome_novo = dados.nome.strip()
    if not nome_novo:
        raise HTTPException(status_code=400, detail="O nome não pode ser vazio.")
    participante.nome = nome_novo

    # Propagação automática: todo segmento vinculado a este participante
    # passa a exibir o novo nome, sem precisar editar um por um.
    db.query(Segmento).filter(Segmento.participante_id == participante.id).update({"falante": nome_novo})

    db.commit()
    db.refresh(participante)
    return participante


@router.delete("/{reuniao_id}/participantes/{participante_id}")
def excluir_participante(reuniao_id: str, participante_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    participante = _obter_participante_ou_404(reuniao.id, participante_id, db)

    db.query(Segmento).filter(Segmento.participante_id == participante.id).update(
        {"participante_id": None, "falante": None}
    )
    db.delete(participante)
    db.commit()
    return {"detail": "Participante excluído."}
