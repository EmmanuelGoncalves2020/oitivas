"""Extração e inspeção de áudio via ffmpeg/ffprobe (processamento 100% local)."""
import shutil
import subprocess
from pathlib import Path


class FFmpegNaoEncontradoError(RuntimeError):
    """ffmpeg/ffprobe não está instalado ou não está no PATH."""


class ArquivoInvalidoError(RuntimeError):
    """O arquivo enviado não pôde ser lido como áudio/vídeo válido."""


def _verificar_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise FFmpegNaoEncontradoError(
            "ffmpeg/ffprobe não foi encontrado no sistema. "
            "Instale o ffmpeg e garanta que esteja disponível no PATH "
            "(consulte docs/INSTALACAO.md)."
        )


def obter_duracao_segundos(caminho: Path) -> float:
    """Retorna a duração do arquivo em segundos usando ffprobe."""
    _verificar_ffmpeg()
    try:
        resultado = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(caminho),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(resultado.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise ArquivoInvalidoError(
            f"Não foi possível ler a duração do arquivo '{caminho.name}'. "
            "Verifique se o arquivo não está corrompido."
        ) from exc


def extrair_audio_wav(origem: Path, destino: Path) -> None:
    """Extrai/normaliza o áudio para WAV mono 16kHz, formato exigido pelo faster-whisper."""
    _verificar_ffmpeg()
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(origem),
                "-ac", "1", "-ar", "16000",
                "-vn",
                str(destino),
            ],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ArquivoInvalidoError(
            f"Falha ao extrair o áudio de '{origem.name}'. "
            "O arquivo pode estar corrompido ou em formato não suportado."
        ) from exc
