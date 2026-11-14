import { useState } from "react";

const G = {
  deep:"#074031",mid:"#51774B",sage:"#81A969",pale:"#EEF8EB",
  white:"#FFFFFF",ink:"#1C2B22",gray:"#F4F7F4",border:"#D4E8D0",muted:"#6B7F6E",
};

const CIDADES = {
  "Petrópolis — RJ":{hps:4.20,hpsMin:3.42,zona:3,prec:1520},
  "Rio de Janeiro — RJ":{hps:4.65,hpsMin:3.71,zona:4,prec:1200},
  "São Paulo — SP":{hps:4.40,hpsMin:3.52,zona:3,prec:1400},
  "Brasília — DF":{hps:5.47,hpsMin:4.12,zona:4,prec:1500},
  "Belo Horizonte — MG":{hps:4.90,hpsMin:3.85,zona:3,prec:1500},
  "Curitiba — PR":{hps:3.90,hpsMin:2.98,zona:1,prec:1400},
  "Salvador — BA":{hps:5.20,hpsMin:4.20,zona:7,prec:1900},
  "João Pessoa — PB":{hps:5.80,hpsMin:4.92,zona:8,prec:1700},
  "Manaus — AM":{hps:4.89,hpsMin:4.21,zona:8,prec:2200},
  "Tunis — Tunísia":{hps:5.02,hpsMin:2.87,zona:0,prec:400},
  "Amsterdã — Holanda":{hps:2.68,hpsMin:0.81,zona:0,prec:900},
};

const MAT_ZONA = {
  0:{e:"CLT + SIP",v:"Análise local",i:"Verificar",c:"Verificar",es:"Vidro duplo",l:"Internacional",cor:"#F3E5F5"},
  1:{e:"CLT + SIP 150mm",v:"SIP + BTC + hempcrete",i:"Lã rocha 100mm",c:"Sanduíche 80mm + telhado verde",es:"Vidro triplo câmara argônio",l:"Frio (Zona 1)",cor:"#DBEAFE"},
  2:{e:"CLT + SIP 100mm",v:"SIP + BTC",i:"Lã rocha 75mm",c:"Sanduíche 60mm + telhado verde",es:"Vidro triplo câmara argônio",l:"Muito frio (Zona 2)",cor:"#DBEAFE"},
  3:{e:"CLT + SIP 100mm",v:"SIP + BTC ou Hempcrete",i:"Lã PET 50mm",c:"Sanduíche 50mm + telhado verde",es:"Vidro duplo câmara ar",l:"Temperado (Zona 3)",cor:"#EDE7F6"},
  4:{e:"CLT ou SIP",v:"SIP ou BTC",i:"Lã PET cobertura",c:"Telhado verde",es:"Vidro duplo Low-E",l:"Subquente (Zona 4)",cor:"#E8F5E9"},
  5:{e:"CLT ou geopolímero",v:"BTC + alta inércia",i:"Lã rocha cobertura",c:"Sanduíche + câmara ar",es:"Vidro duplo Low-E",l:"Quente seco (Zona 5)",cor:"#FFF9C4"},
  6:{e:"Bambu + aço reciclado",v:"Adobe ou BTC",i:"Cobertura apenas",c:"Argila + cal refletiva",es:"Vidro duplo + shutters",l:"Quente e seco (Zona 6)",cor:"#FFE0B2"},
  7:{e:"Bambu + aço reciclado",v:"Adobe branco + pedra",i:"Cobertura apenas",c:"Argila + cal refletiva",es:"Vidro duplo + shutters madeira",l:"Quente e seco (Zona 7)",cor:"#FFE0B2"},
  8:{e:"Bambu Guadua + madeira FSC",v:"Paredes abertas + venezianas",i:"Mínimo",c:"Palha / sedum",es:"Venezianas + tela mosquiteiro",l:"Quente e úmido (Zona 8)",cor:"#FCE4EC"},
};

