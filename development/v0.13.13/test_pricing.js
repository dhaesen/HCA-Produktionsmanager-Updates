'use strict';
const assert=require('node:assert/strict');

global.window=global;
global.hca103Qty=line=>Number(line.quantity)||1;
global.hca103EnrichStep=()=>{};

let sentBody=null;
global.businessApi=async(_path,options)=>{
  sentBody=JSON.parse(options.body);
  return {
    source:'woocommerce-wizard',base_unit:1.25,
    positions:[{print_per_item:0.16,bearbeitung_unit:0.04,setup_total:13.87}]
  };
};

require('./hca-v01313.js');

(async()=>{
  const line={
    product_id:4711,quantity:500,
    config:{
      wizard_config:{areas:[{id:'neu',index:0,assignments:[{druckart_id:999,cost_id:998,bearbeitung_cost_id:997}]}]},
      production_steps:[
        {area_id:'alt',area_index:4,druckart_id:17,cost_id:23,bearbeitung_cost_id:42,colors_count:1},
        {manual_override:true,druckart_id:88,cost_id:89,bearbeitung_cost_id:90}
      ]
    }
  };
  await global.hca103ShopPrice(line);
  const sent=sentBody.config.production_steps;
  assert.equal(sent.length,1,'manuelle Schritte dürfen nicht an den Shop gehen');
  assert.deepEqual(
    [sent[0].druckart_id,sent[0].cost_id,sent[0].bearbeitung_cost_id],
    [17,23,42],
    'gespeicherte WooCommerce-IDs dürfen nicht überschrieben werden'
  );
  assert.equal(line.config.production_steps[0].print_price,0.16);
  assert.equal(line.config.production_steps[0].handling_price,0.04);
  assert.equal(line.config.production_steps[0].setup_price,13.87);
  assert.equal(line.config.production_steps[1].print_price,undefined);
  global.businessApi=async()=>({source:'woocommerce-wizard',base_unit:1.25,positions:[{print_per_item:0,bearbeitung_unit:0,setup_total:0}]});
  await assert.rejects(()=>global.hca103ShopPrice(line),/für alle gewählten Veredelungen 0,00 €/);
  process.stdout.write('Preiszuordnung v0.13.13: OK\n');
})().catch(error=>{console.error(error);process.exitCode=1});
