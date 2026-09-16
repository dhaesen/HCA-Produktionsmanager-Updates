/* HCA v0.13.24 · Produktionsauftragssuche, Lieferadresse und Serienmonitor */
(()=>{
'use strict';
const V='0.13.24';
const state={orderId:'',customerId:'',selectedTaskId:'',returnToMonitor:false,searchTimer:0};

function splitStreet(value=''){
  const text=String(value||'').trim();
  const m=text.match(/^(.*?)[,\s]+(\d+[a-zA-Z]?(?:\s*[-/]\s*\d+[a-zA-Z]?)?)$/);
  return m?[m[1].trim(),m[2].trim()]:[text,''];
}
function customerLabel(c={}){
  return String(c.company_name||[c.first_name,c.last_name].filter(Boolean).join(' ')||c.email||c.customer_no||'Kunde').trim();
}
function customerRecipient(c={}){
  const addresses=Array.isArray(c.addresses)?c.addresses:[];
  const address=addresses.find(a=>String(a.id)===String(c.default_shipping_address_id||''))||addresses.find(a=>a.is_default_shipping)||addresses[0]||{};
  const streetValue=address.street||c.shipping_street||c.billing_street||'';
  const [street,house]=splitStreet(streetValue);
  const contacts=Array.isArray(c.contacts)?c.contacts:[];
  const contact=contacts.find(x=>x.is_primary)||contacts[0]||{};
  const person=[contact.first_name||c.first_name,contact.last_name||c.last_name].filter(Boolean).join(' ').trim();
  return {recipient_name:person||customerLabel(c),company:c.company_name||address.company_name||'',address_line_1:street,house_number:house,address_line_2:address.address_line_2||'',postal_code:address.zip||c.shipping_zip||c.billing_zip||'',city:address.city||c.shipping_city||c.billing_city||'',country_code:String(address.country||c.shipping_country||c.billing_country||'DE').toUpperCase(),email:contact.email||c.email||'',phone:contact.phone||contact.mobile||c.phone||c.mobile||''};
}
function orderRecipient(o={}){
  const s=o.shipping||{};const [street,house]=splitStreet(s.street||'');
  return {recipient_name:s.attention||s.contact_name||s.name||o.customer_name||'',company:s.name||o.customer_name||'',address_line_1:street,house_number:house,address_line_2:s.address_line_2||'',postal_code:s.zip||'',city:s.city||'',country_code:String(s.country||'DE').toUpperCase(),email:s.email||'',phone:s.phone||''};
}
function addressIsUseful(r={}){return !!(r.address_line_1&&r.postal_code&&r.city);}
function applyRecipient(r){
  fillStandardRecipient(r||{});
  if(addressIsUseful(r)){$('#centralOrderType').value='standard';updateOrderShippingTypeUI();}
}

function searchHost(input){
  let host=input.parentElement.querySelector(':scope > .hca1324-search-results');
  if(!host){input.parentElement.classList.add('hca1324-search-field');host=document.createElement('div');host.className='hca1324-search-results hidden';input.insertAdjacentElement('afterend',host);}
  return host;
}
function hideSearches(except=null){document.querySelectorAll('.hca1324-search-results').forEach(x=>{if(x!==except)x.classList.add('hidden');});}
function renderSearch(input,items,type){
  const host=searchHost(input);host.innerHTML='';
  if(!items.length){host.innerHTML='<div class="hca1324-search-empty">Keine Treffer</div>';host.classList.remove('hidden');return;}
  items.forEach(item=>{const b=document.createElement('button');b.type='button';b.className='hca1324-search-result';
    if(type==='order')b.innerHTML=`<strong>${escapeHtml(item.order_no||'Auftrag')}</strong><span>${escapeHtml(item.customer_name||'')}${item.subject?` · ${escapeHtml(item.subject)}`:''}</span>`;
    else b.innerHTML=`<strong>${escapeHtml(customerLabel(item))}</strong><span>${escapeHtml(item.customer_no||'')}${item.email?` · ${escapeHtml(item.email)}`:''}</span>`;
    b.addEventListener('mousedown',e=>e.preventDefault());b.addEventListener('click',async()=>{host.classList.add('hidden');try{if(type==='order')await selectOrder(item);else await selectCustomer(item);}catch(err){alert(`Auswahl konnte nicht übernommen werden:\n${err.message||err}`);}});host.appendChild(b);
  });host.classList.remove('hidden');
}
async function selectCustomer(summary){
  const data=await businessApi(`/crm/customers/${encodeURIComponent(summary.id)}`),c=data.item||summary;
  state.customerId=String(c.id||'');$('#centralOrderCustomer').value=customerLabel(c);applyRecipient(customerRecipient(c));
}
async function selectOrder(summary){
  const data=await businessApi(`/sales/orders/${encodeURIComponent(summary.id)}`),o=data.item||summary;
  state.orderId=String(o.id||'');state.customerId=String(o.customer_id||'');$('#centralOrderNo').value=o.order_no||'';$('#centralOrderCustomer').value=o.customer_name||'';
  if(!$('#centralOrderTitle').value.trim())$('#centralOrderTitle').value=o.subject||'Produktionsauftrag';
  if(!$('#centralOrderDue').value&&o.due_date)$('#centralOrderDue').value=String(o.due_date).slice(0,10);
  const r=orderRecipient(o);if(addressIsUseful(r))applyRecipient(r);else if(o.customer_id)await selectCustomer({id:o.customer_id});
}
async function runSearch(input,type){
  const q=input.value.trim();if(q.length<2){searchHost(input).classList.add('hidden');return;}
  try{const data=type==='order'?await businessApi(`/sales/orders?q=${encodeURIComponent(q)}&limit=20`):await businessApi(`/crm/customers?q=${encodeURIComponent(q)}&limit=20`);renderSearch(input,Array.isArray(data.items)?data.items:[],type);}catch(err){const host=searchHost(input);host.innerHTML=`<div class="hca1324-search-empty">${escapeHtml(err.message||String(err))}</div>`;host.classList.remove('hidden');}
}
function installSearch(input,type){
  if(!input||input.dataset.hca1324Search)return;input.dataset.hca1324Search=type;input.setAttribute('autocomplete','off');input.placeholder=type==='order'?'Auftragsnummer oder Kunde suchen …':'Kundennummer, Firma oder Name suchen …';
  input.addEventListener('input',()=>{if(type==='order')state.orderId='';else state.customerId='';clearTimeout(state.searchTimer);state.searchTimer=setTimeout(()=>runSearch(input,type),180);});
  input.addEventListener('focus',()=>{if(input.value.trim().length>=2)runSearch(input,type);});input.addEventListener('keydown',e=>{if(e.key==='Escape')searchHost(input).classList.add('hidden');});
}
function installOrderSearches(){installSearch($('#centralOrderNo'),'order');installSearch($('#centralOrderCustomer'),'customer');}
document.addEventListener('mousedown',e=>{if(!e.target.closest('.hca1324-search-field'))hideSearches();});
const baseOpenCentralOrderDialog=openCentralOrderDialog;
openCentralOrderDialog=function(mode='customer'){state.orderId='';state.customerId='';baseOpenCentralOrderDialog(mode);installOrderSearches();};
const baseOpenCentralOrderEditDialog=openCentralOrderEditDialog;
openCentralOrderEditDialog=async function(orderId){await baseOpenCentralOrderEditDialog(orderId);installOrderSearches();};
installOrderSearches();

/* Die bisherige Personalisierung bleibt kompatibel. Die Bezeichnung erklärt nun auch
   Standort-/Teamnamen; daraus wird zugleich ein eindeutiger Dateivorschlag erzeugt. */
const baseSyncManualPersonalizationFields=syncManualPersonalizationFields;
syncManualPersonalizationFields=function(card){baseSyncManualPersonalizationFields(card);card?.querySelectorAll('[data-manual-person="name"]').forEach(i=>i.placeholder='Name / Standort / Team (z. B. Berlin)');};

function isSeriesOrder(){
  const meta=sharedMetaForOrder(centralProductionMonitorOrder?.id)||{};
  return meta.shipping_mode==='merch'||centralProductionMonitorTasks.some(t=>String(t.personalization_name||t.team_name||t.number_text||t.shipping_group||'').trim());
}
function slots(){appState.productionMachineSlots=Array.isArray(appState.productionMachineSlots)?appState.productionMachineSlots:Array(4).fill(null);while(appState.productionMachineSlots.length<4)appState.productionMachineSlots.push(null);return appState.productionMachineSlots;}
function remaining(task){return Math.max(0,(Number(task?.target_qty)||0)-(Number(task?.done_qty)||0));}
function assignedCount(taskId){return slots().filter(s=>s&&String(s.task_id)===String(taskId)).length;}
function sizeKey(t){return String(t.size||'Ohne Größe').trim()||'Ohne Größe';}
function seriesTasksForSize(size){return centralProductionMonitorTasks.filter(t=>sizeKey(t)===size&&remaining(t)>assignedCount(t.id)).sort((a,b)=>[a.personalization_name,a.team_name,a.number_text,a.article].join('|').localeCompare([b.personalization_name,b.team_name,b.number_text,b.article].join('|'),'de',{numeric:true}));}
function currentSeriesTask(){return centralProductionMonitorTasks.find(t=>String(t.id)===String(state.selectedTaskId))||null;}
function expectedFile(task={}){
  const raw=String(task.motif||'Motiv').replace(/\.(tap|dst)$/i,'').trim(),personal=String(task.personalization_name||task.team_name||task.number_text||'').trim();
  return `${raw}${personal?'_'+personal.replace(/[^\p{L}\p{N}._-]+/gu,'_'):''}.TAP`;
}
function selectNextSize(size){const task=seriesTasksForSize(size)[0];state.selectedTaskId=String(task?.id||'');renderCentralProductionMonitor();}
function slotName(i){return workplaceMode()==='embroidery'?(machines[i]?.name||`Maschine ${i+1}`):`Transferplatz ${i+1}`;}
function assignTransferTask(task,index,fileName=''){
  const list=slots();list[index]={task_id:String(task.id),order_id:String(task.order_id||''),file_name:fileName||expectedFile(task),assigned_at:new Date().toISOString()};saveStateSoon();state.selectedTaskId='';
}
function startAtSlot(index){
  const task=currentSeriesTask();if(!task)return;if(slots()[index]){alert(`${slotName(index)} ist bereits belegt.`);return;}
  if(workplaceMode()==='embroidery'){
    state.returnToMonitor=true;state.pendingSlot=index;selectedTransferMachines.clear();selectedTransferMachines.add(index);transferSelectionInitialized=true;renderTransferMachineButtons();openTransferWorkflow(task);
    setTimeout(()=>{const q=$('#fileSearch');if(q){q.value=task.personalization_name||task.team_name||task.motif||'';q.dispatchEvent(new Event('input',{bubbles:true}));}},80);
  }else{assignTransferTask(task,index,'Transferauftrag');renderCentralProductionMonitor();}
}
async function finishSlot(index){
  const s=slots()[index];if(!s)return;const task=centralProductionMonitorTasks.find(t=>String(t.id)===String(s.task_id));if(!task){slots()[index]=null;saveStateSoon();renderCentralProductionMonitor();return;}
  slots()[index]=null;saveStateSoon();await changeCentralTask(task.id,1);await reloadCentralProductionMonitor();
}
function renderSeriesMonitor(){
  const o=centralProductionMonitorOrder,physical=physicalTextileProgress(centralProductionMonitorTasks),total=physical.target,done=physical.done;
  $('#openNewProduction')?.classList.add('hidden');$('#toggleRunning')?.classList.add('hidden');$('#runningProductionList')?.classList.add('hidden');$('#completedProductions')?.closest('.completed-panel')?.classList.add('hidden');$('#activeProductionEmpty')?.classList.add('hidden');$('#activeProduction')?.classList.remove('hidden');
  $('#prodTitle').textContent=o.order_no||o.title||'Auftrag';$('#prodMeta').textContent=[o.customer||'',o.title&&o.title!==o.order_no?o.title:'',centralDueText(o.due_date)].filter(Boolean).join(' · ');$('#prodNeedles')?.classList.add('hidden');$('#prodTotalText').textContent=`${done} / ${total}`;$('#prodTotalBar').style.width=`${total?Math.min(100,done/total*100):0}%`;$('#prodRemaining').textContent=Math.max(0,total-done);
  const bySize=new Map();for(const g of physical.groups.values()){const size=sizeKey(g.sample);if(!bySize.has(size))bySize.set(size,{target:0,done:0});const x=bySize.get(size);x.target+=g.target;x.done+=Math.min(g.completed,g.target);}
  const selected=currentSeriesTask(),grid=$('#sizeGrid');grid.innerHTML=`<section class="hca1324-series"><div class="hca1324-size-overview"><div class="hca1324-section-title"><span class="eyebrow">SERIENPRODUKTION</span><h3>Größenübersicht</h3></div><div class="hca1324-size-buttons">${[...bySize.entries()].map(([size,x])=>`<button type="button" data-series-size="${escapeHtml(size)}" class="${selected&&sizeKey(selected)===size?'active':''}" ${x.done>=x.target?'disabled':''}><strong>${escapeHtml(size)}</strong><span>${x.done} fertig · ${Math.max(0,x.target-x.done)} offen</span></button>`).join('')}</div></div><div class="hca1324-next">${selected?`<div><span class="eyebrow">NÄCHSTES TEXTIL</span><h3>${escapeHtml(selected.article||'Artikel')} · Größe ${escapeHtml(sizeKey(selected))}</h3><p>${[selected.team_name,selected.personalization_name,selected.number_text&&`Nr. ${selected.number_text}`,selected.position].filter(Boolean).map(escapeHtml).join(' · ')||'Ohne zusätzliche Personalisierung'}</p><div class="hca1324-file"><span>Vorgeschlagene Stickdatei</span><strong>${escapeHtml(expectedFile(selected))}</strong></div></div><div class="hca1324-start-buttons">${slots().map((s,i)=>`<button type="button" data-series-start="${i}" ${s||(workplaceMode()==='embroidery'&&!machines[i]?.connected)?'disabled':''}>${escapeHtml(slotName(i))}</button>`).join('')}</div>`:'<div class="hca1324-empty">Eine Größe anklicken, um das nächste Textil und die passende Datei aufzurufen.</div>'}</div><div class="hca1324-machine-board">${slots().map((s,i)=>{const t=s&&centralProductionMonitorTasks.find(x=>String(x.id)===String(s.task_id));return `<button type="button" class="hca1324-machine-slot ${s?'occupied':''}" data-series-finish="${i}" ${s?'':'disabled'}><span>${escapeHtml(slotName(i))}</span>${s&&t?`<strong>${escapeHtml(t.article||'Artikel')} · ${escapeHtml(sizeKey(t))}</strong><small>${[t.personalization_name,t.team_name,t.number_text&&`Nr. ${t.number_text}`].filter(Boolean).map(escapeHtml).join(' · ')||escapeHtml(s.file_name||'')}</small><em>Antippen: fertigmelden, Etikett drucken und Versand prüfen</em>`:'<strong>Frei</strong><small>Keine laufende Position</small>'}</button>`;}).join('')}</div></section>`;
  grid.querySelectorAll('[data-series-size]').forEach(b=>b.addEventListener('click',()=>selectNextSize(b.dataset.seriesSize)));grid.querySelectorAll('[data-series-start]').forEach(b=>b.addEventListener('click',()=>startAtSlot(Number(b.dataset.seriesStart))));grid.querySelectorAll('[data-series-finish]').forEach(b=>b.addEventListener('click',()=>finishSlot(Number(b.dataset.seriesFinish))));
  $('#pauseProduction').disabled=false;$('#pauseProduction').textContent='Produktionsmonitor schließen';$('#finishProduction').disabled=false;$('#finishProduction').textContent='Produktion abschließen';
}
const baseRenderCentralProductionMonitor=renderCentralProductionMonitor;
renderCentralProductionMonitor=function(){if(centralProductionMonitorOrder&&isSeriesOrder())return renderSeriesMonitor();return baseRenderCentralProductionMonitor();};

const baseSendPatternToMachines=sendPatternToMachines;
sendPatternToMachines=async function(targetIndexes){
  const task=transferWorkflowTask,index=Number(state.pendingSlot),before=(appState.inventory||[]).map(list=>(list||[]).map(x=>`${x.key}|${x.transferredAt}`).join(';'));
  await baseSendPatternToMachines(targetIndexes);
  if(!task||!Number.isInteger(index))return;const after=(appState.inventory||[]).map(list=>(list||[]).map(x=>`${x.key}|${x.transferredAt}`).join(';'));
  if(targetIndexes.includes(index)&&before[index]!==after[index]){assignTransferTask(task,index,selectedFile?.name||'');state.pendingSlot=null;alert(`${selectedFile?.name||'Stickdatei'} wurde ${slotName(index)} und dem nächsten Textil zugeordnet.`);}
};
const baseBackToWorkbenchFromTransfer=backToWorkbenchFromTransfer;
backToWorkbenchFromTransfer=function(){if(state.returnToMonitor&&centralProductionMonitorOrder){state.returnToMonitor=false;transferWorkflowTask=null;$('#transferWorkflowContext')?.classList.add('hidden');showView('production');renderCentralProductionMonitor();return;}baseBackToWorkbenchFromTransfer();};

window.HCA01324={version:V,customerRecipient,orderRecipient,expectedFile,isSeriesOrder};
})();