const CERTS = {
  leed:{nome:"LEED v5 BD+C (Abril 2025)",cor:"#1565C0",criterios:[
    {req:"Descarbonização — NZEB + eletrificação total + ACV obrigatório",campo:"l1"},
    {req:"Carbono Incorporado — LCA + EPD obrigatória (ISO 14025)",campo:"l2"},
    {req:"Energia — M&V datalogger por circuito + Arc platform",campo:"l3"},
    {req:"Água — Redução ≥30% + medição real (WaterSense)",campo:"l4"},
    {req:"Materiais — HPD obrigatória para itens principais",campo:"l5"},
    {req:"Ecologia — Plano biodiversidade + restauração (NOVO v5)",campo:"l6"},
    {req:"Qualidade de Vida — CO₂, VOC e PM2.5 monitorados",campo:"l7"},
    {req:"Resiliência Climática — avaliação de risco obrigatória (NOVO v5)",campo:"l8"},
    {req:"Equidade Social — práticas trabalhistas justas (NOVO v5)",campo:"l9"},
    {req:"Registro na plataforma Arc (arc-app.gbci.org)",campo:"l10"},
  ]},
  edge:{nome:"EDGE (IFC/Banco Mundial)",cor:"#1976D2",criterios:[
    {req:"Energia: redução ≥20% vs. linha de base",campo:"e1"},
    {req:"Água: redução ≥20% vs. linha de base",campo:"e2"},
    {req:"Carbono incorporado: redução ≥20%",campo:"e3"},
    {req:"EPDs dos materiais principais",campo:"e4"},
    {req:"Registro em edgebuildings.com",campo:"e5"},
  ]},
  casaazul:{nome:"Selo Casa Azul — Caixa",cor:"#0D47A1",criterios:[
    {req:"RTQ-R Nível A (PROCEL Edifica)",campo:"c1"},
    {req:"Captação pluvial (NBR 15527)",campo:"c2"},
    {req:"Coleta seletiva e compostagem",campo:"c3"},
    {req:"Ventilação e iluminação natural (NBR 15575)",campo:"c4"},
    {req:"Manual do proprietário entregue",campo:"c5"},
  ]},
  greenkey:{nome:"GreenKey — Hospitalidade",cor:"#2E7D32",criterios:[
    {req:"Política ambiental documentada",campo:"g1"},
    {req:"Medição e redução de energia",campo:"g2"},
    {req:"100% água sustentável",campo:"g3"},
    {req:"Separação de resíduos + compostagem",campo:"g4"},
    {req:"Produtos locais e orgânicos",campo:"g5"},
  ]},
  pbqp:{nome:"PBQP-H Bioconstrução",cor:"#6A1B9A",criterios:[
    {req:"Materiais naturais/reciclados rastreados",campo:"p1"},
    {req:"ART assinada em todos os projetos",campo:"p2"},
    {req:"Conformidade NBR 15575 e NBR 15220",campo:"p3"},
  ]},
};

const ACABAMENTOS = {
  tadelakt:{nome:"Tadelakt",matM2:115,base:42,ferramentas:680,moM2:280},
  cal:{nome:"Reboco Cal + Fibra",matM2:62,base:0,ferramentas:180,moM2:50},
  argila:{nome:"Tinta Argila (Arpex)",matM2:48,base:0,ferramentas:80,moM2:20},
  stucco:{nome:"Stucco Veneziano",matM2:220,base:0,ferramentas:220,moM2:320},
  bambu:{nome:"Piso Bambu (BLC)",matM2:160,base:18,ferramentas:120,moM2:45},
};

const CHECKLIST=[
  {fase:"Fase 1 — Planejamento",cor:"#0D47A1",itens:["Verificar zoneamento e zona de risco","Obter LPLS","Elaborar PGRCC","Submeter ao INEA","Registrar no LEED Arc ou EDGE"]},
  {fase:"Fase 2 — Pré-Produção",cor:"#1565C0",itens:["Encomendar CLT, SIP e sistemas solar","Instalar cisterna e captação pluvial","Executar fundação com SPDA (NBR 5419)"]},
  {fase:"Fase 3 — Montagem",cor:"#1976D2",itens:["Montar estrutura CLT + SIP","Instalar sistema FV (NBR 16690)","Instalar inversor + bateria + DPS"]},
  {fase:"Fase 4 — Acabamento",cor:"#2196F3",itens:["Aplicar tadelakt ou cal","Aplicar tinta Arpex zero VOC","Configurar Home Assistant + IoT","Paisagismo com mudas nativas"]},
  {fase:"Fase 5 — Certificação",cor:"#0288D1",itens:["Solicitar Habite-se","Homologação ANEEL sistema FV","Auditoria LEED/EDGE","Manual digital ao hóspede"]},
];

const MODELOS=[
  {id:"chale",icon:"🏡",nome:"Chalé Individual",escala:"1 un · 60–120m²",solar:"8–12 kWp",cert:"EDGE + LEED Gold",cor:"#E8F5E9"},
  {id:"conjunto",icon:"🏘️",nome:"Conjunto (3–5)",escala:"3–5 un · terreno único",solar:"25–40 kWp",cert:"EDGE + LEED Gold",cor:"#EDE7F6"},
  {id:"sede",icon:"🏢",nome:"Sede Physis",escala:"200–400m²",solar:"15–25 kWp",cert:"LEED Platinum",cor:"#FFF9C4"},
  {id:"hotel",icon:"🏨",nome:"Hotel Boutique",escala:"8–15 quartos",solar:"60–100 kWp",cert:"LEED Gold + WELL",cor:"#FCE4EC"},
];

const AGRO_C=[
  {nome:"Bomba irrigação",potencia:750,horas:6,ativo:false},
  {nome:"Câmara fria 10m³",potencia:2200,horas:16,ativo:false},
  {nome:"Ordenhadeira mecânica",potencia:1100,horas:2,ativo:false},
  {nome:"Debulhadora",potencia:3000,horas:3,ativo:false},
  {nome:"Iluminação LED galpão",potencia:200,horas:12,ativo:false},
  {nome:"Hub IoT rural",potencia:5,horas:24,ativo:false},
];

const STATUS_OPTS=["✅ Atende","⚠️ Parcial","❌ Não atende","⬜ N/A"];
const STATUS_BG={"✅ Atende":"#C8E6C9","⚠️ Parcial":"#FFE0B2","❌ Não atende":"#FFCDD2","⬜ N/A":"#E3F2FD"};

