import { useState } from "react";

const C = {
  main:"#4E342E", light:"#EFEBE9", mid:"#6D4C41", pale:"#FBE9E7",
  white:"#FFFFFF", ink:"#1C2B22", gray:"#F4F7F4", border:"#FFCCBC",
  muted:"#6B7F6E", green:"#1B5E20",
};

const CARGAS = [
  {nome:"Bomba irrigação gotejamento",tipo:"Bombeamento",potencia:750,horas:6},
  {nome:"Bomba aspersão",tipo:"Bombeamento",potencia:1500,horas:5},
  {nome:"Bomba dessedentação animal",tipo:"Bombeamento",potencia:400,horas:4},
  {nome:"Câmara fria 10m³",tipo:"Refrigeração",potencia:2200,horas:16},
  {nome:"Resfriador de leite",tipo:"Refrigeração",potencia:1800,horas:6},
  {nome:"Debulhadora / trilhadora",tipo:"Processamento",potencia:3000,horas:3},
  {nome:"Ordenhadeira mecânica",tipo:"Processamento",potencia:1100,horas:2},
  {nome:"Secador de grãos",tipo:"Processamento",potencia:3700,horas:4},
  {nome:"Iluminação LED galpão",tipo:"Iluminação",potencia:200,horas:12},
  {nome:"Hub IoT / monitoramento",tipo:"IoT",potencia:5,horas:24},
  {nome:"Cerca elétrica",tipo:"Segurança",potencia:5,horas:24},
];

const CULTURAS_AGRIPV = [
  {nome:"🍓 Morango",compat:"★★★★★",sombra:"30%",red:"0–5% (melhora)",nota:"Ideal altitude. Protege do calor"},
  {nome:"🥬 Alface / Rúcula",compat:"★★★★★",sombra:"30%",red:"0–10%",nota:"Evita espigamento. Alta produtividade"},
  {nome:"☕ Café",compat:"★★★★☆",sombra:"30–40%",red:"0–10%",nota:"Planta de sub-bosque. Muito compatível"},
  {nome:"🍇 Uva",compat:"★★★★☆",sombra:"20–30%",red:"5–15%",nota:"Controla temperatura das bagas"},
  {nome:"🌿 Hortaliças gerais",compat:"★★★☆☆",sombra:"20%",red:"10–20%",nota:"Reduz estresse térmico no verão"},
  {nome:"🌾 Soja / Milho",compat:"★★☆☆☆",sombra:"<15%",red:"25–40%",nota:"Não recomendado como cultura única"},
];

const ANIMAIS = [
  {nome:"Bovinos de corte",lcd:50,unit:"L/cabeça/dia"},
  {nome:"Bovinos de leite",lcd:80,unit:"L/cabeça/dia"},
  {nome:"Suínos",lcd:15,unit:"L/cabeça/dia"},
  {nome:"Aves (frango)",lcd:0.3,unit:"L/ave/dia"},
  {nome:"Caprinos / Ovinos",lcd:5,unit:"L/cabeça/dia"},
];

