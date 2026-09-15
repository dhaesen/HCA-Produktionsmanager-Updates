const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(__dirname+'/hca-v01321.js','utf8');
const fields={
  '#hca136QuoteTiers':{value:'500, 1000, 1500'},
  '#hca136TierStatus':{textContent:''}
};
let rendered=0;
const sandbox={
  window:{},console,crypto:{randomUUID:()=>`id-${Math.random()}`},
  document:{querySelector:selector=>fields[selector]||null},
  activeBusinessQuote:null,hcaEditorDirty:false,
  businessMoney:n=>Number(n).toFixed(2)+' EUR',escapeHtml:String,
  hca103Qty:line=>Number(line.quantity)||1,
  businessQuoteLineAmounts:line=>{
    const qty=Number(line.quantity)||0,steps=line.config.production_steps||[];
    const net=qty*(Number(line.unit_price)||0)+steps.reduce((s,x)=>s+qty*(Number(x.unit_price)||0)+(Number(x.setup_price)||0),0);
    return {net,tax:net*.19,gross:net*1.19};
  },
  renderBusinessQuoteEditor:()=>{rendered++},
  businessApi:async(path,options)=>{
    if(path.includes('/wizard-config'))return {meta_product_id:42,tier_prices:[{qty:500,price:.22},{qty:1000,price:.18},{qty:1500,price:.15}],areas:[],product_details:{name:'Testartikel',main_image:'main.jpg',gallery_images:[],color_images:[{name:'Rot',image:'red.jpg'},{name:'Blau',image:'blue.jpg'}]}};
    if(path==='/business/shop-price'){
      const body=JSON.parse(options.body),q=body.quantity;
      const base=q>=1500?.15:q>=1000?.18:.22,print=q>=1500?.10:q>=1000?.12:.16;
      return {base_unit:base,positions:[{print_per_item:print,setup_total:13.87,bearbeitung_unit:.04}],source:'woocommerce-wizard'};
    }
    throw new Error(path);
  },
  hca103ShopPrice:async line=>{
    const result=await sandbox.businessApi('/business/shop-price',{body:JSON.stringify({product_id:42,quantity:line.quantity})});
    line.unit_price=result.base_unit;
    const step=line.config.production_steps[0],p=result.positions[0];
    step.print_price=p.print_per_item;step.handling_price=p.bearbeitung_unit;step.unit_price=p.print_per_item+p.bearbeitung_unit;step.setup_price=p.setup_total;
    return result;
  },
  businessQuotePayload:()=>({items:(sandbox.activeBusinessQuote.items||[]).map(x=>({...x,config:{...x.config,quote_tier_quantities:[500,1000,1500]}}))})
};
sandbox.window=sandbox;
vm.createContext(sandbox);vm.runInContext(source,sandbox);
(async()=>{
  const base={id:'base',item_type:'product',product_id:42,description:'Testartikel',quantity:500,unit_price:.22,config:{main_product_id:42,product_type:'promotional',sizes:{},production_steps:[{manual_override:false,unit_price:.16,setup_price:13.87}]}};
  sandbox.activeBusinessQuote={items:[base],quantity_tiers:[]};
  await sandbox.buildTierSnapshots();
  const rows=sandbox.activeBusinessQuote.items;
  if(rows.length!==3)throw new Error('Es wurden nicht genau zwei Mengenoptionen angelegt');
  const q1000=rows.find(x=>x.quantity===1000),q1500=rows.find(x=>x.quantity===1500);
  if(q1000?.item_type!=='optional'||q1000.unit_price!==.18||q1000.config.production_steps[0].print_price!==.12)throw new Error('1000er Staffel ist falsch');
  if(q1500?.item_type!=='optional'||q1500.unit_price!==.15||q1500.config.production_steps[0].print_price!==.10)throw new Error('1500er Staffel ist falsch');
  if(q1000.config.production_steps[0].setup_price!==13.87||q1000.config.production_steps[0].handling_price!==.04)throw new Error('Einrichtungs- oder Bearbeitungskosten fehlen');
  if(q1000.config.product_details.color_images.length!==2)throw new Error('Farbvarianten wurden nicht übernommen');
  const payload=sandbox.businessQuotePayload();
  if(payload.items[0].config.quote_quantity_tiers.length!==3)throw new Error('Staffelauswahl für die spätere Auftragsumwandlung fehlt');
  if(payload.items.some(x=>'quote_tier_quantities' in x.config))throw new Error('Veraltete Staffel-Felder wurden nicht entfernt');
  if(rendered!==1)throw new Error('Editor wurde nicht aktualisiert');
  console.log('v0.13.21 client regression test passed');
})().catch(error=>{console.error(error);process.exit(1)});