function Card({children,style={},bg=G.white}){
  return <div style={{background:bg,border:`1px solid ${G.border}`,borderRadius:12,padding:"15px 17px",boxShadow:"0 2px 8px rgba(7,64,49,0.06)",...style}}>{children}</div>;
}
function Inp({label,value,onChange,unit,min=0,max=9999,step=1,note}){
  return <div style={{marginBottom:10}}>
    {label&&<div style={{fontSize:11,fontWeight:600,color:G.ink,marginBottom:3}}>{label}</div>}
    <div style={{display:"flex",gap:6,alignItems:"center"}}>
      <input type="number" value={value} min={min} max={max} step={step} onChange={e=>onChange(+e.target.value)}
        style={{flex:1,padding:"7px 9px",border:"2px solid #BFDBFE",borderRadius:7,fontSize:14,fontWeight:700,color:"#1E40AF",background:"#EFF6FF",fontFamily:"inherit",outline:"none"}}/>
      {unit&&<span style={{fontSize:11,color:G.muted,minWidth:34}}>{unit}</span>}
    </div>
    {note&&<div style={{fontSize:10,color:G.muted,marginTop:2,fontStyle:"italic"}}>{note}</div>}
  </div>;
}
function Sel({label,value,onChange,opts}){
  return <div style={{marginBottom:10}}>
    {label&&<div style={{fontSize:11,fontWeight:600,color:G.ink,marginBottom:3}}>{label}</div>}
    <select value={value} onChange={e=>onChange(e.target.value)}
      style={{width:"100%",padding:"7px 9px",border:"2px solid #BFDBFE",borderRadius:7,background:"#EFF6FF",fontSize:12,color:"#1E40AF",fontWeight:600,fontFamily:"inherit"}}>
      {opts.map(o=><option key={typeof o==="string"?o:o.v} value={typeof o==="string"?o:o.v}>{typeof o==="string"?o:o.l}</option>)}
    </select>
  </div>;
}
function Res({label,value,hi=false}){
  return <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"7px 10px",background:hi?G.pale:G.gray,borderRadius:7,marginBottom:4,border:hi?`1px solid ${G.sage}`:"none"}}>
    <span style={{fontSize:12,color:G.ink}}>{label}</span>
    <span style={{fontSize:13,fontWeight:800,color:hi?G.deep:G.ink}}>{value}</span>
  </div>;
}

