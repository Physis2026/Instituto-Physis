import { useState, useEffect } from "react";

// ── Physis brand tokens ────────────────────────────────────────
const G = {
  deep:   "#074031",
  mid:    "#51774B",
  sage:   "#81A969",
  pale:   "#EEF8EB",
  white:  "#FFFFFF",
  ink:    "#1C2B22",
  gray:   "#F4F7F4",
  border: "#D4E8D0",
  muted:  "#6B7F6E",
  warn:   "#F59E0B",
};

// ── HPS data por cidade ────────────────────────────────────────
const CIDADES = {
  "Petrópolis — RJ":    { hps: 4.2, hps_min: 3.42, zona: 3, pais: "Brasil" },
  "Rio de Janeiro — RJ":{ hps: 4.65,hps_min: 3.71, zona: 4, pais: "Brasil" },
  "São Paulo — SP":     { hps: 4.4, hps_min: 3.52, zona: 3, pais: "Brasil" },
  "Brasília — DF":      { hps: 5.47,hps_min: 4.12, zona: 4, pais: "Brasil" },
  "Belo Horizonte — MG":{ hps: 4.9, hps_min: 3.85, zona: 3, pais: "Brasil" },
  "Salvador — BA":      { hps: 5.2, hps_min: 4.20, zona: 7, pais: "Brasil" },
  "João Pessoa — PB":   { hps: 5.8, hps_min: 4.92, zona: 8, pais: "Brasil" },
  "Manaus — AM":        { hps: 4.89,hps_min: 4.21, zona: 8, pais: "Brasil" },
  "Curitiba — PR":      { hps: 3.9, hps_min: 2.98, zona: 1, pais: "Brasil" },
  "Tunis — Tunísia":    { hps: 5.02,hps_min: 2.87, zona: 0, pais: "Tunísia" },
  "Amsterdã — Holanda": { hps: 2.68,hps_min: 0.81, zona: 0, pais: "Holanda" },
};

// ── Materiais por zona ─────────────────────────────────────────
const MATERIAIS = {
  1: { estrutura:"CLT + SIP 150mm", vedacao:"SIP + BTC", isolamento:"Lã de rocha 75mm", cobertura:"Sanduíche 80mm + telhado verde", esquadria:"Vidro triplo (U < 0,8)", label:"Frio", cor:"#DBEAFE" },
  2: { estrutura:"CLT + SIP 100mm", vedacao:"SIP + BTC", isolamento:"Lã de rocha 50mm", cobertura:"Sanduíche 50mm + telhado verde", esquadria:"Vidro duplo câmara argônio", label:"Muito frio", cor:"#DBEAFE" },
  3: { estrutura:"CLT + SIP 100mm", vedacao:"SIP + BTC / Hempcrete", isolamento:"Lã PET 50mm", cobertura:"Sanduíche 50mm + telhado verde", esquadria:"Vidro duplo câmara ar", label:"Temperado", cor:"#EDE7F6" },
  4: { estrutura:"CLT ou SIP", vedacao:"SIP ou BTC", isolamento:"Lã PET 50mm cobertura", cobertura:"Telhado verde ou sanduíche", esquadria:"Vidro duplo Low-E", label:"Subquente", cor:"#E8F5E9" },
  5: { estrutura:"CLT ou concreto cinza volante", vedacao:"BTC + inércia alta", isolamento:"Lã rocha 75mm cobertura", cobertura:"Sanduíche + câmara de ar", esquadria:"Vidro duplo Low-E", label:"Quente seco sazonal", cor:"#FFF9C4" },
  6: { estrutura:"Bambu + aço reciclado", vedacao:"Adobe ou BTC", isolamento:"Lã rocha cobertura", cobertura:"Argila + cal refletiva", esquadria:"Vidro duplo + shutters", label:"Quente seco", cor:"#FFE0B2" },
  7: { estrutura:"Bambu + aço reciclado", vedacao:"Adobe branco + pedra", isolamento:"Cobertura apenas", cobertura:"Argila + cal refletiva", esquadria:"Vidro duplo + shutters", label:"Quente e seco", cor:"#FFE0B2" },
  8: { estrutura:"Bambu Guadua + madeira FSC", vedacao:"Paredes abertas + venezianas", isolamento:"Cobertura apenas (mínimo)", cobertura:"Palha / sedum / policarbonato", esquadria:"Venezianas + tela mosquiteiro", label:"Quente e úmido", cor:"#FCE4EC" },
  0: { estrutura:"CLT + SIP (verificar norma local)", vedacao:"Depende do clima local", isolamento:"Verificar dados PVGIS locais", cobertura:"Verificar dados PVGIS locais", esquadria:"Vidro duplo ou triplo", label:"Internacional", cor:"#F3E5F5" },
};

