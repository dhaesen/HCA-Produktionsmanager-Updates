const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(__dirname+'/hca-v01325.js','utf8');

function host(id){
  return {id,innerHTML:'',querySelector:()=>null,querySelectorAll:()=>[]};
}

(async()=>{
  let formBinds=0,wizardBinds=0,priced=0,rendered=0;
  const orderHost=host('businessOrderLines'),invoiceHost=host('financeInvoiceLines'),quoteHost=host('businessQuoteEditor');
  const line={product_id:'42',quantity:100,config:{production_steps:[]}};
  const sandbox={
    window:null,document:{
      querySelector(selector){return {'#businessOrderLines':orderHost,'#financeInvoiceLines':invoiceHost,'#businessQuoteEditor':quoteHost}[selector]||null},
      createElement(){return {className:'',textContent:'',append(){}}}
    },console,setTimeout,clearTimeout,
    activeBusinessQuote:{items:[line]},HCA103:{orderLines:[line]},financeInvoiceLines:[line],hcaEditorDirty:false,
    hcaUnifiedPositionHtml:(item,index)=>`<article data-bq-line="${index}">${item.product_id}</article>`,
    hcaBindPositionForm(){formBinds++},hcaV121BindWizardControls(){wizardBinds++},financeNewLine:x=>x,
    hca103RenderOrderLines(){},renderFinanceInvoiceLines(){},renderBusinessQuoteEditor(){rendered++},
    hca103ShopPrice:async item=>{priced++;item.unit_price=1.23}
  };
  sandbox.window=sandbox;
  vm.createContext(sandbox);vm.runInContext(source,sandbox);
  if(sandbox.window.HCA01325.lineIndexFrom({dataset:{bqStepAdd:'3'}})!==3)throw new Error('Neue Veredelung wird nicht ihrer Position zugeordnet');
  if(sandbox.window.HCA01325.lineIndexFrom({dataset:{hcaStepMethod:'2:1'}})!==2)throw new Error('Veredelungsänderung wird nicht ihrer Position zugeordnet');
  sandbox.hca103RenderOrderLines();sandbox.renderFinanceInvoiceLines();
  if(!orderHost.innerHTML.includes('42')||!invoiceHost.innerHTML.includes('42'))throw new Error('Gemeinsame Positionsmaske wurde nicht gerendert');
  if(formBinds!==2||wizardBinds!==2)throw new Error('Positions- oder Wizard-Steuerung wurde nicht einheitlich gebunden');
  sandbox.window.HCA01325.schedulePrice(line,()=>{rendered++},quoteHost,'quote:0',0);
  await new Promise(resolve=>setTimeout(resolve,25));
  if(priced!==1||line.unit_price!==1.23||rendered!==1)throw new Error('Automatische Preisaktualisierung wurde nicht ausgeführt');
  console.log('v0.13.25 client regression test passed');
})().catch(error=>{console.error(error);process.exit(1)});
