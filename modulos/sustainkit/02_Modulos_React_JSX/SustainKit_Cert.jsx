import { useState } from "react";

const C = {
  main:"#4A148C", light:"#F3E5F5", mid:"#6A1B9A", pale:"#F3E5F5",
  white:"#FFFFFF", ink:"#1C2B22", gray:"#F4F7F4", border:"#E1BEE7",
  muted:"#6B7F6E",
};

const CERTS = {
  leed:{nome:"LEED v5 BD+C (Abril 2025)",cor:"#1565C0",criterios:[
    {req:"Descarbonização — NZEB + eletrificação total + ACV ciclo de vida obrigatório",campo:"l1"},
    {req:"Carbono incorporado — LCA + EPD obrigatória para estrutura e vedação",campo:"l2"},
    {req:"Energia — M&V datalogger por circuito integrado ao Arc platform",campo:"l3"},
    {req:"Água — Redução ≥30% + medição de consumo real (WaterSense)",campo:"l4"},
    {req:"Materiais — HPD (Health Product Declaration) para itens principais",campo:"l5"},
    {req:"Ecologia — Plano de biodiversidade e restauração do terreno (NOVO v5)",campo:"l6"},
    {req:"Qualidade de Vida — Monitoramento CO₂, VOC e PM2.5 interno",campo:"l7"},
    {req:"Resiliência Climática — Avaliação de risco climático obrigatória (NOVO v5)",campo:"l8"},
    {req:"Equidade Social — Práticas trabalhistas justas na cadeia construtiva (NOVO v5)",campo:"l9"},
    {req:"Registro na plataforma Arc (arc-app.gbci.org) antes do início das obras",campo:"l10"},
  ]},
  edge:{nome:"EDGE (IFC/Banco Mundial)",cor:"#1976D2",criterios:[
    {req:"Energia: redução ≥20% do consumo vs. linha de base local",campo:"e1"},
    {req:"Água: redução ≥20% do consumo vs. linha de base",campo:"e2"},
    {req:"Carbono incorporado: redução ≥20% nos materiais",campo:"e3"},
    {req:"EPDs dos materiais principais documentadas",campo:"e4"},
    {req:"Registro do projeto na plataforma edgebuildings.com",campo:"e5"},
    {req:"Auditor EDGE certificado contratado para revisão",campo:"e6"},
  ]},
  casaazul:{nome:"Selo Casa Azul — Caixa",cor:"#1565C0",criterios:[
    {req:"Eficiência energética RTQ-R Nível A (PROCEL Edifica)",campo:"c1"},
    {req:"Captação de água pluvial instalada (ABNT NBR 15527)",campo:"c2"},
    {req:"Coleta seletiva e compostagem",campo:"c3"},
    {req:"Ventilação e iluminação natural (ABNT NBR 15575)",campo:"c4"},
    {req:"Manual do proprietário / hóspede entregue",campo:"c5"},
  ]},
  greenkey:{nome:"GreenKey — Hospitalidade",cor:"#2E7D32",criterios:[
    {req:"Política ambiental documentada e comunicada ao hóspede",campo:"g1"},
    {req:"Medição e redução do consumo de energia",campo:"g2"},
    {req:"100% água de fontes sustentáveis",campo:"g3"},
    {req:"Separação de resíduos e compostagem",campo:"g4"},
    {req:"Produtos locais e orgânicos para hóspedes",campo:"g5"},
  ]},
  pbqp:{nome:"PBQP-H Bioconstrução",cor:"#6A1B9A",criterios:[
    {req:"Materiais naturais ou reciclados documentados e rastreados",campo:"p1"},
    {req:"ART assinada em todos os projetos técnicos (CREA)",campo:"p2"},
    {req:"Conformidade NBR 15575 e NBR 15220",campo:"p3"},
    {req:"Responsável técnico credenciado pelo PBQP-H",campo:"p4"},
  ]},
};