// ── Certificações demo ────────────────────────────────────────
const CERTS = [
  { id:"edge",  nome:"EDGE (IFC/Banco Mundial)", cor:"#2196F3",
    criterios:[
      { req:"Redução ≥20% no consumo de energia vs. linha de base",       campo:"energia" },
      { req:"Redução ≥20% no consumo de água vs. linha de base",           campo:"agua"   },
      { req:"Redução ≥20% no carbono incorporado dos materiais",           campo:"carbon" },
      { req:"Documentação EPD dos materiais principais",                   campo:"epd"    },
      { req:"Registro do projeto na plataforma edgebuildings.com",         campo:"reg"    },
    ]
  },
  { id:"casaazul", nome:"Selo Casa Azul — Caixa",  cor:"#1565C0",
    criterios:[
      { req:"Eficiência energética RTQ-R Nível A",                         campo:"rtq"    },
      { req:"Sistema de captação de água pluvial (NBR 15527)",             campo:"chuva"  },
      { req:"Coleta seletiva e compostagem no empreendimento",             campo:"res"    },
      { req:"Ventilação e iluminação natural adequadas (NBR 15575)",       campo:"vent"   },
      { req:"Manual do proprietário / hóspede entregue",                  campo:"man"    },
    ]
  },
  { id:"greenkey", nome:"GreenKey — Hospitalidade", cor:"#2E7D32",
    criterios:[
      { req:"Política ambiental documentada e comunicada",                  campo:"pol"   },
      { req:"Medição e redução de consumo de energia",                      campo:"emed"  },
      { req:"Consumo 100% de água de fontes sustentáveis",                  campo:"ague"  },
      { req:"Separação de resíduos + compostagem",                          campo:"resg"  },
      { req:"Produtos locais e orgânicos para hóspedes",                    campo:"food"  },
    ]
  },
];

// ── Acabamentos ───────────────────────────────────────────────
const ACABAMENTOS = {
  tadelakt:  { nome:"Tadelakt (cal marroquina)", matM2:115, base:42,  ferramentas:680, moM2:280 },
  cal:       { nome:"Reboco de Cal + Fibra",     matM2:62,  base:0,   ferramentas:180, moM2:50  },
  argila:    { nome:"Tinta Natural Argila",       matM2:48,  base:0,   ferramentas:80,  moM2:20  },
  stucco:    { nome:"Stucco Veneziano",           matM2:220, base:0,   ferramentas:220, moM2:320 },
  bambu:     { nome:"Piso Bambu Laminado",        matM2:160, base:18,  ferramentas:120, moM2:45  },
};

// ═══════════════════════════════════════════════════════════════
// Componentes auxiliares
// ═══════════════════════════════════════════════════════════════
function Badge({ children, color = G.mid }) {
  return (
    <span style={{
      background: color + "18", color, border: `1px solid ${color}33`,
      borderRadius: 4, padding: "2px 10px", fontSize: 11,
      fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase",
      whiteSpace: "nowrap"
    }}>{children}</span>
  );
}

function Card({ children, style = {}, bg = G.white }) {
  return (
    <div style={{
      background: bg, border: `1px solid ${G.border}`,
      borderRadius: 12, padding: "20px 22px",
      boxShadow: "0 2px 12px rgba(7,64,49,0.06)", ...style
    }}>{children}</div>
  );
}

