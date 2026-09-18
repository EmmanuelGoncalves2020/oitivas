/* Transcritor CTCE - frontend (vanilla JS, sem dependências externas) */
"use strict";

const API = "/api/meetings";
const API_DICIONARIO = "/api/dicionario";

const views = {
  home: document.getElementById("view-home"),
  upload: document.getElementById("view-upload"),
  processando: document.getElementById("view-processando"),
  revisao: document.getElementById("view-revisao"),
  dicionario: document.getElementById("view-dicionario"),
  ata: document.getElementById("view-ata"),
};

let capacidades = { diarizacao_disponivel: false };

function mostrarView(nome) {
  Object.values(views).forEach((v) => v.classList.add("hidden"));
  views[nome].classList.remove("hidden");
}

function formatarTempo(segundosTotais) {
  if (segundosTotais == null || isNaN(segundosTotais)) return "--:--";
  const s = Math.floor(segundosTotais);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

function formatarTamanho(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatarData(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

// ---------------------------------------------------------------------------
// SALVAMENTO AUTOMÁTICO
//
// Campos de texto (segmentos, ata, encaminhamentos) salvam sozinhos pouco
// depois de parar de digitar, e imediatamente ao sair do campo - assim uma
// edição nunca se perde por esquecer de clicar em "Salvar". O botão de
// salvar continua existindo como confirmação explícita, mas deixa de ser
// obrigatório.
// ---------------------------------------------------------------------------

const ATRASO_AUTOSAVE_MS = 900;
const temporizadoresAutosave = new Map();

function agendarAutosave(chave, executar, elementoStatus) {
  if (elementoStatus) elementoStatus.textContent = "Alterações não salvas...";
  if (temporizadoresAutosave.has(chave)) clearTimeout(temporizadoresAutosave.get(chave));
  const timer = setTimeout(() => {
    temporizadoresAutosave.delete(chave);
    executarAutosave(executar, elementoStatus);
  }, ATRASO_AUTOSAVE_MS);
  temporizadoresAutosave.set(chave, timer);
}

function flushAutosave(chave, executar, elementoStatus) {
  if (temporizadoresAutosave.has(chave)) {
    clearTimeout(temporizadoresAutosave.get(chave));
    temporizadoresAutosave.delete(chave);
  }
  return executarAutosave(executar, elementoStatus);
}

async function executarAutosave(executar, elementoStatus) {
  if (elementoStatus) elementoStatus.textContent = "Salvando...";
  try {
    await executar();
    if (elementoStatus) {
      elementoStatus.textContent = "Salvo";
      elementoStatus.classList.remove("status-erro");
      setTimeout(() => { if (elementoStatus.textContent === "Salvo") elementoStatus.textContent = ""; }, 2000);
    }
  } catch (erro) {
    if (elementoStatus) {
      elementoStatus.textContent = `Não foi possível salvar: ${erro.message}`;
      elementoStatus.classList.add("status-erro");
    }
  }
}

async function apiFetch(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, opcoes);
  if (!resposta.ok) {
    let detalhe = "Ocorreu um erro inesperado.";
    try {
      const corpo = await resposta.json();
      detalhe = corpo.detail || detalhe;
    } catch (_) { /* resposta sem corpo JSON */ }
    throw new Error(detalhe);
  }
  const tipo = resposta.headers.get("content-type") || "";
  if (tipo.includes("application/json")) return resposta.json();
  return resposta;
}

// ---------------------------------------------------------------------------
// HISTÓRICO
// ---------------------------------------------------------------------------

const BADGES = {
  concluida: ["Concluída", "badge-concluida"],
  processando: ["Processando", "badge-processando"],
  pendente: ["Pendente", "badge-pendente"],
  erro: ["Erro", "badge-erro"],
  cancelada: ["Cancelada", "badge-erro"],
};

async function carregarHistorico() {
  const busca = document.getElementById("busca-historico").value;
  const status = document.getElementById("filtro-status-historico").value;
  const corpo = document.getElementById("tabela-historico-body");
  const vazio = document.getElementById("historico-vazio");

  const params = new URLSearchParams();
  if (busca) params.set("busca", busca);
  if (status) params.set("status", status);
  const query = params.toString() ? `?${params.toString()}` : "";
  const reunioes = await apiFetch(`${API}${query}`);

  corpo.innerHTML = "";
  vazio.classList.toggle("hidden", reunioes.length > 0);

  for (const r of reunioes) {
    const [rotulo, classe] = BADGES[r.status] || ["-", "badge-pendente"];
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatarData(r.criado_em)}</td>
      <td>${escaparHtml(r.titulo)}</td>
      <td>${r.duracao_segundos ? formatarTempo(r.duracao_segundos) : "-"}</td>
      <td><span class="badge ${classe}">${rotulo}</span></td>
      <td><a class="link-acao" data-id="${r.id}" data-status="${r.status}">Visualizar</a></td>
    `;
    corpo.appendChild(tr);
  }

  corpo.querySelectorAll(".link-acao").forEach((link) => {
    link.addEventListener("click", () => abrirReuniao(link.dataset.id, link.dataset.status));
  });
}

function escaparHtml(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

function abrirReuniao(id, status) {
  if (status === "processando" || status === "pendente") {
    acompanharProcessamento(id);
  } else {
    abrirRevisao(id);
  }
}

document.getElementById("busca-historico").addEventListener("input", () => carregarHistorico());
document.getElementById("filtro-status-historico").addEventListener("change", () => carregarHistorico());

// ---------------------------------------------------------------------------
// NOVA TRANSCRIÇÃO / UPLOAD
// ---------------------------------------------------------------------------

let arquivoSelecionado = null;
let duracaoSelecionada = null;

document.getElementById("btn-nova").addEventListener("click", () => {
  resetarFormularioUpload();
  document.getElementById("linha-diarizacao").classList.toggle("hidden", !capacidades.diarizacao_disponivel);
  document.getElementById("aviso-diarizacao-indisponivel").classList.toggle("hidden", capacidades.diarizacao_disponivel);
  mostrarView("upload");
});

document.getElementById("btn-cancelar-upload").addEventListener("click", () => {
  resetarFormularioUpload();
  mostrarView("home");
});

function resetarFormularioUpload() {
  arquivoSelecionado = null;
  duracaoSelecionada = null;
  document.getElementById("input-arquivo").value = "";
  document.getElementById("arquivo-info").classList.add("hidden");
  document.getElementById("input-titulo").value = "";
  document.getElementById("input-excluir-audio").checked = false;
  document.getElementById("input-diarizacao").checked = false;
}

document.getElementById("input-arquivo").addEventListener("change", async (e) => {
  const arquivo = e.target.files[0];
  if (!arquivo) return;
  arquivoSelecionado = arquivo;

  document.getElementById("info-nome").textContent = arquivo.name;
  document.getElementById("info-tamanho").textContent = formatarTamanho(arquivo.size);
  document.getElementById("info-formato").textContent = arquivo.name.split(".").pop().toUpperCase();
  document.getElementById("info-duracao").textContent = "calculando...";
  document.getElementById("input-titulo").value = arquivo.name.replace(/\.[^/.]+$/, "");
  document.getElementById("arquivo-info").classList.remove("hidden");

  duracaoSelecionada = await estimarDuracaoLocal(arquivo);
  document.getElementById("info-duracao").textContent = duracaoSelecionada
    ? formatarTempo(duracaoSelecionada)
    : "não disponível (será calculada no processamento)";
});

function estimarDuracaoLocal(arquivo) {
  return new Promise((resolve) => {
    const elemento = arquivo.type.startsWith("video") ? document.createElement("video") : document.createElement("audio");
    elemento.preload = "metadata";
    elemento.onloadedmetadata = () => {
      URL.revokeObjectURL(elemento.src);
      resolve(isFinite(elemento.duration) ? elemento.duration : null);
    };
    elemento.onerror = () => resolve(null);
    elemento.src = URL.createObjectURL(arquivo);
  });
}

document.getElementById("btn-iniciar").addEventListener("click", async () => {
  if (!arquivoSelecionado) return;
  const botao = document.getElementById("btn-iniciar");
  botao.disabled = true;
  botao.textContent = "Enviando...";

  const formData = new FormData();
  formData.append("arquivo", arquivoSelecionado);
  formData.append("titulo", document.getElementById("input-titulo").value || arquivoSelecionado.name);
  formData.append("excluir_audio_apos_processar", document.getElementById("input-excluir-audio").checked);
  formData.append("usar_diarizacao", capacidades.diarizacao_disponivel && document.getElementById("input-diarizacao").checked);

  try {
    const reuniao = await apiFetch(`${API}/upload`, { method: "POST", body: formData });
    acompanharProcessamento(reuniao.id, reuniao.titulo);
  } catch (erro) {
    alert(`Não foi possível enviar o arquivo: ${erro.message}`);
  } finally {
    botao.disabled = false;
    botao.textContent = "Iniciar transcrição";
  }
});

// ---------------------------------------------------------------------------
// PROCESSAMENTO (POLLING DE STATUS)
// ---------------------------------------------------------------------------

let intervalPolling = null;
let inicioProcessamento = null;
let intervalCronometro = null;

function acompanharProcessamento(id, titulo) {
  mostrarView("processando");
  document.getElementById("processando-titulo").textContent = titulo
    ? `Processando "${titulo}"...`
    : "Processando reunião...";
  document.getElementById("processando-erro").classList.add("hidden");
  document.getElementById("btn-voltar-home").classList.add("hidden");
  inicioProcessamento = Date.now();

  atualizarCronometro();
  intervalCronometro = setInterval(atualizarCronometro, 1000);

  const verificar = async () => {
    try {
      const st = await apiFetch(`${API}/${id}/status`);
      document.getElementById("barra-progresso-fill").style.width = `${st.progresso_percentual}%`;
      document.getElementById("processando-etapa").textContent = st.etapa_atual || "Processando...";
      document.getElementById("processando-percentual").textContent = `${st.progresso_percentual}%`;

      if (st.status === "concluida") {
        pararPolling();
        abrirRevisao(id);
      } else if (st.status === "erro") {
        pararPolling();
        const el = document.getElementById("processando-erro");
        el.textContent = st.mensagem_erro || "Ocorreu um erro durante o processamento.";
        el.classList.remove("hidden");
        document.getElementById("btn-voltar-home").classList.remove("hidden");
      }
    } catch (erro) {
      pararPolling();
      const el = document.getElementById("processando-erro");
      el.textContent = `Falha ao consultar o status do processamento: ${erro.message}`;
      el.classList.remove("hidden");
      document.getElementById("btn-voltar-home").classList.remove("hidden");
    }
  };

  verificar();
  intervalPolling = setInterval(verificar, 2000);
}

function pararPolling() {
  if (intervalPolling) clearInterval(intervalPolling);
  if (intervalCronometro) clearInterval(intervalCronometro);
  intervalPolling = null;
  intervalCronometro = null;
}

function atualizarCronometro() {
  const decorrido = Math.floor((Date.now() - inicioProcessamento) / 1000);
  document.getElementById("processando-tempo").textContent = `Tempo decorrido: ${formatarTempo(decorrido)}`;
}

document.getElementById("btn-voltar-home").addEventListener("click", () => {
  mostrarView("home");
  carregarHistorico();
});

// ---------------------------------------------------------------------------
// REVISÃO / EDITOR DE TRANSCRIÇÃO
// ---------------------------------------------------------------------------

let reuniaoAtual = null;
let participantesAtuais = [];

async function abrirRevisao(id) {
  mostrarView("revisao");
  const lista = document.getElementById("lista-segmentos");
  lista.innerHTML = "<p class='texto-vazio'>Carregando transcrição...</p>";

  const [reuniao, participantes] = await Promise.all([
    apiFetch(`${API}/${id}`),
    apiFetch(`${API}/${id}/participantes`),
  ]);
  reuniaoAtual = reuniao;
  participantesAtuais = participantes;

  document.getElementById("revisao-titulo").textContent = reuniaoAtual.titulo;
  document.getElementById("revisao-meta").textContent =
    `${formatarData(reuniaoAtual.criado_em)} · Duração: ${formatarTempo(reuniaoAtual.duracao_segundos)} ` +
    `· ${reuniaoAtual.segmentos.length} segmentos`;

  atualizarAvisoDiarizacao();
  renderizarParticipantes();
  renderizarSegmentos();
}

function atualizarAvisoDiarizacao() {
  const aviso = document.getElementById("aviso-diarizacao");
  if (reuniaoAtual.diarizacao_disponivel) {
    aviso.textContent = "Participantes identificados automaticamente (diarização) — a separação por voz é uma estimativa e pode conter imprecisões. Revise abaixo.";
    aviso.classList.remove("hidden");
    aviso.classList.add("sucesso");
  } else if (reuniaoAtual.diarizacao_solicitada) {
    aviso.textContent = "A identificação automática de participantes foi solicitada, mas não pôde ser concluída nesta reunião. Use o quadro abaixo para atribuir os participantes manualmente.";
    aviso.classList.remove("hidden", "sucesso");
  } else {
    aviso.classList.add("hidden");
  }
}

// --- Quadro de participantes -------------------------------------------
// Nomear um participante aqui propaga automaticamente para todos os
// segmentos vinculados a ele (por ID, nunca por comparação de texto).

function renderizarParticipantes() {
  const lista = document.getElementById("lista-participantes");
  lista.innerHTML = "";

  if (participantesAtuais.length === 0) {
    lista.innerHTML = "<p class='texto-vazio texto-vazio-compacto'>Nenhum participante cadastrado. Adicione abaixo para poder atribuí-los aos trechos da transcrição.</p>";
  }

  participantesAtuais.forEach((p) => {
    const item = document.createElement("div");
    item.className = "item-participante";
    item.innerHTML = `
      <input type="text" class="input-nome-participante" value="${escaparHtml(p.nome)}" />
      <span class="status-autosave" aria-live="polite"></span>
      <button class="btn-icone btn-icone-perigo" data-acao="excluir" title="Excluir participante">Excluir</button>
    `;
    const input = item.querySelector(".input-nome-participante");
    const status = item.querySelector(".status-autosave");

    input.addEventListener("input", () => {
      p.nome = input.value; // mantém o estado local sempre atual, mesmo antes de salvar
      agendarAutosave(`participante-${p.id}`, () => renomearParticipante(p.id, input.value), status);
    });
    input.addEventListener("blur", () => flushAutosave(`participante-${p.id}`, () => renomearParticipante(p.id, input.value), status));
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); });

    item.querySelector('[data-acao="excluir"]').addEventListener("click", () => excluirParticipante(p.id));
    lista.appendChild(item);
  });
}

document.getElementById("btn-adicionar-participante").addEventListener("click", async () => {
  try {
    const novo = await apiFetch(`${API}/${reuniaoAtual.id}/participantes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    participantesAtuais.push(novo);
    renderizarParticipantes();
    renderizarSegmentos();
  } catch (erro) {
    alert(`Não foi possível adicionar o participante: ${erro.message}`);
  }
});

