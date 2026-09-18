"""Geração do rascunho de Ata/Relatório a partir da transcrição revisada.

O documento final é sempre editável pelo usuário. Esta função apenas tenta
preencher um rascunho inicial das seções narrativas (Assuntos tratados,
Decisões, Pendências) usando um modelo de linguagem local via Ollama -
somente se TRANSCRITOR_OLLAMA_HABILITADO estiver configurado. Sem essa
configuração, retorna None e as seções ficam em branco para preenchimento
manual (comportamento padrão, sem qualquer dependência adicional).
"""
from . import ollama_client

_PROMPT_TEMPLATE = """Você está organizando a ata de uma reunião administrativa da \
Corregedoria Tributária de Controle Externo (CTCE). Abaixo está a transcrição \
literal da reunião, com marcação de tempo.

REGRAS OBRIGATÓRIAS:
- Baseie-se SOMENTE no texto abaixo. NUNCA invente fatos, decisões, nomes, \
prazos ou responsáveis que não estejam explicitamente no texto.
- Se um tópico não estiver claro na transcrição, não o inclua.
- Não registre algo como "decisão" se foi apenas uma opinião, dúvida ou sugestão.
- Use linguagem institucional, objetiva, sem floreios.

TRANSCRIÇÃO:
{transcricao}

Gere três seções separadas EXATAMENTE pelos marcadores abaixo, em texto simples (sem markdown):

###ASSUNTOS_TRATADOS###
(temas efetivamente discutidos, um por linha, iniciando com "- ")

###DECISOES###
(decisões e deliberações efetivamente tomadas, um por linha iniciando com "- "; \
se nenhuma decisão foi tomada, escreva apenas "Nenhuma decisão formal identificada nesta reunião.")

###PENDENCIAS###
(assuntos que ficaram em aberto ou precisam de acompanhamento, um por linha iniciando com "- "; \
se não houver, escreva "Nenhuma pendência identificada.")
"""

_MARCADORES = ["###ASSUNTOS_TRATADOS###", "###DECISOES###", "###PENDENCIAS###"]
_CHAVES = ["assuntos_tratados", "decisoes", "pendencias"]


def _formatar_tempo(segundos: float) -> str:
    segundos = int(segundos)
    return f"{segundos // 60:02d}:{segundos % 60:02d}"


def _montar_transcricao_texto(segmentos) -> str:
    linhas = []
    for s in segmentos:
        prefixo = f"[{_formatar_tempo(s.inicio_segundos)}]"
        if s.falante:
            prefixo += f" {s.falante}:"
        linhas.append(f"{prefixo} {s.texto}")
    return "\n".join(linhas)


def _parse_secoes(texto: str) -> dict[str, str]:
    posicoes = {m: texto.find(m) for m in _MARCADORES}
    resultado = {}
    for marcador, chave in zip(_MARCADORES, _CHAVES):
        inicio = posicoes[marcador]
        if inicio == -1:
            resultado[chave] = ""
            continue
        inicio += len(marcador)
        seguintes = [p for p in posicoes.values() if p > posicoes[marcador]]
        fim = min(seguintes) if seguintes else len(texto)
        resultado[chave] = texto[inicio:fim].strip()
    return resultado


def gerar_rascunho_ia(segmentos) -> dict[str, str] | None:
    """Retorna {"assuntos_tratados", "decisoes", "pendencias"}, ou None se o
    serviço local de IA não estiver disponível (degradação graciosa - não
    interrompe a geração da ata, apenas deixa os campos em branco)."""
    try:
        transcricao = _montar_transcricao_texto(segmentos)
        prompt = _PROMPT_TEMPLATE.format(transcricao=transcricao)
        resposta = ollama_client.gerar_texto(prompt)
        return _parse_secoes(resposta)
    except ollama_client.OllamaIndisponivelError:
        return None
