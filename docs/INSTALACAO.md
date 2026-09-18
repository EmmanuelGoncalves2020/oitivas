# Instalação — Transcritor CTCE (Windows)

Guia para rodar o Transcritor CTCE localmente, sem depender de serviços
externos de IA.

## Requisitos

- **Sistema operacional**: Windows 10/11 (64 bits).
- **RAM**: mínimo 8 GB; recomendado 16 GB se for usar o modelo `medium`.
- **GPU**: não é obrigatória. Sem GPU, o processamento roda em CPU (mais
  lento, mas funcional). Se houver GPU NVIDIA com CUDA, o processamento é
  significativamente mais rápido.
- **Disco**: ao menos 5 GB livres (modelo de transcrição + áudios
  temporários das reuniões).
- **Python**: versão 3.10 ou 3.11.
- **ffmpeg**: necessário para extrair áudio de vídeos e ler a duração dos
  arquivos.

## 1. Instalar o Python

Baixe em https://www.python.org/downloads/ (marque a opção "Add Python to
PATH" durante a instalação).

Verifique no PowerShell:
```powershell
python --version
```

## 2. Instalar o ffmpeg

Opção mais simples, via `winget`:
```powershell
winget install Gyan.FFmpeg
```
Ou baixe manualmente em https://www.gyan.dev/ffmpeg/builds/ e adicione a
pasta `bin` ao PATH do Windows.

Verifique:
```powershell
ffmpeg -version
ffprobe -version
```

## 3. Obter o projeto

Copie/clone a pasta do projeto (`oitivas`) para a máquina local, por exemplo
em `C:\Transcritor-CTCE`.

## 4. Criar o ambiente virtual e instalar dependências

```powershell
cd C:\Transcritor-CTCE\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 5. Sobre o modelo de transcrição (faster-whisper)

Na primeira execução, o `faster-whisper` baixa automaticamente os pesos do
modelo configurado (padrão: `small`) a partir do Hugging Face Hub — **apenas
o modelo, nunca o áudio das reuniões**. Esse download acontece uma única vez
e fica em cache local (`%USERPROFILE%\.cache\huggingface`).

- Se a máquina **tiver acesso à internet** apenas nessa etapa inicial, nada
  mais precisa ser feito.
- Se a máquina for **totalmente isolada da internet (air-gapped)**, baixe o
  modelo em outra máquina e copie a pasta de cache, ou defina a variável de
  ambiente `TRANSCRITOR_WHISPER_MODEL` apontando para o caminho local do
  modelo já convertido para CTranslate2.

Modelos disponíveis (compromisso entre velocidade e qualidade):
`tiny`, `base`, `small` (padrão), `medium`, `large-v3`.

## 6. Iniciar o servidor

Ainda dentro de `backend`, com o ambiente virtual ativado:
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 7. Acessar a ferramenta

Abra o navegador em: **http://127.0.0.1:8000**

## 8. Parar o servidor

No terminal onde o `uvicorn` está rodando, pressione `Ctrl + C`.

## Variáveis de ambiente úteis (opcionais)

| Variável | Padrão | Descrição |
|---|---|---|
| `TRANSCRITOR_WHISPER_MODEL` | `small` | Nome do modelo ou caminho local |
| `TRANSCRITOR_WHISPER_DEVICE` | `cpu` | `cpu` ou `cuda` |
| `TRANSCRITOR_WHISPER_COMPUTE_TYPE` | `int8` | `int8` (CPU) ou `float16` (GPU) |
| `TRANSCRITOR_WHISPER_LANGUAGE` | `pt` | Idioma da transcrição |
| `TRANSCRITOR_DIARIZACAO_HABILITADA` | `false` | Habilita a identificação de participantes |
| `TRANSCRITOR_HF_TOKEN` | (vazio) | Token do Hugging Face (necessário para diarização) |

## 9. Habilitar diarização (identificação de participantes) — opcional

Por padrão, a diarização vem **desabilitada**. Para habilitá-la:

1. Crie uma conta gratuita em https://huggingface.co.
2. Acesse a página do modelo `pyannote/speaker-diarization-3.1` e aceite os
   termos de uso (e do modelo `pyannote/segmentation-3.0`, do qual ele
   depende — a própria página indica).
3. Gere um token em *Settings > Access Tokens* (permissão de leitura já
   basta).
4. Instale as dependências adicionais (bibliotecas pesadas, incluem
   PyTorch):
   ```powershell
   pip install -r requirements-diarizacao.txt
   ```
5. Configure as variáveis de ambiente antes de iniciar o servidor:
   ```powershell
   $env:TRANSCRITOR_DIARIZACAO_HABILITADA = "true"
   $env:TRANSCRITOR_HF_TOKEN = "hf_xxx..."
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

**O que isso envia para fora da máquina**: apenas o download único dos
pesos dos modelos de diarização, feito pela biblioteca `pyannote.audio` a
partir do Hugging Face Hub na primeira execução — nunca o áudio das
reuniões. Sem essa configuração, a ferramenta funciona normalmente, apenas
sem identificação de participantes.

Exemplo, usando GPU:
```powershell
$env:TRANSCRITOR_WHISPER_DEVICE = "cuda"
$env:TRANSCRITOR_WHISPER_COMPUTE_TYPE = "float16"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Solução de problemas comuns

- **"ffmpeg/ffprobe não foi encontrado"**: reinstale o ffmpeg e confirme que
  a pasta `bin` está no PATH (reabra o terminal após instalar).
- **Processamento muito lento**: use um modelo menor (`base` ou `tiny`) ou,
  se disponível, ative o uso de GPU.
- **Erro de memória ao carregar o modelo**: use um modelo menor (`small` ou
  `base`) ou aumente a RAM disponível.
- **"Formato não suportado"**: confira a lista de formatos aceitos na tela
  de upload (MP3, WAV, M4A, MP4, WEBM, OGG, AAC, MOV, MKV).