async function renomearParticipante(participanteId, novoNome) {
  const nome = novoNome.trim();
  if (!nome) throw new Error("o nome não pode ficar vazio");

  const atualizado = await apiFetch(`${API}/${reuniaoAtual.id}/participantes/${participanteId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nome }),
  });
  const p = participantesAtuais.find((x) => x.id === participanteId);
  if (p) p.nome = atualizado.nome;
  reuniaoAtual.segmentos.forEach((s) => { if (s.participante_id === participanteId) s.falante = atualizado.nome; });
  renderizarSegmentos();
}

async function excluirParticipante(participanteId) {
  if (!confirm("Excluir este participante? Os trechos vinculados a ele ficarão sem participante atribuído.")) return;
  try {
    await apiFetch(`${API}/${reuniaoAtual.id}/participantes/${participanteId}`, { method: "DELETE" });
    participantesAtuais = participantesAtuais.filter((p) => p.id !== participanteId);
    reuniaoAtual.segmentos.forEach((s) => {
      if (s.participante_id === participanteId) { s.participante_id = null; s.falante = null; }
    });
    renderizarParticipantes();
    renderizarSegmentos();
  } catch (erro) {
    alert(`Não foi possível excluir o participante: ${erro.message}`);
  }
}

// --- Segmentos -----------------------------------------------------------

function renderizarSegmentos() {
  const lista = document.getElementById("lista-segmentos");
  lista.innerHTML = "";

  if (reuniaoAtual.segmentos.length === 0) {
    const vazio = document.createElement("p");
    vazio.className = "texto-vazio";
    vazio.textContent = "Nenhum segmento de fala foi identificado neste áudio.";
    lista.appendChild(vazio);
    const botaoAdicionar = document.createElement("button");
    botaoAdicionar.className = "btn btn-secundario btn-pequeno";
    botaoAdicionar.textContent = "+ Adicionar trecho manualmente";
    botaoAdicionar.addEventListener("click", () => inserirSegmento(null));
    lista.appendChild(botaoAdicionar);
    return;
  }

  const opcoesParticipante = (selecionadoId) => {
    let html = `<option value="">— Sem participante —</option>`;
    for (const p of participantesAtuais) {
      html += `<option value="${p.id}" ${p.id === selecionadoId ? "selected" : ""}>${escaparHtml(p.nome)}</option>`;
    }
    return html;
  };

  const criarDivisorInsercao = (aposOrdem) => {
    const divisor = document.createElement("div");
    divisor.className = "insercao-segmento";
    divisor.innerHTML = `<button type="button" title="Inserir um trecho que a transcrição não capturou">+ Adicionar trecho aqui</button>`;
    divisor.querySelector("button").addEventListener("click", () => inserirSegmento(aposOrdem));
    return divisor;
  };

  // Um "+" antes do primeiro trecho, para o caso de a transcrição ter
  // pulado uma fala logo no início da reunião.
  lista.appendChild(criarDivisorInsercao(null));

  reuniaoAtual.segmentos.forEach((seg) => {
    const div = document.createElement("div");
    div.className = "segmento" + (seg.baixa_confianca ? " baixa-confianca" : "");
    div.dataset.id = seg.id;
    const semTexto = !seg.texto;
    div.innerHTML = `
      <div class="segmento-cabecalho">
        <span class="segmento-tempo">${formatarTempo(seg.inicio_segundos)} – ${formatarTempo(seg.fim_segundos)}</span>
        <select class="segmento-participante">${opcoesParticipante(seg.participante_id)}</select>
        ${seg.baixa_confianca ? '<span class="segmento-flag">⚠ baixa confiança — revisar</span>' : ""}
        ${semTexto ? '<span class="segmento-flag segmento-flag-info">✎ trecho adicionado manualmente</span>' : ""}
      </div>
      <textarea placeholder="Digite aqui o trecho que a transcrição não capturou...">${escaparHtml(seg.texto)}</textarea>
      <div class="segmento-rodape">
        <span class="segmento-status" aria-live="polite"></span>
        <div class="segmento-acoes">
          <button data-acao="salvar">Salvar agora</button>
          <button data-acao="dividir">Dividir no cursor</button>
          <button data-acao="mesclar-proximo">Unir com próximo</button>
          <button data-acao="excluir" class="acao-perigo">Excluir</button>
        </div>
      </div>
    `;
    lista.appendChild(div);
    // "+" logo depois de cada trecho, para inserir algo que veio a seguir
    // (ou entre este e o próximo) e não foi capturado.
    lista.appendChild(criarDivisorInsercao(seg.ordem));
  });

  lista.querySelectorAll(".segmento").forEach((div) => {
    const id = div.dataset.id;
    const textarea = div.querySelector("textarea");
    const selectParticipante = div.querySelector(".segmento-participante");
    const status = div.querySelector(".segmento-status");

    const salvarTextoNoServidor = async () => {
      const atualizado = await apiFetch(`${API}/${reuniaoAtual.id}/segmentos/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto: textarea.value }),
      });
      // Revisar (salvar) um trecho remove a marcação de baixa confiança -
      // ela é um alerta para a revisão, não algo permanente no documento.
      const seg = reuniaoAtual.segmentos.find((s) => s.id === id);
      if (seg) seg.baixa_confianca = atualizado.baixa_confianca;
      if (!atualizado.baixa_confianca) {
        div.classList.remove("baixa-confianca");
        const flag = div.querySelector(".segmento-flag");
        if (flag) flag.remove();
      }
    };

    textarea.addEventListener("input", () => {
      // Atualiza o estado local imediatamente: mesmo que a tela seja
      // redesenhada antes do salvamento no servidor terminar, o texto
      // digitado nunca volta a ser o antigo.
      const seg = reuniaoAtual.segmentos.find((s) => s.id === id);
      if (seg) seg.texto = textarea.value;
      agendarAutosave(`segmento-${id}`, salvarTextoNoServidor, status);
    });
    textarea.addEventListener("blur", () => flushAutosave(`segmento-${id}`, salvarTextoNoServidor, status));

    div.querySelector('[data-acao="salvar"]').addEventListener("click", () => flushAutosave(`segmento-${id}`, salvarTextoNoServidor, status));
    div.querySelector('[data-acao="excluir"]').addEventListener("click", () => excluirSegmento(id));
    div.querySelector('[data-acao="mesclar-proximo"]').addEventListener("click", () => mesclarComProximo(id));
    div.querySelector('[data-acao="dividir"]').addEventListener("click", () => {
      const pos = textarea.selectionStart;
      dividirSegmento(id, pos);
    });
    selectParticipante.addEventListener("change", () => atribuirParticipanteSegmento(id, selectParticipante.value || null));
  });
}

