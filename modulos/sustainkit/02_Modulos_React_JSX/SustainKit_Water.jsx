import { useState } from "react";

const C = {
  main:"#006064", light:"#E0F7FA", mid:"#00838F", pale:"#E0F7FA",
  white:"#FFFFFF", ink:"#1C2B22", gray:"#F4F7F4", border:"#B2EBF2",
  muted:"#6B7F6E",
};

const CIDADES_PREC = {
  "Petrópolis — RJ":1520,"Rio de Janeiro — RJ":1200,"São Paulo — SP":1400,
  "Brasília — DF":1500,"Belo Horizonte — MG":1500,"Curitiba — PR":1400,
  "Salvador — BA":1900,"João Pessoa — PB":1700,"Manaus — AM":2200,
};

const CULTURAS = [
  {nome:"Alface / Rúcula",et:3.5,pe:1.5,ef:0.90,kc:"0,7–1,0"},
  {nome:"Tomate",et:5.0,pe:1.5,ef:0.85,kc:"0,6–1,15"},
  {nome:"Milho (grão)",et:4.5,pe:2.0,ef:0.75,kc:"0,3–1,2"},
  {nome:"Feijão",et:4.0,pe:1.5,ef:0.80,kc:"0,4–1,1"},
  {nome:"Pastagem",et:3.0,pe:2.0,ef:0.70,kc:"0,85"},
  {nome:"Café",et:4.5,pe:1.8,ef:0.85,kc:"0,9–1,05"},
  {nome:"Cana-de-açúcar",et:5.0,pe:2.0,ef:0.75,kc:"0,4–1,25"},
];

const RESIDUOS_BIOGAS = [
  {nome:"Esterco bovino (corte)",qtdPorCab:10,biogas:0.30,ch4:60},
  {nome:"Esterco bovino (leite)",qtdPorCab:15,biogas:0.35,ch4:60},
  {nome:"Esterco suíno",qtdPorCab:2.5,biogas:0.45,ch4:65},
  {nome:"Esterco avícola",qtdPorCab:0.15,biogas:0.50,ch4:60},
  {nome:"Resíduo de silagem (kg)",qtdPorCab:1,biogas:0.35,ch4:55},
];

function Card({children,style={},bg=C.white}){
  return <div style={{background:bg,border:`1px solid ${C.border}`,borderRadius:12,
    padding:"16px 18px",boxShadow:"0 2px 10px rgba(0,96,100,0.07)",...style}}>{children}</div>;
}
function Lbl({children}){return <div style={{fontSize:11,fontWeight:600,color:C.ink,marginBottom:4}}>{children}</div>;}
function Inp({label,value,onChange,unit,min=0,max=9999,step=1,note}){
  return <div style={{marginBottom:11}}>
    {label&&<Lbl>{label}</Lbl>}
    <div style={{display:"flex",gap:6,alignItems:"center"}}>
      <input type="number" value={value} min={min} max={max} step={step}
        onChange={e=>onChange(+e.target.value)}
        style={{flex:1,padding:"7px 10px",border:`2px solid ${C.border}`,borderRadius:8,
          fontSize:14,fontWeight:700,color:C.main,background:C.pale,fontFamily:"inherit",outline:"none"}}/>
      {unit&&<span style={{fontSize:11,color:C.muted,minWidth:36}}>{unit}</span>}
    </div>
    {note&&<div style={{fontSize:10,color:C.muted,marginTop:2,fontStyle:"italic"}}>{note}</div>}
  </div>;
}
function Sel({label,value,onChange,opts}){
  return <div style={{marginBottom:11}}>
    {label&&<Lbl>{label}</Lbl>}
    <select value={value} onChange={e=>onChange(e.target.value)}
      style={{width:"100%",padding:"7px 10px",border:`2px solid ${C.border}`,borderRadius:8,
        background:C.pale,fontSize:12,color:C.main,fontWeight:600,fontFamily:"inherit"}}>
      {opts.map(o=><option key={typeof o==="string"?o:o.v} value={typeof o==="string"?o:o.v}>
        {typeof o==="string"?o:o.l}</option>)}
    </select>
  </div>;
}
function Res({label,value,hi=false}){
  return <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",
    padding:"8px 11px",background:hi?C.pale:C.gray,borderRadius:8,marginBottom:5,
    border:hi?`1px solid ${C.border}`:"none"}}>
    <span style={{fontSize:12,color:C.ink}}>{label}</span>
    <span style={{fontSize:14,fontWeight:800,color:hi?C.main:C.ink}}>{value}</span>
  </div>;
}
function TabBtn({label,icon,active,onClick}){
  return <button onClick={onClick} style={{padding:"9px 16px",border:"none",background:"transparent",
    cursor:"pointer",color:active?C.white:C.main+"99",fontWeight:active?700:400,fontSize:12,
    fontFamily:"inherit",borderBottom:active?`2px solid ${C.white}`:"2px solid transparent",
    display:"flex",alignItems:"center",gap:5,whiteSpace:"nowrap"}}>
    <span>{icon}</span>{label}
  </button>;
}

