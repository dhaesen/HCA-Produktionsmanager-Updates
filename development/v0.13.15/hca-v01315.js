/* HCA v0.13.15 · Rücksetzung auf die bewährte WooCommerce-Preisberechnung */
(()=>{
'use strict';

/*
 * Die Preis-Overrides aus v0.13.11 bis v0.13.14 werden bewusst nicht mehr
 * verwendet. Diese Routine entspricht wieder dem bis v0.13.10 bewährten
 * Ablauf: Wizard laden, die gewählte Zuordnung anwenden, genau einmal beim
 * HCA-Server kalkulieren und alle drei Preisbestandteile übernehmen.
 */
window.hca103ShopPrice=async function(line){
  if(!line?.product_id)return null;
  line.config=line.config||{};
  if(typeof hcaV121LoadWizardConfig==='function')await hcaV121LoadWizardConfig(line);
  const steps=(line.config.production_steps||[]).filter(step=>!step?.manual_override);
  for(const step of steps){
    if(typeof hcaV121Area==='function'&&typeof hcaV121Assignment==='function'&&typeof hcaV121ApplyAssignment==='function'){
      const area=hcaV121Area(line,step),assignment=hcaV121Assignment(area,step);
      if(area&&assignment)hcaV121ApplyAssignment(step,area,assignment);
    }
    if(typeof hca103EnrichStep==='function')hca103EnrichStep(line,step);
  }
  const productId=Number(line.config.main_product_id||line.config.wizard_config?.meta_product_id||line.product_id)||line.product_id;
  const quantity=typeof hca103Qty==='function'?hca103Qty(line):Math.max(1,Number(line.quantity)||1);
  const pricingConfig=JSON.parse(JSON.stringify({...line.config,production_steps:steps}));
  const result=await businessApi('/business/shop-price',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({product_id:productId,quantity,config:pricingConfig})
  });
  const positions=Array.isArray(result?.positions)?result.positions:[];
  if(steps.length&&positions.length!==steps.length){
    throw new Error(`WooCommerce hat ${positions.length} von ${steps.length} Veredelungspreisen geliefert.`);
  }
  line.unit_price=Number(result?.base_unit)||0;
  positions.forEach((position,index)=>{
    const step=steps[index];if(!step)return;
    step.print_price=Number(position?.print_per_item)||0;
    step.handling_price=Number(position?.bearbeitung_unit)||0;
    step.unit_price=step.print_price+step.handling_price;
    step.setup_price=Number(position?.setup_total)||0;
    step.setup_price_before_discount=Number(position?.setup_total_before_discount)||step.setup_price;
    step.setup_discount=Number(position?.setup_discount)||0;
    step.setup_discount_percent=Number(position?.setup_discount_percent)||0;
  });
  line.config.shop_price_breakdown=result;
  line.config.shop_price_source=result?.source||'woocommerce-wizard';
  line.config.shop_price_updated_at=new Date().toISOString();
  line.config.shop_price_error='';
  return result;
};

/* Alte Angebote unmittelbar nach dem Laden neu kalkulieren. */
const previousOpenQuote=window.openBusinessQuoteEditor;
if(previousOpenQuote)window.openBusinessQuoteEditor=async function(id){
  await previousOpenQuote(id);
  const lines=(typeof activeBusinessQuote!=='undefined'&&activeBusinessQuote?.items?activeBusinessQuote.items:[]).filter(line=>line?.product_id&&(line.config?.production_steps||[]).some(step=>!step?.manual_override));
  if(!lines.length)return;
  try{
    for(const line of lines)await window.hca103ShopPrice(line);
    if(typeof window.renderBusinessQuoteEditor==='function')window.renderBusinessQuoteEditor();
  }catch(error){
    for(const line of lines)line.config.shop_price_error=String(error?.message||error||'Veredelungspreise konnten nicht geladen werden.');
    if(typeof window.renderBusinessQuoteEditor==='function')window.renderBusinessQuoteEditor();
  }
};

})();
