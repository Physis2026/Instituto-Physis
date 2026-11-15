/* physis-calc-comum.js v1 — contas que a plataforma, o SustainKit e o Planejador fazem do MESMO jeito (15/11/2026).
   Uma regra só para: economia solar pela Lei 14.300 (autoconsumo, energia injetada, Fio B e custo de disponibilidade),
   irradiação no plano das placas (modelo isotrópico), banco de baterias, cisterna de água de chuva mês a mês com descarte
   inicial, calhas pela NBR 10844 e aquecimento solar mês a mês. Os números vêm da base de premissas
   (sistema/physis-premissas.json), copiada abaixo entre PREMISSAS-INICIO e PREMISSAS-FIM.
   Como atualizar: mude o JSON e rode `python ferramentas/sincronizar.py` (copia o JSON para cá e este arquivo para os
   blocos <script id="physis-calc-comum"> do painel, do SustainKit e do Planejador). Espelho em Python e testes:
   physis-hub/tests/test_adequacoes_normas.py. Normas citadas só pelo número e item; redação própria.
   Contrato: window.PhysisCalc = { premissa, info, fioB, economiaSolar, h0Mensal, fatorPlano, bateria, diasChuva, cisterna,
   calhas, coletorMensal }. Funções puras (não leem nem escrevem a tela). Sem internet. */
