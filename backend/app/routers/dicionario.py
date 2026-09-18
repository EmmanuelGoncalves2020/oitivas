"""Dicionário institucional de termos (siglas, nomes, expressões) usado para
orientar o reconhecimento de fala - ex.: CTCE, SEFAZ, SEI, Auditor Fiscal da
Receita Estadual."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import TermoDicionario, get_db

router = APIRouter(prefix="/api/dicionario", tags=["dicionario"])


@router.get("", response_model=list[schemas.TermoOut])
def listar_termos(db: Session = Depends(get_db)):
    return db.query(TermoDicionario).order_by(TermoDicionario.termo).all()


@router.post("", response_model=schemas.TermoOut)
def criar_termo(dados: schemas.TermoCriar, db: Session = Depends(get_db)):
    termo_normalizado = dados.termo.strip()
    if not termo_normalizado:
        raise HTTPException(status_code=400, detail="O termo não pode ser vazio.")

    existente = db.query(TermoDicionario).filter(TermoDicionario.termo == termo_normalizado).first()
    if existente:
        raise HTTPException(status_code=400, detail="Este termo já está cadastrado.")

    novo = TermoDicionario(termo=termo_normalizado)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.delete("/{termo_id}")
def excluir_termo(termo_id: str, db: Session = Depends(get_db)):
    termo = db.get(TermoDicionario, termo_id)
    if termo is None:
        raise HTTPException(status_code=404, detail="Termo não encontrado.")
    db.delete(termo)
    db.commit()
    return {"detail": "Termo excluído."}