function InputRow({ label, value, onChange, unit, min, max, step = 1, note }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: G.ink, marginBottom: 4 }}>{label}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="number" value={value} min={min} max={max} step={step}
          onChange={e => onChange(+e.target.value)}
          style={{
            flex: 1, padding: "8px 12px", border: `2px solid #BFDBFE`,
            borderRadius: 8, fontSize: 15, fontWeight: 700, color: "#1E40AF",
            background: "#EFF6FF", fontFamily: "inherit", outline: "none"
          }} />
        {unit && <span style={{ fontSize: 12, color: G.muted, minWidth: 40 }}>{unit}</span>}
      </div>
      {note && <div style={{ fontSize: 11, color: G.muted, marginTop: 3, fontStyle: "italic" }}>{note}</div>}
    </div>
  );
}

function ResultRow({ label, value, unit, highlight }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "10px 14px", background: highlight ? G.pale : G.gray,
      borderRadius: 8, marginBottom: 6,
      border: highlight ? `1px solid ${G.sage}` : "none"
    }}>
      <span style={{ fontSize: 13, color: G.ink }}>{label}</span>
      <span style={{ fontSize: 15, fontWeight: 800, color: highlight ? G.deep : G.ink }}>
        {value} <span style={{ fontSize: 11, fontWeight: 400, color: G.muted }}>{unit}</span>
      </span>
    </div>
  );
}

function LockedBadge() {
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      background: "#FFF3E0", border: "1px solid #FFB74D",
      borderRadius: 6, padding: "3px 10px", fontSize: 11,
      color: "#E65100", fontWeight: 600
    }}>🔒 Versão completa</div>
  );
}

function TabBtn({ label, active, onClick, icon }) {
  return (
    <button onClick={onClick} style={{
      padding: "10px 18px", borderRadius: 8, border: "none", cursor: "pointer",
      background: active ? G.deep : "transparent",
      color: active ? G.white : G.muted,
      fontWeight: active ? 700 : 500, fontSize: 13,
      transition: "all 0.2s", fontFamily: "inherit",
      display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap"
    }}>
      <span>{icon}</span> {label}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab 1 — Calculadora Solar
// ═══════════════════════════════════════════════════════════════
function TabSolar() {
  const [consumo, setConsumo] = useState(22);
  const [cidade, setCidade] = useState("Petrópolis — RJ");
  const [potInst, setPotInst] = useState(10);
  const [modo, setModo] = useState("media"); // media | pior

  const c = CIDADES[cidade];
  const hps = modo === "pior" ? c.hps_min : c.hps;
  const pr = 0.78;
  const potMin = +(consumo / (hps * pr)).toFixed(1);
  const geracao = Math.round(potInst * hps * 365 * pr);
  const consumoAnual = consumo * 365;
  const saldo = geracao - consumoAnual;
  const nzeb = saldo >= 0;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      {/* Inputs */}
      <Card>
        <div style={{ fontWeight: 700, color: G.deep, marginBottom: 16, fontSize: 14 }}>
          ☀️ Dados do projeto
        </div>

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: G.ink, marginBottom: 4 }}>Cidade / Localização</div>
          <select value={cidade} onChange={e => setCidade(e.target.value)} style={{
            width: "100%", padding: "8px 12px", borderRadius: 8,
            border: `2px solid #BFDBFE`, background: "#EFF6FF",
            fontSize: 13, color: "#1E40AF", fontWeight: 600, fontFamily: "inherit"
          }}>
            {Object.keys(CIDADES).map(c => <option key={c}>{c}</option>)}
          </select>
        </div>

        <InputRow label="Consumo diário estimado" value={consumo}
          onChange={setConsumo} unit="kWh/dia" min={1} max={200} step={0.5}
          note="Somar todos os equipamentos da edificação" />

        <InputRow label="Potência instalada adotada" value={potInst}
          onChange={setPotInst} unit="kWp" min={1} max={500} step={0.5}
          note="Ajuste para ver o impacto na geração" />

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: G.ink, marginBottom: 6 }}>Método de HPS</div>
          <div style={{ display: "flex", gap: 8 }}>
            {[["media","Média anual"],["pior","Pior mês (conservador)"]].map(([v,l]) => (
              <button key={v} onClick={() => setModo(v)} style={{
                flex: 1, padding: "7px", borderRadius: 7, border: `1px solid ${modo===v ? G.deep : G.border}`,
                background: modo===v ? G.pale : G.white,
                color: modo===v ? G.deep : G.muted,
                fontWeight: modo===v ? 700 : 400, fontSize: 11, cursor: "pointer", fontFamily: "inherit"
              }}>{l}</button>
            ))}
          </div>
          <div style={{ fontSize: 10, color: G.muted, marginTop: 4, fontStyle: "italic" }}>
            {modo === "pior" ? "✅ Recomendado — garante autonomia o ano todo (metodologia PVGIS)" : "⚠️ Média pode subestimar nos meses de menor sol"}
          </div>
        </div>
      </Card>

      {/* Resultados */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Card bg={G.pale}>
          <div style={{ fontWeight: 700, color: G.deep, marginBottom: 12, fontSize: 14 }}>
            📊 Resultados calculados
          </div>
          <div style={{ fontSize: 11, color: G.muted, marginBottom: 10 }}>
            HPS {modo === "pior" ? "(pior mês)" : "(média anual)"}: <strong style={{color:G.deep}}>{hps}h/dia</strong>
            {" · "}PR: {pr} {" · "}Fonte: PVGIS ERA5
          </div>
          <ResultRow label="Potência mínima necessária" value={potMin} unit="kWp" />
          <ResultRow label="Potência instalada" value={potInst} unit="kWp" highlight />
          <ResultRow label="Geração anual estimada" value={geracao.toLocaleString("pt-BR")} unit="kWh/ano" />
          <ResultRow label="Consumo anual estimado" value={consumoAnual.toLocaleString("pt-BR")} unit="kWh/ano" />
          <div style={{
            padding: "12px 14px", borderRadius: 8, marginTop: 4, textAlign: "center",
            background: nzeb ? "#C8E6C9" : "#FFCDD2",
            border: `1px solid ${nzeb ? "#81C784" : "#E57373"}`
          }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: nzeb ? "#1B5E20" : "#B71C1C" }}>
              {nzeb ? "✅ NZEB alcançado" : "⚠️ Déficit energético"}
            </div>
            <div style={{ fontSize: 12, color: nzeb ? "#2E7D32" : "#C62828", marginTop: 2 }}>
              Saldo: {saldo > 0 ? "+" : ""}{saldo.toLocaleString("pt-BR")} kWh/ano
            </div>
          </div>
        </Card>

        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: G.ink }}>Dimensionamento de bateria</span>
            <LockedBadge />
          </div>
          <div style={{ fontSize: 12, color: G.muted, fontStyle: "italic" }}>
            Autonomia, DoD, capacidade instalada e sizing de inversor disponíveis na versão completa.
          </div>
        </Card>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab 2 — Gap Analysis
