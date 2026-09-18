"""Cliente HTTP mínimo para um servidor Ollama local (inferência 100% local).

Componente OPCIONAL, desabilitado por padrão (TRANSCRITOR_OLLAMA_HABILITADO=false).

TRANSPARÊNCIA SOBRE DEPENDÊNCIA EXTERNA: diferente da transcrição e da
diarização, aqui não há biblioteca Python pesada nem download automático -
é necessário instalar separadamente o aplicativo Ollama
(https://ollama.com) na própria máquina ou em um servidor da rede interna,
e baixar manualmente um modelo (ex.: `ollama pull llama3.1`). Esta
aplicação apenas faz uma chamada HTTP para esse servidor local
(TRANSCRITOR_OLLAMA_URL, padrão http://localhost:11434) - nenhum dado é
enviado à internet ou a terceiros. Sem essa configuração, os campos
narrativos da ata (assuntos tratados, decisões, pendências) simplesmente
ficam em branco para preenchimento manual.
"""
import json
import urllib.error
import urllib.request

from ..config import settings


class OllamaIndisponivelError(RuntimeError):
    """O serviço local Ollama não está habilitado, acessível, ou não respondeu."""


def gerar_texto(prompt: str, timeout: int = 180) -> str:
    if not settings.ollama_habilitado:
        raise OllamaIndisponivelError("Rascunho por IA local desabilitado nesta instalação.")

    payload = json.dumps({
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode("utf-8")

    requisicao = urllib.request.Request(
        f"{settings.ollama_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            corpo = json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OllamaIndisponivelError(
            f"Não foi possível conectar ao Ollama local em {settings.ollama_url}. "
            "Verifique se o aplicativo está em execução."
        ) from exc
    except json.JSONDecodeError as exc:
        raise OllamaIndisponivelError("Resposta inválida do Ollama local.") from exc

    texto = (corpo.get("response") or "").strip()
    if not texto:
        raise OllamaIndisponivelError("O modelo local não retornou nenhum texto.")
    return texto
