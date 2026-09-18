"""Configurações da aplicação Transcritor CTCE."""
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Diretórios de armazenamento local (nunca enviados para serviços externos)
    base_dir: Path = Path(__file__).resolve().parent.parent
    storage_dir: Path = base_dir / "storage"
    uploads_dir: Path = storage_dir / "uploads"
    audio_dir: Path = storage_dir / "audio"
    database_path: Path = storage_dir / "db.sqlite3"

    # Modelo de transcrição (faster-whisper). Pode ser um nome do Hugging Face
    # (ex: "small", "medium") ou um caminho local para instalação 100% offline.
    whisper_model: str = "small"
    whisper_device: str = "cpu"  # "cpu" ou "cuda"
    whisper_compute_type: str = "int8"  # int8 (cpu) / float16 (gpu)
    whisper_language: str = "pt"

    # Diarização (identificação de participantes) - OPCIONAL, desabilitada por
    # padrão. Usa pyannote.audio, que roda localmente após um download único
    # (uma única vez, por modelo) dos pesos a partir do Hugging Face Hub -
    # exige conta gratuita + aceite dos termos do modelo + token de acesso.
    # Consulte docs/INSTALACAO.md antes de habilitar.
    diarizacao_habilitada: bool = False
    hf_token: str | None = None
    diarization_model: str = "pyannote/speaker-diarization-3.1"

    # Formatos de entrada suportados
    allowed_extensions: set[str] = {
        ".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".aac", ".mov", ".mkv",
    }

    # Limite de tamanho de upload (bytes) - 2GB
    max_upload_size: int = 2 * 1024 * 1024 * 1024

    class Config:
        env_prefix = "TRANSCRITOR_"


settings = Settings()

for directory in (settings.storage_dir, settings.uploads_dir, settings.audio_dir):
    directory.mkdir(parents=True, exist_ok=True)
