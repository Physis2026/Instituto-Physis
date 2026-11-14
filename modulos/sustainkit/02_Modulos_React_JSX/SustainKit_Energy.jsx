import { useState } from "react";

const C = {
  main:"#0D47A1", light:"#E3F2FD", mid:"#1565C0", pale:"#EFF6FF",
  white:"#FFFFFF", ink:"#1C2B22", gray:"#F4F7F4", border:"#BFDBFE",
  muted:"#6B7F6E", sage:"#81A969", deep:"#074031",
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

const RISCOS = [
  {risco:"Deslizamentos e enxurradas",prob:5,imp:4,medida:"Laudo geotécnico obrigatório. Drenagem reforçada. Evitar encostas >30°"},
  {risco:"Chuvas intensas e alagamentos",prob:4,imp:4,medida:"Telhado verde retém 60% da chuva. Cisterna com extravasor. Calçadas drenantes"},
  {risco:"Ondas de calor extremo",prob:3,imp:3,medida:"Isolamento SIP + ventilação cruzada. Telhado verde. Brises horizontais"},
  {risco:"Ventos fortes / tempestades",prob:3,imp:3,medida:"SPDA (NBR 5419) obrigatório. Estrutura CLT resistente"},
  {risco:"Seca e escassez hídrica",prob:2,imp:4,medida:"Cisterna 15.000L + reúso águas cinzas. Irrigação por gotejamento"},
  {risco:"Geadas e frio extremo (altitude)",prob:3,imp:3,medida:"Vidro duplo obrigatório. Inércia térmica BTC/adobe. Solar passivo"},
  {risco:"Falha na rede elétrica",prob:4,imp:3,medida:"Bateria 40kWh → 48h autonomia. Biogás como backup"},
];

function Card({children,style={},bg=C.white}){
  return <div style={{background:bg,border:`1px solid ${C.border}`,borderRadius:12,
    padding:"16px 18px",boxShadow:"0 2px 10px rgba(13,71,161,0.07)",...style}}>{children}</div>;
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
    transition:"all 0.2s",display:"flex",alignItems:"center",gap:5,whiteSpace:"nowrap"}}>
    <span>{icon}</span>{label}
  </button>;
}

function TabSolar(){
  const [cidade,setCidade]=useState("Petrópolis — RJ");
  const [consumo,setConsumo]=useState(22);
  const [pot,setPot]=useState(10);
  const [modo,setModo]=useState("pior");
  const c=CIDADES[cidade];
  const hps=modo==="pior"?c.hpsMin:c.hps;
  const pr=0.78;
  const potMin=+(consumo/(hps*pr)).toFixed(1);
  const ger=Math.round(pot*hps*365*pr);
  const consAnual=consumo*365;
  const saldo=ger-consAnual;
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:12,fontSize:13}}>☀️ Dados do projeto</div>
        <Sel label="Cidade" value={cidade} onChange={setCidade} opts={Object.keys(CIDADES)}/>
        <Inp label="Consumo diário" value={consumo} onChange={setConsumo} unit="kWh/dia" min={1} max={500} step={0.5}/>
        <Inp label="Potência instalada" value={pot} onChange={setPot} unit="kWp" min={1} max={1000} step={0.5}/>
        <Lbl>Método HPS</Lbl>
        <div style={{display:"flex",gap:6,marginBottom:10}}>
          {[["pior","Pior mês ✅"],["media","Média anual"]].map(([v,l])=>(
            <button key={v} onClick={()=>setModo(v)} style={{flex:1,padding:"6px",borderRadius:7,
              border:`1px solid ${modo===v?C.main:C.border}`,background:modo===v?C.pale:C.white,
              color:modo===v?C.main:C.muted,fontWeight:modo===v?700:400,fontSize:11,cursor:"pointer",fontFamily:"inherit"}}>{l}</button>
          ))}
        </div>
        <div style={{fontSize:10,color:C.muted,fontStyle:"italic",padding:"7px",background:C.gray,borderRadius:6}}>
          HPS: {hps}h/dia · PR: {pr} · Fonte: PVGIS ERA5 (JRC — Comissão Europeia)
        </div>
      </Card>
      <div style={{display:"flex",flexDirection:"column",gap:10}}>
        <Card bg={C.pale}>
          <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>📊 Resultados</div>
          <Res label="Potência mínima" value={potMin+" kWp"}/>
          <Res label="Potência instalada" value={pot+" kWp"} hi/>
          <Res label="Geração anual" value={ger.toLocaleString("pt-BR")+" kWh"}/>
          <Res label="Consumo anual" value={consAnual.toLocaleString("pt-BR")+" kWh"}/>
          <div style={{padding:"11px",borderRadius:8,marginTop:4,textAlign:"center",
            background:saldo>=0?"#C8E6C9":"#FFCDD2",border:`1px solid ${saldo>=0?"#81C784":"#E57373"}`}}>
            <div style={{fontWeight:800,fontSize:14,color:saldo>=0?"#1B5E20":"#B71C1C"}}>
              {saldo>=0?"✅ NZEB alcançado":"⚠️ Déficit energético"}
            </div>
            <div style={{fontSize:11,marginTop:2,color:saldo>=0?"#2E7D32":"#C62828"}}>
              Saldo: {saldo>0?"+":""}{saldo.toLocaleString("pt-BR")} kWh/ano
            </div>
          </div>
        </Card>
        <Card>
          <div style={{fontSize:11,color:C.muted,fontStyle:"italic"}}>
            💡 HPS do pior mês recomendado para dimensionamento conservador — garante autonomia no inverno (menor irradiação)
          </div>
        </Card>
      </div>
    </div>
  );
}