const STATUS_OPTS=["✅ Atende","⚠️ Parcial","❌ Não atende","⬜ N/A"];
const STATUS_BG={"✅ Atende":"#C8E6C9","⚠️ Parcial":"#FFE0B2","❌ Não atende":"#FFCDD2","⬜ N/A":"#E3F2FD"};

const CHECKLIST=[
  {fase:"Fase 1 — Planejamento",cor:"#0D47A1",itens:[
    "Verificar zoneamento e zona de risco (Defesa Civil)",
    "Obter LPLS — Licença Prévia de Localização e Saneamento",
    "Contratar arquiteto especialista em bioconstrução",
    "Elaborar PGRCC — Plano de Gerenciamento de Resíduos",
    "Submeter ao INEA (licença ambiental Mata Atlântica)",
    "Registrar projeto no LEED Arc ou EDGE",
  ]},
  {fase:"Fase 2 — Pré-Produção",cor:"#1565C0",itens:[
    "Encomendar painéis SIP e vigas CLT na fábrica",
    "Pedido de painéis solares, inversor e baterias",
    "Instalar cisterna e sistema de captação pluvial",
    "Instalar biodigestor e gasômetro",
    "Executar fundação com anel de aterramento (SPDA)",
  ]},
  {fase:"Fase 3 — Montagem",cor:"#1976D2",itens:[
    "Montar estrutura CLT (equipe especializada)",
    "Fixar painéis SIP de fechamento e cobertura",
    "Instalar sistema elétrico FV (NBR 5410 + NBR 16690)",
    "Instalar inversor + bateria + DPS Classe II/III",
    "Executar instalações hidrossanitárias",
  ]},
  {fase:"Fase 4 — Acabamento",cor:"#2196F3",itens:[
    "Aplicar tadelakt ou reboco de cal (áreas molhadas)",
    "Aplicar tinta Arpex zero VOC (paredes internas)",
    "Instalar piso deck madeira FSC",
    "Configurar hub Home Assistant + IoT",
    "Executar paisagismo com mudas nativas",
  ]},
  {fase:"Fase 5 — Certificação",cor:"#0288D1",itens:[
    "Solicitar Habite-se na Prefeitura",
    "Solicitar homologação ANEEL sistema FV",
    "Submeter documentação para auditoria LEED/EDGE",
    "Sessão fotográfica + publicar nos OTAs",
    "Entregar manual digital ao hóspede com QR codes",
  ]},
];

const MODELOS=[
  {id:"chale",icon:"🏡",nome:"Chalé Individual",escala:"1 un · 60–120m²",
   solar:"8–12 kWp",cert:"EDGE + LEED Gold",
   forca:"Baixo risco · rápido · prova de conceito",
   oportunidade:"Showcase SustainKit · modelo replicável",cor:"#E8F5E9"},
  {id:"conjunto",icon:"🏘️",nome:"Conjunto (3–5 chalés)",escala:"3–5 un · terreno único",
   solar:"25–40 kWp",cert:"EDGE + LEED Gold",
   forca:"Economia de escala · grupos · retiros",
   oportunidade:"Turismo de wellness em crescimento",cor:"#EDE7F6"},
  {id:"sede",icon:"🏢",nome:"Sede Physis",escala:"200–400m²",
   solar:"15–25 kWp",cert:"LEED Platinum + PBQP-H",
   forca:"Credibilidade · vitrine · captação editais",
   oportunidade:"GIZ · Banco Mundial · laboratório",cor:"#FFF9C4"},
  {id:"hotel",icon:"🏨",nome:"Hotel Boutique",escala:"8–15 quartos · 800–1.500m²",
   solar:"60–100 kWp",cert:"LEED Gold + WELL + GreenKey",
   forca:"Maior receita · marca consolidada",
   oportunidade:"Mercado de hospedagem sustentável premium",cor:"#FCE4EC"},
];

