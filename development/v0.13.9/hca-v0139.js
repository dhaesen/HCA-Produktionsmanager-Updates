/* HCA v0.13.9 · positionsbezogene Mengenstaffeln */
(()=>{
'use strict';
const H139={pending:null,busy:false};
const clone=value=>JSON.parse(JSON.stringify(value||{}));
function parseQuantities(value){
  const source=Array.isArray(value)?value.join(','):String(value||'');
  return [...new Set(source.split(/[,;\s]+/).map(Number).filter(x=>Number.isFinite(x)&&x>0).map(Math.round))].sort((a,b)=>a-b);
}
function lineQuantities(line={}){
  const cfg=line.config||{};
  return parseQuantities((cfg.quote_quantity_tiers||[]).map(x=>x?.quantity).filter(Boolean).length?(cfg.quote_quantity_tiers||[]).map(x=>x.quantity):(cfg.quote_tier_quantities||[]));
}
function money(value){return typeof businessMoney==='function'?businessMoney(Number(value)||0):(Number(value)||0).toFixed(2)+' EUR'}
function tierTable(line={}){
  const tiers=Array.isArray(line.config?.quote_quantity_tiers)?line.config.quote_quantity_tiers:[];
  if(!tiers.length)return '<small class="hca139-tier-help">Mehrere Mengen mit Komma trennen und anschließend berechnen.</small>';
  return '<table><thead><tr><th>Menge</th><th>Einzel netto</th><th>Gesamt netto</th><th>Gesamt brutto</th></tr></thead><tbody>'+tiers.map(t=>'<tr><td>'+Number(t.quantity).toLocaleString('de-DE')+'</td><td>'+money(t.unit_price)+'</td><td>'+money(t.net)+'</td><td><b>'+money(t.gross)+'</b></td></tr>').join('')+'</tbody></table>';
}
function tierEditor(line,index,locked){
  if(['text','optional'].includes(String(line?.item_type||'product').toLowerCase()))return '';
  return '<section class="hca139-line-tiers"><div class="hca139-tier-head"><div><b>Mengenstaffeln dieser Position</b><small>Alternative Angebotsmengen, z. B. 500, 1000, 1500</small></div><div class="hca139-tier-controls"><input class="text-input" data-h139-tier-input="'+index+'" value="'+lineQuantities(line).join(', ')+'" placeholder="500, 1000, 1500" '+(locked?'disabled':'')+'><button class="btn secondary" type="button" data-h139-tier-calculate="'+index+'" '+(locked?'disabled':'')+'>Staffeln berechnen</button></div></div><div class="hca139-tier-result">'+tierTable(line)+'</div></section>';
}
const previousLineHtml=window.businessQuoteLineHtml;
window.businessQuoteLineHtml=function(line,index,locked=false){
  const html=previousLineHtml(line,index,locked),extra=tierEditor(line,index,locked),at=html.lastIndexOf('<div class="business-quote-line-sum">');
  return extra&&at>=0?html.slice(0,at)+extra+html.slice(at):html;
};
function hideOldGlobalPanel(){document.querySelector('.hca136-tier-panel')?.remove()}
const previousRender=window.renderBusinessQuoteEditor;
window.renderBusinessQuoteEditor=function(){previousRender();hideOldGlobalPanel()};

async function calculateLine(line,quantities){
  line.config=line.config||{};line.config.quote_tier_quantities=quantities;
  const snapshots=[];
  for(const quantity of quantities){
    const candidate=clone(line);candidate.quantity=quantity;candidate.config=candidate.config||{};
    if(candidate.config.sizes&&Object.keys(candidate.config.sizes).length){candidate.config.sizes={};candidate.config.size=''}
    try{if(candidate.product_id&&typeof hca103ShopPrice==='function')await hca103ShopPrice(candidate)}catch{}
    const amount=businessQuoteLineAmounts(candidate);
    snapshots.push({quantity,unit_price:Number(candidate.unit_price)||0,net:Number(amount.net)||0,tax:Number(amount.tax)||0,gross:Number(amount.gross)||0,production_steps:clone(candidate.config.production_steps||[])});
  }
  line.config.quote_quantity_tiers=snapshots;return snapshots;
}
async function calculateIndex(index,rerender=true){
  const line=activeBusinessQuote?.items?.[index],input=document.querySelector('[data-h139-tier-input="'+index+'"]');if(!line)return;
  const quantities=parseQuantities(input?.value||lineQuantities(line));
  if(input)input.value=quantities.join(', ');
  const button=document.querySelector('[data-h139-tier-calculate="'+index+'"]');if(button){button.disabled=true;button.textContent='Wird berechnet …'}
  await calculateLine(line,quantities);hcaEditorDirty=true;
  if(rerender)renderBusinessQuoteEditor();
}
document.addEventListener('input',event=>{
  if(event.target?.dataset?.h139TierInput===undefined)return;
  const line=activeBusinessQuote?.items?.[Number(event.target.dataset.h139TierInput)];if(!line)return;
  line.config=line.config||{};line.config.quote_tier_quantities=parseQuantities(event.target.value);hcaEditorDirty=true;
},true);
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-h139-tier-calculate]');if(!button)return;
  event.preventDefault();calculateIndex(Number(button.dataset.h139TierCalculate));
},true);

