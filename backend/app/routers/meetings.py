"""Endpoints REST do Transcritor CTCE."""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import jobs, schemas
from ..config import settings
from ..database import LogEvento, Participante, Reuniao, Segmento, StatusReuniao, get_db
from ..services import docx_export, txt_export

router = APIRouter(prefix="/api/meetings", tags=["reunioes"])


def _extensao_valida(nome_arquivo: str) -> str:
    ext = Path(nome_arquivo).suffix.lower()
    if ext not in settings.allowed_extensions:
        suportados = ", ".join(sorted(settings.allowed_extensions))
        raise HTTPException(
            status_code=400,
            detail=f"Formato '{ext}' não suportado. Formatos aceitos: {suportados}.",
        )
    return ext


@router.post("/upload", response_model=schemas.ReuniaoResumo)
async def enviar_reuniao(
    arquivo: UploadFile = File(...),
    titulo: Optional[str] = Form(None),
    excluir_audio_apos_processar: bool = Form(False),
    usar_diarizacao: bool = Form(False),
    usuario_responsavel: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    ext = _extensao_valida(arquivo.filename)

    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise HTTPException(status_code=400, detail="O arquivo enviado está vazio.")
    if len(conteudo) > settings.max_upload_size:
        raise HTTPException(status_code=400, detail="Arquivo excede o tamanho máximo permitido (2GB).")

    reuniao = Reuniao(
        titulo=titulo or Path(arquivo.filename).stem,
        nome_arquivo_original=arquivo.filename,
        formato=ext,
        tamanho_bytes=len(conteudo),
        status=StatusReuniao.PENDENTE.value,
        excluir_audio_apos_processar=excluir_audio_apos_processar,
        diarizacao_solicitada=usar_diarizacao,
        usuario_responsavel=usuario_responsavel,
    )
    db.add(reuniao)
    db.commit()
    db.refresh(reuniao)

    destino = settings.uploads_dir / reuniao.id / f"original{ext}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        destino.write_bytes(conteudo)
    except OSError as exc:
        db.delete(reuniao)
        db.commit()
        raise HTTPException(
            status_code=500,
            detail="Não foi possível salvar o arquivo no servidor (verifique espaço em disco).",
        ) from exc

    reuniao.caminho_audio_original = str(destino)
    db.add(LogEvento(
        reuniao_id=reuniao.id, tipo="upload",
        descricao=f"Arquivo '{arquivo.filename}' recebido ({len(conteudo)} bytes).",
        usuario=usuario_responsavel,
    ))
    db.commit()
    db.refresh(reuniao)

    jobs.iniciar_processamento(reuniao.id)
    return reuniao


@router.get("", response_model=list[schemas.ReuniaoResumo])
def listar_reunioes(busca: Optional[str] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Reuniao)
    if status:
        query = query.filter(Reuniao.status == status)
    if busca:
        query = query.filter(Reuniao.titulo.ilike(f"%{busca}%"))
    return query.order_by(Reuniao.criado_em.desc()).all()


def _obter_reuniao_ou_404(reuniao_id: str, db: Session) -> Reuniao:
    reuniao = db.get(Reuniao, reuniao_id)
    if reuniao is None:
        raise HTTPException(status_code=404, detail="Reunião não encontrada.")
    return reuniao


@router.get("/{reuniao_id}", response_model=schemas.ReuniaoDetalhe)
def obter_reuniao(reuniao_id: str, db: Session = Depends(get_db)):
    return _obter_reuniao_ou_404(reuniao_id, db)


@router.get("/{reuniao_id}/status", response_model=schemas.StatusProcessamento)
def status_reuniao(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    return schemas.StatusProcessamento(
        id=reuniao.id,
        status=reuniao.status,
        etapa_atual=reuniao.etapa_atual,
        progresso_percentual=reuniao.progresso_percentual,
        mensagem_erro=reuniao.mensagem_erro,
        quantidade_segmentos=len(reuniao.segmentos),
    )


@router.delete("/{reuniao_id}")
def excluir_reuniao(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    for caminho_str in (reuniao.caminho_audio_original, reuniao.caminho_audio_extraido):
        if caminho_str and Path(caminho_str).exists():
            Path(caminho_str).unlink()
    db.delete(reuniao)
    db.commit()
    return {"detail": "Reunião excluída."}


# --- Segmentos (editor de transcrição) -------------------------------------

def _obter_segmento_ou_404(reuniao: Reuniao, segmento_id: str) -> Segmento:
    for segmento in reuniao.segmentos:
        if segmento.id == segmento_id:
            return segmento
    raise HTTPException(status_code=404, detail="Segmento não encontrado.")


@router.put("/{reuniao_id}/segmentos/{segmento_id}", response_model=schemas.SegmentoOut)
def editar_segmento(reuniao_id: str, segmento_id: str, dados: schemas.SegmentoUpdate, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    segmento = _obter_segmento_ou_404(reuniao, segmento_id)

    if dados.texto is not None:
        segmento.texto = dados.texto
        # Salvar o texto (mesmo sem alterá-lo, como confirmação de que o
        # trecho foi revisado e está correto) remove a marcação de baixa
        # confiança - ela existe para chamar atenção durante a revisão, não
        # depois que um humano já revisou aquele trecho.
        segmento.baixa_confianca = False
    if dados.inicio_segundos is not None:
        segmento.inicio_segundos = dados.inicio_segundos
    if dados.fim_segundos is not None:
        segmento.fim_segundos = dados.fim_segundos
    segmento.editado_manualmente = True

    db.commit()
    db.refresh(segmento)
    return segmento


@router.delete("/{reuniao_id}/segmentos/{segmento_id}")
def excluir_segmento(reuniao_id: str, segmento_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    segmento = _obter_segmento_ou_404(reuniao, segmento_id)
    db.delete(segmento)
    db.commit()
    return {"detail": "Segmento excluído."}


@router.post("/{reuniao_id}/segmentos", response_model=schemas.SegmentoOut)
def criar_segmento(reuniao_id: str, dados: schemas.SegmentoCriar, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    ordem_insercao = dados.apos_ordem + 1 if dados.apos_ordem is not None else 1
    for segmento in reuniao.segmentos:
        if segmento.ordem >= ordem_insercao:
            segmento.ordem += 1
    novo = Segmento(
        reuniao_id=reuniao.id,
        ordem=ordem_insercao,
        inicio_segundos=dados.inicio_segundos,
        fim_segundos=dados.fim_segundos,
        texto=dados.texto,
        editado_manualmente=True,
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.post("/{reuniao_id}/segmentos/{segmento_id}/dividir", response_model=list[schemas.SegmentoOut])
def dividir_segmento(reuniao_id: str, segmento_id: str, dados: schemas.SegmentoDividir, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    segmento = _obter_segmento_ou_404(reuniao, segmento_id)

    texto = segmento.texto
    pos = dados.posicao_caractere
    if pos <= 0 or pos >= len(texto):
        raise HTTPException(status_code=400, detail="Posição de divisão inválida.")

    proporcao = pos / len(texto)
    duracao = segmento.fim_segundos - segmento.inicio_segundos
    tempo_corte = segmento.inicio_segundos + duracao * proporcao

    for s in reuniao.segmentos:
        if s.ordem > segmento.ordem:
            s.ordem += 1

    segundo = Segmento(
        reuniao_id=reuniao.id,
        ordem=segmento.ordem + 1,
        inicio_segundos=tempo_corte,
        fim_segundos=segmento.fim_segundos,
        participante_id=segmento.participante_id,
        falante=segmento.falante,
        texto=texto[pos:].strip(),
        editado_manualmente=True,
    )
    segmento.texto = texto[:pos].strip()
    segmento.fim_segundos = tempo_corte
    segmento.editado_manualmente = True

    db.add(segundo)
    db.commit()
    db.refresh(segmento)
    db.refresh(segundo)
    return [segmento, segundo]


@router.post("/{reuniao_id}/segmentos/mesclar", response_model=schemas.SegmentoOut)
def mesclar_segmentos(reuniao_id: str, dados: schemas.SegmentosMesclar, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    a = _obter_segmento_ou_404(reuniao, dados.segmento_id_a)
    b = _obter_segmento_ou_404(reuniao, dados.segmento_id_b)
    if a.ordem > b.ordem:
        a, b = b, a

    a.texto = f"{a.texto} {b.texto}".strip()
    a.fim_segundos = b.fim_segundos
    a.baixa_confianca = a.baixa_confianca or b.baixa_confianca
    a.editado_manualmente = True

    for s in reuniao.segmentos:
        if s.ordem > b.ordem:
            s.ordem -= 1
    db.delete(b)
    db.commit()
    db.refresh(a)
    return a


@router.put("/{reuniao_id}/segmentos/{segmento_id}/participante", response_model=schemas.SegmentoOut)
def atribuir_participante(reuniao_id: str, segmento_id: str, dados: schemas.SegmentoParticipante, db: Session = Depends(get_db)):
    """Vincula (ou desvincula) um segmento a um participante do quadro da
    reunião. O nome exibido (falante) é sempre copiado do quadro - editar o
    nome do participante depois propaga automaticamente para aqui."""
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    segmento = _obter_segmento_ou_404(reuniao, segmento_id)

    if dados.participante_id is None:
        segmento.participante_id = None
        segmento.falante = None
    else:
        participante = db.get(Participante, dados.participante_id)
        if participante is None or participante.reuniao_id != reuniao.id:
            raise HTTPException(status_code=404, detail="Participante não encontrado.")
        segmento.participante_id = participante.id
        segmento.falante = participante.nome

    db.commit()
    db.refresh(segmento)
    return segmento


# --- Exportação --------------------------------------------------------------

@router.get("/{reuniao_id}/exportar/docx")
def exportar_docx(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    if reuniao.status != StatusReuniao.CONCLUIDA.value:
        raise HTTPException(status_code=400, detail="A transcrição ainda não foi concluída.")
    buffer = docx_export.gerar_docx_transcricao(reuniao)
    nome_arquivo = f"transcricao_{reuniao.titulo.replace(' ', '_')}.docx"
    db.add(LogEvento(reuniao_id=reuniao.id, tipo="exportacao", descricao="Exportação DOCX", usuario=reuniao.usuario_responsavel))
    db.commit()
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@router.get("/{reuniao_id}/exportar/txt", response_class=PlainTextResponse)
def exportar_txt(reuniao_id: str, db: Session = Depends(get_db)):
    reuniao = _obter_reuniao_ou_404(reuniao_id, db)
    if reuniao.status != StatusReuniao.CONCLUIDA.value:
        raise HTTPException(status_code=400, detail="A transcrição ainda não foi concluída.")
    texto = txt_export.gerar_txt_transcricao(reuniao)
    db.add(LogEvento(reuniao_id=reuniao.id, tipo="exportacao", descricao="Exportação TXT", usuario=reuniao.usuario_responsavel))
    db.commit()
    nome_arquivo = f"transcricao_{reuniao.titulo.replace(' ', '_')}.txt"
    return PlainTextResponse(
        texto,
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