function Card({children,style={},bg=C.white}){
  return <div style={{background:bg,border:`1px solid ${C.border}`,borderRadius:12,
    padding:"16px 18px",boxShadow:"0 2px 10px rgba(78,52,46,0.07)",...style}}>{children}</div>;
}
function Inp({label,value,onChange,unit,min=0,max=9999,step=1,note}){
  return <div style={{marginBottom:11}}>
    {label&&<div style={{fontSize:11,fontWeight:600,color:C.ink,marginBottom:4}}>{label}</div>}
    <div style={{display:"flex",gap:6,alignItems:"center"}}>
      <input type="number" value={value} min={min} max={max} step={step}
        onChange={e=>onChange(+e.target.value)}
        style={{flex:1,padding:"7px 10px",border:`2px solid ${C.border}`,borderRadius:8,
          fontSize:14,fontWeight:700,color:C.main,background:C.pale,fontFamily:"inherit",outline:"none"}}/>
      {unit&&<span style={{fontSize:11,color:C.muted,minWidth:42}}>{unit}</span>}
    </div>
    {note&&<div style={{fontSize:10,color:C.muted,marginTop:2,fontStyle:"italic"}}>{note}</div>}
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

function TabDiagnostico(){
  const [cargas,setCargas]=useState(CARGAS.map(c=>({...c,ativo:false})));
  const [hps,setHps]=useState(4.5);
  const [autonomia,setAutonomia]=useState(48);
  const totalWh=cargas.filter(c=>c.ativo).reduce((a,c)=>a+c.potencia*c.horas,0);
  const totalKwh=+(totalWh/1000).toFixed(1);
  const potMin=+(totalKwh/(hps*0.75)).toFixed(1);
  const capBat=Math.round((totalKwh*(autonomia/24))/0.80*1.2);
  const tiposCores={"Bombeamento":"#DBEAFE","Refrigeração":"#FCE4EC","Processamento":"#FFF9C4",
    "Iluminação":"#F3E5F5","IoT":"#E0F2F1","Segurança":"#FFCDD2"};
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:4,fontSize:13}}>⚡ Cargas da Propriedade</div>
        <div style={{fontSize:11,color:C.muted,marginBottom:10}}>Marque os equipamentos presentes:</div>
        {cargas.map((c,i)=>(
          <div key={i} onClick={()=>setCargas(cs=>cs.map((x,j)=>j===i?{...x,ativo:!x.ativo}:x))}
            style={{display:"flex",alignItems:"center",gap:8,padding:"8px 10px",borderRadius:8,
              marginBottom:5,cursor:"pointer",background:c.ativo?C.pale:C.gray,
              border:`1px solid ${c.ativo?C.main:C.border}`,transition:"all 0.15s"}}>
            <div style={{width:15,height:15,borderRadius:3,flexShrink:0,
              background:c.ativo?C.main:"transparent",border:`2px solid ${c.ativo?C.main:C.border}`,
              display:"flex",alignItems:"center",justifyContent:"center"}}>
              {c.ativo&&<span style={{color:C.white,fontSize:9}}>✓</span>}
            </div>
            <div style={{flex:1}}>
              <span style={{fontSize:12,fontWeight:c.ativo?600:400,color:c.ativo?C.main:C.muted}}>{c.nome}</span>
              <span style={{fontSize:10,color:C.muted,marginLeft:6,
                background:tiposCores[c.tipo]||"#eee",padding:"1px 6px",borderRadius:10}}>{c.tipo}</span>
            </div>
            <span style={{fontSize:11,fontWeight:700,color:c.ativo?C.main:C.muted,minWidth:55,textAlign:"right"}}>
              {(c.potencia*c.horas/1000).toFixed(1)} kWh
            </span>
          </div>
        ))}
      </Card>
      <div style={{display:"flex",flexDirection:"column",gap:12}}>
        <Card>
          <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>⚙️ Parâmetros</div>
          <Inp label="HPS local (pior mês — PVGIS)" value={hps} onChange={setHps}
            unit="h/dia" min={1} max={8} step={0.1}
            note="Usar pior mês para sistemas off-grid rurais"/>
          <Inp label="Autonomia de bateria" value={autonomia} onChange={setAutonomia}
            unit="horas" min={12} max={168} step={12}
            note="Câmara fria e ordenha: mínimo 48h"/>
        </Card>
        <Card bg={C.pale}>
          <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>📊 Dimensionamento</div>
          {[["Equipamentos selecionados",cargas.filter(c=>c.ativo).length+"/"+cargas.length],
            ["Consumo diário total",totalKwh+" kWh/dia"],
            ["Potência FV mínima",potMin+" kWp"],
            ["Capacidade de bateria",capBat+" kWh"],
            ["PR sistema agro off-grid","0,75 (conservador)"]].map(([l,v],i)=>(
            <div key={l} style={{display:"flex",justifyContent:"space-between",alignItems:"center",
              padding:"8px 11px",background:i<2?C.gray:C.white,borderRadius:8,marginBottom:5,
              border:i>=2?`1px solid ${C.border}`:"none"}}>
              <span style={{fontSize:12,color:C.ink}}>{l}</span>
              <span style={{fontSize:14,fontWeight:800,color:i>=2?C.main:C.ink}}>{v}</span>
            </div>
          ))}
          <div style={{marginTop:6,padding:"9px",background:"#C8E6C9",borderRadius:8,fontSize:11,color:C.green}}>
            Fórmula: P_min = Consumo(kWh) ÷ (HPS × PR) · Bateria com margem 20%
          </div>
        </Card>
      </div>
    </div>
  );
}