// ═══════════════════════════════════════════════════════════════
function TabGap() {
  const [cert, setCert] = useState("edge");
  const [status, setStatus] = useState({});

  const certAtual = CERTS.find(c => c.id === cert);
  const opts = ["✅ Atende","⚠️ Parcial","❌ Não atende","⬜ N/A"];
  const bgMap = {"✅ Atende":"#C8E6C9","⚠️ Parcial":"#FFE0B2","❌ Não atende":"#FFCDD2","⬜ N/A":"#E3F2FD"};

  const counts = opts.reduce((acc,o) => {
    acc[o] = certAtual.criterios.filter(c => status[cert+"_"+c.campo] === o).length;
    return acc;
  }, {});
  const total = certAtual.criterios.length;
  const atende = counts["✅ Atende"] || 0;
  const pct = Math.round((atende / total) * 100);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 16 }}>
      {/* Seletor de certificação */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {CERTS.map(c => (
          <button key={c.id} onClick={() => setCert(c.id)} style={{
            padding: "12px 14px", borderRadius: 10, border: `1px solid ${cert===c.id ? c.cor : G.border}`,
            background: cert===c.id ? c.cor + "12" : G.white, cursor: "pointer",
            textAlign: "left", fontFamily: "inherit", transition: "all 0.15s"
          }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: cert===c.id ? c.cor : G.ink }}>{c.nome}</div>
          </button>
        ))}
        <div style={{
          padding: "12px 14px", borderRadius: 10, border: `1px solid ${G.border}`,
          background: "#FFF8E1", opacity: 0.7
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#E65100" }}>🔒 LEED v5</div>
          <div style={{ fontSize: 10, color: G.muted, marginTop: 2 }}>Versão completa</div>
        </div>
        <div style={{
          padding: "12px 14px", borderRadius: 10, border: `1px solid ${G.border}`,
          background: "#FFF8E1", opacity: 0.7
        }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#E65100" }}>🔒 +5 certificações</div>
          <div style={{ fontSize: 10, color: G.muted, marginTop: 2 }}>Versão completa</div>
        </div>
      </div>

      {/* Critérios */}
      <div>
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: G.deep }}>{certAtual.nome}</div>
              <div style={{ fontSize: 11, color: G.muted, marginTop: 2 }}>{total} critérios nesta versão demo</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 26, fontWeight: 800, color: pct >= 60 ? G.mid : pct >= 30 ? "#F59E0B" : "#EF4444" }}>{pct}%</div>
              <div style={{ fontSize: 10, color: G.muted }}>atendido</div>
            </div>
          </div>

          {/* Barra de progresso */}
          <div style={{ height: 6, background: G.gray, borderRadius: 3, marginBottom: 16, overflow: "hidden" }}>
            <div style={{ height: "100%", width: pct + "%", background: G.sage, borderRadius: 3, transition: "width 0.3s" }} />
          </div>

          {certAtual.criterios.map(c => {
            const key = cert + "_" + c.campo;
            const val = status[key] || "";
            return (
              <div key={c.campo} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "10px 12px", borderRadius: 8, marginBottom: 6,
                background: bgMap[val] || G.gray,
                border: `1px solid ${val ? bgMap[val] : G.border}`
              }}>
                <span style={{ fontSize: 12, color: G.ink, flex: 1, paddingRight: 12 }}>{c.req}</span>
                <select value={val} onChange={e => setStatus(s => ({...s, [key]: e.target.value}))}
                  style={{
                    padding: "4px 8px", borderRadius: 6, border: `1px solid ${G.border}`,
                    fontSize: 11, fontFamily: "inherit", cursor: "pointer",
                    background: bgMap[val] || G.white, minWidth: 130
                  }}>
                  <option value="">— selecionar —</option>
                  {opts.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
            );
          })}

          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            {opts.map(o => (
              <div key={o} style={{
                padding: "4px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600,
                background: bgMap[o], color: G.ink
              }}>
                {o}: {counts[o] || 0}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab 3 — Materiais por Clima
// ═══════════════════════════════════════════════════════════════
function TabMateriais() {
  const [cidade, setCidade] = useState("Petrópolis — RJ");
  const c = CIDADES[cidade];
  const mat = MATERIAIS[c.zona];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      <div>
        <Card>
          <div style={{ fontWeight: 700, color: G.deep, marginBottom: 14, fontSize: 14 }}>
            🌍 Selecionar cidade de referência
          </div>
          <select value={cidade} onChange={e => setCidade(e.target.value)} style={{
            width: "100%", padding: "10px 12px", borderRadius: 8,
            border: `2px solid #BFDBFE`, background: "#EFF6FF",
            fontSize: 13, color: "#1E40AF", fontWeight: 600, fontFamily: "inherit",
            marginBottom: 14
          }}>
            {Object.keys(CIDADES).map(c => <option key={c}>{c}</option>)}
          </select>

          <div style={{ padding: "14px 16px", background: mat.cor, borderRadius: 10, marginBottom: 12 }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: G.deep, marginBottom: 4 }}>
              {CIDADES[cidade].pais === "Brasil" ? `Zona Bioclimática ${c.zona}` : "Referência Internacional"}
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, color: G.mid }}>{mat.label}</div>
            <div style={{ fontSize: 11, color: G.muted, marginTop: 4 }}>
              HPS: {c.hps}h/dia (média) · {c.hps_min}h/dia (pior mês)
            </div>
          </div>

          <div style={{ fontSize: 11, color: G.muted, fontStyle: "italic" }}>
            Recomendações baseadas na NBR 15220 (zonas BR) e PVGIS ERA5. Confirmar com simulação EnergyPlus.
          </div>
        </Card>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {[
          ["🏗️ Estrutura principal", mat.estrutura],
          ["🧱 Vedação / paredes", mat.vedacao],
          ["🌡️ Isolamento", mat.isolamento],
          ["🏠 Cobertura", mat.cobertura],
          ["🪟 Esquadrias / vidro", mat.esquadria],
        ].map(([label, value]) => (
          <div key={label} style={{
            padding: "12px 14px", background: G.white, borderRadius: 10,
            border: `1px solid ${G.border}`, display: "flex", gap: 12, alignItems: "flex-start"
          }}>
            <span style={{ fontSize: 16, flexShrink: 0 }}>{label.split(" ")[0]}</span>
            <div>
              <div style={{ fontSize: 11, color: G.muted, marginBottom: 2 }}>{label.replace(label.split(" ")[0]+" ","")}</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: G.deep }}>{value}</div>
            </div>
          </div>
        ))}
        <div style={{
          padding: "12px 14px", background: "#FFF8E1", borderRadius: 10,
          border: "1px solid #FFB74D", display: "flex", gap: 12, alignItems: "center"
        }}>
          <span style={{ fontSize: 16 }}>🔒</span>
          <div>
            <div style={{ fontSize: 11, color: "#E65100", fontWeight: 700 }}>Versão completa</div>
            <div style={{ fontSize: 11, color: G.muted }}>Fichas técnicas completas com CO₂, custo e fornecedores por região</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Tab 4 — Calculadora de Acabamentos