async function atribuirParticipanteSegmento(id, participanteId) {
  try {
    const atualizado = await apiFetch(`${API}/${reuniaoAtual.id}/segmentos/${id}/participante`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ participante_id: participanteId }),
    });
    const seg = reuniaoAtual.segmentos.find((s) => s.id === id);
    if (seg) { seg.participante_id = atualizado.participante_id; seg.falante = atualizado.falante; }
  } catch (erro) {
    alert(`Não foi possível atribuir o participante: ${erro.message}`);
    renderizarSegmentos();
  }
}

async function inserirSegmento(aposOrdem) {
  const indiceAnterior = aposOrdem === null
    ? -1
    : reuniaoAtual.segmentos.findIndex((s) => s.ordem === aposOrdem);
  const anterior = indiceAnterior >= 0 ? reuniaoAtual.segmentos[indiceAnterior] : null;
  const seguinte = reuniaoAtual.segmentos[indiceAnterior + 1] || null;

  const inicio = anterior ? anterior.fim_segundos : Math.max(0, (seguinte ? seguinte.inicio_segundos - 1 : 0));
  const fim = seguinte && seguinte.inicio_segundos > inicio ? seguinte.inicio_segundos : inicio;

  try {
    const novo = await apiFetch(`${API}/${reuniaoAtual.id}/segmentos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inicio_segundos: inicio, fim_segundos: fim, texto: "", apos_ordem: aposOrdem }),
    });

    // A inserção pode ter deslocado a ordem dos trechos seguintes -
    // buscar a reunião de novo garante que a lista fique na ordem certa.
    const atualizada = await apiFetch(`${API}/${reuniaoAtual.id}`);
    reuniaoAtual.segmentos = atualizada.segmentos;
    renderizarSegmentos();

    const textareaNovo = document.querySelector(`.segmento[data-id="${novo.id}"] textarea`);
    if (textareaNovo) {
      textareaNovo.focus();
      textareaNovo.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  } catch (erro) {
    alert(`Não foi possível inserir o trecho: ${erro.message}`);
  }
}

async function excluirSegmento(id) {
  if (!confirm("Excluir este trecho da transcrição?")) return;
  try {
    await apiFetch(`${API}/${reuniaoAtual.id}/segmentos/${id}`, { method: "DELETE" });
    reuniaoAtual.segmentos = reuniaoAtual.segmentos.filter((s) => s.id !== id);
    renderizarSegmentos();
  } catch (erro) {
    alert(`Não foi possível excluir o trecho: ${erro.message}`);
  }
}

async function mesclarComProximo(id) {
  const idx = reuniaoAtual.segmentos.findIndex((s) => s.id === id);
  if (idx === -1 || idx === reuniaoAtual.segmentos.length - 1) return;
  const proximo = reuniaoAtual.segmentos[idx + 1];
  try {
    const mesclado = await apiFetch(`${API}/${reuniaoAtual.id}/segmentos/mesclar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segmento_id_a: id, segmento_id_b: proximo.id }),
    });
    reuniaoAtual.segmentos.splice(idx, 2, mesclado);
    renderizarSegmentos();
  } catch (erro) {
    alert(`Não foi possível unir os trechos: ${erro.message}`);
  }
}

