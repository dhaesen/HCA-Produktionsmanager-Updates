const fs=require('fs');
const path=require('path');
const vm=require('vm');

const code=fs.readFileSync(path.join(__dirname,'hca-v01316.js'),'utf8');
new Function(code);

let request;
const sandbox={
  window:null,
  hcaV121LoadWizardConfig:async()=>({areas:[]}),
  hca103Qty:()=>500,
  hca103EnrichStep(_line,step){
    if(!step.druckart_id)throw new Error('Test erwartet bereits gespeicherte IDs');
  },
  hcaV121ApplyAssignment(){throw new Error('Gespeicherte IDs dürfen nicht überschrieben werden');},
  businessApi:async(_path,options)=>{
    request=JSON.parse(options.body);
    return {
      base_unit:0.22,
      source:'woocommerce-wizard',
      positions:[{
        print_per_item:0.16,
        setup_total:13.87,
        setup_total_before_discount:13.87,
        setup_discount:0,
        setup_discount_percent:0,
        bearbeitung_unit:0.04
      }]
    };
  },
  JSON,Number,Date
};
sandbox.window=sandbox;
vm.createContext(sandbox);
vm.runInContext(code,sandbox);

(async()=>{
  const line={
    product_id:5266,
    quantity:500,
    unit_price:0,
    config:{production_steps:[{
      area_id:'front',area_index:0,druckart_id:15,cost_id:47,
      bearbeitung_cost_id:4,colors_count:1,manual_override:false
    }]}
  };
  await sandbox.hca103ShopPrice(line);
  const sent=request.config.production_steps[0];
  if(sent.druckart_id!==15||sent.cost_id!==47||sent.bearbeitung_cost_id!==4){
    throw new Error('WooCommerce-Preis-IDs wurden verändert');
  }
  const step=line.config.production_steps[0];
  if(line.unit_price!==0.22||step.print_price!==0.16||step.setup_price!==13.87||step.handling_price!==0.04||step.unit_price!==0.20){
    throw new Error('Preisbestandteile wurden nicht vollständig übernommen');
  }
  console.log('v0.13.16 pricing regression test passed');
})().catch(error=>{console.error(error);process.exitCode=1});
