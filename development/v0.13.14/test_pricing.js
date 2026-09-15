'use strict';
const assert=require('node:assert/strict');
global.window=global;
global.hca103Qty=line=>Number(line.quantity)||1;

const calls=[];
global.businessApi=async(path,options)=>{
  calls.push({path,options});
  if(path.includes('/wizard-config'))return {
    product_id:5266,meta_product_id:5266,
    areas:[{index:0,id:'area-live',name:'Vorderseite',assignments:[{
      druckart_id:15,cost_id:47,bearbeitung_cost_id:4,max_colors:1,
      method:{code:'S2A',name:'SIEBDRUCK',max_colors:1},
      setup:{price:44.46,label:'Einrichtungskosten S2A'},handling:{price:0.18}
    }]}]
  };
  return {source:'woocommerce-wizard',base_unit:16.90,positions:[{
    print_per_item:0.86,setup_total:44.46,bearbeitung_unit:0.18
  }]};
};

require('./hca-v01314.js');

(async()=>{
  const line={product_id:99999,quantity:500,config:{main_product_id:5266,production_steps:[{
    area_id:'beschädigt',area_index:0,druckart_id:0,cost_id:0,bearbeitung_cost_id:0,
    technique:'S2A',technique_label:'SIEBDRUCK',colors_count:1,
    print_price:0,setup_price:0,handling_price:0,unit_price:0
  }]}};
  await global.hca103ShopPrice(line);
  const sent=JSON.parse(calls[1].options.body);
  const step=sent.config.production_steps[0];
  assert.equal(sent.product_id,5266,'für die Kalkulation muss der Hauptartikel verwendet werden');
  assert.deepEqual([step.druckart_id,step.cost_id,step.bearbeitung_cost_id],[15,47,4]);
  assert.equal(line.config.production_steps[0].print_price,0.86);
  assert.equal(line.config.production_steps[0].setup_price,44.46);
  assert.equal(line.config.production_steps[0].handling_price,0.18);
  assert.equal(line.config.production_steps[0].unit_price,1.04);
  const priced=line.config.production_steps[0];
  const documentRows=1+(priced.print_price>0?1:0)+(priced.setup_price>0?1:0)+(priced.handling_price>0?1:0);
  assert.equal(documentRows,4,'Produkt, Veredelung, Einrichtung und Bearbeitung müssen vier Positionen ergeben');
  process.stdout.write('Beschädigte Preiszuordnung repariert: OK\n');
})().catch(error=>{console.error(error);process.exitCode=1});