async function dividirSegmento(id, posicaoCaractere) {
  const seg = reuniaoAtual.segmentos.find((s) => s.id === id);
  if (!seg || posicaoCaractere <= 0 || posicaoCaractere >= seg.texto.length) {
    alert("Posicione o cursor dentro do texto do trecho (não no início/fim) antes de dividir.");
    return;
  }
  try {
    const [a, b] = await apiFetch(`${API}/${reuniaoAtual.id}/segmentos/${id}/dividir`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ posicao_caractere: posicaoCaractere }),
    });
    const idx = reuniaoAtual.segmentos.findIndex((s) => s.id === id);
    reuniaoAtual.segmentos.splice(idx, 1, a, b);
    renderizarSegmentos();
  } catch (erro) {
    alert(`Não foi possível dividir o trecho: ${erro.message}`);
  }
}

document.getElementById("btn-exportar-docx").addEventListener("click", () => {
  window.location.href = `${API}/${reuniaoAtual.id}/exportar/docx`;
});
document.getElementById("btn-exportar-txt").addEventListener("click", () => {
  window.location.href = `${API}/${reuniaoAtual.id}/exportar/txt`;
});

// ---------------------------------------------------------------------------
// ATA / RELATÓRIO E ENCAMINHAMENTOS
// ---------------------------------------------------------------------------

