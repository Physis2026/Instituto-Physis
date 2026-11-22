"""Inglês do que os motores escrevem na Modelagem Physis 3D (dona, 21/11/2026: "tudo deve funcionar antes do lançamento").
Só texto da tela: nenhuma conta muda. Os motores (physis-simulacao.js, physis-3d.js, casos.js) são cópias exatas e não são
alterados; a casca do laboratório aplica este dicionário sobre o que eles escrevem quando o idioma é English.
Conferido pela varredura tests/test_inovastem.py::InglesNoNavegador (todas as subabas e todos os casos)."""

# texto exato (espaços normalizados) -> inglês
MOTOR_EN = {
    # ── rótulos dos resultados (physis-simulacao.js, render) ──
    "Acumulação de fluxo (células a montante)": "Flow accumulation (upstream cells)",
    "Atraso térmico": "Thermal lag", "Biogás por mês": "Biogas per month", "Biogás": "Biogas",
    "CO₂e evitado (total)": "CO₂e avoided (total)", "Capacidade térmica": "Thermal capacity", "Carga orgânica": "Organic loading rate",
    "Chaminé": "Stack effect", "Células visíveis (escuro) e escondidas (claro)": "Visible cells (dark) and hidden cells (light)",
    "Declividade por célula": "Slope per cell", "Depressões (sem saída)": "Depressions (no outlet)",
    "Deslocamento máximo": "Maximum displacement", "Energia térmica": "Thermal energy", "Faixa (percentis)": "Range (percentiles)",
    "Gerador (P, Q, S, FP)": "Generator (P, Q, S, PF)", "Maior tensão normal": "Largest normal stress", "Máxima": "Maximum",
    "Média": "Mean", "Método": "Method", "Parte visível": "Visible share", "Pela série": "From the series",
    "Perda de solo por célula": "Soil loss per cell", "Pela Weibull ajustada": "From the fitted Weibull",
    "Qualitativo, Fase 1: mostra esteira e aceleração, não números de projeto.": "Qualitative, Phase 1: shows the wake and speed-up, not design numbers.", "Solução clássica": "Classical solution",
    "Temperatura máxima": "Maximum temperature", "Temperatura mínima": "Minimum temperature", "Transmitância": "Thermal transmittance",
    "Vazão": "Flow rate", "Velocidade do ar em unidades de rede; o bloco cinza claro é o obstáculo":
        "Air speed in lattice units; the light grey block is the obstacle",
    "Vento médio no cubo": "Mean wind at hub height", "Verificação": "Check", "Von Mises máxima": "Maximum von Mises",
    "células": "cells", "u (rede)": "u (lattice)", "0 = escondida, 1 = visível": "0 = hidden, 1 = visible",
    "todos os elementos passam": "all elements pass", "há elemento acima do limite ou sem dado ([MARCADOR])":
        "an element is above the limit or has no data ([MARCADOR])",
    "U calculado": "Calculated U", "U da base": "U from the database", "Vento": "Wind", "Combinada": "Combined",
    "Energia do QUBO": "QUBO energy", "Resposta": "Answer", "Entrada inválida:": "Invalid input:",
    # ── método, hipóteses e limites (resultados) ──
    "2D, escoamento quase incompressível (Mach baixo)": "2D, nearly incompressible flow (low Mach)",
    "A faixa só é tão boa quanto as distribuições de entrada. Entradas correlacionadas (ex.: tarifa e inflação) ficam mais largas ou estreitas do que o real.":
        "The range is only as good as the input distributions. Correlated inputs (e.g. tariff and inflation) come out wider or narrower than reality.",
    "ABNT NBR 15220-2 (tabela de resistências superficiais), mesmos valores de sistema/physis-materiais.json (resistencias_superficiais) [CONFERIR NA NORMA]":
        "ABNT NBR 15220-2 (surface resistance table), same values as sistema/physis-materiais.json (resistencias_superficiais) [CONFERIR NA NORMA]",
    "Alumínio de perfil (liga a definir)": "Aluminium section (alloy to be defined)",
    "Atraso e amortecimento valem para regime periódico (vários dias simulados). Terra crua e fibras mudam com a umidade.":
        "Lag and damping hold for a periodic regime (several simulated days). Raw earth and fibres change with moisture.",
    "Aço estrutural de perfil": "Structural steel section",
    "Biogás é inflamável e o H₂S é tóxico e corrosivo: filtro de H₂S (limalha de ferro ou similar), dreno de condensado, válvula de alívio e corta-chamas antes do queimador ou do motor.":
        "Biogas is flammable and H₂S is toxic and corrosive: H₂S filter (iron filings or similar), condensate drain, relief valve and flame arrester before the burner or engine.",
    "Biogás: potencial (ST × SV × BMP) × fração alcançada por cinética de 1ª ordem com k(T) = k_ref·θ^(T−T_ref)":
        "Biogas: potential (TS × VS × BMP) × fraction reached by 1st-order kinetics with k(T) = k_ref·θ^(T−T_ref)",
    "CST é rígido demais em flexão com poucos elementos na altura: refine e compare. Peça impressa é anisotrópica (camadas): E e resistência entre camadas são menores [CONFERIR com ensaio].":
        "CST is too stiff in bending with few elements through the depth: refine and compare. A printed part is anisotropic (layers): E and strength between layers are lower [CONFERIR com ensaio].",
    "Cama de aviário / esterco de aves": "Poultry litter / poultry manure",
    "Caminho de tubo numa grade (QUBO com restrição de grau) — resolvido no clássico": "Pipe route on a grid (QUBO with degree constraint) — solved classically",
    "Condução 1D em regime permanente, camadas homogêneas em série (método da ABNT NBR 15220-2, redação própria)":
        "1D steady-state conduction, homogeneous layers in series (ABNT NBR 15220-2 method, own wording)",
    "D8 concentra o fluxo em linhas; em encosta lisa ele exagera canais. Depressões (−1) param o fluxo: confira no campo se são reais (lagoa, bacia) ou erro do modelo de elevação.":
        "D8 concentrates flow into lines; on a smooth slope it exaggerates channels. Depressions (−1) stop the flow: check in the field whether they are real (pond, basin) or an elevation model error.",
    "Dejeto suíno (chorume)": "Pig slurry",
    "Diferenças finitas 1D (volumes finitos), método θ = 0.5 (Crank-Nicolson)": "1D finite differences (finite volumes), θ = 0.5 method (Crank-Nicolson)",
    "Diferenças finitas 1D (volumes finitos), método θ = 1 (implícito)": "1D finite differences (finite volumes), θ = 1 method (implicit)",
    "Diferenças finitas 2D (volumes finitos), regime permanente por SOR": "2D finite differences (finite volumes), steady state by SOR",
    "Digestato de dejetos ainda pode ter patógenos: aplicar no solo seguindo a orientação agronômica.":
        "Digestate from manure may still carry pathogens: apply to soil following agronomic guidance.",
    "Direção de escoamento D8 (maior queda) e acumulação de fluxo": "D8 flow direction (steepest descent) and flow accumulation",
    "Elementos finitos 2D, estado plano de tensões, triângulo de deformação constante (CST)": "2D finite elements, plane stress, constant strain triangle (CST)",
    "Elementos finitos lineares, pórtico 2D (barra axial + viga de Euler-Bernoulli)": "Linear finite elements, 2D frame (axial bar + Euler-Bernoulli beam)",
    "Elementos finitos lineares, pórtico 3D (barra axial + viga de Euler-Bernoulli)": "Linear finite elements, 3D frame (axial bar + Euler-Bernoulli beam)",
    "Elementos finitos lineares, treliça 2D (barra axial + viga de Euler-Bernoulli)": "Linear finite elements, 2D truss (axial bar + Euler-Bernoulli beam)",
    "Energia da série (Σ P(v)·Δt) e pela Weibull ajustada (método de Justus), contas de vento.py":
        "Energy from the series (Σ P(v)·Δt) and from the fitted Weibull (Justus method), vento.py calculations",
    "Escoamento superficial pelo número de curva (SCS-CN, USDA NRCS) e soma a montante pelo D8": "Surface runoff by curve number (SCS-CN, USDA NRCS) summed upstream by D8",
    "Escolha de posições de placas sob sombra (QUBO) — resolvido no clássico": "Choice of panel positions under shading (QUBO) — solved classically",
    "Esterco bovino (fresco, com urina)": "Cattle manure (fresh, with urine)",
    "Evento isolado, bacias pequenas. Não dá vazão de pico nem hidrograma; para drenagem urbana use o método da norma/prefeitura.":
        "Single event, small catchments. Gives neither peak flow nor hydrograph; for urban drainage use the standard's or the city's method.",
    "Flambagem elástica de Euler: Pcr = π²·E·I/(K·L)²": "Euler elastic buckling: Pcr = π²·E·I/(K·L)²",
    "Grade grossa; desníveis, diâmetro e perda de carga são das abas Água/Turbinas/AVAC (redes existentes).":
        "Coarse grid; heights, diameter and head loss come from the Water/Turbines/HVAC tabs (existing networks).",
    "Heurística de um passo, não é otimização topológica completa (SIMP). Reanalise a peça nova no CST.":
        "One-step heuristic, not full topology optimisation (SIMP). Re-analyse the new part with CST.",
    "Lattice-Boltzmann D2Q9, colisão BGK — QUALITATIVO, Fase 1": "Lattice-Boltzmann D2Q9, BGK collision — QUALITATIVE, Phase 1",
    "Local ventilado, sem chama perto do gasômetro; nunca entrar no digestor sem ventilação e acompanhante.":
        "Ventilated site, no flame near the gas holder; never enter the digester without ventilation and a companion.",
    "Lodo de esgoto": "Sewage sludge",
    "Malha grossa erra perto de cantos e de materiais muito diferentes: refine (dx menor) e compare. Peça impressa: preenchimento (infill) entra como k equivalente da célula [CONFERIR com ensaio].":
        "A coarse mesh errs near corners and very different materials: refine (smaller dx) and compare. Printed part: infill enters as the cell's equivalent k [CONFERIR com ensaio].",
    "Monte Carlo (amostragem aleatória simples, gerador mulberry32 com semente fixa)": "Monte Carlo (simple random sampling, mulberry32 generator with a fixed seed)",
    "Ordem de grandeza para comparar cenários (com e sem cobertura, curva de nível). Não prevê deslizamento: risco de encosta é a aba Resiliência e a Defesa Civil.":
        "Order of magnitude to compare scenarios (with and without cover, contour farming). Does not predict landslides: slope risk is the Resilience tab and Civil Defence.",
    "Ordem de grandeza para pré-dimensionar aberturas. Vento real varia com a direção e o entorno: ΔCp de túnel de vento ou de norma vale mais. Para o Secador, a vazão do coletor depende da insolação.":
        "Order of magnitude for pre-sizing openings. Real wind varies with direction and surroundings: ΔCp from a wind tunnel or a standard is better. For the Dryer, the collector flow depends on sunshine.",
    "Primeira ordem: não pega efeito P-Δ, flambagem local, ligações semirrígidas nem fadiga. Bambu e madeira variam muito por peça: use valores de ensaio. Confira a combinação de ações na norma do material.":
        "First order: does not capture the P-Δ effect, local buckling, semi-rigid joints or fatigue. Bamboo and timber vary a lot piece by piece: use test values. Check the load combination in the material's standard.",
    "Pré-dimensionamento para revisão do engenheiro responsável. Não aprova projeto, não substitui norma nem ensaio. Premissas marcadas 'conferir' precisam ser conferidas antes de uso em proposta.":
        "Pre-sizing for review by the responsible engineer. It does not approve a design and does not replace standards or tests. Assumptions marked 'to be checked' must be checked before use in a proposal.",
    "Pré-dimensionamento. BMP e ST mudam com a dieta dos animais e a idade do resíduo: o ensaio de BMP do substrato real vale mais. Partida, codigestão desequilibrada e inibição não estão no modelo.":
        "Pre-sizing. BMP and TS change with the animals' diet and the age of the waste: a BMP test of the real substrate is better. Start-up, unbalanced co-digestion and inhibition are not in the model.",
    "Qualitativo, Fase 1: mostra onde o ar acelera, separa e forma esteira. Não usar para pressão de projeto, conforto ou dimensionamento. Projeto: OpenFOAM na Fase 2.":
        "Qualitative, Phase 1: shows where air speeds up, separates and forms a wake. Not for design pressure, comfort or sizing. Design: OpenFOAM in Phase 2.",
    "Restos de alimentos": "Food waste", "Resíduos de colheita (palha seca)": "Crop residues (dry straw)",
    "Simulação de biogás (physis_hub.simulacao.biogas), parte usada no lugar do GLP": "Biogas simulation (physis_hub.simulacao.biogas), share used instead of LPG",
    "Sombra mútua entra só aos pares; a geração de cada posição vem do estudo solar (aba Energia solar).":
        "Mutual shading only enters in pairs; each position's generation comes from the solar study (Solar energy tab).",
    "Série curta (menos de 1 ano) não representa o ano. Meça no local, na altura do cubo.": "A short series (under 1 year) does not represent the year. Measure on site, at hub height.",
    "Só barras esbeltas (flambagem elástica); barras curtas falham por esmagamento antes. Imperfeições reduzem a carga real: a norma do material dá a curva de projeto.":
        "Slender bars only (elastic buckling); short bars fail by crushing first. Imperfections reduce the real load: the material's standard gives the design curve.",
    "Só relevo; vegetação e construções mudam tudo. Distâncias de poucos km.": "Terrain only; vegetation and buildings change everything. Distances of a few km.",
    "Taipa de pilão (terra compactada)": "Rammed earth (compacted soil)",
    "Topologia grossa de peça 2D (QUBO heurístico sobre a energia de deformação) — resolvido no clássico":
        "Coarse topology of a 2D part (heuristic QUBO on strain energy) — solved classically",
    "Triagem. O dimensionamento final segue a norma do material (aço, madeira, bambu, alumínio).": "Screening. Final sizing follows the material's standard (steel, timber, bamboo, aluminium).",
    "Trilha de pesquisa: solução quântica (QAOA/QUBO) é P&D, cabe ~20–30 variáveis em simulador e precisa reproduzir o ótimo clássico. Nunca usar em relatório nem certificação.":
        "Research track: the quantum solution (QAOA/QUBO) is R&D, fits ~20–30 variables in a simulator and must reproduce the classical optimum. Never use it in a report or certification.",
    "USDA NRCS, TR-55 (1986), tabelas de número de curva para condição de umidade média [CONFERIR]": "USDA NRCS, TR-55 (1986), curve number tables for average moisture condition [CONFERIR]",
    "USDA NRCS, método do número de curva [CONFERIR]": "USDA NRCS, curve number method [CONFERIR]",
    "USLE: A = R·K·LS·C·P (Wischmeier & Smith), LS pela declividade e comprimento de rampa": "USLE: A = R·K·LS·C·P (Wischmeier & Smith), LS from slope and slope length",
    "Ventilação natural: efeito chaminé e vento por orifício (coeficientes de premissa)": "Natural ventilation: stack effect and wind through an orifice (assumed coefficients)",
    "Verificação por tensões admissíveis (σ ≤ fy/FS) e flambagem de Euler (|N| ≤ Pcr/FS)": "Check by allowable stresses (σ ≤ fy/FS) and Euler buckling (|N| ≤ Pcr/FS)",
    "Visada simples (linha de visada sobre a grade, sem curvatura da Terra)": "Simple viewshed (line of sight over the grid, no Earth curvature)",
    "Válido para camadas contínuas; pontes térmicas (montantes, pilares, juntas) pedem a placa_2d. Umidade muda a condutividade da terra e das fibras.":
        "Valid for continuous layers; thermal bridges (studs, columns, joints) need placa_2d. Moisture changes the conductivity of earth and fibres.",
    "[MARCADOR] carbono incorporado de alguma camada: total por m² não calculado": "[MARCADOR] embodied carbon of some layer: total per m² not calculated",
    "alimentação diária constante": "constant daily feeding",
    "aço: valores usuais de aço estrutural (fy do aço ASTM A36 / MR250) [CONFERIR NA NORMA ABNT NBR 8800]; alumínio: E usual, fy depende da liga e da têmpera [MARCADOR]; madeira: classe de resistência da ABNT NBR 7190 ou ensaio [MARCADOR]; bambu: ensaio (ISO 22156 / ABNT NBR 16828) [MARCADOR]; filamentos: ensaio da oficina [MARCADOR]. Densidades de sistema/physis-materiais.json e de physis-3d-premissas.json.":
        "steel: usual structural steel values (fy of ASTM A36 / MR250 steel) [CONFERIR NA NORMA ABNT NBR 8800]; aluminium: usual E, fy depends on alloy and temper [MARCADOR]; timber: ABNT NBR 7190 strength class or test [MARCADOR]; bamboo: test (ISO 22156 / ABNT NBR 16828) [MARCADOR]; filaments: workshop test [MARCADOR]. Densities from sistema/physis-materiais.json and physis-3d-premissas.json.",
    "camadas homogêneas, sem pontes térmicas": "homogeneous layers, no thermal bridges", "cargas características (sem majorar)": "characteristic loads (unfactored)",
    "chaminé e vento somados em quadratura (aproximação)": "stack and wind added in quadrature (approximation)", "chuva uniforme no evento": "uniform rainfall during the event",
    "comprimento de flambagem = comprimento do elemento × K": "buckling length = element length × K",
    "condição de umidade antecedente média (II)": "average antecedent moisture condition (II)", "condução 2D, propriedades constantes por célula": "2D conduction, constant properties per cell",
    "contato perfeito entre camadas": "perfect contact between layers", "contato perfeito entre células": "perfect contact between cells",
    "curva de potência ideal ou do fabricante": "ideal or manufacturer's power curve", "densidade da carga 1000 kg/m³": "feedstock density 1000 kg/m³",
    "depressões não são preenchidas": "depressions are not filled", "distribuições escolhidas pela pessoa ou premissa": "distributions chosen by the user or by assumption",
    "entradas independentes (sem correlação)": "independent inputs (no correlation)", "erosão laminar e em sulcos (não voçoroca)": "sheet and rill erosion (not gullies)",
    "escoamento por orifício, ar incompressível": "orifice flow, incompressible air", "estudo do lugar": "site study",
    "exato (enumeração em código de Gray)": "exact (Gray code enumeration)", "faixas clássicas de digestão anaeróbia [CONFERIR]": "classical anaerobic digestion ranges [CONFERIR]",
    "faixas típicas de tabelas de substratos para biogás (FNR, Leitfaden Biogas; KTBL) e literatura de digestão anaeróbia [CONFERIR]; N-P-K de tabelas de adubação com dejetos [CONFERIR]":
        "typical ranges from biogas substrate tables (FNR, Leitfaden Biogas; KTBL) and anaerobic digestion literature [CONFERIR]; N-P-K from manure fertilisation tables [CONFERIR]",
    "faixas usuais de literatura [CONFERIR]": "usual literature ranges [CONFERIR]",
    "faixas usuais de literatura para digestores rurais e de mistura completa [CONFERIR]": "usual literature ranges for rural and completely mixed digesters [CONFERIR]",
    "fluxo perpendicular à parede": "heat flow perpendicular to the wall", "lei de potência para a altura do cubo": "power law to hub height",
    "ligações ideais (rótula ou engaste)": "ideal joints (pinned or fixed)", "material elástico linear": "linear elastic material",
    "material elástico linear e isótropo": "linear elastic, isotropic material", "modelo de reator: mistura": "reactor model: completely mixed",
    "modelo de reator: pistonado": "reactor model: plug flow", "ordem de grandeza [CONFERIR com o fabricante]": "order of magnitude [CONFERIR com o fabricante]",
    "ordem de grandeza de literatura de digestão anaeróbia de dejetos (correção de temperatura na forma θ, tipo Arrhenius) [CONFERIR]":
        "order of magnitude from manure anaerobic digestion literature (θ-form, Arrhenius-type temperature correction) [CONFERIR]",
    "ordem de grandeza de literatura e de metodologias de crédito [CONFERIR]": "order of magnitude from literature and credit methodologies [CONFERIR]",
    "ordem de grandeza de literatura para prédio baixo isolado [CONFERIR]; túnel de vento ou norma valem mais":
        "order of magnitude from literature for a low isolated building [CONFERIR]; a wind tunnel or a standard is better",
    "ordem de grandeza de motogeradores pequenos [CONFERIR com o fabricante]": "order of magnitude for small gensets [CONFERIR com o fabricante]",
    "penalidade grande o bastante para não violar": "penalty large enough not to be violated", "pequenas deformações": "small strains", "perda média anual": "mean annual loss",
    "premissa Physis (mesmo valor do Planejador, physisBiogas, e da aba Carbono); conferir com o teor de metano medido":
        "Physis assumption (same value as the Planner, physisBiogas, and the Carbon tab); check against the measured methane content",
    "premissa Physis (reprodutível: mesma semente, mesmo resultado no servidor e no navegador)": "Physis assumption (reproducible: same seed, same result on the server and in the browser)",
    "premissa Physis (valor da aba Carbono); conferir com a ficha do combustível": "Physis assumption (Carbon tab value); check against the fuel data sheet",
    "premissa Physis para estimativa, igual à referência regulatória abaixo [CONFERIR]; vale a medição (V6, medidor) quando houver":
        "Physis assumption for estimates, equal to the regulatory reference below [CONFERIR]; measurement (V6, meter) prevails when available",
    "premissa Physis provisória [CONFERIR NA NORMA]": "provisional Physis assumption [CONFERIR NA NORMA]",
    "premissa Physis provisória para triagem por tensões admissíveis; o dimensionamento segue os coeficientes da norma do material [CONFERIR NA NORMA]":
        "provisional Physis assumption for allowable-stress screening; sizing follows the material standard's factors [CONFERIR NA NORMA]",
    "profundidade unitária (1 m)": "unit depth (1 m)", "propriedades da base de materiais": "properties from the materials database",
    "regime elástico": "elastic range", "restrições como penalidade quadrática": "constraints as a quadratic penalty",
    "sem cisalhamento na flexão (Euler-Bernoulli)": "no shear deformation in bending (Euler-Bernoulli)", "sem infiltração ao longo do caminho": "no infiltration along the path",
    "sem inibição (amônia, H₂S, óleo)": "no inhibition (ammonia, H₂S, oil)", "sem turbulência modelada": "no turbulence model",
    "sem umidade nem mudança de fase": "no moisture or phase change", "seções planas permanecem planas": "plane sections remain plane",
    "série representativa do período": "series representative of the period",
    "temperatura do digestor = do regime ou a média mensal do local (+ ganho de enterrar)": "digester temperature = the regime's or the site's monthly mean (+ gain from burying)",
    "terreno nu (sem árvores nem prédios)": "bare terrain (no trees or buildings)", "unidades de rede (sem escala física direta)": "lattice units (no direct physical scale)",
    "valor usual de orifício de borda viva na literatura de ventilação natural [CONFERIR]": "usual sharp-edged orifice value in natural ventilation literature [CONFERIR]",
    "valores teóricos da flambagem de Euler (livros de resistência dos materiais); as normas recomendam valores um pouco maiores para projeto [CONFERIR NA NORMA]":
        "theoretical Euler buckling values (strength of materials textbooks); standards recommend slightly larger values for design [CONFERIR NA NORMA]",
    "vizinho mais próximo ao longo do raio": "nearest neighbour along the ray", "água segue o vizinho mais baixo (um só caminho)": "water follows the lowest neighbour (a single path)",
    # ── Physis 3D (Método): rótulo em <strong> e corpo são nós de texto separados ──
    "Leitura:": "Reading:", "Medidas:": "Measurements:", "Fatiamento da tela:": "On-screen slicing:",
    "Materiais reciclados:": "Recycled materials:", "Avisos aprendidos:": "Learned warnings:", "Licenças:": "Licences:", "Fase 2:": "Phase 2:",
    "STL (texto e binário), OBJ e 3MF lidos por código próprio; o 3MF é um ZIP, aberto com um descompactador escrito aqui. O arquivo original fica guardado como veio.":
        "STL (text and binary), OBJ and 3MF read by our own code; 3MF is a ZIP, opened with an unzipper written here. The original file is kept as it came.",
    "volume pela soma dos tetraedros de cada triângulo com a origem; área pela soma dos triângulos; balanço = faces viradas para baixo mais deitadas que o limite (45° da vertical, padrão), fora da mesa; conferência de arestas (cada aresta tem de ter exatamente duas faces, em sentidos opostos).":
        "volume as the sum of the tetrahedra formed by each triangle and the origin; area as the sum of the triangles; overhang = downward faces lying flatter than the limit (45° from vertical, default), off the bed; edge check (each edge must have exactly two faces, in opposite directions).",
    "planos no meio de cada camada; cada triângulo cortado dá um segmento orientado pela face, e a área sai pela fórmula de Gauss sem montar os contornos. Estimativa de pré-projeto; o G-code de verdade vem do fatiador aberto do servidor (PrusaSlicer, AGPL-3.0, num contêiner separado).":
        "planes through the middle of each layer; each cut triangle gives a segment oriented by its face, and the area comes from Gauss's formula without building the outlines. A pre-design estimate; the real G-code comes from the server's open slicer (PrusaSlicer, AGPL-3.0, in a separate container).",
    "densidade, temperaturas e contração são premissas \"conferir\" (valores típicos do polímero virgem). Troque pelos do fornecedor ou pelo ensaio da oficina.":
        "density, temperatures and shrinkage are \"to be checked\" assumptions (typical virgin polymer values). Replace them with the supplier's values or the workshop test.",
    "classificador de Bayes ingênuo, treinado nas revisões com resultado (material, camada, balanço, parede, tamanho e temperatura do bico). Com poucos dados, a tela diz que são poucos.":
        "naive Bayes classifier trained on reviews with an outcome (material, layer, overhang, wall, size and nozzle temperature). With little data, the screen says so.",
    "este código é da Physis, aberto; o visualizador é WebGL escrito à mão (sem biblioteca de terceiros). Cada peça publicada leva a licença aberta escolhida pelo autor (CC BY 4.0, CC BY-SA 4.0, CC0 1.0, CERN-OHL-S/W/P 2.0). Formatos: 3MF (especificação aberta do 3MF Consortium) e STL.":
        "this code is Physis's own, open; the viewer is hand-written WebGL (no third-party library). Each published part carries the open licence chosen by its author (CC BY 4.0, CC BY-SA 4.0, CC0 1.0, CERN-OHL-S/W/P 2.0). Formats: 3MF (open specification by the 3MF Consortium) and STL.",
    "simulações (escoamento, calor, pressão, compressão, impacto, tração, flambagem) com resolvedores clássicos abertos como referência (CalculiX, FEniCS, OpenFOAM) e a trilha de programação quântica (Qiskit, PennyLane), que só entra no Planejador depois de validada contra os clássicos. Veja physis-hub/docs/PHYSIS_3D.md.":
        "simulations (flow, heat, pressure, compression, impact, tension, buckling) with classical open solvers as a reference (CalculiX, FEniCS, OpenFOAM) and the quantum programming track (Qiskit, PennyLane), which only enters the Planner after validation against the classical ones. See physis-hub/docs/PHYSIS_3D.md.",
    # ── Physis 3D (Fatiar): fonte e nota dos perfis de material (physis-3d-premissas.json) ──
    "[CONFERIR] valores típicos de literatura e de fabricantes para ABS virgem (densidade 1,03 a 1,06 g/cm³). Trocar pela folha de dados do filamento reciclado usado.":
        "[CONFERIR] typical literature and manufacturer values for virgin ABS (density 1.03 to 1.06 g/cm³). Replace with the data sheet of the recycled filament used.",
    "[CONFERIR] valores típicos de literatura e de fabricantes para PETG virgem; PET de garrafa tem densidade maior (cerca de 1,33 a 1,38 g/cm³). Trocar pela folha de dados do filamento reciclado usado.":
        "[CONFERIR] typical literature and manufacturer values for virgin PETG; bottle PET has a higher density (about 1.33 to 1.38 g/cm³). Replace with the data sheet of the recycled filament used.",
    "[CONFERIR] valores típicos de literatura e de fabricantes para PLA virgem (densidade 1,21 a 1,25 g/cm³). PLA reciclado perde massa molar a cada ciclo: a faixa de bico costuma cair. Trocar pela folha de dados do filamento reciclado usado.":
        "[CONFERIR] typical literature and manufacturer values for virgin PLA (density 1.21 to 1.25 g/cm³). Recycled PLA loses molar mass with each cycle: the nozzle range tends to drop. Replace with the data sheet of the recycled filament used.",
    "[CONFERIR] valores típicos de literatura para PEAD virgem (densidade 0,94 a 0,97 g/cm³; contração de moldagem de 1,5 a 4 %). Poucos dados publicados para impressão FDM. Trocar pelo ensaio da oficina.":
        "[CONFERIR] typical literature values for virgin HDPE (density 0.94 to 0.97 g/cm³; moulding shrinkage 1.5 to 4 %). Little published data for FDM printing. Replace with the workshop test.",
    "[CONFERIR] valores típicos de literatura para PP virgem (densidade 0,89 a 0,91 g/cm³; contração de moldagem de 1 a 2,5 %). Trocar pela folha de dados do filamento reciclado usado.":
        "[CONFERIR] typical literature values for virgin PP (density 0.89 to 0.91 g/cm³; moulding shrinkage 1 to 2.5 %). Replace with the data sheet of the recycled filament used.",
    "Mais fácil de imprimir; PLA não é reciclável junto com PET na coleta comum.": "Easiest to print; PLA cannot be recycled together with PET in ordinary collection.",
    "O mais difícil dos cinco: empenamento forte. Peças pequenas, borda (brim) larga e mesa de PP/PE.": "The hardest of the five: strong warping. Small parts, a wide brim and a PP/PE bed.",
    "PP adere mal à maioria das mesas e empena muito: mesa com fita de PP ou adesivo próprio; câmara fechada ajuda.": "PP sticks poorly to most beds and warps a lot: a bed with PP tape or its own adhesive; an enclosed chamber helps.",
    "Reciclado de garrafa (PET) seca mal e cristaliza; secar antes de imprimir. Contração é de ordem de grandeza: medir no cubo de calibração.": "Bottle-recycled PET dries poorly and crystallises; dry it before printing. Shrinkage is an order of magnitude: measure it on the calibration cube.",
    "Solta vapores (estireno): imprimir com ventilação ou exaustão. Câmara fechada reduz a separação de camadas.": "Releases fumes (styrene): print with ventilation or extraction. An enclosed chamber reduces layer separation.",
}

