const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(__dirname+'/../v0.13.19/hca-v01319.js','utf8');
let sent=null,rendered=0;
const button={disabled:false,textContent:'',onclick:null};
const sandbox={
  window:{},console,
  document:{querySelector:selector=>selector==='#businessQuoteReprice'?button:null},
  activeBusinessQuote:null,
  renderBusinessQuoteEditor:()=>{rendered++},
  hcaV121LoadWizardConfig:async()=>({}),
  hca103Qty:line=>Number(line.quantity)||1,
  hca103EnrichStep:()=>{},
  businessApi:async(_path,options)=>{
    sent=JSON.parse(options.body);
    return {base_unit:0.22,source:'woocommerce-wizard',positions:[{print_per_item:0.16,setup_total:13.87,bearbeitung_unit:0.04}]};
  },
  alert:message=>{throw new Error(message)}
};
sandbox.window=sandbox;
vm.createContext(sandbox);
vm.runInContext(source,sandbox);
(async()=>{
  const step={manual_override:'false',technique_label:'LASERGRAVUR',druckart_id:15,cost_id:47,bearbeitung_cost_id:4};
  const line={product_id:'',quantity:500,config:{main_product_id:'5266',product_type:'textile',available_sizes:['XS','S'],sizes:{XS:0,S:0},product_variants:[{product_id:'5266',color:'Grün',sizes:[]}],production_steps:[step]}};
  sandbox.activeBusinessQuote={items:[line]};
  await sandbox.hca103RepriceQuote();
  if(sent.product_id!==5266||sent.quantity!==500)throw new Error('Button überträgt Hauptartikel-ID oder Menge nicht');
  if(line.config.product_type!=='promotional')throw new Error('Bestandsposition wurde nicht als Werbeartikel repariert');
  if(step.print_price!==0.16||step.setup_price!==13.87||step.handling_price!==0.04)throw new Error('Nicht alle Preisbestandteile wurden übernommen');
  if(rendered!==1)throw new Error('Angebotsformular wurde nach der Kalkulation nicht aktualisiert');
  console.log('v0.13.20 end-to-end button regression test passed');
})().catch(error=>{console.error(error);process.exit(1)});
