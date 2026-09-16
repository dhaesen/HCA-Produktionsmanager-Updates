/* HCA v0.13.25 · gemeinsame Positionsmaske und automatische Shoppreise */
(()=>{
'use strict';

const VERSION='0.13.25';
const priceState=new WeakMap();

/* Die ältere Maske hatte bereits einen stillen change-Handler. Er zeigte
   Fehler nicht an und konnte parallel zu einer neuen Eingabe laufen. Die
   Eingabefelder selbst bleiben unverändert gebunden; nur dieser alte
   Preis-Timer wird durch die zentrale, entprellte Routine unten ersetzt. */
if(typeof window.hcaV121SchedulePrice==='function')window.hcaV121SchedulePrice=()=>{};

function stateFor(line){
  let state=priceState.get(line);
  if(!state){state={revision:0,timer:0,status:'',message:''};priceState.set(line,state)}
  return state;
}

function lineIndexFrom(element){
  const direct=element?.dataset?.bqIndex;
  if(direct!==undefined)return Number(direct);
  for(const key of ['bqStepAdd','bqStepRemove','bqStepColors','hcaStepArea','hcaStepMethod','hcaStepManual']){
    const value=element?.dataset?.[key];
    if(value!==undefined)return Number(String(value).split(':')[0]);
  }
  return -1;
}

function statusText(state){
  if(state.status==='loading')return 'Shoppreise werden automatisch aktualisiert …';
  if(state.status==='ok')return 'Shoppreise automatisch aktualisiert';
  if(state.status==='error')return `Automatische Preisaktualisierung fehlgeschlagen: ${state.message}`;
  return '';
}

function paintStatus(host,line,index){
  const card=host?.querySelector?.(`[data-bq-line="${index}"]`);
  if(!card)return;
  let status=card.querySelector?.('.hca1325-price-status');
  const state=stateFor(line),text=statusText(state);
  if(!text){status?.remove?.();return}
  if(!status){
    status=document.createElement('div');
    status.className='hca1325-price-status';
    card.querySelector?.('.business-quote-line-head')?.append?.(status);
  }
  if(status){status.className=`hca1325-price-status ${state.status}`;status.textContent=text}
}

function schedulePrice(line,rerender,host,key,delay=360){
  if(!line?.product_id)return;
  const state=stateFor(line),revision=++state.revision;
  clearTimeout(state.timer);
  state.status='loading';state.message='';
  const lines=host?.id==='businessQuoteEditor'?(activeBusinessQuote?.items||[]):host?.id==='businessOrderLines'?(HCA103?.orderLines||[]):host?.id==='financeInvoiceLines'?(financeInvoiceLines||[]):[];
  const initialIndex=lines.indexOf(line);if(initialIndex>=0)paintStatus(host,line,initialIndex);
  state.timer=setTimeout(async()=>{
    try{
      await window.hca103ShopPrice(line);
      if(state.revision!==revision){schedulePrice(line,rerender,host,key,80);return}
      state.status='ok';state.message='';
      if(typeof hcaEditorDirty!=='undefined'&&host?.id==='businessQuoteEditor')hcaEditorDirty=true;
      rerender();
    }catch(error){
      if(state.revision!==revision)return;
      state.status='error';state.message=error?.message||String(error);
      const current=host?.id==='businessQuoteEditor'?(activeBusinessQuote?.items||[]):host?.id==='businessOrderLines'?(HCA103?.orderLines||[]):host?.id==='financeInvoiceLines'?(financeInvoiceLines||[]):[];
      const currentIndex=current.indexOf(line);if(currentIndex>=0)paintStatus(host,line,currentIndex);
    }
  },delay);
}

function bindAutomaticPricing(host,lines,rerender){
  if(!host)return;
  const scheduleElement=element=>{
    const index=lineIndexFrom(element),line=lines[index];
    if(!line?.product_id)return;
    schedulePrice(line,rerender,host,`${host.id}:${index}`);
  };
  host.querySelectorAll('[data-bq-field="quantity"],[data-bq-size],[data-bq-step-colors]').forEach(element=>{
    element.addEventListener('input',()=>scheduleElement(element));
  });
  host.querySelectorAll('[data-hca-step-area],[data-hca-step-method]').forEach(element=>{
    element.addEventListener('change',()=>scheduleElement(element));
  });
  host.querySelectorAll('[data-hca-step-manual]').forEach(element=>{
    element.addEventListener('change',()=>{if(!element.checked)scheduleElement(element)});
  });
  host.querySelectorAll('[data-bq-step-add],[data-bq-step-remove]').forEach(element=>{
    element.addEventListener('click',()=>scheduleElement(element));
  });
  lines.forEach((line,index)=>paintStatus(host,line,index));
}

function renderSharedLines(host,lines,rerender){
  if(!host)return;
  host.innerHTML=lines.map((line,index)=>window.hcaUnifiedPositionHtml(line,index,false)).join('');
  window.hcaBindPositionForm(host,lines,rerender);
  window.hcaV121BindWizardControls(host,lines,rerender);
  bindAutomaticPricing(host,lines,rerender);
}

/* Auftrag und Kundenrechnung verwenden bewusst denselben Kernrenderer und
   dieselben WooCommerce-Wizard-Steuerelemente wie das Angebot. */
window.hca103RenderOrderLines=function(){
  const host=document.querySelector('#businessOrderLines');
  renderSharedLines(host,HCA103.orderLines,window.hca103RenderOrderLines);
};

window.renderFinanceInvoiceLines=function(){
  const host=document.querySelector('#financeInvoiceLines');
  financeInvoiceLines=financeInvoiceLines.map(financeNewLine);
  renderSharedLines(host,financeInvoiceLines,window.renderFinanceInvoiceLines);
};

const previousQuoteRender=window.renderBusinessQuoteEditor;
window.renderBusinessQuoteEditor=function(...args){
  const result=previousQuoteRender.apply(this,args);
  bindAutomaticPricing(document.querySelector('#businessQuoteEditor'),activeBusinessQuote?.items||[],window.renderBusinessQuoteEditor);
  return result;
};

window.HCA01325={VERSION,lineIndexFrom,schedulePrice,bindAutomaticPricing,renderSharedLines};
})();