function TabSolar(){
  const [cidade,setCidade]=useState("Petrópolis — RJ");
  const [consumo,setConsumo]=useState(22);
  const [pot,setPot]=useState(10);
  const [modo,setModo]=useState("pior");
  const [autonomia,setAutonomia]=useState(48);
  const [dod,setDod]=useState(0.90);
  const [areaT,setAreaT]=useState(84);
  const [pessoas,setPessoas]=useState(2);
  const c=CIDADES[cidade];
  const hps=modo==="pior"?c.hpsMin:c.hps;
  const pr=0.78;
  const potMin=+(consumo/(hps*pr)).toFixed(1);
  const ger=Math.round(pot*hps*365*pr);
  const saldo=ger-consumo*365;
  const capBat=Math.round((consumo*(autonomia/24))/dod*1.2);
  const captacao=Math.round((c.prec/1000)*(areaT*0.85)*1000/365);
  const consumoAgua=pessoas*130;
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <div style={{display:"flex",flexDirection:"column",gap:10}}>
        <Card>
          <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:10}}>☀️ Sistema Solar FV</div>
          <Sel label="Cidade" value={cidade} onChange={setCidade} opts={Object.keys(CIDADES)}/>
          <Inp label="Consumo diário" value={consumo} onChange={setConsumo} unit="kWh/dia" min={1} max={500} step={0.5}/>
          <Inp label="Potência instalada" value={pot} onChange={setPot} unit="kWp" min={1} max={1000} step={0.5}/>
          <div style={{display:"flex",gap:6,marginBottom:8}}>
            {[["pior","Pior mês ✅"],["media","Média anual"]].map(([v,l])=>(
              <button key={v} onClick={()=>setModo(v)} style={{flex:1,padding:"5px",borderRadius:7,border:`1px solid ${modo===v?G.deep:G.border}`,background:modo===v?G.pale:G.white,color:modo===v?G.deep:G.muted,fontWeight:modo===v?700:400,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>{l}</button>
            ))}
          </div>
          <div style={{fontSize:10,color:G.muted,fontStyle:"italic",padding:"6px 8px",background:G.gray,borderRadius:6}}>
            HPS: {hps}h/dia · PR: {pr} · PVGIS ERA5 (JRC/EU)
          </div>
        </Card>
        <Card>
          <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:10}}>🔋 Bateria + 💧 Água</div>
          <Inp label="Autonomia bateria" value={autonomia} onChange={setAutonomia} unit="horas" min={12} max={168} step={12}/>
          <Sel label="Tecnologia" value={String(dod)} onChange={v=>setDod(+v)} opts={[{v:"0.90",l:"LiFePO4 — DoD 90%"},{v:"0.85",l:"Li-NMC — DoD 85%"},{v:"0.50",l:"AGM — DoD 50%"}]}/>
          <Inp label="Área de captação" value={areaT} onChange={setAreaT} unit="m²" min={10} max={5000}/>
          <Inp label="Ocupantes" value={pessoas} onChange={setPessoas} unit="pessoas" min={1} max={200}/>
        </Card>
      </div>
      <div style={{display:"flex",flexDirection:"column",gap:10}}>
        <Card bg={G.pale}>
          <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:8}}>📊 Resultados</div>
          <Res label="Potência mínima" value={potMin+" kWp"}/>
          <Res label="Potência instalada" value={pot+" kWp"} hi/>
          <Res label="Geração anual" value={ger.toLocaleString("pt-BR")+" kWh"}/>
          <div style={{padding:"9px",borderRadius:8,marginTop:4,textAlign:"center",background:saldo>=0?"#C8E6C9":"#FFCDD2"}}>
            <div style={{fontWeight:800,fontSize:13,color:saldo>=0?"#1B5E20":"#B71C1C"}}>{saldo>=0?"✅ NZEB alcançado":"⚠️ Déficit energético"}</div>
            <div style={{fontSize:11,color:saldo>=0?"#2E7D32":"#C62828",marginTop:2}}>Saldo: {saldo>0?"+":""}{saldo.toLocaleString("pt-BR")} kWh/ano</div>
          </div>
        </Card>
        <Card bg={G.pale}>
          <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:8}}>🔋 Bateria · 💧 Água</div>
          <Res label="Capacidade bateria" value={capBat+" kWh"} hi/>
          <Res label="Captação pluvial" value={captacao+" L/dia"}/>
          <Res label="Consumo água" value={consumoAgua+" L/dia"}/>
          <div style={{padding:"9px",borderRadius:8,marginTop:4,textAlign:"center",background:captacao>=consumoAgua?"#C8E6C9":"#FFCDD2"}}>
            <div style={{fontWeight:700,fontSize:12,color:captacao>=consumoAgua?"#1B5E20":"#B71C1C"}}>{captacao>=consumoAgua?"✅ Autossuficiente em água":"⚠️ Complementar com poço/rede"}</div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function TabMateriais(){
  const [cidade,setCidade]=useState("Petrópolis — RJ");
  const c=CIDADES[cidade];
  const mat=MAT_ZONA[c.zona];
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:10}}>🌍 Recomendação por Clima</div>
        <Sel value={cidade} onChange={setCidade} opts={Object.keys(CIDADES)}/>
        <div style={{padding:"10px",background:mat.cor,borderRadius:10,marginBottom:8}}>
          <div style={{fontWeight:700,fontSize:12,color:G.deep}}>Zona Bioclimática</div>
          <div style={{fontSize:11,color:G.mid,fontWeight:600}}>{mat.l}</div>
          <div style={{fontSize:10,color:G.muted,marginTop:2}}>HPS: {c.hps}h/dia · Prec.: {c.prec}mm/ano</div>
        </div>
        {[["🏗️ Estrutura",mat.e],["🧱 Vedação",mat.v],["🌡️ Isolamento",mat.i],["🏠 Cobertura",mat.c],["🪟 Esquadria",mat.es]].map(([l,v])=>(
          <div key={l} style={{padding:"8px 10px",background:G.gray,borderRadius:8,marginBottom:4}}>
            <div style={{fontSize:10,color:G.muted}}>{l}</div>
            <div style={{fontSize:11,fontWeight:600,color:G.deep}}>{v}</div>
          </div>
        ))}
      </Card>
      <Card>
        <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:10}}>🏆 Top Materiais Sustentáveis</div>
        {[
          ["CLT","Estrutura","CO₂ negativo · FSC","−1,5 kg CO₂e/kg","R$2.200–3.000/m³"],
          ["Hempcrete","Vedação","CO₂ negativo · LEED","−0,4 kg CO₂e/kg","R$150–250/m²"],
          ["Lã PET reciclado","Isolamento","Reciclado pós-consumo","0,03–0,06","R$35–55/m²"],
          ["Vidro duplo","Esquadria","LEED EQ · RTQ-R","1,20–1,60","R$180–320/m²"],
          ["Tadelakt","Revestimento","Zero VOC · WELL","0,45","R$280–420/m²"],
          ["Telhado verde","Cobertura","CO₂ negativo · LEED SS","negativo","R$220–280/m²"],
          ["Bambu Guadua","Estrutura","CO₂ negativo · NBR 16828","−0,8 kg CO₂e/kg","R$80–140/colmo"],
          ["Geopolímero","Estrutura","−70% CO₂ vs. concreto","0,06–0,10","Similar concreto"],
        ].map(([nome,cat,cert,co2,custo])=>(
          <div key={nome} style={{padding:"9px 11px",background:G.gray,borderRadius:8,marginBottom:5,display:"flex",gap:10,alignItems:"center"}}>
            <div style={{flex:1}}>
              <div style={{fontSize:12,fontWeight:700,color:G.deep}}>{nome}</div>
              <div style={{fontSize:10,color:G.muted}}>{cat} · {cert}</div>
            </div>
            <div style={{textAlign:"right"}}>
              <div style={{fontSize:10,color:co2.includes("neg")?"#1B5E20":"#E65100",fontWeight:600}}>{co2}</div>
              <div style={{fontSize:10,color:G.muted}}>{custo}</div>
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
}

function TabOrientacao(){
  const [lat,setLat]=useState(-22.505);
  const [mes,setMes]=useState(7);
  const meses=["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
  const N=[15,46,74,105,135,166,196,227,258,288,319,349][mes-1];
  const decl=+(23.45*Math.sin((Math.PI/180)*(360/365*(284+N)))).toFixed(2);
  const latR=lat*Math.PI/180;
  const ws_=Math.acos(Math.max(-1,Math.min(1,-Math.tan(latR)*Math.tan(decl*Math.PI/180))))*(180/Math.PI);
  const dur=+(2*ws_/15).toFixed(1);
  const alt=+(Math.asin(Math.sin(latR)*Math.sin(decl*Math.PI/180)+Math.cos(latR)*Math.cos(decl*Math.PI/180))*(180/Math.PI)).toFixed(1);
  const hpsAll=meses.map((_,i)=>{
    const nn=[15,46,74,105,135,166,196,227,258,288,319,349][i];
    const dd=23.45*Math.sin((Math.PI/180)*(360/365*(284+nn)));
    const w2=Math.acos(Math.max(-1,Math.min(1,-Math.tan(latR)*Math.tan(dd*Math.PI/180))))*(180/Math.PI);
    return +(2*w2/15*0.4).toFixed(1);
  });
  const maxH=Math.max(...hpsAll);
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:10}}>🌞 Localização</div>
        <Inp label="Latitude" value={lat} onChange={setLat} unit="°" min={-90} max={90} step={0.001} note="Negativo = Hemisfério Sul"/>
        <Sel label="Mês" value={String(mes)} onChange={v=>setMes(+v)} opts={meses.map((m,i)=>({v:String(i+1),l:m}))}/>
        {[["Declinação",decl+"°"],["Duração do dia",dur+"h"],["Altitude solar",alt+"°"],["HPS estimadas",+(dur*0.4).toFixed(1)+"h/dia"],["Inclinação ótima",+Math.abs(lat).toFixed(1)+"°"],["Fachada principal",lat<0?"Norte (0°)":"Sul (180°)"]].map(([l,v])=>(
          <div key={l} style={{display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:`1px solid ${G.border}`,fontSize:12}}>
            <span style={{color:G.muted}}>{l}</span><span style={{fontWeight:700,color:G.deep}}>{v}</span>
          </div>
        ))}
      </Card>
      <Card bg={G.pale}>
        <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:10}}>📊 HPS por mês</div>
        <div style={{display:"flex",gap:2,alignItems:"flex-end",height:80,marginBottom:8}}>
          {hpsAll.map((h,i)=>(
            <div key={i} style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",gap:1}}>
              <div style={{fontSize:7,color:i===mes-1?G.deep:G.muted,fontWeight:i===mes-1?700:400}}>{h}</div>
              <div style={{width:"100%",height:Math.round((h/maxH)*64),background:i===mes-1?G.deep:G.sage,borderRadius:"2px 2px 0 0"}}/>
              <div style={{fontSize:7,color:i===mes-1?G.deep:G.muted,fontWeight:i===mes-1?700:400}}>{meses[i]}</div>
            </div>
          ))}
        </div>
        {[["Norte","40–60% · beiral 80–100cm · solar passivo"],["Sul","15–25% · luz difusa"],["Leste","20–30% · brise vertical"],["Oeste","≤20% · máxima proteção"]].map(([f,d])=>(
          <div key={f} style={{padding:"7px 10px",background:G.white,borderRadius:7,marginBottom:4,border:`1px solid ${G.border}`}}>
            <span style={{fontSize:11,fontWeight:700,color:G.deep}}>{f}: </span>
            <span style={{fontSize:11,color:G.ink}}>{d}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}

function TabCerts(){
  const [cert,setCert]=useState("leed");
  const [status,setStatus]=useState({});
  const certAtual=CERTS[cert];
  const pctMap={};
  Object.keys(CERTS).forEach(k=>{
    const t=CERTS[k].criterios.length;
    const ok=CERTS[k].criterios.filter(c=>status[k+"_"+c.campo]==="✅ Atende").length;
    pctMap[k]=Math.round((ok/t)*100);
  });
  const counts=STATUS_OPTS.reduce((a,o)=>({...a,[o]:certAtual.criterios.filter(c=>status[cert+"_"+c.campo]===o).length}),{});
  return(
    <div style={{display:"grid",gridTemplateColumns:"180px 1fr",gap:14}}>
      <div style={{display:"flex",flexDirection:"column",gap:6}}>
        {Object.entries(CERTS).map(([k,c])=>(
          <button key={k} onClick={()=>setCert(k)} style={{padding:"10px 12px",borderRadius:10,border:`1px solid ${cert===k?c.cor:G.border}`,background:cert===k?c.cor+"12":G.white,cursor:"pointer",textAlign:"left",fontFamily:"inherit"}}>
            <div style={{fontSize:11,fontWeight:700,color:cert===k?c.cor:G.ink,marginBottom:3}}>{c.nome}</div>
            <div style={{height:3,background:G.gray,borderRadius:2,overflow:"hidden"}}><div style={{height:"100%",width:pctMap[k]+"%",background:c.cor,transition:"width 0.3s"}}/></div>
            <div style={{fontSize:10,color:G.muted,marginTop:2}}>{pctMap[k]}%</div>
          </button>
        ))}
      </div>
      <Card>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:10}}>
          <div><div style={{fontWeight:700,fontSize:13,color:G.deep}}>{certAtual.nome}</div><div style={{fontSize:11,color:G.muted}}>{certAtual.criterios.length} critérios</div></div>
          <div style={{padding:"6px 12px",background:certAtual.cor+"15",borderRadius:10,textAlign:"center"}}><div style={{fontSize:20,fontWeight:800,color:certAtual.cor}}>{pctMap[cert]}%</div><div style={{fontSize:9,color:G.muted}}>atendido</div></div>
        </div>
        <div style={{height:5,background:G.gray,borderRadius:3,marginBottom:10,overflow:"hidden"}}><div style={{height:"100%",width:pctMap[cert]+"%",background:certAtual.cor,transition:"width 0.4s"}}/></div>
        {certAtual.criterios.map(c=>{
          const key=cert+"_"+c.campo; const val=status[key]||"";
          return(<div key={c.campo} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"8px 10px",borderRadius:7,marginBottom:4,gap:8,background:STATUS_BG[val]||G.gray,border:`1px solid ${val?STATUS_BG[val]:G.border}`}}>
            <span style={{fontSize:12,color:G.ink,flex:1}}>{c.req}</span>
            <select value={val} onChange={e=>setStatus(s=>({...s,[key]:e.target.value}))} style={{padding:"3px 7px",borderRadius:6,border:`1px solid ${G.border}`,fontSize:11,fontFamily:"inherit",cursor:"pointer",background:STATUS_BG[val]||G.white,minWidth:120}}>
              <option value="">— selecionar —</option>
              {STATUS_OPTS.map(o=><option key={o} value={o}>{o}</option>)}
            </select>
          </div>);
        })}
        <div style={{display:"flex",gap:5,marginTop:8,flexWrap:"wrap"}}>
          {STATUS_OPTS.map(o=><div key={o} style={{padding:"2px 8px",borderRadius:14,fontSize:11,fontWeight:600,background:STATUS_BG[o]}}>{o}: {counts[o]||0}</div>)}
        </div>
      </Card>
    </div>
  );
}

