"""Geração de transcrição em formato TXT simples."""
from ..database import Reuniao


def _formatar_tempo(segundos: float) -> str:
    segundos = int(segundos)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def gerar_txt_transcricao(reuniao: Reuniao) -> str:
    linhas = [
        f"TRANSCRIÇÃO - {reuniao.titulo}",
        f"Arquivo original: {reuniao.nome_arquivo_original}",
        f"Data de processamento: {reuniao.criado_em.strftime('%d/%m/%Y %H:%M')}",
    ]
    if reuniao.duracao_segundos:
        linhas.append(f"Duração: {_formatar_tempo(reuniao.duracao_segundos)}")
    linhas.append("")
    linhas.append("-" * 60)
    linhas.append("")

    for segmento in reuniao.segmentos:
        prefixo = f"[{_formatar_tempo(segmento.inicio_segundos)}]"
        if segmento.falante:
            prefixo += f" {segmento.falante}:"
        texto = segmento.texto
        if segmento.baixa_confianca:
            texto += " [trecho com baixa confiança - revisar]"
        linhas.append(f"{prefixo} {texto}")

    return "\n".join(linhas)
