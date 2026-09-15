/* HCA v0.13.16 · exakte Wiederherstellung der Preisfunktion aus v0.13.6.1 */
(()=>{
'use strict';

/*
 * Dieser Block entspricht absichtlich wortgleich der zuletzt nachweislich
 * funktionierenden hca103ShopPrice-Routine aus dem Client v0.13.6.1.
 * Vorhandene WooCommerce-IDs werden nicht durch eine vermeintlich passende
 * erste Wizard-Zuordnung ersetzt.
 */
window.hca103ShopPrice=async function(line){
  if(!line?.product_id)return null;line.config=line.config||{};await hcaV121LoadWizardConfig(line);const qty=hca103Qty(line),steps=line.config.production_steps||[],automatic=steps.filter(s=>!s.manual_override);automatic.forEach(s=>hca103EnrichStep(line,s));
  const pricingConfig={...line.config,production_steps:automatic};const res=await businessApi('/business/shop-price',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_id:line.product_id,quantity:qty,config:pricingConfig})});line.unit_price=Number(res.base_unit)||0;
  (res.positions||[]).forEach((p,i)=>{const s=automatic[i];if(!s)return;s.print_price=Number(p.print_per_item)||0;s.handling_price=Number(p.bearbeitung_unit)||0;s.unit_price=s.print_price+s.handling_price;s.setup_price=Number(p.setup_total)||0;s.setup_price_before_discount=Number(p.setup_total_before_discount)||s.setup_price;s.setup_discount=Number(p.setup_discount)||0;s.setup_discount_percent=Number(p.setup_discount_percent)||0});
  line.config.shop_price_breakdown=res;line.config.shop_price_source=res.source||'woocommerce-wizard';line.config.shop_price_updated_at=new Date().toISOString();return res;
};

})();