let ataAtual = null;

document.getElementById("btn-abrir-ata").addEventListener("click", () => abrirAta(reuniaoAtual.id));
document.getElementById("btn-voltar-revisao").addEventListener("click", () => mostrarView("revisao"));

async function abrirAta(reuniaoId) {
  mostrarView("ata");
  document.getElementById("ata-titulo").textContent = `Ata / Relatório — ${reuniaoAtual.titulo}`;
  document.getElementById("ata-meta").textContent =
    `${formatarData(reuniaoAtual.criado_em)} · Duração: ${formatarTempo(reuniaoAtual.duracao_segundos)}`;

  const btnExportar = document.getElementById("btn-exportar-ata-docx");
  try {
    ataAtual = await apiFetch(`${API}/${reuniaoId}/ata`);
    btnExportar.disabled = false;
    exibirAtaGerada();
  } catch (_) {
    ataAtual = null;
    btnExportar.disabled = true;
    document.getElementById("ata-vazia").classList.remove("hidden");
    document.getElementById("ata-gerar-container").classList.remove("hidden");
    document.getElementById("ata-conteudo").classList.add("hidden");
  }
}

document.getElementById("btn-gerar-ata").addEventListener("click", async () => {
  const botao = document.getElementById("btn-gerar-ata");
  botao.disabled = true;
  botao.textContent = "Gerando...";
  try {
    ataAtual = await apiFetch(`${API}/${reuniaoAtual.id}/ata/gerar`, { method: "POST" });
    document.getElementById("btn-exportar-ata-docx").disabled = false;
    exibirAtaGerada();
  } catch (erro) {
    alert(`Não foi possível gerar a ata: ${erro.message}`);
  } finally {
    botao.disabled = false;
    botao.textContent = "Gerar ata a partir da transcrição";
  }
});

