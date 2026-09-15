const fs=require('fs');
const path=require('path');
const vm=require('vm');
const root=__dirname;
const js=fs.readFileSync(path.join(root,'hca-v01315.js'),'utf8');
const css=fs.readFileSync(path.join(root,'hca-v01315.css'),'utf8');
if(!js.includes("step.print_price=Number(position?.print_per_item)||0"))throw new Error('Druckpreis wird nicht übernommen');
if(!js.includes("step.setup_price=Number(position?.setup_total)||0"))throw new Error('Einrichtungskosten werden nicht übernommen');
if(!js.includes("step.handling_price=Number(position?.bearbeitung_unit)||0"))throw new Error('Bearbeitungskosten werden nicht übernommen');
if(!js.includes('previousOpenQuote'))throw new Error('Alte Angebote werden nicht neu kalkuliert');
if(!css.includes('.size-name')||!css.includes('visibility:visible'))throw new Error('Größenanzeige ist nicht abgesichert');
new Function(js);
const response={base_unit:0.22,source:'woocommerce-wizard',positions:[{print_per_item:0.16,setup_total:13.87,bearbeitung_unit:0.04}]};
const sandbox={window:null,activeBusinessQuote:null,openBusinessQuoteEditor:async()=>{},renderBusinessQuoteEditor(){},
  hca103Qty:()=>500,hcaV121LoadWizardConfig:async()=>{},hcaV121Area:()=>({id:'A'}),hcaV121Assignment:()=>({druckart_id:15,cost_id:47,bearbeitung_cost_id:4}),
  hcaV121ApplyAssignment(step){Object.assign(step,{druckart_id:15,cost_id:47,bearbeitung_cost_id:4})},hca103EnrichStep(){},
  businessApi:async(_url,options)=>{const body=JSON.parse(options.body);if(body.quantity!==500||body.config.production_steps[0].cost_id!==47)throw new Error('Falsche Preisanfrage');return response},
  JSON,Number,String,Date,Error,console,setTimeout,clearTimeout};
sandbox.window=sandbox;
vm.createContext(sandbox);vm.runInContext(js,sandbox);
(async()=>{const line={product_id:5266,unit_price:0,config:{production_steps:[{}]}};await sandbox.hca103ShopPrice(line);const step=line.config.production_steps[0];
  if(line.unit_price!==0.22||step.print_price!==0.16||step.setup_price!==13.87||step.handling_price!==0.04||step.unit_price!==0.20)throw new Error('Preisbestandteile nicht vollständig wiederhergestellt');
  console.log('v0.13.15 rollback tests passed');
})().catch(error=>{console.error(error);process.exitCode=1});