// ═══════════════════════════════════════════════════════════════
function TabAcabamentos() {
  const [tipo, setTipo] = useState("tadelakt");
  const [area, setArea] = useState(12);
  const [aplic, setAplic] = useState("prof");

  const ac = ACABAMENTOS[tipo];
  const matTotal = (ac.matM2 + ac.base) * area;
  const ferrTotal = ac.ferramentas;
  const moTotal = aplic === "diy" ? 0 : ac.moM2 * area;
  const total = matTotal + ferrTotal + moTotal;
  const totalM2 = total / area;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      <Card>
        <div style={{ fontWeight: 700, color: G.deep, marginBottom: 14, fontSize: 14 }}>
          🎨 Selecionar acabamento
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
          {Object.entries(ACABAMENTOS).map(([key, ac]) => (
            <button key={key} onClick={() => setTipo(key)} style={{
              padding: "10px 14px", borderRadius: 8, textAlign: "left", cursor: "pointer",
              border: `1px solid ${tipo===key ? G.deep : G.border}`,
              background: tipo===key ? G.pale : G.white,
              fontFamily: "inherit", transition: "all 0.15s"
            }}>
              <span style={{ fontSize: 13, fontWeight: tipo===key ? 700 : 400,
                color: tipo===key ? G.deep : G.ink }}>{ac.nome}</span>
            </button>
          ))}
        </div>

        <InputRow label="Área a revestir" value={area}
          onChange={setArea} unit="m²" min={1} max={500}
          note="Incluir paredes, teto e áreas molhadas conforme o caso" />

        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: G.ink, marginBottom: 6 }}>Tipo de aplicação</div>
          <div style={{ display: "flex", gap: 8 }}>
            {[["prof","Profissional"],["diy","DIY (você mesmo)"]].map(([v,l]) => (
              <button key={v} onClick={() => setAplic(v)} style={{
                flex: 1, padding: "8px", borderRadius: 7,
                border: `1px solid ${aplic===v ? G.deep : G.border}`,
                background: aplic===v ? G.pale : G.white,
                color: aplic===v ? G.deep : G.muted,
                fontWeight: aplic===v ? 700 : 400, fontSize: 11,
                cursor: "pointer", fontFamily: "inherit"
              }}>{l}</button>
            ))}
          </div>
          {aplic === "diy" && (
            <div style={{ fontSize: 10, marginTop: 4, color: "#2E7D32", fontStyle: "italic" }}>
              ✅ DIY economiza R$ {(ac.moM2 * area).toLocaleString("pt-BR")} em mão de obra
            </div>
          )}
        </div>
      </Card>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Card bg={G.pale}>
          <div style={{ fontWeight: 700, color: G.deep, marginBottom: 12, fontSize: 14 }}>
            💰 Orçamento estimado
          </div>
          <ResultRow label="Material + base de aderência"
            value={"R$ " + matTotal.toLocaleString("pt-BR", {minimumFractionDigits:0})} unit="" />
          <ResultRow label="Kit de ferramentas (custo único)"
            value={"R$ " + ferrTotal.toLocaleString("pt-BR")} unit="" />
          <ResultRow label={aplic === "diy" ? "Mão de obra (DIY — R$0)" : "Mão de obra profissional"}
            value={aplic === "diy" ? "R$ 0" : "R$ " + moTotal.toLocaleString("pt-BR")} unit="" />
          <div style={{
            padding: "14px", background: G.deep, borderRadius: 10, marginTop: 8, textAlign: "center"
          }}>
            <div style={{ fontSize: 11, color: G.sage, marginBottom: 2 }}>CUSTO TOTAL ESTIMADO</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: G.white }}>
              R$ {total.toLocaleString("pt-BR", {minimumFractionDigits: 0})}
            </div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 2 }}>
              R$ {Math.round(totalM2).toLocaleString("pt-BR")} / m² · área: {area}m²
            </div>
          </div>
        </Card>

        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: G.ink }}>Detalhamento completo</span>
            <LockedBadge />
          </div>
          <div style={{ fontSize: 12, color: G.muted, fontStyle: "italic" }}>
            Quantidade exata de sacos, fornecedores regionais, comparativo de todos os acabamentos e certificações compatíveis na versão completa.
          </div>
        </Card>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// App principal
