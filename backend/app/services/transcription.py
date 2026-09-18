"""Transcrição local de áudio via faster-whisper.

Processamento inteiramente local/offline: o áudio nunca é enviado para
nenhum serviço externo. A única comunicação de rede possível é o download
único dos pesos do modelo (na primeira execução), feito pela própria
biblioteca faster-whisper a partir do Hugging Face Hub. Para ambientes sem
acesso à internet, defina TRANSCRITOR_WHISPER_MODEL com o caminho local de
um modelo já baixado.
"""
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from ..config import settings

_model_cache: dict[tuple[str, str, str], object] = {}
_model_cache_lock = Lock()


class ModeloIndisponivelError(RuntimeError):
    """A biblioteca faster-whisper não está instalada ou o modelo não pôde ser carregado."""


@dataclass
class SegmentoTranscrito:
    inicio_segundos: float
    fim_segundos: float
    texto: str
    baixa_confianca: bool
    confianca_media: float


def _carregar_modelo():
    chave = (settings.whisper_model, settings.whisper_device, settings.whisper_compute_type)
    with _model_cache_lock:
        if chave not in _model_cache:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ModeloIndisponivelError(
                    "A biblioteca 'faster-whisper' não está instalada. "
                    "Execute 'pip install -r requirements.txt' no ambiente do backend."
                ) from exc
            try:
                _model_cache[chave] = WhisperModel(
                    settings.whisper_model,
                    device=settings.whisper_device,
                    compute_type=settings.whisper_compute_type,
                )
            except Exception as exc:  # noqa: BLE001 - reempacotado como erro de domínio
                raise ModeloIndisponivelError(
                    f"Falha ao carregar o modelo de transcrição '{settings.whisper_model}'. "
                    "Verifique memória disponível e conectividade (para o download inicial "
                    "do modelo) ou configure um modelo local já baixado."
                ) from exc
        return _model_cache[chave]


_REPETICAO_PALAVRA = re.compile(r"\b(\w+)( \1\b){2,}", re.IGNORECASE)


def _limpar_texto(texto: str) -> str:
    """Melhora a forma do texto sem alterar o conteúdo: espaços, capitalização
    inicial e remoção de repetições óbvias de reconhecimento (ex.: 'então então então')."""
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = _REPETICAO_PALAVRA.sub(r"\1", texto)
    if texto and texto[0].isalpha():
        texto = texto[0].upper() + texto[1:]
    return texto


def transcrever(
    caminho_audio: Path,
    progresso_callback: Callable[[float], None] | None = None,
    termos_dicionario: list[str] | None = None,
) -> Iterator[SegmentoTranscrito]:
    """Transcreve o áudio localmente, gerando segmentos com timestamp.

    progresso_callback recebe um valor de 0.0 a 1.0 conforme o processamento avança.
    termos_dicionario (opcional) são termos institucionais cadastrados pelo
    usuário (siglas, nomes, cargos) usados para orientar o reconhecimento de
    fala via prompt inicial do Whisper - apenas influenciam a probabilidade
    de reconhecimento correto, nunca inserem conteúdo que não foi falado.
    """
    modelo = _carregar_modelo()
    initial_prompt = ", ".join(termos_dicionario) if termos_dicionario else None
    segmentos, info = modelo.transcribe(
        str(caminho_audio),
        language=settings.whisper_language,
        vad_filter=True,
        initial_prompt=initial_prompt,
    )

    duracao_total = info.duration or 1.0
    for seg in segmentos:
        texto = _limpar_texto(seg.text)
        if not texto:
            continue
        avg_logprob = getattr(seg, "avg_logprob", 0.0) or 0.0
        no_speech_prob = getattr(seg, "no_speech_prob", 0.0) or 0.0
        baixa_confianca = avg_logprob < -1.0 or no_speech_prob > 0.6

        if progresso_callback is not None:
            progresso_callback(min(seg.end / duracao_total, 1.0))

        yield SegmentoTranscrito(
            inicio_segundos=seg.start,
            fim_segundos=seg.end,
            texto=texto,
            baixa_confianca=baixa_confianca,
            confianca_media=avg_logprob,
        )
