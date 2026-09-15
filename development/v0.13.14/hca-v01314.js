/* HCA v0.13.14 · Reparatur beschädigter Veredelungs-Preiszuordnungen */
(()=>{
'use strict';

const requests=new WeakMap();
const clone=value=>JSON.parse(JSON.stringify(value||{}));
const text=value=>String(value??'').trim();
const norm=value=>text(value).toLocaleLowerCase('de-DE').replace(/[^a-z0-9äöüß]+/g,'');
const message=error=>String(error?.message||error||'Unbekannter Fehler');

function automaticSteps(line){
  return (line?.config?.production_steps||[]).filter(step=>!step?.manual_override);
}

async function freshWizardConfig(line){
  const productId=Number(line?.config?.main_product_id||line?.product_id||0);
  if(!productId)throw new Error('Die WooCommerce-Produkt-ID fehlt.');
  const data=await businessApi(`/woocommerce/products/${encodeURIComponent(productId)}/wizard-config`);
  if(!Array.isArray(data?.areas)||!data.areas.length){
    throw new Error('WooCommerce hat für diesen Artikel keine Veredelungspositionen geliefert.');
  }
  line.config.wizard_config=data;
  line.config.shop_areas=data.areas;
  line.config.tier_prices=Array.isArray(data.tier_prices)?data.tier_prices:[];
  line.config.wizard_config_error='';
  return data;
}

function exactArea(areas,step){
  let area=areas.find(item=>text(item?.id)&&text(item.id)===text(step?.area_id));
  if(area)return area;
  const names=[step?.area_name,step?.position].map(norm).filter(Boolean);
  area=areas.find(item=>{
    const candidates=[item?.name,item?.position].map(norm).filter(Boolean);
    return names.some(name=>candidates.includes(name));
  });
  if(area)return area;
  const index=Number(step?.area_index);
  if(Number.isInteger(index))area=areas.find(item=>Number(item?.index)===index);
  if(area)return area;
  return areas.length===1?areas[0]:null;
}

function exactAssignment(area,step){
  const assignments=Array.isArray(area?.assignments)?area.assignments:[];
  let assignment=assignments.find(item=>Number(item?.druckart_id)>0&&Number(item.druckart_id)===Number(step?.druckart_id));
  if(assignment)return assignment;
  const wanted=[step?.technique,step?.technique_label,step?.technique_name].map(norm).filter(Boolean);
  assignment=assignments.find(item=>{
    const method=item?.method||{};
    const candidates=[method.code,method.name,method.label].map(norm).filter(Boolean);
    return wanted.some(value=>candidates.includes(value));
  });
  if(assignment)return assignment;
  return assignments.length===1?assignments[0]:null;
}

function repairStep(step,area,assignment){
  if(!step||!area||!assignment)return;
  const method=assignment.method||{};
  step.manual_override=false;
  step.area_id=text(area.id);
  step.area_index=Number(area.index)||0;
  step.area_name=text(area.name||area.position);
  step.position=text(area.name||area.position);
  step.druckart_id=Number(assignment.druckart_id)||0;
  step.cost_id=Number(assignment.cost_id)||0;
  step.bearbeitung_cost_id=Number(assignment.bearbeitung_cost_id)||0;
  step.technique=text(method.code)||String(step.druckart_id);
  step.technique_label=text(method.name||method.label)||'Veredelung';
  step.max_colors=Math.max(1,Number(assignment.max_colors||method.max_colors)||1);
  step.colors_count=Math.max(1,Math.min(step.max_colors,Number(step.colors_count)||1));
  step.setup_label=text(assignment.setup?.label)||'Einrichtungskosten';
  step.handling_label='Bearbeitungskosten/Artikel';
}

function expectedPrice(assignment,key){
  return Number(assignment?.[key]?.price)||0;
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
    const wizard=await freshWizardConfig(line);
    const steps=automaticSteps(line);
    const resolved=steps.map((step,index)=>{
      const area=exactArea(wizard.areas,step);
      if(!area)throw new Error(`Druckposition ${index+1} konnte nicht eindeutig zugeordnet werden.`);
      const assignment=exactAssignment(area,step);
      if(!assignment)throw new Error(`Veredelungsart ${index+1} konnte nicht eindeutig zugeordnet werden.`);
      repairStep(step,area,assignment);
      return {step,area,assignment};
    });
    const productId=Number(line.config.main_product_id||wizard.meta_product_id||line.product_id);
    const quantity=Number(typeof hca103Qty==='function'?hca103Qty(line):line.quantity)||1;
    const pricingConfig={...clone(line.config),production_steps:clone(steps)};
    const result=await businessApi('/business/shop-price',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({product_id:productId,quantity,config:pricingConfig})
    });
    if(sequence!==state.sequence)return result;
    const positions=Array.isArray(result?.positions)?result.positions:[];
    if(positions.length!==steps.length){
      throw new Error(`WooCommerce hat ${positions.length} von ${steps.length} Veredelungspreisen geliefert.`);
    }
    resolved.forEach(({assignment},index)=>{
      const position=positions[index]||{};
      const setup=Number(position.setup_total)||0;
      const handling=Number(position.bearbeitung_unit)||0;
      if(expectedPrice(assignment,'setup')>0&&setup<=0){
        throw new Error(`Einrichtungskosten fehlen in der WooCommerce-Antwort (Druckart-ID ${assignment.druckart_id}, Kosten-ID ${assignment.cost_id}).`);
      }
      if(expectedPrice(assignment,'handling')>0&&handling<=0){
        throw new Error(`Bearbeitungskosten fehlen in der WooCommerce-Antwort (Druckart-ID ${assignment.druckart_id}, Kosten-ID ${assignment.bearbeitung_cost_id}).`);
      }
      if(Number(position.print_per_item||0)<=0){
        throw new Error(`Der Druckpreis fehlt in der WooCommerce-Antwort (Druckart-ID ${assignment.druckart_id}, Menge ${quantity}).`);
      }
    });
    line.unit_price=Number(result?.base_unit)||0;
    resolved.forEach(({step},index)=>applyPosition(step,positions[index]));
    line.config.shop_price_breakdown=result;
    line.config.shop_price_source=result?.source||'woocommerce-wizard';
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

})();
