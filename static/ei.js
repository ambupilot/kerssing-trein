(() => {
"use strict";
const TYPES = [
["1","Toestemming een EOA/stoptonend sein te passeren","#F5B3B4"],
["2","Toestemming tot doorrijden na TRIP","#D2D4D4"],
["3","Verplichting om stil te blijven staan","#EDD0E0"],
["4","Intrekking van een instructie","#FFF0BD"],
["5","Verplichting om de snelheid te beperken","#AFD2EB"],
["6","Verplichting om te rijden op zicht","#F5F09B"],
["7","Toestemming om te vertrekken","#D2D4D4"],
["8","Toestemming om een defecte overweg te passeren","#F8C4A7"]];
const $=id=>document.getElementById(id);
let SCHEMA={};
const state={selected:[],details:{},checks:{},accepted:false,identification:"",date:"",time:""};
let db, wake=null, saveChain=Promise.resolve();
const now=new Date(), local=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString();
state.date=local.slice(0,10);state.time=local.slice(11,16);
function openDb(){return new Promise((resolve,reject)=>{const req=indexedDB.open("kerssing-ei",1);req.onupgradeneeded=()=>req.result.createObjectStore("drafts");req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});}
function transact(mode,fn){return new Promise((resolve,reject)=>{const tx=db.transaction("drafts",mode),req=fn(tx.objectStore("drafts"));req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});}
function snapshot(){return JSON.parse(JSON.stringify(state));}
function save(){const data=snapshot();$("ei-storage").textContent="Lokaal opslaan…";saveChain=saveChain.catch(()=>{}).then(()=>transact("readwrite",s=>s.put(data,"current"))).then(()=>$("ei-storage").textContent="Lokaal opgeslagen om "+new Date().toLocaleTimeString("nl-NL"),()=>$("ei-storage").textContent="WAARSCHUWING: lokaal opslaan mislukt");}
function render(){
$("ei-selection").hidden=state.accepted;$("ei-selected").hidden=!state.accepted;
document.querySelectorAll(".ei-choice").forEach(c=>c.checked=state.selected.includes(c.value));
$("ei-id").value=state.identification;$("ei-date").value=state.date;$("ei-time").value=state.time;
const root=$("ei-forms");root.replaceChildren();
if(state.accepted) for(const num of state.selected){
const def=SCHEMA[num];if(!def)continue;
const card=document.createElement("section");card.className="ei-card";card.style.background=def.color;
const h=document.createElement("h3");h.textContent=(Number(num)>8?"x.":"EI ")+num+" — "+def.title;card.append(h);
for(const [code,description] of def.checks){
const label=document.createElement("label");label.style.display="flex";label.style.gap="10px";label.style.margin="12px 0";
const cb=document.createElement("input");cb.type="checkbox";cb.checked=!!(state.checks[num]||{})[code];cb.style.width="22px";cb.style.height="22px";
cb.addEventListener("change",()=>{(state.checks[num]??={})[code]=cb.checked;save();});
const span=document.createElement("span");span.textContent=code+" "+description;label.append(cb,span);card.append(label);
}
for(const [key,description,type] of def.fields){
const label=document.createElement("label");label.style.display="block";label.style.margin="12px 0";
const span=document.createElement("span");span.textContent=description;span.style.display="block";span.style.fontWeight="600";
const field=document.createElement(type==="textarea"?"textarea":"input");
if(type!=="textarea")field.type=type;field.style.width="100%";field.style.padding="10px";
field.value=(state.details[num]||{})[key]||"";
field.addEventListener("input",()=>{if(typeof state.details[num]!=="object"||!state.details[num])state.details[num]={};state.details[num][key]=field.value;save();});
label.append(span,field);card.append(label);
}
root.append(card);
}
}
}
async function requestWake(){
if(!state.accepted)return;
try{if(!("wakeLock" in navigator))throw Error("Niet ondersteund");wake=await navigator.wakeLock.request("screen");$("ei-wake").textContent="Scherm actief houden: actief";wake.addEventListener("release",()=>{wake=null;$("ei-wake").textContent="Scherm actief houden: niet actief";});}
catch(e){$("ei-wake").textContent="WAARSCHUWING: scherm kan uitschakelen ("+e.message+")";}
}
document.querySelectorAll(".ei-choice").forEach(c=>c.addEventListener("change",()=>{state.selected=Array.from(document.querySelectorAll(".ei-choice:checked")).map(x=>x.value);save();}));
$("ei-accept").addEventListener("click",()=>{if(!state.selected.length){alert("Selecteer minimaal één EI.");return;}if(!db){alert("Lokale opslag is niet beschikbaar. Aannemen is geblokkeerd.");return;}state.accepted=true;render();save();requestWake();});
$("ei-back").addEventListener("click",()=>{state.accepted=false;wake?.release();wake=null;render();save();});
for(const [id,key] of [["ei-id","identification"],["ei-date","date"],["ei-time","time"]])$(id).addEventListener("input",e=>{state[key]=e.target.value;save();});
function connectivity(){$("ei-connectivity").textContent=navigator.onLine?"Online — concept lokaal opgeslagen; geen serversynchronisatie":"Offline — concept uitsluitend lokaal opgeslagen";}
window.addEventListener("online",connectivity);window.addEventListener("offline",connectivity);
document.addEventListener("visibilitychange",()=>{if(!document.hidden&&state.accepted&&!wake)requestWake();});
window.addEventListener("beforeunload",()=>{if(state.accepted)return;});
(async()=>{try{const response=await fetch(document.currentScript?.dataset?.schema||"/static/ei-schema.json");if(!response.ok)throw Error("Schema niet beschikbaar");SCHEMA=await response.json();}catch(e){$("ei-storage").textContent="WAARSCHUWING: EI-formulieren niet geladen";return;}try{db=await openDb();const saved=await transact("readonly",s=>s.get("current"));if(saved)Object.assign(state,saved);state.checks ||= {};state.details ||= {};render();$("ei-storage").textContent="Lokale conceptopslag gereed";if(state.accepted)requestWake();}catch(e){$("ei-storage").textContent="WAARSCHUWING: IndexedDB niet beschikbaar — geen betrouwbare opslag";render();}connectivity();})();
})();