# expressões regulares (texto inteiro): [padrão, troca]; $1… são traduzidos de novo quando der
MOTOR_EN_RX = [
    [r"^(\d+) giros sem rigidez \(nós só de barras\) foram travados automaticamente$",
     "$1 rotations without stiffness (bar-only nodes) were locked automatically"],
    [r"^Sobrecarga: carga orgânica ([\d.,]+) kg SV/m³·dia acima do limite ([\d.,]+) do regime \(premissa sim\.biogas\.cov_max\): risco de acidificação; aumente o volume ou reduza a carga\.$",
     "Overload: organic loading rate $1 kg VS/m³·day above the regime's limit of $2 (assumption sim.biogas.cov_max): risk of acidification; increase the volume or reduce the load."],
    [r"^TRH curto: ([\d.,]+) dias, abaixo de ([\d.,]+) dias para o regime \(lavagem das bactérias\)\.$",
     "Short HRT: $1 days, below $2 days for the regime (bacteria wash-out)."],
    [r"^\[MARCADOR\] N-P-K de: (.+) \(análise do digestato\)$", "[MARCADOR] N-P-K of: $1 (digestate analysis)"],
    [r"^\[MARCADOR\] densidade ou calor específico de: (.+) \(capacidade térmica incompleta\)$",
     "[MARCADOR] density or specific heat of: $1 (thermal capacity incomplete)"],
    [r"^Material: (.+?) — bico (.+?), mesa (.+?), densidade (.+?), contração (.+?)\.$",
     "Material: $1 — nozzle $2, bed $3, density $4, shrinkage $5."],
    [r"^(.*) \(escala logarítmica\) (.*)$", "$1 (log scale) $2"],
    [r"^\(escala logarítmica\) (.*)$", "(log scale) $1"],   # legenda: os números ficam em nós à parte
    [r"^(\d+) °C \((\d+) a (\d+)\)$", "$1 °C ($2 to $3)"],
]