// ═══════════════════════════════════════════════════════════════
const TABS = [
  { id: "solar",     icon: "☀️", label: "Energia Solar",     comp: TabSolar },
  { id: "gap",       icon: "🔍", label: "Certificações",      comp: TabGap },
  { id: "materiais", icon: "🌍", label: "Materiais por Clima",comp: TabMateriais },
  { id: "acabamentos",icon:"🎨", label: "Acabamentos",        comp: TabAcabamentos },
];

export default function SustainKitDemo() {
  const [tab, setTab] = useState("solar");
  const Tab = TABS.find(t => t.id === tab).comp;

  return (
    <div style={{
      fontFamily: "-apple-system, 'Segoe UI', Arial, sans-serif",
      background: G.gray, minHeight: "100vh", padding: "0 0 32px"
    }}>
      {/* Header */}
      <div style={{ background: G.deep, padding: "20px 28px 0" }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
            <div style={{
              width: 36, height: 36, borderRadius: "50%", background: G.sage,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 18, flexShrink: 0
            }}>🌿</div>
            <div>
              <div style={{ fontWeight: 800, fontSize: 18, color: G.white, letterSpacing: "-0.02em" }}>
                Physis SustainKit
              </div>
              <div style={{ fontSize: 11, color: G.sage }}>
                Plataforma de dimensionamento para construção sustentável · Demo gratuita
              </div>
            </div>
            <div style={{ marginLeft: "auto" }}>
              <Badge color={G.sage}>DEMO</Badge>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 4, overflowX: "auto", paddingBottom: 0 }}>
            {TABS.map(t => (
              <TabBtn key={t.id} icon={t.icon} label={t.label}
                active={tab === t.id} onClick={() => setTab(t.id)} />
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 900, margin: "20px auto", padding: "0 16px" }}>
        <Tab />

        {/* CTA */}
        <div style={{
          marginTop: 20, padding: "16px 20px", background: G.white,
          borderRadius: 12, border: `1px solid ${G.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "center",
          flexWrap: "wrap", gap: 12
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: G.deep }}>
              Quer a ferramenta completa?
            </div>
            <div style={{ fontSize: 12, color: G.muted, marginTop: 2 }}>
              252 fórmulas · 9 certificações · 6 cidades globais · Checklist de obra · Fornecedores · Manual técnico
            </div>
          </div>
          <a href="mailto:contato@physis.com.br" style={{
            padding: "10px 22px", background: G.deep, color: G.white,
            borderRadius: 8, fontWeight: 700, fontSize: 13,
            textDecoration: "none", whiteSpace: "nowrap"
          }}>
            Solicitar versão completa →
          </a>
        </div>
      </div>
    </div>
  );
}
