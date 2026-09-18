# Arquitetura — Transcritor CTCE

Ferramenta institucional de transcrição automática de reuniões para a
Corregedoria Tributária de Controle Externo (CTCE) — SEFAZ-RJ, com foco em
**sigilo, processamento local e fidelidade ao conteúdo falado**.

## 1. Princípio de sigilo

O requisito não negociável do projeto é que **áudio e transcrições não sejam
enviados a serviços externos de IA**. A arquitetura reflete isso:

- A transcrição roda com **faster-whisper**, executado no próprio processo
  Python, usando o modelo carregado em memória local (CPU ou GPU).
- Nenhuma chamada de rede é feita com o conteúdo da reunião.
- **Única exceção, e apenas uma vez por modelo**: o download dos *pesos* do
  modelo (não do áudio) via Hugging Face Hub, na primeira vez que aquele
  modelo é usado. Esse download é cacheado localmente (`~/.cache/huggingface`
  por padrão). Para ambientes sem acesso à internet, é possível apontar
  `TRANSCRITOR_WHISPER_MODEL` para uma pasta local com o modelo já baixado
  manualmente em outra máquina — nesse caso, o sistema roda 100% air-gapped.
- Arquivos de áudio ficam em `backend/storage/`, fora do controle de versão
  (`.gitignore`), e podem ser excluídos automaticamente após o processamento
  (opção "Excluir áudio original após o processamento").

## 2. Visão geral dos componentes

```
Navegador (frontend HTML/CSS/JS)
        │  HTTP (upload, polling de status, edição de segmentos, exportação)
        ▼
FastAPI (backend/app)
        │
        ├── routers/meetings.py     → endpoints REST
        ├── jobs.py                 → processamento em thread (background)
        ├── services/audio.py       → ffmpeg/ffprobe (extração/duração)
        ├── services/transcription.py → faster-whisper (transcrição local)
        ├── services/docx_export.py / txt_export.py
        └── database.py             → SQLite (SQLAlchemy)
```

## 3. Fluxo do MVP (Fase 1)

1. Upload do arquivo → salvo em `backend/storage/uploads/{id}/`.
2. Um registro `Reuniao` é criado no banco com status `pendente`.
3. Uma thread de processamento é iniciada:
   - extrai o áudio (WAV mono 16kHz) via ffmpeg;
   - transcreve localmente com faster-whisper, gerando segmentos com
     timestamp;
   - marca trechos de baixa confiança (`avg_logprob` / `no_speech_prob`)
     para revisão humana, sem tentar "adivinhar" o conteúdo;
   - aplica limpeza leve de forma (pontuação/espaços/capitalização e remoção
     de repetições óbvias de reconhecimento) — nunca altera o sentido.
4. O frontend consulta `/status` a cada poucos segundos e atualiza a barra
   de progresso e a etapa atual.
5. Ao concluir, o usuário revisa os segmentos (editar texto, dividir, unir,
   excluir, incluir) e exporta em DOCX ou TXT.

## 4. Fase 2: diarização e dicionário institucional

- **Diarização (identificação de participantes)**: implementada via
  `pyannote.audio`, mas **desabilitada por padrão**
  (`TRANSCRITOR_DIARIZACAO_HABILITADA=false`). Motivo da transparência
  exigida: o modelo `pyannote/speaker-diarization-3.1` é *gated* no
  Hugging Face — habilitar a funcionalidade exige criar uma conta
  gratuita, aceitar os termos de uso do modelo e gerar um token de acesso
  (`TRANSCRITOR_HF_TOKEN`). Como no faster-whisper, **apenas os pesos do
  modelo são baixados uma única vez**; o áudio da reunião nunca sai da
  máquina. Sem essa configuração, a ferramenta funciona normalmente sem
  diarização — o job de processamento degrada graciosamente (registra o
  evento `diarizacao_indisponivel` e segue sem interromper a transcrição).
  Os segmentos de fala são associados ao participante com maior
  sobreposição temporal (`services/diarization.py::atribuir_falantes`);
  sem sobreposição, o segmento fica sem rótulo — nunca se "adivinha" um
  participante sem evidência.
- **Dicionário institucional**: termos cadastrados pelo usuário (siglas,
  nomes, cargos) são usados como `initial_prompt` do faster-whisper, uma
  técnica padrão para influenciar a probabilidade de reconhecimento de
  determinado vocabulário — não insere texto que não foi falado.
- **Renomeação de participantes**: `POST /api/meetings/{id}/participantes/renomear`
  propaga o novo nome para todos os segmentos daquele participante na
  reunião.

## 5. O que NÃO está no MVP (por decisão de escopo, não por esquecimento)

- **Geração de ata/relatório e extração de encaminhamentos** — Fase 3.
- **Autenticação, controle de acesso, logs de acesso por usuário,
  PostgreSQL** — Fase 4.
- **Exportação em PDF** — planejada, ainda não implementada.
- **Migrações de banco**: o MVP usa `Base.metadata.create_all` (cria
  tabelas ausentes, não altera colunas existentes). Adequado para uso
  local sem dados críticos acumulados; Alembic fica previsto para a Fase 4
  (uso multiusuário com PostgreSQL).

## 6. Requisitos de hardware

| Recurso | Mínimo | Recomendado |
|---|---|---|
| RAM | 8 GB | 16 GB (para modelo `medium`) |
| GPU | Não obrigatória | Opcional (acelera bastante com CUDA) |
| Disco | ~5 GB livres | 10 GB+ (modelo + áudios temporários) |
| CPU | 4 núcleos | 8+ núcleos |

## 7. Riscos técnicos conhecidos

- **Desempenho em CPU**: reuniões de 2h+ podem levar bastante tempo em
  máquinas sem GPU. Mitigado com processamento em background (não trava a
  interface) — mas o usuário deve ter essa expectativa de tempo. A
  diarização adiciona uma etapa extra de processamento quando habilitada.
- **Qualidade de diarização local**: soluções open source ainda ficam atrás
  de serviços comerciais, especialmente com sobreposição de falas ou
  áudio de baixa qualidade. Por isso a interface trata o resultado como
  estimativa a ser revisada, nunca como fato definitivo.
- **Dependência do ffmpeg**: é um binário externo (não pip), precisa ser
  instalado separadamente no servidor/máquina — documentado em
  `docs/INSTALACAO.md`, com mensagem de erro clara caso ausente.
- **Peso das dependências de diarização**: `pyannote.audio` traz PyTorch
  como dependência transitiva (centenas de MB). Por isso fica em
  `requirements-diarizacao.txt` separado, instalado apenas por quem for
  habilitar a funcionalidade.

## 8. Estratégia de segurança (MVP → evolução)

- MVP (Fase 1): sem autenticação — destinado a uso local/individual. Isso é
  uma limitação conhecida e documentada, não uma omissão silenciosa.
- Já implementado desde o MVP: registro de eventos (`logs_eventos`) para
  upload, processamento, exportação e exclusão de arquivos, com timestamp;
  opção de exclusão do áudio original após processamento.
- Fase 4: autenticação, sessões, controle de acesso por usuário/perfil,
  registro do usuário responsável por cada processamento, migração para
  PostgreSQL para uso multiusuário.
