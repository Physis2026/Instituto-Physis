/*!
 * physis-nucleo.js — o contrato de dados da Physis. Versão 1.
 *
 * Um arquivo, zero dependência, roda no navegador e no Node.
 *
 * Existe para que três coisas escrevam o mesmo dado do mesmo jeito:
 *   1. a tela do cliente        (physis-tela-cliente.html)
 *   2. os apps de cada projeto  (turbina, coleira, caixa de medicamentos, ...)
 *   3. a ponte do SCADA         (physis-ponte.py)
 *
 * Regra que não se negocia: nenhum registro existe sem org_id.
 *
 * Como plugar no seu app:
 *   <script src="physis-nucleo.js"></script>
 *   const N = PhysisNucleo;
 *   const r = N.registro("medicao", { org_id: "cliente-alfa-01", valor: 42 });
 *   if (!r.ok) console.error(r.erros);
 *
 * No Node:  const N = require("./physis-nucleo.js");
 * Autoteste: N.verificar()  ->  { ok: true, total: n }
 */
(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === "object" && module.exports) module.exports = api;
  else raiz.PhysisNucleo = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var VERSAO = "physis/1";
  var FORMATOS_ACEITOS = ["physis/1", "physis-tela-cliente/1"];

  /* ------------------------------------------------------------------ *
   * 1. Tabelas canônicas
   * ------------------------------------------------------------------ */
  var TABELAS = [
    "organizacao", "site", "pessoa", "projeto", "tarefa", "apontamento_hora",
    "despesa", "fluxo", "medicao", "indicador", "ativo", "medida_eficiencia",
    "certificacao", "requisito", "risco", "incidente", "treinamento",
    "dado_sensivel_pessoa"
  ];

  // Campos exigidos além de org_id, por tabela.
  var OBRIGATORIOS = {
    organizacao: ["razao_social"],
    site: ["nome"],
    pessoa: ["nome"],
    projeto: ["nome"],
    tarefa: ["titulo", "projeto_id"],
    apontamento_hora: ["pessoa_id", "projeto_id", "horas", "data"],
    despesa: ["valor", "data"],
    fluxo: ["descricao", "classe", "destinacao"],
    medicao: ["grandeza", "valor"],
    indicador: ["nome", "valor"],
    ativo: ["nome"],
    medida_eficiencia: ["nome"],
    certificacao: ["nome"],
    requisito: ["descricao"],
    risco: ["descricao"],
    incidente: ["descricao", "data"],
    treinamento: ["nome"],
    dado_sensivel_pessoa: ["pessoa_id", "base_legal", "data_consentimento"]
  };

  /* ------------------------------------------------------------------ *
   * 2. org_id
   * ------------------------------------------------------------------ */
  var RE_ORG = /^[a-z0-9][a-z0-9._-]{1,63}$/;

  function normalizarOrg(valor) {
    if (valor === null || valor === undefined) return "";
    return String(valor).trim().toLowerCase()
      .normalize ? String(valor).trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64)
      : String(valor).trim().toLowerCase();
  }
  function orgValido(valor) { return RE_ORG.test(String(valor || "")); }

  /* ------------------------------------------------------------------ *
   * 3. Números — o separador decimal segue o idioma, nunca o chute
   * ------------------------------------------------------------------ */
  function caraDeMilhar(s, i) {
    return (s.length - i - 1) === 3 && /^[1-9][0-9]{0,2}$/.test(s.slice(0, i));
  }
  function num(valor, idioma) {
    if (valor === null || valor === undefined) return NaN;
    if (typeof valor === "number") return isFinite(valor) ? valor : NaN;
    var s = String(valor).trim();
    if (!s) return NaN;
    s = s.replace(/[^0-9.,-]/g, "");
    if (!s) return NaN;
    var neg = /^-/.test(s); s = s.replace(/-/g, "");
    var pt = (idioma || "pt") === "pt";
    var nP = (s.match(/\./g) || []).length, nV = (s.match(/,/g) || []).length;
    var iP = s.lastIndexOf("."), iV = s.lastIndexOf(",");
    var dec = "";
    if (nP && nV) dec = iP > iV ? "." : ",";
    else if (nP > 1 || nV > 1) dec = "";
    else if (nP === 1) dec = pt ? (caraDeMilhar(s, iP) ? "" : ".") : ".";
    else if (nV === 1) dec = pt ? "," : (caraDeMilhar(s, iV) ? "" : ",");
    if (dec === ".") s = s.replace(/,/g, "");
    else if (dec === ",") s = s.replace(/\./g, "").replace(",", ".");
    else s = s.replace(/[.,]/g, "");
    var n = parseFloat(s);
    return isFinite(n) ? (neg ? -n : n) : NaN;
  }

  /* ------------------------------------------------------------------ *
   * 4. MQTT — precisa bater com physis-ponte.py, byte a byte
   * ------------------------------------------------------------------ */
  var RE_TOPICO = /^physis\/([a-z0-9][a-z0-9._-]*)\/([a-z0-9_-]+)\/([a-z0-9._-]+)$/i;

  function montarTopico(org, grandeza, ativo) {
    if (!orgValido(org)) return null;
    var g = String(grandeza || "").toLowerCase(), a = String(ativo || "").toLowerCase();
    if (!/^[a-z0-9_-]+$/.test(g) || !/^[a-z0-9._-]+$/.test(a)) return null;
    return "physis/" + org + "/" + g + "/" + a;
  }
  function analisarTopico(topico) {
    if (!topico) return null;
    var m = RE_TOPICO.exec(String(topico).trim().replace(/^\/+|\/+$/g, ""));
    if (!m) return null;
    return { org_id: m[1].toLowerCase(), grandeza: m[2].toLowerCase(), ativo: m[3].toLowerCase() };
  }

  // Mesmas faixas do physis-ponte.py. Valores de partida: ajustar por ativo.
  var FAIXAS = {
    energia: [0, 500, "kW"], tensao: [198, 242, "V"], corrente: [0, 630, "A"],
    fp: [0.92, 1, "-"], temperatura: [0, 80, "C"], umidade: [20, 90, "%"],
    nivel: [5, 95, "%"], pressao: [0, 10, "bar"], vazao: [0, 100, "m3/h"],
    // pluviômetro de báscula (TIPO:PLUV): chuva no intervalo e intensidade (mm/h, calculada pelo hub)
    chuva: [0, 200, "mm"], chuva_intensidade: [null, null, "mm/h"],
    // secador solar (TIPO:SEC, a homologar): o limite de temperatura é do produto (physis-secador.js), não daqui
    temperatura_interna: [null, null, "C"], umidade_interna: [0, 100, "%"], temperatura_coletor: [null, null, "C"],
    peso_produto: [null, null, "kg"], irradiancia: [0, 1500, "W/m2"],
    // rede V6 e dispositivos via ESP (as mesmas de physis_hub/nucleo.py)
    umidade_solo: [0, 100, "%"], estado: [null, null, "0/1"], previsao_min: [null, null, "min"],
    bateria: [3.3, 4.3, "V"], rssi: [-120, 0, "dBm"], snr: [null, null, "dB"], latitude: [-90, 90, "grau"],
    longitude: [-180, 180, "grau"], atividade: [null, null, "0-2"], impacto: [null, null, "0/1"], porcoes: [null, null, "un"],
    // medidor de energia (TIPO:ENE): potência reativa e aparente; o fator de potência já é "fp"
    potencia_reativa: [null, null, "kvar"], potencia_aparente: [null, null, "kVA"]
  };
  function avaliarAlarme(grandeza, valor, faixas) {
    var f = (faixas || FAIXAS)[grandeza];
    if (!f || (f[0] == null && f[1] == null)) return "sem_faixa";
    if (f[0] != null && valor < f[0]) return "baixo";
    if (f[1] != null && valor > f[1]) return "alto";
    return "ok";
  }

  /* ------------------------------------------------------------------ *
   * 5. Resíduo — classe, destinação e MTR ou não passa
   * ------------------------------------------------------------------ */
  var CLASSES = ["I", "IIA", "IIB"];
  var DESTINOS = ["reuso", "reciclagem", "compostagem", "coproc", "incineracao",
    "aterro1", "aterro2", "reversa", "publica", "armazenado"];
  var EXIGE_MTR = ["reciclagem", "compostagem", "coproc", "incineracao",
    "aterro1", "aterro2", "reversa"];
  var PROIBIDO_CLASSE_I = ["publica", "aterro2", "compostagem"];
  var DESVIADO = ["reuso", "reciclagem", "compostagem", "reversa"];
  var NAO_DESVIADO = ["aterro1", "aterro2", "incineracao", "publica", "coproc"];

  function validarResiduo(r) {
    var e = [];
    r = r || {};
    if (!r.classe) e.push("classe_ausente");
    else if (CLASSES.indexOf(String(r.classe).toUpperCase()) < 0) e.push("classe_invalida");
    if (!r.destinacao && !r.dest) e.push("destinacao_ausente");
    var dest = r.destinacao || r.dest;
    if (dest && DESTINOS.indexOf(dest) < 0) e.push("destinacao_invalida");
    if (String(r.classe).toUpperCase() === "I" && PROIBIDO_CLASSE_I.indexOf(dest) > -1)
      e.push("classe_I_em_destinacao_proibida");
    if (dest && EXIGE_MTR.indexOf(dest) > -1 && !String(r.mtr || "").trim()) e.push("mtr_ausente");
    var q = num(r.quantidade !== undefined ? r.quantidade : r.qtd);
    if (!isFinite(q) || q <= 0) e.push("quantidade_ausente");
    return e;
  }

  var FATOR_ANO = { "kg/mes": 12 / 1000, "kg/ano": 1 / 1000, "t/mes": 12, "t/ano": 1, "m3/ano": 1 };
  function toneladasAno(quantidade, unidade) {
    var q = num(quantidade), f = FATOR_ANO[unidade];
    return (isFinite(q) && f) ? q * f : NaN;
  }
  function desvioAterro(residuos) {
    var d = 0, n = 0;
    (residuos || []).forEach(function (r) {
      var t = toneladasAno(r.quantidade !== undefined ? r.quantidade : r.qtd, r.unidade || r.un);
      var dest = r.destinacao || r.dest;
      if (!isFinite(t) || t <= 0 || !dest) return;
      if (DESVIADO.indexOf(dest) > -1) { d += t; n += t; }
      else if (NAO_DESVIADO.indexOf(dest) > -1) { n += t; }
    });
    return n > 0 ? { pct: d / n * 100, desviado: d, total: n } : { pct: NaN, desviado: 0, total: 0 };
  }


  /* ------------------------------------------------------------------ *
   * 5b. Equipamentos — consumo estimado a partir do uso real
   * ------------------------------------------------------------------ *
   * Placa não é consumo. Motor de 30 CV rodando a 45% de carregamento,
   * 6 h por dia, não gasta o que a placa diz. O erro clássico de proposta
   * é multiplicar potência nominal por hora de expediente.
   *
   * Cadeia:  potência de eixo -> carregamento -> rendimento -> potência
   *          de entrada -> horas -> kWh/ano.  E kVA e kvar pelo fator de
   *          potência, porque abaixo de 0,92 a distribuidora cobra.
   */
  var CV_PARA_KW = 0.7355;

  var TIPOS_EQUIPAMENTO = {
    motor:        { pt: "Motor elétrico", en: "Electric motor", fp: 0.85, rend: 0.90, fpAplicavel: true },
    compressor:   { pt: "Compressor", en: "Compressor", fp: 0.86, rend: 0.90, fpAplicavel: true },
    bomba:        { pt: "Bomba", en: "Pump", fp: 0.85, rend: 0.88, fpAplicavel: true },
    ventilador:   { pt: "Ventilador ou exaustor", en: "Fan or exhaust", fp: 0.83, rend: 0.85, fpAplicavel: true },
    refrigeracao: { pt: "Refrigeração", en: "Refrigeration", fp: 0.84, rend: 0.90, fpAplicavel: true },
    iluminacao:   { pt: "Iluminação", en: "Lighting", fp: 0.92, rend: 1.00, fpAplicavel: true },
    resistivo:    { pt: "Aquecimento resistivo", en: "Resistive heating", fp: 1.00, rend: 1.00, fpAplicavel: false },
    outro:        { pt: "Outro", en: "Other", fp: 0.90, rend: 1.00, fpAplicavel: true }
  };

  // Correções por carregamento. São aproximações declaradas, não medição:
  // rendimento e fator de potência caem quando o equipamento roda folgado,
  // e o fator de potência cai muito mais rápido que o rendimento.
  function corrigirRendimento(nominal, carga) {
    if (!isFinite(carga) || carga <= 0) return nominal;
    var c = Math.min(carga, 1.2);
    return nominal * (1 - 0.25 * Math.pow(1 - Math.min(c, 1), 2));
  }
  function corrigirFatorPotencia(nominal, carga) {
    if (!isFinite(carga) || carga <= 0) return nominal;
    var c = Math.min(carga, 1.2);
    return nominal * (1 - 0.55 * Math.pow(1 - Math.min(c, 1), 2));
  }

  function potenciaEixoKw(eq) {
    var kw = num(eq.potencia_kw);
    if (isFinite(kw) && kw > 0) return kw;
    var cv = num(eq.potencia_cv);
    if (isFinite(cv) && cv > 0) return cv * CV_PARA_KW;
    return NaN;
  }

  function equipamento(eq) {
    eq = eq || {};
    var tipo = TIPOS_EQUIPAMENTO[eq.tipo] ? eq.tipo : "outro";
    var def = TIPOS_EQUIPAMENTO[tipo];
    var alertas = [], estimado = { fp: false, rendimento: false };

    var qtd = num(eq.quantidade); if (!isFinite(qtd) || qtd <= 0) qtd = 1;
    var eixo = potenciaEixoKw(eq);
    var carga = num(eq.fator_carga);
    if (!isFinite(carga) || carga <= 0) { carga = NaN; }
    else if (carga > 1.5) { carga = carga / 100; }   // aceita 65 e 0,65

    var horasDia = num(eq.horas_dia), diasAno = num(eq.dias_ano);
    var horasAno = num(eq.horas_ano);
    if (!isFinite(horasAno) && isFinite(horasDia) && isFinite(diasAno)) horasAno = horasDia * diasAno;

    var rendNom = num(eq.rendimento);
    if (!isFinite(rendNom) || rendNom <= 0) { rendNom = def.rend; estimado.rendimento = true; }
    else if (rendNom > 1.5) rendNom = rendNom / 100;
    var rend = corrigirRendimento(rendNom, carga);

    var fpMedido = num(eq.fp_medido);
    var fp;
    if (!def.fpAplicavel) { fp = 1; }
    else if (isFinite(fpMedido) && fpMedido > 0 && fpMedido <= 1) { fp = fpMedido; }
    else { fp = corrigirFatorPotencia(num(eq.fp_nominal) > 0 ? num(eq.fp_nominal) : def.fp, carga); estimado.fp = true; }

    var falta = [];
    if (!isFinite(eixo)) falta.push("potencia");
    if (!isFinite(carga)) falta.push("fator_carga");
    if (!isFinite(horasAno)) falta.push("horas");

    var entrada = NaN, kwhAno = NaN, kva = NaN, kvar = NaN;
    if (!falta.length) {
      entrada = (eixo * carga / rend) * qtd;
      kwhAno = entrada * horasAno;
      if (def.fpAplicavel && fp > 0) {
        kva = entrada / fp;
        kvar = entrada * Math.tan(Math.acos(Math.min(fp, 1)));
      }
    }

    if (isFinite(carga) && carga < 0.4) alertas.push("superdimensionado");
    if (isFinite(carga) && carga > 1.05) alertas.push("acima_da_nominal");
    if (def.fpAplicavel && isFinite(fp) && fp < 0.92) alertas.push("fp_abaixo_de_092");
    if (isFinite(horasAno) && horasAno > 8760) alertas.push("horas_acima_do_ano");

    return {
      tipo: tipo, quantidade: qtd, potencia_eixo_kw: eixo, fator_carga: carga,
      horas_ano: horasAno, rendimento_nominal: rendNom, rendimento_efetivo: rend,
      fp_efetivo: def.fpAplicavel ? fp : null, fp_aplicavel: def.fpAplicavel,
      potencia_entrada_kw: entrada, kwh_ano: kwhAno, kva: kva, kvar: kvar,
      estimado: estimado, alertas: alertas, falta: falta
    };
  }

  function validarEquipamento(eq) {
    var e = [];
    eq = eq || {};
    if (!String(eq.nome || "").trim()) e.push("nome_ausente");
    if (eq.tipo && !TIPOS_EQUIPAMENTO[eq.tipo]) e.push("tipo_invalido");
    var c = equipamento(eq);
    c.falta.forEach(function (f) { e.push("falta:" + f); });
    return e;
  }

  // A conta que o auditor faz: o inventário explica a fatura?
  function reconciliarConsumo(equipamentos, kwhMedidoAno) {
    var soma = 0, comConta = 0;
    (equipamentos || []).forEach(function (eq) {
      var c = equipamento(eq);
      if (isFinite(c.kwh_ano)) { soma += c.kwh_ano; comConta++; }
    });
    var medido = num(kwhMedidoAno);
    if (!isFinite(medido) || medido <= 0) {
      return { estimado: soma, medido: null, cobertura_pct: null, veredito: "sem_medicao", itens: comConta };
    }
    var cob = soma / medido * 100;
    var veredito = cob < 85 ? "inventario_incompleto"
      : (cob > 115 ? "inventario_superestimado" : "fecha");
    return { estimado: soma, medido: medido, cobertura_pct: cob, veredito: veredito, itens: comConta };
  }


  /* ------------------------------------------------------------------ *
   * 5c. Medição: onde medir, e se a medida prova o que se quer provar
   * ------------------------------------------------------------------ *
   * Instrumento calibrado não é o mesmo que medida útil. Se a incerteza da
   * medição é maior que o efeito que se quer comprovar, a campanha não serve
   * para nada — e isso se descobre antes de ir a campo, não depois.
   */
  var PONTOS_MEDICAO = {
    motor: {
      onde: "No alimentador do motor, dentro do quadro, não na entrada geral",
      ondeEn: "At the motor feeder inside the panel, not at the main incomer",
      grandezas: "Corrente nas três fases, tensão, potência ativa e fator de potência",
      grandezasEn: "Current on all three phases, voltage, active power and power factor",
      instrumento: "Analisador de energia registrador, classe 1", instrumentoEn: "Logging power analyser, class 1",
      duracao: "No mínimo um ciclo produtivo completo; sete dias se houver variação semanal",
      duracaoEn: "At least one full production cycle; seven days if there is weekly variation",
      revela: "Carregamento real, regime de partida e reativo — os três campos que hoje são estimativa",
      revelaEn: "Real loading, starting regime and reactive power — the three fields that are estimates today"
    },
    compressor: {
      onde: "No alimentador do compressor, e vazão no cabeçote de ar comprimido",
      ondeEn: "At the compressor feeder, plus flow on the compressed air header",
      grandezas: "Potência ativa, vazão de ar, pressão e tempo em carga contra alívio",
      grandezasEn: "Active power, air flow, pressure and time on load versus unload",
      instrumento: "Registrador de energia e medidor de vazão de ar", instrumentoEn: "Energy logger and compressed air flow meter",
      duracao: "Uma semana, mais um ensaio de vazamento com a produção parada",
      duracaoEn: "One week, plus a leak test with production stopped",
      revela: "Vazamento de ar, que costuma ser de 20% a 30% da produção e não aparece em nenhuma planilha",
      revelaEn: "Air leakage, typically 20% to 30% of output, which shows up in no spreadsheet"
    },
    bomba: {
      onde: "No alimentador da bomba, com pressão na sucção e na descarga",
      ondeEn: "At the pump feeder, with suction and discharge pressure",
      grandezas: "Potência ativa, vazão, pressão diferencial",
      grandezasEn: "Active power, flow, differential pressure",
      instrumento: "Registrador de energia e medidor de vazão ultrassônico", instrumentoEn: "Energy logger and ultrasonic flow meter",
      duracao: "Um ciclo operacional completo", duracaoEn: "One complete operating cycle",
      revela: "Estrangulamento por válvula, que é energia jogada fora para depois ser barrada",
      revelaEn: "Throttling by valve — energy paid for and then thrown away"
    },
    ventilador: {
      onde: "No alimentador, com pressão estática no duto",
      ondeEn: "At the feeder, with static pressure in the duct",
      grandezas: "Potência ativa, vazão de ar, pressão estática",
      grandezasEn: "Active power, air flow, static pressure",
      instrumento: "Registrador de energia, tubo de Pitot ou anemômetro", instrumentoEn: "Energy logger, Pitot tube or anemometer",
      duracao: "Um turno em cada regime de operação", duracaoEn: "One shift in each operating regime",
      revela: "Ventilador operando fora do ponto de melhor rendimento", revelaEn: "Fan operating away from its best efficiency point"
    },
    refrigeracao: {
      onde: "No alimentador da unidade condensadora, mais temperatura da câmara e do ambiente",
      ondeEn: "At the condensing unit feeder, plus chamber and ambient temperature",
      grandezas: "Potência ativa, temperatura interna, temperatura ambiente, tempo em funcionamento",
      grandezasEn: "Active power, internal temperature, ambient temperature, run time",
      instrumento: "Registrador de energia e dois registradores de temperatura", instrumentoEn: "Energy logger and two temperature loggers",
      duracao: "Sete dias, para pegar o ciclo de degelo e a variação de dia e noite",
      duracaoEn: "Seven days, to capture the defrost cycle and the day-night variation",
      revela: "O tempo em funcionamento é o próprio fator de carga — aqui ele deixa de ser chute",
      revelaEn: "Run time is the load factor itself — here it stops being a guess"
    },
    iluminacao: {
      onde: "No circuito de iluminação no quadro, mais lux no plano de trabalho",
      ondeEn: "On the lighting circuit at the panel, plus lux at the working plane",
      grandezas: "Potência ativa, horas efetivas, iluminância em lux por área",
      grandezasEn: "Active power, effective hours, illuminance in lux per area",
      instrumento: "Registrador de energia e luxímetro calibrado", instrumentoEn: "Energy logger and calibrated lux meter",
      duracao: "Uma semana de energia; lux em uma visita, por área de tarefa",
      duracaoEn: "One week of energy; lux in a single visit, per task area",
      revela: "Área iluminada além ou abaixo do exigido pela norma de iluminação de ambientes de trabalho",
      revelaEn: "Areas lit above or below the level required by the workplace lighting standard"
    },
    resistivo: {
      onde: "No circuito do equipamento; sem fator de potência a medir, aqui kW é igual a kVA",
      ondeEn: "On the equipment circuit; no power factor to measure, kW equals kVA here",
      grandezas: "Energia acumulada, tempo ligado, temperatura de processo",
      grandezasEn: "Accumulated energy, on time, process temperature",
      instrumento: "Medidor de energia e registrador de temperatura", instrumentoEn: "Energy meter and temperature logger",
      duracao: "Um ciclo completo de processo", duracaoEn: "One complete process cycle",
      revela: "Perda por isolamento e por porta aberta, e ciclo mais longo que o necessário",
      revelaEn: "Insulation and open-door losses, and cycles longer than needed"
    },
    outro: {
      onde: "No alimentador do equipamento, no quadro que o serve",
      ondeEn: "At the equipment feeder, in the panel that serves it",
      grandezas: "Potência ativa e tempo de operação",
      grandezasEn: "Active power and operating time",
      instrumento: "Registrador de energia classe 1", instrumentoEn: "Class 1 energy logger",
      duracao: "Um ciclo produtivo", duracaoEn: "One production cycle",
      revela: "Consumo real contra o estimado por placa", revelaEn: "Real consumption versus the nameplate estimate"
    }
  };

  var PONTOS_UTILIDADE = {
    entrada: {
      onde: "Logo depois do medidor da distribuidora, com medidor próprio classe 1 — nunca no medidor dela",
      ondeEn: "Just downstream of the utility meter, with your own class 1 meter — never on theirs",
      grandezas: "Energia ativa e reativa, demanda, fator de potência, por intervalo de 15 minutos",
      grandezasEn: "Active and reactive energy, demand, power factor, in 15-minute intervals",
      instrumento: "Medidor de energia classe 1 com registro", instrumentoEn: "Class 1 recording energy meter",
      duracao: "Permanente. É a linha de base de tudo", duracaoEn: "Permanent. It is the baseline for everything",
      revela: "Fecha a reconciliação com a fatura e denuncia ultrapassagem de demanda e excedente reativo",
      revelaEn: "Closes the reconciliation with the bill and exposes demand overrun and reactive excess"
    },
    agua: {
      onde: "Na entrada geral e no maior uso individual",
      ondeEn: "At the main inlet and at the single largest use",
      grandezas: "Volume acumulado e vazão instantânea",
      grandezasEn: "Accumulated volume and instantaneous flow",
      instrumento: "Hidrômetro com saída de pulso, ou medidor ultrassônico não invasivo",
      instrumentoEn: "Water meter with pulse output, or non-invasive ultrasonic meter",
      duracao: "Permanente na entrada; uma semana no uso individual",
      duracaoEn: "Permanent at the inlet; one week at the individual use",
      revela: "Consumo fora do horário de produção, que é vazamento até prova em contrário",
      revelaEn: "Consumption outside production hours, which is leakage until proven otherwise"
    },
    combustivel: {
      onde: "No tanque e no queimador, ou horímetro no equipamento",
      ondeEn: "At the tank and the burner, or an hour meter on the equipment",
      grandezas: "Volume ou massa consumida, horas de operação",
      grandezasEn: "Volume or mass consumed, operating hours",
      instrumento: "Medidor de vazão de combustível, régua ou balança, horímetro",
      instrumentoEn: "Fuel flow meter, dip gauge or scale, hour meter",
      duracao: "Um mês, cruzado com as notas de compra",
      duracaoEn: "One month, cross-checked against purchase invoices",
      revela: "Diferença entre o que foi comprado e o que foi queimado",
      revelaEn: "The gap between what was purchased and what was burned"
    },
    efluente: {
      onde: "Na saída da estação de tratamento", ondeEn: "At the treatment plant outlet",
      grandezas: "Vazão acumulada", grandezasEn: "Accumulated flow",
      instrumento: "Medidor de vazão em canal aberto ou eletromagnético",
      instrumentoEn: "Open channel or electromagnetic flow meter",
      duracao: "Permanente, se houver outorga de lançamento",
      duracaoEn: "Permanent, if there is a discharge permit",
      revela: "Balanço hídrico: o que entra e não sai virou produto, perda ou vazamento",
      revelaEn: "Water balance: what comes in and does not leave became product, loss or leakage"
    },
    geracao: {
      onde: "Na saída do inversor e no ponto de conexão", ondeEn: "At the inverter output and the connection point",
      grandezas: "Energia gerada, energia injetada, irradiância se houver solar",
      grandezasEn: "Generated energy, exported energy, irradiance if solar",
      instrumento: "Medidor bidirecional e piranômetro", instrumentoEn: "Bidirectional meter and pyranometer",
      duracao: "Permanente", duracaoEn: "Permanent",
      revela: "Desempenho real contra o prometido na proposta, e o custo de disponibilidade que não zera",
      revelaEn: "Real performance versus what the proposal promised, and the availability charge that never zeroes"
    }
  };

  /* Calibração vence. E vencida, o dado vira opinião. */
  function statusCalibracao(validade, referencia) {
    if (!validade) return { estado: "sem_calibracao", dias: null };
    var v = new Date(String(validade).slice(0, 10) + "T00:00:00Z");
    if (isNaN(v.getTime())) return { estado: "data_invalida", dias: null };
    var r = referencia ? new Date(String(referencia).slice(0, 10) + "T00:00:00Z") : new Date();
    var dias = Math.round((v - r) / 86400000);
    var estado = dias < 0 ? "vencida" : (dias <= 60 ? "vence_em_breve" : "valida");
    return { estado: estado, dias: dias };
  }

  /* A regra que decide se vale ir a campo: a incerteza tem que ser bem menor
     que a economia que se pretende comprovar. Razão de 3 para 1 é o mínimo
     defensável; abaixo de 1 para 1 a medição não distingue economia de ruído. */
  function economiaComprovavel(economiaPct, incertezaPct) {
    var e = num(economiaPct), i = num(incertezaPct);
    if (!isFinite(e) || e <= 0) return { ok: null, razao: null, veredito: "falta_economia" };
    if (!isFinite(i) || i < 0) return { ok: null, razao: null, veredito: "falta_incerteza" };
    if (i === 0) return { ok: true, razao: Infinity, veredito: "confortavel" };
    var razao = e / i;
    var veredito = razao >= 3 ? "confortavel" : (razao >= 1 ? "apertado" : "nao_comprova");
    return { ok: razao >= 3, razao: razao, veredito: veredito };
  }

  function validarInstrumento(inst) {
    var e = [];
    inst = inst || {};
    if (!String(inst.nome || "").trim()) e.push("nome_ausente");
    if (!String(inst.grandeza || "").trim()) e.push("grandeza_ausente");
    var exa = num(inst.exatidao);
    if (!isFinite(exa) || exa <= 0) e.push("exatidao_ausente");
    if (!String(inst.laboratorio || "").trim()) e.push("laboratorio_ausente");
    if (!String(inst.certificado || "").trim()) e.push("certificado_ausente");
    var st = statusCalibracao(inst.validade, inst.referencia);
    if (st.estado === "sem_calibracao") e.push("validade_ausente");
    if (st.estado === "data_invalida") e.push("validade_invalida");
    if (st.estado === "vencida") e.push("calibracao_vencida");
    return e;
  }

  /* Monta o plano de medição a partir do inventário que a pessoa já preencheu. */
  function planoMedicao(dados) {
    dados = dados || {};
    var pontos = [{ chave: "entrada", ref: PONTOS_UTILIDADE.entrada, alvo: "Entrada de energia", alvoEn: "Energy incomer" }];
    var tiposVistos = {};
    (dados.equipamentos || []).forEach(function (eq) {
      var tipo = PONTOS_MEDICAO[eq.tipo] ? eq.tipo : "outro";
      var chave = tipo + ":" + (eq.nome || "");
      if (tiposVistos[chave]) return;
      tiposVistos[chave] = true;
      pontos.push({ chave: chave, ref: PONTOS_MEDICAO[tipo], alvo: eq.nome || tipo, alvoEn: eq.nome || tipo,
                    kwh_ano: equipamento(eq).kwh_ano });
    });
    if (isFinite(num(dados.agua_m3_ano))) pontos.push({ chave: "agua", ref: PONTOS_UTILIDADE.agua, alvo: "Água", alvoEn: "Water" });
    if (["diesel_l_ano", "glp_kg_ano", "gn_m3_ano"].some(function (k) { return isFinite(num(dados[k])); }))
      pontos.push({ chave: "combustivel", ref: PONTOS_UTILIDADE.combustivel, alvo: "Combustível", alvoEn: "Fuel" });
    if (isFinite(num(dados.efluente_m3_ano))) pontos.push({ chave: "efluente", ref: PONTOS_UTILIDADE.efluente, alvo: "Efluente", alvoEn: "Effluent" });
    if (isFinite(num(dados.geracao_kwh_ano))) pontos.push({ chave: "geracao", ref: PONTOS_UTILIDADE.geracao, alvo: "Geração própria", alvoEn: "On-site generation" });
    // maior consumidor primeiro, depois de manter a entrada no topo
    var cabeca = pontos.shift();
    pontos.sort(function (a, b) {
      var x = isFinite(a.kwh_ano) ? a.kwh_ano : -1, y = isFinite(b.kwh_ano) ? b.kwh_ano : -1;
      return y - x;
    });
    pontos.unshift(cabeca);
    return pontos;
  }

  /* ------------------------------------------------------------------ *
   * 6. Indicadores — quem não pode ser calculado diz o que falta
   * ------------------------------------------------------------------ */
  var FATORES = { rede: 0.0289, diesel: 2.671, glp: 2.939, gn: 1.999 };

  function indicadores(d, fatores) {
    d = d || {}; fatores = Object.assign({}, FATORES, fatores || {});
    var prod = num(d.producao_ano), kwh = num(d.energia_kwh_ano), agua = num(d.agua_m3_ano);
    function razao(a, b, faltaA, faltaB) {
      var falta = [];
      if (!(isFinite(b) && b > 0)) falta.push(faltaB);
      if (!isFinite(a)) falta.push(faltaA);
      return falta.length ? { valor: null, falta: falta } : { valor: a / b, falta: [] };
    }
    var e1 = 0, temE1 = false;
    [["diesel_l_ano", "diesel"], ["glp_kg_ano", "glp"], ["gn_m3_ano", "gn"]].forEach(function (p) {
      var v = num(d[p[0]]);
      if (isFinite(v) && v > 0) { e1 += v * fatores[p[1]]; temE1 = true; }
    });
    var e2 = isFinite(kwh) ? (kwh / 1000) * fatores.rede : 0;
    return {
      intensidade_energetica: razao(kwh, prod, "energia_kwh_ano", "producao_ano"),
      intensidade_hidrica: razao(agua, prod, "agua_m3_ano", "producao_ano"),
      emissoes_tco2e_ano: (temE1 || isFinite(kwh))
        ? { valor: e1 / 1000 + e2, falta: [] }
        : { valor: null, falta: ["energia_kwh_ano", "combustivel"] },
      desvio_aterro_pct: (function () {
        var x = desvioAterro(d.residuos);
        return isFinite(x.pct) ? { valor: x.pct, falta: [] } : { valor: null, falta: ["fluxo"] };
      })(),
      fatores_usados: fatores
    };
  }

  /* ------------------------------------------------------------------ *
   * 7. Registro e validação
   * ------------------------------------------------------------------ */
  function registro(tabela, dados) {
    var erros = [];
    if (TABELAS.indexOf(tabela) < 0) erros.push("tabela_desconhecida:" + tabela);
    dados = Object.assign({}, dados || {});
    var org = normalizarOrg(dados.org_id);
    if (!org) erros.push("org_id_ausente");
    else if (!orgValido(org)) erros.push("org_id_invalido");
    dados.org_id = org;
    (OBRIGATORIOS[tabela] || []).forEach(function (campo) {
      var v = dados[campo];
      if (v === undefined || v === null || String(v).trim() === "") erros.push("campo_ausente:" + campo);
    });
    if (tabela === "fluxo") validarResiduo(dados).forEach(function (e) { erros.push("residuo:" + e); });
    if (tabela === "medicao" && dados.grandeza !== undefined && dados.valor !== undefined) {
      var v = num(dados.valor);
      if (!isFinite(v)) erros.push("valor_nao_numerico");
      else { dados.valor = v; dados.alarme = avaliarAlarme(dados.grandeza, v); }
    }
    if (!dados.ts) dados.ts = new Date().toISOString();
    return { ok: erros.length === 0, registro: dados, erros: erros };
  }

  /* ------------------------------------------------------------------ *
   * 8. Trilha de auditoria
   * ------------------------------------------------------------------ */
  function Trilha(limite) {
    this.linhas = []; this.limite = limite || 1000;
  }
  Trilha.prototype.registrar = function (usuario, tabela, campo, antes, depois) {
    if (String(antes === undefined || antes === null ? "" : antes) ===
      String(depois === undefined || depois === null ? "" : depois)) return false;
    this.linhas.unshift({
      ts: new Date().toISOString(), usuario: usuario || "—",
      tabela: tabela, campo: campo,
      antes: antes === undefined || antes === null ? "" : antes,
      depois: depois === undefined || depois === null ? "" : depois
    });
    if (this.linhas.length > this.limite) this.linhas.pop();
    return true;
  };
  Trilha.prototype.exportar = function () { return this.linhas.slice(); };

  /* ------------------------------------------------------------------ *
   * 9. Pacote de intercâmbio — o arquivo que atravessa os apps
   * ------------------------------------------------------------------ */
  function criarPacote(opcoes) {
    opcoes = opcoes || {};
    var org = normalizarOrg(opcoes.org_id);
    if (!orgValido(org)) throw new Error("pacote sem org_id válido");
    return {
      _formato: VERSAO,
      _gerado_em: new Date().toISOString(),
      _gerado_por: opcoes.usuario || "—",
      _app: opcoes.app || "desconhecido",
      org_id: org,
      tabelas: opcoes.tabelas || {},
      fluxo_residuo: opcoes.residuos || [],
      requisito: opcoes.requisitos || [],
      indicadores: opcoes.indicadores || null,
      trilha_auditoria: opcoes.trilha || []
    };
  }

  function lerPacote(entrada) {
    var j = entrada;
    if (typeof entrada === "string") {
      try { j = JSON.parse(entrada); } catch (e) { return { ok: false, erros: ["json_invalido"] }; }
    }
    if (!j || typeof j !== "object") return { ok: false, erros: ["pacote_vazio"] };
    var formato = j._formato || "";
    if (FORMATOS_ACEITOS.indexOf(formato) < 0) return { ok: false, erros: ["formato_desconhecido:" + formato] };
    var org = normalizarOrg(j.org_id || (j.tabelas && j.tabelas.organizacao && j.tabelas.organizacao.org_id));
    if (!orgValido(org)) return { ok: false, erros: ["org_id_ausente"] };
    var avisos = [];
    if (formato !== VERSAO) avisos.push("migrado_de:" + formato);
    // carimba org_id em tudo que veio sem
    var tabelas = j.tabelas || {};
    Object.keys(tabelas).forEach(function (t) {
      if (tabelas[t] && typeof tabelas[t] === "object" && !tabelas[t].org_id) {
        tabelas[t].org_id = org; avisos.push("org_id_carimbado:" + t);
      }
    });
    ["fluxo_residuo", "requisito", "trilha_auditoria"].forEach(function (chave) {
      (j[chave] || []).forEach(function (linha) {
        if (linha && typeof linha === "object" && !linha.org_id && chave !== "trilha_auditoria") {
          linha.org_id = org; avisos.push("org_id_carimbado:" + chave);
        }
      });
    });
    return {
      ok: true, erros: [], avisos: avisos, formato: formato, org_id: org,
      pacote: Object.assign({}, j, { _formato: VERSAO, org_id: org, tabelas: tabelas })
    };
  }

  /* ------------------------------------------------------------------ *
   * 10. Autoteste — a equipe roda isto antes de plugar
   * ------------------------------------------------------------------ */
  function verificar() {
    var falhas = [], total = 0;
    function checar(nome, cond) { total++; if (!cond) falhas.push(nome); }

    checar("18 tabelas canônicas", TABELAS.length === 18);
    checar("org_id normaliza acento e espaço", normalizarOrg(" Cliente Alfa 01 ") === "cliente-alfa-01");
    checar("org_id vazio é inválido", !orgValido(normalizarOrg("")));
    checar("tópico casa com a ponte",
      montarTopico("cliente-alfa-01", "energia", "quadro-geral") === "physis/cliente-alfa-01/energia/quadro-geral");
    checar("tópico volta inteiro",
      analisarTopico("physis/c1/energia/qg").grandeza === "energia");
    checar("tópico torto é rejeitado", analisarTopico("physis/c1/energia") === null);
    checar("número pt", num("1.234,56") === 1234.56);
    checar("número en", num("1,234.56", "en") === 1234.56);
    checar("fator não vira milhar", num("2,671") === 2.671);
    checar("alarme alto", avaliarAlarme("temperatura", 90) === "alto");
    checar("alarme sem faixa", avaliarAlarme("xpto", 1) === "sem_faixa");
    checar("resíduo sem MTR não passa",
      validarResiduo({ classe: "I", dest: "coproc", qtd: 1 }).indexOf("mtr_ausente") > -1);
    checar("classe I em coleta pública é barrada",
      validarResiduo({ classe: "I", dest: "publica", qtd: 1, mtr: "x" }).indexOf("classe_I_em_destinacao_proibida") > -1);
    checar("registro sem org_id falha", registro("medicao", { grandeza: "energia", valor: 1 }).ok === false);
    checar("registro com org_id passa", registro("medicao", { org_id: "c1", grandeza: "energia", valor: 1 }).ok === true);
    checar("indicador sem produção diz o que falta",
      indicadores({ energia_kwh_ano: 100 }).intensidade_energetica.falta.indexOf("producao_ano") > -1);
    checar("indicador calcula 80 kWh/t",
      Math.abs(indicadores({ energia_kwh_ano: 116000, producao_ano: 1450 }).intensidade_energetica.valor - 80) < 1e-9);
    checar("30 CV vira 22,065 kW de eixo",
      Math.abs(potenciaEixoKw({ potencia_cv: 30 }) - 22.065) < 1e-9);
    checar("carregamento aceita 65 e 0,65",
      Math.abs(equipamento({ tipo: "motor", potencia_cv: 30, fator_carga: 65, horas_ano: 1 }).fator_carga - 0.65) < 1e-9);
    checar("equipamento sem horas diz o que falta",
      equipamento({ tipo: "motor", potencia_cv: 30, fator_carga: 0.6 }).falta.indexOf("horas") > -1);
    checar("aquecimento resistivo não tem fator de potência",
      equipamento({ tipo: "resistivo", potencia_kw: 10, fator_carga: 1, horas_ano: 1 }).fp_efetivo === null);
    checar("motor folgado é apontado",
      equipamento({ tipo: "motor", potencia_cv: 30, fator_carga: 0.3, horas_ano: 1 }).alertas.indexOf("superdimensionado") > -1);
    checar("inventário que não fecha é apontado",
      reconciliarConsumo([{ tipo: "motor", potencia_kw: 10, fator_carga: 1, horas_ano: 1000 }], 100000).veredito === "inventario_incompleto");
    checar("calibração vencida é apontada",
      statusCalibracao("2026-01-01", "2026-09-01").estado === "vencida");
    checar("calibração perto do fim avisa antes",
      statusCalibracao("2026-10-15", "2026-09-01").estado === "vence_em_breve");
    checar("calibração longe é válida",
      statusCalibracao("2027-06-01", "2026-09-01").estado === "valida");
    checar("sem validade não há calibração",
      statusCalibracao("", "2026-09-01").estado === "sem_calibracao");
    checar("economia de 3% com incerteza de 5% não se comprova",
      economiaComprovavel(3, 5).veredito === "nao_comprova");
    checar("economia de 20% com incerteza de 2% é confortável",
      economiaComprovavel(20, 2).veredito === "confortavel");
    checar("razão entre 1 e 3 é apertada",
      economiaComprovavel(8, 4).veredito === "apertado");
    checar("instrumento sem certificado é apontado",
      validarInstrumento({ nome: "x", grandeza: "energia", exatidao: 1 }).indexOf("certificado_ausente") > -1);
    checar("plano de medição sempre começa pela entrada",
      planoMedicao({}).length === 1 && planoMedicao({}) [0].chave === "entrada");
    checar("plano ordena por maior consumo depois da entrada",
      (function () {
        var p = planoMedicao({ equipamentos: [
          { nome: "pequeno", tipo: "bomba", potencia_kw: 1, fator_carga: 1, horas_ano: 100 },
          { nome: "grande", tipo: "motor", potencia_kw: 100, fator_carga: 1, horas_ano: 8000 }] });
        return p[1].alvo === "grande";
      })());
    checar("pacote exige org_id", (function () {
      try { criarPacote({}); return false; } catch (e) { return true; }
    })());
    checar("lê o formato da tela do cliente",
      lerPacote({ _formato: "physis-tela-cliente/1", org_id: "c1", tabelas: {} }).ok === true);
    checar("rejeita formato estranho",
      lerPacote({ _formato: "outra-coisa/9", org_id: "c1" }).ok === false);
    return { ok: falhas.length === 0, total: total, falhas: falhas };
  }

  return {
    VERSAO: VERSAO, FORMATOS_ACEITOS: FORMATOS_ACEITOS, TABELAS: TABELAS,
    OBRIGATORIOS: OBRIGATORIOS, FAIXAS: FAIXAS, FATORES: FATORES,
    CLASSES: CLASSES, DESTINOS: DESTINOS,
    normalizarOrg: normalizarOrg, orgValido: orgValido, num: num,
    montarTopico: montarTopico, analisarTopico: analisarTopico, avaliarAlarme: avaliarAlarme,
    validarResiduo: validarResiduo, toneladasAno: toneladasAno, desvioAterro: desvioAterro,
    TIPOS_EQUIPAMENTO: TIPOS_EQUIPAMENTO, CV_PARA_KW: CV_PARA_KW,
    potenciaEixoKw: potenciaEixoKw, equipamento: equipamento,
    PONTOS_MEDICAO: PONTOS_MEDICAO, PONTOS_UTILIDADE: PONTOS_UTILIDADE,
    statusCalibracao: statusCalibracao, economiaComprovavel: economiaComprovavel,
    validarInstrumento: validarInstrumento, planoMedicao: planoMedicao,
    validarEquipamento: validarEquipamento, reconciliarConsumo: reconciliarConsumo,
    indicadores: indicadores, registro: registro, Trilha: Trilha,
    criarPacote: criarPacote, lerPacote: lerPacote, verificar: verificar
  };
});
