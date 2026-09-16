const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync(__dirname+'/hca-v01324.js','utf8');
const noop=()=>{};
const ctx={
  console,setTimeout,clearTimeout,Event:function(){},CSS:{escape:String},
  document:{addEventListener:noop,querySelectorAll:()=>[]},window:{},
  $:()=>null,escapeHtml:s=>String(s),fillStandardRecipient:noop,updateOrderShippingTypeUI:noop,
  openCentralOrderDialog:noop,openCentralOrderEditDialog:async()=>{},syncManualPersonalizationFields:noop,
  sharedMetaForOrder:()=>({}),centralProductionMonitorOrder:null,centralProductionMonitorTasks:[],
  appState:{settings:{workplaceMode:'embroidery'},inventory:[[],[],[],[]]},saveStateSoon:noop,
  workplaceMode:()=> 'embroidery',machines:[{name:'HCA 1',connected:true},{name:'HCA 2',connected:true},{name:'HCA 3',connected:true},{name:'HCA 4',connected:true}],
  renderTransferMachineButtons:noop,openTransferWorkflow:noop,transferSelectionInitialized:false,
  selectedTransferMachines:new Set(),showView:noop,renderCentralProductionMonitor:noop,
  sendPatternToMachines:async()=>{},backToWorkbenchFromTransfer:noop,transferWorkflowTask:null,
  selectedFile:null,physicalTextileProgress:()=>({target:0,done:0,groups:new Map()}),
  centralDueText:()=>'',changeCentralTask:async()=>{},reloadCentralProductionMonitor:async()=>{},
  businessApi:async()=>({items:[]}),alert:noop
};
vm.createContext(ctx);vm.runInContext(source,ctx);
const api=ctx.window.HCA01324;
if(!api)throw new Error('Runtime-API fehlt');
const address=api.orderRecipient({customer_name:'Muster GmbH',shipping:{name:'Muster GmbH',attention:'Max Mustermann',street:'Hauptstraße 12a',zip:'53639',city:'Königswinter',country:'DE'}});
if(address.address_line_1!=='Hauptstraße'||address.house_number!=='12a'||address.city!=='Königswinter')throw new Error('Auftragsadresse wird falsch normalisiert');
const file=api.expectedFile({motif:'Firmenlogo.tap',personalization_name:'Köln Süd'});
if(file!=='Firmenlogo_Köln_Süd.TAP')throw new Error('Personalisierter Dateivorschlag falsch: '+file);
ctx.centralProductionMonitorOrder={id:'O1'};ctx.centralProductionMonitorTasks=[{personalization_name:'Berlin'}];
if(!api.isSeriesOrder())throw new Error('Personalisierter Auftrag nicht als Serie erkannt');
console.log('v0.13.24 client runtime test passed');
