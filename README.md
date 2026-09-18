# Transcritor CTCE

Ferramenta institucional de transcrição automática de reuniões, desenvolvida
para a Corregedoria Tributária de Controle Externo (CTCE) — SEFAZ-RJ.

Transforma gravações de áudio/vídeo em transcrições organizadas, com
processamento **local/offline** (sem envio de áudio ou texto a serviços
externos de IA), revisão humana e exportação em documento profissional.

## Status: MVP — Fases 1, 2 e 3 do roadmap

Implementado nesta versão:
- Upload de áudio/vídeo (MP3, WAV, M4A, MP4, WEBM, OGG, AAC, MOV, MKV);
- extração automática de áudio de arquivos de vídeo (ffmpeg);
- transcrição local com timestamps (faster-whisper);
- sinalização de trechos com baixa confiança para revisão;
- editor de revisão (editar, dividir, unir e excluir trechos);
- **diarização opcional** (identificação de participantes) via
  pyannote.audio — desabilitada por padrão, requer configuração explícita
  (ver `docs/INSTALACAO.md`);
- **quadro de participantes**: nomeie cada participante uma única vez e o
  nome se propaga automaticamente para todos os trechos vinculados a ele
  (vínculo por ID, não por texto — não se perde mais ao editar);
- **dicionário institucional de termos** (siglas, nomes, expressões) usado
  para orientar o reconhecimento de fala;
- histórico de reuniões com busca por título e filtro por status;
- exportação em DOCX e TXT;
- opção de excluir o áudio original após o processamento;
- registro de eventos (upload, processamento, exportação, exclusão,
  diarização indisponível);
- **Ata/Relatório**, documento separado da transcrição, com objetivo,
  assuntos tratados, decisões e pendências (editáveis pelo usuário);
- **Encaminhamentos** extraídos automaticamente por padrões de texto
  (responsável, prazo e status), sempre editáveis, nunca inventados —
  campos não identificados aparecem como "Não identificado";
- **rascunho de ata por IA local (opcional)** via Ollama — desabilitado
  por padrão, sempre marcado como rascunho sujeito a revisão;
- exportação da ata em DOCX.

**Ainda não implementado** (fase seguinte do roadmap, ver
`docs/ARQUITETURA.md`): autenticação e controle de acesso (Fase 4);
exportação em PDF (transcrição e ata).

## Documentação

- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — arquitetura, decisões
  técnicas e estratégia de sigilo.
- [`docs/INSTALACAO.md`](docs/INSTALACAO.md) — instalação e execução local
  no Windows.

## Início rápido

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Acesse http://127.0.0.1:8000