function Card({children,style={},bg=C.white}){
  return <div style={{background:bg,border:`1px solid ${C.border}`,borderRadius:12,
    padding:"16px 18px",boxShadow:"0 2px 10px rgba(74,20,140,0.07)",...style}}>{children}</div>;
}
function TabBtn({label,icon,active,onClick}){
  return <button onClick={onClick} style={{padding:"9px 16px",border:"none",background:"transparent",
    cursor:"pointer",color:active?C.white:C.main+"99",fontWeight:active?700:400,fontSize:12,
    fontFamily:"inherit",borderBottom:active?`2px solid ${C.white}`:"2px solid transparent",
    display:"flex",alignItems:"center",gap:5,whiteSpace:"nowrap"}}>
    <span>{icon}</span>{label}
  </button>;
}

function TabGap(){
  const [cert,setCert]=useState("leed");
  const [status,setStatus]=useState({});
  const certAtual=CERTS[cert];
  const pctMap={};
  Object.keys(CERTS).forEach(k=>{
    const total=CERTS[k].criterios.length;
    const ok=CERTS[k].criterios.filter(c=>status[k+"_"+c.campo]==="✅ Atende").length;
    pctMap[k]=Math.round((ok/total)*100);
  });
  const counts=STATUS_OPTS.reduce((a,o)=>{
    a[o]=certAtual.criterios.filter(c=>status[cert+"_"+c.campo]===o).length; return a;},{});
  return(
    <div style={{display:"grid",gridTemplateColumns:"200px 1fr",gap:14}}>
      <div style={{display:"flex",flexDirection:"column",gap:7}}>
        {Object.entries(CERTS).map(([k,c])=>(
          <button key={k} onClick={()=>setCert(k)} style={{padding:"11px 13px",borderRadius:10,
            border:`1px solid ${cert===k?c.cor:C.border}`,background:cert===k?c.cor+"15":C.white,
            cursor:"pointer",textAlign:"left",fontFamily:"inherit",transition:"all 0.15s"}}>
            <div style={{fontSize:11,fontWeight:700,color:cert===k?c.cor:C.ink,marginBottom:4}}>{c.nome}</div>
            <div style={{height:3,background:C.gray,borderRadius:2,overflow:"hidden"}}>
              <div style={{height:"100%",width:pctMap[k]+"%",background:c.cor,transition:"width 0.3s"}}/>
            </div>
            <div style={{fontSize:10,color:C.muted,marginTop:2}}>{pctMap[k]}% atendido</div>
          </button>
        ))}
      </div>
      <Card>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:12}}>
          <div>
            <div style={{fontWeight:700,fontSize:13,color:C.ink}}>{certAtual.nome}</div>
            <div style={{fontSize:11,color:C.muted,marginTop:2}}>{certAtual.criterios.length} critérios</div>
          </div>
          <div style={{padding:"7px 14px",background:certAtual.cor+"15",borderRadius:10,textAlign:"center",
            border:`1px solid ${certAtual.cor}33`}}>
            <div style={{fontSize:22,fontWeight:800,color:certAtual.cor}}>{pctMap[cert]}%</div>
            <div style={{fontSize:9,color:C.muted}}>atendido</div>
          </div>
        </div>
        <div style={{height:5,background:C.gray,borderRadius:3,marginBottom:12,overflow:"hidden"}}>
          <div style={{height:"100%",width:pctMap[cert]+"%",background:certAtual.cor,transition:"width 0.4s"}}/>
        </div>
        {certAtual.criterios.map(c=>{
          const key=cert+"_"+c.campo;
          const val=status[key]||"";
          return(
            <div key={c.campo} style={{display:"flex",justifyContent:"space-between",alignItems:"center",
              padding:"9px 11px",borderRadius:8,marginBottom:5,gap:10,
              background:STATUS_BG[val]||C.gray,border:`1px solid ${val?STATUS_BG[val]:C.border}`}}>
              <span style={{fontSize:12,color:C.ink,flex:1}}>{c.req}</span>
              <select value={val} onChange={e=>setStatus(s=>({...s,[key]:e.target.value}))}
                style={{padding:"4px 8px",borderRadius:6,border:`1px solid ${C.border}`,
                  fontSize:11,fontFamily:"inherit",cursor:"pointer",background:STATUS_BG[val]||C.white,minWidth:130}}>
                <option value="">— selecionar —</option>
                {STATUS_OPTS.map(o=><option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          );
        })}
        <div style={{display:"flex",gap:6,marginTop:10,flexWrap:"wrap"}}>
          {STATUS_OPTS.map(o=>(
            <div key={o} style={{padding:"3px 10px",borderRadius:20,fontSize:11,fontWeight:600,
              background:STATUS_BG[o]}}>{o}: {counts[o]||0}</div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TabChecklist(){
  const [checks,setChecks]=useState({});
  const toggle=k=>setChecks(s=>({...s,[k]:!s[k]}));
  const total=CHECKLIST.reduce((a,f)=>a+f.itens.length,0);
  const done=Object.values(checks).filter(Boolean).length;
  const pct=Math.round((done/total)*100);
  return(
    <div>
      <Card style={{marginBottom:12,padding:"12px 16px"}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:6}}>
          <div style={{fontWeight:700,fontSize:13,color:C.ink}}>✅ {total} itens em 5 fases construtivas</div>
          <div style={{fontWeight:800,fontSize:18,color:C.main}}>{done}/{total} ({pct}%)</div>
        </div>
        <div style={{height:7,background:C.gray,borderRadius:4,overflow:"hidden"}}>
          <div style={{height:"100%",width:pct+"%",background:pct===100?"#2E7D32":C.main,borderRadius:4,transition:"width 0.4s"}}/>
        </div>
      </Card>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        {CHECKLIST.map((f,fi)=>{
          const fd=f.itens.filter((_,ii)=>checks[fi+"_"+ii]).length;
          return(
            <Card key={f.fase} style={{padding:"13px 15px"}}>
              <div style={{fontWeight:700,fontSize:12,color:f.cor,marginBottom:2}}>{f.fase}</div>
              <div style={{fontSize:10,color:C.muted,marginBottom:8}}>{fd}/{f.itens.length} concluídos</div>
              {f.itens.map((item,ii)=>{
                const key=fi+"_"+ii;
                const done=checks[key];
                return(
                  <div key={ii} onClick={()=>toggle(key)} style={{display:"flex",gap:7,alignItems:"flex-start",
                    padding:"6px 8px",borderRadius:7,marginBottom:4,cursor:"pointer",
                    background:done?"#C8E6C9":C.gray,border:`1px solid ${done?"#81C784":C.border}`,transition:"all 0.15s"}}>
                    <div style={{width:15,height:15,borderRadius:3,flexShrink:0,marginTop:1,
                      background:done?C.main:"transparent",border:`2px solid ${done?C.main:C.border}`,
                      display:"flex",alignItems:"center",justifyContent:"center"}}>
                      {done&&<span style={{color:C.white,fontSize:9}}>✓</span>}
                    </div>
                    <span style={{fontSize:11,color:done?"#1B5E20":C.ink,textDecoration:done?"line-through":"none",lineHeight:1.4}}>
                      {item}
                    </span>
                  </div>
                );
              })}
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function TabModelos(){
  const [sel,setSel]=useState("chale");
  const m=MODELOS.find(x=>x.id===sel);
  return(
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{display:"flex",gap:10}}>
        {MODELOS.map(x=>(
          <button key={x.id} onClick={()=>setSel(x.id)} style={{flex:1,padding:"12px",borderRadius:12,
            border:`2px solid ${sel===x.id?C.main:C.border}`,background:sel===x.id?C.pale:C.white,
            cursor:"pointer",textAlign:"center",fontFamily:"inherit",transition:"all 0.2s"}}>
            <div style={{fontSize:20,marginBottom:4}}>{x.icon}</div>
            <div style={{fontSize:11,fontWeight:700,color:sel===x.id?C.main:C.ink}}>{x.nome}</div>
            <div style={{fontSize:10,color:C.muted}}>{x.escala}</div>
          </button>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
        <Card bg={m.cor}>
          <div style={{fontWeight:700,fontSize:14,color:C.ink,marginBottom:12}}>{m.icon} {m.nome}</div>
          {[["Escala",m.escala],["Sistema solar",m.solar],["Certificação alvo",m.cert]].map(([l,v])=>(
            <div key={l} style={{padding:"9px 11px",background:"rgba(255,255,255,0.7)",borderRadius:8,marginBottom:6}}>
              <div style={{fontSize:10,color:C.muted}}>{l}</div>
              <div style={{fontSize:13,fontWeight:700,color:C.ink}}>{v}</div>
            </div>
          ))}
        </Card>
        <div style={{display:"flex",flexDirection:"column",gap:8}}>
          {[["💪 Forças",m.forca,"#C8E6C9","#1B5E20"],
            ["🚀 Oportunidades",m.oportunidade,"#C8E6C9","#1B5E20"]].map(([l,v,bg,co])=>(
            <div key={l} style={{padding:"12px 14px",background:bg,borderRadius:10}}>
              <div style={{fontSize:11,fontWeight:700,color:co,marginBottom:3}}>{l}</div>
              <div style={{fontSize:12,color:C.ink}}>{v}</div>
            </div>
          ))}
          <Card>
            <div style={{fontSize:11,fontWeight:700,color:C.main,marginBottom:6}}>Próximos passos</div>
            <div style={{fontSize:11,color:C.muted}}>
              1. Definir terreno e verificar zoneamento<br/>
              2. Registrar no LEED Arc ou EDGE<br/>
              3. Contratar equipe técnica especializada<br/>
              4. Elaborar PGRCC antes das obras
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

const TABS=[
  {id:"gap",icon:"🔍",label:"Gap Analysis",comp:TabGap},
  {id:"check",icon:"✅",label:"Checklist Obra",comp:TabChecklist},
  {id:"modelos",icon:"💼",label:"Modelos de Negócio",comp:TabModelos},
];

export default function App(){
  const [tab,setTab]=useState("gap");
  const Tab=TABS.find(t=>t.id===tab).comp;
  return(
    <div style={{fontFamily:"-apple-system,'Segoe UI',Arial,sans-serif",background:"#F3E5F5",minHeight:"100vh"}}>
      <div style={{background:C.main,padding:"14px 20px 0"}}>
        <div style={{maxWidth:900,margin:"0 auto"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
            <div style={{display:"flex",alignItems:"center",gap:10}}>
              <div style={{width:32,height:32,borderRadius:"50%",background:"rgba(255,255,255,0.2)",
                display:"flex",alignItems:"center",justifyContent:"center",fontSize:16}}>🔍</div>
              <div>
                <div style={{fontWeight:800,fontSize:16,color:C.white}}>SustainKit Cert</div>
                <div style={{fontSize:10,color:"rgba(255,255,255,0.7)"}}>Physis Engineering · Certificações, Checklist e Modelos de Negócio</div>
              </div>
            </div>
            <div style={{background:"rgba(255,255,255,0.15)",borderRadius:6,padding:"3px 12px",
              fontSize:11,fontWeight:700,color:C.white}}>v1.0</div>
          </div>
          <div style={{display:"flex",gap:2}}>
            {TABS.map(t=><TabBtn key={t.id} icon={t.icon} label={t.label} active={tab===t.id} onClick={()=>setTab(t.id)}/>)}
          </div>
        </div>
      </div>
      <div style={{maxWidth:900,margin:"16px auto",padding:"0 16px"}}><Tab/></div>
      <div style={{textAlign:"center",padding:"12px",fontSize:10,color:C.muted}}>
        Physis Engineering · LEED v5 (Abril 2025) · EDGE IFC · Selo Casa Azul · GreenKey · PBQP-H
      </div>
    </div>
  );
}
