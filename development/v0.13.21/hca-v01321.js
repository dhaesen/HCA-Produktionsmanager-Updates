/* HCA v0.13.21 · echte Mengenoptionen, Produktstaffeln und Farbvarianten */
(()=>{
'use strict';

const H1321={building:false};
const clone=value=>JSON.parse(JSON.stringify(value||{}));
const truthy=value=>{
  if(typeof value==='boolean')return value;
  if(typeof value==='number')return value!==0;
  return ['1','true','yes','ja','on'].includes(String(value??'').trim().toLowerCase());
};
const productId=line=>Number(line?.config?.main_product_id||line?.config?.wizard_config?.meta_product_id||line?.product_id||0);
const parseQuantities=value=>[...new Set((Array.isArray(value)?value:String(value||'').split(/[,;\s]+/)).map(Number).filter(x=>Number.isFinite(x)&&x>0).map(Math.round))].sort((a,b)=>a-b);
const uniqueStrings=values=>[...new Set((values||[]).map(x=>String(x||'').trim()).filter(Boolean))];

function mergeProductDetails(line,data){
  line.config=line.config||{};
  const incoming=data?.product_details&&typeof data.product_details==='object'?data.product_details:{};
  const existing=line.config.product_details&&typeof line.config.product_details==='object'?line.config.product_details:{};
  const details={...existing,...incoming};
  for(const key of ['images','gallery_images','color_images','refinement_areas','attributes','categories']){
    if(!Array.isArray(incoming[key])&&Array.isArray(existing[key]))details[key]=existing[key];
  }
  line.config.product_details=details;
  const allImages=uniqueStrings([
    ...(Array.isArray(details.images)?details.images:[]),
    details.main_image,
    ...(Array.isArray(details.gallery_images)?details.gallery_images:[])
  ]);
  if(allImages.length)line.config.product_images=allImages;
}

async function refreshWizardConfig(line){
  if(!line)return null;
  line.config=line.config||{};
  const pid=productId(line);
  if(!pid)throw new Error('Der Position fehlt die WooCommerce-Hauptartikel-ID.');
  const data=await businessApi('/woocommerce/products/'+encodeURIComponent(pid)+'/wizard-config');
  if(Number(data?.meta_product_id)>0)line.config.main_product_id=Number(data.meta_product_id);
  line.config.wizard_config=data;
  line.config.shop_areas=Array.isArray(data?.areas)?data.areas:[];
  line.config.tier_prices=Array.isArray(data?.tier_prices)?data.tier_prices:[];
  line.config.wizard_config_error='';
  mergeProductDetails(line,data);
  return data;
}

/* Die bewährte Preisroutine aus 0.13.20 bleibt unangetastet. Vor jedem Abruf
   werden lediglich die aktuellen Produktstaffeln und Bilddaten neu geladen. */
const workingShopPrice=window.hca103ShopPrice;
if(typeof workingShopPrice==='function')window.hca103ShopPrice=async function(line){
  await refreshWizardConfig(line);
  return workingShopPrice(line);
};

function generatedQuantityOption(line){
  const cfg=line?.config||{};
  return truthy(cfg.quantity_option_generated)||truthy(cfg.alternative_quantity_generated)||truthy(cfg.hca_quantity_option);
}
function eligibleBaseLine(line){
  if(!line||['text','optional'].includes(String(line.item_type||'product').toLowerCase())||generatedQuantityOption(line))return false;
  if(!productId(line))return false;
  const type=String(line.config?.product_type||'').toLowerCase();
  return type==='promotional'||type==='werbeartikel'||type==='textile';
}
function currentQuoteQuantities(){
  const field=document.querySelector('#hca136QuoteTiers');
  return parseQuantities(field?.value||activeBusinessQuote?.quantity_tiers||[]);
}
function optionId(){return crypto.randomUUID?.()||('qty-'+Date.now()+'-'+Math.random().toString(16).slice(2))}

window.buildTierSnapshots=async function(){
  if(H1321.building||!activeBusinessQuote)return;
  H1321.building=true;
  const field=document.querySelector('#hca136QuoteTiers');
  const quantities=parseQuantities(field?.value||activeBusinessQuote.quantity_tiers||[]);
  activeBusinessQuote.quantity_tiers=quantities;
  const original=(activeBusinessQuote.items||[]).filter(line=>!generatedQuantityOption(line));
  const status=document.querySelector('#hca136TierStatus');
  if(status)status.textContent=quantities.length?'Optionale Mengen werden mit den aktuellen Shoppreisen berechnet …':'Keine zusätzlichen Mengen eingetragen.';
  try{
    const rebuilt=[];
    for(let index=0;index<original.length;index++){
      const base=original[index];
      if(base?.config){delete base.config.quote_quantity_tiers;delete base.config.quote_tier_quantities;}
      rebuilt.push(base);
      if(!eligibleBaseLine(base))continue;
      await window.hca103ShopPrice(base);
      const baseQuantity=Math.max(1,Number(typeof hca103Qty==='function'?hca103Qty(base):base.quantity)||1);
      const snapshots=[];
      for(const quantity of quantities){
        if(quantity===baseQuantity){
          const amount=businessQuoteLineAmounts(base);
          snapshots.push({quantity,unit_price:Number(base.unit_price)||0,net:Number(amount.net)||0,tax:Number(amount.tax)||0,gross:Number(amount.gross)||0,production_steps:clone(base.config.production_steps||[])});
          continue;
        }
        const option=clone(base);
        option.id=optionId();
        option.item_type='optional';
        option.quantity=quantity;
        option.config=option.config||{};
        option.config.sizes={};
        option.config.size='';
        option.config.available_sizes=[];
        option.config.size_skus={};
        option.config.quantity_option_generated=true;
        option.config.hca_quantity_option=true;
        option.config.quantity_option_source_id=String(base.id||('position-'+index));
        option.config.quantity_option_quantity=quantity;
        option.config.datasheet_enabled=false;
        option.config.datasheet_images=[];
        delete option.config.quote_quantity_tiers;
        delete option.config.quote_tier_quantities;
        await window.hca103ShopPrice(option);
        const amount=businessQuoteLineAmounts(option);
        snapshots.push({quantity,unit_price:Number(option.unit_price)||0,net:Number(amount.net)||0,tax:Number(amount.tax)||0,gross:Number(amount.gross)||0,production_steps:clone(option.config.production_steps||[])});
        rebuilt.push(option);
      }
      base.config.quote_quantity_tiers=snapshots;
      base.config.alternative_offer_quantities=quantities;
    }
    activeBusinessQuote.items=rebuilt;
    hcaEditorDirty=true;
    window.renderBusinessQuoteEditor();
    const refreshed=document.querySelector('#hca136TierStatus');
    if(refreshed)refreshed.textContent=quantities.length
      ? quantities.length+' Zusatzmenge(n) als optionale Positionen berechnet. Artikel- und Veredelungsstaffeln wurden berücksichtigt.'
      : 'Optionale Mengenpositionen wurden entfernt.';
  }finally{H1321.building=false;}
};

window.tierPreviewHtml=function(){
  const rows=(activeBusinessQuote?.items||[]).filter(generatedQuantityOption);
  if(!rows.length)return '';
  return '<div class="hca1321-tier-summary"><b>Berechnete optionale Mengen</b>'+rows.map(line=>{
    const amount=businessQuoteLineAmounts(line);
    const tier=(line.config?.tier_prices||[]).filter(x=>Number(line.quantity)>=Number(x.qty||0)).sort((a,b)=>Number(a.qty)-Number(b.qty)).at(-1);
    return '<span>'+Number(line.quantity).toLocaleString('de-DE')+' × '+escapeHtml(line.description||'Artikel')+
      (tier?' · Produktstaffel ab '+Number(tier.qty).toLocaleString('de-DE'):'')+
      ' · netto '+businessMoney(amount.net)+' · brutto '+businessMoney(amount.gross)+'</span>';
  }).join('')+'</div>';
};

const oldPayload=window.businessQuotePayload;
if(typeof oldPayload==='function')window.businessQuotePayload=function(){
  const payload=oldPayload();
  payload.quantity_tiers=parseQuantities(activeBusinessQuote?.quantity_tiers||[]);
  payload.items=(payload.items||[]).map(item=>{
    const cfg={...(item.config||{})};
    delete cfg.quote_tier_quantities;
    return {...item,config:cfg};
  });
  return payload;
};

window.hca1321={refreshWizardConfig,mergeProductDetails,generatedQuantityOption,eligibleBaseLine};
})();
