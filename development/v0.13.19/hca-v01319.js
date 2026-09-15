/* HCA v0.13.19 · Bestandspositionen und Preisabruf reparieren */
(()=>{
'use strict';

const truthy=value=>{
  if(typeof value==='boolean')return value;
  if(typeof value==='number')return value!==0;
  return ['1','true','yes','ja','on'].includes(String(value??'').trim().toLowerCase());
};

function productId(line){
  return Number(line?.config?.main_product_id||line?.config?.wizard_config?.meta_product_id||line?.product_id||0);
}

function normalizeExistingLine(line){
  if(!line||typeof line!=='object')return line;
  line.config=line.config||{};
  const cfg=line.config;
  const variants=Array.isArray(cfg.product_variants)?cfg.product_variants:[];
  const variantSizes=variants.flatMap(v=>Array.isArray(v?.sizes)?v.sizes:[]).map(x=>String(x||'').trim()).filter(Boolean);
  const meaningful=variantSizes.filter(x=>!['standard','einheitsgröße','einheitsgroesse','one size','onesize','n/a','-'].includes(x.toLowerCase()));
  if(cfg.product_type==='textile'&&productId(line)&&variants.length&&!meaningful.length){
    cfg.product_type='promotional';
    cfg.available_sizes=[];
    cfg.size_skus={};
    cfg.sizes={};
  }
  for(const step of Array.isArray(cfg.production_steps)?cfg.production_steps:[]){
    if(step&&typeof step==='object')step.manual_override=truthy(step.manual_override);
  }
  return line;
}

const oldVariantData=window.hcaProductVariantData;
if(typeof oldVariantData==='function')window.hcaProductVariantData=function(raw={}){
  return {...oldVariantData(raw),wsk:truthy(raw.wsk),product_type:raw.product_type||oldVariantData(raw).product_type||''};
};

const oldSelect=window.hcaSelectMainProduct;
if(typeof oldSelect==='function')window.hcaSelectMainProduct=function(line,main){
  const quantity=Math.max(1,Number(line?.quantity)||1);
  oldSelect(line,main);
  const variants=Array.isArray(main?._variants)?main._variants:[];
  if(truthy(main?.wsk)||variants.some(v=>truthy(v?.wsk))){
    line.config.product_type='promotional';
    line.config.available_sizes=[];
    line.config.size_skus={};
    line.config.sizes={};
    line.quantity=quantity;
  }
  normalizeExistingLine(line);
};

const oldUnified=window.hcaUnifiedPositionHtml;
if(typeof oldUnified==='function')window.hcaUnifiedPositionHtml=function(line,...args){
  normalizeExistingLine(line);
  return oldUnified.call(this,line,...args);
};
const oldLineHtml=window.businessQuoteLineHtml;
if(typeof oldLineHtml==='function')window.businessQuoteLineHtml=function(line,...args){
  normalizeExistingLine(line);
  return oldLineHtml.call(this,line,...args);
};

window.hca103ShopPrice=async function(line){
  normalizeExistingLine(line);
  const pid=productId(line);
  if(!pid)throw new Error('Der Position fehlt die WooCommerce-Produkt-ID. Bitte den Hauptartikel erneut über die Suche auswählen.');
  await hcaV121LoadWizardConfig(line);
  const qty=hca103Qty(line);
  const steps=Array.isArray(line.config.production_steps)?line.config.production_steps:[];
  const automatic=steps.filter(step=>!truthy(step?.manual_override));
  automatic.forEach(step=>hca103EnrichStep(line,step));
  const pricingConfig={...line.config,production_steps:automatic};
  const result=await businessApi('/business/shop-price',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({product_id:pid,quantity:qty,config:pricingConfig})
  });
  const positions=Array.isArray(result?.positions)?result.positions:[];
  if(automatic.length&&positions.length!==automatic.length){
    throw new Error(`WooCommerce hat ${positions.length} von ${automatic.length} Veredelungspreisen geliefert.`);
  }
  positions.forEach((position,index)=>{
    const step=automatic[index];if(!step)return;
    const print=Number(position?.print_per_item)||0;
    const setup=Number(position?.setup_total)||0;
    const handling=Number(position?.bearbeitung_unit)||0;
    if(print<=0&&setup<=0&&handling<=0){
      throw new Error(`WooCommerce hat für ${step.technique_label||step.technique||'die Veredelung'} nur 0,00 EUR geliefert. Die Position wurde nicht als erfolgreich aktualisiert.`);
    }
    step.print_price=print;
    step.handling_price=handling;
    step.unit_price=print+handling;
    step.setup_price=setup;
    step.setup_price_before_discount=Number(position?.setup_total_before_discount)||setup;
    step.setup_discount=Number(position?.setup_discount)||0;
    step.setup_discount_percent=Number(position?.setup_discount_percent)||0;
  });
  line.unit_price=Number(result?.base_unit)||0;
  line.config.shop_price_breakdown=result;
  line.config.shop_price_source=result?.source||'woocommerce-wizard';
  line.config.shop_price_updated_at=new Date().toISOString();
  line.config.shop_price_error='';
  return result;
};

window.hca103RepriceQuote=async function(){
  if(!activeBusinessQuote)return;
  const button=document.querySelector('#businessQuoteReprice');
  if(button){button.disabled=true;button.textContent='Shoppreise werden geladen …';}
  try{
    const lines=(activeBusinessQuote.items||[]).filter(line=>String(line?.item_type||'product')!=='text'&&productId(line));
    if(!lines.length)throw new Error('Keine Position mit WooCommerce-Produkt-ID gefunden. Bitte den Hauptartikel erneut auswählen.');
    for(const line of lines)await window.hca103ShopPrice(line);
    window.renderBusinessQuoteEditor();
  }catch(error){
    alert('Shoppreise konnten nicht vollständig geladen werden:\n'+(error?.message||error));
  }finally{
    if(button){button.disabled=false;button.textContent='Shoppreise aktualisieren';}
  }
};

const oldQuoteRender=window.renderBusinessQuoteEditor;
if(typeof oldQuoteRender==='function')window.renderBusinessQuoteEditor=function(...args){
  (activeBusinessQuote?.items||[]).forEach(normalizeExistingLine);
  const result=oldQuoteRender.apply(this,args);
  const button=document.querySelector('#businessQuoteReprice');
  if(button)button.onclick=window.hca103RepriceQuote;
  return result;
};

window.hca1319={productId,normalizeExistingLine};
})();
