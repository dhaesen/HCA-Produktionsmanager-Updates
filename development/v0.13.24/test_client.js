const fs=require('fs');
const source=fs.readFileSync(__dirname+'/hca-v01324.js','utf8');
for(const needle of [
  'crm/customers?q=',
  'sales/orders?q=',
  'const r=orderRecipient(o)',
  'productionMachineSlots',
  'renderSeriesMonitor',
  'expectedFile',
  'await changeCentralTask(task.id,1)',
  'sendPatternToMachines=async function',
  'openTransferWorkflow(task)'
]){
  if(!source.includes(needle))throw new Error('Fehlender Client-Prüfpunkt: '+needle);
}
if(!source.includes("placeholder='Name / Standort / Team (z. B. Berlin)'"))throw new Error('Teamnamen-Hinweis fehlt');
console.log('v0.13.24 client static test passed');
