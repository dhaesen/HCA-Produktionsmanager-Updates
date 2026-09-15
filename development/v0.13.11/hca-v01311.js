/* HCA v0.13.11 · zuverlässige WooCommerce-Veredelungspreise */
(()=>{
'use strict';

const requests=new WeakMap();
const waits=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const clone=value=>JSON.parse(JSON.stringify(value||{}));
const message=error=>String(error?.message||error||'Unbekannter Fehler');

function automaticSteps(line){
  return (line?.config?.production_steps||[]).filter(step=>!step?.manual_override);
}

function normalizeSteps(line){
  for(const step of automaticSteps(line)){
    const area=typeof hcaV121Area==='function'?hcaV121Area(line,step):null;
    const assignment=area&&typeof hcaV121Assignment==='function'?hcaV121Assignment(area,step):null;
    if(area&&assignment&&typeof hcaV121ApplyAssignment==='function')hcaV121ApplyAssignment(step,area,assignment);
    if(typeof hca103EnrichStep==='function')hca103EnrichStep(line,step);
    if(!Number(step.druckart_id)||!Number(step.cost_id)){
      throw new Error('Die gewählte Veredelung ist nicht vollständig mit der WooCommerce-Druckpreisverwaltung verknüpft.');
    }
  }
}

function requestSignature(line,steps){
  return JSON.stringify({
    product_id:String(line.product_id||''),
    quantity:Number(typeof hca103Qty==='function'?hca103Qty(line):line.quantity)||1,
    color:String(line.config?.color||''),
    steps:steps.map(step=>({
      area_id:String(step.area_id||''),area_index:Number(step.area_index)||0,
      druckart_id:Number(step.druckart_id)||0,cost_id:Number(step.cost_id)||0,
      bearbeitung_cost_id:Number(step.bearbeitung_cost_id)||0,colors_count:Number(step.colors_count)||1
    }))
  });
}

function applyPosition(step,position){
  step.print_price=Number(position.print_per_item)||0;
  step.handling_price=Number(position.bearbeitung_unit)||0;
  step.unit_price=step.print_price+step.handling_price;
  step.setup_price=Number(position.setup_total)||0;
  step.setup_price_before_discount=Number(position.setup_total_before_discount)||step.setup_price;
  step.setup_discount=Number(position.setup_discount)||0;
  step.setup_discount_percent=Number(position.setup_discount_percent)||0;
}

function matches(position,step,index){
  const posNumber=Number(position?.posNumber??position?.pos_number??position?.position_no);
  if(posNumber)return posNumber===index+1;
  const areaId=String(position?.areaId??position?.area_id??'');
  const methodId=Number(position?.druckartId??position?.druckart_id??0);
  if(areaId&&methodId)return areaId===String(step.area_id||'')&&methodId===Number(step.druckart_id||0);
  if(areaId)return areaId===String(step.area_id||'');
  return false;
}

async function fetchPrice(line,pricingConfig,quantity){
  let lastError;
  for(let attempt=0;attempt<2;attempt++){
    try{
      const result=await businessApi('/business/shop-price',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({product_id:line.product_id,quantity,config:pricingConfig})
      });
      if(result?.warning&&automaticSteps(line).length)throw new Error(result.warning);
      return result;
    }catch(error){
      lastError=error;
      if(attempt===0)await waits(350);
    }
  }
  throw lastError;
}

window.hca103ShopPrice=async function(line){
  if(!line?.product_id)return null;
  line.config=line.config||{};
  const state=requests.get(line)||{sequence:0};
  const sequence=++state.sequence;
  requests.set(line,state);
  line.config.shop_price_loading=true;
  line.config.shop_price_error='';
  try{
    if(typeof hcaV121LoadWizardConfig==='function')await hcaV121LoadWizardConfig(line);
    normalizeSteps(line);
    const steps=automaticSteps(line),quantity=Number(typeof hca103Qty==='function'?hca103Qty(line):line.quantity)||1;
    const signature=requestSignature(line,steps);
    const pricingConfig={...clone(line.config),production_steps:clone(steps)};
    const result=await fetchPrice(line,pricingConfig,quantity);
    if(sequence!==state.sequence||signature!==requestSignature(line,automaticSteps(line)))return result;
    const positions=Array.isArray(result?.positions)?result.positions:[];
    if(steps.length&&positions.length!==steps.length){
      throw new Error(`WooCommerce hat ${positions.length} von ${steps.length} Veredelungspreisen geliefert.`);
    }
    line.unit_price=Number(result.base_unit)||0;
    const unused=[...positions];
    steps.forEach((step,index)=>{
      let found=unused.findIndex(position=>matches(position,step,index));
      if(found<0)found=0;
      const position=unused.splice(found,1)[0];
      if(!position)throw new Error(`Der Preis für Veredelung ${index+1} fehlt.`);
      applyPosition(step,position);
    });
    line.config.shop_price_breakdown=result;
    line.config.shop_price_source=result.source||'woocommerce-wizard';
    line.config.shop_price_updated_at=new Date().toISOString();
    line.config.shop_price_error='';
    return result;
  }catch(error){
    if(sequence===state.sequence)line.config.shop_price_error=message(error);
    throw error;
  }finally{
    if(sequence===state.sequence)line.config.shop_price_loading=false;
  }
};

function statusHtml(line,scope,index){
  const config=line?.config||{};
  if(config.shop_price_loading)return '<div class="hca1311-price-status loading"><span></span>Veredelungspreise werden geladen …</div>';
  if(config.shop_price_error)return `<div class="hca1311-price-status error"><b>Veredelungspreise nicht geladen:</b> ${escapeHtml(config.shop_price_error)} <button type="button" class="btn secondary compact" data-h1311-retry="${scope}:${index}">Erneut laden</button></div>`;
  if(automaticSteps(line).length&&config.shop_price_updated_at)return '<div class="hca1311-price-status ok">✓ Produkt- und Veredelungspreise vollständig aus WooCommerce geladen</div>';
  return '';
}

function insertStatus(html,line,scope,index){
  const status=statusHtml(line,scope,index);
  return status?html.replace('<div class="business-quote-line-sum">',status+'<div class="business-quote-line-sum">'):html;
}

const quoteHtml=window.businessQuoteLineHtml;
window.businessQuoteLineHtml=function(line,index,locked=false){return insertStatus(quoteHtml(line,index,locked),line,'quote',index)};
const unifiedHtml=window.hcaUnifiedPositionHtml;
window.hcaUnifiedPositionHtml=function(line,index,locked=false){
  let scope='quote';
  if(typeof HCA103!=='undefined'&&HCA103.orderLines?.includes(line))scope='order';
  else if(typeof financeInvoiceLines!=='undefined'&&financeInvoiceLines?.includes(line))scope='invoice';
  return insertStatus(unifiedHtml(line,index,locked),line,scope,index);
};

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-h1311-retry]');if(!button)return;
  event.preventDefault();
  const [scope,indexText]=button.dataset.h1311Retry.split(':'),index=Number(indexText);
  const line=scope==='order'?(typeof HCA103!=='undefined'?HCA103.orderLines?.[index]:null):scope==='invoice'?(typeof financeInvoiceLines!=='undefined'?financeInvoiceLines?.[index]:null):(typeof activeBusinessQuote!=='undefined'?activeBusinessQuote?.items?.[index]:null);
  if(!line)return;
  button.disabled=true;button.textContent='Wird geladen …';
  try{await window.hca103ShopPrice(line)}catch(error){/* Status steht direkt an der Position. */}
  if(typeof hcaV121LineOwnerRender==='function')hcaV121LineOwnerRender(line);
},true);

})();
