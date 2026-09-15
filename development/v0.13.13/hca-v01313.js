/* HCA v0.13.13 · Wiederherstellung der WooCommerce-Veredelungspreise */
(()=>{
'use strict';

const requests=new WeakMap();
const clone=value=>JSON.parse(JSON.stringify(value||{}));
const errorText=error=>String(error?.message||error||'Unbekannter Fehler');

function automaticSteps(line){
  return (line?.config?.production_steps||[]).filter(step=>!step?.manual_override);
}

/*
 * Wichtig: Bereits gespeicherte WooCommerce-IDs sind die verbindliche
 * Preiszuordnung. Sie dürfen beim Nachladen oder Öffnen alter Angebote nicht
 * aus einer möglicherweise neu sortierten Wizard-Konfiguration überschrieben
 * werden. Nur tatsächlich fehlende IDs werden eindeutig ergänzt.
 */
function completeMissingLinks(line,step){
  if(typeof hca103EnrichStep==='function')hca103EnrichStep(line,step);
  const hasMethod=Number(step?.druckart_id)>0;
  if(hasMethod)return;
  const areas=typeof hcaV121Areas==='function'?hcaV121Areas(line):[];
  const exactArea=areas.find(area=>String(area?.id||'')===String(step?.area_id||''))
    ||areas.find(area=>Number.isFinite(Number(step?.area_index))&&Number(area?.index)===Number(step.area_index));
  const assignments=Array.isArray(exactArea?.assignments)?exactArea.assignments:[];
  if(exactArea&&assignments.length===1&&typeof hcaV121ApplyAssignment==='function'){
    hcaV121ApplyAssignment(step,exactArea,assignments[0]);
  }
}

function requestSignature(line,steps){
  return JSON.stringify({
    product_id:String(line?.product_id||''),
    quantity:Number(typeof hca103Qty==='function'?hca103Qty(line):line?.quantity)||1,
    steps:steps.map(step=>({
      druckart_id:Number(step?.druckart_id)||0,
      cost_id:Number(step?.cost_id)||0,
      bearbeitung_cost_id:Number(step?.bearbeitung_cost_id)||0,
      colors_count:Number(step?.colors_count)||1
    }))
  });
}

function applyPosition(step,position){
  step.print_price=Number(position?.print_per_item)||0;
  step.handling_price=Number(position?.bearbeitung_unit)||0;
  step.unit_price=step.print_price+step.handling_price;
  step.setup_price=Number(position?.setup_total)||0;
  step.setup_price_before_discount=Number(position?.setup_total_before_discount)||step.setup_price;
  step.setup_discount=Number(position?.setup_discount)||0;
  step.setup_discount_percent=Number(position?.setup_discount_percent)||0;
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
    const steps=automaticSteps(line);
    for(const step of steps)completeMissingLinks(line,step);
    const missing=steps.find(step=>!Number(step?.druckart_id));
    if(missing){
      throw new Error(`Die Veredelung „${missing.technique_label||missing.technique||'ohne Bezeichnung'}“ ist nicht eindeutig mit der WooCommerce-Druckpreisverwaltung verknüpft.`);
    }
    const quantity=Number(typeof hca103Qty==='function'?hca103Qty(line):line.quantity)||1;
    const signature=requestSignature(line,steps);
    const pricingConfig={...clone(line.config),production_steps:clone(steps)};
    const result=await businessApi('/business/shop-price',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({product_id:line.product_id,quantity,config:pricingConfig})
    });
    if(sequence!==state.sequence||signature!==requestSignature(line,automaticSteps(line)))return result;
    const positions=Array.isArray(result?.positions)?result.positions:[];
    if(steps.length&&positions.length!==steps.length){
      throw new Error(`WooCommerce hat ${positions.length} von ${steps.length} Veredelungspreisen geliefert.`);
    }
    if(steps.length&&positions.every(position=>
      Number(position?.print_per_item||0)===0&&
      Number(position?.setup_total||0)===0&&
      Number(position?.bearbeitung_unit||0)===0
    )){
      throw new Error('WooCommerce hat für alle gewählten Veredelungen 0,00 € geliefert. Die gespeicherten Druckpreis-IDs wurden nicht übernommen; bitte die Veredelung neu auswählen.');
    }
    line.unit_price=Number(result?.base_unit)||0;
    steps.forEach((step,index)=>applyPosition(step,positions[index]));
    line.config.shop_price_breakdown=result;
    line.config.shop_price_source=result?.source||'woocommerce-wizard';
    line.config.shop_price_updated_at=new Date().toISOString();
    line.config.shop_price_error='';
    return result;
  }catch(error){
    if(sequence===state.sequence)line.config.shop_price_error=errorText(error);
    throw error;
  }finally{
    if(sequence===state.sequence)line.config.shop_price_loading=false;
  }
};

})();