const previousPayload=window.businessQuotePayload;
window.businessQuotePayload=function(){
  const payload=previousPayload();
  const source=H139.pending||(activeBusinessQuote?.items||[]).map(line=>({quantities:clone(line.config?.quote_tier_quantities||lineQuantities(line)),snapshots:clone(line.config?.quote_quantity_tiers||[])}));
  payload.items=(payload.items||[]).map((item,index)=>({...item,config:{...(item.config||{}),quote_tier_quantities:clone(source[index]?.quantities||[]),quote_quantity_tiers:clone(source[index]?.snapshots||[])}}));
  payload.quantity_tiers=[...new Set(source.flatMap(x=>x?.quantities||[]))].sort((a,b)=>a-b);
  return payload;
};
const previousSave=window.saveBusinessQuote;
window.saveBusinessQuote=async function(){
  if(H139.busy)return;H139.busy=true;
  const saveButton=document.querySelector('#businessSaveQuote');if(saveButton)saveButton.disabled=true;
  try{
    const items=activeBusinessQuote?.items||[];
    for(let index=0;index<items.length;index++){
      if(['text','optional'].includes(String(items[index]?.item_type||'product').toLowerCase()))continue;
      const input=document.querySelector('[data-h139-tier-input="'+index+'"]'),quantities=parseQuantities(input?.value||lineQuantities(items[index]));
      if(quantities.length)await calculateLine(items[index],quantities);else{items[index].config=items[index].config||{};items[index].config.quote_tier_quantities=[];items[index].config.quote_quantity_tiers=[]}
    }
    H139.pending=items.map(line=>({quantities:clone(line.config?.quote_tier_quantities||[]),snapshots:clone(line.config?.quote_quantity_tiers||[])}));
    activeBusinessQuote.quantity_tiers=[...new Set(H139.pending.flatMap(x=>x.quantities))].sort((a,b)=>a-b);
    await previousSave();
  }finally{
    if(H139.pending&&activeBusinessQuote?.items)activeBusinessQuote.items.forEach((line,index)=>{line.config=line.config||{};line.config.quote_tier_quantities=clone(H139.pending[index]?.quantities||line.config.quote_tier_quantities||[]);line.config.quote_quantity_tiers=clone(H139.pending[index]?.snapshots||line.config.quote_quantity_tiers||[])});
    H139.pending=null;H139.busy=false;if(saveButton?.isConnected)saveButton.disabled=false;
  }
};
hideOldGlobalPanel();
})();
