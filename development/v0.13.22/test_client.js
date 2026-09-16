const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(__dirname+'/hca-v01322.js','utf8');
let rendered=0,saved=0;
const removed=[];
const base={id:'base',item_type:'product',quantity:500,config:{alternative_offer_quantities:[1000],quote_quantity_tiers:[{quantity:1000}],quote_tier_quantities:[1000],quantity_option_group:'g1'}};
const generated={id:'generated',item_type:'optional',quantity:1000,config:{quantity_option_generated:true,quantity_option_group:'g1'}};
const manual={id:'manual',item_type:'optional',description:'Wartungspauschale',config:{}};
const sandbox={
  window:null,console,
  activeBusinessQuote:{quantity_tiers:[1000],items:[base,generated,manual]},
  document:{querySelectorAll:()=>[{remove:()=>removed.push(true)}]},
  renderBusinessQuoteEditor(){rendered++},
  businessQuotePayload(){return {quantity_tiers:[1000],items:sandbox.activeBusinessQuote.items.map(x=>({...x,config:{...x.config}}))}},
  async saveBusinessQuote(){saved++;return 'ok'}
};
sandbox.window=sandbox;
vm.createContext(sandbox);vm.runInContext(source,sandbox);

if(sandbox.activeBusinessQuote.items.length!==2)throw new Error('Automatisch erzeugte Mengenoption wurde nicht entfernt');
if(!sandbox.activeBusinessQuote.items.includes(manual))throw new Error('Manuelle optionale Position wurde fälschlich entfernt');
if(sandbox.activeBusinessQuote.quantity_tiers.length)throw new Error('Globale Mengenstaffel blieb erhalten');
if('alternative_offer_quantities' in base.config||'quote_quantity_tiers' in base.config||'quote_tier_quantities' in base.config)throw new Error('Staffeldaten blieben an der Grundposition erhalten');
sandbox.renderBusinessQuoteEditor();
if(rendered!==1||!removed.length)throw new Error('Mengenstaffel-Steuerelemente wurden beim Rendern nicht entfernt');
const payload=sandbox.businessQuotePayload();
if(payload.quantity_tiers.length||payload.items.some(x=>x.id==='generated'))throw new Error('Mengenstaffel gelangte in die Nutzdaten');
sandbox.saveBusinessQuote().then(result=>{
  if(result!=='ok'||saved!==1)throw new Error('Normales Speichern wurde beeinträchtigt');
  console.log('v0.13.22 client regression test passed');
}).catch(error=>{console.error(error);process.exit(1)});