(function (global) {
"use strict";
if (global.PhysisCalc) return;
/*PREMISSAS-INICIO*/
var PREMISSAS = {"versao":1,"atualizado":"2026-11-15","premissas":[{"id":"agua.per_capita","grandeza":"Consumo de água por pessoa","valor_padrao":130,"unidade":"L/pessoa·dia","opcoes":[{"rotulo":"Residência, padrão alto","valor":160,"quando":"casas de padrão alto; é o valor da Residência no Planejador"},{"rotulo":"Residência, padrão médio","valor":130,"quando":"padrão do SustainKit para moradia"},{"rotulo":"Residência, padrão baixo","valor":100,"quando":"moradia de padrão baixo ou uso muito econômico"},{"rotulo":"Edifício residencial (Planejador)","valor":150,"quando":"prédio de apartamentos, valor de catálogo do Planejador"},{"rotulo":"Hospedagem sem cozinha e lavanderia","valor":100,"quando":"hotel ou pousada em que cozinha e lavanderia são contadas à parte"},{"rotulo":"Hospedagem (Planejador)","valor":120,"quando":"chalé ou pousada, valor de catálogo do Planejador"},{"rotulo":"Escritório","valor":50,"quando":"escritório, estúdio, prédio comercial ou público"}],"fonte":"ABNT NBR 7229:1993, tabela de contribuição (os valores de residência, hospedagem e escritório); Planejador Physis (edifício residencial 150 e hospedagem 120, premissa Physis)","nota":"A tabela da NBR 7229 dá a contribuição de esgoto; aqui ela é usada como estimativa de consumo de água. Medição real do projeto sempre vale mais que este número."},{"id":"chuva.coef_escoamento","grandeza":"Coeficiente de escoamento do telhado (parte da chuva que chega à cisterna)","valor_padrao":0.8,"unidade":"adimensional (0 a 1)","opcoes":[{"rotulo":"Telha cerâmica","valor":0.8,"quando":"telhado de telha cerâmica"},{"rotulo":"Telha metálica","valor":0.9,"quando":"telhado metálico"},{"rotulo":"Fibrocimento","valor":0.85,"quando":"telha de fibrocimento"},{"rotulo":"Concreto ou laje","valor":0.8,"quando":"laje impermeabilizada"},{"rotulo":"Telhado verde","valor":0.3,"quando":"cobertura vegetada"}],"fonte":"premissa Physis (literatura técnica de aproveitamento de água de chuva); ABNT NBR 15527:2019 não fixa um valor único","nota":"Usado no SustainKit (captação) e no Planejador (balanço da cisterna). Valor do projeto escolhido pelo material real do telhado."},{"id":"app.declividade","grandeza":"Declividade a partir da qual a encosta é APP","valor_padrao":45,"unidade":"graus (°)","opcoes":[{"rotulo":"Limite legal","valor":45,"quando":"sempre: encostas acima de 45° são APP"}],"fonte":"Lei 12.651/2012 (Código Florestal), art. 4º, V","nota":"45° = 100% de declividade (sobe 100 m em 100 m andados). Não confundir com 45% (cerca de 24°). Lei municipal ou plano de manejo da APA podem ser mais restritivos."},{"id":"pv.pr","grandeza":"Rendimento global do sistema solar (PR)","valor_padrao":0.78,"unidade":"adimensional (0 a 1)","opcoes":[{"rotulo":"Padrão Physis","valor":0.78,"quando":"estudo preliminar, sem simulação do sistema real"}],"fonte":"premissa Physis","nota":"Inclui perdas de temperatura, sujeira, cabos e inversor. Trocar pelo valor simulado quando houver projeto executivo. Também é o PR do agro solar do SustainKit (antes 0,75 fixo)."},{"id":"bateria.dod","grandeza":"Profundidade de descarga da bateria (DoD)","valor_padrao":0.9,"unidade":"adimensional (0 a 1)","opcoes":[{"rotulo":"LiFePO4 (lítio-ferro-fosfato)","valor":0.9,"quando":"bateria de lítio-ferro-fosfato"},{"rotulo":"Li-NMC","valor":0.85,"quando":"bateria de lítio NMC"},{"rotulo":"Chumbo-ácido ou AGM","valor":0.5,"quando":"bateria de chumbo-ácido ou AGM"}],"fonte":"premissa Physis (conferir na folha de dados do fabricante escolhido)","nota":"Regra única do banco de baterias (plataforma, SustainKit e agro): consumo diário × horas ÷ 24 ÷ DoD ÷ bateria.rendimento."},{"id":"rede.fator_emissao","grandeza":"Fator de emissão da energia da rede (SIN)","valor_padrao":0.0289,"unidade":"tCO2/MWh","opcoes":[{"rotulo":"Fator médio do SIN","valor":0.0289,"quando":"inventário de emissões da energia comprada da rede"}],"fonte":"fator médio SIN (MCTI), conferir ano","nota":"Mesmo valor de FATORES.rede em sistema/physis-nucleo.js. O fator muda todo ano; atualizar aqui e no núcleo juntos."},{"id":"combustivel.diesel","grandeza":"Fator de emissão do diesel","valor_padrao":2.671,"unidade":"kgCO2e/L","opcoes":[],"fonte":"valor usado em sistema/physis-nucleo.js (FATORES.diesel); conferir fonte e ano","nota":"Mantido igual ao núcleo. O SustainKit usa este fator por litro, igual à aba Carbono (antes 0,74 kgCO2e/kWh)."},{"id":"combustivel.glp","grandeza":"Fator de emissão do GLP","valor_padrao":2.939,"unidade":"kgCO2e/kg","opcoes":[],"fonte":"valor usado em sistema/physis-nucleo.js (FATORES.glp); conferir fonte e ano","nota":"Mantido igual ao núcleo."},{"id":"combustivel.gn","grandeza":"Fator de emissão do gás natural","valor_padrao":1.999,"unidade":"kgCO2e/m³","opcoes":[],"fonte":"valor usado em sistema/physis-nucleo.js (FATORES.gn); conferir fonte e ano","nota":"Mantido igual ao núcleo."},{"id":"solar.fio_b_escala","grandeza":"Parte do Fio B que a energia injetada não compensa, por ano (Lei 14.300)","valor_padrao":{"2023":0.15,"2024":0.3,"2025":0.45,"2026":0.6,"2027":0.75,"2028":0.9},"unidade":"fração do componente Fio B da tarifa (0 a 1), por ano","opcoes":[{"rotulo":"Regra de transição (art. 27)","valor":"lei14300","quando":"unidade com pedido de acesso depois de 07/01/2023"},{"rotulo":"Regra antiga (art. 26)","valor":"antiga","quando":"pedido de acesso até 07/01/2023: sem Fio B até 2045"}],"fonte":"Lei 14.300/2022, art. 27 (escala de transição) e art. 26 (regra antiga até 2045); depois de 2028 a regra é da ANEEL (art. 17) [CONFERIR NA LEI]","status":"conferir","nota":"Percentuais lembrados da lei: o engenheiro confere no texto oficial antes de usar em proposta. Depois do último ano a conta repete o último percentual e avisa."},{"id":"tarifa.custo_disponibilidade","grandeza":"Custo de disponibilidade (consumo mínimo faturado por mês)","valor_padrao":{"monofasico":30,"bifasico":50,"trifasico":100},"unidade":"kWh/mês, por tipo de ligação","opcoes":[{"rotulo":"Monofásico","valor":30,"quando":"ligação monofásica"},{"rotulo":"Bifásico","valor":50,"quando":"ligação bifásica"},{"rotulo":"Trifásico","valor":100,"quando":"ligação trifásica"}],"fonte":"REN ANEEL 1.000/2021 (custo de disponibilidade por tipo de ligação) [CONFERIR NA RESOLUÇÃO]","status":"conferir","nota":"A conta de luz nunca fica abaixo deste mínimo, com ou sem geração própria."},{"id":"solar.albedo","grandeza":"Refletância do solo em volta das placas (albedo)","valor_padrao":0.2,"unidade":"adimensional (0 a 1)","opcoes":[{"rotulo":"Solo, grama ou telhado comum","valor":0.2,"quando":"valor usual sem neve"}],"fonte":"Duffie & Beckman, Solar Engineering of Thermal Processes, 4ª ed., 2013 (valor usual de refletância do solo no modelo isotrópico); premissa Physis","status":"conferir","nota":"Só pesa em placas muito inclinadas. Superfície clara (brita branca, membrana) reflete mais: trocar pelo valor medido."},{"id":"bateria.rendimento","grandeza":"Rendimento de ida e volta da bateria com o inversor","valor_padrao":0.95,"unidade":"adimensional (0 a 1)","opcoes":[{"rotulo":"Lítio (LiFePO4) com inversor híbrido","valor":0.95,"quando":"padrão da Physis; o valor que a aba Energia solar já usava"}],"fonte":"premissa Physis (regra única do banco de baterias desde 15/11/2026: plataforma, SustainKit e agro); conferir na folha de dados da bateria e do inversor","status":"conferir","nota":"Banco = consumo diário × horas ÷ 24 ÷ DoD ÷ rendimento. Substitui a margem de 1,2 do SustainKit e do agro."},{"id":"agro.autonomia_dias","grandeza":"Dias de autonomia da bateria no agro solar","valor_padrao":2,"unidade":"dias","opcoes":[{"rotulo":"Padrão do agro","valor":2,"quando":"cargas do campo sem rede"}],"fonte":"premissa Physis (valor que o agro do SustainKit já usava)","status":"conferir","nota":"Entra como horas = dias × 24 na regra única do banco de baterias."},{"id":"biogas.pci","grandeza":"Energia do biogás","valor_padrao":6,"unidade":"kWh/m³","opcoes":[],"fonte":"premissa Physis (mesmo valor do Planejador, physisBiogas, e da aba Carbono); conferir com o teor de metano medido","status":"conferir","nota":"Usado para dizer quanto GLP o biogás substitui (emissões evitadas)."},{"id":"glp.pci","grandeza":"Energia do GLP","valor_padrao":12.8,"unidade":"kWh/kg","opcoes":[],"fonte":"premissa Physis (valor da aba Carbono); conferir com a ficha do combustível","status":"conferir","nota":"Biogás evitado = m³ × biogas.pci ÷ glp.pci × fator do GLP (combustivel.glp). Regra única: aba Carbono e SustainKit."},{"id":"drenagem.calha_tr","grandeza":"Tempo de retorno da chuva para calhas e condutores","valor_padrao":5,"unidade":"anos","opcoes":[{"rotulo":"Área pavimentada onde empoçar é tolerável","valor":1,"quando":"[CONFERIR NA NORMA]"},{"rotulo":"Coberturas e terraços","valor":5,"quando":"padrão [CONFERIR NA NORMA]"},{"rotulo":"Coberturas onde não pode transbordar","valor":25,"quando":"[CONFERIR NA NORMA]"}],"fonte":"ABNT NBR 10844:1989 (período de retorno das instalações de águas pluviais) [CONFERIR NA NORMA]","status":"conferir","nota":"Usado com a equação IDF do lugar."},{"id":"drenagem.calha_duracao","grandeza":"Duração da chuva de projeto para calhas e condutores","valor_padrao":5,"unidade":"min","opcoes":[],"fonte":"ABNT NBR 10844:1989 (duração da precipitação) [CONFERIR NA NORMA]","status":"conferir","nota":"Entra na IDF do lugar: i = K·T^a ÷ (t + b)^c."},{"id":"drenagem.calha_manning_n","grandeza":"Coeficiente de rugosidade da calha (Manning)","valor_padrao":0.011,"unidade":"adimensional","opcoes":[{"rotulo":"Plástico, fibrocimento, aço ou metal","valor":0.011,"quando":"[CONFERIR NA NORMA]"},{"rotulo":"Concreto alisado ou alvenaria revestida","valor":0.012,"quando":"[CONFERIR NA NORMA]"},{"rotulo":"Cerâmica ou concreto não alisado","valor":0.013,"quando":"[CONFERIR NA NORMA]"}],"fonte":"ABNT NBR 10844:1989 (tabela de coeficientes de rugosidade) [CONFERIR NA NORMA]","status":"conferir","nota":"Usado na fórmula de Manning para a lâmina d'água da calha."},{"id":"drenagem.calha_declividade","grandeza":"Declividade da calha","valor_padrao":0.005,"unidade":"m/m","opcoes":[],"fonte":"ABNT NBR 10844:1989 (declividade mínima de calhas) [CONFERIR NA NORMA]","status":"conferir","nota":"Calha mais inclinada escoa mais com a mesma seção."},{"id":"drenagem.condutor_diam_min","grandeza":"Diâmetro interno mínimo do condutor vertical","valor_padrao":70,"unidade":"mm","opcoes":[],"fonte":"ABNT NBR 10844:1989 (condutores verticais) [CONFERIR NA NORMA]","status":"conferir","nota":"O diâmetro final sai do ábaco da norma com a vazão e a altura da lâmina na calha; o sistema mostra a vazão a conduzir."},{"id":"chuva.descarte_inicial","grandeza":"Descarte da primeira chuva (lavagem do telhado)","valor_padrao":2,"unidade":"mm por chuva","opcoes":[{"rotulo":"Sem dado do local","valor":2,"quando":"valor recomendado na falta de dados [CONFERIR NA NORMA]"}],"fonte":"ABNT NBR 15527:2019 (descarte da água do escoamento inicial) [CONFERIR NA NORMA]","status":"conferir","nota":"Descontado em cada dia de chuva: captado = área × (chuva × coeficiente − descarte × dias de chuva)."},{"id":"agua.fracao_nao_potavel","grandeza":"Parte do consumo das pessoas que pode ser água de chuva (usos não potáveis)","valor_padrao":0.3,"unidade":"adimensional (0 a 1)","opcoes":[{"rotulo":"Padrão do Planejador","valor":0.3,"quando":"descarga, limpeza e lavagem"}],"fonte":"premissa Physis (valor que o Planejador já usava); ABNT NBR 16783:2019 lista os usos não potáveis","status":"conferir","nota":"Mesma regra no Planejador e no SustainKit para a cisterna sair igual."},{"id":"agua.reserva_dias","grandeza":"Dias de reserva de água fria","valor_padrao":2,"unidade":"dias","opcoes":[{"rotulo":"Padrão Physis","valor":2,"quando":"estudo preliminar"}],"fonte":"premissa Physis; a ABNT NBR 5626:2020 deixa a reservação ao projetista e à concessionária","status":"conferir","nota":"Usado no Planejador (reservação) e no SustainKit (cisterna do fluxo da água)."},{"id":"esgoto.coef_retorno","grandeza":"Coeficiente de retorno (parte da água usada que vira esgoto)","valor_padrao":0.8,"unidade":"adimensional (0 a 1)","opcoes":[],"fonte":"ABNT NBR 9649:1986 (coeficiente de retorno) [CONFERIR NA NORMA]","status":"conferir","nota":"Usado no fluxo da água do SustainKit."},{"id":"app.faixa_rio","grandeza":"Largura da faixa de APP ao longo de rios e córregos, pela largura do rio","valor_padrao":[{"largura_ate_m":10,"faixa_m":30},{"largura_ate_m":50,"faixa_m":50},{"largura_ate_m":200,"faixa_m":100},{"largura_ate_m":600,"faixa_m":200},{"largura_ate_m":null,"faixa_m":500}],"unidade":"m (medidos da borda da calha do leito regular, para cada lado)","opcoes":[{"rotulo":"Rio com menos de 10 m","valor":30,"quando":"[CONFERIR NA LEI]"},{"rotulo":"10 a 50 m","valor":50,"quando":"[CONFERIR NA LEI]"},{"rotulo":"50 a 200 m","valor":100,"quando":"[CONFERIR NA LEI]"},{"rotulo":"200 a 600 m","valor":200,"quando":"[CONFERIR NA LEI]"},{"rotulo":"Mais de 600 m","valor":500,"quando":"[CONFERIR NA LEI]"}],"fonte":"Lei 12.651/2012 (Código Florestal), art. 4º, I, alíneas a a e [CONFERIR NA LEI]","status":"conferir","nota":"O engenheiro aprova as larguras. Área urbana consolidada e lei municipal podem ter regra própria (conferir). A faixa só é desenhada quando há um rio no mapa e a largura dele foi digitada."},{"id":"app.raio_nascente","grandeza":"Raio da APP em volta de nascentes e olhos d'água perenes","valor_padrao":50,"unidade":"m","opcoes":[],"fonte":"Lei 12.651/2012 (Código Florestal), art. 4º, IV [CONFERIR NA LEI]","status":"conferir","nota":"O engenheiro aprova. Só é desenhado quando há uma nascente marcada no mapa."},{"id":"resiliencia.encosta_limiares","grandeza":"Chuva acumulada que muda o nível de alerta de encosta","valor_padrao":{"atencao_24h":40,"alerta_24h":80,"atencao_72h":60,"alerta_72h":120},"unidade":"mm","opcoes":[{"rotulo":"Referência de planejamento Physis","valor":"padrão","quando":"sem limiar da Defesa Civil do município"}],"fonte":"premissa Physis (valores que a aba Resiliência já usava); trocar pelos limiares da Defesa Civil do município","status":"conferir","nota":"Os limiares digitados na tela (Defesa Civil) valem no lugar destes."},{"id":"res.alertas_limiares","grandeza":"Limiares dos alertas por atividade (previsão do tempo)","valor_padrao":{"geada_tmin_c":3,"colheita_chuva_mm":10,"rebanho_tmax_c":30,"irrigacao_chuva_mm":5,"horta_chuva_mm":30,"horta_tmin_c":4,"horta_tmax_c":34,"hospedagem_chuva_mm":30},"unidade":"°C ou mm por dia","opcoes":[],"fonte":"premissa Physis (valores que os alertas da plataforma já usavam); conferir com o técnico da atividade","status":"conferir","nota":"Alertas de planejamento; não substituem a Defesa Civil nem o agrônomo."},{"id":"residuos.rendimentos","grandeza":"Rendimento de cada rota de resíduo no próprio lugar","valor_padrao":{"compostagem":0.35,"vermi":0.3,"larvas":0.15,"biodiesel_l_por_l_oleo":0.9,"filamento":0.85,"agregado":0.9,"biomassa_kwh_por_kg":4.0,"biochar":0.25},"unidade":"kg de produto por kg de resíduo (biodiesel em L por L de óleo; biomassa em kWh por kg)","opcoes":[],"fonte":"premissa Physis (estimativas de literatura que a Economia circular já usava) [CONFERIR]","status":"conferir","nota":"Ordem de grandeza para planejar; o rendimento real é medido."},{"id":"residuos.biogas_por_kg","grandeza":"Biogás por kg de resíduo fresco","valor_padrao":{"alimentos":0.1,"esterco_bov":0.04,"esterco_sui":0.06,"cama_aviario":0.07,"colheita":0.05,"outros":0.05},"unidade":"m³/kg","opcoes":[],"fonte":"premissa Physis (estimativas de literatura que a Economia circular já usava) [CONFERIR]","status":"conferir","nota":"Mesmos valores na aba Carbono (biogás do plano de resíduos)."},{"id":"agua.referencias_por_uso","grandeza":"Faixas de referência por uso da água (só informação, nunca limite)","valor_padrao":{"beber":{"rotulo":"Água para beber","fonte":"Portaria GM/MS 888/2021 [CONFERIR NA PORTARIA]","turbidez_max_ut":5,"cloro_min_mgl":0.2,"cloro_max_mgl":5,"ph_min":6,"ph_max":9},"rio":{"rotulo":"Rio ou represa (água doce classe 2)","fonte":"Resolução CONAMA 357/2005 [CONFERIR NA RESOLUÇÃO]","turbidez_max_ut":100,"ph_min":6,"ph_max":9},"efluente":{"rotulo":"Efluente lançado","fonte":"Resolução CONAMA 430/2011 [CONFERIR NA RESOLUÇÃO]","ph_min":5,"ph_max":9},"reuso":{"rotulo":"Reúso (classe mais exigente)","fonte":"ABNT NBR 13969:1997 (classes de reúso) [CONFERIR NA NORMA]","turbidez_max_ut":5,"cloro_min_mgl":0.5,"cloro_max_mgl":1.5,"ph_min":6,"ph_max":8}},"unidade":"uT, mg/L e pH","opcoes":[],"fonte":"Portaria GM/MS 888/2021; Resoluções CONAMA 357/2005 e 430/2011; ABNT NBR 13969:1997 [CONFERIR]","status":"conferir","nota":"Aparece ao lado de cada limite como informação. Nada é preenchido e nenhum alerta sai sem o limite digitado pela pessoa (regra 3)."},{"id":"avac.exaustao","grandeza":"Vazões e trocas de ar das exaustões (banheiro, lixo, garagem)","valor_padrao":{"vazao_banheiro_m3h":90,"trocas_banheiro_h":15,"trocas_lixo_h":20,"trocas_garagem_h":6,"garagem_ls_por_m2":7.5,"garagem_m3h_por_vaga":300},"unidade":"m³/h, trocas por hora, L/s·m²","opcoes":[],"fonte":"planilha PHYSIS_AVAC-5 (premissa Physis); exaustão de banheiro, lixo e garagem não tem vazão em NBR: conferir com o código de obras do município e a NBR 16401-3","status":"conferir","nota":"Valores de partida da tela de Ventilação; o projeto troca pelos do código de obras."},{"id":"avac.velocidade_dutos","grandeza":"Velocidade máxima do ar por tipo de duto","valor_padrao":{"Prumada residencial (shaft)":8,"Ramal em forro — residencial":5,"Exaustão técnica (lixo, bombas)":8,"Garagem":12,"Pressurização e fumaça":12,"Duto principal — comercial":10},"unidade":"m/s","opcoes":[],"fonte":"planilha PHYSIS_AVAC-5 (premissa Physis); conferir os limites de velocidade e ruído na ABNT NBR 16401-1 [CONFERIR NA NORMA]","status":"conferir","nota":"Usado para conferir a velocidade adotada em cada sistema de dutos."}]};
/*PREMISSAS-FIM*/
var DIAS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], DIA_REP = [17, 47, 75, 105, 135, 162, 198, 228, 258, 288, 318, 344];
var RAD = Math.PI / 180, POR_ID = {};
(PREMISSAS.premissas || []).forEach(function (p) { POR_ID[p.id] = p; });

/* valor padrão de uma premissa da base (ou null se não existir) */
function premissa(id) { var p = POR_ID[id]; return p ? p.valor_padrao : null; }
function info(id) { return POR_ID[id] || null; }
function num(x, d) { return typeof x === "number" && isFinite(x) ? x : d; }

/* ── Lei 14.300/2022, art. 27: parte do Fio B que a energia injetada NÃO compensa, por ano ──
   escala = premissa solar.fio_b_escala ({"2023": 0.15, …}); depois do último ano da escala a lei manda a ANEEL
   definir a regra (art. 17): a conta repete o último percentual e avisa (alem = true). regra "antiga" = pedido de
   acesso até 07/01/2023 (art. 26): sem Fio B até 2045. */
function fioB(ano, regra, escala) {
  escala = escala || premissa("solar.fio_b_escala") || {};
  if (regra === "antiga") return { pct: ano <= 2045 ? 0 : null, alem: ano > 2045 };
  var anos = Object.keys(escala).map(Number).sort(function (a, b) { return a - b; });
  if (!anos.length) return { pct: null, alem: false };
  if (ano < anos[0]) return { pct: 0, alem: false };
  var ult = anos[anos.length - 1];
  if (ano > ult) return { pct: escala[String(ult)], alem: true };
  var k = anos.filter(function (a) { return a <= ano; }).pop();
  return { pct: escala[String(k)], alem: false };
}

/* ── Economia da energia solar, mês a mês ──
   p.ger_meses[12] kWh gerados; p.consumo_ano kWh (ou p.consumo_meses[12]); p.autoconsumo 0–1 (parte da geração usada
   na hora); p.tarifa R$/kWh; p.fio_b R$/kWh (componente Fio B da TUSD) ou null; p.ano 1º ano; p.regra "lei14300"|"antiga";
   p.disponibilidade kWh/mês (mínimo por tipo de ligação) ou null.
   Mês a mês: autoconsumo = min(geração × parte, consumo); injetada = geração − autoconsumo; créditos compensam o que
   veio da rede (sobra fica como crédito); a energia compensada paga pct(ano) × Fio B; a conta nunca fica abaixo do custo
   de disponibilidade. economia = conta sem solar − conta com solar. */
function economiaSolar(p) {
  var ger = p.ger_meses || [], a = Math.max(0, Math.min(1, num(p.autoconsumo, 1))), t = num(p.tarifa, 0), fb = num(p.fio_b, null);
  var temCons = p.consumo_meses ? true : num(p.consumo_ano, 0) > 0, disp = num(p.disponibilidade, 0), ano = num(p.ano, new Date().getFullYear());
  var f = fioB(ano, p.regra, p.escala), pct = f.pct == null ? 0 : f.pct, cred = 0, r = { auto: 0, injetada: 0, compensada: 0, credito_sobra: 0, economia: 0, ano: ano, pct_fio_b: f.pct, alem_da_escala: f.alem, avisos: [] };
  for (var m = 0; m < 12; m++) {
    var g = num(ger[m], 0), cons = temCons ? (p.consumo_meses ? num(p.consumo_meses[m], 0) : p.consumo_ano / 12) : Infinity;
    var au = Math.min(g * a, cons), inj = g - au, rede = cons - au;
    cred += inj; var comp = Math.min(cred, rede); cred -= comp;
    var custoFio = fb != null ? comp * pct * fb : 0;
    if (temCons) {
      var antes = Math.max(cons, disp) * t, depoisE = (rede - comp) * t + custoFio, depois = Math.max(depoisE, disp * t);
      r.economia += antes - depois;
    } else r.economia += au * t + comp * t - custoFio;
    r.auto += au; r.injetada += inj; r.compensada += comp;
  }
  r.credito_sobra = cred;
  if (fb == null && a < 1) r.avisos.push("Sem o valor do Fio B da tarifa: a economia da energia injetada está sem o desconto da Lei 14.300.");
  if (f.alem) r.avisos.push("Depois do último ano da escala do art. 27 a regra é da ANEEL: a conta repete o último percentual [CONFERIR].");
  if (!temCons) r.avisos.push("Sem consumo informado: não dá para aplicar o custo de disponibilidade nem limitar os créditos.");
  if (cred > 0.5) r.avisos.push("Sobram créditos no fim do ano: energia injetada além do consumo não vira dinheiro (vale como crédito por até 60 meses).");
  return r;
}

/* ── Sol fora da atmosfera, média do mês (Duffie & Beckman, cap. 1) ── kWh/m²·dia */
function h0Mensal(lat) {
  return DIA_REP.map(function (n) {
    var d = 23.45 * Math.sin(RAD * 360 * (284 + n) / 365) * RAD, f = lat * RAD, ws = Math.acos(Math.max(-1, Math.min(1, -Math.tan(f) * Math.tan(d))));
    var E = 1 + 0.033 * Math.cos(2 * Math.PI * n / 365);
    return 24 / Math.PI * 1.367 * E * (Math.cos(f) * Math.cos(d) * Math.sin(ws) + ws * Math.sin(f) * Math.sin(d));
  });
}

/* ── Irradiação no plano das placas, modelo isotrópico (Liu e Jordan; Duffie & Beckman, cap. 2) ──
   H[12] horizontal (kWh/m²·dia); lat (°); incl β (°, 0 = plano); azim (°, para onde a face aponta: 0 = norte,
   90 = leste, 180 = sul, 270 = oeste); albedo ρ (premissa solar.albedo).
   HT/H = (1 − Hd/H)·Rb + (Hd/H)·(1 + cos β)/2 + ρ·(1 − cos β)/2
   Hd/H pela correlação mensal de Erbs (Duffie & Beckman, eq. da fração difusa média do mês) com KT = H/H0;
   Rb = razão entre o sol direto no plano e no horizontal, integrada ao longo do dia médio do mês.
   Plano horizontal (β = 0) dá fator 1 em todos os meses. */
function fatorPlano(H, lat, incl, azim, albedo) {
  var b = num(incl, 0) * RAD, A = num(azim, 0) * RAD, rho = num(albedo, num(premissa("solar.albedo"), 0.2)), H0 = h0Mensal(lat), f = lat * RAD;
  var n = [Math.sin(b) * Math.sin(A), Math.sin(b) * Math.cos(A), Math.cos(b)];
  var fator = DIA_REP.map(function (dn, m) {
    var h = num(H[m], 0); if (!(h > 0) || b === 0) return 1;
    var d = 23.45 * Math.sin(RAD * 360 * (284 + dn) / 365) * RAD, ws = Math.acos(Math.max(-1, Math.min(1, -Math.tan(f) * Math.tan(d))));
    var sP = 0, sH = 0, N = 240;
    for (var k = 0; k < N; k++) {
      var w = -ws + (k + 0.5) * 2 * ws / N;
      var s = [-Math.cos(d) * Math.sin(w), Math.sin(d) * Math.cos(f) - Math.cos(d) * Math.sin(f) * Math.cos(w), Math.sin(f) * Math.sin(d) + Math.cos(f) * Math.cos(d) * Math.cos(w)];
      if (s[2] <= 0) continue;
      sH += s[2]; sP += Math.max(0, n[0] * s[0] + n[1] * s[1] + n[2] * s[2]);
    }
    var Rb = sH > 0 ? sP / sH : 1, kt = Math.max(0.3, Math.min(0.8, h / H0[m]));
    var fd = ws <= 81.4 * RAD ? 1.391 - 3.560 * kt + 4.189 * kt * kt - 2.137 * kt * kt * kt : 1.311 - 3.022 * kt + 3.427 * kt * kt - 1.821 * kt * kt * kt;
    return (1 - fd) * Rb + fd * (1 + Math.cos(b)) / 2 + rho * (1 - Math.cos(b)) / 2;
  });
  var hT = fator.map(function (x, m) { return num(H[m], 0) * x; }), sh = 0, st = 0;
  for (var m = 0; m < 12; m++) { sh += num(H[m], 0) * DIAS[m]; st += hT[m] * DIAS[m]; }
  return { fator: fator, Ht: hT, anual: sh > 0 ? st / sh : 1 };
}

/* ── Banco de baterias: uma regra para a plataforma, o SustainKit e o agro ──
   E (kWh) = consumo diário (kWh) × horas de autonomia ÷ 24 ÷ DoD ÷ rendimento (premissas bateria.dod e bateria.rendimento) */
function bateria(consumoDia, horas, dod, rend) {
  dod = num(dod, premissa("bateria.dod")); rend = num(rend, premissa("bateria.rendimento"));
  if (!(consumoDia > 0) || !(horas > 0) || !(dod > 0) || !(rend > 0)) return 0;
  return consumoDia * horas / 24 / dod / rend;
}

/* dias de chuva por mês estimados pela chuva do mês (mesma regra do Planejador desde 2026): 2 + mm/12, entre 3 e (dias do mês − 2).
   Estimativa: a normal climatológica do INMET dá o valor real. */
function diasChuva(ch) { return ch.map(function (c, m) { return Math.max(3, Math.min(DIAS[m] - 2, Math.round(2 + num(c, 0) / 12))); }); }

/* ── Cisterna de água de chuva, balanço mês a mês (ABNT NBR 15527:2019, dimensionamento do reservatório) ──
   p.chuva[12] mm; p.area m² de telhado; p.coef (premissa chuva.coef_escoamento); p.demanda m³/mês (usos não potáveis);
   p.descarte mm por chuva (premissa chuva.descarte_inicial); p.dias[12] dias de chuva (ou estimados);
   p.volumes m³ candidatos; p.alvo parte da demanda atendida (0,95); p.anos de simulação (10).
   captado no mês = área × max(0, chuva × coef − descarte × dias de chuva) ÷ 1000 (m³);
   S(m) = min(V, S(m−1) + captado − demanda); falta quando S < 0 (conta só o último ano, já em regime).
   Devolve o menor volume que atinge o alvo (ou o maior testado), a cobertura, o captado e o descarte de cada mês e o pior mês. */
var VOLUMES = [5, 10, 15, 20, 30, 45, 60, 90, 120, 160, 220];
function cisterna(p) {
  var ch = p.chuva || [], area = num(p.area, 0), coef = num(p.coef, premissa("chuva.coef_escoamento")), dem = num(p.demanda, 0);
  var desc = num(p.descarte, premissa("chuva.descarte_inicial")) || 0, dias = p.dias && p.dias.length === 12 ? p.dias : diasChuva(ch);
  var cap = ch.map(function (c, m) { return area * Math.max(0, num(c, 0) * coef - desc * dias[m]) / 1000; });
  var desc_m3 = ch.map(function (c, m) { return area * Math.min(num(c, 0) * coef, desc * dias[m]) / 1000; });
  var vols = p.volumes || VOLUMES, alvo = num(p.alvo, 0.95), anos = num(p.anos, 10), best = null;
  for (var i = 0; i < vols.length; i++) {
    var V = vols[i], e = V, f = 0;
    for (var k = 0; k < anos; k++) for (var m = 0; m < 12; m++) { e = Math.min(V, e + cap[m] - dem); if (e < 0) { if (k === anos - 1) f += -e; e = 0; } }
    var cob = 1 - f / (dem * 12 || 1);
    best = { V: V, cob: cob };
    if (cob >= alvo) break;
  }
  var pior = 0; for (var j = 1; j < 12; j++) if (cap[j] - dem < cap[pior] - dem) pior = j;
  return { V: best ? best.V : null, cob: best ? best.cob : null, dem: dem, roofs: area, coef: coef, descarte_mm: desc, dias: dias,
    captado: cap, descartado: desc_m3, captado_ano: cap.reduce(function (a, b) { return a + b; }, 0), pior_mes: pior };
}

/* ── Calhas e condutores (ABNT NBR 10844:1989): vazão de cada água de telhado ──
   aguas: [{ nome, a (m, projeção horizontal no sentido do caimento), b (m, comprimento da calha), incl (°) }];
   i = intensidade (mm/h) da IDF do lugar no tempo de retorno e na duração da premissa;
   área de contribuição de superfície inclinada = (a + h/2) · b, com h = a · tan(incl) (correção da norma pela inclinação);
   Q (L/min) = i · A / 60.
   Calha retangular com largura = 2 × lâmina (seção hidráulica mais econômica), fórmula de Manning em L/min:
   Q = 60.000 · (S/n) · Rh^(2/3) · I^(1/2) → lâmina y; n e I das premissas (conferir na norma).
   O diâmetro do condutor vertical sai do ábaco da norma: aqui só o mínimo da premissa e a vazão a conduzir. */
function calhas(aguas, i, opc) {
  opc = opc || {}; var n = num(opc.n, premissa("drenagem.calha_manning_n")), I = num(opc.declividade, premissa("drenagem.calha_declividade"));
  return (aguas || []).map(function (w) {
    var h = w.a * Math.tan(num(w.incl, 0) * RAD), A = (w.a + h / 2) * w.b, Q = i * A / 60, y = null;
    if (n > 0 && I > 0 && Q > 0) y = Math.pow(Q * n / (60000 * 2 * Math.sqrt(I) * Math.pow(0.5, 2 / 3)), 3 / 8);
    return { nome: w.nome, a: w.a, b: w.b, incl: num(w.incl, 0), h: h, area: A, q_l_min: Q, lamina_m: y, largura_m: y == null ? null : 2 * y,
      condutor_min_mm: premissa("drenagem.condutor_diam_min") };
  });
}

/* ── Aquecimento solar de água mês a mês (ABNT NBR 15569:2020, roteiro do método simplificado) ──
   produção do coletor no mês (kWh/m²·dia) = eficiência média da etiqueta Inmetro (ENCE, 0–1) × irradiação no plano
   do coletor no mês; área = parcela solar ÷ produção do PIOR mês (o sistema atende o ano todo). */
function coletorMensal(Ht, eta, parcela) {
  var prod = (Ht || []).map(function (h) { return num(h, 0) * num(eta, 0); }), pior = 0;
  for (var m = 1; m < prod.length; m++) if (prod[m] < prod[pior]) pior = m;
  return { prod: prod, pior_mes: pior, prod_pior: prod.length ? prod[pior] : null, area: prod.length && prod[pior] > 0 ? parcela / prod[pior] : null };
}

global.PhysisCalc = { PREMISSAS: PREMISSAS, DIAS: DIAS, premissa: premissa, info: info, fioB: fioB, economiaSolar: economiaSolar, h0Mensal: h0Mensal,
  fatorPlano: fatorPlano, bateria: bateria, diasChuva: diasChuva, cisterna: cisterna, calhas: calhas, coletorMensal: coletorMensal };
})(typeof window !== "undefined" ? window : this);