function TabAcabamentos(){
  const [tipo,setTipo]=useState("tadelakt");
  const [area,setArea]=useState(12);
  const [aplic,setAplic]=useState("prof");
  const ac=ACABAMENTOS[tipo];
  const mat=(ac.matM2+ac.base)*area;
  const mo=aplic==="diy"?0:ac.moM2*area;
  const total=mat+ac.ferramentas+mo;
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:10}}>🎨 Acabamento</div>
        {Object.entries(ACABAMENTOS).map(([k,a])=>(
          <button key={k} onClick={()=>setTipo(k)} style={{display:"flex",justifyContent:"space-between",width:"100%",padding:"9px 12px",borderRadius:9,marginBottom:5,textAlign:"left",cursor:"pointer",fontFamily:"inherit",border:`1px solid ${tipo===k?G.deep:G.border}`,background:tipo===k?G.pale:G.white}}>
            <span style={{fontSize:12,fontWeight:tipo===k?700:400,color:tipo===k?G.deep:G.ink}}>{a.nome}</span>
            <span style={{fontSize:11,color:G.muted}}>~R${a.matM2}/m²</span>
          </button>
        ))}
        <Inp label="Área (m²)" value={area} onChange={setArea} unit="m²" min={1} max={2000}/>
        <div style={{display:"flex",gap:6}}>
          {[["prof","Profissional"],["diy","DIY"]].map(([v,l])=>(
            <button key={v} onClick={()=>setAplic(v)} style={{flex:1,padding:"6px",borderRadius:7,border:`1px solid ${aplic===v?G.deep:G.border}`,background:aplic===v?G.pale:G.white,color:aplic===v?G.deep:G.muted,fontWeight:aplic===v?700:400,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>{l}</button>
          ))}
        </div>
      </Card>
      <Card bg={G.pale}>
        <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:8}}>💰 Orçamento</div>
        {[["Material + base","R$ "+mat.toLocaleString("pt-BR",{minimumFractionDigits:0})],["Ferramentas","R$ "+ac.ferramentas.toLocaleString("pt-BR")],["Mão de obra",aplic==="diy"?"R$ 0 (DIY)":"R$ "+mo.toLocaleString("pt-BR")]].map(([l,v])=>(
          <Res key={l} label={l} value={v}/>
        ))}
        <div style={{padding:"12px",background:G.deep,borderRadius:10,marginTop:8,textAlign:"center"}}>
          <div style={{fontSize:10,color:G.sage,marginBottom:1}}>TOTAL</div>
          <div style={{fontSize:24,fontWeight:800,color:G.white}}>R$ {total.toLocaleString("pt-BR",{minimumFractionDigits:0})}</div>
          <div style={{fontSize:11,color:"rgba(255,255,255,0.6)",marginTop:1}}>R$ {Math.round(total/area).toLocaleString("pt-BR")}/m²</div>
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
      <Card style={{marginBottom:10,padding:"11px 14px"}}>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:5}}>
          <div style={{fontWeight:700,fontSize:13,color:G.ink}}>✅ {total} itens · 5 fases</div>
          <div style={{fontWeight:800,fontSize:16,color:G.mid}}>{done}/{total} ({pct}%)</div>
        </div>
        <div style={{height:6,background:G.gray,borderRadius:3,overflow:"hidden"}}><div style={{height:"100%",width:pct+"%",background:pct===100?"#2E7D32":G.mid,borderRadius:3,transition:"width 0.4s"}}/></div>
      </Card>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        {CHECKLIST.map((f,fi)=>(
          <Card key={f.fase} style={{padding:"12px 14px"}}>
            <div style={{fontWeight:700,fontSize:11,color:f.cor,marginBottom:6}}>{f.fase}</div>
            {f.itens.map((item,ii)=>{
              const key=fi+"_"+ii; const d=checks[key];
              return(<div key={ii} onClick={()=>toggle(key)} style={{display:"flex",gap:6,alignItems:"flex-start",padding:"6px 7px",borderRadius:7,marginBottom:3,cursor:"pointer",background:d?"#C8E6C9":G.gray,border:`1px solid ${d?"#81C784":G.border}`,transition:"all 0.15s"}}>
                <div style={{width:13,height:13,borderRadius:3,flexShrink:0,marginTop:1,background:d?G.mid:"transparent",border:`2px solid ${d?G.mid:G.border}`,display:"flex",alignItems:"center",justifyContent:"center"}}>{d&&<span style={{color:G.white,fontSize:8}}>✓</span>}</div>
                <span style={{fontSize:11,color:d?"#1B5E20":G.ink,textDecoration:d?"line-through":"none",lineHeight:1.4}}>{item}</span>
              </div>);
            })}
          </Card>
        ))}
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
          <button key={x.id} onClick={()=>setSel(x.id)} style={{flex:1,padding:"11px",borderRadius:12,border:`2px solid ${sel===x.id?G.deep:G.border}`,background:sel===x.id?G.pale:G.white,cursor:"pointer",textAlign:"center",fontFamily:"inherit",transition:"all 0.2s"}}>
            <div style={{fontSize:18,marginBottom:3}}>{x.icon}</div>
            <div style={{fontSize:11,fontWeight:700,color:sel===x.id?G.deep:G.ink}}>{x.nome}</div>
            <div style={{fontSize:10,color:G.muted}}>{x.escala}</div>
          </button>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
        <Card bg={m.cor}>
          <div style={{fontWeight:700,fontSize:14,color:G.ink,marginBottom:10}}>{m.icon} {m.nome}</div>
          {[["Escala",m.escala],["Solar",m.solar],["Certificação",m.cert]].map(([l,v])=>(
            <div key={l} style={{padding:"8px 10px",background:"rgba(255,255,255,0.7)",borderRadius:8,marginBottom:5}}>
              <div style={{fontSize:10,color:G.muted}}>{l}</div>
              <div style={{fontSize:13,fontWeight:700,color:G.ink}}>{v}</div>
            </div>
          ))}
        </Card>
        <Card>
          <div style={{fontWeight:700,color:G.deep,fontSize:12,marginBottom:8}}>📋 Próximos passos</div>
          {["Definir terreno e verificar zoneamento","Registrar no LEED Arc ou EDGE","Contratar equipe técnica","Elaborar PGRCC","Solicitar LPLS e licença INEA"].map((p,i)=>(
            <div key={i} style={{fontSize:11,padding:"5px 0",borderBottom:`1px solid ${G.border}`,color:G.ink}}>{i+1}. {p}</div>
          ))}
          <div style={{marginTop:8,padding:"8px",background:G.pale,borderRadius:7,fontSize:11,color:G.mid,fontStyle:"italic"}}>
            Recomendação: começar pelo Chalé Individual como prova de conceito do SustainKit.
          </div>
        </Card>
      </div>
    </div>
  );
}

