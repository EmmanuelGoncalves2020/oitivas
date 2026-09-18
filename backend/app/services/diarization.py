"""Diarização local (identificação de participantes) via pyannote.audio.

Componente OPCIONAL, desabilitado por padrão (TRANSCRITOR_DIARIZACAO_HABILITADA=false).

TRANSPARÊNCIA SOBRE DEPENDÊNCIA EXTERNA: para habilitar esta funcionalidade é
necessário criar uma conta gratuita em https://huggingface.co, aceitar os
termos de uso do modelo "pyannote/speaker-diarization-3.1" (e do modelo de
segmentação do qual ele depende) na própria página do modelo, gerar um
token de acesso e configurá-lo em TRANSCRITOR_HF_TOKEN. Nessas condições, o
que é enviado à internet é exclusivamente o download único dos PESOS do
modelo (nunca o áudio da reunião), feito uma única vez e cacheado
localmente. A partir daí, a diarização roda inteiramente offline, como a
transcrição. Sem essa configuração, a ferramenta funciona normalmente sem
identificação de participantes (comportamento padrão da Fase 1).
"""
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from ..config import settings

_pipeline_cache = None
_pipeline_lock = Lock()


class DiarizacaoIndisponivelError(RuntimeError):
    """A diarização não está configurada, instalada ou pôde ser carregada."""


@dataclass
class TrechoFalante:
    inicio_segundos: float
    fim_segundos: float
    rotulo: str  # rótulo bruto do pipeline (ex.: "SPEAKER_00")


def _carregar_pipeline():
    global _pipeline_cache
    with _pipeline_lock:
        if _pipeline_cache is None:
            if not settings.hf_token:
                raise DiarizacaoIndisponivelError(
                    "Diarização habilitada, mas TRANSCRITOR_HF_TOKEN não foi configurado "
                    "(consulte docs/INSTALACAO.md)."
                )
            try:
                from pyannote.audio import Pipeline
            except ImportError as exc:
                raise DiarizacaoIndisponivelError(
                    "A biblioteca 'pyannote.audio' não está instalada. Execute "
                    "'pip install -r requirements-diarizacao.txt' no ambiente do backend."
                ) from exc
            try:
                _pipeline_cache = Pipeline.from_pretrained(
                    settings.diarization_model, use_auth_token=settings.hf_token,
                )
            except Exception as exc:  # noqa: BLE001 - reempacotado como erro de domínio
                raise DiarizacaoIndisponivelError(
                    "Falha ao carregar o modelo de diarização. Verifique o token do "
                    "Hugging Face e se os termos de uso do modelo foram aceitos."
                ) from exc
        return _pipeline_cache


def diarizar(caminho_audio: Path) -> list[TrechoFalante]:
    """Executa a diarização local e retorna os intervalos de fala por participante."""
    pipeline = _carregar_pipeline()
    resultado = pipeline(str(caminho_audio))
    return [
        TrechoFalante(inicio_segundos=turno.start, fim_segundos=turno.end, rotulo=rotulo)
        for turno, _, rotulo in resultado.itertracks(yield_label=True)
    ]


def atribuir_falantes(
    segmentos: list[tuple[float, float]],
    trechos_falantes: list[TrechoFalante],
) -> list[str | None]:
    """Associa cada segmento de transcrição (início, fim) ao participante com
    maior sobreposição temporal, convertendo rótulos brutos em nomes estáveis
    e legíveis ("Participante 1", "Participante 2", ...), na ordem em que
    aparecem pela primeira vez. Segmentos sem sobreposição ficam sem falante
    (não se inventa uma atribuição sem evidência)."""
    ordem_rotulos: list[str] = []
    for trecho in sorted(trechos_falantes, key=lambda t: t.inicio_segundos):
        if trecho.rotulo not in ordem_rotulos:
            ordem_rotulos.append(trecho.rotulo)
    nomes = {rotulo: f"Participante {i + 1}" for i, rotulo in enumerate(ordem_rotulos)}

    resultado: list[str | None] = []
    for inicio, fim in segmentos:
        melhor_rotulo = None
        melhor_sobreposicao = 0.0
        for trecho in trechos_falantes:
            sobreposicao = min(fim, trecho.fim_segundos) - max(inicio, trecho.inicio_segundos)
            if sobreposicao > melhor_sobreposicao:
                melhor_sobreposicao = sobreposicao
                melhor_rotulo = trecho.rotulo
        resultado.append(nomes.get(melhor_rotulo) if melhor_rotulo else None)
    return resultado