function TabCaptacao(){
  const [cidade,setCidade]=useState("Petrópolis — RJ");
  const [area,setArea]=useState(84);
  const [coef,setCoef]=useState(0.85);
  const [pessoas,setPessoas]=useState(2);
  const [reserva,setReserva]=useState(60);
  const prec=CIDADES_PREC[cidade]||1200;
  const captAnual=+(prec/1000*area*coef).toFixed(0);
  const captDia=+(captAnual/365).toFixed(0);
  const consumoDia=pessoas*130;
  const saldo=captDia-consumoDia;
  const cisterna=consumoDia*reserva;
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:12,fontSize:13}}>💧 Parâmetros do sistema</div>
        <Sel label="Cidade / localização" value={cidade} onChange={setCidade} opts={Object.keys(CIDADES_PREC)}/>
        <Inp label="Área de captação (telhado)" value={area} onChange={setArea} unit="m²" min={10} max={5000}/>
        <Sel label="Coeficiente de escoamento" value={String(coef)} onChange={v=>setCoef(+v)}
          opts={[{v:"0.85",l:"Telha metálica: 0,85"},{v:"0.80",l:"Fibrocimento: 0,80"},
            {v:"0.75",l:"Telha cerâmica: 0,75"},{v:"0.40",l:"Telhado verde: 0,40"}]}/>
        <Inp label="Número de ocupantes" value={pessoas} onChange={setPessoas} unit="pessoas" min={1} max={200}/>
        <Inp label="Dias de reserva na cisterna" value={reserva} onChange={setReserva} unit="dias" min={7} max={180}
          note="Recomendado: 30–60 dias. Semiárido: 90 dias"/>
        <div style={{fontSize:10,color:C.muted,fontStyle:"italic",padding:"7px",background:C.gray,borderRadius:6}}>
          Precipitação local: {prec}mm/ano · ABNT NBR 15527:2007
        </div>
      </Card>
      <div style={{display:"flex",flexDirection:"column",gap:10}}>
        <Card bg={C.pale}>
          <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>📊 Balanço Hídrico</div>
          <Res label="Volume captado anual" value={captAnual.toLocaleString("pt-BR")+" L"}/>
          <Res label="Captação diária média" value={captDia+" L/dia"} hi/>
          <Res label="Consumo diário (130 L/p)" value={consumoDia+" L/dia"}/>
          <Res label="Saldo hídrico diário" value={(saldo>0?"+":"")+saldo+" L/dia"} hi/>
          <Res label="Cisterna mínima recomendada" value={Math.round(cisterna/1000)+" m³ ("+cisterna.toLocaleString("pt-BR")+" L)"}/>
          <div style={{padding:"10px",borderRadius:8,marginTop:4,textAlign:"center",
            background:saldo>=0?"#C8E6C9":"#FFCDD2"}}>
            <div style={{fontWeight:800,fontSize:13,color:saldo>=0?"#1B5E20":"#B71C1C"}}>
              {saldo>=0?"✅ Sistema autossuficiente":"⚠️ Complementar com poço ou rede"}
            </div>
          </div>
        </Card>
        <Card>
          <div style={{fontWeight:700,color:C.main,marginBottom:8,fontSize:12}}>🔧 Componentes recomendados</div>
          {[["Cisterna","Polietileno ou concreto armado · enterrada · tampa hermética"],
            ["Filtro 1° chuva","Descarta primeiros 2mm · remove folhas e contaminantes"],
            ["Filtro grosso","Tela inox 200μm na entrada da cisterna"],
            ["Purificação","UV 25W + ozônio para água potável · custo ~R$50/mês"],
            ["Bomba","Pressurizadora 300W DC · acionamento por demanda"]].map(([c,d])=>(
            <div key={c} style={{fontSize:11,padding:"5px 0",borderBottom:`1px solid ${C.border}`}}>
              <strong style={{color:C.main}}>{c}:</strong> <span style={{color:C.ink}}>{d}</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

function TabDemandas(){
  const [pessoas,setPessoas]=useState(2);
  const [tipo,setTipo]=useState("chale");
  const mult={"chale":1.0,"hotel":1.3,"residencial":0.85}[tipo]||1;
  const agua=[
    ["Beber e cozinhar",4],["Banho e higiene",55],["Descarga (vaso)",35],
    ["Limpeza",20],["Lavanderia",15],["Irrigação horta",10],
  ];
  const totalPerCapita=agua.reduce((a,[,v])=>a+v,0);
  const totalDia=Math.round(totalPerCapita*pessoas*mult);
  const esgoto=[
    ["Águas negras (30%)","Biodigestor → digestato fertilizante"],
    ["Águas cinzas (60%)","Wetland construído → reúso irrigação"],
    ["Perdas/evaporação (10%)","Evaporação natural"],
  ];
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:12,fontSize:13}}>👤 Demandas por pessoa</div>
        <Inp label="Número de ocupantes" value={pessoas} onChange={setPessoas} unit="pessoas" min={1} max={100}/>
        <Sel label="Tipo de uso" value={tipo} onChange={setTipo}
          opts={[{v:"chale",l:"Glamping / Chalé"},{v:"hotel",l:"Hotel (×1,3)"},{v:"residencial",l:"Residencial (×0,85)"}]}/>
        <div style={{marginTop:8}}>
          {agua.map(([cat,val])=>(
            <div key={cat} style={{display:"flex",justifyContent:"space-between",alignItems:"center",
              padding:"7px 10px",background:C.gray,borderRadius:7,marginBottom:5}}>
              <span style={{fontSize:12,color:C.ink}}>{cat}</span>
              <div style={{textAlign:"right"}}>
                <div style={{fontSize:12,fontWeight:700,color:C.main}}>{val} L/p/dia</div>
                <div style={{fontSize:10,color:C.muted}}>{Math.round(val*pessoas*mult)} L total</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{padding:"10px",background:C.pale,borderRadius:8,marginTop:4}}>
          <div style={{display:"flex",justifyContent:"space-between",fontWeight:800,color:C.main,fontSize:14}}>
            <span>TOTAL / DIA</span><span>{totalDia} L/dia</span>
          </div>
          <div style={{fontSize:10,color:C.muted,marginTop:2}}>
            {totalPerCapita} L/p/dia × {pessoas} pessoas × fator {mult}
          </div>
        </div>
      </Card>
      <div style={{display:"flex",flexDirection:"column",gap:10}}>
        <Card bg={C.pale}>
          <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>🚿 Tratamento de Esgoto</div>
          {esgoto.map(([tipo_,dest])=>(
            <div key={tipo_} style={{padding:"10px 12px",background:C.white,borderRadius:8,marginBottom:6,
              border:`1px solid ${C.border}`}}>
              <div style={{fontSize:12,fontWeight:600,color:C.main,marginBottom:2}}>{tipo_}</div>
              <div style={{fontSize:10,color:C.muted}}>{dest}</div>
            </div>
          ))}
          <div style={{fontSize:10,color:C.muted,marginTop:4,fontStyle:"italic"}}>
            Normas: ABNT NBR 7229:1993 (fossas) + NBR 13969:1997 (tratamento complementar)
          </div>
        </Card>
        <Card>
          <div style={{fontWeight:700,color:C.main,marginBottom:8,fontSize:12}}>🌿 Horta por pessoa</div>
          {[["Alface/Rúcula","2 m²/pessoa · 4L/m²/dia · ciclo 30–45 dias"],
            ["Tomate","1,5 m²/pessoa · 5L/m²/dia · 2 safras/ano"],
            ["Ervas aromáticas","0,5 m²/pessoa · 3L/m²/dia · colheita contínua"],
            ["Morango (altitude)","1,5 m²/pessoa · ideal Petrópolis"]].map(([c,d])=>(
            <div key={c} style={{fontSize:11,padding:"5px 0",borderBottom:`1px solid ${C.border}`}}>
              <strong style={{color:C.main}}>{c}:</strong> <span style={{color:C.ink}}>{d}</span>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

function TabBiogas(){
  const [animais,setAnimais]=useState(RESIDUOS_BIOGAS.map(r=>({...r,qtd:0})));
  const totalBiogas=animais.reduce((a,r)=>a+(r.qtd*r.qtdPorCab*r.biogas),0);
  const totalEnerg=+(totalBiogas*5.5).toFixed(1);
  const trh=30;
  const volBiodig=+(totalBiogas*trh).toFixed(1);
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:12,fontSize:13}}>🐄 Diagnóstico de Resíduos</div>
        <div style={{fontSize:11,color:C.muted,marginBottom:10}}>Insira o número de animais/quantidade:</div>
        {animais.map((r,i)=>(
          <div key={i} style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
            <span style={{fontSize:12,flex:1,color:C.ink}}>{r.nome}</span>
            <input type="number" value={r.qtd} min={0} max={10000}
              onChange={e=>setAnimais(a=>a.map((x,j)=>j===i?{...x,qtd:+e.target.value}:x))}
              style={{width:70,padding:"5px 8px",border:`2px solid ${C.border}`,borderRadius:7,
                fontSize:13,fontWeight:700,color:C.main,background:C.pale,
                fontFamily:"inherit",textAlign:"center",outline:"none"}}/>
            <span style={{fontSize:10,color:C.muted,minWidth:55,textAlign:"right"}}>
              {+(r.qtd*r.qtdPorCab*r.biogas).toFixed(2)} m³/dia
            </span>
          </div>
        ))}
      </Card>
      <div style={{display:"flex",flexDirection:"column",gap:10}}>
        <Card bg={C.pale}>
          <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>📊 Potencial de Biogás</div>
          <Res label="Produção diária de biogás" value={totalBiogas.toFixed(2)+" m³/dia"} hi/>
          <Res label="Energia equivalente" value={totalEnerg+" kWh/dia"}/>
          <Res label="Volume do biodigestor (TRH 30d)" value={volBiodig+" m³"}/>
          <Res label="Gasômetro recomendado (20%)" value={+(totalBiogas*0.2).toFixed(2)+" m³"}/>
          <div style={{marginTop:8,padding:"10px",background:C.white,borderRadius:8,border:`1px solid ${C.border}`}}>
            <div style={{fontSize:11,fontWeight:700,color:C.main,marginBottom:6}}>Usos do biogás na propriedade</div>
            {[["🍳 Cocção","0,3–0,5 m³/refeição · substitui GLP"],
              ["🚿 Aquecimento água","0,2–0,4 m³/banho · eficiência 85%"],
              ["⚡ Geração elétrica","0,6–0,7 m³/kWh · motogerador backup"],
              ["🌱 Digestato","Fertilizante NPK orgânico · -40–60% adubo químico"]].map(([ico,d])=>(
              <div key={ico} style={{fontSize:10,padding:"4px 0",borderBottom:`1px solid ${C.border}`,color:C.ink}}>
                {ico} {d}
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <div style={{fontSize:11,color:C.muted,fontStyle:"italic"}}>
            Norma: ABNT NBR 7229:1993 · Fonte: EMBRAPA Suínos e Aves · PCI biogás: 5,5 kWh/m³ (60% CH₄)
          </div>
        </Card>
      </div>
    </div>
  );
}

function TabIrrigacao(){
  const [cultura,setCultura]=useState(0);
  const [area,setArea]=useState(1);
  const c=CULTURAS[cultura];
  const ni=+(c.et-c.pe).toFixed(1);
  const lpd=+(ni/c.ef*10).toFixed(1);
  const totalDia=+(lpd*area*10000/1000).toFixed(0);
  const vazao=+(totalDia/8/1000).toFixed(2);
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:12,fontSize:13}}>🌱 Dimensionamento de Irrigação</div>
        <Sel label="Cultura" value={String(cultura)} onChange={v=>setCultura(+v)}
          opts={CULTURAS.map((c,i)=>({v:String(i),l:c.nome}))}/>
        <Inp label="Área irrigada" value={area} onChange={setArea} unit="ha" min={0.1} max={1000} step={0.1}/>
        <div style={{padding:"10px",background:C.pale,borderRadius:8,marginTop:4}}>
          <div style={{fontSize:11,fontWeight:700,color:C.main,marginBottom:6}}>Parâmetros FAO Penman-Monteith</div>
          {[["Evapotranspiração (ETc)",c.et+" mm/dia"],["Precipitação efetiva",c.pe+" mm/dia"],
            ["Necessidade líquida irrigação",ni+" mm/dia"],["Eficiência do sistema",(c.ef*100).toFixed(0)+"%"],
            ["Kc (coeficiente cultura)",c.kc]].map(([l,v])=>(
            <div key={l} style={{display:"flex",justifyContent:"space-between",
              padding:"5px 0",borderBottom:`1px solid ${C.border}`,fontSize:11}}>
              <span style={{color:C.muted}}>{l}</span>
              <span style={{fontWeight:700,color:C.main}}>{v}</span>
            </div>
          ))}
        </div>
      </Card>
      <Card bg={C.pale}>
        <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>📊 Necessidade Hídrica</div>
        <Res label="Lâmina de irrigação" value={lpd+" L/m²/dia"} hi/>
        <Res label="Volume total diário" value={totalDia.toLocaleString("pt-BR")+" L/dia"} hi/>
        <Res label="Vazão necessária (8h/dia)" value={vazao+" m³/h"}/>
        <div style={{marginTop:10,padding:"10px",background:C.white,borderRadius:8,border:`1px solid ${C.border}`}}>
          <div style={{fontSize:11,fontWeight:700,color:C.main,marginBottom:6}}>Métodos de irrigação</div>
          {[["Gotejamento","90–95% ef. · 10–15m pressão · RECOMENDADO"],
            ["Microaspersão","75–85% ef. · 15–25m pressão"],
            ["Aspersão","65–75% ef. · 25–40m pressão"]].map(([m,d])=>(
            <div key={m} style={{fontSize:10,padding:"5px 0",borderBottom:`1px solid ${C.border}`,color:C.ink}}>
              <strong style={{color:C.main}}>{m}:</strong> {d}
            </div>
          ))}
        </div>
        <div style={{fontSize:10,color:C.muted,marginTop:8,fontStyle:"italic"}}>
          Fonte: FAO Irrigation Manual + FAO Paper 56 (Penman-Monteith)
        </div>
      </Card>
    </div>
  );
}

const TABS=[
  {id:"cap",icon:"🌧️",label:"Captação Pluvial",comp:TabCaptacao},
  {id:"dem",icon:"👤",label:"Demandas",comp:TabDemandas},
  {id:"bio",icon:"🐄",label:"Biogás",comp:TabBiogas},
  {id:"irr",icon:"🌱",label:"Irrigação",comp:TabIrrigacao},
];

export default function App(){
  const [tab,setTab]=useState("cap");
  const Tab=TABS.find(t=>t.id===tab).comp;
  return(
    <div style={{fontFamily:"-apple-system,'Segoe UI',Arial,sans-serif",background:"#E0F7FA",minHeight:"100vh"}}>
      <div style={{background:C.main,padding:"14px 20px 0"}}>
        <div style={{maxWidth:900,margin:"0 auto"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
            <div style={{display:"flex",alignItems:"center",gap:10}}>
              <div style={{width:32,height:32,borderRadius:"50%",background:"rgba(255,255,255,0.2)",
                display:"flex",alignItems:"center",justifyContent:"center",fontSize:16}}>💧</div>
              <div>
                <div style={{fontWeight:800,fontSize:16,color:C.white}}>SustainKit Water</div>
                <div style={{fontSize:10,color:"rgba(255,255,255,0.7)"}}>Physis Engineering · Água, Esgoto, Biogás e Irrigação</div>
              </div>
            </div>
            <div style={{background:"rgba(255,255,255,0.15)",borderRadius:6,padding:"3px 12px",
              fontSize:11,fontWeight:700,color:C.white}}>v1.0</div>
          </div>
          <div style={{display:"flex",gap:2,overflowX:"auto"}}>
            {TABS.map(t=><TabBtn key={t.id} icon={t.icon} label={t.label} active={tab===t.id} onClick={()=>setTab(t.id)}/>)}
          </div>
        </div>
      </div>
      <div style={{maxWidth:900,margin:"16px auto",padding:"0 16px"}}><Tab/></div>
      <div style={{textAlign:"center",padding:"12px",fontSize:10,color:C.muted}}>
        Physis Engineering · ABNT NBR 15527 · FAO · EMBRAPA · NBR 7229
      </div>
    </div>
  );
}