# casos da simulação: id -> [nome, descrição]
CASOS_EN = {
    "ex_parede_taipa_u": ["Rammed-earth wall 30 cm: thermal transmittance (U)", "Example / fictitious data. 30 cm rammed earth, properties from the materials database (Bio-construction)."],
    "ex_parede_taipa_transiente": ["Rammed-earth wall 30 cm: thermal lag (10 sunny days)", "Example / fictitious data. Sinusoidal outdoor temperature 25 ± 8 °C, indoor 25 °C; implicit, 1 cm cells."],
    "bench_decaimento_1d": ["1D decay against the analytical solution", ""],
    "bench_placa_quadrada": ["Square 2D plate at steady state", ""],
    "ex_ponte_termica": ["Thermal bridge: concrete column in a rammed-earth wall", "Example / fictitious data. 60 cm horizontal section of wall (rammed earth k 1.1) with a concrete column (k 1.75); 35 °C outside, 24 °C inside."],
    "bench_u_camadas": ["U of typed layers", ""],
    "ex_rack_solar": ["Solar panel rack (steel truss and beam)", "Example / fictitious data. Two panels (22 kg each), wind by the dynamic pressure method with FICTITIOUS V0, S1, S2, S3 and Cf (the design values come from the standard)."],
    "bench_viga_balanco": ["Cantilever beam: deflection PL³/3EI", ""],
    "bench_viga_balanco_3d": ["3D cantilever beam (tube)", ""],
    "bench_trelica": ["Triangular truss: node equilibrium", ""],
    "bench_euler": ["Euler critical load (fixed-free)", ""],
    "bench_cst_patch": ["CST patch test under uniform tension", ""],
    "ex_suporte_3d": ["Printed bracket (Physis 3D): stresses in the section", "Example / fictitious data. 60 × 40 mm section, 10 mm thick, 200 N at the tip; fictitious E and ν (the real ones come from the workshop test)."],
    "ex_torre_turbina": ["12 m wind turbine tower (cantilever)", "Example / fictitious data. 3 m rotor with actuator-disc thrust at 12 m/s and tower drag at 20 m/s (fictitious speeds), plus self-weight."],
    "ex_ventilacao_secador": ["Natural ventilation of the Dryer chamber", "Example / fictitious data. Two 5 × 10 cm openings, 1.2 m height between them, 45 °C inside and 25 °C outside, 1.5 m/s wind."],
    "ex_lbm": ["Wind around a house section (LBM D2Q9, qualitative)", "Example / fictitious data. 48 × 20 cell channel with a block (the house) on the ground; shows the speed-up over the roof and the wake. Only the browser draws it (Python checks the smaller case)."],
    "bench_lbm_canal": ["LBM in a small channel (Python × browser parity)", ""],
    "bench_lbm_conservacao": ["LBM in a periodic box: mass conserved", ""],
    "ex_eolica_serie": ["Small wind turbine with a wind series", "Example / fictitious data. Fictitious 4-day hourly series; vento.py / physis-turbinas.js calculations."],
    "ex_terreno_d8": ["Water path in a small valley (D8)", "Example / fictitious data. 16 × 12 grid of 10 m cells, valley sloping south."],
    "ex_terreno_scs": ["Runoff from 80 mm of rain (SCS-CN)", "Example / fictitious data. Forest on the edges and pasture on the valley floor, soil group C (fictitious)."],
    "ex_terreno_usle": ["Soil loss (USLE) in the valley", "Example / fictitious data. Fictitious R, K, C and P (the real ones come from the site study)."],
    "ex_terreno_visada": ["What can be seen from the top of the valley", "Example / fictitious data. 1.6 m observer at the top."],
    "bench_d8_plano": ["D8 on a plane sloping east", ""],
    "bench_scs": ["SCS-CN: CN 80 and 100 mm of rain", ""],
    "ex_monte_carlo_solar": ["Range of 5 kWp solar generation (Monte Carlo)", "Example / fictitious data. Irradiation 5.2 ± 0.4 kWh/m²·day and PR between 0.70 and 0.82 (fictitious)."],
    "bench_mc_media": ["Monte Carlo: mean of a uniform distribution", ""],
    "ex_qubo_paineis": ["QUBO: 2 panels in 5 positions with shading", "Example / fictitious data. Positions 0 and 1 shade each other (6 kWh), 2 and 3 a little (1 kWh). Fictitious gains."],
    "bench_qubo_rota": ["QUBO: pipe route on a 3 × 2 grid", ""],
    "bench_qubo_topologia": ["QUBO: coarse 4 × 3 topology", ""],
    "bench_fatores_carbono": ["Carbon factors used in biogas (same calculation as carbono.py)", ""],
    "bench_biogas_manual": ["Biogas checked by hand: 100 kg/day of food waste", ""],
    "bench_biogas_trh_longo": ["Biogas: very long HRT reaches the BMP", ""],
    "ex_biogas_bovino": ["Tubular digester with manure from 20 cows", "Example / fictitious data. 500 kg/day of manure (20 cows), 15 m³ working volume, mesophilic; 60 % of the biogas on the stove (instead of LPG), 40 % in the generator 8 h/day."],
    "ex_biogas_ambiente": ["Unheated digester: production month by month", "Example / fictitious data. FICTITIOUS monthly temperature (in real use it comes from the installation site, NASA POWER); pigs and kitchen waste."],
}
