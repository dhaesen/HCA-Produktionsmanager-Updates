const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(__dirname+'/hca-v01318.js','utf8');
let sent=null;
const sandbox={
  window:{},
  console,
  hcaV121LoadWizardConfig:async()=>({}),
  hca103Qty:()=>500,
  hca103EnrichStep:()=>{},
  businessApi:async(_path,options)=>{
    sent=JSON.parse(options.body);
    return {
      base_unit:0.22,
      source:'woocommerce-wizard',
      positions:[{print_per_item:0.16,setup_total:13.87,bearbeitung_unit:0.04}]
    };
  }
};
sandbox.window=sandbox;
vm.createContext(sandbox);
vm.runInContext(source,sandbox);
(async()=>{
  const automatic={manual_override:'false',druckart_id:15,cost_id:47,bearbeitung_cost_id:4};
  const manual={manual_override:'true',print_price:9};
  const line={product_id:5266,quantity:500,config:{production_steps:[automatic,manual]}};
  await sandbox.hca103ShopPrice(line);
  if(sent.config.production_steps.length!==1)throw new Error('Textwert false wurde erneut als manuell aussortiert');
  if(sent.config.production_steps[0].druckart_id!==15)throw new Error('Druckart-ID ging verloren');
  if(automatic.print_price!==0.16||automatic.setup_price!==13.87||automatic.handling_price!==0.04)throw new Error('Preisbestandteile wurden nicht vollständig übernommen');
  if(manual.print_price!==9)throw new Error('Manuelle Position wurde verändert');
  console.log('v0.13.18 client pricing regression test passed');
})().catch(error=>{console.error(error);process.exit(1)});