function TabBombeamento(){
  const [animais,setAnimais]=useState(ANIMAIS.map(a=>({...a,qtd:0})));
  const [poco,setPoço]=useState(30);
  const [dinamico,setDinamico]=useState(40);
  const [recalque,setRecalque]=useState(5);
  const [perdas,setPerdas]=useState(5);
  const [vazao,setVazao]=useState(5);
  const thd=poco+dinamico+recalque+perdas;
  const pHid=+(vazao/3.6*1000*9.81*thd/1000).toFixed(0);
  const pElet=Math.round(pHid/0.55);
  const totalAgua=animais.reduce((a,r)=>a+(r.qtd*r.lcd),0);
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>💧 Bombeamento Solar</div>
        <div style={{fontSize:11,fontWeight:600,color:C.muted,marginBottom:6}}>Dados do poço / sistema</div>
        {[["Nível estático do poço",poco,setPoço],["Nível dinâmico",dinamico,setDinamico],
          ["Altura de recalque",recalque,setRecalque],["Perdas na tubulação",perdas,setPerdas]].map(([l,v,s])=>(
          <Inp key={l} label={l} value={v} onChange={s} unit="m" min={0} max={500}/>
        ))}
        <Inp label="Vazão necessária" value={vazao} onChange={setVazao} unit="m³/h" min={0.1} max={1000} step={0.1}/>
        <div style={{marginTop:4,padding:"10px",background:C.pale,borderRadius:8}}>
          {[["TDH Total",thd+" m"],["Potência hidráulica",pHid+" W"],["Potência elétrica da bomba",pElet+" W"]].map(([l,v])=>(
            <div key={l} style={{display:"flex",justifyContent:"space-between",fontSize:12,
              padding:"4px 0",borderBottom:`1px solid ${C.border}`}}>
              <span style={{color:C.muted}}>{l}</span>
              <span style={{fontWeight:700,color:C.main}}>{v}</span>
            </div>
          ))}
          <div style={{fontSize:10,color:C.muted,marginTop:4,fontStyle:"italic"}}>
            TDH = Nível dinâmico + Recalque + Perdas · η_bomba = 0,55
          </div>
        </div>
      </Card>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>🐄 Dessedentação Animal</div>
        {animais.map((a,i)=>(
          <div key={i} style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
            <span style={{fontSize:12,flex:1,color:C.ink}}>{a.nome}</span>
            <input type="number" value={a.qtd} min={0} max={100000}
              onChange={e=>setAnimais(m=>m.map((x,j)=>j===i?{...x,qtd:+e.target.value}:x))}
              style={{width:65,padding:"5px 8px",border:`2px solid ${C.border}`,borderRadius:7,
                fontSize:13,fontWeight:700,color:C.main,background:C.pale,
                fontFamily:"inherit",textAlign:"center",outline:"none"}}/>
            <span style={{fontSize:10,color:C.muted,minWidth:70,textAlign:"right"}}>
              {(a.qtd*a.lcd).toLocaleString("pt-BR")} L/dia
            </span>
          </div>
        ))}
        <div style={{padding:"10px",background:C.pale,borderRadius:8,marginTop:4,textAlign:"center"}}>
          <div style={{fontSize:11,color:C.muted}}>Total dessedentação</div>
          <div style={{fontSize:22,fontWeight:800,color:C.main}}>{totalAgua.toLocaleString("pt-BR")} L/dia</div>
          <div style={{fontSize:10,color:C.muted,marginTop:2}}>{+(totalAgua/1000).toFixed(2)} m³/dia</div>
        </div>
      </Card>
    </div>
  );
}