function exibirAtaGerada() {
  document.getElementById("ata-vazia").classList.add("hidden");
  document.getElementById("ata-gerar-container").classList.add("hidden");
  document.getElementById("ata-conteudo").classList.remove("hidden");

  document.getElementById("ata-aviso-ia").classList.toggle("hidden", !ataAtual.gerada_por_ia);
  document.getElementById("ata-objetivo").value = ataAtual.objetivo || "";
  document.getElementById("ata-assuntos").value = ataAtual.assuntos_tratados || "";
  document.getElementById("ata-decisoes").value = ataAtual.decisoes || "";
  document.getElementById("ata-pendencias").value = ataAtual.pendencias || "";

  renderizarEncaminhamentos();
}

const CAMPOS_ATA = ["ata-objetivo", "ata-assuntos", "ata-decisoes", "ata-pendencias"];

function salvarSecoesAtaNoServidor() {
  return apiFetch(`${API}/${reuniaoAtual.id}/ata`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      objetivo: document.getElementById("ata-objetivo").value,
      assuntos_tratados: document.getElementById("ata-assuntos").value,
      decisoes: document.getElementById("ata-decisoes").value,
      pendencias: document.getElementById("ata-pendencias").value,
    }),
  }).then((atualizado) => { ataAtual = { ...ataAtual, ...atualizado }; });
}

