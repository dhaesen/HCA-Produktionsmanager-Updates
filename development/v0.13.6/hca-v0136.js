/* HCA v0.13.6 · Angebotsstaffeln, Produktionsart, Verpackungseinheiten und Adressprüfung */
(()=>{
'use strict';
const H136={taskSettings:new Map(),addressTimers:new Map(),lastProductionChoice:''};
const clone=v=>JSON.parse(JSON.stringify(v||{}));
const hasRefinements=items=>(items||[]).some(x=>Array.isArray(x?.config?.production_steps)&&x.config.production_steps.length);
function parseTiers(value){
  return [...new Set(String(value||'').split(/[,;\s]+/).map(Number).filter(x=>Number.isFinite(x)&&x>0).map(Math.round))].sort((a,b)=>a-b);
}
function quoteTiers(){
  const q=activeBusinessQuote||{};
  const own=parseTiers(q.quantity_tiers||[]);
  if(own.length)return own;
  for(const line of q.items||[]){const tiers=parseTiers(line?.config?.quote_quantity_tiers?.map(x=>x.quantity)||[]);if(tiers.length)return tiers}
  return [];
}
async function chooseProductionMode(){
  if(await hcaConfirm('Der Auftrag enthält Veredelungen.\n\nSoll die Veredelung in der Eigenproduktion gefertigt werden?'))return 'inhouse';
  if(await hcaConfirm('Soll die Veredelung als Lieferantenproduktion geführt werden?'))return 'supplier';
  return '';
}
async function buildTierSnapshots(){
  const el=document.querySelector('#hca136QuoteTiers');
  const tiers=parseTiers(el?.value||quoteTiers());
  if(activeBusinessQuote)activeBusinessQuote.quantity_tiers=tiers;
  if(!tiers.length){for(const l of activeBusinessQuote?.items||[])if(l.config)delete l.config.quote_quantity_tiers;return}
  const status=document.querySelector('#hca136TierStatus');
  if(status)status.textContent='Staffelpreise werden berechnet …';
  for(const line of activeBusinessQuote?.items||[]){
    line.config=line.config||{};
    if(line.item_type==='text'||line.item_type==='optional'){line.config.quote_quantity_tiers=[];continue}
    const snapshots=[];
    for(const quantity of tiers){
      const candidate=clone(line);candidate.quantity=quantity;candidate.config=candidate.config||{};
      if(candidate.config.sizes&&Object.keys(candidate.config.sizes).length){
        candidate.config.sizes={};candidate.config.size='';
      }
      try{if(candidate.product_id&&typeof hca103ShopPrice==='function')await hca103ShopPrice(candidate)}catch{}
      const amount=businessQuoteLineAmounts(candidate);
      snapshots.push({quantity,unit_price:Number(candidate.unit_price)||0,net:Number(amount.net)||0,tax:Number(amount.tax)||0,gross:Number(amount.gross)||0,production_steps:clone(candidate.config.production_steps||[])});
    }
    line.config.quote_quantity_tiers=snapshots;
  }
  if(status)status.textContent=tiers.length?tiers.length+' Mengenstaffeln berechnet.':'';
}
function tierPreviewHtml(){
  const tiers=quoteTiers();if(!tiers.length)return '';
  const rows=tiers.map(q=>{
    let net=0,tax=0,gross=0;
    for(const line of activeBusinessQuote?.items||[]){
      const s=(line?.config?.quote_quantity_tiers||[]).find(x=>Number(x.quantity)===q);
      if(s){net+=Number(s.net)||0;tax+=Number(s.tax)||0;gross+=Number(s.gross)||0}
    }
    return '<tr><td>'+q.toLocaleString('de-DE')+'</td><td>'+businessMoney(net)+'</td><td>'+businessMoney(tax)+'</td><td><b>'+businessMoney(gross)+'</b></td></tr>';
  }).join('');
  return '<table class="hca136-tier-table"><thead><tr><th>Menge</th><th>Netto</th><th>MwSt.</th><th>Brutto</th></tr></thead><tbody>'+rows+'</tbody></table>';
}
function enhanceCustomerCombo(){
  const select=document.querySelector('#bqCustomer');if(!select||document.querySelector('#hca136CustomerSearch'))return;
  const wrap=document.createElement('div');wrap.className='hca136-customer-combo';
  const input=document.createElement('input');input.id='hca136CustomerSearch';input.className='text-input';input.setAttribute('list','hca136CustomerList');input.placeholder='Kundennummer, Firma, Vorname, Nachname oder E-Mail suchen …';
  const list=document.createElement('datalist');list.id='hca136CustomerList';
  const customers=businessCustomerCache||[];
  list.innerHTML=customers.map(c=>'<option value="'+escapeHtml((c.customer_no||'')+' · '+businessCustomerDisplay(c))+'"></option>').join('');
  const selected=customers.find(c=>String(c.id)===String(select.value));if(selected)input.value=(selected.customer_no||'')+' · '+businessCustomerDisplay(selected);
  const selectParent=select.parentNode;if(!selectParent)return;
  selectParent.insertBefore(wrap,select);wrap.append(input,list,select);select.classList.add('hca136-combo-fallback');
  const apply=()=>{
    const needle=String(input.value||'').trim().toLowerCase();
    const exact=customers.find(c=>((c.customer_no||'')+' · '+businessCustomerDisplay(c)).toLowerCase()===needle);
    const partial=exact||customers.find(c=>[c.customer_no,c.company_name,c.first_name,c.last_name,c.email,businessCustomerDisplay(c)].join(' ').toLowerCase().includes(needle));
    if(partial){select.value=partial.id;select.dispatchEvent(new Event('change',{bubbles:true}));input.setCustomValidity('')}else if(needle){input.setCustomValidity('Bitte einen Kunden aus der Trefferliste wählen.')}
  };
  input.addEventListener('change',apply);input.addEventListener('blur',apply);
}
const oldRenderQuote=window.renderBusinessQuoteEditor;
window.renderBusinessQuoteEditor=function(){
  oldRenderQuote();
  const head=document.querySelector('.business-document-head');if(!head)return;
  const intro=document.querySelector('#bqIntro')?.parentElement;
  const panel=document.createElement('div');panel.className='hca136-tier-panel';
  panel.innerHTML='<label>Mengenstaffel</label><div class="hca136-tier-row"><input class="text-input" id="hca136QuoteTiers" placeholder="z. B. 500, 1000, 1500" value="'+escapeHtml(quoteTiers().join(', '))+'"><button class="btn secondary" id="hca136CalculateTiers" type="button">Staffelpreise berechnen</button></div><small id="hca136TierStatus">Mehrere alternative Angebotsmengen; nur eine Staffel wird später beauftragt.</small><div id="hca136TierPreview">'+tierPreviewHtml()+'</div>';
  // Bei älteren Angeboten kann das Einleitungsfeld in einer Untergruppe liegen.
  // insertBefore akzeptiert aber ausschließlich ein direktes Kind von `head`.
  if(intro?.parentNode===head)head.insertBefore(panel,intro);else head.appendChild(panel);
  document.querySelector('#hca136CalculateTiers')?.addEventListener('click',async()=>{await buildTierSnapshots();document.querySelector('#hca136TierPreview').innerHTML=tierPreviewHtml();hcaEditorDirty=true});
  document.querySelector('#hca136QuoteTiers')?.addEventListener('change',e=>{activeBusinessQuote.quantity_tiers=parseTiers(e.target.value);hcaEditorDirty=true});
  enhanceCustomerCombo();
};
const oldPayload=window.businessQuotePayload;
window.businessQuotePayload=function(){
  const p=oldPayload();const tiers=parseTiers(document.querySelector('#hca136QuoteTiers')?.value||quoteTiers());
  p.quantity_tiers=tiers;p.items=(p.items||[]).map(x=>({...x,config:{...(x.config||{}),quote_tier_quantities:tiers}}));return p;
};
const oldSaveQuote=window.saveBusinessQuote;
window.saveBusinessQuote=async function(){await buildTierSnapshots();return oldSaveQuote()};
window.convertBusinessQuoteToOrder=async function(){
  if(!activeBusinessQuote?.id)return;
  let productionMode='';
  if(hasRefinements(activeBusinessQuote.items)){
    productionMode=await chooseProductionMode();if(!productionMode)return;
    for(const item of activeBusinessQuote.items||[]){item.config=item.config||{};item.config.production_mode=productionMode}
    await saveBusinessQuote();if(!activeBusinessQuote?.id)return;
  }
  const tiers=quoteTiers();let selectedTier=0;
  if(tiers.length){
    const entered=await hcaPrompt('Welche Angebotsmenge soll beauftragt werden?\\n\\nVerfügbare Staffeln: '+tiers.join(', '),String(tiers[0]));
    if(entered===null)return;selectedTier=Math.round(Number(entered)||0);
    if(!tiers.includes(selectedTier)){alert('Bitte eine der angebotenen Mengen wählen: '+tiers.join(', '));return}
  }
  if(!await hcaConfirm('Angebot '+(activeBusinessQuote.quote_no||'')+' annehmen und daraus einen kaufmännischen Auftrag erstellen?'+(selectedTier?'\\n\\nGewählte Menge: '+selectedTier:'')))return;
  const due=await window.hcaPickDate('');if(due===null)return;
  try{
    const d=await businessApi('/sales/quotes/'+encodeURIComponent(activeBusinessQuote.id)+'/convert-to-order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({due_date:due||'',production_mode:productionMode,selected_quantity_tier:selectedTier||null})});
    await Promise.all([loadBusinessQuotes(),loadBusinessSalesOrders(),loadBusinessDashboard()]);await openBusinessSalesOrder(d.item.id);
  }catch(err){alert('Auftrag konnte nicht erstellt werden:\n'+(err.message||err))}
};
const oldSaveOrder=window.hcaSaveOrderV12;
window.hcaSaveOrderV12=async function(status='confirmed'){
  if(hasRefinements(HCA103.orderLines)&&!(HCA103.orderLines||[]).some(x=>x?.config?.production_mode)){
    const mode=await chooseProductionMode();if(!mode)return;
    for(const item of HCA103.orderLines||[]){item.config=item.config||{};item.config.production_mode=mode}
  }
  return oldSaveOrder(status);
};
const oldOrderLineHtml=window.hca103OrderLineHtml;
window.hca103OrderLineHtml=function(line,index){
  const html=oldOrderLineHtml(line,index),unit=Math.max(1,Number(line?.config?.packaging_unit)||1);
  return html.replace('</div>','<div class="hca136-package-field"><label>Verpackungseinheit</label><input class="text-input" type="number" min="1" step="1" data-o-package="'+index+'" value="'+unit+'"><small>Fertigmeldung und Etikett je Verpackungseinheit</small></div></div>');
};
document.addEventListener('input',e=>{const i=e.target?.dataset?.oPackage;if(i!==undefined&&HCA103.orderLines?.[Number(i)]){HCA103.orderLines[Number(i)].config.packaging_unit=Math.max(1,Math.round(Number(e.target.value)||1));hcaEditorDirty=true}},true);
const oldOrderDetail=window.renderBusinessSalesOrderDetail;
window.renderBusinessSalesOrderDetail=function(o,material,productionOrders,invoices=[]){
  oldOrderDetail(o,material,productionOrders,invoices);
  const refined=hasRefinements(o.items),mode=(o.items||[]).map(x=>x?.config?.production_mode).find(Boolean)||'';
  const actions=document.querySelector('#businessSalesOrderTopActions');
  const create=document.querySelector('#businessCreateProductionOrders');
  if(refined&&mode==='supplier'){
    create?.remove();actions?.insertAdjacentHTML('afterend','<div class="hca136-production-note supplier"><b>Lieferantenproduktion</b><span>Für diesen Auftrag wird kein Eigenproduktionsauftrag vorgeschlagen.</span></div>');
  }else if(refined&&mode==='inhouse'){
    create?.classList.add('hca136-suggested');create?.setAttribute('title','Vorschlag aus den im Auftrag enthaltenen Veredelungen');
    actions?.insertAdjacentHTML('afterend','<div class="hca136-production-note"><b>Vorschlag: Eigenproduktion</b><span>Die enthaltenen Veredelungen können jetzt als Produktionsaufträge erzeugt werden.</span></div>');
  }
};
function packageForTask(task){return Math.max(1,Number(H136.taskSettings.get(String(task?.id))||task?.packaging_unit||1));}
async function savePackage(taskId,value){
  const unit=Math.max(1,Math.round(Number(value)||1));H136.taskSettings.set(String(taskId),unit);
  try{await businessApi('/production/task-settings/'+encodeURIComponent(taskId),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({packaging_unit:unit})})}catch{}
}
async function loadTaskSettings(){
  try{const d=await businessApi('/production/task-settings');H136.taskSettings=new Map((d.items||[]).map(x=>[String(x.task_id),Math.max(1,Number(x.packaging_unit)||1)]))}catch{}
}
function enhanceTaskCards(){
  document.querySelectorAll('[data-task-id]').forEach(card=>{
    const id=card.dataset.taskId,task=(centralTasksCache||[]).find(x=>String(x.id)===String(id));if(!task||card.querySelector('[data-h136-package]'))return;
    const actions=card.querySelector('.work-task-actions');if(!actions)return;
    actions.insertAdjacentHTML('beforebegin','<label class="hca136-task-package">Verpackungseinheit <input class="text-input" type="number" min="1" step="1" data-h136-package="'+escapeHtml(id)+'" value="'+packageForTask(task)+'"> Stück</label>');
  });
  document.querySelectorAll('[data-central-task-id]').forEach(btn=>{
    const id=btn.dataset.centralTaskId,task=(centralProductionMonitorTasks||[]).find(x=>String(x.id)===String(id)),card=btn.closest('.size-card');if(!task||!card||card.querySelector('[data-h136-package]'))return;
    card.insertAdjacentHTML('beforeend','<label class="hca136-task-package">VE <input class="text-input" type="number" min="1" step="1" data-h136-package="'+escapeHtml(id)+'" value="'+packageForTask(task)+'"> Stück</label>');
  });
}
const oldRenderWorkbench=window.renderWorkbench;
window.renderWorkbench=function(){oldRenderWorkbench();enhanceTaskCards()};
const oldRenderCentralMonitor=window.renderCentralProductionMonitor;
if(oldRenderCentralMonitor)window.renderCentralProductionMonitor=function(){oldRenderCentralMonitor();enhanceTaskCards()};
document.addEventListener('change',e=>{if(e.target?.matches('[data-h136-package]'))savePackage(e.target.dataset.h136Package,e.target.value)},true);
document.addEventListener('click',e=>{
  const plus=e.target.closest('[data-task-plus],[data-central-task-action="plus"]');if(!plus)return;
  const id=plus.dataset.taskPlus||plus.dataset.centralTaskId;
  const task=(centralProductionMonitorTasks||[]).find(x=>String(x.id)===String(id))||(centralTasksCache||[]).find(x=>String(x.id)===String(id));
  const unit=packageForTask(task),remaining=Math.max(0,(Number(task?.target_qty)||0)-(Number(task?.done_qty)||0)),delta=Math.min(unit,remaining||unit);
  if(delta<=1)return;
  e.preventDefault();e.stopImmediatePropagation();
  changeCentralTask(id,delta).then(()=>{if(typeof reloadCentralProductionMonitor==='function'&&centralProductionMonitorOrder)return reloadCentralProductionMonitor()});
},true);
const oldLoadWorkbench=window.loadWorkbench;
window.loadWorkbench=async function(){await loadTaskSettings();return oldLoadWorkbench()};
function bindPostal(zipId,cityId,streetId,countryId){
  const zip=document.querySelector(zipId),city=document.querySelector(cityId),street=document.querySelector(streetId),country=document.querySelector(countryId);if(!zip||zip.dataset.h136Postal)return;zip.dataset.h136Postal='1';
  const status=document.createElement('small');status.className='hca136-address-status';zip.parentElement.appendChild(status);
  const lookup=async()=>{
    const postal=String(zip.value||'').trim(),cc=String(country?.value||'DE').trim().toUpperCase();if(cc==='DE'&&!/^\d{5}$/.test(postal)){status.textContent=postal?'Bitte eine fünfstellige deutsche PLZ eingeben.':'';status.classList.toggle('error',!!postal);return}
    if(!postal)return;
    try{const d=await businessApi('/address/lookup?country='+encodeURIComponent(cc)+'&postal_code='+encodeURIComponent(postal)+(street?.value?'&street='+encodeURIComponent(street.value):''));const cities=d.cities||[];if(cities.length===1&&!city.value)city.value=cities[0];if(city.value&&cities.length&&!cities.some(x=>x.toLowerCase()===city.value.trim().toLowerCase())){status.textContent='PLZ und Ort passen nicht zusammen.';status.classList.add('error')}else{status.textContent=cities.length?'✓ '+cities.join(', '):'PLZ konnte online nicht bestätigt werden.';status.classList.remove('error')}if(street&&Array.isArray(d.streets)){let dl=document.querySelector('#h136Streets');if(!dl){dl=document.createElement('datalist');dl.id='h136Streets';document.body.appendChild(dl)}dl.innerHTML=d.streets.slice(0,100).map(x=>'<option value="'+escapeHtml(x)+'"></option>').join('');street.setAttribute('list','h136Streets')}}catch{status.textContent='Adressprüfung vorübergehend nicht verfügbar.';status.classList.remove('error')}
  };
  zip.addEventListener('blur',lookup);city.addEventListener('blur',lookup);street?.addEventListener('input',()=>{clearTimeout(H136.addressTimers.get(streetId));H136.addressTimers.set(streetId,setTimeout(lookup,450))});
}
function bindAllPostal(){
  bindPostal('#bcShipZip','#bcShipCity','#bcShipStreet','#bcShipCountry');
  bindPostal('#bcBillZip','#bcBillCity','#bcBillStreet','#bcBillCountry');
  bindPostal('#bcaZip','#bcaCity','#bcaStreet','#bcaCountry');
  bindPostal('#centralShipPostal','#centralShipCity','#centralShipStreet','#centralShipCountry');
}
new MutationObserver(bindAllPostal).observe(document.documentElement,{childList:true,subtree:true});bindAllPostal();loadTaskSettings();
})();
