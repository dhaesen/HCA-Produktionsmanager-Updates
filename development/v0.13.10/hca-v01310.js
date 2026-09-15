/* HCA v0.13.10 · alternative Angebotsmengen als optionale Positionen */
(()=>{
'use strict';
const H1310={busy:false};
const clone=value=>JSON.parse(JSON.stringify(value||{}));
const esc=value=>typeof escapeHtml==='function'?escapeHtml(String(value??'')):String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function quantities(value){
  const source=Array.isArray(value)?value:String(value||'').split(/[,;\s]+/);
  return [...new Set(source.map(Number).filter(x=>Number.isFinite(x)&&x>0).map(Math.round))].sort((a,b)=>a-b);
}
function isBasePromotional(line){
  const cfg=line?.config||{};
  return String(line?.item_type||'product').toLowerCase()==='product'&&String(cfg.product_type||'').toLowerCase()==='promotional'&&!cfg.quantity_option_generated;
}
function ensureGroup(line){line.config=line.config||{};if(!line.config.quantity_option_group)line.config.quantity_option_group=crypto.randomUUID?.()||('qopt-'+Date.now()+'-'+Math.random());return line.config.quantity_option_group}
function clearLegacyTiers(){
  if(!activeBusinessQuote)return;activeBusinessQuote.quantity_tiers=[];
  for(const line of activeBusinessQuote.items||[]){line.config=line.config||{};delete line.config.quote_tier_quantities;delete line.config.quote_quantity_tiers}
}
function alternativeHtml(line,index,locked){
  if(!isBasePromotional(line))return '';
  ensureGroup(line);const values=quantities(line.config.alternative_offer_quantities||[]);
  const rows=values.map((value,row)=>'<div class="hca1310-quantity-row"><input class="text-input" type="number" min="1" step="1" data-h1310-quantity="'+index+':'+row+'" value="'+value+'" '+(locked?'disabled':'')+'><span>Stück</span>'+(locked?'':'<button class="btn danger compact" type="button" data-h1310-remove="'+index+':'+row+'" title="Menge entfernen">×</button>')+'</div>').join('');
  return '<div class="hca1310-alternatives"><div><b>Weitere Angebotsmengen</b><small>Jede weitere Menge wird als optionale Position einschließlich der Veredelungen berechnet.</small></div><div class="hca1310-quantity-list" data-h1310-list="'+index+'">'+rows+'</div>'+(locked?'':'<div class="hca1310-actions"><button class="btn secondary compact" type="button" data-h1310-add="'+index+'">+ Weitere Menge</button><button class="btn primary compact" type="button" data-h1310-update="'+index+'">Optionale Positionen aktualisieren</button></div>')+'</div>';
}
const previousLineHtml=window.businessQuoteLineHtml;
window.businessQuoteLineHtml=function(line,index,locked=false){
  let html=previousLineHtml(line,index,locked);
  html=html.replace(/<section class="hca139-line-tiers">[\s\S]*?<\/section>/g,'');
  const extra=alternativeHtml(line,index,locked);if(!extra)return html;
  const quantityBlock=/<div class="business-line-section business-qty-row">[\s\S]*?<\/div>/;
  return quantityBlock.test(html)?html.replace(quantityBlock,match=>match+extra):html.replace('<div class="business-quote-line-sum">',extra+'<div class="business-quote-line-sum">');
};
function removeObsoleteControls(){document.querySelector('.hca136-tier-panel')?.remove();document.querySelectorAll('.hca139-line-tiers').forEach(x=>x.remove())}
const previousRender=window.renderBusinessQuoteEditor;
window.renderBusinessQuoteEditor=function(){clearLegacyTiers();previousRender();removeObsoleteControls()};

function collect(index){return quantities([...document.querySelectorAll('[data-h1310-quantity^="'+index+':"]')].map(x=>x.value))}
async function rebuildOptions(base,requested){
  if(!activeBusinessQuote||!base)return;
  const group=ensureGroup(base),all=activeBusinessQuote.items||[],baseIndex=all.indexOf(base);if(baseIndex<0)return;
  const values=quantities(requested).filter(value=>value!==Math.round(Number(base.quantity)||0));
  base.config.alternative_offer_quantities=values;
  const remaining=all.filter(line=>!(line?.config?.quantity_option_generated&&line.config.quantity_option_group===group));
  const insertAt=remaining.indexOf(base)+1,generated=[];
  for(const value of values){
    const option=clone(base);option.id='';option.item_type='optional';option.quantity=value;option.config=clone(base.config);option.config.quantity_option_generated=true;option.config.quantity_option_group=group;option.config.quantity_option_value=value;option.config.alternative_offer_quantities=[];option.config.datasheet_enabled=false;option.config.datasheet_images=[];
    delete option.config.quote_tier_quantities;delete option.config.quote_quantity_tiers;
    if(option.config.sizes&&Object.keys(option.config.sizes).length){option.config.sizes={};option.config.size=''}
    try{if(option.product_id&&typeof hca103ShopPrice==='function')await hca103ShopPrice(option)}catch(error){option.config.shop_price_error=error?.message||String(error)}
    generated.push(option);
  }
  remaining.splice(insertAt,0,...generated);activeBusinessQuote.items=remaining;hcaEditorDirty=true;
}
async function updateIndex(index,rerender=true){
  const base=activeBusinessQuote?.items?.[index];if(!isBasePromotional(base))return;
  const button=document.querySelector('[data-h1310-update="'+index+'"]');if(button){button.disabled=true;button.textContent='Preise werden berechnet …'}
  await rebuildOptions(base,collect(index));if(rerender)renderBusinessQuoteEditor();
}
document.addEventListener('click',event=>{
  const add=event.target.closest('[data-h1310-add]');
  if(add){event.preventDefault();const index=Number(add.dataset.h1310Add),list=document.querySelector('[data-h1310-list="'+index+'"]');if(!list)return;const row=list.children.length;list.insertAdjacentHTML('beforeend','<div class="hca1310-quantity-row"><input class="text-input" type="number" min="1" step="1" data-h1310-quantity="'+index+':'+row+'" placeholder="Weitere Menge"><span>Stück</span><button class="btn danger compact" type="button" data-h1310-remove="'+index+':'+row+'" title="Menge entfernen">×</button></div>');list.lastElementChild?.querySelector('input')?.focus();return}
  const remove=event.target.closest('[data-h1310-remove]');
  if(remove){event.preventDefault();const index=Number(String(remove.dataset.h1310Remove).split(':')[0]);remove.closest('.hca1310-quantity-row')?.remove();updateIndex(index);return}
  const update=event.target.closest('[data-h1310-update]');if(update){event.preventDefault();updateIndex(Number(update.dataset.h1310Update))}
},true);
document.addEventListener('change',event=>{
  if(event.target?.dataset?.h1310Quantity===undefined)return;
  const index=Number(String(event.target.dataset.h1310Quantity).split(':')[0]);updateIndex(index);
},true);

const previousSave=window.saveBusinessQuote;
window.saveBusinessQuote=async function(){
  if(H1310.busy)return;H1310.busy=true;
  try{
    clearLegacyTiers();
    const bases=(activeBusinessQuote?.items||[]).filter(isBasePromotional);
    for(const base of bases)await rebuildOptions(base,quantities(base.config?.alternative_offer_quantities||[]));
    clearLegacyTiers();return await previousSave();
  }finally{H1310.busy=false}
};
clearLegacyTiers();removeObsoleteControls();
})();