const statusAta = document.getElementById("ata-status");
CAMPOS_ATA.forEach((idCampo) => {
  const campo = document.getElementById(idCampo);
  campo.addEventListener("input", () => {
    agendarAutosave("ata-secoes", salvarSecoesAtaNoServidor, statusAta);
  });
  campo.addEventListener("blur", () => {
    flushAutosave("ata-secoes", salvarSecoesAtaNoServidor, statusAta);
  });
});

document.getElementById("btn-salvar-ata").addEventListener("click", () => {
  flushAutosave("ata-secoes", salvarSecoesAtaNoServidor, statusAta);
});

const STATUS_ENCAMINHAMENTO = ["Pendente", "Em andamento", "Concluído"];

function renderizarEncaminhamentos() {
  const corpo = document.getElementById("tabela-encaminhamentos-body");
  const vazio = document.getElementById("encaminhamentos-vazio");
  corpo.innerHTML = "";
  vazio.classList.toggle("hidden", ataAtual.encaminhamentos.length > 0);

  ataAtual.encaminhamentos.forEach((enc) => {
    const tr = document.createElement("tr");
    const opcoesStatus = STATUS_ENCAMINHAMENTO
      .map((s) => `<option value="${s}" ${s === enc.status ? "selected" : ""}>${s}</option>`)
      .join("");
    tr.innerHTML = `
      <td><textarea class="enc-descricao" rows="2">${escaparHtml(enc.descricao)}</textarea></td>
      <td><input type="text" class="enc-responsavel" value="${escaparHtml(enc.responsavel || "")}" placeholder="Não identificado" /></td>
      <td><input type="text" class="enc-prazo" value="${escaparHtml(enc.prazo || "")}" placeholder="Não identificado" /></td>
      <td><select class="enc-status">${opcoesStatus}</select></td>
      <td>
        <span class="enc-status-autosave status-autosave" aria-live="polite"></span>
        <button data-acao="excluir-enc">Excluir</button>
      </td>
    `;

    const status = tr.querySelector(".enc-status-autosave");
    const salvarNoServidor = () => salvarEncaminhamento(enc.id, tr);
    tr.querySelectorAll(".enc-descricao, .enc-responsavel, .enc-prazo").forEach((campo) => {
      campo.addEventListener("input", () => agendarAutosave(`enc-${enc.id}`, salvarNoServidor, status));
      campo.addEventListener("blur", () => flushAutosave(`enc-${enc.id}`, salvarNoServidor, status));
    });
    tr.querySelector(".enc-status").addEventListener("change", () => flushAutosave(`enc-${enc.id}`, salvarNoServidor, status));

    tr.querySelector('[data-acao="excluir-enc"]').addEventListener("click", () => excluirEncaminhamento(enc.id));
    corpo.appendChild(tr);
  });
}

