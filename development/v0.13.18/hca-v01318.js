/* HCA v0.13.18 · Preisfunktion reparieren und Mengenfelder-Rückbau absichern */
(()=>{
'use strict';

function hca1318Truthy(value){
  if(typeof value==='boolean')return value;
  if(typeof value==='number')return value!==0;
  return ['1','true','yes','ja','on'].includes(String(value??'').trim().toLowerCase());
}

function hca1318NormalizeLine(line){
  const steps=Array.isArray(line?.config?.production_steps)?line.config.production_steps:[];
  for(const step of steps){
    if(!step||typeof step!=='object')continue;
    step.manual_override=hca1318Truthy(step.manual_override);
  }
  return line;
}

const previousLineHtml=window.businessQuoteLineHtml;
if(typeof previousLineHtml==='function'){
  window.businessQuoteLineHtml=function(line,...args){
    hca1318NormalizeLine(line);
    return previousLineHtml.call(this,line,...args);
  };
}

window.hca103ShopPrice=async function(line){
  if(!line?.product_id)return null;
  line.config=line.config||{};
  hca1318NormalizeLine(line);
  await hcaV121LoadWizardConfig(line);
  const qty=hca103Qty(line);
  const steps=Array.isArray(line.config.production_steps)?line.config.production_steps:[];
  const automatic=steps.filter(step=>!hca1318Truthy(step?.manual_override));
  automatic.forEach(step=>hca103EnrichStep(line,step));
  const pricingConfig={...line.config,production_steps:automatic};
  const res=await businessApi('/business/shop-price',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({product_id:line.product_id,quantity:qty,config:pricingConfig})
  });
  line.unit_price=Number(res.base_unit)||0;
  const returned=Array.isArray(res.positions)?res.positions:[];
  if(automatic.length&&returned.length!==automatic.length){
    throw new Error(`Shop lieferte ${returned.length} von ${automatic.length} Veredelungspreisen.`);
  }
  returned.forEach((price,index)=>{
    const step=automatic[index];
    if(!step)return;
    step.print_price=Number(price.print_per_item)||0;
    step.handling_price=Number(price.bearbeitung_unit)||0;
    step.unit_price=step.print_price+step.handling_price;
    step.setup_price=Number(price.setup_total)||0;
    step.setup_price_before_discount=Number(price.setup_total_before_discount)||step.setup_price;
    step.setup_discount=Number(price.setup_discount)||0;
    step.setup_discount_percent=Number(price.setup_discount_percent)||0;
  });
  line.config.shop_price_breakdown=res;
  line.config.shop_price_source=res.source||'woocommerce-wizard';
  line.config.shop_price_updated_at=new Date().toISOString();
  return res;
};

})();
