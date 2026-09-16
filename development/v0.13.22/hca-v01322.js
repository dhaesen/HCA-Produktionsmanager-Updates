/* HCA v0.13.22 · Mengenstaffel entfernt */
(()=>{
'use strict';

const generatedQuantityOption=line=>{
  const cfg=line?.config||{};
  const yes=value=>value===true||value===1||['1','true','yes','ja','on'].includes(String(value??'').trim().toLowerCase());
  return yes(cfg.quantity_option_generated)||yes(cfg.alternative_quantity_generated)||yes(cfg.hca_quantity_option);
};

function clearQuantityTierData(){
  if(!activeBusinessQuote)return;
  activeBusinessQuote.quantity_tiers=[];
  activeBusinessQuote.items=(activeBusinessQuote.items||[]).filter(line=>!generatedQuantityOption(line));
  for(const line of activeBusinessQuote.items){
    line.config=line.config||{};
    for(const key of ['alternative_offer_quantities','quote_quantity_tiers','quote_tier_quantities','quantity_option_group','quantity_option_value'])delete line.config[key];
  }
}

function removeQuantityTierControls(){
  document.querySelectorAll('.hca136-tier-panel,.hca139-line-tiers,.hca1310-alternatives,.hca1321-tier-summary').forEach(node=>node.remove());
}

const previousRender=window.renderBusinessQuoteEditor;
window.renderBusinessQuoteEditor=function(){
  clearQuantityTierData();
  const result=previousRender.apply(this,arguments);
  removeQuantityTierControls();
  return result;
};

const previousPayload=window.businessQuotePayload;
window.businessQuotePayload=function(){
  clearQuantityTierData();
  const payload=previousPayload.apply(this,arguments);
  payload.quantity_tiers=[];
  payload.items=(payload.items||[]).filter(line=>!generatedQuantityOption(line)).map(line=>{
    const config={...(line.config||{})};
    for(const key of ['alternative_offer_quantities','quote_quantity_tiers','quote_tier_quantities','quantity_option_group','quantity_option_value'])delete config[key];
    return {...line,config};
  });
  return payload;
};

const previousSave=window.saveBusinessQuote;
window.saveBusinessQuote=async function(){
  clearQuantityTierData();
  return previousSave.apply(this,arguments);
};

clearQuantityTierData();
removeQuantityTierControls();
window.hca1322={clearQuantityTierData,generatedQuantityOption};
})();
