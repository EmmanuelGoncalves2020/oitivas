"""Processamento assíncrono (em thread) de reuniões: extração + transcrição.

Mantém a interface responsiva durante reuniões longas, sem depender de
infraestrutura externa (fila/broker). Adequado para uso local de um único
servidor/máquina, conforme o escopo do MVP.
"""
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import settings
from .database import LogEvento, Reuniao, SessionLocal, Segmento, StatusReuniao, TermoDicionario
from .services import audio, diarization, transcription

logger = logging.getLogger("transcritor_ctce.jobs")


def _registrar_log(db, reuniao_id: str, tipo: str, descricao: str, usuario: str | None) -> None:
    db.add(LogEvento(reuniao_id=reuniao_id, tipo=tipo, descricao=descricao, usuario=usuario))
    db.commit()


def _atualizar(db, reuniao: Reuniao, **campos) -> None:
    for chave, valor in campos.items():
        setattr(reuniao, chave, valor)
    db.commit()


def iniciar_processamento(reuniao_id: str) -> None:
    thread = threading.Thread(target=_processar, args=(reuniao_id,), daemon=True)
    thread.start()


def _processar(reuniao_id: str) -> None:
    db = SessionLocal()
    inicio = time.monotonic()
    try:
        reuniao = db.get(Reuniao, reuniao_id)
        if reuniao is None:
            return

        _atualizar(
            db, reuniao,
            status=StatusReuniao.PROCESSANDO.value,
            etapa_atual="Preparando áudio...",
            progresso_percentual=2,
            processamento_iniciado_em=datetime.utcnow(),
        )
        _registrar_log(db, reuniao.id, "processamento", "Início do processamento", reuniao.usuario_responsavel)

        origem = Path(reuniao.caminho_audio_original)
        extraido = Path(settings.audio_dir) / reuniao.id / "audio.wav"

        duracao = audio.obter_duracao_segundos(origem)
        audio.extrair_audio_wav(origem, extraido)

        _atualizar(
            db, reuniao,
            duracao_segundos=duracao,
            caminho_audio_extraido=str(extraido),
            etapa_atual="Transcrevendo...",
            progresso_percentual=10,
        )

        def _callback_progresso(fracao: float) -> None:
            teto = 75 if reuniao.diarizacao_solicitada else 85
            percentual = 10 + int(fracao * (teto - 10))
            _atualizar(db, reuniao, progresso_percentual=min(percentual, teto))

        termos = [t.termo for t in db.query(TermoDicionario).all()]

        ordem = 0
        segmentos_criados: list[Segmento] = []
        for trecho in transcription.transcrever(extraido, _callback_progresso, termos_dicionario=termos):
            ordem += 1
            segmento = Segmento(
                reuniao_id=reuniao.id,
                ordem=ordem,
                inicio_segundos=trecho.inicio_segundos,
                fim_segundos=trecho.fim_segundos,
                falante=None,
                texto=trecho.texto,
                confianca_media=trecho.confianca_media,
                baixa_confianca=trecho.baixa_confianca,
            )
            db.add(segmento)
            segmentos_criados.append(segmento)
        db.commit()

        if reuniao.diarizacao_solicitada:
            _atualizar(db, reuniao, etapa_atual="Identificando participantes...", progresso_percentual=85)
            try:
                if not settings.diarizacao_habilitada:
                    raise diarization.DiarizacaoIndisponivelError(
                        "Diarização não está habilitada nesta instalação (consulte docs/INSTALACAO.md)."
                    )
                trechos_falantes = diarization.diarizar(extraido)
                rotulos = diarization.atribuir_falantes(
                    [(s.inicio_segundos, s.fim_segundos) for s in segmentos_criados],
                    trechos_falantes,
                )
                for segmento, rotulo in zip(segmentos_criados, rotulos):
                    segmento.falante = rotulo
                db.commit()
                _atualizar(db, reuniao, diarizacao_disponivel=True)
                _registrar_log(db, reuniao.id, "processamento", "Diarização concluída.", reuniao.usuario_responsavel)
            except diarization.DiarizacaoIndisponivelError as exc:
                logger.warning("Diarização indisponível para reunião %s: %s", reuniao_id, exc)
                _registrar_log(db, reuniao.id, "diarizacao_indisponivel", str(exc), reuniao.usuario_responsavel)

        _atualizar(
            db, reuniao,
            etapa_atual="Organizando texto...",
            progresso_percentual=90,
            modelo_whisper=settings.whisper_model,
        )

        if reuniao.excluir_audio_apos_processar:
            _atualizar(db, reuniao, etapa_atual="Excluindo áudio original...", progresso_percentual=95)
            _excluir_arquivos_audio(db, reuniao)

        tempo_total = time.monotonic() - inicio
        _atualizar(
            db, reuniao,
            status=StatusReuniao.CONCLUIDA.value,
            etapa_atual="Concluído",
            progresso_percentual=100,
            processamento_concluido_em=datetime.utcnow(),
            tempo_processamento_segundos=tempo_total,
        )
        _registrar_log(
            db, reuniao.id, "processamento",
            f"Processamento concluído em {tempo_total:.1f}s, {ordem} segmentos.",
            reuniao.usuario_responsavel,
        )
    except Exception as exc:  # noqa: BLE001 - job em background, erro deve virar estado persistido
        logger.exception("Falha ao processar reunião %s", reuniao_id)
        db.rollback()
        reuniao = db.get(Reuniao, reuniao_id)
        if reuniao is not None:
            _atualizar(
                db, reuniao,
                status=StatusReuniao.ERRO.value,
                etapa_atual="Erro no processamento",
                mensagem_erro=_mensagem_amigavel(exc),
            )
            _registrar_log(db, reuniao.id, "erro", str(exc), reuniao.usuario_responsavel)
    finally:
        db.close()


def _mensagem_amigavel(exc: Exception) -> str:
    nome = type(exc).__name__
    mapeamento = {
        "FFmpegNaoEncontradoError": "ffmpeg não está instalado no servidor. Consulte docs/INSTALACAO.md.",
        "ArquivoInvalidoError": "O arquivo enviado está corrompido ou em formato não suportado.",
        "ModeloIndisponivelError": str(exc),
    }
    return mapeamento.get(nome, "Ocorreu um erro inesperado durante o processamento. Tente novamente.")


def _excluir_arquivos_audio(db, reuniao: Reuniao) -> None:
    for caminho_str in (reuniao.caminho_audio_original, reuniao.caminho_audio_extraido):
        if not caminho_str:
            continue
        caminho = Path(caminho_str)
        if caminho.exists():
            caminho.unlink()
    _atualizar(
        db, reuniao,
        audio_excluido=True,
        audio_excluido_em=datetime.utcnow(),
        caminho_audio_original=None,
        caminho_audio_extraido=None,
    )
    _registrar_log(db, reuniao.id, "exclusao", "Arquivos de áudio excluídos após processamento.", reuniao.usuario_responsavel)