function TabAgro(){
  const [cargas,setCargas]=useState(AGRO_C.map(c=>({...c})));
  const [hps,setHps]=useState(4.5);
  const totalKwh=+(cargas.filter(c=>c.ativo).reduce((a,c)=>a+c.potencia*c.horas,0)/1000).toFixed(1);
  const potMin=+(totalKwh/(hps*0.75)).toFixed(1);
  const capBat=Math.round((totalKwh*2)/0.80*1.2);
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:4}}>🌾 Diagnóstico Agro</div>
        <div style={{fontSize:11,color:G.muted,marginBottom:8}}>Marque os equipamentos presentes:</div>
        {cargas.map((c,i)=>(
          <div key={i} onClick={()=>setCargas(cs=>cs.map((x,j)=>j===i?{...x,ativo:!x.ativo}:x))}
            style={{display:"flex",gap:7,alignItems:"center",padding:"7px 9px",borderRadius:8,marginBottom:4,cursor:"pointer",background:c.ativo?G.pale:G.gray,border:`1px solid ${c.ativo?G.sage:G.border}`,transition:"all 0.15s"}}>
            <div style={{width:13,height:13,borderRadius:3,background:c.ativo?G.mid:"transparent",border:`2px solid ${c.ativo?G.mid:G.border}`,display:"flex",alignItems:"center",justifyContent:"center"}}>{c.ativo&&<span style={{color:G.white,fontSize:8}}>✓</span>}</div>
            <span style={{fontSize:11,flex:1,color:c.ativo?G.deep:G.muted,fontWeight:c.ativo?600:400}}>{c.nome}</span>
            <span style={{fontSize:10,color:G.muted}}>{(c.potencia*c.horas/1000).toFixed(1)} kWh</span>
          </div>
        ))}
        <Inp label="HPS local (pior mês)" value={hps} onChange={setHps} unit="h/dia" min={1} max={8} step={0.1}/>
      </Card>
      <div style={{display:"flex",flexDirection:"column",gap:10}}>
        <Card bg={G.pale}>
          <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:8}}>📊 Sistema Solar Agro</div>
          <Res label="Consumo diário" value={totalKwh+" kWh"}/>
          <Res label="Potência FV mínima" value={potMin+" kWp"} hi/>
          <Res label="Bateria (48h autonomia)" value={capBat+" kWh"} hi/>
        </Card>
        <Card>
          <div style={{fontWeight:700,color:G.deep,fontSize:13,marginBottom:8}}>🌱 AgriPV — Culturas</div>
          {[["🍓 Morango","★★★★★","Ideal altitude · melhora qualidade"],["🥬 Alface","★★★★★","Evita espigamento"],["☕ Café","★★★★☆","30–40% sombra OK"],["🌾 Soja/Milho","★★☆☆☆","Não recomendado"]].map(([nome,compat,nota])=>{
            const s=compat.replace(/☆/g,"").length;
            return(<div key={nome} style={{padding:"7px 9px",background:s>=4?"#C8E6C9":s>=3?"#FFF9C4":"#FFE0B2",borderRadius:7,marginBottom:4}}>
              <div style={{display:"flex",justifyContent:"space-between"}}><span style={{fontSize:12,fontWeight:600,color:G.ink}}>{nome}</span><span style={{fontSize:11,color:s>=4?"#1B5E20":"#E65100"}}>{compat}</span></div>
              <div style={{fontSize:10,color:G.muted,marginTop:1}}>{nota}</div>
            </div>);
          })}
          <div style={{fontSize:10,color:G.muted,fontStyle:"italic",marginTop:4}}>LER médio: 1,3–1,7 · Fraunhofer ISE 2023</div>
        </Card>
      </div>
    </div>
  );
}

