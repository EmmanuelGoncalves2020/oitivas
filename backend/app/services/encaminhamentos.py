"""Extração heurística de encaminhamentos a partir da transcrição.

IMPORTANTE: esta é uma extração baseada em padrões de texto (regex),
NÃO uma análise semântica. Ela identifica apenas frases que contêm
marcadores linguísticos típicos de compromisso/ação (ex.: "vamos
verificar", "fica responsável por") e, quando explicitamente presentes no
próprio texto, um possível responsável e prazo. Nada é inferido além do
que está escrito na transcrição - quando responsável ou prazo não são
encontrados, o campo correspondente fica em branco ("Não identificado" na
interface), nunca preenchido por suposição.

Os resultados devem sempre ser tratados como sugestões para revisão
humana, complementadas ou corrigidas manualmente pelo usuário.
"""
import re
from dataclasses import dataclass

_VERBOS_ACAO = [
    "verificar", "providenciar", "encaminhar", "enviar", "elaborar",
    "levantar", "revisar", "conferir", "acompanhar", "apresentar",
    "marcar", "agendar", "confirmar", "atualizar", "corrigir", "resolver",
    "concluir", "finalizar", "preparar", "entregar", "analisar",
    "consultar", "informar", "notificar", "convocar", "instaurar",
    "redigir", "protocolar", "distribuir",
]

_MARCADORES_COMPROMISSO = [
    "vou", "vamos", "vai", "irá", "iremos", "precisa", "precisamos",
    "deve", "devemos", "fica", "ficará", "ficou", "é necessário",
    "temos que", "tem que", "pode", "poderia", "consegue",
]

_PADRAO_ACAO = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in _MARCADORES_COMPROMISSO) + r")\b"
    r"[^.!?]{0,80}?\b(" + "|".join(_VERBOS_ACAO) + r")\w*",
    re.IGNORECASE,
)

_PADRAO_DATA = re.compile(
    r"\b(até\s+(?:o\s+dia\s+)?\d{1,2}(?:/\d{1,2}(?:/\d{2,4})?)?(?:\s+de\s+\w+)?"
    r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?"
    r"|até\s+(?:segunda|ter[cç]a|quarta|quinta|sexta|s[áa]bado|domingo)(?:-feira)?"
    r"|pr[óo]xima\s+(?:semana|segunda|ter[cç]a|quarta|quinta|sexta)"
    r"|amanh[ãa]|ainda\s+esta\s+semana|at[ée]\s+o\s+final\s+do\s+m[êe]s)\b",
    re.IGNORECASE,
)

_PADRAO_PRIMEIRA_PESSOA = re.compile(r"\bvou\b", re.IGNORECASE)


@dataclass
class EncaminhamentoCandidato:
    descricao: str
    responsavel: str | None
    prazo: str | None
    segmento_id: str


def _dividir_sentencas(texto: str) -> list[str]:
    partes = re.split(r"(?<=[.!?])\s+", texto)
    return [p.strip() for p in partes if p.strip()]


def extrair_candidatos(segmentos, nomes_participantes: list[str]) -> list[EncaminhamentoCandidato]:
    """segmentos: iterável de objetos com atributos .id, .texto e .falante."""
    candidatos: list[EncaminhamentoCandidato] = []
    nomes_validos = [n for n in nomes_participantes if n]

    for segmento in segmentos:
        for sentenca in _dividir_sentencas(segmento.texto):
            if not _PADRAO_ACAO.search(sentenca):
                continue

            responsavel = None
            for nome in nomes_validos:
                if re.search(rf"\b{re.escape(nome)}\b", sentenca, re.IGNORECASE):
                    responsavel = nome
                    break
            if responsavel is None and segmento.falante and _PADRAO_PRIMEIRA_PESSOA.search(sentenca):
                responsavel = segmento.falante

            match_data = _PADRAO_DATA.search(sentenca)
            prazo = match_data.group(0) if match_data else None

            candidatos.append(EncaminhamentoCandidato(
                descricao=sentenca,
                responsavel=responsavel,
                prazo=prazo,
                segmento_id=segmento.id,
            ))

    return candidatos