function TabBateria(){
  const [consumo,setConsumo]=useState(22);
  const [autonomia,setAutonomia]=useState(48);
  const [dod,setDod]=useState(0.90);
  const [ef,setEf]=useState(0.97);
  const energia=consumo*(autonomia/24)/ef;
  const capUtil=+(energia/dod).toFixed(1);
  const capInst=Math.round(capUtil*1.2);
  const capAh=Math.round(capInst*1000/48);
  const ciclos={"0.90":"4.000–6.000 (LiFePO4)","0.85":"3.000–5.000 (Li-NMC)","0.50":"500–800 (AGM/Gel)"}[String(dod)]||"—";
  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:12,fontSize:13}}>🔋 Parâmetros da bateria</div>
        <Inp label="Consumo diário" value={consumo} onChange={setConsumo} unit="kWh/dia" min={1} max={500} step={0.5}/>
        <Inp label="Autonomia desejada" value={autonomia} onChange={setAutonomia} unit="horas" min={12} max={240} step={12}
          note="48h = 2 dias sem sol/rede — recomendado para sistemas off-grid"/>
        <Sel label="Tecnologia (DoD)" value={String(dod)} onChange={v=>setDod(+v)}
          opts={[{v:"0.90",l:"LiFePO4 — DoD 90% ✅ Recomendado"},{v:"0.85",l:"Li-NMC — DoD 85%"},{v:"0.50",l:"Chumbo-ácido AGM — DoD 50%"}]}/>
        <Sel label="Eficiência roundtrip" value={String(ef)} onChange={v=>setEf(+v)}
          opts={[{v:"0.97",l:"LiFePO4: 97%"},{v:"0.95",l:"Li-NMC: 95%"},{v:"0.85",l:"AGM: 85%"}]}/>
      </Card>
      <Card bg={C.pale}>
        <div style={{fontWeight:700,color:C.main,marginBottom:10,fontSize:13}}>📊 Dimensionamento</div>
        <Res label="Energia necessária no período" value={energia.toFixed(1)+" kWh"}/>
        <Res label="Capacidade utilizável" value={capUtil+" kWh"}/>
        <Res label="Capacidade instalada (+20% margem)" value={capInst+" kWh"} hi/>
        <Res label="Capacidade em Ah (sistema 48V)" value={capAh+" Ah"}/>
        <Res label="Ciclos de vida estimados" value={ciclos}/>
        <div style={{marginTop:8,padding:"10px",background:C.white,borderRadius:8,border:`1px solid ${C.border}`}}>
          <div style={{fontSize:11,fontWeight:700,color:C.main,marginBottom:4}}>Referências de mercado 2025</div>
          {[["BYD HVS","LiFePO4 · 5–10 kWh/módulo · 10 anos garantia"],
            ["Pylontech US5000","LiFePO4 · 4,8 kWh · melhor custo-benefício"],
            ["Growatt ARK","LiFePO4 · 5–20 kWh · integrado ao inversor"]].map(([m,d])=>(
            <div key={m} style={{fontSize:10,color:C.ink,padding:"4px 0",borderBottom:`1px solid ${C.border}`}}>
              <strong>{m}</strong> — {d}
            </div>
          ))}
        </div>
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
  const declR=decl*Math.PI/180;
  const ws_=Math.acos(Math.max(-1,Math.min(1,-Math.tan(latR)*Math.tan(declR))))*(180/Math.PI);
  const dur=+(2*ws_/15).toFixed(1);
  const alt=+(Math.asin(Math.sin(latR)*Math.sin(declR)+Math.cos(latR)*Math.cos(declR))*(180/Math.PI)).toFixed(1);
  const incOtima=+Math.abs(lat).toFixed(1);
  const hpsEst=+(dur*0.4).toFixed(1);

  const hpsAll=meses.map((_,i)=>{
    const nn=[15,46,74,105,135,166,196,227,258,288,319,349][i];
    const dd=23.45*Math.sin((Math.PI/180)*(360/365*(284+nn)));
    const ac2=-Math.tan(latR)*Math.tan(dd*Math.PI/180);
    const ws2=Math.acos(Math.max(-1,Math.min(1,ac2)))*(180/Math.PI);
    return +(2*ws2/15*0.4).toFixed(1);
  });
  const maxH=Math.max(...hpsAll);

  return(
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
      <Card>
        <div style={{fontWeight:700,color:C.main,marginBottom:12,fontSize:13}}>🌞 Dados da localização</div>
        <Inp label="Latitude" value={lat} onChange={setLat} unit="°" min={-90} max={90} step={0.001}
          note="Negativo = Hemisfério Sul (Brasil)"/>
        <Sel label="Mês de análise" value={String(mes)} onChange={v=>setMes(+v)}
          opts={meses.map((m,i)=>({v:String(i+1),l:m}))}/>
        <div style={{marginTop:8,padding:"10px",background:C.pale,borderRadius:8}}>
          {[["Declinação solar (δ)",decl+"°"],["Duração do dia",dur+"h"],
            ["Altitude solar ao meio-dia",alt+"°"],["HPS estimadas",hpsEst+"h/dia"],
            ["Inclinação ótima anual",incOtima+"°"],["Hemisfério",lat<0?"Sul":"Norte"],
            ["Orientação painéis",lat<0?"Norte verdadeiro (0°)":"Sul verdadeiro (180°)"]].map(([l,v])=>(
            <div key={l} style={{display:"flex",justifyContent:"space-between",
              padding:"6px 0",borderBottom:`1px solid ${C.border}`,fontSize:12}}>
              <span style={{color:C.muted}}>{l}</span>
              <span style={{fontWeight:700,color:C.main}}>{v}</span>
            </div>
          ))}
        </div>
      </Card>
      <Card bg={C.pale}>
        <div style={{fontWeight:700,color:C.main,marginBottom:12,fontSize:13}}>📊 HPS por mês — {lat.toFixed(2)}°</div>
        <div style={{display:"flex",gap:3,alignItems:"flex-end",height:100,marginBottom:8}}>
          {hpsAll.map((h,i)=>(
            <div key={i} style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",gap:2}}>
              <div style={{fontSize:8,color:i===mes-1?C.main:C.muted,fontWeight:i===mes-1?700:400}}>{h}</div>
              <div style={{width:"100%",height:Math.round((h/maxH)*80),
                background:i===mes-1?C.main:C.border,borderRadius:"3px 3px 0 0",transition:"height 0.3s"}}/>
              <div style={{fontSize:8,color:i===mes-1?C.main:C.muted,fontWeight:i===mes-1?700:400}}>
                {meses[i]}
              </div>
            </div>
          ))}
        </div>
        <div style={{padding:"10px",background:C.white,borderRadius:8,border:`1px solid ${C.border}`}}>
          <div style={{fontSize:11,fontWeight:700,color:C.main,marginBottom:4}}>Recomendações por fachada</div>
          {[["Norte","Fachada principal · máxima abertura 40–60% · beiral 80–100cm"],
            ["Sul","Fachada posterior · luz difusa · 15–25% abertura"],
            ["Leste","Sol manhã · brise vertical · 20–30% abertura"],
            ["Oeste","Sol tarde crítico · máxima proteção · ≤20% abertura"]].map(([f,d])=>(
            <div key={f} style={{fontSize:10,color:C.ink,padding:"4px 0",borderBottom:`1px solid ${C.border}`}}>
              <strong style={{color:C.main}}>{f}:</strong> {d}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function TabResiliencia(){
  const [cidade,setCidade]=useState("Petrópolis — RJ");
  return(
    <div>
      <Card style={{marginBottom:12,padding:"12px 16px"}}>
        <div style={{display:"flex",gap:14,alignItems:"center",flexWrap:"wrap"}}>
          <div style={{flex:1}}>
            <Sel label="Cidade do projeto" value={cidade} onChange={setCidade} opts={Object.keys(CIDADES)}/>
          </div>
          <div style={{padding:"8px 14px",background:"#FFF3E0",borderRadius:8,border:"1px solid #FFB74D",fontSize:11}}>
            ⚠️ <strong style={{color:"#E65100"}}>LEED v5 obrigatório:</strong> Avaliação de risco climático deve ser documentada antes da obra
          </div>
        </div>
      </Card>
      <div style={{display:"grid",gridTemplateColumns:"1fr",gap:6}}>
        <div style={{display:"grid",gridTemplateColumns:"2fr 1fr 1fr 1fr 2fr",gap:0,marginBottom:4}}>
          {["Risco Climático","Probabilidade (1–5)","Impacto (1–5)","Total","Medida Recomendada"].map(h=>(
            <div key={h} style={{padding:"8px 10px",background:C.main,color:C.white,
              fontSize:11,fontWeight:700,borderRight:`1px solid rgba(255,255,255,0.2)`}}>{h}</div>
          ))}
        </div>
        {RISCOS.map((r,i)=>{
          const total=r.prob*r.imp;
          const nivel=total>=16?"🔴":total>=9?"🟡":"🟢";
          const bg=total>=16?"#FFCDD2":total>=9?"#FFE0B2":"#C8E6C9";
          return(
            <div key={i} style={{display:"grid",gridTemplateColumns:"2fr 1fr 1fr 1fr 2fr",
              background:i%2===0?C.white:C.gray,border:`1px solid ${C.border}`,borderRadius:i===0?"8px 8px 0 0":i===RISCOS.length-1?"0 0 8px 8px":"0"}}>
              <div style={{padding:"8px 10px",fontSize:12,fontWeight:600,color:C.ink,borderRight:`1px solid ${C.border}`}}>{r.risco}</div>
              <div style={{padding:"8px",textAlign:"center",fontSize:13,fontWeight:700,color:C.main,borderRight:`1px solid ${C.border}`}}>{r.prob}</div>
              <div style={{padding:"8px",textAlign:"center",fontSize:13,fontWeight:700,color:C.main,borderRight:`1px solid ${C.border}`}}>{r.imp}</div>
              <div style={{padding:"8px",textAlign:"center",fontWeight:800,fontSize:14,background:bg,borderRight:`1px solid ${C.border}`}}>{nivel} {total}</div>
              <div style={{padding:"8px 10px",fontSize:11,color:C.ink,fontStyle:"italic"}}>{r.medida}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const TABS=[
  {id:"solar",icon:"☀️",label:"Solar FV",comp:TabSolar},
  {id:"bat",icon:"🔋",label:"Bateria",comp:TabBateria},
  {id:"ori",icon:"🌞",label:"Orientação Solar",comp:TabOrientacao},
  {id:"res",icon:"🌪️",label:"Resiliência",comp:TabResiliencia},
];

export default function App(){
  const [tab,setTab]=useState("solar");
  const Tab=TABS.find(t=>t.id===tab).comp;
  return(
    <div style={{fontFamily:"-apple-system,'Segoe UI',Arial,sans-serif",background:"#F0F4FF",minHeight:"100vh"}}>
      <div style={{background:C.main,padding:"14px 20px 0"}}>
        <div style={{maxWidth:900,margin:"0 auto"}}>
          <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:14}}>
            <div style={{display:"flex",alignItems:"center",gap:10}}>
              <div style={{width:32,height:32,borderRadius:"50%",background:"rgba(255,255,255,0.2)",
                display:"flex",alignItems:"center",justifyContent:"center",fontSize:16}}>⚡</div>
              <div>
                <div style={{fontWeight:800,fontSize:16,color:C.white}}>SustainKit Energy</div>
                <div style={{fontSize:10,color:"rgba(255,255,255,0.7)"}}>Physis Engineering · Energia Solar, Bateria e Resiliência</div>
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
      <div style={{maxWidth:900,margin:"16px auto",padding:"0 16px"}}>
        <Tab/>
      </div>
      <div style={{textAlign:"center",padding:"12px",fontSize:10,color:C.muted}}>
        Physis Engineering · PVGIS ERA5 · ASHRAE 2022 · ABNT NBR · LEED v5
      </div>
    </div>
  );
}