async function salvarEncaminhamento(id, tr) {
  const dados = {
    descricao: tr.querySelector(".enc-descricao").value,
    responsavel: tr.querySelector(".enc-responsavel").value,
    prazo: tr.querySelector(".enc-prazo").value,
    status: tr.querySelector(".enc-status").value,
  };
  const atualizado = await apiFetch(`${API}/${reuniaoAtual.id}/encaminhamentos/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dados),
  });
  const idx = ataAtual.encaminhamentos.findIndex((e) => e.id === id);
  if (idx !== -1) ataAtual.encaminhamentos[idx] = atualizado;
}

async function excluirEncaminhamento(id) {
  if (!confirm("Excluir este encaminhamento?")) return;
  try {
    await apiFetch(`${API}/${reuniaoAtual.id}/encaminhamentos/${id}`, { method: "DELETE" });
    ataAtual.encaminhamentos = ataAtual.encaminhamentos.filter((e) => e.id !== id);
    renderizarEncaminhamentos();
  } catch (erro) {
    alert(`Não foi possível excluir o encaminhamento: ${erro.message}`);
  }
}

document.getElementById("btn-adicionar-encaminhamento").addEventListener("click", async () => {
  const descricao = document.getElementById("novo-enc-descricao").value.trim();
  if (!descricao) return;
  const responsavel = document.getElementById("novo-enc-responsavel").value.trim();
  const prazo = document.getElementById("novo-enc-prazo").value.trim();
  try {
    const novo = await apiFetch(`${API}/${reuniaoAtual.id}/encaminhamentos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ descricao, responsavel: responsavel || null, prazo: prazo || null }),
    });
    ataAtual.encaminhamentos.push(novo);
    renderizarEncaminhamentos();
    document.getElementById("novo-enc-descricao").value = "";
    document.getElementById("novo-enc-responsavel").value = "";
    document.getElementById("novo-enc-prazo").value = "";
  } catch (erro) {
    alert(`Não foi possível adicionar o encaminhamento: ${erro.message}`);
  }
});

document.getElementById("btn-exportar-ata-docx").addEventListener("click", () => {
  window.location.href = `${API}/${reuniaoAtual.id}/exportar/ata-docx`;
});

// ---------------------------------------------------------------------------
// DICIONÁRIO INSTITUCIONAL
// ---------------------------------------------------------------------------

document.getElementById("btn-dicionario").addEventListener("click", () => {
  mostrarView("dicionario");
  carregarDicionario();
});
document.getElementById("btn-fechar-dicionario").addEventListener("click", () => {
  mostrarView("home");
  carregarHistorico();
});

async function carregarDicionario() {
  const lista = document.getElementById("lista-dicionario");
  const vazio = document.getElementById("dicionario-vazio");
  const termos = await apiFetch(API_DICIONARIO);

  lista.innerHTML = "";
  vazio.classList.toggle("hidden", termos.length > 0);

  termos.forEach((termo) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${escaparHtml(termo.termo)}</span><button>Excluir</button>`;
    li.querySelector("button").addEventListener("click", async () => {
      if (!confirm(`Excluir o termo "${termo.termo}" do dicionário?`)) return;
      try {
        await apiFetch(`${API_DICIONARIO}/${termo.id}`, { method: "DELETE" });
        carregarDicionario();
      } catch (erro) {
        alert(`Não foi possível excluir o termo: ${erro.message}`);
      }
    });
    lista.appendChild(li);
  });
}

document.getElementById("btn-adicionar-termo").addEventListener("click", adicionarTermo);
document.getElementById("input-novo-termo").addEventListener("keydown", (e) => {
  if (e.key === "Enter") adicionarTermo();
});

async function adicionarTermo() {
  const input = document.getElementById("input-novo-termo");
  const termo = input.value.trim();
  if (!termo) return;
  try {
    await apiFetch(API_DICIONARIO, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ termo }),
    });
    input.value = "";
    carregarDicionario();
  } catch (erro) {
    alert(`Não foi possível adicionar o termo: ${erro.message}`);
  }
}

// ---------------------------------------------------------------------------
// INICIALIZAÇÃO
// ---------------------------------------------------------------------------

async function inicializar() {
  try {
    capacidades = await apiFetch("/api/sistema/capacidades");
  } catch (_) {
    capacidades = { diarizacao_disponivel: false };
  }
  carregarHistorico();
}

inicializar();