const TABS=[
  {id:"solar",icon:"☀️",label:"Energia + Água",comp:TabSolar},
  {id:"mat",icon:"🧱",label:"Materiais",comp:TabMateriais},
  {id:"ori",icon:"🌞",label:"Orientação Solar",comp:TabOrientacao},
  {id:"certs",icon:"🔍",label:"Certificações",comp:TabCerts},
  {id:"acab",icon:"🎨",label:"Acabamentos",comp:TabAcabamentos},
  {id:"check",icon:"✅",label:"Checklist",comp:TabChecklist},
  {id:"modelos",icon:"💼",label:"Modelos Negócio",comp:TabModelos},
  {id:"agro",icon:"🌾",label:"Agro Solar",comp:TabAgro},
];

export default function App(){
  const [tab,setTab]=useState("solar");
  const Tab=TABS.find(t=>t.id===tab).comp;
  return(
    <div style={{fontFamily:"-apple-system,'Segoe UI',Arial,sans-serif",background:G.gray,minHeight:"100vh",display:"flex",flexDirection:"column"}}>
      <div style={{background:G.deep,padding:"13px 20px 0",flexShrink:0}}>
        <div style={{maxWidth:1000,margin:"0 auto"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12}}>
            <div style={{display:"flex",alignItems:"center",gap:10}}>
              <div style={{width:32,height:32,borderRadius:"50%",background:G.sage,display:"flex",alignItems:"center",justifyContent:"center",fontSize:17}}>🌿</div>
              <div>
                <div style={{fontWeight:800,fontSize:16,color:G.white,letterSpacing:"-0.02em"}}>Physis SustainKit</div>
                <div style={{fontSize:10,color:G.sage}}>Versão Completa · LEED v5 · PVGIS ERA5 · Physis Engineering</div>
              </div>
            </div>
            <div style={{background:G.sage+"22",border:`1px solid ${G.sage}44`,borderRadius:6,padding:"3px 11px",fontSize:11,fontWeight:700,color:G.sage}}>VERSÃO COMPLETA</div>
          </div>
          <div style={{display:"flex",overflowX:"auto",gap:1}}>
            {TABS.map(t=>(
              <button key={t.id} onClick={()=>setTab(t.id)} style={{padding:"8px 13px",border:"none",background:"transparent",cursor:"pointer",color:tab===t.id?G.white:G.sage+"88",fontWeight:tab===t.id?700:400,fontSize:12,fontFamily:"inherit",borderBottom:tab===t.id?`2px solid ${G.sage}`:"2px solid transparent",transition:"all 0.2s",display:"flex",alignItems:"center",gap:4,whiteSpace:"nowrap"}}>
                <span>{t.icon}</span>{t.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div style={{flex:1,overflowY:"auto",padding:"14px"}}>
        <div style={{maxWidth:1000,margin:"0 auto"}}><Tab/></div>
      </div>
      <div style={{background:G.white,borderTop:`1px solid ${G.border}`,padding:"7px 20px",display:"flex",justifyContent:"space-between",alignItems:"center",flexShrink:0}}>
        <div style={{fontSize:10,color:G.muted}}>Physis Engineering · ASHRAE · ABNT NBR · PVGIS ERA5 · LEED v5 · FAO · EMBRAPA</div>
        <div style={{fontSize:11,color:G.mid,fontWeight:600}}>physis.com.br</div>
      </div>
    </div>
  );
}
