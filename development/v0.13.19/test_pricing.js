const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(__dirname+'/hca-v01319.js','utf8');
let sent=null;
const sandbox={
  window:{},console,
  document:{querySelector:()=>null},
  activeBusinessQuote:null,
  hcaV121LoadWizardConfig:async()=>({}),
  hca103Qty:line=>Number(line.quantity)||1,
  hca103EnrichStep:()=>{},
  businessApi:async(_path,options)=>{
    sent=JSON.parse(options.body);
    return {base_unit:0.22,source:'woocommerce-wizard',positions:[{print_per_item:0.16,setup_total:13.87,bearbeitung_unit:0.04}]};
  },
  alert:()=>{}
};
sandbox.window=sandbox;
vm.createContext(sandbox);
vm.runInContext(source,sandbox);

(async()=>{
  const step={manual_override:'false',technique_label:'LASERGRAVUR',druckart_id:15,cost_id:47,bearbeitung_cost_id:4};
  const line={product_id:'',quantity:500,config:{main_product_id:'5266',product_type:'textile',available_sizes:['XS','S'],sizes:{XS:0,S:0},product_variants:[{product_id:'5266',color:'Grün',sizes:[]}],production_steps:[step]}};
  sandbox.hca1319.normalizeExistingLine(line);
  if(line.config.product_type!=='promotional')throw new Error('Beschädigter Werbeartikel wurde nicht repariert');
  if(line.quantity!==500)throw new Error('Menge wurde bei der Reparatur verändert');
  await sandbox.hca103ShopPrice(line);
  if(sent.product_id!==5266)throw new Error('Hauptartikel-ID wurde bei fehlender Farbvariante nicht verwendet');
  if(sent.quantity!==500)throw new Error('Menge wurde nicht an WooCommerce übertragen');
  if(sent.config.production_steps.length!==1)throw new Error('Automatische Veredelung wurde aussortiert');
  if(step.print_price!==0.16||step.setup_price!==13.87||step.handling_price!==0.04)throw new Error('Preisbestandteile fehlen');
  sandbox.businessApi=async()=>({base_unit:0.22,positions:[{print_per_item:0,setup_total:0,bearbeitung_unit:0}]});
  let rejected=false;
  try{await sandbox.hca103ShopPrice(line)}catch{rejected=true}
  if(!rejected)throw new Error('Irreführende Nullpreis-Antwort wurde akzeptiert');
  console.log('v0.13.19 regression test passed');
})().catch(error=>{console.error(error);process.exit(1)});