function TabAgriPV(){
  const [area,setArea]=useState(5);
  const [cobertura,setCobertura]=useState(30);
  const [hps,setHps]=useState(4.5);
  const areaPaineis=area*10000*(cobertura/100);
  const potInst=+(areaPaineis*220/1000).toFixed(1);
  const gerAnual=Math.round(potInst*hps*365*0.75);
  const ler=1.35;
  return(
    <div style={{display:"flex",flexDirection:"column",gap:14}}>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
        <Card>
          <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>🌱 Configuração AgriPV</div>
          <Inp label="Área disponível para AgriPV" value={area} onChange={setArea} unit="ha" min={0.1} max={1000} step={0.1}/>
          <Inp label="Cobertura de painéis (% da área)" value={cobertura} onChange={setCobertura} unit="%" min={10} max={50}
            note="20–40% = sweet spot. >50% reduz produção agrícola excessivamente"/>
          <Inp label="HPS local (pior mês)" value={hps} onChange={setHps} unit="h/dia" min={1} max={8} step={0.1}/>
          <div style={{padding:"10px",background:C.pale,borderRadius:8,marginTop:4}}>
            {[["Área de painéis",Math.round(areaPaineis).toLocaleString("pt-BR")+" m²"],
              ["Potência instalada",potInst+" kWp"],
              ["Geração anual estimada",gerAnual.toLocaleString("pt-BR")+" kWh"],
              ["LER típico AgriPV",ler+" (30–70% mais produção/ha)"]].map(([l,v])=>(
              <div key={l} style={{display:"flex",justifyContent:"space-between",fontSize:12,
                padding:"5px 0",borderBottom:`1px solid ${C.border}`}}>
                <span style={{color:C.muted}}>{l}</span>
                <span style={{fontWeight:700,color:C.main}}>{v}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <div style={{fontWeight:700,color:C.main,marginBottom:4,fontSize:13}}>🌿 Culturas Compatíveis</div>
          <div style={{fontSize:11,color:C.muted,marginBottom:10}}>
            LER: Land Equivalent Ratio — eficiência de uso da terra vs. sistemas separados
          </div>
          {CULTURAS_AGRIPV.map(c=>{
            const stars=c.compat.replace(/☆/g,"").length;
            const bg=stars>=4?"#C8E6C9":stars===3?"#FFF9C4":"#FFE0B2";
            return(
              <div key={c.nome} style={{padding:"9px 11px",background:bg,borderRadius:8,marginBottom:6,
                border:`1px solid ${bg}`}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
                  <span style={{fontSize:12,fontWeight:600,color:C.ink}}>{c.nome}</span>
                  <span style={{fontSize:11,color:stars>=4?C.green:"#E65100"}}>{c.compat}</span>
                </div>
                <div style={{fontSize:10,color:C.muted,marginTop:2}}>
                  Sombra: {c.sombra} · Redução: {c.red} · {c.nota}
                </div>
              </div>
            );
          })}
        </Card>
      </div>
      <Card bg={C.pale}>
        <div style={{fontSize:11,color:C.muted,fontStyle:"italic"}}>
          📚 Referências: Fraunhofer ISE AgriPV Guidelines 2023 · Dupraz et al. (1993) · EMBRAPA + ABSOLAR · FAO
          · LER médio para sistemas bem dimensionados: 1,3–1,7 · Aprovado em projetos no RS, MG e SP
        </div>
      </Card>
    </div>
  );
}

const TABS=[
  {id:"diag",icon:"⚡",label:"Diagnóstico Energético",comp:TabDiagnostico},
  {id:"bomb",icon:"💧",label:"Bombeamento Solar",comp:TabBombeamento},
  {id:"agripv",icon:"🌱",label:"AgriPV",comp:TabAgriPV},
];

export default function App(){
  const [tab,setTab]=useState("diag");
  const Tab=TABS.find(t=>t.id===tab).comp;
  return(
    <div style={{fontFamily:"-apple-system,'Segoe UI',Arial,sans-serif",background:"#EFEBE9",minHeight:"100vh"}}>
      <div style={{background:C.main,padding:"14px 20px 0"}}>
        <div style={{maxWidth:900,margin:"0 auto"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
            <div style={{display:"flex",alignItems:"center",gap:10}}>
              <div style={{width:32,height:32,borderRadius:"50%",background:"rgba(255,255,255,0.2)",
                display:"flex",alignItems:"center",justifyContent:"center",fontSize:16}}>🌾</div>
              <div>
                <div style={{fontWeight:800,fontSize:16,color:C.white}}>SustainKit Agro</div>
                <div style={{fontSize:10,color:"rgba(255,255,255,0.7)"}}>Physis Engineering · Energia Solar para Uso Produtivo Rural</div>
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
        Physis Engineering · GIZ/Physis PUE Solar Manual · FAO · EMBRAPA · Fraunhofer ISE · ABNT
      </div>
    </div>
  );
}
